"""
Stage 4: fetch_crowd
Blueprint §5 & §6.1:
- YouTube: fetch top comment threads via commentThreads.list, parse timestamps and laugh tokens.
  Output: data/videos/<id>/comments.json
- Twitch:
  - 3rd-party emote set (7TV, BTTV, FFZ): public APIs. Output: data/videos/<id>/emotes.json
  - Community clips (Helix Get Clips with vod_offset, creator_id, view_count, is_featured). Output: data/videos/<id>/clips.json
  Skipped for uploads.
"""

import json
import os
import re
import urllib.request
import urllib.parse
from pathlib import Path
from typing import Dict, Any, List, Optional, Set

from src.config import youtube_keys, TWITCH_CLIENT_ID, TWITCH_CLIENT_SECRET


TIMESTAMP_RE = re.compile(r'\b(?:(\d{1,2}):)?([0-5]?\d):([0-5]\d)\b')
LAUGH_TERMS = {"lol", "lmao", "lmfao", "dead", "💀", "😂", "haha", "funny", "kekw", "lul", "crying"}


def parse_timestamp_seconds(match: re.Match) -> float:
    """Convert regex match to seconds."""
    hours, mins, secs = match.groups()
    total = int(mins) * 60 + int(secs)
    if hours:
        total += int(hours) * 3600
    return float(total)


def fetch_youtube_comments(video_id: str, max_pages: int = 10) -> List[Dict[str, Any]]:
    """Fetch top comment threads from YouTube Data API v3."""
    if not youtube_keys():
        print("  [stage 4] No YOUTUBE_API_KEY configured; skipping comments.")
        return []

    comments = []
    page_token = None

    for page in range(max_pages):
        params = {
            "part": "snippet",
            "videoId": video_id,
            "maxResults": 100,
            "key": youtube_keys()[0],
            "textFormat": "plainText",
            "order": "relevance",
        }
        if page_token:
            params["pageToken"] = page_token

        url = f"https://www.googleapis.com/youtube/v3/commentThreads?{urllib.parse.urlencode(params)}"
        req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})

        try:
            with urllib.request.urlopen(req) as resp:
                data = json.loads(resp.read().decode())
        except Exception as e:
            print(f"  [stage 4] Note: YouTube comment fetch ended at page {page}: {e}")
            break

        items = data.get("items", [])
        for item in items:
            top_snippet = item.get("snippet", {}).get("topLevelComment", {}).get("snippet", {})
            text = top_snippet.get("textDisplay", "")
            author = top_snippet.get("authorDisplayName", "")
            like_count = top_snippet.get("likeCount", 0)

            matches = list(TIMESTAMP_RE.finditer(text))
            timestamps = [parse_timestamp_seconds(m) for m in matches]

            words = set(re.findall(r'\w+|[💀😂]', text.lower()))
            is_laugh = bool(words & LAUGH_TERMS)

            comments.append({
                "text": text,
                "author": author,
                "likes": like_count,
                "timestamps": timestamps,
                "is_laugh": is_laugh,
            })

        page_token = data.get("nextPageToken")
        if not page_token:
            break

    return comments


def fetch_third_party_emotes(channel_id: Optional[str] = None) -> Dict[str, List[str]]:
    """
    Fetch 7TV and BTTV global (and channel) emote sets via public REST APIs.
    Categorizes emotes into laugh, hype, confusion, sad families (§6.1).
    """
    emotes_by_family = {
        "laugh": set(),
        "hype": set(),
        "confusion": set(),
        "sad": set(),
    }

    # 1. 7TV global emotes
    try:
        url = "https://7tv.io/v3/emote-sets/global"
        req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
        with urllib.request.urlopen(req, timeout=5) as r:
            d = json.loads(r.read().decode())
        for e in d.get("emotes", []):
            name = e.get("name", "")
            nl = name.lower()
            if any(k in nl for k in ["lul", "kek", "laugh", "giggle", "dead", "icant"]):
                emotes_by_family["laugh"].add(name)
            elif any(k in nl for k in ["pog", "hype", "clap", "fire", "letsgo"]):
                emotes_by_family["hype"].add(name)
            elif any(k in nl for k in ["wut", "monka", "huh", "what"]):
                emotes_by_family["confusion"].add(name)
            elif any(k in nl for k in ["sad", "cry", "rip", "pepehands"]):
                emotes_by_family["sad"].add(name)
    except Exception:
        pass

    # 2. BTTV global emotes
    try:
        url = "https://api.betterttv.net/3/cached/emotes/global"
        req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
        with urllib.request.urlopen(req, timeout=5) as r:
            bttv = json.loads(r.read().decode())
        for e in bttv:
            code = e.get("code", "")
            cl = code.lower()
            if any(k in cl for k in ["lul", "kek", "laugh", "giggle", "icant"]):
                emotes_by_family["laugh"].add(code)
            elif any(k in cl for k in ["pog", "hype", "clap"]):
                emotes_by_family["hype"].add(code)
            elif any(k in cl for k in ["wut", "monka", "huh"]):
                emotes_by_family["confusion"].add(code)
            elif any(k in cl for k in ["sad", "cry", "rip"]):
                emotes_by_family["sad"].add(code)
    except Exception:
        pass

    return {k: sorted(list(v)) for k, v in emotes_by_family.items()}


