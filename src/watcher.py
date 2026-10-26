"""
Spike: Source Watcher Daemon
Blueprint §5 & §13 Phase 3:
Polls Twitch and YouTube sources with auto_process = 1 every 15 minutes:
- Twitch: fetches latest archive VODs via Helix Get Videos or yt-dlp playlist
- YouTube: fetches latest uploads via channel RSS feed
Queues new videos into the database with deduplication (UNIQUE(origin, external_id)).
"""

import time
import urllib.request
import urllib.parse
import xml.etree.ElementTree as ET
from pathlib import Path
from typing import Dict, Any, List, Optional
import yt_dlp

from src.config import WATCHER_INTERVAL_MINUTES, TWITCH_CLIENT_ID, TWITCH_CLIENT_SECRET
from src.db import get_connection, register_video, init_db


def fetch_youtube_uploads(channel_id: str, max_items: int = 10) -> List[Dict[str, str]]:
    """Latest uploads and past streams via the channel's uploads playlist (UC... becomes UU...). Used when
    YouTube's RSS feed fails: it returns 404 for many channels."""
    if not channel_id.startswith("UC"):
        return []
    opts = {"extract_flat": True, "quiet": True, "no_warnings": True, "playlist_items": f"1:{max_items}"}
    try:
        with yt_dlp.YoutubeDL(opts) as ydl:
            info = ydl.extract_info(f"https://www.youtube.com/playlist?list=UU{channel_id[2:]}", download=False)
        return [
            {"id": e["id"], "url": f"https://www.youtube.com/watch?v={e['id']}", "title": e.get("title", "")}
            for e in (info.get("entries") or []) if e and e.get("id")
        ]
    except Exception as e:
        print(f"  [watcher] Note: YouTube uploads fetch for {channel_id}: {e}")
        return []


def fetch_youtube_channel_rss(channel_id: str) -> List[Dict[str, str]]:
    """Fetch latest videos for a YouTube channel via public RSS feed (zero API quota); the uploads playlist
    stands in when the feed fails."""
    url = f"https://www.youtube.com/feeds/videos.xml?channel_id={channel_id}"
    req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
    videos = []

    try:
        with urllib.request.urlopen(req, timeout=10) as resp:
            content = resp.read()
        root = ET.fromstring(content)
        entry_tag = "{http://www.w3.org/2005/Atom}entry"
        yt_vid_tag = "{http://www.youtube.com/xml/schemas/2015}videoId"
        atom_title_tag = "{http://www.w3.org/2005/Atom}title"

        for entry in root.findall(entry_tag):
            vid_elem = entry.find(yt_vid_tag)
            title_elem = entry.find(atom_title_tag)
            if vid_elem is not None and vid_elem.text:
                vid_id = vid_elem.text.strip()
                title = title_elem.text.strip() if title_elem is not None else ""
                videos.append({
                    "id": vid_id,
                    "url": f"https://www.youtube.com/watch?v={vid_id}",
                    "title": title,
                })
    except Exception as e:
        print(f"  [watcher] Note: YouTube RSS fetch for {channel_id}: {e}")

    return videos or fetch_youtube_uploads(channel_id)


def twitch_vod_id(raw: str) -> str:
    """yt-dlp's flat Twitch listing gives ids like 'v2899740602'; VOD URLs and stage 3 need the digits only."""
    raw = str(raw)
    return raw[1:] if raw[:1] == "v" and raw[1:].isdigit() else raw


def fetch_twitch_latest_vods(channel_name: str, max_vods: int = 5) -> List[Dict[str, str]]:
    """Fetch latest past broadcast VODs for a Twitch channel via yt-dlp flat playlist."""
    url = f"https://www.twitch.tv/{channel_name}/videos?filter=archives"
    ydl_opts = {
        "extract_flat": True,
        "quiet": True,
        "no_warnings": True,
        "playlist_items": f"1:{max_vods}",
    }
    vods = []
    try:
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            info = ydl.extract_info(url, download=False)
        for entry in info.get("entries", []):
            if entry and entry.get("id"):
                vod_id = twitch_vod_id(entry["id"])
                vods.append({
                    "id": vod_id,
                    "url": f"https://www.twitch.tv/videos/{vod_id}",
                    "title": entry.get("title", ""),
                })
    except Exception as e:
        print(f"  [watcher] Note: Twitch VOD fetch for {channel_name}: {e}")

    return vods


# yt-dlp options that print nothing: expected "not live" errors would flood the log every cycle.
_SILENT_YDL = {
    "quiet": True,
    "logger": type("Silent", (), dict.fromkeys(["debug", "warning", "error"], lambda *a: None))(),
}


