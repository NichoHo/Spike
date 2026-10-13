"""
Spike: disk cleanup. Keeps data/ small as streamers and clips pile up.
Kept: final renders, thumbnails, captions json, meta/transcript/candidates (small).
Dropped: source audio, uploaded originals, 16:9 baseline cuts, old re-render versions,
the section source plus renders of rejected clips, and section sources of clips left
ready/approved for SECTION_RETENTION_DAYS.
"""

from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Dict, List

from src.config import SECTION_RETENTION_DAYS, UPLOADS_DIR, VIDEOS_DIR
from src.db import get_connection


def _rm(path) -> int:
    """Delete a file, return bytes freed. Never raises (cleanup must not fail a job)."""
    try:
        p = Path(path)
        size = p.stat().st_size
        p.unlink()
        return size
    except OSError:
        return 0


def cleanup_after_pipeline(video_dir: Path, meta: Dict[str, Any], candidates: List[Dict[str, Any]]) -> int:
    """Run once a job finished successfully. Returns bytes freed."""
    freed = sum(_rm(p) for p in video_dir.glob("audio.*"))

    # 16:9 baseline cut is only an intermediate; keep it if the vertical render is missing.
    for c in candidates:
        if c.get("clip_file") and c.get("render_file"):
            freed += _rm(c["clip_file"])

    # Uploaded original: sections already sliced from it, rerenders use sections only.
    local = meta.get("local_path")
    if meta.get("is_local") and local and Path(local).parent.resolve() == UPLOADS_DIR.resolve():
        freed += _rm(local)

    print(f"  [cleanup] Freed {freed / (1024 * 1024):.1f} MB")
    return freed


def delete_rejected_clip_files(clip: Dict[str, Any]) -> int:
    """Delete every file of a rejected clip: render, thumbnail, caption sidecars and its section source.
    The DB row stays so reject reasons keep feeding stats. Returns bytes freed."""
    freed = 0
    if clip.get("file_path"):
        freed += _rm(clip["file_path"]) + _rm(Path(clip["file_path"]).with_suffix(".ass"))
    if clip.get("thumb_path"):
        freed += _rm(clip["thumb_path"])
    video_dir = VIDEOS_DIR / str(clip["video_id"])
    cand_id = clip["candidate_id"]
    freed += _rm(video_dir / "sections" / f"section_{cand_id}.mp4")
    freed += _rm(video_dir / "renders" / f"captions_{cand_id}.json")
    return freed


def sweep_old_sections() -> int:
    """Delete the section source of clips that were ready/approved for SECTION_RETENTION_DAYS.
    Those clips can no longer be trimmed or re-laid out (re-render route returns 404)."""
    cutoff = (datetime.now(timezone.utc) - timedelta(days=SECTION_RETENTION_DAYS)).isoformat()
    with get_connection() as conn:
        rows = conn.execute(
            """SELECT cand.video_id, c.candidate_id
               FROM clips c JOIN candidates cand ON cand.id = c.candidate_id
               WHERE c.status IN ('ready', 'approved')
                 AND COALESCE(c.reviewed_at, c.created_at) < ?""",
            (cutoff,),
        ).fetchall()
    freed = sum(_rm(VIDEOS_DIR / str(r["video_id"]) / "sections" / f"section_{r['candidate_id']}.mp4") for r in rows)
    if freed:
        print(f"[cleanup] Swept old sections, freed {freed / (1024 * 1024):.1f} MB")
    return freed
