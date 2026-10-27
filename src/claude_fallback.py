"""
Spike: Claude (the user's Pro plan, via `claude -p`) stands in for Gemini once Gemini's daily quota is used up.
Every fallback call waits for the user's OK in the web app (a popup on every page). "Don't ask again today"
approves the rest of the day's calls. The pipeline and the web app are separate processes, so the one pending
request lives in the settings table.
"""

import json
import time
import uuid
from typing import Any, Dict, Optional

from src.db import get_setting, log_event, set_setting
from src.gemini_budget import today

REQUEST_KEY = "claude_fallback_request"
SKIP_KEY = "claude_fallback_skip_day"
PAUSE_KEY = "claude_paused"
RUNNING_KEY = "claude_running"
WAIT_S = 3600  # no answer within an hour counts as a no, so an unattended job stops instead of hanging


def paused() -> bool:
    """The user switched Claude off (sidebar button). Every Claude call then fails fast with ClaudeError, which
    every caller already handles: it falls back to Gemini or stops as if Claude had failed."""
    return get_setting(PAUSE_KEY) == "1"


def set_paused(on: bool) -> None:
    set_setting(PAUSE_KEY, "1" if on else "")
    req = pending()
    if on and req:
        answer(req["id"], approve=False, skip_today=False)  # a job waiting for the OK stops waiting


def mark_running(label: str, timeout_s: float) -> None:
    """A Claude call started. `until` ends the mark even if the process dies mid-call.
    ponytail: one slot, two concurrent calls share it; a counter if that ever matters."""
    set_setting(RUNNING_KEY, json.dumps({"label": label, "until": time.time() + timeout_s}))


def clear_running() -> None:
    set_setting(RUNNING_KEY, "")


def running() -> Optional[str]:
    """Label of the Claude call running right now, or None."""
    try:
        cur = json.loads(get_setting(RUNNING_KEY) or "null")
    except ValueError:
        return None
    return cur["label"] if cur and cur.get("until", 0) > time.time() else None


def _all_keys_out(model: Optional[str]) -> bool:
    """True when every Gemini key is capped for the model today, or the model's whole budget is spent."""
    if not model:
        return True
    from src import config, gemini_budget
    keys = config.gemini_keys()
    return gemini_budget.left(model) == 0 or (bool(keys) and all(gemini_budget.key_capped(model, k) for k in keys))


def _notify(label: str, model: Optional[str]) -> None:
    from src.config import PUBLIC_URL
    from src.notify import _post_webhook, get_active_webhook_url
    if not _all_keys_out(model):
        return  # one key out is not "Gemini used up": the other keys still serve the call
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
        set_setting(SKIP_KEY, today())  # Gemini's day (Pacific), so the skip ends when Gemini's quota comes back
    return True


def ask(label: str, detail: str, model: Optional[str] = None) -> bool:
    """Block until the user approves or denies one Claude call. True right away when today is skipped."""
    if paused():
        return False
    if get_setting(SKIP_KEY) == today():
        return True
    req = {"id": uuid.uuid4().hex, "label": label, "detail": detail[:300], "status": "pending", "ts": time.time()}
    set_setting(REQUEST_KEY, json.dumps(req))
    print(f"  [claude] Waiting for your OK in the web app to run on Claude: {label}")
    _notify(label, model)
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
