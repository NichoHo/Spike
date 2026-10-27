"""
Spike: Platform Posting Engine (TikTok, YouTube Shorts, Instagram Reels).
Blueprint §8, §9, §12, §13 (Phase 6).

Rollout & Rules:
1. TikTok upload-to-inbox: free, no audit, lands in creator's TikTok inbox.
2. YouTube Shorts: private uploads until compliance audit passes.
3. Instagram Reels: resumable container upload, wait for processing, then publish.
4. Permission = none is strictly BLOCKED in code (raises PermissionBlockedError).
5. Auto-post rules (§8.3): permission check, score floor (final >= 80, raw LLM >= 70),
   daily cap (default 3/day), no needs_context.
6. Scheduler (§8.4): scheduled slots at 12:00 and 19:00 local time, or immediate 'now'.
"""

from __future__ import annotations

import json
import logging
import os
import re
import time
import urllib.request
import urllib.error
from datetime import datetime, timezone, timedelta
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

from src import config
from src.music import music_credit
from src.platform_auth import IG_API, fresh_token
from src.db import (
    get_connection,
    get_account,
    get_clip_with_details,
    get_post_with_details,
    create_post,
    update_post_status,
    count_account_daily_posts,
    get_due_posts,
    log_event,
    now_utc_iso,
)

logger = logging.getLogger("spike.posting")

# Daily auto-post cap per account (Blueprint §8.3)
DEFAULT_DAILY_POST_CAP = 3
AUTOPOST_MIN_FINAL_SCORE = 80
AUTOPOST_MIN_LLM_SCORE = 70


class PermissionBlockedError(Exception):
    """Raised when an action attempts to post a clip whose source has permission='none'."""
    pass


def verify_clip_posting_permission(clip_id: int) -> Dict[str, Any]:
    """
    Verify that a clip is permitted to be posted.
    Blueprint §12: permission = none BLOCKS posting in code, not just in UI.
    """
    clip_row = get_clip_with_details(clip_id)
    if not clip_row:
        raise ValueError(f"Clip #{clip_id} does not exist.")

    clip = dict(clip_row)
    source_perm = (clip.get("source_permission") or "none").strip().lower()

    if source_perm == "none":
        msg = (
            f"Posting permanently blocked: Clip #{clip_id} from source '{clip.get('source_name')}' "
            f"has permission='none' (private review only). Commercial or platform posting is prohibited."
        )
        logger.warning(msg)
        raise PermissionBlockedError(msg)

    return clip


def get_next_schedule_slot(base_dt: Optional[datetime] = None) -> datetime:
    """
    Calculate next scheduled slot (Blueprint §8.4: default slots at 12:00 and 19:00 local).
    """
    now = base_dt or datetime.now()
    # Candidate slots today
    slot_noon = now.replace(hour=12, minute=0, second=0, microsecond=0)
    slot_evening = now.replace(hour=19, minute=0, second=0, microsecond=0)

    if now < slot_noon - timedelta(minutes=10):
        return slot_noon
    elif now < slot_evening - timedelta(minutes=10):
        return slot_evening
    else:
        # Tomorrow at 12:00
        return (now + timedelta(days=1)).replace(hour=12, minute=0, second=0, microsecond=0)


# ── Platform Upload Implementations ───────────────────────────────────────────

