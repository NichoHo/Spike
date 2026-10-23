"""
Spike: oversized-input gate for the main pipeline.

A very long VOD costs a lot of Claude/Gemini tokens in the 'moments' stage and the stages after it. Before
that expensive work starts, the pipeline pauses and asks the user to Continue or Stop. There are two levels:

  * THRESHOLD (4 h / 14400 s): the first Continue/Stop question.
  * CEILING   (6 h / 21600 s): a second, more serious question. The ceiling is SOFT: if the user still
    continues, the WHOLE video is processed, no truncation.

The question is delivered two ways at once (mirrors src/claude_fallback.py):
  (a) a Discord notification (reuses src/notify._post_webhook + get_active_webhook_url), with a Jobs-page link;
  (b) a Continue/Stop state + buttons on the Jobs page (route + template).

The pending record lives in spike.db settings (src/db.py get_setting/set_setting), because the pipeline/worker
process and the web app are separate processes, exactly like the Claude fallback. If nobody answers within
WAIT_S, ask() returns "timeout" and the runner PARKS the job (back to 'queued') so the worker moves on to the
next queued job; the record stays so the Jobs-page buttons can still answer it.

Token figures below are MEASURED from real claude_usage data (n=80 real moment-scoring calls) and are hardcoded
on purpose so the gate can show a grounded estimate without a live query.
"""

import json
import time
import uuid
from datetime import datetime, timezone
from typing import Any, Dict, Optional

from src.db import get_setting, log_event, set_setting

# Thresholds (seconds of video duration)
THRESHOLD_S = 14400  # 4 h: ask Continue or Stop
CEILING_S = 21600    # 6 h: soft ceiling, escalated warning, never truncates

REQUEST_KEY = "oversize_gate_request"
WAIT_S = 3600  # no answer within an hour -> park the job so the worker moves to the next one

# Measured token figures (claude_usage, n=80 real calls)
TOKENS_PER_MOMENT = 20300        # 14.1k in + 6.2k out per candidate moment scored
COST_PER_MOMENT_USD = 0.052
TOKENS_PER_5MIN_SLICE_LO = 25000
TOKENS_PER_5MIN_SLICE_HI = 45000
# ~2 h VOD = 250-450k tokens end to end -> per hour, anchored to that 2 h figure
TOKENS_PER_HOUR_LO = 125000
TOKENS_PER_HOUR_HI = 225000

# The 10 pipeline stages, in order. The gate fires right before 'moments' (stage 7).
STAGES = [
    "fetch_meta", "fetch_audio", "fetch_chat", "fetch_crowd", "transcribe",
    "signals", "moments", "fetch_sections", "render", "render_vertical",
]
GATE_BEFORE_STAGE = "moments"


def estimate_tokens(duration_s: float) -> Dict[str, int]:
    """End-to-end token estimate for a VOD of this length, scaled linearly from the measured 2 h figure."""
    hours = max(duration_s, 0.0) / 3600.0
    return {
        "lo": int(hours * TOKENS_PER_HOUR_LO),
        "hi": int(hours * TOKENS_PER_HOUR_HI),
    }


def remaining_stages() -> list:
    """Stages still to run at the gate (moments and everything after it)."""
    return STAGES[STAGES.index(GATE_BEFORE_STAGE):]


def _fmt_tokens(n: int) -> str:
    return f"{n:,}"


