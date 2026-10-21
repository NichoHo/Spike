"""
Outreach dashboard routes (/outreach, OUTREACH.md §6.5).
Members review leads and clips. Only admins send email, connect Google, or change finder settings (§6.7).
"""

import re
import time
import urllib.parse
from datetime import datetime, timedelta
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.concurrency import run_in_threadpool
from fastapi.responses import HTMLResponse, RedirectResponse
from starlette.status import HTTP_303_SEE_OTHER, HTTP_403_FORBIDDEN

from src import config
from src.db import list_review_clips
from src.outreach import daemon, db, google, service, twitch
from src.web.auth import get_current_user, require_admin

router = APIRouter()

# In the order a lead moves through them
TABS = {
    "review": ("Review", ["found"]),
    "contact": ("Needs email", ["needs_contact"]),
    "email": ("Ready to send", ["email_ready"]),
    "sent": ("Sent", ["email_ready", "sent", "followup_1", "followup_2", "bounced"]),
    "replies": ("Replies", ["replied"]),
    "progress": ("Sample clips", ["clip_wanted", "clip_queued", "clip_ready", "clip_failed", "clip_approved"]),
    "clients": ("Clients", ["trial", "client"]),
    "stats": ("Stats", []),
    "settings": ("Settings", []),
}
ADMIN_ACTIONS = {"send", "cancel_send", "regenerate"}
INT_SETTINGS = {  # name: (min, max)
    "run_hour": (0, 23), "max_searches_per_run": (1, 60), "new_leads_per_day": (1, 200), "lookback_days": (3, 30),
    "min_long_streams_14d": (0, 14), "min_fit_score": (0, 100), "max_shorts_14d": (0, 200), "search_calls_per_day": (0, 100),
    "units_per_day": (100, 1000000), "units_reserved_for_spike": (0, 1000000), "trial_clips_per_day": (0, 20),
    "trial_max_vod_s": (1800, 43200), "emails_per_day": (1, 100), "send_gap_min": (1, 120),
    "followup_1_days": (1, 30), "followup_2_days": (2, 60), "drive_retention_days": (1, 90),
    "lead_retention_days": (30, 365), "min_views": (0, 10000000), "twitch_new_leads_per_day": (0, 100),
}
FLOAT_SETTINGS = {"min_stream_hours": (0.5, 12.0)}
TEXT_SETTINGS = ("sender_name", "company_name", "proof_url", "rate_default", "rate_sea", "monthly_cap")
TEMPLATE_SETTINGS = tuple(k for k in db.DEFAULT_SETTINGS if k.startswith("tpl_"))


def same_origin(request: Request) -> None:
    """Block cross-site form posts. Tailscale adds identity headers to any request the browser makes,
    so without this a page on another site could make a team member's browser send email."""
    origin = request.headers.get("origin") or request.headers.get("referer")
    if not origin:
        return
    allowed = {request.headers.get("host"), request.headers.get("x-forwarded-host"), urllib.parse.urlsplit(config.PUBLIC_URL).netloc}
    if urllib.parse.urlsplit(origin).netloc not in allowed:
        raise HTTPException(HTTP_403_FORBIDDEN, "Cross-site request blocked. If this is Spike's own address, set SPIKE_PUBLIC_URL to it.")


def _back(tab: str, notice: str = "", error: str = "") -> RedirectResponse:
    q = {"tab": tab if tab in TABS else "review"}
    if notice:
        q["notice"] = notice[:300]
    if error:
        q["error"] = error[:300]
    return RedirectResponse(f"/outreach?{urllib.parse.urlencode(q)}", status_code=HTTP_303_SEE_OTHER)


def _ids(form) -> List[int]:
    return [int(v) for v in form.getlist("ids") if str(v).isdigit()]


def _next_followup(lead: Dict[str, Any], first: Dict[str, Any], settings: Dict[str, Any]) -> Optional[str]:
    if lead["followups_stopped"] or not settings["followups_enabled"] or not first.get("sent_at"):
        return None
    days = {"sent": settings["followup_1_days"], "followup_1": settings["followup_2_days"]}.get(lead["status"])
    return (datetime.fromisoformat(first["sent_at"]) + timedelta(days=days)).isoformat() if days else None


