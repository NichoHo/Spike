"""
Stage 9: render (Phase 1 Baseline Cut)
Blueprint §13 Phase 1: Plain 16:9 cut with speech-snapped boundaries.
(Full vertical reframing, MediaPipe, and ASS karaoke captions are Phase 2).
Output: data/videos/<id>/clips/<cand_id>.mp4
"""

import os
import subprocess
from pathlib import Path
from typing import Dict, Any, List


def run_stage9_render(
    video_dir: Path,
    candidates: List[Dict[str, Any]]
) -> List[Path]:
    """Run Stage 9: produce plain 16:9 cut clips from sections. Resumes existing clips."""
    clips_dir = video_dir / "clips"
    clips_dir.mkdir(exist_ok=True)

    rendered_clips = []

    for idx, cand in enumerate(candidates, 1):
        cand_id = cand.get("id") or idx
        out_clip = clips_dir / f"clip_{cand_id}.mp4"

        if out_clip.exists() and out_clip.stat().st_size > 1000:
            print(f"  [stage 9] Resuming: found clip_{cand_id}.mp4")
            rendered_clips.append(out_clip)
            cand["clip_file"] = str(out_clip)
            continue

        sec_file = cand.get("section_file")
        if not sec_file or not os.path.exists(sec_file):
            print(f"  [stage 9] Error: missing section file for candidate {cand_id}")
            continue

        # The section has 5s padding on the left (pad_st = cand['start_s'] - 5.0)
        # So in the section file, the actual clip starts at t=5.0s, duration = end_s - start_s
        duration = cand["end_s"] - cand["start_s"]
        clip_offset_in_section = 5.0 if cand["start_s"] >= 5.0 else cand["start_s"]

        print(f"  [stage 9] Cutting final clip {cand_id} ({duration:.1f}s, '{cand.get('title')}')...")

        cmd = [
            "ffmpeg", "-y", "-v", "error",
            "-ss", str(clip_offset_in_section),
            "-i", str(sec_file),
            "-t", str(duration),
            "-c:v", "libx264", "-preset", "veryfast", "-crf", "20",
            "-c:a", "aac", "-b:a", "128k",
            str(out_clip)
        ]
        subprocess.run(cmd, check=True)

        rendered_clips.append(out_clip)
        cand["clip_file"] = str(out_clip)

    print(f"  [stage 9] Rendered {len(rendered_clips)} baseline clips.")
    return rendered_clips
