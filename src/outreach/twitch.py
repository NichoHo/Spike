"""
Twitch lead finder (OUTREACH.md §6.2 B). Accepted risk, decided 2026-10-14: the Twitch Developer Agreement,
Schedule 1, bans using Twitch API data to target users with commercial offers. The finder uses Spike's own
TWITCH_CLIENT_ID (user's decision, 2026-10-15): if Twitch revokes it, Spike's VOD and community-clip lookups
for clip scoring stop too. It stays off until an admin turns it on.

How it works:
1. Sample (several times a day, at the targets' prime time): Get Streams per saved category and language.
   Live channels only, sorted by viewers, so paging stops once viewers drop below the range. Stored: user id,
   login, viewers, title, category. Samples older than 24 hours are deleted.
2. Find (nightly): average each channel's viewers over its samples, keep the range, then Get Users (bio,
   100 per call) and Get Videos (archives, 1 call per channel), the same hard filters, Gemini fit score, and
   a daily cap. Emails come only from the bio. Never Whispers or chat APIs.
3. Twitch content may be cached 24 hours (Developer Agreement): Twitch lead data is refreshed every night and
   purged when older than a day.
"""

import json
import re
import statistics
import time
import urllib.error
import urllib.parse
import urllib.request
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, List, Optional, Tuple

from src import config
from src.outreach import db, net, youtube

API = "https://api.twitch.tv/helix"
TOKEN_URL = "https://id.twitch.tv/oauth2/token"
SAMPLE_RETENTION_H = 24
MAX_PAGES_PER_SAMPLE = 30  # ponytail: 3,000 streams deep; raise if a big category never reaches the range

_limiter = net.RateLimiter(per_minute=60)  # far under Twitch's bucket; Ratelimit-* headers are obeyed too
_token: Dict[str, Any] = {"value": "", "expires": 0.0}


class TwitchError(RuntimeError):
    pass


def credentials_problem() -> Optional[str]:
    """Why the finder cannot run, or None."""
    if not (config.TWITCH_CLIENT_ID and config.TWITCH_CLIENT_SECRET):
        return "Set TWITCH_CLIENT_ID and TWITCH_CLIENT_SECRET in .env."
    return None


def _app_token(force: bool = False) -> str:
    if not force and _token["value"] and _token["expires"] > time.time():
        return _token["value"]
    data = urllib.parse.urlencode({"client_id": config.TWITCH_CLIENT_ID,
                                   "client_secret": config.TWITCH_CLIENT_SECRET,
                                   "grant_type": "client_credentials"}).encode()
    try:
        with urllib.request.urlopen(urllib.request.Request(TOKEN_URL, data=data), timeout=20) as r:
            tok = json.loads(r.read().decode("utf-8"))
    except urllib.error.HTTPError as e:
        raise TwitchError(f"Twitch rejected the finder's app credentials (HTTP {e.code}).") from None
    _token.update(value=tok["access_token"], expires=time.time() + int(tok.get("expires_in", 3600)) - 120)
    return _token["value"]


def helix(endpoint: str, params: List[Tuple[str, Any]]) -> Dict[str, Any]:
    """GET one Helix endpoint. params is a list of pairs because Helix repeats keys (id=1&id=2)."""
    problem = credentials_problem()
    if problem:
        raise TwitchError(problem)
    url = f"{API}/{endpoint}?{urllib.parse.urlencode([(k, v) for k, v in params if v not in (None, '')])}"
    for attempt in range(2):
        headers = {"Client-Id": config.TWITCH_CLIENT_ID, "Authorization": f"Bearer {_app_token(force=attempt > 0)}"}
        try:
            return net.get_json(url, _limiter, headers=headers)
        except net.HttpError as e:
            if e.status == 401 and attempt == 0:
                continue  # token expired or was revoked early: get a new one once
            raise TwitchError(f"Twitch {endpoint} {e}") from None
    raise AssertionError("unreachable")