def _tab_leads(tab: str, settings: Dict[str, Any]) -> List[Dict[str, Any]]:
    statuses = TABS[tab][1]
    if not statuses:
        return []
    leads = db.list_leads(statuses, order="fit" if tab in ("review", "contact") else "recent")
    msgs = db.messages_for(l["id"] for l in leads)
    for l in leads:
        l["msgs"] = msgs.get(l["id"], {})
        first = l["msgs"].get("first") or {}
        l["queued"] = first.get("status") in ("queued", "sending")
        l["next_followup"] = _next_followup(l, first, settings)
    if tab == "email":
        leads = [l for l in leads if not l["queued"]]
    elif tab == "sent":
        leads = [l for l in leads if l["status"] != "email_ready" or l["queued"]]
    return leads


def _finder_state(settings: Dict[str, Any]) -> str:
    """starting | running | done | failed | stuck | '' (never run). stuck: asked or running, but no outreach process."""
    status = settings["finder_status"]
    if settings["run_now"] or status == "running":
        if not daemon.is_running():
            return "stuck"
        return "running" if status == "running" else "starting"
    return status


@router.get("/outreach", response_class=HTMLResponse)
async def outreach_page(request: Request, tab: str = "review", notice: str = "", error: str = "",
                        user: Dict[str, Any] = Depends(get_current_user)):
    return _render(request, user, tab, notice, error)


def _render(request: Request, user: Dict[str, Any], tab: str, notice: str = "", error: str = "",
            add_form: Optional[Dict[str, str]] = None, status_code: int = 200):
    """The Outreach page. add_form re-opens the Add lead dialog with what was typed (never put in the URL:
    it holds an email address)."""
    tab = tab if tab in TABS else "review"
    service.sync_clips()  # cheap, and keeps "Clips in progress" current without waiting for the daemon
    settings = db.get_settings()
    counts = db.status_counts()
    leads = _tab_leads(tab, settings)
    tab_counts = {k: len(_tab_leads(k, settings)) if k in ("email", "sent") else sum(counts.get(s, 0) for s in v[1])
                  for k, v in TABS.items() if v[1]}
    ctx: Dict[str, Any] = {
        "page_title": "Outreach", "active_nav": "outreach", "user": user, "tab": tab, "tabs": TABS,
        "tab_counts": tab_counts, "leads": leads, "settings": settings, "notice": notice, "error": error,
        "review_count": len(list_review_clips(status="ready")), "is_admin": user.get("role") == "admin",
        "blockers": service.sending_blockers(settings) if tab in ("email", "sent", "settings") else [],
        "google_account": db.get_google_account(),
        "add_form": add_form or {},
        "finder_state": _finder_state(settings),
    }
    if tab == "stats":
        ctx["stats"] = service.stats()
    if tab == "settings":
        ctx.update(
            searches=db.list_searches(), log=db.recent_log(20), oauth_configured=google.oauth_configured(),
            key_set=google.encryption_key_set(), redirect_uri=google.redirect_uri(),
            quota={"search": db.quota_used("search"), "units": db.quota_used("units")},
            youtube_key=bool(config.YOUTUBE_API_KEY), template_keys=TEMPLATE_SETTINGS,
            twitch_searches=db.list_twitch_searches(), twitch_problem=twitch.credentials_problem(),
        )
    return request.app.state.templates.TemplateResponse(request=request, name="pages/outreach.html", context=ctx,
                                                        status_code=status_code)


ADD_FIELDS = ("url", "email", "stream_url", "name", "language", "notes", "whop", "tab")


@router.post("/outreach/leads/add", dependencies=[Depends(same_origin)])
async def add_lead(request: Request, user: Dict[str, Any] = Depends(get_current_user)):
    """Add a lead found outside the finder (Whop, Kick, referrals). yt-dlp and API calls run off the event loop."""
    form = await request.form()
    data = {k: str(form.get(k, "")).strip()[:500] for k in ADD_FIELDS}
    try:
        lead = await run_in_threadpool(
            service.add_lead, data["url"], data["email"], data["stream_url"], data["name"], data["language"],
            data["notes"], bool(data["whop"]))
    except service.OutreachError as e:
        return _render(request, user, data["tab"], error=str(e), add_form=data, status_code=400)
    if lead["status"] == "approved":
        return _back("email", notice=f"Added {lead['name']}. Its email draft appears here within a minute.")
    return _back("contact", notice=f"Added {lead['name']}. Add an email to queue its trial clip.")


