"""
Spike: a per-model daily count of Gemini requests. Gemini does not report remaining quota, so every request made
through generate_content_with_retry (the only call site) is counted here. The limit is the hardcoded
GEMINI_DAILY_LIMIT in config. Only the Auto layout checks it; the pipeline never blocks on it.
"""

import threading
from datetime import datetime, timedelta, timezone

from src import config
from src.db import get_setting, set_setting

_lock = threading.Lock()


def _today() -> str:
    """Gemini daily quotas reset at midnight Pacific. ponytail: fixed UTC-8, an hour late during daylight time."""
    return (datetime.now(timezone.utc) - timedelta(hours=8)).strftime("%Y-%m-%d")


def _key(model: str) -> str:
    return f"gemini_used:{model}"


def used(model: str) -> int:
    day, _, n = (get_setting(_key(model)) or "").partition("|")
    return int(n) if day == _today() and n.isdigit() else 0


def limit(model: str) -> int:
    """Every key has its own daily quota, so the total is the per-key limit times the number of keys."""
    return config.GEMINI_DAILY_LIMITS.get(model, config.GEMINI_DAILY_LIMIT) * max(1, len(config.gemini_keys()))


def left(model: str) -> int:
    return max(0, limit(model) - used(model))


def exhaust(model: str) -> None:
    """Google said 429 for good today: treat the model's budget as spent until the day resets."""
    try:
        with _lock:
            set_setting(_key(model), f"{_today()}|{max(used(model), limit(model))}")
    except Exception:
        pass


def spend(model: str) -> None:
    """Count one request. Failed and retried requests count too: they use quota."""
    try:
        with _lock:
            set_setting(_key(model), f"{_today()}|{used(model) + 1}")
    except Exception:
        pass  # counting must never fail a Gemini call
