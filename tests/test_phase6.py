"""
Spike: Phase 6 Test Suite (Platform Posting, Scheduling, Encryption, and Permissions).
Blueprint §8, §9, §12, §13 (Phase 6).

Exit criteria:
1. Accounts screen with OAuth connection for TikTok, YouTube, and Instagram. Access and refresh
   tokens encrypted at rest via Fernet.
2. TikTok upload-to-inbox mode (lands in creator's TikTok inbox, status='sent_to_inbox').
3. YouTube Shorts upload (marked privacyStatus: "private" until audit).
4. Auto-post rules (§8.3): permission check, score floors (final_score >= 80, raw llm_score >= 70),
   account daily cap (3/day), needs_context == 0.
5. Scheduling (§8.4) with slots and background scheduler tick.
6. Hard enforcement: permission = 'none' clip cannot post through any path (code, API, scheduler, UI).
"""

import os
import json
import tempfile
from pathlib import Path
from datetime import datetime, timezone, timedelta

import pytest
from starlette.testclient import TestClient

from src.db import (
    init_db,
    get_connection,
    create_source,
    register_video,
    insert_candidate,
    create_or_update_clip,
    get_clip_with_details,
    create_account,
    get_account,
    list_accounts,
    delete_account,
    create_post,
    get_post,
    get_post_with_details,
    list_posts,
    count_account_daily_posts,
)
from src.security import encrypt_token, decrypt_token
from src.posting import (
    verify_clip_posting_permission,
    dispatch_post,
    evaluate_clip_autopost,
    run_posting_scheduler_cycle,
    PermissionBlockedError,
    DEFAULT_DAILY_POST_CAP,
)
from src.web.app import app


@pytest.fixture(autouse=True)
def setup_test_db():
    init_db()
    with get_connection() as conn:
        conn.execute("DELETE FROM posts")
        conn.execute("DELETE FROM accounts")


@pytest.fixture
def dummy_media_file():
    """Create a temporary video file on disk to simulate a rendered clip."""
    with tempfile.NamedTemporaryFile(suffix=".mp4", delete=False) as f:
        f.write(b"\x00\x00\x00\x1cftypisom\x00\x00\x02\x00isomiso2mp41\x00\x00\x00\x08free")
        temp_path = Path(f.name)
    yield temp_path
    if temp_path.exists():
        try:
            temp_path.unlink()
        except Exception:
            pass


def _create_test_clip(permission: str = "own", final_score: int = 85, llm_score: int = 80, needs_context: int = 0, dummy_path: Path = None):
    """Helper to create a complete database hierarchy for a clip."""
    import uuid
    uid = uuid.uuid4().hex[:6]
    src_id = create_source({
        "kind": "twitch",
        "external_id": f"src_{uid}",
        "display_name": f"Streamer {uid}",
        "permission": permission,
        "permission_note": "Verified for tests",
    })
    vid_id = register_video(
        origin="url",
        url_or_path=f"https://twitch.tv/videos/{uid}",
        external_id=f"vid_{uid}",
        title=f"Stream VOD {uid}",
        source_id=src_id,
    )
    cand_id = insert_candidate(
        video_id=vid_id,
        cand={
            "start_s": 10.0,
            "end_s": 40.0,
            "title": f"Awesome Clip {uid}",
            "hook_text": f"Watch this {uid}!",
            "punchline": f"Haha {uid}!",
            "reason": "High hype and chat activity",
            "final_score": final_score,
            "signal_score": 80,
            "llm_score": llm_score,
            "mood": "funny",
            "chat_mood": "hype",
            "needs_context": needs_context,
            "features": ["gaming", "clip"],
            "status": "approved",
        },
    )
    file_path = str(dummy_path) if dummy_path else f"data/videos/{vid_id}/renders/clip_{cand_id}.mp4"
    clip_id = create_or_update_clip(
        candidate_id=cand_id,
        file_path=file_path,
        thumb_path=f"data/videos/{vid_id}/renders/thumb_{cand_id}.jpg",
        layout="face_track",
        caption_style="karaoke",
        trim_start_s=10.0,
        trim_end_s=40.0,
        status="ready",
    )
    return clip_id, src_id, vid_id, cand_id