def find_category(name: str) -> Optional[Dict[str, str]]:
    """Exact Twitch category name to {id, name}. Get Games matches names exactly."""
    data = helix("games", [("name", name.strip())]).get("data", [])
    return {"id": data[0]["id"], "name": data[0]["name"]} if data else None


# ── 1. Sampling live channels ─────────────────────────────────────────────────

def sample_live(settings: Optional[Dict[str, Any]] = None) -> Dict[str, int]:
    """One sample of every active Twitch search. Keeps channels within half to twice the viewer range, so a
    channel near an edge is averaged fairly instead of dropped on one quiet or busy moment."""
    out = {"searches": 0, "pages": 0, "samples": 0}
    now = db.now_iso()
    for search in db.list_twitch_searches(active_only=True):
        lo, hi = search["min_viewers"] / 2, search["max_viewers"] * 2
        params: List[Tuple[str, Any]] = [("first", 100), ("type", "live"), ("game_id", search["game_id"]),
                                         ("language", search["language"])]
        after = None
        for _ in range(MAX_PAGES_PER_SAMPLE):
            res = helix("streams", params + ([("after", after)] if after else []))
            rows = res.get("data", [])
            out["pages"] += 1
            keep = [r for r in rows if lo <= r.get("viewer_count", 0) <= hi]
            db.add_twitch_samples(search["id"], keep, now)
            out["samples"] += len(keep)
            after = (res.get("pagination") or {}).get("cursor")
            if not rows or rows[-1].get("viewer_count", 0) < lo or not after:
                break  # sorted by viewers: everything after this is below the range
        db.update_twitch_search(search["id"], last_sampled_at=now)
        out["searches"] += 1
    db.purge_twitch_samples(SAMPLE_RETENTION_H)
    return out


# ── 2. Nightly finder ─────────────────────────────────────────────────────────

_DUR_RE = re.compile(r"^(?:(\d+)h)?(?:(\d+)m)?(?:(\d+)s)?$")


def parse_duration(text: str) -> int:
    """Helix video duration ('3h2m10s', '3m21s') to seconds."""
    m = _DUR_RE.match(text or "")
    if not m or not any(m.groups()):
        return 0
    h, mi, s = (int(x or 0) for x in m.groups())
    return h * 3600 + mi * 60 + s


def archive_stats(videos: List[Dict[str, Any]], lookback_days: int, min_stream_h: float) -> Dict[str, Any]:
    """The same activity numbers as YouTube's stream_stats, from Get Videos archives."""
    now = datetime.now(timezone.utc)
    since = now - timedelta(days=lookback_days)
    streams = []
    for v in videos:
        started = youtube._ts(v.get("created_at"))
        dur = parse_duration(v.get("duration", ""))
        if v.get("type", "archive") == "archive" and started and started >= since and dur > 0:
            streams.append((started, dur, v))
    long_streams = [s for s in streams if s[1] >= min_stream_h * 3600]
    counted = long_streams or streams
    latest = max(counted, key=lambda s: s[0], default=None)
    settled = [s for s in counted if s[0] <= now - timedelta(days=1)] or counted
    views = sorted(int(s[2].get("view_count", 0)) for s in settled)
    return {
        "streams_14d": len(long_streams),
        "avg_stream_h": round(sum(s[1] for s in streams) / len(streams) / 3600, 1) if streams else None,
        "last_stream_at": max(s[0] for s in streams).isoformat() if streams else None,
        "vod_views": statistics.median_low(views) if views else None,
        "vod_video_id": latest[2]["id"] if latest else None,
        "vod_url": latest[2].get("url") or f"https://www.twitch.tv/videos/{latest[2]['id']}" if latest else None,
        "vod_title": latest[2].get("title") if latest else None,
        "vod_published_at": latest[0].isoformat() if latest else None,
        "vod_duration_s": float(latest[1]) if latest else None,
        "_titles": [s[2].get("title", "") for s in sorted(streams, key=lambda s: s[0], reverse=True)][:6],
    }


