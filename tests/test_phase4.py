"""
Phase 4 Test Suite: Web App, Auth, Routing, Re-render, Security, and Worker.
Blueprint §3, §4, §8, §10, §13 (Phase 4).
"""

import os
import io
import pytest
from starlette.testclient import TestClient

from src.db import (
    init_db,
    create_user,
    update_user_status,
    get_user_by_login,
    list_review_clips,
    get_clip,
    update_clip_status,
    list_sources,
    create_source,
    get_source,
    delete_source,
    register_video,
    get_job,
    update_video_stage,
)
from src.notify import verify_discord_webhook, send_job_ready_notification
from src.worker import claim_next_job
from src.web.app import app


@pytest.fixture(scope="module")
def client():
    init_db()
    with TestClient(app) as test_client:
        yield test_client


# ── 1. Auth & Tailscale Serve Headers ─────────────────────────────────────────

def test_auth_tailscale_headers_and_fallback(client):
    # Valid Tailscale user header
    res_valid = client.get("/", headers={"Tailscale-User-Login": "admin@local"})
    assert res_valid.status_code == 200

    # Unknown Tailscale header -> 403
    res_unknown = client.get("/", headers={"Tailscale-User-Login": "random_stranger@tailscale.net"})
    assert res_unknown.status_code == 403
    assert "Access denied" in res_unknown.text or "restricted" in res_unknown.text

    # Inactive user -> 403
    test_user_id = create_user("test_disabled@tailscale.net", "Disabled User", role="member")
    update_user_status(test_user_id, 0)
    res_disabled = client.get("/", headers={"Tailscale-User-Login": "test_disabled@tailscale.net"})
    assert res_disabled.status_code == 403

    # Member user role checks
    member_login = "test_member@tailscale.net"
    if not get_user_by_login(member_login):
        create_user(member_login, "Test Member", role="member")

    res_member_home = client.get("/", headers={"Tailscale-User-Login": member_login})
    assert res_member_home.status_code == 200

    res_member_settings = client.get("/settings", headers={"Tailscale-User-Login": member_login})
    assert res_member_settings.status_code == 403

    # Local fallback (no Tailscale header) -> 200
    res_local = client.get("/settings")
    assert res_local.status_code == 200


# ── 2. Screen Rendering ───────────────────────────────────────────────────────

def test_all_screens_render_200(client):
    endpoints = ["/", "/new", "/sources", "/jobs", "/jobs/table", "/settings"]
    for path in endpoints:
        res = client.get(path)
        assert res.status_code == 200, f"Endpoint {path} failed with {res.status_code}"
        assert len(res.text) > 200, f"Endpoint {path} returned suspiciously empty body"

    # Detail view for existing clip 1
    res_clip = client.get("/clips/1")
    assert res_clip.status_code == 200
    assert "Why this clip" in res_clip.text
    assert "Re-render clip" in res_clip.text


# ── 3. Sources CRUD ───────────────────────────────────────────────────────────

def test_sources_crud(client):
    # Create source
    src_data = {
        "kind": "twitch",
        "external_id": "test_streamer_123",
        "display_name": "Test Streamer",
        "permission": "written",
        "permission_note": "Signed clip agreement 2026-10",
        "auto_process": True,
        "layout": "face_track",
        "caption_style": "karaoke",
        "style_notes": "Fast-paced gaming streamer",
    }
    res_create = client.post("/sources/new", data=src_data, follow_redirects=False)
    assert res_create.status_code == 303

    sources = [dict(s) for s in list_sources()]
    created = [s for s in sources if s["external_id"] == "test_streamer_123"]
    assert len(created) == 1
    src_id = created[0]["id"]
    assert created[0]["permission"] == "written"

    # Edit source
    edit_data = {
        "display_name": "Test Streamer Updated",
        "permission": "own",
        "permission_note": "Self owned channel",
        "auto_process": False,
        "layout": "split",
        "caption_style": "clean",
        "style_notes": "Updated notes",
    }
    res_edit = client.post(f"/sources/{src_id}/edit", data=edit_data, follow_redirects=False)
    assert res_edit.status_code == 303

    updated = get_source(src_id)
    assert updated["display_name"] == "Test Streamer Updated"
    assert updated["layout"] == "split"

    # Delete source
    res_del = client.post(f"/sources/{src_id}/delete", follow_redirects=False)
    assert res_del.status_code == 303
    assert get_source(src_id) is None


# ── 4. Jobs Queue and Control ─────────────────────────────────────────────────