# ── Test 1: Token Encryption at Rest (Blueprint §8, §9) ───────────────────────

def test_token_encryption_at_rest():
    """Verify access and refresh tokens are encrypted at rest using Fernet."""
    plain_token = "oauth2_bearer_secret_xyz123"
    plain_refresh = "oauth2_refresh_secret_abc456"

    account_id = create_account(
        platform="tiktok",
        display_name="@testcreator",
        access_token=plain_token,
        refresh_token=plain_refresh,
    )

    # 1. Inspect raw DB bytes
    with get_connection() as conn:
        row = conn.execute("SELECT access_token_enc, refresh_token_enc FROM accounts WHERE id = ?", (account_id,)).fetchone()
        raw_enc = row["access_token_enc"]
        raw_ref = row["refresh_token_enc"]

        # Raw DB values must be bytes, not plain text string
        assert isinstance(raw_enc, bytes)
        assert plain_token.encode("utf-8") not in raw_enc
        assert isinstance(raw_ref, bytes)
        assert plain_refresh.encode("utf-8") not in raw_ref

    # 2. Decrypt via get_account(..., decrypt=True)
    decrypted_acc = get_account(account_id, decrypt=True)
    assert decrypted_acc["access_token"] == plain_token
    assert decrypted_acc["refresh_token"] == plain_refresh

    # 3. list_accounts(decrypt=False) must not expose plaintext tokens or ciphertext
    public_accounts = list_accounts(decrypt=False)
    acc = next(a for a in public_accounts if a["id"] == account_id)
    assert "access_token" not in acc
    assert "access_token_enc" not in acc
    assert acc["display_name"] == "@testcreator"


# ── Test 2: Permission = 'none' Hard Block (Blueprint §8.3, §12) ───────────────

def test_permission_none_permanently_blocked(dummy_media_file):
    """
    Blueprint §12 & Exit Criteria:
    Verify that an automated test proves a permission = 'none' clip cannot post through any path.
    """
    clip_id, src_id, vid_id, cand_id = _create_test_clip(
        permission="none",  # Private review only!
        final_score=95,
        llm_score=90,
        dummy_path=dummy_media_file,
    )

    acc_id = create_account(
        platform="youtube",
        display_name="@teamchannel",
        access_token="mock_yt_token",
    )

    # Path 1: verify_clip_posting_permission strictly raises PermissionBlockedError
    with pytest.raises(PermissionBlockedError) as exc_info:
        verify_clip_posting_permission(clip_id)
    assert "permission='none'" in str(exc_info.value)

    # Path 2: dispatch_post strictly blocks execution
    post_id = create_post(
        clip_id=clip_id,
        account_id=acc_id,
        status="scheduled",
    )
    with pytest.raises(PermissionBlockedError):
        dispatch_post(post_id)

    # Path 3: evaluate_clip_autopost ignores permission = 'none' clips
    scheduled_posts = evaluate_clip_autopost(clip_id)
    assert len(scheduled_posts) == 0

    # Path 4: Web UI route /clips/{id}/post blocks with HTTP 403 Forbidden
    client = TestClient(app)
    resp = client.post(
        f"/clips/{clip_id}/post",
        data={
            "account_id": acc_id,
            "timing": "now",
            "caption": "Forbidden clip",
        },
        headers={"Tailscale-User-Login": "admin@local"},
    )
    assert resp.status_code == 403
    assert "Posting permanently blocked" in resp.text

    # Path 5: Web UI GET /clips/{id}/post renders blocked warning and hides form
    get_resp = client.get(
        f"/clips/{clip_id}/post",
        headers={"Tailscale-User-Login": "admin@local"},
    )
    assert get_resp.status_code == 200
    assert "Posting permanently blocked" in get_resp.text
    assert "<form" not in get_resp.text


