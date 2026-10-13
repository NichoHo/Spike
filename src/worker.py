"""
Spike: Background Worker Daemon.
Blueprint §3, §5 (Worker loop), §13 (Phase 4).
Runs jobs sequentially from the videos queue.
"""

import json
import os
import sys
import time
import signal
import socket
import traceback
from typing import Optional, Dict, Any

from src.db import (
    init_db,
    get_connection,
    now_utc_iso,
    get_source,
    log_event,
    update_video_stage,
)
from src.cleanup import sweep_old_sections
from src.pipeline.runner import run_pipeline

# ponytail: One worker, one job at a time. A second worker needs a row-level
# claim check and more RAM than a small PC has (Whisper + ffmpeg + YAMNet).

_RUNNING = True
WORKER_LOCK_PORT = 47811


def _handle_signal(signum, frame):
    global _RUNNING
    print(f"\n[worker] Received signal {signum}, stopping gracefully...")
    _RUNNING = False


def claim_next_job() -> Optional[Dict[str, Any]]:
    """Atomically claim the highest-priority queued video."""
    now = now_utc_iso()
    with get_connection() as conn:
        cur = conn.cursor()
        cur.execute(
            """
            UPDATE videos
            SET status = 'running', claimed_at = ?
            WHERE id = (
                SELECT id FROM videos
                WHERE status = 'queued'
                ORDER BY priority DESC, created_at ASC
                LIMIT 1
            )
            RETURNING id, origin, url, title, source_id, settings
            """,
            (now,)
        )
        row = cur.fetchone()
        if row:
            return dict(row)
        return None


def run_worker_cycle() -> bool:
    """Check for and run a single job. Returns True if a job was processed."""
    job = claim_next_job()
    if not job:
        return False

    video_id = job["id"]
    source_input = job["url"]
    source_id = job["source_id"]
    title = job.get("title") or source_input

    print(f"\n[worker] Claimed job #{video_id}: '{title}' (origin: {job['origin']})")
    log_event("info", f"Worker started processing job #{video_id} ('{title}')", video_id=video_id)

    # Load source-specific settings if available
    source_settings = {}
    if source_id:
        src_row = get_source(source_id)
        if src_row:
            src_dict = dict(src_row)
            source_settings = {
                "layout": src_dict.get("layout", "split"),
                "caption_style": src_dict.get("caption_style", "bold_pop"),
                "caption_y": src_dict.get("caption_y", 0.85),
                "music": bool(src_dict.get("music", False)),
                "default_music_mood": src_dict.get("default_music_mood", "chill"),
                "silence_trim": bool(src_dict.get("silence_trim", False)),
                "punch_in_zoom": bool(src_dict.get("punch_in_zoom", True)),
                "letterbox_style": src_dict.get("letterbox_style") or "title",
                "style_notes": src_dict.get("style_notes"),
                "language": src_dict.get("language"),
                "chat_offset_s": src_dict.get("chat_offset_s", 12.0),
                "facecam_box": src_dict.get("facecam_box"),
            }

    # Options picked on the New job form override the source's defaults
    if job.get("settings"):
        source_settings.update(json.loads(job["settings"]))

    try:
        run_pipeline(source_input=source_input, source_settings=source_settings, video_id=video_id)
        print(f"[worker] Job #{video_id} completed successfully.")
        log_event("info", f"Worker completed job #{video_id}", video_id=video_id)
        return True
    except Exception as e:
        err_msg = str(e)
        print(f"[worker] Job #{video_id} failed: {err_msg}")
        log_event("error", f"Job #{video_id} failed: {err_msg}", video_id=video_id)
        update_video_stage(video_id, "failed", status="failed", error=err_msg)
        return False


def start_worker(poll_interval_s: float = 5.0):
    """Main worker loop."""
    global _RUNNING
    signal.signal(signal.SIGINT, _handle_signal)
    signal.signal(signal.SIGTERM, _handle_signal)

    from src.music import validate_music_library

    # Single-instance lock: the OS frees the port when this process dies, even on a hard kill.
    lock = socket.socket()
    try:
        lock.bind(("127.0.0.1", WORKER_LOCK_PORT))
    except OSError:
        print(f"[worker] Another worker is already running (port {WORKER_LOCK_PORT} taken). Exiting.")
        sys.exit(1)

    init_db()
    validate_music_library(enforce=True)
    # Safe only because of the lock above: a job left 'running' means the last worker died mid-job.
    # Requeue it; stages with output are skipped.
    with get_connection() as conn:
        conn.execute("UPDATE videos SET status = 'queued' WHERE status = 'running'")
    print(f"[worker] Spike background worker running (PID {os.getpid()}). Press Ctrl+C to stop.")

    last_scheduler_check = 0.0
    last_sweep = 0.0
    while _RUNNING:
        try:
            now_ts = time.time()
            if now_ts - last_scheduler_check >= 30.0:
                try:
                    from src.posting import run_posting_scheduler_cycle
                    dispatched = run_posting_scheduler_cycle()
                    if dispatched > 0:
                        print(f"[worker] Scheduler cycle dispatched {dispatched} due post(s).")
                except Exception as sc_err:
                    print(f"[worker] Scheduler cycle error: {sc_err}")
                last_scheduler_check = now_ts

            if now_ts - last_sweep >= 3600.0:
                sweep_old_sections()
                last_sweep = now_ts

            processed = run_worker_cycle()
            if not processed:
                time.sleep(poll_interval_s)
        except Exception as e:
            print(f"[worker] Unexpected error in worker loop: {e}")
            traceback.print_exc()
            time.sleep(poll_interval_s)

    print("[worker] Worker stopped.")


if __name__ == "__main__":
    start_worker()