def fetch_users(logins: List[str]) -> Dict[str, Dict[str, Any]]:
    out: Dict[str, Dict[str, Any]] = {}
    for i in range(0, len(logins), 100):
        for u in helix("users", [("login", l) for l in logins[i:i + 100]]).get("data", []):
            out[u["login"].lower()] = u
    return out


def fetch_archives(user_id: str) -> List[Dict[str, Any]]:
    return helix("videos", [("user_id", user_id), ("type", "archive"), ("first", 30)]).get("data", [])


def user_fields(u: Dict[str, Any]) -> Dict[str, Any]:
    login = u["login"].lower()
    bio = u.get("description") or ""
    contacts = youtube.extract_contacts(bio)
    contacts["twitch"] = login  # the channel itself, so YouTube channels linking here find this lead
    return {
        "platform": "twitch", "channel_id": db.channel_key("twitch", login), "url": f"https://www.twitch.tv/{login}",
        "name": u.get("display_name") or login, "handle": login, "thumbnail": u.get("profile_image_url"),
        "description_excerpt": bio[:600], "_description": bio, **contacts,
    }


def qualifies(row: Dict[str, Any], settings: Dict[str, Any]) -> Optional[str]:
    if (row.get("streams_14d") or 0) < settings["min_long_streams_14d"]:
        return "too few long streams"
    if not row.get("vod_video_id"):
        return "no past broadcast to clip (VODs may be off)"
    text = " ".join([row.get("name", ""), row.get("_description", ""), row.get("_category", "")] + row.get("_titles", []))
    if youtube.GAMBLING_RE.search(text):
        return "gambling"
    return None