def upload_to_tiktok_inbox(
    clip_path: Path,
    access_token: str,
    title: str,
) -> Dict[str, Any]:
    """
    Upload clip to creator's TikTok inbox via TikTok Creator API (Blueprint §8.1, §8.2).
    In unaudited / inbox mode, this requires no compliance audit; clip lands in TikTok inbox.
    """
    if not clip_path.exists():
        raise FileNotFoundError(f"Clip file not found: {clip_path}")

    # Simulated / Test Token Mode for unit testing & sandbox
    if access_token.startswith("mock_") or access_token.startswith("test_") or "mock" in access_token:
        mock_id = f"tt_inbox_{os.urandom(6).hex()}"
        return {
            "platform_post_id": mock_id,
            "status": "sent_to_inbox",
            "url": f"https://www.tiktok.com/inbox/{mock_id}",
            "mode": "upload_to_inbox",
        }

    # Live TikTok Creator Share / Direct Post Init Endpoint
    url = "https://open.tiktokapis.com/v2/post/publish/inbox/video/init/"
    video_size = clip_path.stat().st_size
    # TikTok takes one chunk up to 64 MB, else 10 MB chunks with the remainder added to the last one
    chunk_size = video_size if video_size <= 64 * 1024 * 1024 else 10 * 1024 * 1024
    chunk_count = video_size // chunk_size
    payload = {
        "source_info": {
            "source": "FILE_UPLOAD",
            "video_size": video_size,
            "chunk_size": chunk_size,
            "total_chunk_count": chunk_count,
        }
    }

    req = urllib.request.Request(
        url,
        data=json.dumps(payload).encode("utf-8"),
        headers={
            "Authorization": f"Bearer {access_token}",
            "Content-Type": "application/json; charset=UTF-8",
        },
        method="POST",
    )

    try:
        with urllib.request.urlopen(req, timeout=30) as resp:
            data = json.loads(resp.read().decode("utf-8"))
            publish_id = data.get("data", {}).get("publish_id", "")
            upload_url = data.get("data", {}).get("upload_url", "")

            if not upload_url:
                raise RuntimeError(f"TikTok did not return an upload URL: {data.get('error')}")
            video = clip_path.read_bytes()
            for i in range(chunk_count):
                start = i * chunk_size
                end = video_size if i == chunk_count - 1 else start + chunk_size
                put_req = urllib.request.Request(
                    upload_url,
                    data=video[start:end],
                    headers={
                        "Content-Type": "video/mp4",
                        "Content-Range": f"bytes {start}-{end - 1}/{video_size}",
                    },
                    method="PUT",
                )
                with urllib.request.urlopen(put_req, timeout=120):
                    pass

            return {
                "platform_post_id": publish_id,
                "status": "sent_to_inbox",
                "url": f"https://www.tiktok.com/inbox/{publish_id}",
                "mode": "upload_to_inbox",
            }
    except Exception as e:
        logger.error(f"TikTok upload failed: {e}")
        raise


def upload_to_youtube_shorts(
    clip_path: Path,
    access_token: str,
    title: str,
    description: str,
    tags: Optional[List[str]] = None,
) -> Dict[str, Any]:
    """
    Upload vertical video to YouTube Shorts (Blueprint §8.1: private until audit passes).
    """
    if not clip_path.exists():
        raise FileNotFoundError(f"Clip file not found: {clip_path}")

    # Ensure title contains #Shorts for vertical recognition
    clean_title = title.strip()
    if "#Shorts" not in clean_title and "#shorts" not in clean_title:
        clean_title = (clean_title[:85] + " #Shorts").strip()

    # Simulated / Test Mode
    if access_token.startswith("mock_") or access_token.startswith("test_") or "mock" in access_token:
        mock_id = f"yt_{os.urandom(6).hex()}"
        return {
            "platform_post_id": mock_id,
            "status": "posted",
            "url": f"https://youtube.com/shorts/{mock_id}",
            "privacy": "private",
        }

    # Live YouTube Data API v3 Resumable Upload
    init_url = "https://www.googleapis.com/upload/youtube/v3/videos?uploadType=resumable&part=snippet,status"
    metadata = {
        "snippet": {
            "title": clean_title[:100],
            "description": description[:5000],
            "tags": tags or ["Shorts", "Spike"],
            "categoryId": "22",
        },
        "status": {
            "privacyStatus": config.YOUTUBE_PRIVACY,
            "selfDeclaredMadeForKids": False,
        },
    }

    req = urllib.request.Request(
        init_url,
        data=json.dumps(metadata).encode("utf-8"),
        headers={
            "Authorization": f"Bearer {access_token}",
            "Content-Type": "application/json; charset=UTF-8",
            "X-Upload-Content-Type": "video/mp4",
            "X-Upload-Content-Length": str(clip_path.stat().st_size),
        },
        method="POST",
    )

    try:
        with urllib.request.urlopen(req, timeout=30) as resp:
            upload_url = resp.headers.get("Location")
            if not upload_url:
                raise RuntimeError("YouTube upload initialization did not return a Location header")

            # Stream video content
            with open(clip_path, "rb") as f:
                video_data = f.read()

            upload_req = urllib.request.Request(
                upload_url,
                data=video_data,
                headers={"Content-Type": "video/mp4"},
                method="PUT",
            )
            with urllib.request.urlopen(upload_req, timeout=120) as up_resp:
                result = json.loads(up_resp.read().decode("utf-8"))
                video_id = result.get("id", "")
                return {
                    "platform_post_id": video_id,
                    "status": "posted",
                    "url": f"https://youtube.com/shorts/{video_id}",
                    "privacy": config.YOUTUBE_PRIVACY,
                }
    except Exception as e:
        logger.error(f"YouTube upload failed: {e}")
        raise


