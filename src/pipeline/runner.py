"""
Spike: Master Pipeline Runner
Orchestrates Stages 1, 2, 4, 5, 6, 7, 8, 9, 9c with resume checkpoints.
Blueprint §5 & §13 Phase 1 and Phase 2.
"""

import os
import sys
import traceback
from pathlib import Path
from typing import Dict, Any, Optional

from src.cleanup import cleanup_after_pipeline
from src.config import VIDEOS_DIR, PUBLIC_URL
from src.db import (
    init_db,
    register_video,
    enter_stage,
    JobInterrupted,
    update_video_stage,
    set_video_duration,
    set_stage_progress,
    get_connection,
    get_job,
    finish_video,
)
from src import oversize_gate
from src.notify import send_job_ready_notification, send_job_failed_notification
from src.pipeline.stage1_meta import run_stage1_meta
from src.profile import ensure_profiles
from src.pipeline.stage2_audio import run_stage2_audio
from src.pipeline.stage3_chat import run_stage3_chat
from src.pipeline.stage4_crowd import run_stage4_crowd
from src.pipeline.stage5_transcribe import run_stage5_transcribe
from src.pipeline.stage6_signals import run_stage6_signals
from src.pipeline.stage7_moments import run_stage7_moments
from src.pipeline.stage8_sections import run_stage8_sections
from src.pipeline.stage9_render import run_stage9_render
from src.pipeline.stage9c_render import run_stage9c_render


def _park_job(video_id: int) -> None:
    """Set a running job back to 'queued', like a queue-reorder pause, so the worker picks the next one."""
    with get_connection() as conn:
        conn.execute("UPDATE videos SET status = 'queued' WHERE id = ? AND status = 'running'", (video_id,))


def _oversize_gate(video_id: int, meta: Dict[str, Any]) -> None:
    """Pause before the expensive 'moments' stage when the VOD is too long, and ask the user.

    Levels: 4 h threshold -> ask once; 6 h soft ceiling -> ask a second, escalated time; a Continue there
    processes the WHOLE video (no truncation). Stop cancels the job; no answer within the timeout parks it
    (back to 'queued') and raises JobInterrupted so the worker moves to the next queued job and resumes this
    one later from the same stage.
    """
    duration_s = float(meta.get("duration") or 0.0)
    if duration_s <= oversize_gate.THRESHOLD_S:
        return
    job = get_job(video_id)
    title = (job["title"] if job and job["title"] else None) or meta.get("title") or f"Video #{video_id}"

    # Level 1 at the 4 h threshold, then level 2 if the user continues past the 6 h ceiling.
    levels = [1] + ([2] if duration_s > oversize_gate.CEILING_S else [])
    for level in levels:
        decision = oversize_gate.ask(video_id, title, duration_s, level, PUBLIC_URL)
        if decision == "stop":
            with get_connection() as conn:
                conn.execute("UPDATE videos SET status = 'done', error = 'Stopped: video too long' "
                             "WHERE id = ? AND status = 'running'", (video_id,))
            oversize_gate.clear(video_id)
            raise JobInterrupted(video_id, "cancelled")
        if decision == "timeout":
            _park_job(video_id)
            raise JobInterrupted(video_id, "queued")
        # decision == "continue": fall through to the next level (if any), else proceed into stage 7.
    oversize_gate.clear(video_id)


