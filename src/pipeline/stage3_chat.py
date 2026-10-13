"""
Stage 3: fetch_chat
Blueprint §5:
Twitch: download chat replay JSON using TwitchDownloaderCLI.
YouTube: download the live chat replay of a finished stream via yt-dlp, converted to the Twitch shape.
Skipped for other sources, and for YouTube uploads with no live chat.
Output: data/videos/<id>/chat.json
"""

import json
import os
import re
import subprocess
from pathlib import Path
from typing import Dict, Any, Optional, Iterable, List

import yt_dlp

from src.config import TWITCH_DOWNLOADER_PATH


TWITCH_VOD_RE = re.compile(r'(?:twitch\.tv/videos/|/v/)(\d+)')
YOUTUBE_RE = re.compile(r'(?:youtube\.com|youtu\.be)/')


def convert_youtube_live_chat(lines: Iterable[str]) -> List[Dict[str, Any]]:
    """Convert yt-dlp .live_chat.json lines into the TwitchDownloaderCLI comment shape stage 6/7 read."""
    comments = []
    for line in lines:
        if not line.strip():
            continue
        replay = json.loads(line).get("replayChatItemAction", {})
        offset_ms = replay.get("videoOffsetTimeMsec")
        if offset_ms is None:
            continue
        for action in replay.get("actions", []):
            msg = action.get("addChatItemAction", {}).get("item", {}).get("liveChatTextMessageRenderer")
            if not msg:
                continue
            parts = []
            for run in msg.get("message", {}).get("runs", []):
                if "text" in run:
                    parts.append(run["text"])
                elif "emoji" in run:
                    emoji = run["emoji"]
                    # Standard emoji ids are the character itself, so "😂" matches the token lists.
                    token = (emoji.get("shortcuts") or [""])[0] if emoji.get("isCustomEmoji") else emoji.get("emojiId", "")
                    parts.append(f" {token} ")
            body = " ".join("".join(parts).split())
            if not body:
                continue
            comments.append({
                "content_offset_seconds": int(offset_ms) / 1000.0,
                "commenter": {"display_name": msg.get("authorName", {}).get("simpleText", "")},
                "message": {"body": body},
            })
    return comments


def fetch_youtube_live_chat(video_dir: Path, url: str, chat_path: Path) -> Optional[Dict[str, Any]]:
    """Download a finished stream's chat replay. None for uploads, chat-disabled streams, or errors."""
    print("  [stage 3] Checking for YouTube live chat replay via yt-dlp...")
    ydl_opts = {
        "skip_download": True,
        "writesubtitles": True,
        "subtitleslangs": ["live_chat"],
        "outtmpl": str(video_dir / "yt_chat.%(ext)s"),
        "quiet": True,
        "no_warnings": True,
        "noprogress": True,
    }
    raw_path = video_dir / "yt_chat.live_chat.json"
    try:
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            info = ydl.extract_info(url, download=True) or {}
        if not raw_path.exists():
            why = ("was a live stream, so the creator likely disabled the chat replay"
                   if info.get("was_live") else "is a regular upload with no live chat")
            print(f"  [stage 3] No live chat replay offered by YouTube (video {why}; "
                  f"subtitle tracks: {sorted((info.get('subtitles') or {}).keys())}); skipping chat.")
            return None
        with open(raw_path, "r", encoding="utf-8") as f:
            comments = convert_youtube_live_chat(f)
    except Exception as e:
        print(f"  [stage 3] Warning: YouTube live chat fetch failed ({type(e).__name__}): {e}")
        return None
    finally:
        # The raw replay is ~35 MB per busy hour; chat.json keeps only what later stages read.
        raw_path.unlink(missing_ok=True)

    if not comments:
        print("  [stage 3] Live chat replay file had no text messages after conversion; skipping chat.")
        return None
    data = {"comments": comments}
    with open(chat_path, "w", encoding="utf-8") as f:
        json.dump(data, f)
    print(f"  [stage 3] Downloaded {len(comments):,} YouTube chat messages.")
    return data


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
        if YOUTUBE_RE.search(webpage_url) and not meta.get("is_local"):
            return fetch_youtube_live_chat(video_dir, webpage_url, chat_path)
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
