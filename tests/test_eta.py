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


def test_eta_uses_recent_speed_not_the_slow_start():
    import json, time
    vid = _running_job(7200)  # two hours in, but only recently up to speed
    set_stage_progress(vid, 0.1)
    now = time.time()  # last 5 min: 0.2 -> 0.3 of the stage, so 0.7 left takes 2100 s
    with get_connection() as conn:
        conn.execute("UPDATE stage_timings SET progress = 0.3, progress_samples = ? WHERE video_id = ?",
                     (json.dumps([[now - 300, 0.2], [now, 0.3]]), vid))
    eta = estimate_remaining_seconds([{"id": vid, "status": "running", "stage": "transcribe", "duration_s": 3600}])
    assert eta[vid] == pytest.approx(2100 + AFTER_TRANSCRIBE, abs=2)


def test_eta_history_uses_median_so_one_stalled_run_does_not_skew_it():
    vid = _running_job(0)
    for i, secs in enumerate([360, 360, 360, 360 * 50]):  # three normal runs, one stalled
        past = register_video("url", f"https://example.test/eta/past/{i}/{datetime.now().timestamp()}")
        set_video_duration(past, 3600)
        end = datetime.now(timezone.utc)
        with get_connection() as conn:
            conn.execute("INSERT INTO stage_timings (video_id, stage, started_at, finished_at) VALUES (?, 'transcribe', ?, ?)",
                         (past, (end - timedelta(seconds=secs)).isoformat(), end.isoformat()))
    eta = estimate_remaining_seconds([{"id": vid, "status": "running", "stage": "transcribe", "duration_s": 3600}])
    assert eta[vid] == pytest.approx(360 + AFTER_TRANSCRIBE, abs=2)


def test_download_fraction_from_bytes_or_fragments():
    from src.pipeline.stage2_audio import _download_fraction
    assert _download_fraction({"downloaded_bytes": 50, "total_bytes_estimate": 200}) == 0.25
    assert _download_fraction({"downloaded_bytes": 50, "fragment_index": 3, "fragment_count": 4}) == 0.75
    assert _download_fraction({"downloaded_bytes": 50}) is None
