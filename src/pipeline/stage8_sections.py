"""
Stage 8: fetch_sections
Blueprint §5: Download or slice candidate sections with 5 s padding on each side.
Output: data/videos/<id>/sections/<cand_id>.mp4
"""

import os
import subprocess
from pathlib import Path
from typing import Dict, Any, List
import yt_dlp


def run_stage8_sections(
    video_dir: Path,
    meta: Dict[str, Any],
    candidates: List[Dict[str, Any]]
) -> List[Path]:
    """Run Stage 8: download/slice sections with 5s padding. Resumes existing sections."""
    sections_dir = video_dir / "sections"
    sections_dir.mkdir(exist_ok=True)

    is_local = meta.get("is_local", False)
    local_path = meta.get("local_path")
    video_url = meta.get("webpage_url")

    section_files = []

    for idx, cand in enumerate(candidates, 1):
        cand_id = cand.get("id") or idx
        out_file = sections_dir / f"section_{cand_id}.mp4"

        if out_file.exists() and out_file.stat().st_size > 1000:
            print(f"  [stage 8] Resuming: found section_{cand_id}.mp4")
            section_files.append(out_file)
            cand["section_file"] = str(out_file)
            continue

        pad_st = max(0.0, cand["start_s"] - 5.0)
        pad_et = cand["end_s"] + 5.0

        print(f"  [stage 8] Slicing section {cand_id} ({pad_st:.1f}s to {pad_et:.1f}s)...")

        if is_local and local_path and os.path.exists(local_path):
            cmd = [
                "ffmpeg", "-y", "-v", "error",
                "-ss", str(pad_st),
                "-to", str(pad_et),
                "-i", local_path,
                "-c:v", "libx264", "-preset", "veryfast", "-crf", "22",
                "-c:a", "aac", "-b:a", "128k",
                str(out_file)
            ]
            subprocess.run(cmd, check=True)
        else:
            # Remote URL section download via yt-dlp
            out_tmpl = str(sections_dir / f"section_{cand_id}.%(ext)s")
            section_range = f"*{int(pad_st)}-{int(pad_et)}"
            ydl_opts = {
                "format": "bestvideo[ext=mp4]+bestaudio[ext=m4a]/best[ext=mp4]/best",
                "merge_output_format": "mp4",
                "outtmpl": out_tmpl,
                "download_ranges": yt_dlp.utils.download_range_func(None, [(pad_st, pad_et)]),
                "force_keyframes_at_cuts": True,
                "quiet": True,
                "no_warnings": True,
            }
            try:
                with yt_dlp.YoutubeDL(ydl_opts) as ydl:
                    ydl.download([video_url])
            except Exception as e:
                print(f"  [stage 8] Warning: yt-dlp range download failed, falling back to full section seek: {e}")
                # Fallback: stream URL through ffmpeg
                cmd = [
                    "ffmpeg", "-y", "-v", "error",
                    "-ss", str(pad_st),
                    "-to", str(pad_et),
                    "-i", video_url,
                    "-c:v", "libx264", "-preset", "veryfast", "-crf", "22",
                    "-c:a", "aac",
                    str(out_file)
                ]
                subprocess.run(cmd, check=True)

        # Check output
        if not out_file.exists():
            matches = list(sections_dir.glob(f"section_{cand_id}.*"))
            if matches:
                out_file = matches[0]

        section_files.append(out_file)
        cand["section_file"] = str(out_file)

    print(f"  [stage 8] Completed {len(section_files)} sections.")
    return section_files