# ── Test 3: TikTok Upload-to-Inbox (Blueprint §8.1, §8.2) ─────────────────────

def test_tiktok_upload_to_inbox(dummy_media_file):
    """
    Blueprint §8.1, §8.2 & Exit Criteria:
    Verify clip dispatch reaches TikTok inbox mode (status='sent_to_inbox').
    """
    clip_id, _, _, _ = _create_test_clip(permission="own", dummy_path=dummy_media_file)

    acc_id = create_account(
        platform="tiktok",
        display_name="@tiktok_creator",
        access_token="mock_tiktok_token_xyz",
    )

    post_id = create_post(
        clip_id=clip_id,
        account_id=acc_id,
        status="scheduled",
        caption="Epic TikTok clip #gaming",
    )

    res = dispatch_post(post_id)
    assert res["status"] == "sent_to_inbox"
    assert "platform_post_id" in res
    assert "inbox" in res["url"]

    # Verify database update
    updated_post = get_post_with_details(post_id)
    assert updated_post["status"] == "sent_to_inbox"
    assert updated_post["posted_at"] is not None
    assert updated_post["url"] == res["url"]


# ── Test 4: YouTube Shorts Private Upload (Blueprint §8.1) ─────────────────────

def test_youtube_shorts_private_upload(dummy_media_file):
    """
    Blueprint §8.1 & Exit Criteria:
    Verify YouTube Shorts upload succeeds with privacyStatus='private'.
    """
    clip_id, _, _, _ = _create_test_clip(permission="written", dummy_path=dummy_media_file)

    acc_id = create_account(
        platform="youtube",
        display_name="@youtube_shorts_channel",
        access_token="mock_youtube_token_abc",
    )

    post_id = create_post(
        clip_id=clip_id,
        account_id=acc_id,
        status="scheduled",
        caption="YouTube Short testing",
    )

    res = dispatch_post(post_id)
    assert res["status"] == "posted"
    assert res["privacy"] == "private"
    assert "youtube.com/shorts/" in res["url"]

    updated_post = get_post_with_details(post_id)
    assert updated_post["status"] == "posted"
    assert updated_post["posted_at"] is not None


# ── Test 5: Auto-Post Rules (§8.3) ────────────────────────────────────────────

def test_autopost_rules_score_floors_and_cap(dummy_media_file):
    """
    Blueprint §8.3:
    - final_score >= 80
    - raw llm_score >= 70
    - needs_context == 0
    - daily cap default 3 per day
    """
    # 1. High score clip (passes all checks)
    high_clip_id, _, _, _ = _create_test_clip(
        permission="own",
        final_score=85,
        llm_score=75,
        needs_context=0,
        dummy_path=dummy_media_file,
    )
    acc_id = create_account(
        platform="youtube",
        display_name="@autochannel",
        access_token="mock_token",
    )

    scheduled = evaluate_clip_autopost(high_clip_id)
    assert len(scheduled) == 1
    post = get_post(scheduled[0])
    assert post["status"] == "scheduled"

    # 2. Low final score (< 80)
    low_final_clip, _, _, _ = _create_test_clip(
        permission="own",
        final_score=79,
        llm_score=85,
        needs_context=0,
        dummy_path=dummy_media_file,
    )
    assert len(evaluate_clip_autopost(low_final_clip)) == 0

    # 3. Low LLM score (< 70)
    low_llm_clip, _, _, _ = _create_test_clip(
        permission="own",
        final_score=90,
        llm_score=68,
        needs_context=0,
        dummy_path=dummy_media_file,
    )
    assert len(evaluate_clip_autopost(low_llm_clip)) == 0

    # 4. needs_context == 1
    context_clip, _, _, _ = _create_test_clip(
        permission="own",
        final_score=90,
        llm_score=85,
        needs_context=1,
        dummy_path=dummy_media_file,
    )
    assert len(evaluate_clip_autopost(context_clip)) == 0

    # 5. Daily Cap Enforcement (default 3 posts per day)
    # We already have 1 post for acc_id. Add 2 more to hit cap = 3.
    clip_a, _, _, _ = _create_test_clip(permission="own", final_score=85, llm_score=75, dummy_path=dummy_media_file)
    clip_b, _, _, _ = _create_test_clip(permission="own", final_score=85, llm_score=75, dummy_path=dummy_media_file)
    clip_c, _, _, _ = _create_test_clip(permission="own", final_score=85, llm_score=75, dummy_path=dummy_media_file)

    res_a = evaluate_clip_autopost(clip_a)
    assert len(res_a) == 1
    res_b = evaluate_clip_autopost(clip_b)
    assert len(res_b) == 1

    # Now daily count is 3!
    today_prefix = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    assert count_account_daily_posts(acc_id, today_prefix) == 3

    # 4th clip must be skipped due to daily cap
    res_c = evaluate_clip_autopost(clip_c)
    assert len(res_c) == 0


