"""
Stage 2: fetch_audio
Blueprint §5: Download or extract audio stream as audio.m4a.
Output: data/videos/<id>/audio.m4a
"""

import os
import subprocess
from pathlib import Path
from typing import Dict, Any
import yt_dlp


def run_stage2_audio(video_dir: Path, meta: Dict[str, Any]) -> Path:
    """Run Stage 2: fetch_audio. Resumes if audio.m4a exists."""
    audio_path = video_dir / "audio.m4a"
    if audio_path.exists() and audio_path.stat().st_size > 1000:
        print(f"  [stage 2] Resuming: found {audio_path.name} ({audio_path.stat().st_size / (1024*1024):.1f} MB)")
        return audio_path

    is_local = meta.get("is_local", False)
    local_path = meta.get("local_path")
    url = meta.get("webpage_url")
    limit_s = meta.get("process_limit_s")  # set by stage 1 when only the start of the video is processed

    print(f"  [stage 2] Extracting/Downloading audio to {audio_path.name}...")

    if is_local and local_path and os.path.exists(local_path):
        # Extract audio using ffmpeg from local file
        cmd = [
            "ffmpeg", "-y", "-v", "error",
            "-i", local_path,
            *(["-t", str(limit_s)] if limit_s else []),
            "-vn",
            "-c:a", "aac",
            "-b:a", "128k",
            str(audio_path)
        ]
        subprocess.run(cmd, check=True)
    else:
        # Download audio-only using yt-dlp
        out_tmpl = str(video_dir / "audio.%(ext)s")
        ydl_opts = {
            "format": "bestaudio/best",
            "outtmpl": out_tmpl,
            "postprocessors": [{
                "key": "FFmpegExtractAudio",
                "preferredcodec": "m4a",
                "preferredquality": "128",
            }],
            "quiet": True,
            "no_warnings": True,
        }
        if limit_s:
            ydl_opts["download_ranges"] = yt_dlp.utils.download_range_func(None, [(0, limit_s)])
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            ydl.download([url])

    if not audio_path.exists():
        # In case yt-dlp named it slightly differently, search for audio.*
        found = list(video_dir.glob("audio.*"))
        if found:
            audio_path = found[0]

    for leftover in video_dir.glob("audio.*"):  # e.g. audio.webm left by yt-dlp
        if leftover != audio_path:
            leftover.unlink(missing_ok=True)

    print(f"  [stage 2] Audio ready: {audio_path.name} ({audio_path.stat().st_size / (1024*1024):.1f} MB)")
    return audio_path