def upload_to_instagram_reels(
    clip_path: Path,
    access_token: str,
    caption: str,
    ig_user_id: str = "me",
) -> Dict[str, Any]:
    """
    Upload clip to Instagram Reels via Graph API.
    """
    if not clip_path.exists():
        raise FileNotFoundError(f"Clip file not found: {clip_path}")

    # Simulated / Test Mode
    if access_token.startswith("mock_") or access_token.startswith("test_") or "mock" in access_token:
        mock_id = f"ig_{os.urandom(6).hex()}"
        return {
            "platform_post_id": mock_id,
            "status": "posted",
            "url": f"https://www.instagram.com/reel/{mock_id}/",
        }

    from src.outreach.google import _http

    # Resumable upload sends the file itself, so Meta does not need a public URL to fetch it from
    _, _, made = _http("POST", f"{IG_API}/{ig_user_id}/media", token=access_token,
                       json_body={"media_type": "REELS", "upload_type": "resumable", "caption": caption[:2200]})
    container_id = made["id"]
    video = clip_path.read_bytes()
    _http("POST", made["uri"], data=video, timeout=300,
          headers={"Authorization": f"OAuth {access_token}", "offset": "0", "file_size": str(len(video))})

    # Instagram processes the video before it can be published; usually under a minute
    for _ in range(60):
        _, _, st = _http("GET", f"{IG_API}/{container_id}?fields=status_code,status", token=access_token)
        code = (st or {}).get("status_code")
        if code == "FINISHED":
            break
        if code in ("ERROR", "EXPIRED"):
            raise RuntimeError(f"Instagram could not process the video: {(st or {}).get('status')}")
        time.sleep(5)
    else:
        raise RuntimeError("Instagram was still processing the video after 5 minutes.")

    _, _, pub = _http("POST", f"{IG_API}/{ig_user_id}/media_publish", token=access_token,
                      json_body={"creation_id": container_id})
    media_id = pub["id"]
    _, _, info = _http("GET", f"{IG_API}/{media_id}?fields=permalink", token=access_token)
    return {
        "platform_post_id": media_id,
        "status": "posted",
        "url": (info or {}).get("permalink", ""),
    }


# ── Core Dispatch & Execution ─────────────────────────────────────────────────

def dispatch_post(post_id: int) -> Dict[str, Any]:
    """
    Dispatch and upload a post to its connected platform.
    Enforces permission != 'none' check in code!
    """
    post_row = get_post_with_details(post_id)
    if not post_row:
        raise ValueError(f"Post #{post_id} does not exist.")

    post = dict(post_row)
    clip_id = post["clip_id"]
    account_id = post["account_id"]

    # 1. Enforce permission != 'none' check in code (Blueprint §8.3, §12)
    verify_clip_posting_permission(clip_id)

    # 2. Retrieve account and decrypted tokens
    account = get_account(account_id, decrypt=True)
    if not account:
        raise ValueError(f"Account #{account_id} not found.")

    # 3. Locate clip media file
    clip_path = Path(post["clip_file_path"]) if post.get("clip_file_path") else None
    if not clip_path or not clip_path.exists():
        err = f"Rendered video file is missing on disk: {clip_path}"
        update_post_status(post_id, "failed", error=err)
        raise FileNotFoundError(err)

    # 4. Mark status as uploading
    update_post_status(post_id, "uploading")

    platform = account["platform"]
    caption = post.get("caption") or post.get("cand_caption") or post.get("clip_title") or "Short video"
    hashtags = post.get("hashtags") or post.get("cand_hashtags") or "[]"
    tag_list = json.loads(hashtags) if isinstance(hashtags, str) and hashtags.startswith("[") else []
    full_caption = caption + " " + " ".join(f"#{t.lstrip('#')}" for t in tag_list) if tag_list else caption
    # CC BY music must be credited on every post that uses it
    credit = music_credit(post.get("clip_music_track"))
    if credit and credit not in full_caption:
        full_caption = f"{full_caption}\n\n{credit}"

    try:
        access_token = fresh_token(account)
        if platform == "tiktok":
            res = upload_to_tiktok_inbox(
                clip_path=clip_path,
                access_token=access_token,
                title=post.get("clip_title") or caption,
            )
        elif platform == "youtube":
            res = upload_to_youtube_shorts(
                clip_path=clip_path,
                access_token=access_token,
                title=post.get("clip_title") or caption,
                description=full_caption,
                tags=tag_list,
            )
        elif platform == "instagram":
            res = upload_to_instagram_reels(
                clip_path=clip_path,
                access_token=access_token,
                caption=full_caption,
                ig_user_id=account.get("platform_user_id") or "me",
            )
        else:
            raise ValueError(f"Unsupported platform: {platform}")

        final_status = res.get("status", "posted")
        platform_post_id = res.get("platform_post_id", "")
        post_url = res.get("url", "")

        update_post_status(
            post_id=post_id,
            status=final_status,
            platform_post_id=platform_post_id,
            url=post_url,
        )

        log_event(
            "info",
            f"Post #{post_id} dispatched to {platform} ({final_status}, ID: {platform_post_id})",
            video_id=post.get("video_id"),
        )
        return res

    except Exception as e:
        err_msg = str(e)
        logger.error(f"Post #{post_id} failed: {err_msg}")
        update_post_status(post_id, "failed", error=err_msg)
        log_event("error", f"Post #{post_id} failed to dispatch to {platform}: {err_msg}")
        raise