def test_jobs_control(client):
    # Register test failed video
    vid = register_video("url", "https://youtube.com/watch?v=fake_for_retry", title="Test Retry Video")
    update_video_stage(vid, "fetch_audio", status="failed", error="Simulated network failure")

    job_before = get_job(vid)
    assert job_before["status"] == "failed"

    # Retry job
    res_retry = client.post(f"/jobs/{vid}/retry", follow_redirects=False)
    assert res_retry.status_code == 303
    job_after = get_job(vid)
    assert job_after["status"] == "queued"
    assert job_after["error"] is None

    # Cancel job
    res_cancel = client.post(f"/jobs/{vid}/cancel", follow_redirects=False)
    assert res_cancel.status_code == 303
    job_cancelled = get_job(vid)
    assert job_cancelled["status"] == "done"


# ── 5. Upload Security and Input Validation ───────────────────────────────────

def test_upload_security_and_url_validation(client):
    # Disallowed file extension (.exe) -> 400
    res_ext = client.post(
        "/new/submit",
        data={"tab": "upload"},
        files={"file": ("malicious.exe", b"fake binary content", "application/octet-stream")},
    )
    assert res_ext.status_code == 400
    assert "Unsupported file format" in res_ext.text

    # Corrupt fake video file (.mp4 but fails ffprobe check) -> 400
    res_fake = client.post(
        "/new/submit",
        data={"tab": "upload"},
        files={"file": ("corrupt.mp4", b"not a real video stream", "video/mp4")},
    )
    assert res_fake.status_code == 400
    assert "Security check failed" in res_fake.text

    # Disallowed host URL -> 400
    res_bad_host = client.post(
        "/new/submit",
        data={"tab": "url", "url": "https://unauthorized-domain.com/video"},
    )
    assert res_bad_host.status_code == 400
    assert "is not supported" in res_bad_host.text

    # Valid YouTube URL -> 303 queued
    res_valid_url = client.post(
        "/new/submit",
        data={"tab": "url", "url": "https://www.youtube.com/watch?v=D1hIpF1C_r4"},
        follow_redirects=False,
    )
    assert res_valid_url.status_code == 303

    # Bad clip count -> 400
    res_bad_count = client.post(
        "/new/submit",
        data={"tab": "url", "url": "https://www.youtube.com/watch?v=x", "target_clips": "abc"},
    )
    assert res_bad_count.status_code == 400


def test_target_clips_auto_vs_explicit(client):
    import json
    from src.db import get_connection

    def submit(count):
        client.post("/new/submit", data={"tab": "url", "url": "https://www.youtube.com/watch?v=x", "target_clips": count},
                    follow_redirects=False)
        with get_connection() as conn:
            return json.loads(conn.execute("SELECT settings FROM videos ORDER BY id DESC LIMIT 1").fetchone()[0])

    assert "target_clips" not in submit("")  # Auto: stage 6 picks from video length
    assert submit("4")["target_clips"] == 4
    assert submit("50")["target_clips"] == 15


# ── 6. Clip Lifecycle, Streaming & Download ───────────────────────────────────

def test_clip_lifecycle_and_download(client):
    # Stream
    res_stream = client.get("/media/clip/1/stream")
    assert res_stream.status_code == 200
    assert res_stream.headers.get("content-type") == "video/mp4"

    # Thumb
    res_thumb = client.get("/media/clip/1/thumb")
    assert res_thumb.status_code == 200
    assert res_thumb.headers.get("content-type") == "image/jpeg"

    # Download attachment
    res_dl = client.get("/clips/1/download")
    assert res_dl.status_code == 200
    assert "attachment" in res_dl.headers.get("content-disposition", "")

    # Approve
    res_app = client.post("/clips/1/approve", follow_redirects=False)
    assert res_app.status_code == 303
    assert get_clip(1)["status"] == "approved"

    # Reject
    res_rej = client.post("/clips/1/reject", data={"reason": "punchline cutoff"}, follow_redirects=False)
    assert res_rej.status_code == 303
    c1 = get_clip(1)
    assert c1["status"] == "rejected"
    assert c1["reject_reason"] == "punchline cutoff"

    # Reset
    update_clip_status(1, "ready")


# ── 7. Discord Webhook Helper ─────────────────────────────────────────────────

def test_discord_webhook_helper():
    # Empty url rejection
    ok, msg = verify_discord_webhook("")
    assert not ok
    assert "empty" in msg

    # Notification call with non-configured webhook does not crash
    assert not send_job_ready_notification(999999)


# ── 8. Worker Claiming ────────────────────────────────────────────────────────

def test_worker_claim():
    # Verify worker claims queued jobs in priority order
    init_db()
    unique_url = f"https://youtube.com/watch?v=worker_test_{os.urandom(4).hex()}"
    vid = register_video("url", unique_url, priority=100)
    claimed = claim_next_job()
    assert claimed is not None
    assert claimed["id"] == vid
    assert claimed["origin"] == "url"
