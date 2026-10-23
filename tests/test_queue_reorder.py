"""Queue reorder: priorities follow the chosen order, and a running job that loses first place is paused at
its next stage boundary (only after the person confirms)."""

import pytest
from starlette.testclient import TestClient

import src.worker as worker
from src.db import (
    JobInterrupted,
    enter_stage,
    get_connection,
    get_job,
    init_db,
    list_jobs,
    register_video,
    reorder_queue,
)
from src.web.app import app


@pytest.fixture
def jobs():
    init_db()
    with get_connection() as conn:  # the test DB is a copy of the real one: park its live jobs
        conn.execute("UPDATE videos SET status = 'done' WHERE status IN ('queued', 'running')")
    a = register_video("url", "https://example.com/reorder-a", title="A")
    b = register_video("url", "https://example.com/reorder-b", title="B")
    c = register_video("url", "https://example.com/reorder-c", title="C")
    with get_connection() as conn:
        conn.execute("UPDATE videos SET status = 'queued', stage = 'fetch_meta', priority = 1, claimed_at = NULL WHERE id IN (?, ?, ?)", (a, b, c))
    yield a, b, c
    with get_connection() as conn:
        conn.execute("DELETE FROM videos WHERE id IN (?, ?, ?)", (a, b, c))


def _queued_order():
    return [j["id"] for j in list_jobs() if j["status"] == "queued"]


def test_reorder_sets_claim_order(jobs):
    a, b, c = jobs
    assert reorder_queue([c, a, b]) == {"paused": None}
    assert _queued_order() == [c, a, b]
    assert worker.claim_next_job()["id"] == c


def test_new_manual_job_joins_after_the_custom_order(jobs):
    a, b, c = jobs
    reorder_queue([b, c, a])
    d = register_video("url", "https://example.com/reorder-d", title="D", priority=10)
    try:
        assert _queued_order()[:4] == [b, c, a, d]
    finally:
        with get_connection() as conn:
            conn.execute("DELETE FROM videos WHERE id = ?", (d,))


def test_running_job_moved_down_needs_confirm_then_pauses(jobs):
    a, b, c = jobs
    assert worker.claim_next_job()["id"] == a  # a is running now
    enter_stage(a, "transcribe")

    assert reorder_queue([b, a, c]) == {"needs_confirm": a}
    assert get_job(a)["status"] == "running"  # nothing changed without confirmation

    assert reorder_queue([b, a, c], allow_pause=True) == {"paused": a}
    assert get_job(a)["status"] == "queued"
    with pytest.raises(JobInterrupted) as exc:
        enter_stage(a, "signals")  # the pipeline stops at its next boundary...
    assert exc.value.status == "queued"
    assert get_job(a)["stage"] == "transcribe"  # ...and resumes from the stage it had reached
    assert worker.claim_next_job()["id"] == b


def test_running_job_kept_first_is_not_paused(jobs):
    a, b, c = jobs
    worker.claim_next_job()
    assert reorder_queue([a, c, b]) == {"paused": None}
    assert get_job(a)["status"] == "running"
    enter_stage(a, "fetch_audio")  # no interrupt


def test_worker_does_not_mark_a_paused_job_failed(jobs, monkeypatch):
    a, b, c = jobs

    def fake_pipeline(source_input, source_settings, video_id):
        reorder_queue([b, a, c], allow_pause=True)
        enter_stage(video_id, "fetch_audio")

    monkeypatch.setattr(worker, "run_pipeline", fake_pipeline)
    monkeypatch.setattr(worker, "source_settings_for", lambda *a: {})
    assert worker.run_worker_cycle() is True
    job = get_job(a)
    assert job["status"] == "queued" and job["error"] is None


def test_cancel_now_stops_a_running_job(jobs):
    from src.db import cancel_job
    a, b, c = jobs
    worker.claim_next_job()
    cancel_job(a)
    with pytest.raises(JobInterrupted):
        enter_stage(a, "fetch_audio")
    assert get_job(a)["status"] == "done"  # previously the next stage flipped it back to running


def test_reorder_route(jobs):
    a, b, c = jobs
    worker.claim_next_job()
    client = TestClient(app)
    r = client.post("/jobs/reorder", json={"order": [b, a, c]})
    assert r.status_code == 409 and r.json() == {"needs_confirm": a}
    r = client.post("/jobs/reorder", json={"order": [b, a, c], "confirm_pause": True})
    assert r.status_code == 200 and r.json() == {"paused": a}
    assert client.post("/jobs/reorder", json={"order": ["x"]}).status_code == 400
    html = client.get("/jobs").text
    assert 'id="reorder-dialog"' in html and f'data-queue-id="{b}"' in html
