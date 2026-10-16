"""
Spike: Sources management routes.
Blueprint §10.3, §10.5, §10.6 & DESIGN.md §10.5, §10.6.
"""

import json
import re
import time
import urllib.parse
import urllib.request
from concurrent.futures import ThreadPoolExecutor
from typing import Dict, Any, List
from fastapi import APIRouter, Request, Depends, Form, HTTPException
from fastapi.responses import HTMLResponse, RedirectResponse
from starlette.status import HTTP_404_NOT_FOUND, HTTP_303_SEE_OTHER

from src.db import (
    get_connection,
    get_json_column,
    set_json_column,
    list_sources,
    get_source,
    create_source,
    update_source,
    delete_source,
    list_review_clips,
)
from src.concepts import CONCEPT_LABELS, CONCEPTS, DEFAULT_AUTO_CONCEPTS
from src.config import (
    CREATOR_TYPES, HUMOR_STYLES, VIDEOS_DIR, YOUTUBE_API_KEY, TWITCH_CLIENT_ID, TWITCH_CLIENT_SECRET,
)
from src.web.auth import get_current_user


router = APIRouter()

_YT_ID_RE = re.compile(r"^UC[\w-]{22}$")
_LOOKUP_TTL = 600
# ponytail: in-process cache; YouTube search costs 100 quota units of 10k/day
_lookup_cache: Dict[tuple, tuple] = {}
_twitch_token = {"value": "", "expires": 0.0}


def _get_json(url: str, headers: Dict[str, str] = None, data: bytes = None) -> Dict[str, Any]:
    req = urllib.request.Request(url, data=data, headers={"User-Agent": "Mozilla/5.0", **(headers or {})})
    with urllib.request.urlopen(req, timeout=8) as r:
        return json.loads(r.read().decode())


def _youtube_lookup(q: str) -> List[Dict[str, str]]:
    def call(endpoint: str, **params) -> Dict[str, Any]:
        params["key"] = YOUTUBE_API_KEY
        return _get_json(f"https://www.googleapis.com/youtube/v3/{endpoint}?{urllib.parse.urlencode(params)}")

    def row(channel_id: str, sn: Dict[str, Any]) -> Dict[str, str]:
        return {
            "id": channel_id,
            "name": sn.get("title") or sn.get("channelTitle", ""),
            "sub": sn.get("customUrl", ""),
            "thumb": (sn.get("thumbnails", {}).get("default") or {}).get("url", ""),
        }

    def with_stats(rows: List[Dict[str, str]]) -> List[Dict[str, str]]:
        # search.list has no statistics; one batched channels.list (1 unit) adds them
        if rows:
            items = call("channels", part="statistics", id=",".join(r["id"] for r in rows), maxResults=len(rows)).get("items", [])
            stats = {it["id"]: it.get("statistics", {}) for it in items}
            for r in rows:
                st = stats.get(r["id"], {})
                if not st.get("hiddenSubscriberCount") and "subscriberCount" in st:
                    r["followers"] = int(st["subscriberCount"])
        return rows

    if _YT_ID_RE.match(q):
        return with_stats([row(it["id"], it["snippet"]) for it in call("channels", part="snippet", id=q).get("items", [])])

    out: List[Dict[str, str]] = []
    if " " not in q:
        handle = q if q.startswith("@") else "@" + q
        out = [row(it["id"], it["snippet"]) for it in call("channels", part="snippet", forHandle=handle).get("items", [])]
    found = call("search", part="snippet", type="channel", q=q, maxResults=5).get("items", [])
    seen = {r["id"] for r in out}
    for it in found:
        cid = it["snippet"]["channelId"]
        if cid not in seen:
            out.append(row(cid, it["snippet"]))
            seen.add(cid)
    return with_stats(out)