@router.post("/outreach/leads/bulk", dependencies=[Depends(same_origin)])
async def bulk_action(request: Request, user: Dict[str, Any] = Depends(get_current_user)):
    form = await request.form()
    action, tab, ids = form.get("action", ""), form.get("tab", "review"), _ids(form)
    if action in ADMIN_ACTIONS and user.get("role") != "admin":
        raise HTTPException(HTTP_403_FORBIDDEN, "Only admins can send or regenerate emails.")
    if action == "save_drafts" or action == "send":
        # Edits on the Ready to email screen are saved before anything is queued
        for lid in ([int(k.split("_", 1)[1]) for k in form if k.startswith("body_")] if action == "save_drafts" else ids):
            if f"body_{lid}" in form:
                try:
                    service.save_draft(lid, form.get(f"to_{lid}", ""), form.get(f"subject_{lid}", ""), form.get(f"body_{lid}", ""))
                except service.OutreachError as e:
                    return _back(tab, error=str(e))
        if action == "save_drafts":
            return _back(tab, notice="Drafts saved.")
    if not ids:
        return _back(tab, error="Select at least one row first.")
    try:
        if action == "approve":
            r = service.approve(ids)
            return _back(tab, notice=f"{r['approved']} approved, drafts appear in Ready to send within a minute. "
                         f"{r['needs_contact']} need an email first"
                         + (f", {r['opted_out']} had opted out" if r["opted_out"] else "") + ".")
        if action == "reject":
            return _back(tab, notice=f"{service.reject(ids, form.get('reason', ''))} rejected.")
        if action == "snooze":
            return _back(tab, notice=f"{service.snooze(ids)} snoozed for 30 days.")
        if action == "make_clip":
            return _back("progress", notice=f"{service.request_clips(ids)} sample clip(s) queued. "
                         "Approve each one in the clip editor, then send the link in your Gmail reply.")
        if action == "retry_clip":
            return _back(tab, notice=f"{service.retry_clip(ids)} Spike job(s) queued again.")
        if action == "send":
            r = service.queue_send(ids)
            msg = f"{r['queued']} email(s) queued, sent {db.get_settings()['send_gap_min']} min apart."
            return _back("sent" if r["queued"] else tab, notice=msg, error="Skipped: " + "; ".join(r["skipped"]) if r["skipped"] else "")
        if action == "cancel_send":
            return _back(tab, notice=f"{service.cancel_send(ids)} send(s) cancelled. Back in Ready to email.")
        if action == "regenerate":
            r = service.draft_emails(None, ids)
            return _back(tab, notice=f"{r['drafted']} draft(s) rewritten from the template.")
        if action == "stop_followups":
            return _back(tab, notice=f"Follow-ups stopped for {service.stop_followups(ids)} lead(s).")
        if action in ("trial", "client"):
            return _back("clients", notice=f"{service.mark(ids, action)} marked as {action}.")
        if action == "opt_out":
            return _back(tab, notice=f"{service.opt_out(ids)} opted out permanently.")
    except service.OutreachError as e:
        return _back(tab, error=str(e))
    return _back(tab, error="Unknown action.")


@router.post("/outreach/leads/{lead_id}/contact", dependencies=[Depends(same_origin)])
async def save_contact(lead_id: int, request: Request, user: Dict[str, Any] = Depends(get_current_user)):
    form = await request.form()
    try:
        lead = service.save_contact(lead_id, form.get("email", ""),
                                    {k: form.get(k, "") for k in ("instagram", "x", "tiktok", "discord", "website") if k in form})
    except service.OutreachError as e:
        return _back("contact", error=str(e))
    moved = lead["status"] == "approved"
    return _back("contact", notice=f"Saved {lead['name']}." + (" Its email draft appears in Ready to send." if moved else ""))


@router.post("/outreach/leads/{lead_id}/client", dependencies=[Depends(same_origin)])
async def save_client(lead_id: int, request: Request, user: Dict[str, Any] = Depends(require_admin)):
    form = await request.form()
    try:
        service.save_client(lead_id, form.get("model", "A"), form.get("cap", ""), form.get("start", ""))
    except service.OutreachError as e:
        return _back("clients", error=str(e))
    return _back("clients", notice="Client terms saved.")


# ── Finder settings (admin) ───────────────────────────────────────────────────

@router.post("/outreach/run-now", dependencies=[Depends(same_origin)])
async def run_now(user: Dict[str, Any] = Depends(require_admin)):
    settings = db.get_settings()
    has_twitch = settings["twitch_enabled"] and any(s["active"] for s in db.list_twitch_searches())
    if not db.list_searches(active_only=True) and not has_twitch:
        return _back("settings", error="Add a topic first: the finder only looks for the topics you add.")
    db.set_settings({"run_now": 1})
    return _back("settings")


