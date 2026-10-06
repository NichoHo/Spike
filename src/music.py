"""
Spike: Music library management, startup license verification, and mood track selection.
Blueprint §7.3, §12, §13:
- music/ folder with mood subfolders: hype, funny, chill, dramatic, wholesome.
- Every audio track MUST have an accompanying .json license sidecar.
- Startup check strictly enforces that every track has a verified license sidecar.
"""

from __future__ import annotations

import json
import logging
import os
import random
from pathlib import Path
from typing import Any, Dict, List, Optional, Set, Tuple

from src.config import (
    MUSIC_DIR,
    MUSIC_MOODS,
)

logger = logging.getLogger("spike.music")

AUDIO_EXTENSIONS: Set[str] = {".mp3", ".wav", ".m4a", ".aac", ".flac", ".ogg"}
REQUIRED_SIDECAR_FIELDS: Tuple[str, ...] = ("license", "source", "url")

# Common mood synonym mappings to map LLM / candidate moods to library folders
MOOD_SYNONYMS: Dict[str, str] = {
    # Hype
    "energetic": "hype",
    "energy": "hype",
    "exciting": "hype",
    "hype": "hype",
    "action": "hype",
    "intense": "hype",
    "epic": "hype",
    # Funny
    "funny": "funny",
    "humor": "funny",
    "comedy": "funny",
    "silly": "funny",
    "laugh": "funny",
    "quirky": "funny",
    "awkward": "funny",
    # Chill
    "chill": "chill",
    "relaxed": "chill",
    "calm": "chill",
    "lofi": "chill",
    "peaceful": "chill",
    "neutral": "chill",
    "casual": "chill",
    # Dramatic
    "dramatic": "dramatic",
    "serious": "dramatic",
    "tension": "dramatic",
    "suspense": "dramatic",
    "dark": "dramatic",
    "sad": "dramatic",
    "somber": "dramatic",
    # Wholesome
    "wholesome": "wholesome",
    "happy": "wholesome",
    "sweet": "wholesome",
    "heartwarming": "wholesome",
    "uplifting": "wholesome",
    "cute": "wholesome",
    "joy": "wholesome",
}


class MusicLicenseError(Exception):
    """Raised when an audio track is missing a required license sidecar or has invalid metadata."""
    pass


def validate_music_library(
    music_dir: Optional[Path] = None,
    enforce: bool = True,
) -> Dict[str, Any]:
    """
    Scan the music library and verify every track has an accompanying license sidecar.
    Blueprint §7.3, §13 Phase 5:
    'every track in music/ has a license sidecar (a startup check enforces it).'

    Args:
        music_dir: Path to the music library. Defaults to MUSIC_DIR.
        enforce: If True, raises MusicLicenseError on any violation.

    Returns:
        Dict with keys:
            'valid': bool,
            'by_mood': Dict[str, List[Dict[str, Any]]],
            'all_tracks': List[Dict[str, Any]],
            'errors': List[str]
    """
    mdir = Path(music_dir or MUSIC_DIR)
    errors: List[str] = []
    by_mood: Dict[str, List[Dict[str, Any]]] = {m: [] for m in MUSIC_MOODS}
    all_tracks: List[Dict[str, Any]] = []

    if not mdir.exists():
        # Ensure directory exists with mood folders
        mdir.mkdir(parents=True, exist_ok=True)
        for mood in MUSIC_MOODS:
            (mdir / mood).mkdir(exist_ok=True)
        return {
            "valid": True,
            "by_mood": by_mood,
            "all_tracks": [],
            "errors": [],
        }

    # Iterate over all files in music_dir recursively
    for path in mdir.rglob("*"):
        if path.is_file() and path.suffix.lower() in AUDIO_EXTENSIONS:
            # Check for sidecar JSON
            sidecar_path = path.with_suffix(".json")
            if not sidecar_path.exists():
                err = f"Track '{path.name}' in '{path.parent.name}' is missing license sidecar '{sidecar_path.name}'"
                errors.append(err)
                continue

            try:
                data = json.loads(sidecar_path.read_text(encoding="utf-8"))
            except Exception as e:
                err = f"Track '{path.name}' sidecar '{sidecar_path.name}' is corrupted or invalid JSON: {e}"
                errors.append(err)
                continue

            if not isinstance(data, dict):
                err = f"Track '{path.name}' sidecar '{sidecar_path.name}' must contain a JSON object"
                errors.append(err)
                continue

            # Verify required license fields
            missing_fields = [f for f in REQUIRED_SIDECAR_FIELDS if not str(data.get(f, "")).strip()]
            if missing_fields:
                err = (
                    f"Track '{path.name}' sidecar '{sidecar_path.name}' is missing required license fields: "
                    f"{', '.join(missing_fields)}"
                )
                errors.append(err)
                continue

            mood = path.parent.name.lower()
            rel_path = path.relative_to(mdir.parent).as_posix() if mdir.parent in path.parents else path.as_posix()

            track_info = {
                "title": data.get("title", path.stem.replace("_", " ").title()),
                "artist": data.get("artist", "Unknown Artist"),
                "mood": mood,
                "license": data["license"],
                "source": data["source"],
                "url": data["url"],
                "attribution": data.get("attribution", ""),
                "feel": data.get("feel", ""),
                "bpm": data.get("bpm", ""),
                "description": data.get("description", ""),
                "use_for": data.get("use_for", ""),
                "filename": path.name,
                "stem": path.stem,
                "path": str(path),
                "rel_path": rel_path,
                "sidecar_path": str(sidecar_path),
            }

            if mood not in by_mood:
                by_mood[mood] = []
            by_mood[mood].append(track_info)
            all_tracks.append(track_info)

    if errors:
        msg = f"Music library license check failed ({len(errors)} error(s)):\n  - " + "\n  - ".join(errors)
        logger.error(msg)
        if enforce:
            raise MusicLicenseError(msg)

    return {
        "valid": len(errors) == 0,
        "by_mood": by_mood,
        "all_tracks": all_tracks,
        "errors": errors,
    }


