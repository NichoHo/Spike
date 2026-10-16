"""
Spike: Master Pipeline Runner
Orchestrates Stages 1, 2, 4, 5, 6, 7, 8, 9, 9c with resume checkpoints.
Blueprint §5 & §13 Phase 1 and Phase 2.
"""

import json
import os
import sys
import traceback
from pathlib import Path
from typing import Dict, Any, Optional

from src.cleanup import cleanup_after_pipeline
from src.config import VIDEOS_DIR
from src.db import (
    init_db,
    register_video,
    update_video_stage,
    finish_video,
    create_or_update_clip,
)
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
    video_id = video_id or register_video(origin, source_input)
    video_dir = VIDEOS_DIR / str(video_id)
    video_dir.mkdir(parents=True, exist_ok=True)

    try:
        # Stage 1: fetch_meta
        update_video_stage(video_id, "fetch_meta", status="running")
        meta = run_stage1_meta(video_dir, source_input, (source_settings or {}).get("max_process_s"))

        # Stage 2: fetch_audio
        update_video_stage(video_id, "fetch_audio", status="running")
        audio_path = run_stage2_audio(video_dir, meta)

        # Stage 3: fetch_chat (Twitch VODs and finished YouTube streams; skipped for uploads)
        update_video_stage(video_id, "fetch_chat", status="running")
        chat_override = Path(source_settings["chat_file"]) if source_settings and source_settings.get("chat_file") else None
        chat_data = run_stage3_chat(video_dir, meta, source_input, chat_file_override=chat_override)

        # Stage 4: fetch_crowd (YouTube comments or Twitch emotes/clips)
        update_video_stage(video_id, "fetch_crowd", status="running")
        crowd_data = run_stage4_crowd(video_dir, meta)

        # Stage 5: transcribe
        update_video_stage(video_id, "transcribe", status="running")
        transcript = run_stage5_transcribe(video_dir, audio_path)

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
        update_video_stage(video_id, "signals", status="running")
        signals_data = run_stage6_signals(
            video_dir, meta, audio_path, transcript, crowd_data, chat_data=chat_data,
            weight_mult=(profile_ctx or {}).get("preset", {}).get("weight_mult"),
        )
        if source_settings and source_settings.get("target_clips"):
            signals_data["target_clip_count"] = int(source_settings["target_clips"])
            signals_data["explicit_target"] = True

        # Stage 7: moments (LLM judge + snapping + pairwise rerank)
        update_video_stage(video_id, "moments", status="running")
        candidates = run_stage7_moments(
            video_id, video_dir, meta, transcript, signals_data, crowd_data, chat_data=chat_data, profile_ctx=profile_ctx
        )

        if not candidates:
            print("  [pipeline] No candidate moments met selection criteria.")
            finish_video(video_id, status="ready")
            cleanup_after_pipeline(video_dir, meta, [])
            return {"video_id": video_id, "candidates": []}

        # Stage 8: fetch_sections
        update_video_stage(video_id, "fetch_sections", status="running")
        run_stage8_sections(video_dir, meta, candidates)

        # Stage 9: plain 16:9 baseline cut (Phase 1 output, always produced)
        update_video_stage(video_id, "render", status="running")
        rendered_clips = run_stage9_render(video_dir, candidates)

        # Stage 9c: Phase 2 vertical 9:16 render with face tracking, captions & effects
        update_video_stage(video_id, "render_vertical", status="running")
        vertical_clips = run_stage9c_render(video_dir, candidates, transcript, source_settings)

        # Register clips into clips table for UI
        for c in candidates:
            render_path = c.get("render_file")
            thumb_path = c.get("thumbnail_file")
            if render_path and os.path.exists(render_path):
                clip_id = create_or_update_clip(
                    candidate_id=c["id"],
                    file_path=str(render_path),
                    thumb_path=str(thumb_path) if thumb_path else "",
                    layout=c.get("layout", source_settings.get("layout", "split") if source_settings else "split"),
                    caption_style=c.get("caption_style", source_settings.get("caption_style", "bold_pop") if source_settings else "bold_pop"),
                    trim_start_s=c.get("trim_start_s", c.get("start_s")),
                    trim_end_s=c.get("trim_end_s", c.get("end_s")),
                    status="ready",
                    cuts=json.dumps(c.get("cuts") or []),
                    zooms=json.dumps(c.get("zooms") or []),
                )
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

    except Exception as e:
        err_msg = str(e)
        traceback.print_exc()
        update_video_stage(video_id, "failed", status="failed", error=err_msg)
        send_job_failed_notification(video_id, err_msg)
        raise
