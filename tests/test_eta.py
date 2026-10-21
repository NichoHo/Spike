"""ETA: stream-length scaling, defaults without history, and live transcribe progress."""

from datetime import datetime, timedelta, timezone

import pytest

from src.db import (
    estimate_remaining_seconds,
    get_connection,
    init_db,
    register_video,
    set_stage_progress,
    set_video_duration,
    update_video_stage,
)


def _running_job(started_ago_s: float) -> int:
    init_db()
    with get_connection() as conn:
        conn.execute("DELETE FROM stage_timings")
    vid = register_video("url", f"https://example.test/eta/{datetime.now().timestamp()}")
    set_video_duration(vid, 3600)
    update_video_stage(vid, "transcribe", status="running")
    started = (datetime.now(timezone.utc) - timedelta(seconds=started_ago_s)).isoformat()
    with get_connection() as conn:
        conn.execute("UPDATE stage_timings SET started_at = ? WHERE video_id = ?", (started, vid))
    return vid


# Defaults for the stages after transcribe on a 1 h stream: signals 36 + moments 72 + 120 + 120 + 600.
AFTER_TRANSCRIBE = 948


def test_eta_without_progress_uses_length_scaled_defaults():
    vid = _running_job(100)
    eta = estimate_remaining_seconds([{"id": vid, "status": "running", "stage": "transcribe", "duration_s": 3600}])
    # transcribe default 0.25 s per stream second -> 900 s expected, 100 s already spent
    assert eta[vid] == pytest.approx(800 + AFTER_TRANSCRIBE, abs=2)


def test_eta_with_progress_extrapolates_from_elapsed():
    vid = _running_job(100)
    set_stage_progress(vid, 0.5)
    eta = estimate_remaining_seconds([{"id": vid, "status": "running", "stage": "transcribe", "duration_s": 3600}])
    assert eta[vid] == pytest.approx(100 + AFTER_TRANSCRIBE, abs=2)
