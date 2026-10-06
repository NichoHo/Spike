"""
Stage 1: fetch_meta
Blueprint §5: Extract metadata, duration, title, channel, and yt-dlp heatmap.
Rejects if duration exceeds MAX_VIDEO_DURATION_S (12 hours).
Output: data/videos/<id>/meta.json
"""

import json
import os
import subprocess
from pathlib import Path
from typing import Dict, Any, Optional
import yt_dlp

from src.config import MAX_VIDEO_DURATION_S


def get_local_video_meta(file_path: str) -> Dict[str, Any]:
    """Extract metadata from local video file using ffprobe."""
    cmd = [
        "ffprobe", "-v", "error",
        "-show_entries", "format=duration,size,bit_rate:format_tags=title",
        "-show_entries", "stream=width,height,codec_name,codec_type",
        "-of", "json",
        file_path
    ]
    res = subprocess.run(cmd, capture_output=True, text=True, check=True)
    probe = json.loads(res.stdout)
    fmt = probe.get("format", {})
    streams = probe.get("streams", [])
    v_stream = next((s for s in streams if s.get("codec_type") == "video"), {})

    dur = float(fmt.get("duration", 0.0))
    title = Path(file_path).stem

    return {
        "id": Path(file_path).stem,
        "title": title,
        "duration": dur,
        "uploader": "local_upload",
        "webpage_url": os.path.abspath(file_path),
        "heatmap": None,
        "width": v_stream.get("width"),
        "height": v_stream.get("height"),
        "is_local": True,
        "local_path": os.path.abspath(file_path),
    }


def get_remote_video_meta(url: str) -> Dict[str, Any]:
    """Extract metadata and heatmap using yt-dlp without downloading."""
    ydl_opts = {
        "extract_flat": False,
        "quiet": True,
        "no_warnings": True,
    }
    with yt_dlp.YoutubeDL(ydl_opts) as ydl:
        info = ydl.extract_info(url, download=False)

    return {
        "id": info.get("id"),
        "title": info.get("title", ""),
        "duration": float(info.get("duration", 0.0) or 0.0),
        "uploader": info.get("uploader", "") or info.get("channel", ""),
        "webpage_url": info.get("webpage_url", url),
        "heatmap": info.get("heatmap"),  # list of 100 bins {start_time, end_time, value}
        "width": info.get("width"),
        "height": info.get("height"),
        "is_local": False,
        "local_path": None,
    }


def run_stage1_meta(video_dir: Path, source_input: str) -> Dict[str, Any]:
    """Run Stage 1: fetch_meta. Resumes if meta.json exists."""
    meta_path = video_dir / "meta.json"
    if meta_path.exists():
        print(f"  [stage 1] Resuming: found {meta_path.name}")
        with open(meta_path, "r", encoding="utf-8") as f:
            return json.load(f)

    print(f"  [stage 1] Fetching metadata for: {source_input}")
    if os.path.exists(source_input):
        meta = get_local_video_meta(source_input)
    else:
        meta = get_remote_video_meta(source_input)

    # Check duration guard
    duration = meta.get("duration", 0.0)
    if duration > MAX_VIDEO_DURATION_S:
        raise ValueError(
            f"Video duration ({duration / 3600:.1f}h) exceeds maximum allowed {MAX_VIDEO_DURATION_S / 3600:.0f}h"
        )

    with open(meta_path, "w", encoding="utf-8") as f:
        json.dump(meta, f, indent=2)

    print(f"  [stage 1] Done: '{meta.get('title')}' ({duration:.0f}s)")
    return meta