def build_message(video_id: int, title: str, duration_s: float, level: int, public_url: str) -> str:
    """The Discord/Jobs-page text. Grounded in real figures and this job's actual duration."""
    threshold = THRESHOLD_S if level == 1 else CEILING_S
    over_min = int(round((duration_s - threshold) / 60.0))
    hours = duration_s / 3600.0
    tok = estimate_tokens(duration_s)
    now = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S UTC")
    remaining = remaining_stages()
    jobs_link = f"{public_url.rstrip('/')}/jobs"

    head = (
        "**Oversized video - final check before the expensive stages.**" if level == 2
        else "**Long video - confirm before the expensive stages.**"
    )
    severity = (
        "This VOD is over the 6 hour ceiling. Processing it whole will cost a LOT of tokens and money, and "
        "there is no truncation: every stage runs over the full length. Continue only if you really want the "
        "entire video processed."
        if level == 2 else
        "This VOD is over the 4 hour threshold. The next stages score moments with Claude/Gemini and are the "
        "expensive part of the run."
    )
    lines = [
        head,
        f"Job #{video_id}: {title[:150]}",
        severity,
        "",
        f"Duration: {hours:.1f} h ({int(duration_s)} s) - {over_min} min over the "
        f"{'6 h ceiling' if level == 2 else '4 h threshold'}.",
        f"Estimated cost end to end: {_fmt_tokens(tok['lo'])}-{_fmt_tokens(tok['hi'])} tokens.",
        f"Reference: ~{_fmt_tokens(TOKENS_PER_MOMENT)} tokens per moment scored (~${COST_PER_MOMENT_USD:.3f} each, "
        f"n=80 real calls); ~{_fmt_tokens(TOKENS_PER_5MIN_SLICE_LO)}-{_fmt_tokens(TOKENS_PER_5MIN_SLICE_HI)} "
        f"tokens per 5-min transcript slice; ~2 h VOD = 250,000-450,000 tokens.",
        f"Current stage: signals (done). About to start: moments (stage "
        f"{STAGES.index(GATE_BEFORE_STAGE) + 1} of {len(STAGES)}).",
        f"Remaining stages: {' -> '.join(remaining)}.",
        f"Now: {now}.",
        "",
        f"Answer here, or on the Jobs page if you cannot from Discord: <{jobs_link}>",
    ]
    return "\n".join(lines)


def _notify(text: str) -> None:
    from src.notify import _post_webhook, get_active_webhook_url
    url = get_active_webhook_url()
    if not url:
        return
    try:
        _post_webhook(url, text)
    except Exception:
        pass


def pending(video_id: Optional[int] = None) -> Optional[Dict[str, Any]]:
    """The request waiting for an answer, or None. When video_id is given, only a pending request for that
    job is returned."""
    try:
        req = json.loads(get_setting(REQUEST_KEY) or "null")
    except ValueError:
        return None
    if not req or req.get("status") != "pending":
        return None
    if video_id is not None and req.get("video_id") != video_id:
        return None
    return req


def _current() -> Optional[Dict[str, Any]]:
    try:
        return json.loads(get_setting(REQUEST_KEY) or "null") or None
    except ValueError:
        return None


def answer(req_id: str, approve: bool) -> bool:
    """Record the user's Continue (approve=True) / Stop (approve=False) answer. False when req_id is no longer
    the current request."""
    req = _current()
    if not req or req.get("id") != req_id:
        return False
    req["status"] = "continue" if approve else "stop"
    set_setting(REQUEST_KEY, json.dumps(req))
    return True


def clear(video_id: int) -> None:
    """Drop any gate record for this job (called when the job finishes or is cancelled)."""
    req = _current()
    if req and req.get("video_id") == video_id:
        set_setting(REQUEST_KEY, "null")


def ask(video_id: int, title: str, duration_s: float, level: int, public_url: str) -> str:
    """Block until the user answers, or WAIT_S passes. Returns "continue", "stop", or "timeout".

    If a resolved answer for this exact (video_id, level) already exists - e.g. the job was parked after a
    Continue and re-claimed - it is returned at once without asking again.
    """
    existing = _current()
    if existing and existing.get("video_id") == video_id and existing.get("level") == level \
            and existing.get("status") in ("continue", "stop"):
        return existing["status"]

    req = {
        "id": uuid.uuid4().hex,
        "video_id": video_id,
        "title": title[:200],
        "duration_s": float(duration_s),
        "level": level,
        "status": "pending",
        "ts": time.time(),
    }
    set_setting(REQUEST_KEY, json.dumps(req))
    msg = build_message(video_id, title, duration_s, level, public_url)
    print(f"  [gate] Job #{video_id} is {duration_s / 3600:.1f} h (level {level}). Waiting for Continue/Stop.")
    _notify(msg)

    deadline = time.time() + WAIT_S
    while time.time() < deadline:
        time.sleep(2)
        cur = _current() or {}
        if cur.get("id") != req["id"]:
            return "stop"  # replaced by another request: treat as not approved
        if cur.get("status") in ("continue", "stop"):
            return cur["status"]
    log_event("info", f"Oversized-input gate (level {level}) not answered within {WAIT_S // 60} min for job "
              f"#{video_id}; parking it.", video_id=video_id)
    return "timeout"