def run_pipeline(
    source_input: str,
    source_settings: Optional[Dict[str, Any]] = None,
    video_id: Optional[int] = None,
) -> Dict[str, Any]:
    """Execute the full Spike pipeline (Phase 1, 2, 3) for a video file or URL."""
    init_db()

    print(f"\n==========================================")
    print(f"  Spike Pipeline: {source_input}")
    print(f"==========================================")

    # Determine origin
    is_local = os.path.exists(source_input)
    origin = "upload" if is_local else "url"

    # Register in DB, unless the worker already claimed a queued row for this job
    claimed = video_id is not None
    video_id = video_id or register_video(origin, source_input)
    video_dir = VIDEOS_DIR / str(video_id)
    video_dir.mkdir(parents=True, exist_ok=True)

    try:
        # Stage 1: fetch_meta. A CLI run has no worker claim, so it marks its own row running.
        # Every enter_stage raises JobInterrupted if the job was paused (queue reorder) or cancelled.
        if claimed:
            enter_stage(video_id, "fetch_meta")
        else:
            update_video_stage(video_id, "fetch_meta", status="running")
        meta = run_stage1_meta(video_dir, source_input, (source_settings or {}).get("max_process_s"))
        if meta.get("duration"):
            set_video_duration(video_id, meta["duration"])

        # Stage 2: fetch_audio
        enter_stage(video_id, "fetch_audio")
        audio_path = run_stage2_audio(video_dir, meta)

        # Stage 3: fetch_chat (Twitch VODs and finished YouTube streams; skipped for uploads)
        enter_stage(video_id, "fetch_chat")
        chat_override = Path(source_settings["chat_file"]) if source_settings and source_settings.get("chat_file") else None
        chat_data = run_stage3_chat(video_dir, meta, source_input, chat_file_override=chat_override)

        # Stage 4: fetch_crowd (YouTube comments or Twitch emotes/clips)
        enter_stage(video_id, "fetch_crowd")
        crowd_data = run_stage4_crowd(video_dir, meta)
        if source_settings and source_settings.get("holdout_clips") and isinstance(crowd_data, dict):
            crowd_data["clips"] = []  # eval runs: community clips are the answer key, so Spike must not see them

        # Stage 5: transcribe
        enter_stage(video_id, "transcribe")
        transcript = run_stage5_transcribe(
            video_dir, audio_path, on_progress=lambda f: set_stage_progress(video_id, f)
        )

        # Creator + session profile (needs the transcript; cached per source, so usually free)
        try:
            profile_ctx = ensure_profiles(
                video_id, video_dir, meta, transcript,
                refresh=bool(source_settings and source_settings.get("refresh_profile")),
            )
        except Exception as profile_err:
            print(f"  [profile] Skipped: {profile_err}")
            profile_ctx = None

        # Stage 6: signals (fused audio + crowd + chat)
        enter_stage(video_id, "signals")
        signals_data = run_stage6_signals(
            video_dir, meta, audio_path, transcript, crowd_data, chat_data=chat_data,
            weight_mult=(profile_ctx or {}).get("preset", {}).get("weight_mult"),
        )
        if source_settings and source_settings.get("target_clips"):
            signals_data["target_clip_count"] = int(source_settings["target_clips"])
            signals_data["explicit_target"] = True

        # Oversized-input gate (replaces the old hard VOD chop): before the expensive 'moments' stage, a VOD
        # longer than the 4 h threshold needs a Continue/Stop answer; past the 6 h soft ceiling it needs a
        # second, escalated one. No answer within the timeout parks the job for the next queued one.
        _oversize_gate(video_id, meta)

        # Stage 7: moments (LLM judge + snapping + pairwise rerank)
        enter_stage(video_id, "moments")
        candidates = run_stage7_moments(
            video_id, video_dir, meta, transcript, signals_data, crowd_data, chat_data=chat_data, profile_ctx=profile_ctx
        )

        if not candidates:
            print("  [pipeline] No candidate moments met selection criteria.")
            finish_video(video_id, status="ready")
            cleanup_after_pipeline(video_dir, meta, [])
            return {"video_id": video_id, "candidates": []}

        # Stage 8: fetch_sections
        enter_stage(video_id, "fetch_sections")
        run_stage8_sections(video_dir, meta, candidates)

        # Stage 9: plain 16:9 baseline cut (Phase 1 output, always produced)
        enter_stage(video_id, "render")
        rendered_clips = run_stage9_render(video_dir, candidates)

        # Stage 9c: Phase 2 vertical 9:16 render with face tracking, captions & effects
        enter_stage(video_id, "render_vertical")
        vertical_clips = run_stage9c_render(video_dir, candidates, transcript, source_settings)

        # Stage 9c registered each clip with its full render settings. Registering again here wrote defaults
        # over them (pause trimming off, no music, blur letterbox), so later re-renders lost the pause cuts.
        for c in candidates:
            clip_id = c.get("clip_id")
            if clip_id:
                try:
                    from src.posting import evaluate_clip_autopost
                    evaluate_clip_autopost(clip_id, source_settings=source_settings)
                except Exception as auto_err:
                    print(f"  [autopost] Auto-post evaluation for clip #{clip_id}: {auto_err}")

        # Finished!
        finish_video(video_id, status="ready")
        cleanup_after_pipeline(video_dir, meta, candidates)

        # Stage 10: notify via Discord webhook
        send_job_ready_notification(video_id)

        print(f"\n==========================================")
        print(f"  Pipeline Complete! {len(vertical_clips)} vertical clips ready in:")
        print(f"  {video_dir / 'renders'}")
        print(f"==========================================")

        for c in candidates:
            render_path = c.get("render_file", c.get("clip_file", "N/A"))
            print(f"  * [{c.get('llm_score')}/100] {c.get('title')}")
            print(f"    Punchline: \"{c.get('punchline')}\"")
            print(f"    Vertical: {render_path}")

        return {
            "video_id": video_id,
            "meta": meta,
            "candidates": candidates,
            "clips": [str(p) for p in rendered_clips],
            "vertical_clips": [str(p) for p in vertical_clips],
        }

    except JobInterrupted:
        raise  # paused or cancelled, not failed: keep its files so it resumes from this stage
    except Exception as e:
        err_msg = str(e)
        traceback.print_exc()
        update_video_stage(video_id, "failed", status="failed", error=err_msg)
        send_job_failed_notification(video_id, err_msg)
        raise