# ── Test 6: Scheduling & Scheduler Cycle (§8.4) ───────────────────────────────

def test_scheduler_cycle_dispatches_due_posts(dummy_media_file):
    """
    Blueprint §8.4:
    Background scheduler cycle picks up posts whose scheduled_for <= now and dispatches them.
    """
    clip_id, _, _, _ = _create_test_clip(permission="program", dummy_path=dummy_media_file)
    acc_id = create_account(
        platform="tiktok",
        display_name="@scheduled_tok",
        access_token="mock_tok",
    )

    # Schedule post for 5 minutes in the past
    past_iso = (datetime.now(timezone.utc) - timedelta(minutes=5)).isoformat()
    post_id = create_post(
        clip_id=clip_id,
        account_id=acc_id,
        status="scheduled",
        scheduled_for=past_iso,
    )

    dispatched = run_posting_scheduler_cycle()
    assert dispatched >= 1

    updated = get_post(post_id)
    assert updated["status"] == "sent_to_inbox"


# ── Test 7: Web UI Routes & Endpoints ─────────────────────────────────────────

def test_web_routes_for_posts_and_accounts(dummy_media_file):
    """Verify web endpoints: /posts, /clips/{id}/post, /settings accounts."""
    client = TestClient(app)
    headers = {"Tailscale-User-Login": "admin@local"}

    # 1. Accounts in Settings
    add_resp = client.post(
        "/settings/accounts/add",
        data={
            "platform": "youtube",
            "display_name": "@spike_official",
            "access_token": "mock_token_123",
        },
        headers=headers,
        follow_redirects=True,
    )
    assert add_resp.status_code == 200
    assert "@spike_official" in add_resp.text

    accounts = list_accounts(decrypt=False)
    created_acc = next(a for a in accounts if a["display_name"] == "@spike_official")

    # 2. Posts monitoring screen
    posts_resp = client.get("/posts?tab=scheduled", headers=headers)
    assert posts_resp.status_code == 200
    assert "Posts" in posts_resp.text

    # 3. Post clip page & immediate publish
    clip_id, _, _, _ = _create_test_clip(permission="own", dummy_path=dummy_media_file)
    get_clip_post = client.get(f"/clips/{clip_id}/post", headers=headers)
    assert get_clip_post.status_code == 200
    assert "Post clip" in get_clip_post.text

    post_submit_resp = client.post(
        f"/clips/{clip_id}/post",
        data={
            "account_id": created_acc["id"],
            "timing": "now",
            "caption": "Published via Spike Web UI",
            "hashtags": "#Spike #Shorts",
        },
        headers=headers,
        follow_redirects=True,
    )
    assert post_submit_resp.status_code == 200
    assert "Published via Spike Web UI" in post_submit_resp.text

    # 4. Delete account
    del_resp = client.post(
        f"/settings/accounts/{created_acc['id']}/delete",
        headers=headers,
        follow_redirects=True,
    )
    assert del_resp.status_code == 200