def youtube_video_is_finished(url: str) -> bool:
    """False for live, upcoming, or still-processing streams, and on errors (retried next cycle)."""
    try:
        with yt_dlp.YoutubeDL(_SILENT_YDL) as ydl:
            info = ydl.extract_info(url, download=False, process=False)
        return info.get("live_status") in (None, "not_live", "was_live")
    except yt_dlp.utils.DownloadError:
        return False


def twitch_channel_is_live(channel_name: str) -> bool:
    """True if the channel is streaming now. Errors other than 'not live' count as live, so a
    flaky check only delays the newest VOD by one watcher cycle instead of clipping a partial one."""
    try:
        with yt_dlp.YoutubeDL(_SILENT_YDL) as ydl:
            ydl.extract_info(f"https://www.twitch.tv/{channel_name}", download=False, process=False)
        return True
    except yt_dlp.utils.DownloadError as e:
        return not isinstance(e.exc_info[1], yt_dlp.utils.UserNotLive)


def latest_finished_vod(kind: str, ext_id: str, vods: Optional[List[Dict[str, str]]] = None) -> Optional[Dict[str, str]]:
    """Newest finished broadcast or upload of a source, or None. A live Twitch stream's own archive is skipped,
    like check_and_queue_sources does. Pass `vods` to reuse a listing already fetched."""
    if kind == "youtube":
        items = fetch_youtube_channel_rss(ext_id) if vods is None else vods
        return next((v for v in items if youtube_video_is_finished(v["url"])), None)
    vods = fetch_twitch_latest_vods(ext_id, 2) if vods is None else vods
    if vods and twitch_channel_is_live(ext_id):
        vods = vods[1:]
    return vods[0] if vods else None


def vod_url_for(kind: str, raw: str) -> str:
    """The field accepts a full URL or a bare video ID; turn an ID into the URL yt-dlp needs."""
    raw = raw.strip()
    if "://" in raw:
        return raw
    if kind == "twitch":
        return f"https://www.twitch.tv/videos/{twitch_vod_id(raw)}"
    return f"https://www.youtube.com/watch?v={raw}"


def check_and_queue_sources() -> int:
    """Check all auto_process sources and queue new videos. Returns number of newly queued videos."""
    init_db()
    new_count = 0

    with get_connection() as conn:
        c = conn.cursor()
        c.execute("SELECT id, kind, external_id, display_name FROM sources WHERE auto_process = 1")
        sources = c.fetchall()

    if not sources:
        return 0

    print(f"  [watcher] Checking {len(sources)} auto-process source(s)...")

    for s in sources:
        s_id = s["id"]
        kind = s["kind"]
        ext_id = s["external_id"]
        name = s["display_name"] or ext_id

        found_items = []
        if kind == "youtube":
            found_items = fetch_youtube_channel_rss(ext_id)
        elif kind == "twitch":
            found_items = fetch_twitch_latest_vods(ext_id)
            # While live, the newest archive is the stream still being recorded. Queue it after it ends.
            if found_items and twitch_channel_is_live(ext_id):
                print(f"  [watcher] {name} is live; waiting for the stream to end.")
                found_items = found_items[1:]

        for item in found_items:
            try:
                # Skip anything already known, so a failed job is not re-queued every cycle.
                with get_connection() as conn:
                    if conn.execute(
                        "SELECT 1 FROM videos WHERE origin = 'url' AND external_id = ?", (item["id"],)
                    ).fetchone():
                        continue
                # RSS also lists live and upcoming streams. Queue them once they have ended.
                if kind == "youtube" and not youtube_video_is_finished(item["url"]):
                    print(f"  [watcher] Skipping {item['id']} from {name} for now: live, upcoming, or unavailable.")
                    continue
                vid_id = register_video(
                    origin="url",
                    url_or_path=item["url"],
                    external_id=item["id"],
                    title=item["title"],
                    source_id=s_id,
                )
                new_count += 1
                safe_title = item['title'].encode('ascii', errors='replace').decode('ascii')
                print(f"  [watcher] Queued new video #{vid_id} from {name}: '{safe_title}'")
            except Exception as e:
                print(f"  [watcher] Note: error queuing {item.get('id')}: {e}")

    return new_count


def run_watcher_loop(single_run: bool = False):
    """Run watcher loop every WATCHER_INTERVAL_MINUTES."""
    print("==========================================")
    print("  Spike Watcher Daemon started")
    print(f"  Interval: {WATCHER_INTERVAL_MINUTES} minutes")
    print("==========================================")

    while True:
        try:
            n = check_and_queue_sources()
            if n > 0:
                print(f"  [watcher] Queued {n} new video(s) for processing.")
            else:
                print("  [watcher] Check complete: no new videos found.")
        except Exception as e:
            print(f"  [watcher] Error during source check: {e}")

        if single_run:
            break

        time.sleep(WATCHER_INTERVAL_MINUTES * 60)