def run_finder(settings: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
    """Turn the last 24 hours of samples into leads. Returns a summary."""
    settings = settings or db.get_settings()
    summary = {"sampled_channels": 0, "candidates": 0, "skipped_seen": 0, "qualified": 0, "added": 0, "stopped": ""}
    problem = credentials_problem()
    if not settings["twitch_enabled"] or problem:
        summary["stopped"] = problem or "Twitch finder is off"
        return summary
    room = settings["twitch_new_leads_per_day"] - db.count_created_since(youtube.local_midnight_utc_iso(), "twitch")
    if room <= 0:
        summary["stopped"] = "daily Twitch lead cap reached"
        return summary
    searches = {s["id"]: s for s in db.list_twitch_searches()}
    known = db.known_channel_ids("twitch")
    candidates = []
    for ch in db.twitch_sample_summary(SAMPLE_RETENTION_H):
        summary["sampled_channels"] += 1
        search = searches.get(ch["search_id"])
        if not search or not search["min_viewers"] <= ch["avg_viewers"] <= search["max_viewers"]:
            continue  # not marked seen: the average moves as samples come in
        if db.channel_key("twitch", ch["login"]) in known:
            summary["skipped_seen"] += 1
            continue
        candidates.append(ch)
    summary["candidates"] = len(candidates)
    if not candidates:
        return summary

    dropped: Dict[str, str] = {}
    passed = []
    try:
        users = fetch_users([c["login"] for c in candidates])
        for c in candidates:
            u = users.get(c["login"].lower())
            key = db.channel_key("twitch", c["login"])
            if not u:
                dropped[key] = "channel not found"
                continue
            row = {**user_fields(u), **archive_stats(fetch_archives(u["id"]), settings["lookback_days"], settings["min_stream_hours"]),
                   "subscribers_or_viewers": round(c["avg_viewers"]), "language": c["language"] if c["language"] != "other" else None,
                   "twitch_search_id": c["search_id"], "_category": c["category"] or ""}
            row["_titles"] = (row["_titles"] or []) + [t for t in (c["titles"] or "").split("\n") if t][:3]
            reason = qualifies(row, settings)
            if reason:
                dropped[key] = reason
            else:
                passed.append(row)
    except TwitchError as e:
        db.mark_seen("twitch", dropped)
        summary["stopped"] = str(e)
        return summary
    summary["qualified"] = len(passed)

    passed = passed[:room * 2]
    fits = youtube.score_fit(passed)
    for row in passed:
        fit = fits.get(row["channel_id"])
        row["fit_score"] = fit.fit_score if fit else None
        row["fit_reason"] = fit.reason if fit else "Not scored (LLM unavailable)"
    passed.sort(key=lambda r: -(r["fit_score"] if r["fit_score"] is not None else -1))
    for row in passed:
        if summary["added"] >= room:
            break
        if row["fit_score"] is not None and row["fit_score"] < settings["min_fit_score"]:
            dropped[row["channel_id"]] = f"fit score {row['fit_score']}"
            continue
        twin = db.find_streamer(row["twitch"], row.get("kick"))
        if twin or db.is_opted_out(row.get("email"), *db.lead_keys(row)):
            dropped[row["channel_id"]] = f"same streamer as lead #{twin['id']}" if twin else "opted out on another platform"
            continue
        lead = {k: v for k, v in row.items() if not k.startswith("_") and (v is not None or k not in db.CONTACT_COLUMNS)}
        if row.get("email"):
            lead["email_source"] = "api"
        lead["api_fetched_at"] = db.now_iso()
        if db.insert_lead(lead):
            summary["added"] += 1
    db.mark_seen("twitch", dropped)
    return summary


# ── 3. 24-hour cache: nightly refresh and purge ───────────────────────────────

def refresh_leads(settings: Optional[Dict[str, Any]] = None) -> Dict[str, int]:
    """Re-fetch every Twitch lead's API data so none is older than a day. Leads added by hand hold none."""
    settings = settings or db.get_settings()
    out = {"refreshed": 0, "gone": 0}
    if credentials_problem():
        return out
    with db.connect() as conn:
        leads = [dict(r) for r in conn.execute(
            "SELECT * FROM leads WHERE platform = 'twitch' AND api_fetched_at IS NOT NULL "
            "AND status NOT IN ('rejected', 'opted_out')")]
    if not leads:
        return out
    viewers = {r["login"].lower(): r["avg_viewers"] for r in db.twitch_sample_summary(SAMPLE_RETENTION_H)}
    try:
        users = fetch_users([l["handle"] for l in leads])
        now = db.now_iso()
        for lead in leads:
            u = users.get(lead["handle"])
            if not u:
                youtube.purge_api_fields(lead)
                out["gone"] += 1
                continue
            fields = {k: v for k, v in user_fields(u).items()
                      if not k.startswith("_") and k not in ("platform", "channel_id", "url")}
            if lead["contacts_manual"]:
                for c in db.CONTACT_COLUMNS:
                    fields.pop(c, None)
            elif fields.get("email") and fields["email"] != lead["email"]:
                fields["email_source"] = "api"
            fields["subscribers_or_viewers"] = round(viewers[lead["handle"]]) if lead["handle"] in viewers else None
            if lead["status"] in youtube.ACTIVITY_STATUSES:
                act = archive_stats(fetch_archives(u["id"]), settings["lookback_days"], settings["min_stream_hours"])
                fields.update({k: v for k, v in act.items() if not k.startswith("_") and (k not in youtube.VOD_COLUMNS + ("vod_url",) or not lead["vod_manual"])})
            else:  # past approval nothing here is needed again: the clip's stream date was copied to clip_stream_at
                fields.update({c: None for c in youtube.STAT_COLUMNS + youtube.VOD_COLUMNS})
            fields["api_fetched_at"] = now
            db.update_lead(lead["id"], **fields)
            out["refreshed"] += 1
    except TwitchError as e:
        db.log(f"Twitch refresh stopped: {e}", "warning")
    return out
