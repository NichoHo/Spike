"""Gemini calls are paced to the free tier's per-minute limit, and a 429 waits as long as Google says.
The 429 bodies below are copied from real google-genai ClientError text (github.com/getzep/graphiti/issues/697)."""

import pytest

import src.pipeline.stage7_moments as s7
from src import gemini_budget as gb

MINUTE_429 = (
    "429 RESOURCE_EXHAUSTED. {'error': {'code': 429, 'message': 'You exceeded your current quota, please check your plan "
    "and billing details.', 'status': 'RESOURCE_EXHAUSTED', 'details': [{'@type': 'type.googleapis.com/google.rpc.QuotaFailure', "
    "'violations': [{'quotaMetric': 'generativelanguage.googleapis.com/generate_content_free_tier_requests', "
    "'quotaId': 'GenerateRequestsPerMinutePerProjectPerModel-FreeTier', 'quotaDimensions': {'model': 'gemini-2.5-flash-lite', "
    "'location': 'global'}, 'quotaValue': '12'}]}, {'@type': 'type.googleapis.com/google.rpc.RetryInfo', 'retryDelay': '46s'}]}}"
)
DAY_429 = MINUTE_429.replace("PerMinute", "PerDay").replace("'46s'", "'34s'")
TOKENS_429 = MINUTE_429.replace("GenerateRequestsPerMinutePerProjectPerModel", "GenerateContentInputTokensPerModelPerMinute")


class _FlakyClient:
    """Raises each error in turn, then answers."""

    def __init__(self, *errors):
        self.models = self
        self.errors = list(errors)

    def generate_content(self, **kw):
        if self.errors:
            raise RuntimeError(self.errors.pop(0))
        return "ok"


@pytest.fixture
def fake_clock(monkeypatch):
    clock = {"t": 1000.0, "waits": []}

    def sleep(s):
        clock["waits"].append(round(s, 2))
        clock["t"] += s

    monkeypatch.setattr(gb.time, "monotonic", lambda: clock["t"])
    monkeypatch.setattr(gb.time, "sleep", sleep)
    gb._calls.clear()
    return clock


def test_pace_holds_a_call_until_the_minute_window_frees(fake_clock, monkeypatch):
    monkeypatch.setattr(gb, "rpm", lambda model: 3)
    for _ in range(3):
        gb.pace("m")
    assert fake_clock["waits"] == []
    gb.pace("m")
    assert fake_clock["waits"] == [gb.PACE_WINDOW_S]


def test_retry_delay_reads_both_hint_forms():
    assert s7._retry_delay_s(MINUTE_429.lower()) == 46.0
    assert s7._retry_delay_s("please retry in 7h33m11s.") == 7 * 3600 + 33 * 60 + 11


def test_a_minute_429_teaches_the_limit_and_waits_googles_delay(fake_clock):
    gb.learn_rpm("pacing-test", 0)
    out = s7.generate_content_with_retry(_FlakyClient(MINUTE_429), "pacing-test", "x", None)
    assert out == "ok" and 46.0 in fake_clock["waits"]
    assert gb.rpm("pacing-test") == 12


def test_a_token_429_waits_but_does_not_change_the_request_limit(fake_clock):
    gb.learn_rpm("pacing-test-2", 0)
    s7.generate_content_with_retry(_FlakyClient(TOKENS_429), "pacing-test-2", "x", None)
    assert 46.0 in fake_clock["waits"] and gb.rpm("pacing-test-2") == gb.config.GEMINI_RPM_GUESS


def test_a_per_day_429_is_the_daily_cap_even_with_a_short_delay(fake_clock):
    with pytest.raises(s7.QuotaExhausted):
        s7.generate_content_with_retry(_FlakyClient(DAY_429), "pacing-test", "x", None, allow_claude=False)
    assert s7._daily_cap(RuntimeError(DAY_429)) and not s7._daily_cap(RuntimeError(MINUTE_429))