def _twitch_lookup(q: str) -> List[Dict[str, str]]:
    if _twitch_token["expires"] < time.time():
        tok = _get_json(
            "https://id.twitch.tv/oauth2/token",
            data=urllib.parse.urlencode({
                "client_id": TWITCH_CLIENT_ID,
                "client_secret": TWITCH_CLIENT_SECRET,
                "grant_type": "client_credentials",
            }).encode(),
        )
        _twitch_token.update(value=tok["access_token"], expires=time.time() + tok.get("expires_in", 3600) - 60)
    headers = {"Client-ID": TWITCH_CLIENT_ID, "Authorization": f"Bearer {_twitch_token['value']}"}
    login = q.lstrip("@")
    base = "https://api.twitch.tv/helix"
    # external_id for Twitch is the login name (the watcher builds twitch.tv/<login> URLs).
    # Helix search ranks poorly for exact names, so look the exact login up first.
    exact = _get_json(f"{base}/users?{urllib.parse.urlencode({'login': login})}", headers=headers).get("data", [])
    found = _get_json(f"{base}/search/channels?{urllib.parse.urlencode({'query': login, 'first': 5})}", headers=headers).get("data", [])
    out = [
        {"id": u["login"], "bid": u["id"], "name": u["display_name"], "sub": f"twitch.tv/{u['login']}", "thumb": u.get("profile_image_url", "")}
        for u in exact
    ]
    seen = {r["id"] for r in out}
    out += [
        {"id": it["broadcaster_login"], "bid": it["id"], "name": it["display_name"], "sub": f"twitch.tv/{it['broadcaster_login']}", "thumb": it.get("thumbnail_url", "")}
        for it in found
        if it["broadcaster_login"] not in seen
    ]

    def followers(r: Dict[str, str]) -> None:
        try:
            r["followers"] = _get_json(f"{base}/channels/followers?broadcaster_id={r['bid']}&first=1", headers=headers)["total"]
        except Exception:
            pass  # count is cosmetic; keep the result without it

    with ThreadPoolExecutor(max_workers=5) as pool:
        list(pool.map(followers, out))
    for r in out:
        del r["bid"]
    return out


@router.get("/sources/lookup")
def lookup_channel(
    kind: str,
    q: str,
    user: Dict[str, Any] = Depends(get_current_user),
):
    """Autocomplete: name, handle, or channel ID -> matching channels."""
    q = q.strip()
    if kind not in ("youtube", "twitch") or not 2 <= len(q) <= 100:
        return {"results": []}
    if kind == "youtube" and not YOUTUBE_API_KEY:
        return {"results": [], "error": "YOUTUBE_API_KEY is not set."}
    if kind == "twitch" and not (TWITCH_CLIENT_ID and TWITCH_CLIENT_SECRET):
        return {"results": [], "error": "Twitch credentials are not set."}

    key = (kind, q.lower())
    hit = _lookup_cache.get(key)
    if hit and hit[0] > time.time():
        return {"results": hit[1]}
    try:
        results = _youtube_lookup(q) if kind == "youtube" else _twitch_lookup(q)
    except Exception as e:
        print(f"  [sources] lookup failed ({kind}, {q!r}): {e}")
        return {"results": [], "error": "Lookup failed. Enter the ID manually."}
    _lookup_cache[key] = (time.time() + _LOOKUP_TTL, results)
    return {"results": results}


@router.get("/sources", response_class=HTMLResponse)
async def sources_list(
    request: Request,
    user: Dict[str, Any] = Depends(get_current_user),
):
    templates = request.app.state.templates
    sources = [dict(s) for s in list_sources()]
    review_count = len(list_review_clips(status="ready"))

    return templates.TemplateResponse(
        request=request,
        name="pages/sources.html",
        context={
            "page_title": "Sources",
            "active_nav": "sources",
            "page_width": "wide",
            "user": user,
            "sources": sources,
            "review_count": review_count,
        },
    )


