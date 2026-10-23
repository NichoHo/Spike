"""
Spike: a per-model daily count of Gemini requests. Gemini does not report remaining quota, so every request made
through generate_content_with_retry (the only call site) is counted here. The limit is the hardcoded
GEMINI_DAILY_LIMIT in config. Only the Auto layout checks it; the pipeline never blocks on it.
"""

import hashlib
import threading
from datetime import datetime, timedelta, timezone

from src import config
from src.db import get_setting, set_setting

_lock = threading.Lock()


try:
    from zoneinfo import ZoneInfo
    _PACIFIC = ZoneInfo("America/Los_Angeles")
except Exception:  # no tz database (Windows Python without tzdata): fixed PST, an hour late during daylight time
    _PACIFIC = timezone(timedelta(hours=-8))


def today() -> str:
    """Gemini daily quotas reset at midnight Pacific (ai.google.dev/gemini-api/docs/rate-limits), whatever the
    machine's own timezone."""
    return datetime.now(_PACIFIC).strftime("%Y-%m-%d")


def reset_at() -> float:
    """Unix time of the next quota reset: the coming midnight Pacific."""
    now = datetime.now(_PACIFIC)
    return (now.replace(hour=0, minute=0, second=0, microsecond=0) + timedelta(days=1)).timestamp()


def _key_tag(api_key: str) -> str:
    """A short, stable id for a key's value, so per-key caps follow the key even if .env order changes and never
    store the key itself."""
    return hashlib.sha256(api_key.encode("utf-8")).hexdigest()[:12]


def _cap_key(model: str, api_key: str) -> str:
    return f"gemini_key_capped:{model}:{_key_tag(api_key)}"


def key_capped(model: str, api_key: str) -> bool:
    """True when this key's daily quota for this model ran out today. Persisted in the shared settings table, so it
    survives a restart (Option A: capped until midnight Pacific) and every Tailscale user's process reads the same
    state from the one shared DB."""
    return get_setting(_cap_key(model, api_key)) == today()


def cap_key(model: str, api_key: str) -> None:
    """Mark this key's daily quota for this model used up for the rest of the day. Idempotent; never raises."""
    try:
        with _lock:
            set_setting(_cap_key(model, api_key), today())
    except Exception:
        pass


def _key(model: str) -> str:
    return f"gemini_used:{model}"


def used(model: str) -> int:
    day, _, n = (get_setting(_key(model)) or "").partition("|")
    return int(n) if day == today() and n.isdigit() else 0


def limit(model: str) -> int:
    """Every key has its own daily quota, so the total is the per-key limit times the number of keys."""
    return config.GEMINI_DAILY_LIMITS.get(model, config.GEMINI_DAILY_LIMIT) * max(1, len(config.gemini_keys()))


def left(model: str) -> int:
    return max(0, limit(model) - used(model))


def exhaust(model: str) -> None:
    """Google said 429 for good today: treat the model's budget as spent until the day resets."""
    try:
        with _lock:
            set_setting(_key(model), f"{today()}|{max(used(model), limit(model))}")
    except Exception:
        pass


def spend(model: str) -> None:
    """Count one request. Failed and retried requests count too: they use quota."""
    try:
        with _lock:
            set_setting(_key(model), f"{today()}|{used(model) + 1}")
    except Exception:
        pass  # counting must never fail a Gemini call
