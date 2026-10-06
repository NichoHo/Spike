"""
Spike: Discord webhook notification service.
Blueprint §3, §5 (Stage 10 notify), §13 (Phase 4).
"""

import json
import urllib.request
import urllib.error
from typing import Optional, Tuple
from src.config import DISCORD_WEBHOOK_URL, PUBLIC_URL
from src.db import get_job, get_candidates, get_setting, log_event


def get_active_webhook_url() -> Optional[str]:
    """Retrieve active Discord webhook URL from DB settings or environment."""
    db_val = get_setting("discord_webhook_url")
    if db_val and db_val.strip():
        return db_val.strip()
    if DISCORD_WEBHOOK_URL and DISCORD_WEBHOOK_URL.strip():
        return DISCORD_WEBHOOK_URL.strip()
    return None


def _post_webhook(webhook_url: str, content: str) -> int:
    """POST a plain-text message to a Discord webhook. Returns the HTTP status; raises on network errors.
    Plain `content`, not embeds: embeds render blank when a viewer has link previews turned off."""
    payload = {
        "content": content[:2000],  # Discord's message length limit
        "allowed_mentions": {"parse": []},  # stream titles are untrusted; never ping @everyone
    }
    req = urllib.request.Request(
        webhook_url,
        data=json.dumps(payload).encode("utf-8"),
        headers={"Content-Type": "application/json", "User-Agent": "Spike-Clip-Engine/1.0"},
        method="POST",
    )
    with urllib.request.urlopen(req, timeout=10) as resp:
        return resp.status


def send_job_failed_notification(video_id: int, error: str) -> bool:
    """Send a Discord message when a job fails, so a broken automated run is not silent."""
    webhook_url = get_active_webhook_url()
    job = get_job(video_id)
    if not webhook_url or not job:
        return False
    title = job["title"] or f"Video #{video_id}"
    content = (
        f"**Job failed:** {title[:150]}\n"
        f"```{error[:1500]}```\n"
        f"Retry it from the Jobs page: <{PUBLIC_URL}/jobs>"
    )
    try:
        return _post_webhook(webhook_url, content) in (200, 204)
    except Exception as e:
        log_event("error", f"Failed to send failure webhook for video #{video_id}: {e}", video_id=video_id)
        return False


def send_job_ready_notification(video_id: int) -> bool:
    """Send Discord webhook notification when a video job reaches 'ready' status."""
    webhook_url = get_active_webhook_url()
    job = get_job(video_id)
    if not job:
        return False

    candidates = get_candidates(video_id, status="selected")
    if not candidates:
        candidates = get_candidates(video_id)

    clip_count = len(candidates)
    top_score = max([c["final_score"] or 0 for c in candidates]) if candidates else 0
    title = job["title"] or f"Video #{video_id}"
    source_name = job["source_name"] or job["origin"]
    duration_s = job["duration_s"] or 0
    dur_min = int(duration_s // 60)
    dur_str = f"{dur_min} min" if dur_min > 0 else f"{int(duration_s)} s"

    if not webhook_url:
        log_event("info", f"Video #{video_id} ('{title}') ready with {clip_count} clips (top score: {top_score}). Webhook not configured.", video_id=video_id)
        return False

    review_url = f"{PUBLIC_URL}/" + (f"?source_id={job['source_id']}" if job["source_id"] else "")
    content = (
        f"**Clips ready:** {title[:150]}\n"
        f"{clip_count} clips, top score {top_score}/100. Source: {source_name}, {dur_str}.\n"
        f"Review: <{review_url}>"
    )

    try:
        status = _post_webhook(webhook_url, content)
        if status in (200, 204):
            log_event("info", f"Discord notification sent for video #{video_id}.", video_id=video_id)
            return True
        log_event("warning", f"Discord webhook returned HTTP {status} for video #{video_id}.", video_id=video_id)
        return False
    except Exception as e:
        log_event("error", f"Failed to send Discord webhook for video #{video_id}: {e}", video_id=video_id)
        return False


def verify_discord_webhook(webhook_url: str) -> Tuple[bool, str]:
    """Send a test ping message to verify webhook connectivity."""
    if not webhook_url or not webhook_url.strip():
        return False, "Webhook URL cannot be empty."

    try:
        status = _post_webhook(webhook_url.strip(), "**Spike webhook test:** Discord notifications work.")
        if status in (200, 204):
            return True, "Notification sent successfully."
        return False, f"Discord returned status {status}."
    except urllib.error.HTTPError as e:
        return False, f"HTTP Error {e.code}: {e.reason}"
    except Exception as e:
        return False, f"Network error: {str(e)}"