def fetch_twitch_community_clips(vod_id: str, max_pages: int = 10) -> List[Dict[str, Any]]:
    """
    Fetch community clips of one VOD via Twitch Helix (Blueprint §5, §6.1).
    Helix filters clips by broadcaster and creation time, not by VOD: the VOD gives its owner and start time,
    clips made from then on are paged through, and only clips cut from this VOD are kept.
    Requires valid client_id and client_secret in .env.
    """
    vod_id = vod_id.lstrip("v")
    if not vod_id.isdigit() or not TWITCH_CLIENT_ID or not TWITCH_CLIENT_SECRET or TWITCH_CLIENT_ID.startswith("your_"):
        return []

    try:
        # Acquire app access token
        data = urllib.parse.urlencode({
            "client_id": TWITCH_CLIENT_ID,
            "client_secret": TWITCH_CLIENT_SECRET,
            "grant_type": "client_credentials",
        }).encode("utf-8")
        req = urllib.request.Request("https://id.twitch.tv/oauth2/token", data=data, method="POST")
        with urllib.request.urlopen(req, timeout=8) as r:
            token = json.loads(r.read().decode()).get("access_token")
        if not token:
            return []
        headers = {"Client-ID": TWITCH_CLIENT_ID, "Authorization": f"Bearer {token}", "User-Agent": "Mozilla/5.0"}

        def helix(path: str, params: Dict[str, Any]) -> Dict[str, Any]:
            url = f"https://api.twitch.tv/helix/{path}?{urllib.parse.urlencode(params)}"
            with urllib.request.urlopen(urllib.request.Request(url, headers=headers), timeout=8) as resp:
                return json.loads(resp.read().decode())

        vods = helix("videos", {"id": vod_id}).get("data") or []
        if not vods:
            return []
        params = {"broadcaster_id": vods[0]["user_id"], "started_at": vods[0]["created_at"], "first": 100}

        clips = []
        for _ in range(max_pages):  # ponytail: 1000 clips max; the most-viewed come first
            page = helix("clips", params)
            for item in page.get("data", []):
                if item.get("video_id") != vod_id:
                    continue
                clips.append({
                    "id": item.get("id"),
                    "url": item.get("url"),
                    "vod_offset": item.get("vod_offset"),
                    "creator_id": item.get("creator_id"),
                    "view_count": item.get("view_count", 0),
                    "is_featured": item.get("is_featured", False),
                    "duration": item.get("duration", 0.0),
                    "title": item.get("title", ""),
                    "created_at": item.get("created_at"),
                    "vod_created_at": vods[0]["created_at"],  # with created_at, tells a live clip from a VOD clip
                })
            cursor = (page.get("pagination") or {}).get("cursor")
            if not cursor:
                break
            params["after"] = cursor
        return clips
    except Exception as e:
        print(f"  [stage 4] Note: Helix community clips call: {e}")
        return []


def run_stage4_crowd(video_dir: Path, meta: Dict[str, Any]) -> Dict[str, Any]:
    """
    Run Stage 4: fetch_crowd.
    Returns crowd dict with comments, clips, and emotes.
    Resumes if files exist.
    """
    webpage_url = meta.get("webpage_url", "")
    is_twitch = "twitch.tv" in webpage_url.lower() or meta.get("is_twitch", False)
    is_local = meta.get("is_local", False)

    # 1. Twitch branch
    if is_twitch:
        emotes_path = video_dir / "emotes.json"
        clips_path = video_dir / "clips.json"

        # Emotes
        if emotes_path.exists():
            with open(emotes_path, "r", encoding="utf-8") as f:
                emotes = json.load(f)
        else:
            print("  [stage 4] Fetching third-party emotes (7TV, BTTV)...")
            emotes = fetch_third_party_emotes()
            with open(emotes_path, "w", encoding="utf-8") as f:
                json.dump(emotes, f, indent=2)

        # Community clips
        if clips_path.exists():
            with open(clips_path, "r", encoding="utf-8") as f:
                clips = json.load(f)
        else:
            clips = fetch_twitch_community_clips(str(meta.get("id") or ""))
            with open(clips_path, "w", encoding="utf-8") as f:
                json.dump(clips, f, indent=2)

        print(f"  [stage 4] Twitch crowd ready: {sum(len(v) for v in emotes.values())} emotes, {len(clips)} community clips.")
        return {
            "platform": "twitch",
            "comments": [],
            "emotes": emotes,
            "clips": clips,
        }

    # 2. Local upload branch
    if is_local:
        print("  [stage 4] Local video; skipping crowd fetch.")
        return {
            "platform": "upload",
            "comments": [],
            "emotes": {},
            "clips": [],
        }

    # 3. YouTube branch
    comments_path = video_dir / "comments.json"
    if comments_path.exists():
        print(f"  [stage 4] Resuming: found {comments_path.name}")
        with open(comments_path, "r", encoding="utf-8") as f:
            comments = json.load(f)
    else:
        video_id = meta.get("id")
        print(f"  [stage 4] Fetching crowd comments for YouTube video {video_id}...")
        comments = fetch_youtube_comments(video_id) if video_id else []
        with open(comments_path, "w", encoding="utf-8") as f:
            json.dump(comments, f, indent=2)

    n_with_ts = sum(1 for c in comments if c.get("timestamps"))
    print(f"  [stage 4] Saved {len(comments)} YouTube comments ({n_with_ts} with timestamps).")
    return {
        "platform": "youtube",
        "comments": comments,
        "emotes": {},
        "clips": [],
    }
