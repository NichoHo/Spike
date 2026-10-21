"""
Stage 8: fetch_sections
Blueprint §5: Download or slice candidate sections with 5 s padding on each side.
Story clips (§6.7) have several segments from different parts of the stream. Each segment is fetched
exactly and the parts are joined into one section, so the renderer sees a single file on a virtual
timeline that starts at 0.
Output: data/videos/<id>/sections/section_<cand_id>.mp4
"""

import json
import os
import subprocess
from pathlib import Path
from typing import Dict, Any, List
import yt_dlp


def _fetch_range(meta: Dict[str, Any], sections_dir: Path, stem: str, pad_st: float, pad_et: float) -> Path:
    """Download or slice [pad_st, pad_et] of the source into sections_dir/<stem>.mp4."""
    out_file = sections_dir / f"{stem}.mp4"
    is_local = meta.get("is_local", False)
    local_path = meta.get("local_path")
    video_url = meta.get("webpage_url")

    if is_local and local_path and os.path.exists(local_path):
        cmd = [
            "ffmpeg", "-y", "-v", "error",
            "-ss", str(pad_st),
            "-to", str(pad_et),
            "-i", local_path,
            "-c:v", "libx264", "-preset", "veryfast", "-crf", "18",
            "-c:a", "aac", "-b:a", "128k",
            str(out_file)
        ]
        subprocess.run(cmd, check=True)
    else:
        # Remote URL section download via yt-dlp
        ydl_opts = {
            # Highest resolution up to 1440p, whatever the container: the old mp4-only filter could settle for a
            # low progressive stream. Crops and zooms upscale, so source pixels matter.
            "format": "bv*+ba/b",
            "format_sort": ["res:1440", "fps"],
            "merge_output_format": "mp4",
            "outtmpl": str(sections_dir / f"{stem}.%(ext)s"),
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
                "-c:v", "libx264", "-preset", "veryfast", "-crf", "18",
                "-c:a", "aac",
                str(out_file)
            ]
            subprocess.run(cmd, check=True)

    if not out_file.exists():
        matches = list(sections_dir.glob(f"{stem}.*"))
        if matches:
            out_file = matches[0]
    return out_file


def write_section_start(sec_file: Path, start_s: float) -> None:
    """Record the stream time at second 0 of a section, so a re-render with moved trims still finds its frames."""
    sec_file.with_suffix(".json").write_text(json.dumps({"start_s": round(start_s, 3)}), encoding="utf-8")


def _media_duration(path: Path) -> float:
    res = subprocess.run(
        ["ffprobe", "-v", "error", "-show_entries", "format=duration", "-of", "csv=p=0", str(path)],
        capture_output=True, text=True,
    )
    try:
        return float(res.stdout.strip())
    except ValueError:
        return 0.0


def section_bounds(sec_file: Path, cand_start_s: float, cand_end_s: float) -> Tuple[float, float]:
    """Stream seconds covered by a section file. Sections made before the sidecar existed had 5 s of padding."""
    try:
        lo = float(json.loads(sec_file.with_suffix(".json").read_text(encoding="utf-8"))["start_s"])
    except (OSError, ValueError, KeyError):
        lo = max(0.0, cand_start_s - 5.0)
    dur = _media_duration(sec_file)
    return lo, lo + dur if dur > 0 else cand_end_s + 5.0


def refetch_section(video_dir: Path, meta: Dict[str, Any], cand_id: int, start_s: float, end_s: float) -> Path:
    """Replace a section with one that covers [start_s - 5, end_s + 5]: used when an edit moves the edges
    outside the 5 s of padding that were downloaded. The old file stays if the download fails."""
    sections_dir = video_dir / "sections"
    pad_st = max(0.0, start_s - 5.0)
    new = _fetch_range(meta, sections_dir, f"section_{cand_id}_new", pad_st, end_s + 5.0)
    if not new.exists() or new.stat().st_size < 1000:
        raise RuntimeError("could not download the wider section")
    final = sections_dir / f"section_{cand_id}.mp4"
    new.replace(final)
    write_section_start(final, pad_st)
    return final


def ensure_segment_section(video_dir: Path, meta: Dict[str, Any], cand_id: int, k: int, start_s: float, end_s: float, pad_s: float = 3.0) -> Path:
    """Section file for segment k of a concept clip: it covers [start_s, end_s] with a little room, fetched or fetched
    again when an edit moved the segment outside what was downloaded. Raises when the download fails; an existing
    section is kept in that case."""
    sections_dir = video_dir / "sections"
    sections_dir.mkdir(exist_ok=True)
    final = sections_dir / f"section_{cand_id}_s{k}.mp4"
    if final.exists() and final.stat().st_size > 1000:
        lo, hi = section_bounds(final, start_s, end_s)
        if lo <= start_s - 0.5 and hi >= end_s + 0.5:
            return final
    pad_st = max(0.0, start_s - pad_s)
    new = _fetch_range(meta, sections_dir, f"section_{cand_id}_s{k}_new", pad_st, end_s + pad_s)
    if not new.exists() or new.stat().st_size < 1000:
        raise RuntimeError(f"could not download segment {k + 1}")
    new.replace(final)
    write_section_start(final, pad_st)
    return final


def run_stage8_sections(
    video_dir: Path,
    meta: Dict[str, Any],
    candidates: List[Dict[str, Any]]
) -> List[Path]:
    """Run Stage 8: download/slice sections with 5s padding. Resumes existing sections."""
    sections_dir = video_dir / "sections"
    sections_dir.mkdir(exist_ok=True)

    section_files = []

    for idx, cand in enumerate(candidates, 1):
        cand_id = cand.get("id") or idx
        out_file = sections_dir / f"section_{cand_id}.mp4"

        if not cand.get("segs") and out_file.exists() and out_file.stat().st_size > 1000:
            print(f"  [stage 8] Resuming: found section_{cand_id}.mp4")
            section_files.append(out_file)
            cand["section_file"] = str(out_file)
            continue

        if cand.get("segs"):
            # Concept clip: one section per segment, rendered one by one and joined (concept_render)
            print(f"  [stage 8] Fetching {cand.get('concept')} clip {cand_id}: {len(cand['segs'])} segments...")
            for k, seg in enumerate(cand["segs"]):
                out_file = ensure_segment_section(video_dir, meta, cand_id, k, seg["start_s"], seg["end_s"])
                if k == 0:
                    cand["section_file"] = str(out_file)
            section_files.append(out_file)
            continue
        else:
            pad_st = max(0.0, cand["start_s"] - 5.0)
            pad_et = cand["end_s"] + 5.0
            print(f"  [stage 8] Slicing section {cand_id} ({pad_st:.1f}s to {pad_et:.1f}s)...")
            out_file = _fetch_range(meta, sections_dir, f"section_{cand_id}", pad_st, pad_et)
            write_section_start(out_file, pad_st)

        section_files.append(out_file)
        cand["section_file"] = str(out_file)

    print(f"  [stage 8] Completed {len(section_files)} sections.")
    return section_files
