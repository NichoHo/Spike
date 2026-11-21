"""
Suggested standards (clip analytics Step 4): Shorts that beat their own channel's median, from comparable channels the team
follows and from Spike's own results. Ranked by the multiple over the channel's median, not by raw views. Public data has
views only, so these teach what YouTube pushes. Spike's own stats teach what keeps viewers watching.
"""

import json
import re
import statistics
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, List, Optional

from src import analytics
from src.db import get_setting, list_labels, now_utc_iso, set_setting
from src.outreach import db as outreach_db
from src.outreach import youtube
from src.outreach.net import HttpError

CHANNELS_KEY, DISMISSED_KEY = "standard_channels", "standard_dismissed"
UPLOADS_SCANNED = 200   # 4 playlistItems calls and 4 videos.list calls, about 8 of 10,000 units
MIN_AGE_DAYS = 14       # younger Shorts are still gaining views
MIN_REST = 5            # other Shorts needed for a median
CHANNEL_HIT = 3.0       # multiple for a comparable channel's Short
OWN_HIT = 2.0           # multiple for Spike's own Short
OWN_MIN_SHORTS = 10     # own Shorts before own suggestions start
OWN_MIN_AGE_DAYS = 7
MAX_SUGGESTIONS = 10
RESCAN = timedelta(days=30)
HANDLE_RE = re.compile(r"^@[A-Za-z0-9._-]{3,30}$")
CHANNEL_ID_RE = re.compile(r"^UC[\w-]{22}$")
LINK_RE = re.compile(r"^(?:https?://)?(?:www\.|m\.)?(?:youtube\.com|youtu\.be)/(@[A-Za-z0-9._-]{3,30}|channel/UC[\w-]{22})(?:[/?#].*)?$", re.I)
VIDEO_ID_RE = re.compile(r"(?:shorts/|v=|youtu\.be/)([\w-]{11})(?![\w-])")


def parse_channel(text: str) -> Optional[str]:
    """A handle (@Hakaizo) or a channel id (UC...) from a handle or a youtube.com / youtu.be link. None for anything else:
    the text is a form field, and it only ever becomes an API parameter, never a shell argument."""
    t = (text or "").strip()
    if HANDLE_RE.match(t) or CHANNEL_ID_RE.match(t):
        return t
    m = LINK_RE.match(t)
    return m.group(1).removeprefix("channel/") if m else None


def video_id(url: Optional[str]) -> Optional[str]:
    m = VIDEO_ID_RE.search(url or "")
    return m.group(1) if m else None


def _load(key: str) -> list:
    try:
        v = json.loads(get_setting(key) or "[]")
    except ValueError:
        return []
    return v if isinstance(v, list) else []


def channels() -> List[Dict[str, Any]]:
    return _load(CHANNELS_KEY)


def _save_channels(items: List[Dict[str, Any]]) -> None:
    set_setting(CHANNELS_KEY, json.dumps(items))


def with_multiples(shorts: List[Dict[str, Any]], today: Optional[datetime] = None) -> List[Dict[str, Any]]:
    """Shorts (id, title, views, published_at) at least 14 days old, each with its views over the median of the rest."""
    now = today or datetime.now(timezone.utc)
    old = [s for s in shorts if (when := analytics._when(s["published_at"])) and now - when >= timedelta(days=MIN_AGE_DAYS)]
    out = []
    for i, s in enumerate(old):
        rest = [o["views"] for j, o in enumerate(old) if j != i]
        med = statistics.median(rest) if len(rest) >= MIN_REST else 0
        if med > 0:
            out.append({**s, "multiple": round(s["views"] / med, 1)})
    return out


