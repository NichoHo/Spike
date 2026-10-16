"""
Spike: render one stored candidate on demand ("Other moments" Render button, Blueprint §6.7).
Runs in the worker, never in a web request: it fetches the section and then renders.
"""

import json
from typing import Any, Dict, Optional

from src.config import VIDEOS_DIR
from src.db import get_candidate, get_job
from src.pipeline.stage8_sections import run_stage8_sections
from src.pipeline.stage9c_render import run_stage9c_render


def source_settings_for(source_id: Optional[int], job_settings_json: Optional[str] = None) -> Dict[str, Any]:
    """Render settings from the source's defaults, overridden by the options picked when the job was submitted."""
    from src.db import get_source

    settings: Dict[str, Any] = {}
    row = get_source(source_id) if source_id else None
    if row:
        src = dict(row)
        settings = {
            "layout": src.get("layout", "split"),
            "caption_style": src.get("caption_style", "bold_pop"),
            "caption_y": src.get("caption_y", 0.85),
            "music": bool(src.get("music", False)),
            "default_music_mood": src.get("default_music_mood", "chill"),
            "silence_trim": bool(src.get("silence_trim", False)),
            "letterbox_style": src.get("letterbox_style") or "title",
            "style_notes": src.get("style_notes"),
            "language": src.get("language"),
            "chat_offset_s": src.get("chat_offset_s", 12.0),
            "facecam_box": src.get("facecam_box"),
        }
    if job_settings_json:
        settings.update(json.loads(job_settings_json))
    return settings


def render_candidate(candidate_id: int) -> None:
    """Fetch the section and render the vertical clip. Raises with a readable message on failure."""
    row = get_candidate(candidate_id)
    if not row:
        raise RuntimeError("candidate no longer exists")
    cand: Dict[str, Any] = dict(row)
    job = get_job(cand["video_id"])
    video_dir = VIDEOS_DIR / str(cand["video_id"])
    try:
        meta = json.loads((video_dir / "meta.json").read_text(encoding="utf-8"))
        transcript = json.loads((video_dir / "transcript.json").read_text(encoding="utf-8"))
    except OSError as e:
        raise RuntimeError(f"video files are gone ({e.filename})") from e

    cand["cuts"] = json.loads(cand.get("cuts") or "[]")
    cand["zooms"] = json.loads(cand["zooms"]) if cand.get("zooms") else None  # None: default zoom at the payoff
    cand["segments"] = json.loads(cand["segments"]) if cand.get("segments") else None
    if cand.get("concept_spec") and cand.get("concept", "single") != "single":
        spec = json.loads(cand["concept_spec"])  # a story, POV or countdown: render it by its segments
        cand.update(segs=spec["segments"], overlay=spec.get("overlay") or {}, theme=spec.get("theme", ""),
                    concept_source=spec.get("concept_source", "user"))
    settings = source_settings_for(job["source_id"] if job else None, job["settings"] if job else None)

    run_stage8_sections(video_dir, meta, [cand])
    # candidates.json lists the original picks only; a hand-rendered moment must not replace that file
    run_stage9c_render(video_dir, [cand], transcript, settings, update_candidates_json=False)
    if not cand.get("render_file"):
        raise RuntimeError("the render did not produce a clip (section download or ffmpeg failed)")
