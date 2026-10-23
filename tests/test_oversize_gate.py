"""Oversized-input gate: thresholds, grounded message, ask/answer/timeout, and runner integration.

Modeled on tests/test_claude_fallback.py (threaded answerer, patched sleep) and tests/test_queue_reorder.py
(JobInterrupted + queued/running status) and tests/test_eta.py (register_video + duration).
"""

import threading
import time

import pytest

from src import oversize_gate as gate
from src.db import (
    JobInterrupted,
    get_connection,
    get_job,
    init_db,
    register_video,
    set_setting,
    set_video_duration,
)
from src.pipeline import runner

_real_sleep = time.sleep


def _answer_when_pending(approve, video_id=None):
    def run():
        for _ in range(400):
            req = gate.pending(video_id)
            if req:
                gate.answer(req["id"], approve)
                return
            _real_sleep(0.02)
    t = threading.Thread(target=run)
    t.start()
    return t


def _reset():
    set_setting(gate.REQUEST_KEY, "null")


# ── Pure helpers ───────────────────────────────────────────────────────────────

def test_estimate_scales_linearly_from_the_measured_2h_figure():
    two_h = gate.estimate_tokens(2 * 3600)
    assert two_h["lo"] == 250000 and two_h["hi"] == 450000  # anchored to the ~2 h = 250-450k measurement
    four_h = gate.estimate_tokens(4 * 3600)
    assert four_h["lo"] == 500000 and four_h["hi"] == 900000


def test_remaining_stages_are_moments_onward():
    assert gate.remaining_stages() == ["moments", "fetch_sections", "render", "render_vertical"]
    assert len(gate.STAGES) == 10 and gate.STAGES.index("moments") == 6


def test_message_is_grounded_and_level_two_is_escalated():
    dur = 5 * 3600  # 5 h: over the 4 h threshold, under the 6 h ceiling
    m1 = gate.build_message(42, "Big VOD", dur, level=1, public_url="http://host:8000")
    assert "20,300 tokens per moment" in m1 and "$0.052" in m1 and "n=80 real calls" in m1
    assert "25,000-45,000" in m1 and "250,000-450,000" in m1
    assert "moments -> fetch_sections -> render -> render_vertical" in m1
    assert "stage 7 of 10" in m1 and "Job #42" in m1
    assert "60 min over the 4 h threshold" in m1  # (5h - 4h) = 60 min
    assert "/jobs" in m1

    m2 = gate.build_message(42, "Big VOD", 7 * 3600, level=2, public_url="http://host:8000")
    assert "ceiling" in m2 and "no truncation" in m2 and "60 min over the 6 h ceiling" in m2


# ── ask / answer / pending ───────────────────────────────────────────────────

def test_ask_waits_for_continue_and_stop(monkeypatch):
    monkeypatch.setattr(gate, "_notify", lambda text: None)
    monkeypatch.setattr(gate.time, "sleep", lambda s: _real_sleep(0.02))
    _reset()

    t = _answer_when_pending(True)
    assert gate.ask(1, "v", 5 * 3600, 1, "http://h") == "continue"
    t.join()

    _reset()
    t = _answer_when_pending(False)
    assert gate.ask(1, "v", 5 * 3600, 1, "http://h") == "stop"
    t.join()
    _reset()


def test_ask_returns_cached_decision_without_asking_again(monkeypatch):
    # After a Continue, a parked job re-reaching the SAME level must not re-ask.
    monkeypatch.setattr(gate, "_notify", lambda text: None)
    monkeypatch.setattr(gate.time, "sleep", lambda s: _real_sleep(0.02))
    _reset()
    t = _answer_when_pending(True, video_id=7)
    assert gate.ask(7, "v", 5 * 3600, 1, "http://h") == "continue"
    t.join()
    # No answerer thread this time: a cached 'continue' for (7, level 1) returns at once.
    assert gate.ask(7, "v", 5 * 3600, 1, "http://h") == "continue"
    _reset()


def test_ask_times_out_and_parks(monkeypatch):
    monkeypatch.setattr(gate, "_notify", lambda text: None)
    monkeypatch.setattr(gate.time, "sleep", lambda s: _real_sleep(0.02))
    monkeypatch.setattr(gate, "WAIT_S", 0.1)  # nobody answers
    _reset()
    vid = _running_job(5 * 3600)  # a real row so the timeout log_event's FK holds
    assert gate.ask(vid, "v", 5 * 3600, 1, "http://h") == "timeout"
    assert gate.pending(vid) is not None  # record stays so the Jobs-page buttons can still answer it
    _reset()


# ── Runner integration ─────────────────────────────────────────────────────────

def _running_job(duration_s: float) -> int:
    init_db()
    vid = register_video("url", f"https://example.test/gate/{time.time()}", title="GateJob")
    with get_connection() as conn:
        conn.execute("UPDATE videos SET status = 'running' WHERE id = ?", (vid,))
    set_video_duration(vid, duration_s)
    return vid


def test_gate_noop_below_threshold(monkeypatch):
    called = []
    monkeypatch.setattr(gate, "ask", lambda *a, **k: called.append(a) or "continue")
    vid = _running_job(3 * 3600)
    runner._oversize_gate(vid, {"duration": 3 * 3600, "title": "GateJob"})  # under 4 h
    assert called == []  # the gate never asked


def test_gate_stop_cancels_the_job(monkeypatch):
    monkeypatch.setattr(gate, "ask", lambda *a, **k: "stop")
    vid = _running_job(5 * 3600)
    with pytest.raises(JobInterrupted) as exc:
        runner._oversize_gate(vid, {"duration": 5 * 3600, "title": "GateJob"})
    assert exc.value.status == "cancelled"
    assert get_job(vid)["status"] == "done" and "too long" in (get_job(vid)["error"] or "")


def test_gate_timeout_parks_the_job(monkeypatch):
    monkeypatch.setattr(gate, "ask", lambda *a, **k: "timeout")
    vid = _running_job(5 * 3600)
    with pytest.raises(JobInterrupted) as exc:
        runner._oversize_gate(vid, {"duration": 5 * 3600, "title": "GateJob"})
    assert exc.value.status == "queued"
    assert get_job(vid)["status"] == "queued"  # back in the queue for the next worker claim


def test_gate_continue_past_ceiling_asks_twice_then_proceeds(monkeypatch):
    levels = []
    monkeypatch.setattr(gate, "ask", lambda video_id, title, dur, level, url: levels.append(level) or "continue")
    monkeypatch.setattr(gate, "clear", lambda vid: None)
    vid = _running_job(7 * 3600)  # over the 6 h ceiling
    runner._oversize_gate(vid, {"duration": 7 * 3600, "title": "GateJob"})
    assert levels == [1, 2]  # threshold, then the escalated ceiling question
    assert get_job(vid)["status"] == "running"  # proceeds into stage 7