def scan(ref: str) -> Dict[str, Any]:
    """Read a channel's last 200 uploads and keep its Shorts that beat the channel's own median. Errors come back in the
    result (the quota can be used up, the key missing, the channel unknown): a scan never raises."""
    settings = outreach_db.get_settings()
    result: Dict[str, Any] = {"ref": ref, "checked": now_utc_iso(), "error": "", "name": ref, "suggestions": []}
    try:
        q = {"part": "snippet,contentDetails", **({"id": ref} if ref.startswith("UC") else {"forHandle": ref})}
        items = youtube.call("channels", settings, **q).get("items") or []
        if not items:
            raise youtube.YouTubeError(f"No YouTube channel found for {ref}")
        result["name"] = items[0]["snippet"]["title"]
        playlist = items[0]["contentDetails"]["relatedPlaylists"]["uploads"]
        ids: List[str] = []
        page = ""
        while len(ids) < UPLOADS_SCANNED:
            res = youtube.call("playlistItems", settings, part="contentDetails", playlistId=playlist, maxResults=50, pageToken=page)
            ids += [i["contentDetails"]["videoId"] for i in res.get("items") or []]
            page = res.get("nextPageToken") or ""
            if not page:
                break
        shorts = []
        for batch in youtube._chunks(ids[:UPLOADS_SCANNED], 50):
            for v in youtube.call("videos", settings, part="snippet,contentDetails,statistics", id=",".join(batch), maxResults=50).get("items") or []:
                if 0 < youtube.parse_duration(v["contentDetails"].get("duration", "")) <= youtube.SHORT_MAX_S and "viewCount" in v.get("statistics", {}):
                    shorts.append({"id": v["id"], "title": v["snippet"].get("title", "")[:200], "views": int(v["statistics"]["viewCount"]),
                                   "published_at": v["snippet"].get("publishedAt")})
        hits = sorted((s for s in with_multiples(shorts) if s["multiple"] >= CHANNEL_HIT), key=lambda s: -s["multiple"])
        result["suggestions"] = hits[:MAX_SUGGESTIONS]
    except (youtube.YouTubeError, youtube.QuotaExhausted, HttpError, OSError, KeyError, ValueError) as e:
        result["error"] = str(e)[:300]
    return result


def add_channel(text: str) -> Optional[str]:
    """Remember a channel and scan it now. Returns an error text, or None."""
    ref = parse_channel(text)
    if not ref:
        return "Paste a youtube.com channel link or a handle like @Hakaizo."
    items = [c for c in channels() if c["ref"].lower() != ref.lower()]
    got = scan(ref)
    _save_channels(items + [got])
    return got["error"] or None


def remove_channel(ref: str) -> None:
    _save_channels([c for c in channels() if c["ref"] != ref])


def run_monthly() -> int:
    """From the worker loop: scan each followed channel whose last scan is 30 or more days old."""
    done, items = 0, channels()
    for i, c in enumerate(items):
        when = analytics._when(c.get("checked"))
        if not when or datetime.now(timezone.utc) - when >= RESCAN:
            items[i] = scan(c["ref"])
            done += 1
    if done:
        _save_channels(items)
    return done


def own_suggestions() -> List[Dict[str, Any]]:
    """Spike's own Shorts that did 2x the channel's median and kept more viewers than usual. Starts at 10 Shorts of 7 days or older."""
    rows = [r for r in analytics.shorts_table() if (r["age"] or 0) >= OWN_MIN_AGE_DAYS and r["stayed"] is not None]
    if len(rows) < OWN_MIN_SHORTS:
        return []
    typical = statistics.median(r["stayed"] for r in rows)
    return [{"id": video_id(r["url"]) or r["platform_video_id"], "title": r["title"], "views": r["views_7d"], "multiple": round(r["multiple"], 1),
             "published_at": r["published_at"], "source": "Your channel"}
            for r in sorted(rows, key=lambda r: -(r["multiple"] or 0)) if r["multiple"] and r["multiple"] >= OWN_HIT and r["stayed"] > typical]


def dismissed() -> set:
    return set(_load(DISMISSED_KEY))


def dismiss(vid: str) -> None:
    set_setting(DISMISSED_KEY, json.dumps(sorted(dismissed() | {vid})))


def suggestions() -> List[Dict[str, Any]]:
    """What the Standards card offers: own winners first, then each channel's, minus standards and dismissed ones."""
    have = {video_id(g["source_url"]) for g in list_labels("gold")} | dismissed()
    out = [s for s in own_suggestions() if s["id"] not in have]
    for c in channels():
        out += [{**s, "source": c["name"]} for s in c["suggestions"] if s["id"] not in have]
    return out


def find(vid: str) -> Optional[Dict[str, Any]]:
    return next((s for s in suggestions() if s["id"] == vid), None)