@router.get("/sources/new", response_class=HTMLResponse)
async def new_source_form(
    request: Request,
    user: Dict[str, Any] = Depends(get_current_user),
):
    templates = request.app.state.templates
    review_count = len(list_review_clips(status="ready"))

    return templates.TemplateResponse(
        request=request,
        name="pages/source_edit.html",
        context={
            "page_title": "Add Source",
            "active_nav": "sources",
            "page_width": "narrow",
            "user": user,
            "source": None,
            "review_count": review_count,
            "concepts": [(c, CONCEPT_LABELS[c]) for c in CONCEPTS],
            "auto_concepts": DEFAULT_AUTO_CONCEPTS,
        },
    )


@router.post("/sources/new")
async def create_source_action(
    kind: str = Form("twitch"),
    external_id: str = Form(...),
    display_name: str = Form(...),
    permission: str = Form("review"),
    auto_process: bool = Form(False),
    caption_style: str = Form("bold_pop"),
    music: bool = Form(False),
    default_music_mood: str = Form("chill"),
    silence_trim: bool = Form(False),
    style_notes: str = Form(""),
    auto_concepts: List[str] = Form(default_factory=list),
    user: Dict[str, Any] = Depends(get_current_user),
):
    data = {
        "kind": kind,
        "external_id": external_id.strip(),
        "display_name": display_name.strip(),
        "permission": permission,
        "auto_process": auto_process,
        "layout": "auto",  # the AI picks per clip; change it on the New page or in clip detail
        "caption_style": caption_style,
        "music": 1 if music else 0,
        "default_music_mood": default_music_mood,
        "silence_trim": 1 if silence_trim else 0,
        "letterbox_style": "title",
        "style_notes": style_notes.strip(),
    }
    source_id = create_source(data)
    set_json_column(source_id, "auto_concepts", _chosen_concepts(auto_concepts))
    return RedirectResponse(url="/sources", status_code=HTTP_303_SEE_OTHER)


@router.get("/sources/{source_id}", response_class=HTMLResponse)
async def edit_source_form(
    request: Request,
    source_id: int,
    user: Dict[str, Any] = Depends(get_current_user),
):
    templates = request.app.state.templates
    src_row = get_source(source_id)
    if not src_row:
        raise HTTPException(status_code=HTTP_404_NOT_FOUND, detail="Source not found.")

    review_count = len(list_review_clips(status="ready"))

    return templates.TemplateResponse(
        request=request,
        name="pages/source_edit.html",
        context={
            "page_title": f"Edit {src_row['display_name']}",
            "active_nav": "sources",
            "page_width": "narrow",
            "user": user,
            "source": dict(src_row),
            "review_count": review_count,
            "profile": get_json_column(source_id, "creator_profile", None) or {},
            "learned_prefs": get_json_column(source_id, "learned_prefs", []),
            "creator_types": CREATOR_TYPES,
            "humor_styles": HUMOR_STYLES,
            "profile_status": request.query_params.get("profile", ""),
            "concepts": [(c, CONCEPT_LABELS[c]) for c in CONCEPTS],
            "auto_concepts": get_json_column(source_id, "auto_concepts", None) or DEFAULT_AUTO_CONCEPTS,
        },
    )


def _chosen_concepts(values: List[str]) -> List[str]:
    """Concepts ticked on the form, in the fixed order. Single is always on: it is what the pipeline falls back to."""
    return [c for c in CONCEPTS if c == "single" or c in values]


def _lines(text: str) -> List[str]:
    return [ln.strip() for ln in text.splitlines() if ln.strip()]


@router.post("/sources/{source_id}/profile")
async def save_profile_action(
    source_id: int,
    display_name: str = Form(""),
    creator_type: str = Form("other"),
    energy: str = Form("medium"),
    humor_styles: List[str] = Form([]),
    aliases: str = Form(""),
    fans_clip: str = Form(""),
    recurring_bits: str = Form(""),
    baseline_behaviors: str = Form(""),
    languages: str = Form(""),
    avoid: str = Form(""),
    notes: str = Form(""),
    user: Dict[str, Any] = Depends(get_current_user),
):
    """Save hand edits. Changed fields are marked as edited, so a rebuild never overwrites them."""
    if not get_source(source_id):
        raise HTTPException(status_code=HTTP_404_NOT_FOUND, detail="Source not found.")
    from src.profile import save_user_edits
    save_user_edits(source_id, {
        "display_name": display_name.strip(), "creator_type": creator_type, "energy": energy,
        "humor_styles": humor_styles, "aliases": _lines(aliases), "fans_clip": _lines(fans_clip),
        "recurring_bits": _lines(recurring_bits), "baseline_behaviors": _lines(baseline_behaviors),
        "languages": _lines(languages), "avoid": _lines(avoid), "notes": notes.strip(),
    })
    return RedirectResponse(url=f"/sources/{source_id}?profile=saved", status_code=HTTP_303_SEE_OTHER)


