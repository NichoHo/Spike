"""
Shared HTTP for the outreach finders: one rate limiter per API, plus retries on 429, 5xx and network errors.

Spacing, not jitter: requests go out evenly at most `per_minute` a minute. An API that reports its own budget
(Twitch: Ratelimit-Remaining / Ratelimit-Reset) or asks us to wait (Retry-After) pauses the limiter until then.
"""

import json
import threading
import time
import urllib.error
import urllib.request
from typing import Any, Callable, Dict, Mapping, Optional

MAX_WAIT_S = 120  # never trust a header that asks for more; the next run picks up where this one stopped


class HttpError(RuntimeError):
    def __init__(self, status: int, body: str, url: str):
        super().__init__(f"HTTP {status}: {body[:200]}")
        self.status, self.body, self.url = status, body, url


class RateLimiter:
    """At most `per_minute` requests a minute, evenly spaced. Thread-safe."""

    def __init__(self, per_minute: float):
        self.gap = 60.0 / per_minute
        self.next_at = 0.0
        self.lock = threading.Lock()

    def wait(self) -> None:
        with self.lock:
            now = time.monotonic()
            if self.next_at > now:
                time.sleep(self.next_at - now)
                now = self.next_at
            self.next_at = now + self.gap

    def pause(self, seconds: float) -> None:
        """Hold every later request for `seconds` (capped), e.g. until a rate-limit window resets."""
        with self.lock:
            self.next_at = max(self.next_at, time.monotonic() + min(max(seconds, 0.0), MAX_WAIT_S))

    def observe(self, headers: Mapping[str, str]) -> None:
        """Respect an API's own budget headers. Ratelimit-Reset is a Unix time (Twitch Helix)."""
        h = {k.lower(): v for k, v in headers.items()}
        try:
            if "ratelimit-remaining" in h and int(h["ratelimit-remaining"]) <= 0 and "ratelimit-reset" in h:
                self.pause(float(h["ratelimit-reset"]) - time.time() + 1)
        except ValueError:
            pass  # a malformed header is ignored, not fatal


def get_json(url: str, limiter: RateLimiter, headers: Optional[Dict[str, str]] = None, retries: int = 3,
             on_attempt: Optional[Callable[[], None]] = None, timeout: float = 20) -> Dict[str, Any]:
    """GET and parse JSON. Retries 429, 5xx and network errors with backoff; other errors raise HttpError
    at once. `on_attempt` runs before every attempt (quota accounting: retries cost quota too)."""
    req_headers = {"User-Agent": "Spike-Outreach/1.0", **(headers or {})}
    for attempt in range(retries + 1):
        limiter.wait()
        if on_attempt:
            on_attempt()
        try:
            with urllib.request.urlopen(urllib.request.Request(url, headers=req_headers), timeout=timeout) as r:
                limiter.observe(r.headers)
                return json.loads(r.read().decode("utf-8"))
        except urllib.error.HTTPError as e:
            body = e.read().decode("utf-8", errors="replace")
            limiter.observe(e.headers or {})
            if (e.code == 429 or e.code >= 500) and attempt < retries:
                retry_after = (e.headers or {}).get("Retry-After")
                limiter.pause(float(retry_after) if retry_after and retry_after.isdigit() else 5 * 2 ** attempt)
                continue
            raise HttpError(e.code, body, url) from None
        except (urllib.error.URLError, TimeoutError) as e:
            if attempt >= retries:
                raise HttpError(0, str(e), url) from None
            limiter.pause(5 * 2 ** attempt)
    raise AssertionError("unreachable")
