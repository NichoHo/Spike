"""Judge pool: stage 7 calls run in parallel on Gemini; Claude helps while Gemini is down (docs/superpowers/specs/
2026-11-07-judge-pool-design.md)."""

import threading
import time

import pytest

from src import judge_pool as jp
from src.db import set_setting


@pytest.fixture(autouse=True)
def fast_pool(monkeypatch):
    monkeypatch.setattr(jp, "PROBE_START_S", 0.01)
    monkeypatch.setattr(jp, "PROBE_MAX_S", 0.04)
    monkeypatch.setattr(jp.claude_fallback, "ask", lambda *a, **k: True)
    set_setting(jp.CLAUDE_USED_KEY, "")
    set_setting(jp.HELP_KEY, "down")
    yield
    set_setting(jp.HELP_KEY, "off")


def test_results_come_back_in_task_order_with_their_provider():
    tasks = [jp.Task(lambda p, i=i: i * 10) for i in range(20)]
    assert jp.run_pool(tasks, seed=1) == [("gemini", i * 10) for i in range(20)]


def test_no_tasks_returns_at_once():
    assert jp.run_pool([], seed=1) == []


def test_claude_never_runs_while_gemini_is_up_in_the_default_mode():
    out = jp.run_pool([jp.Task(lambda p: p) for _ in range(10)], seed=2)
    assert {p for p, _ in out} == {"gemini"}


def test_always_mode_shares_the_work_with_claude():
    set_setting(jp.HELP_KEY, "always")

    def slow(p):
        time.sleep(0.02)
        return p

    out = jp.run_pool([jp.Task(slow) for _ in range(30)], seed=3)
    assert {p for p, _ in out} == {"gemini", "claude"}


def test_gemini_outage_moves_work_to_claude_and_back():
    state = {"down": True, "claude": 0}
    lock = threading.Lock()

    def run(p):
        with lock:
            if p == "gemini" and state["down"]:
                raise jp.GeminiUnavailable("503 unavailable")
            if p == "claude":
                state["claude"] += 1
                if state["claude"] == 3:
                    state["down"] = False  # Gemini recovers
        time.sleep(0.005)
        return p

    out = jp.run_pool([jp.Task(run) for _ in range(40)], seed=4)
    providers = [p for p, _ in out]
    assert len(out) == 40
    assert 3 <= providers.count("claude") < 40 and "gemini" in providers


def test_gemini_only_tasks_wait_for_gemini():
    state = {"n": 0}

    def run(p):
        assert p == "gemini"
        state["n"] += 1
        if state["n"] <= 2:
            raise jp.GeminiUnavailable("503 unavailable")
        return "ok"

    assert jp.run_pool([jp.Task(run, claude_ok=False)], seed=5) == [("gemini", "ok")]


def test_denied_claude_leaves_gemini_to_finish(monkeypatch):
    monkeypatch.setattr(jp.claude_fallback, "ask", lambda *a, **k: False)
    state = {"n": 0}
    lock = threading.Lock()

    def run(p):
        assert p == "gemini"
        with lock:
            state["n"] += 1
            if state["n"] <= 3:
                raise jp.GeminiUnavailable("503 unavailable")
        return p

    out = jp.run_pool([jp.Task(run) for _ in range(6)], seed=6)
    assert {p for p, _ in out} == {"gemini"}


def test_a_claude_error_hands_the_task_back_to_gemini():
    set_setting(jp.HELP_KEY, "always")

    def run(p):
        if p == "claude":
            raise RuntimeError("claude exited 1")
        return p

    out = jp.run_pool([jp.Task(run) for _ in range(8)], seed=7)
    assert {p for p, _ in out} == {"gemini"}


def test_off_with_gemini_down_fails_after_the_stall_limit():
    set_setting(jp.HELP_KEY, "off")

    def run(p):
        raise jp.GeminiUnavailable("503 unavailable")

    with pytest.raises(RuntimeError, match="no call finished"):
        jp.run_pool([jp.Task(run)], seed=8, stall_s=0.3)


def test_claude_lane_stops_at_the_daily_cap(monkeypatch):
    monkeypatch.setattr(jp, "CLAUDE_LANE_DAILY_CAP", 2)
    set_setting(jp.HELP_KEY, "always")

    def run(p):
        if p == "gemini":
            raise jp.GeminiUnavailable("503 unavailable")
        return p

    with pytest.raises(RuntimeError, match="no call finished"):
        jp.run_pool([jp.Task(run) for _ in range(5)], seed=9, stall_s=0.3)
    assert jp.claude_used_today() == 2


def test_a_bug_in_a_gemini_task_stops_the_pool():
    def run(p):
        raise ValueError("bug")

    with pytest.raises(ValueError, match="bug"):
        jp.run_pool([jp.Task(run)], seed=10)


def test_on_result_sees_every_task_once():
    seen = []
    jp.run_pool([jp.Task(lambda p, i=i: i) for i in range(10)], seed=11,
                on_result=lambda i, p, v: seen.append((i, v)))
    assert sorted(seen) == [(i, i) for i in range(10)]


def test_unknown_stored_mode_reads_as_the_default():
    set_setting(jp.HELP_KEY, "bogus")
    assert jp.help_mode() == "down"


def test_settings_saves_only_known_claude_help_modes():
    from starlette.testclient import TestClient
    from src.web.app import app

    client = TestClient(app)
    client.post("/settings/claude-help", data={"mode": "always"}, follow_redirects=False)
    assert jp.help_mode() == "always"
    client.post("/settings/claude-help", data={"mode": "everything"}, follow_redirects=False)
    assert jp.help_mode() == "always"  # an unknown value from the form is ignored
    page = client.get("/settings").text
    assert "Claude help for the judge" in page and '<option value="always" selected>' in page