@router.post("/outreach/settings", dependencies=[Depends(same_origin)])
async def save_settings(request: Request, user: Dict[str, Any] = Depends(require_admin)):
    form = await request.form()
    values: Dict[str, Any] = {}
    try:
        for key, (lo, hi) in INT_SETTINGS.items():
            if key in form:
                values[key] = min(hi, max(lo, int(form[key])))
        for key, (lo, hi) in FLOAT_SETTINGS.items():
            if key in form:
                values[key] = min(hi, max(lo, float(form[key])))
    except ValueError:
        return _back("settings", error="Numbers only in the number fields.")
    for key in TEXT_SETTINGS + TEMPLATE_SETTINGS:
        if key in form:
            values[key] = str(form[key]).replace("\r\n", "\n").strip()[:8000]
    if "proof_url" in values and values["proof_url"] and not re.match(r"^https?://\S+$", values["proof_url"]):
        return _back("settings", error="The proof link must start with http:// or https://.")
    if "followup_1_days" in values and "followup_2_days" in values and values["followup_2_days"] <= values["followup_1_days"]:
        return _back("settings", error="Follow-up 2 must come after follow-up 1.")
    if form.get("form") == "limits":
        values["followups_enabled"] = 1 if form.get("followups_enabled") else 0
    if form.get("form") == "twitch":
        hours = [h.strip() for h in str(form.get("twitch_sample_hours", "")).split(",") if h.strip()]
        if not hours or not all(h.isdigit() and 0 <= int(h) <= 23 for h in hours):
            return _back("settings", error="Sample hours must be whole hours from 0 to 23, separated by commas.")
        values["twitch_sample_hours"] = ",".join(str(int(h)) for h in sorted(set(hours), key=int))
        values["twitch_enabled"] = 1 if form.get("twitch_enabled") else 0
        if values["twitch_enabled"] and twitch.credentials_problem():
            return _back("settings", error=twitch.credentials_problem())
    db.set_settings(values)
    return _back("settings", notice="Settings saved.")


_trending: Dict[str, Any] = {"at": 0.0, "names": []}


@router.get("/outreach/trending")
async def trending_topics(user: Dict[str, Any] = Depends(get_current_user)):
    """Top Twitch categories right now, as topic ideas. YouTube has no trending-games endpoint, so Twitch only."""
    if time.time() - _trending["at"] > 3600:
        try:
            data = await run_in_threadpool(twitch.helix, "games/top", [("first", 20)])
        except Exception as e:  # missing credentials or an API failure: the page keeps its fixed ideas
            return {"topics": [], "error": str(e)}
        _trending.update(at=time.time(), names=[g["name"] for g in data.get("data", []) if g["name"].lower() != "just chatting"])
    return {"topics": _trending["names"], "error": ""}


@router.post("/outreach/searches", dependencies=[Depends(same_origin)])
async def add_search(request: Request, user: Dict[str, Any] = Depends(require_admin)):
    form = await request.form()
    query = (form.get("query") or "").strip()[:200]
    lang = (form.get("language") or "").strip().lower()[:8]
    region = (form.get("region") or "").strip().upper()[:2]
    if not query:
        return _back("settings", error="Type a topic first.")
    if lang and not re.match(r"^[a-z]{2}(-[A-Za-z]{2,4})?$", lang):
        return _back("settings", error="Language must be a 2-letter code like en or id.")
    if region and not re.match(r"^[A-Z]{2}$", region):
        return _back("settings", error="Region must be a 2-letter country code like ID or US.")
    kind = form.get("kind") if form.get("kind") in ("live", "reupload") else "live"
    try:
        lo, hi = int(form.get("min_size") or 0), int(form.get("max_size") or 300000)
        vlo = int(form.get("min_views") or 0)
        vhi = int(form["max_views"]) if form.get("max_views") else None
    except ValueError:
        return _back("settings", error="Sizes and views must be whole numbers.")
    if lo > hi or (vhi is not None and vlo > vhi):
        return _back("settings", error="A minimum is above its maximum.")
    db.add_search(query, lang, region, lo, hi, kind, vlo, vhi)
    return _back("settings", notice=f"Added '{query}'. Run the finder now, or wait for tonight's run.")


@router.post("/outreach/searches/{search_id}/toggle", dependencies=[Depends(same_origin)])
async def toggle_search(search_id: int, user: Dict[str, Any] = Depends(require_admin)):
    s = next((s for s in db.list_searches() if s["id"] == search_id), None)
    if s:
        db.update_search(search_id, active=0 if s["active"] else 1)
    return _back("settings")


