"""
Spike: Claude (the user's Pro plan, via `claude -p`) stands in for Gemini once Gemini's daily quota is used up.
Every fallback call waits for the user's OK in the web app (a popup on every page). "Don't ask again today"
approves the rest of the day's calls. The pipeline and the web app are separate processes, so the one pending
request lives in the settings table.
"""

import json
import time
import uuid
from datetime import date
from typing import Any, Dict, Optional

from src.db import get_setting, log_event, set_setting

REQUEST_KEY = "claude_fallback_request"
SKIP_KEY = "claude_fallback_skip_day"
WAIT_S = 3600  # no answer within an hour counts as a no, so an unattended job stops instead of hanging


def _notify(label: str) -> None:
    from src.config import PUBLIC_URL
    from src.notify import _post_webhook, get_active_webhook_url
    url = get_active_webhook_url()
    if url:
        try:
            _post_webhook(url, f"**Gemini quota used up.** Spike wants to use your Claude plan for: {label}\nApprove or deny: <{PUBLIC_URL}/>")
        except Exception:
            pass


def pending() -> Optional[Dict[str, Any]]:
    """The request waiting for an answer, or None."""
    try:
        req = json.loads(get_setting(REQUEST_KEY) or "null")
    except ValueError:
        return None
    return req if req and req.get("status") == "pending" else None


def answer(req_id: str, approve: bool, skip_today: bool) -> bool:
    """Record the user's answer. False when req_id is no longer the pending request."""
    req = pending()
    if not req or req["id"] != req_id:
        return False
    req["status"] = "approved" if approve else "denied"
    set_setting(REQUEST_KEY, json.dumps(req))
    if approve and skip_today:
        set_setting(SKIP_KEY, date.today().isoformat())
    return True


def ask(label: str, detail: str) -> bool:
    """Block until the user approves or denies one Claude call. True right away when today is skipped."""
    if get_setting(SKIP_KEY) == date.today().isoformat():
        return True
    req = {"id": uuid.uuid4().hex, "label": label, "detail": detail[:300], "status": "pending", "ts": time.time()}
    set_setting(REQUEST_KEY, json.dumps(req))
    print(f"  [claude] Waiting for your OK in the web app to run on Claude: {label}")
    _notify(label)
    deadline = time.time() + WAIT_S
    while time.time() < deadline:
        time.sleep(2)
        try:
            cur = json.loads(get_setting(REQUEST_KEY) or "null") or {}
        except ValueError:
            cur = {}
        if cur.get("id") != req["id"]:
            return False  # replaced by another request: treat this one as not approved
        if cur.get("status") in ("approved", "denied"):
            return cur["status"] == "approved"
    req["status"] = "expired"
    set_setting(REQUEST_KEY, json.dumps(req))
    log_event("info", f"Claude fallback not approved within {WAIT_S // 60} min: {label}")
    return False