@router.post("/sources/{source_id}/profile/rebuild")
def rebuild_profile_action(
    source_id: int,
    user: Dict[str, Any] = Depends(get_current_user),
):
    """Rebuild from the source's latest processed VOD. One Claude call, so this runs in a worker thread."""
    src_row = get_source(source_id)
    if not src_row:
        raise HTTPException(status_code=HTTP_404_NOT_FOUND, detail="Source not found.")
    with get_connection() as conn:
        vids = conn.execute(
            "SELECT id FROM videos WHERE source_id = ? ORDER BY id DESC", (source_id,)
        ).fetchall()
    vid_dir = next((VIDEOS_DIR / str(v[0]) for v in vids if (VIDEOS_DIR / str(v[0]) / "transcript.json").exists()), None)
    if not vid_dir:
        return RedirectResponse(url=f"/sources/{source_id}?profile=no_vod", status_code=HTTP_303_SEE_OTHER)

    from src.profile import build_creator_profile
    try:
        meta = json.loads((vid_dir / "meta.json").read_text(encoding="utf-8"))
        transcript = json.loads((vid_dir / "transcript.json").read_text(encoding="utf-8"))
        built = build_creator_profile(
            meta, transcript, get_json_column(source_id, "creator_profile", None),
            int(vid_dir.name), src_row["style_notes"] or "",
        )
        set_json_column(source_id, "creator_profile", built)
        status = "rebuilt"
    except Exception as e:
        print(f"  [sources] Profile rebuild failed: {e}")
        status = "failed"
    return RedirectResponse(url=f"/sources/{source_id}?profile={status}", status_code=HTTP_303_SEE_OTHER)


@router.post("/sources/{source_id}/edit")
async def update_source_action(
    source_id: int,
    display_name: str = Form(...),
    permission: str = Form("review"),
    auto_process: bool = Form(False),
    caption_style: str = Form("bold_pop"),
    music: bool = Form(False),
    default_music_mood: str = Form("chill"),
    silence_trim: bool = Form(False),
    style_notes: str = Form(""),
    auto_concepts: List[str] = Form(default_factory=list),
    user: Dict[str, Any] = Depends(get_current_user),
):
    src_row = get_source(source_id)
    if not src_row:
        raise HTTPException(status_code=HTTP_404_NOT_FOUND, detail="Source not found.")

    data = {
        "display_name": display_name.strip(),
        "permission": permission,
        "permission_note": src_row["permission_note"],  # field removed from the form; keep any saved note
        "auto_process": auto_process,
        "layout": "auto",  # the AI picks per clip; change it on the New page or in clip detail
        "caption_style": caption_style,
        "music": 1 if music else 0,
        "default_music_mood": default_music_mood,
        "silence_trim": 1 if silence_trim else 0,
        "letterbox_style": src_row["letterbox_style"] or "title",  # no longer on this form; keep the saved value
        "style_notes": style_notes.strip(),
    }
    update_source(source_id, data)
    set_json_column(source_id, "auto_concepts", _chosen_concepts(auto_concepts))
    return RedirectResponse(url="/sources", status_code=HTTP_303_SEE_OTHER)


@router.post("/sources/{source_id}/delete")
async def delete_source_action(
    source_id: int,
    user: Dict[str, Any] = Depends(get_current_user),
):
    delete_source(source_id)
    return RedirectResponse(url="/sources", status_code=HTTP_303_SEE_OTHER)