def normalize_mood(mood_str: Optional[str]) -> str:
    """Normalize a mood descriptor to one of the standard mood folders."""
    if not mood_str:
        return "chill"
    cleaned = mood_str.strip().lower()
    return MOOD_SYNONYMS.get(cleaned, "chill")


def get_random_track_for_mood(
    mood: Optional[str] = None,
    music_dir: Optional[Path] = None,
    seed: Optional[int] = None,
) -> Optional[Path]:
    """
    Select an audio track matching the given mood from the music library.
    Falls back gracefully to 'chill' or any available track if the requested mood is empty.
    """
    target_mood = normalize_mood(mood)
    lib = validate_music_library(music_dir, enforce=False)
    
    tracks = lib["by_mood"].get(target_mood, [])
    if not tracks and target_mood != "chill":
        tracks = lib["by_mood"].get("chill", [])
    if not tracks and lib["all_tracks"]:
        tracks = lib["all_tracks"]
    if not tracks:
        return None

    rng = random.Random(seed) if seed is not None else random
    selected = rng.choice(tracks)
    return Path(selected["path"])


def resolve_music_path(
    track_identifier: str,
    music_dir: Optional[Path] = None,
) -> Optional[Path]:
    """
    Resolve a track identifier (path, relative path, filename stem, or mood) to a valid audio file.
    """
    if not track_identifier:
        return None

    mdir = Path(music_dir or MUSIC_DIR)

    # 1. Direct path exists
    p = Path(track_identifier)
    if p.exists() and p.is_file():
        return p

    # 2. Relative to music_dir or project root
    candidate = mdir.parent / track_identifier
    if candidate.exists() and candidate.is_file():
        return candidate
    candidate = mdir / track_identifier
    if candidate.exists() and candidate.is_file():
        return candidate

    # 3. Search by filename or stem across music_dir
    cleaned_id = track_identifier.strip().lower()
    lib = validate_music_library(mdir, enforce=False)
    for track in lib["all_tracks"]:
        if (
            track["filename"].lower() == cleaned_id
            or track["stem"].lower() == cleaned_id
            or track["rel_path"].lower() == cleaned_id
        ):
            return Path(track["path"])

    # 4. If identifier is a mood name, pick a track from that mood
    if cleaned_id in MUSIC_MOODS or cleaned_id in MOOD_SYNONYMS:
        return get_random_track_for_mood(cleaned_id, music_dir=mdir)

    return None


def list_all_tracks(music_dir: Optional[Path] = None) -> List[Dict[str, Any]]:
    """Return all valid tracks with their license metadata for UI selection."""
    lib = validate_music_library(music_dir, enforce=False)
    return sorted(lib["all_tracks"], key=lambda x: (x["mood"], x["title"]))


def music_credit(track: "str | Path | None") -> str:
    """The credit line a post must carry when its clip uses this track ("" when none is needed)."""
    path = resolve_music_path(str(track)) if track else None
    if not path:
        return ""
    sidecar = path.with_suffix(".json")
    try:
        return json.loads(sidecar.read_text(encoding="utf-8")).get("attribution", "").strip()
    except (OSError, ValueError):
        return ""


def track_catalog_for_llm(music_dir: Optional[Path] = None) -> str:
    """One line per track for the LLM judge to pick from: id | feel | bpm | when to use it."""
    lines = []
    for t in list_all_tracks(music_dir):
        desc = t["use_for"] or t["description"][:120]
        lines.append(f"{t['stem']} | {t['feel'] or t['mood']} | {t['bpm'] or '?'} bpm | {desc}")
    return "\n".join(lines)
