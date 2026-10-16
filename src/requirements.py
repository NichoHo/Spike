"""
Spike: what a person must set up before an action works (API keys, Twitch app, Google sign-in).
Each check runs only for actions that need it, so a step is never flagged before it matters.
GET /requirements/check feeds the popup in app.js; the submit routes call missing() too, so the popup cannot be bypassed.
"""

from typing import Any, Dict, List, Optional
from urllib.parse import urlparse

from fastapi import APIRouter, Depends

from src import config
from src.db import get_source
from src.web.auth import get_current_user

router = APIRouter()

_ENV = "Add it to the .env file, then restart Spike."


def _item(title: str, detail: str, fix_url: str = "", fix_label: str = "") -> Dict[str, str]:
    return {"title": title, "detail": detail, "fix_url": fix_url, "fix_label": fix_label}


def _gemini() -> List[Dict[str, str]]:
    return [] if config.GEMINI_API_KEY else [_item("Gemini API key", f"Set GEMINI_API_KEY. It finds the moments. {_ENV}")]


def _twitch() -> List[Dict[str, str]]:
    if config.TWITCH_CLIENT_ID and config.TWITCH_CLIENT_SECRET and not config.TWITCH_CLIENT_ID.startswith("your_"):
        return []
    return [_item("Twitch app", f"Set TWITCH_CLIENT_ID and TWITCH_CLIENT_SECRET (from dev.twitch.tv/console). {_ENV}")]


def _youtube() -> List[Dict[str, str]]:
    return [] if config.YOUTUBE_API_KEY else [_item("YouTube API key", f"Set YOUTUBE_API_KEY. {_ENV}")]


def _google() -> List[Dict[str, str]]:
    from src.outreach import db as odb, google
    if not google.oauth_configured():
        return [_item("Google sign-in not set up", f"Set GOOGLE_OAUTH_CLIENT_ID and GOOGLE_OAUTH_CLIENT_SECRET. {_ENV}")]
    if not google.encryption_key_set():
        return [_item("Encryption key", f"Set SPIKE_ENCRYPTION_KEY. Gmail tokens are never stored without it. {_ENV}")]
    acc = odb.get_google_account()
    if not acc:
        return [_item("Sign in with Google", "Emails are sent from your Google account.", "/outreach/google/connect", "Sign in with Google")]
    if acc.get("error"):
        return [_item("Google needs a new sign-in", acc["error"], "/outreach/google/connect", "Sign in again")]
    return []


def _kind_of(source_id: Optional[int], url: str) -> str:
    """'twitch' or 'youtube' from a followed source or a pasted link; '' when unknown."""
    if source_id:
        src = get_source(source_id)
        return src["kind"] if src else ""
    host = (urlparse(url.strip()).hostname or "").lower()
    return "twitch" if host.endswith("twitch.tv") else "youtube" if host.endswith(("youtube.com", "youtu.be")) else ""


def missing(action: str, kind: str = "", source_id: Optional[int] = None, url: str = "") -> List[Dict[str, str]]:
    """Setup steps still open for an action: video | source | outreach_send | outreach_find."""
    if action == "video":
        kind = _kind_of(source_id, url)
        return _gemini() + (_twitch() if kind == "twitch" else [])
    if action == "source":
        return _twitch() if kind == "twitch" else _youtube() if kind == "youtube" else []
    if action == "outreach_send":
        return _google()
    if action == "outreach_find":
        return _twitch() if kind == "twitch" else _youtube()
    return []


@router.get("/requirements/check")
def check(action: str, kind: str = "", source_id: Optional[int] = None, url: str = "",
          user: Dict[str, Any] = Depends(get_current_user)):
    return {"missing": missing(action, kind, source_id, url)}
