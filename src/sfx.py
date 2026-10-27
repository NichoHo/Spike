"""
Meme sound effects placed on a clip from the clip page.

The files are Pixabay uploads (Pixabay Content License: free in videos, but the raw files may not be handed out on
their own). The repo is public, so they are not in git: each one is fetched from Pixabay's CDN into data/sfx the
first time it is needed. Picked as low risk: plain noises or the uploader's own voice, not in YouTube Content ID.
"""

import json
import logging
import subprocess
import threading
import urllib.request
from pathlib import Path
from typing import Any, Dict, List, Optional

from src.config import SFX_DIR

logger = logging.getLogger("spike.sfx")

_CDN = "https://cdn.pixabay.com/audio/"
# id, title, CDN path, uploader, Pixabay page id, when it fits ("Ask the editor" reads this); speed > 1 plays it faster
SOUNDS: List[Dict[str, Any]] = [
    {"id": "thud", "title": "Thud", "src": "2025/09/16/audio_5e920f9ce0.mp3", "author": "DRAGON-STUDIO", "page": 405470, "use": "a heavy boom right on a shocking line or reveal (the Vine boom)"},
    {"id": "bonk", "title": "Bonk", "src": "2022/03/10/audio_7111d17a49.mp3", "author": "freesound_community", "page": 36055, "use": "someone gets hit, fails or says something dumb"},
    {"id": "waterphone", "title": "Waterphone", "src": "2023/11/04/audio_786b4724fb.mp3", "author": "u_a7pk5xrn16", "page": 174768, "use": "creepy or suspicious moment, awkward realization"},
    {"id": "waterphone_2", "title": "Waterphone 2", "src": "2025/05/16/audio_1be1707a05.mp3", "author": "ALEXIS_GAMING_CAM", "page": 342936, "use": "longer suspense build before something weird"},
    {"id": "woah", "title": "Woooaah", "src": "2024/04/03/audio_23bf7b77ed.mp3", "author": "Alex_Jauk", "page": 199849, "use": "surprised amazement at something big"},
    {"id": "eaaah", "title": "Eaaaah", "src": "2025/04/01/audio_2dae8fe99c.mp3", "author": "Alex_Jauk", "page": 321241, "use": "panic or a sudden startled scream"},
    {"id": "scream", "title": "Hysteric scream", "src": "2024/02/13/audio_c67d77ce30.mp3", "author": "Alex_Jauk", "page": 190845, "use": "over-the-top panic, chaos"},
    {"id": "fart", "title": "Fart", "src": "2024/07/30/audio_4aa94d4d1e.mp3", "author": "aPebble", "page": 228244, "use": "gross or embarrassing moment, a cheap joke"},
    {"id": "sad_trombone", "title": "Sad trombone", "src": "2021/08/04/audio_c003cb2711.mp3", "author": "freesound_community", "page": 6347, "speed": 1.6, "use": "a fail, a loss, a plan that did not work"},
    {"id": "record_scratch", "title": "Record scratch", "src": "2022/03/26/audio_7d318dd030.mp3", "author": "freesound_community", "page": 108233, "use": "everything stops: right before a twist or an awkward silence"},
]
_BY_ID = {s["id"]: s for s in SOUNDS}
SFX_MAX = 40  # per clip
_lock = threading.Lock()


def sound_menu() -> str:
    """One line per sound for an AI prompt: id: when it fits."""
    return "\n".join(f"{s['id']}: {s['use']}" for s in SOUNDS)


def list_sounds() -> List[Dict[str, Any]]:
    return [{"id": s["id"], "title": s["title"], "author": s["author"]} for s in SOUNDS]


def sound_path(sound_id: str) -> Optional[Path]:
    """The local file for a sound, fetched (and sped up) on first use. None for an unknown id or a failed fetch."""
    s = _BY_ID.get(sound_id)
    if not s:
        return None
    path = SFX_DIR / f"{sound_id}.mp3"
    with _lock:  # a render and a preview may ask for the same file at once
        if path.exists():
            return path
        SFX_DIR.mkdir(parents=True, exist_ok=True)
        raw = SFX_DIR / f"{sound_id}.raw.mp3"
        try:
            req = urllib.request.Request(_CDN + s["src"], headers={"User-Agent": "Mozilla/5.0", "Referer": "https://pixabay.com/"})
            with urllib.request.urlopen(req, timeout=30) as r:
                raw.write_bytes(r.read())
            if s.get("speed"):
                subprocess.run(["ffmpeg", "-y", "-hide_banner", "-loglevel", "error", "-i", str(raw),
                                "-filter:a", f"atempo={s['speed']}", str(path)], check=True)
                raw.unlink()
            else:
                raw.replace(path)
        except Exception as exc:
            raw.unlink(missing_ok=True)
            logger.warning("Could not fetch sound %s: %s", sound_id, exc)
            return None
    return path


def clean_sfx(raw: Any, clip_start: float, clip_end: float) -> List[Dict[str, Any]]:
    """[{t, id}] from the page or the database: known sounds inside the clip, sorted, at most SFX_MAX."""
    if isinstance(raw, str):
        try:
            raw = json.loads(raw or "[]")
        except ValueError:
            return []
    out = []
    for item in raw if isinstance(raw, list) else []:
        try:
            t, sid = round(float(item["t"]), 2), str(item["id"])
        except (KeyError, TypeError, ValueError):
            continue
        if sid in _BY_ID and clip_start <= t < clip_end:
            out.append({"t": t, "id": sid})
    return sorted(out, key=lambda x: x["t"])[:SFX_MAX]
