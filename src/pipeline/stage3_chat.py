"""
Stage 3: fetch_chat
Blueprint §5:
Twitch only. Download chat replay JSON using TwitchDownloaderCLI.
Skipped for other sources.
Output: data/videos/<id>/chat.json
"""

import json
import os
import re
import subprocess
from pathlib import Path
from typing import Dict, Any, Optional

from src.config import TWITCH_DOWNLOADER_PATH


TWITCH_VOD_RE = re.compile(r'(?:twitch\.tv/videos/|/v/)(\d+)')


def extract_twitch_vod_id(source_str: str) -> Optional[str]:
    """Extract numeric Twitch VOD ID from URL or return if already numeric."""
    source_str = source_str.strip()
    if source_str.isdigit():
        return source_str
    m = TWITCH_VOD_RE.search(source_str)
    if m:
        return m.group(1)
    return None


def run_stage3_chat(
    video_dir: Path,
    meta: Dict[str, Any],
    source_input: str,
    chat_file_override: Optional[Path] = None,
) -> Optional[Dict[str, Any]]:
    """
    Run Stage 3: fetch_chat.
    Returns chat replay dict with 'comments' list, or None if skipped/unavailable.
    Resumes if chat.json already exists.
    """
    chat_path = video_dir / "chat.json"

    # 1. Resume check
    if chat_path.exists() and chat_path.stat().st_size > 100:
        print(f"  [stage 3] Resuming: found {chat_path.name} ({chat_path.stat().st_size:,} bytes)")
        try:
            with open(chat_path, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception as e:
            print(f"  [stage 3] Warning: corrupt chat.json ({e}), re-fetching...")

    # 2. Check if chat override provided (e.g. for testing / evaluation)
    if chat_file_override and chat_file_override.exists():
        print(f"  [stage 3] Using provided chat file: {chat_file_override}")
        with open(chat_file_override, "r", encoding="utf-8") as f:
            data = json.load(f)
        with open(chat_path, "w", encoding="utf-8") as f:
            json.dump(data, f)
        return data

    # 3. Check if source is Twitch
    webpage_url = meta.get("webpage_url", source_input)
    vod_id = extract_twitch_vod_id(webpage_url) or extract_twitch_vod_id(source_input)

    if not vod_id:
        print("  [stage 3] Non-Twitch source; skipping chat fetch.")
        return None

    # 4. Check TwitchDownloaderCLI availability
    if not TWITCH_DOWNLOADER_PATH.exists():
        print(f"  [stage 3] Warning: TwitchDownloaderCLI not found at {TWITCH_DOWNLOADER_PATH}; skipping chat.")
        return None

    print(f"  [stage 3] Downloading chat replay for Twitch VOD {vod_id} via TwitchDownloaderCLI...")
    cmd = [
        str(TWITCH_DOWNLOADER_PATH),
        "chatdownload",
        "-u", vod_id,
        "-o", str(chat_path),
        "--collision", "Overwrite"
    ]

    try:
        res = subprocess.run(cmd, capture_output=True, text=True, timeout=600)
        if res.returncode != 0:
            print(f"  [stage 3] Note: TwitchDownloaderCLI returned {res.returncode}: {res.stderr.strip()[:200]}")
            # If download fails, don't crash pipeline - record gap and continue
            return None
    except subprocess.TimeoutExpired:
        print("  [stage 3] Warning: Twitch chat download timed out after 10m.")
        return None
    except Exception as e:
        print(f"  [stage 3] Warning: Failed to run TwitchDownloaderCLI: {e}")
        return None

    if chat_path.exists() and chat_path.stat().st_size > 100:
        try:
            with open(chat_path, "r", encoding="utf-8") as f:
                data = json.load(f)
            n_comments = len(data.get("comments", []))
            print(f"  [stage 3] Downloaded {n_comments:,} chat messages ({chat_path.stat().st_size / 1_000_000:.1f} MB).")
            return data
        except Exception as e:
            print(f"  [stage 3] Warning: could not parse downloaded chat: {e}")
            return None

    return None