@router.post("/outreach/twitch/searches", dependencies=[Depends(same_origin)])
async def add_twitch_search(request: Request, user: Dict[str, Any] = Depends(require_admin)):
    """A Twitch category + language to sample. The category name is resolved to its id once, here."""
    form = await request.form()
    name = (form.get("category") or "").strip()[:100]
    lang = (form.get("language") or "").strip().lower()[:8]
    if lang and not re.match(r"^([a-z]{2}|other)$", lang):
        return _back("settings", error="Language must be a 2-letter code like id or en.")
    try:
        lo, hi = int(form.get("min_viewers") or 50), int(form.get("max_viewers") or 1000)
    except ValueError:
        return _back("settings", error="Viewer counts must be whole numbers.")
    if not 1 <= lo <= hi:
        return _back("settings", error="Minimum viewers must be at least 1 and not above the maximum.")
    if not name and not lang:
        return _back("settings", error="Pick a category, a language, or both: all of Twitch is too broad.")
    game = None
    if name:
        try:
            game = await run_in_threadpool(twitch.find_category, name)
        except twitch.TwitchError as e:
            return _back("settings", error=str(e))
        if not game:
            return _back("settings", error=f"No Twitch category is named exactly '{name}'.")
    db.add_twitch_search(game and game["id"], game and game["name"], lang, lo, hi)
    return _back("settings", notice=f"Saved Twitch search: {game['name'] if game else 'all categories'}"
                 + (f", {lang}" if lang else "") + ". Samples start at the next listed hour.")


@router.post("/outreach/twitch/searches/{search_id}/toggle", dependencies=[Depends(same_origin)])
async def toggle_twitch_search(search_id: int, user: Dict[str, Any] = Depends(require_admin)):
    s = next((s for s in db.list_twitch_searches() if s["id"] == search_id), None)
    if s:
        db.update_twitch_search(search_id, active=0 if s["active"] else 1)
    return _back("settings")


@router.post("/outreach/twitch/searches/{search_id}/delete", dependencies=[Depends(same_origin)])
async def delete_twitch_search(search_id: int, user: Dict[str, Any] = Depends(require_admin)):
    db.delete_twitch_search(search_id)
    return _back("settings", notice="Twitch search deleted with its samples. Leads it found are kept.")


@router.post("/outreach/twitch/sample-now", dependencies=[Depends(same_origin)])
async def twitch_sample_now(user: Dict[str, Any] = Depends(require_admin)):
    problem = twitch.credentials_problem()
    if problem:
        return _back("settings", error=problem)
    db.set_settings({"twitch_sample_now": 1})
    return _back("settings", notice="Sampling live Twitch channels within a minute. Run the finder after a few samples.")


@router.post("/outreach/searches/{search_id}/delete", dependencies=[Depends(same_origin)])
async def delete_search(search_id: int, user: Dict[str, Any] = Depends(require_admin)):
    db.delete_search(search_id)
    return _back("settings", notice="Topic deleted. Streamers it found are kept.")


# ── Google account (admin) ────────────────────────────────────────────────────

@router.get("/outreach/google/connect")
async def google_connect(user: Dict[str, Any] = Depends(require_admin)):
    if not google.oauth_configured():
        return _back("settings", error="Set GOOGLE_OAUTH_CLIENT_ID and GOOGLE_OAUTH_CLIENT_SECRET in .env first.")
    if not google.encryption_key_set():
        return _back("settings", error="Set SPIKE_ENCRYPTION_KEY in .env first. Gmail tokens are never stored under the default key.")
    return RedirectResponse(google.start_auth(user.get("id")), status_code=HTTP_303_SEE_OTHER)


@router.get("/outreach/google/callback")
async def google_callback(state: str = "", code: str = "", error: Optional[str] = None,
                          user: Dict[str, Any] = Depends(require_admin)):
    if error or not code:
        return _back("settings", error=f"Google sign-in was cancelled ({error or 'no code'}).")
    try:
        email = google.finish_auth(state, code)
    except google.GoogleError as e:
        return _back("settings", error=str(e))
    return _back("settings", notice=f"Connected {email}. Emails are sent from this address.")


@router.post("/outreach/google/disconnect", dependencies=[Depends(same_origin)])
async def google_disconnect(user: Dict[str, Any] = Depends(require_admin)):
    google.revoke()
    return _back("settings", notice="Google account disconnected. Queued emails wait until one is connected.")