# ── Auto-Post Rule Evaluator (§8.3) ───────────────────────────────────────────

def evaluate_clip_autopost(
    clip_id: int,
    source_settings: Optional[Dict[str, Any]] = None,
) -> List[int]:
    """
    Evaluate Blueprint §8.3 auto-post rules for a newly ready clip.
    Returns list of created post IDs (if any scheduled).
    """
    try:
        clip = verify_clip_posting_permission(clip_id)
    except PermissionBlockedError:
        # Permission is 'none' -> silently skip auto-post
        return []

    # 'review' sources: a person approves and posts each clip, never automatic
    if (clip.get("source_permission") or "").strip().lower() == "review":
        return []

    # Check needs_context flag
    if clip.get("needs_context"):
        return []

    # Check score floors (Blueprint §8.3: final_score >= 80, raw llm_score >= 70)
    final_score = int(clip.get("final_score") or 0)
    llm_score = int(clip.get("llm_score") or 0)
    if final_score < AUTOPOST_MIN_FINAL_SCORE or llm_score < AUTOPOST_MIN_LLM_SCORE:
        return []

    source_id = clip.get("source_id")
    if not source_id:
        return []

    # Get accounts configured for auto-post
    from src.db import list_accounts
    accounts = list_accounts(decrypt=False)
    if not accounts:
        return []

    scheduled_post_ids: List[int] = []
    # YouTube's daily upload quota resets at midnight Pacific, same as Gemini's, so the
    # posting-cap "day" uses the shared Pacific helper rather than the machine's UTC day.
    from src import gemini_budget
    today_prefix = gemini_budget.today()

    for acc in accounts:
        acc_id = acc["id"]
        # Check daily posting cap (Blueprint §8.3: default 3 per day)
        daily_count = count_account_daily_posts(acc_id, today_prefix)
        if daily_count >= DEFAULT_DAILY_POST_CAP:
            continue

        # Schedule for next slot
        next_slot = get_next_schedule_slot()
        slot_iso = next_slot.astimezone(timezone.utc).isoformat()

        post_id = create_post(
            clip_id=clip_id,
            account_id=acc_id,
            status="scheduled",
            scheduled_for=slot_iso,
            caption=clip.get("cand_caption") or clip.get("cand_title"),
            hashtags=clip.get("features"),
        )
        scheduled_post_ids.append(post_id)
        log_event("info", f"Auto-post scheduled clip #{clip_id} to {acc['platform']} for {slot_iso}")

    return scheduled_post_ids


# ── Scheduler Daemon Tick (§8.4) ──────────────────────────────────────────────

def run_posting_scheduler_cycle() -> int:
    """
    Check for due scheduled posts and dispatch them.
    Called once per minute by the background worker.
    """
    due_posts = get_due_posts()
    dispatched_count = 0
    for p in due_posts:
        post_id = p["id"]
        try:
            dispatch_post(post_id)
            dispatched_count += 1
        except Exception as e:
            logger.error(f"Failed to dispatch due post #{post_id}: {e}")

    return dispatched_count
