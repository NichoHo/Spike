"""
Spike: concept renderer (story, pov, top3, top5; reports/Clip concepts.md).

There is one renderer. Every segment goes through render_single_vertical_clip with the clip's single layout
(so it gets its own face tracking, captions and loudness normalisation); the pieces, plus the few generated
ones (skip card, tease, foreshadow flash), are joined with the ffmpeg concat demuxer using hard cuts, then one
final loudnorm pass. No transitions and no sound effects (§7.4).

Order of pieces:
  pov    the reaction, with the caption at the top for the whole clip. No hook title, no speech captions.
  story  [0.6 s flash of the payoff peak] setup (hook title), skip card, [middle, skip card], payoff (callback quote)
  top N  the entries from #N down to #1 under a fixed header (the title), with a numbered list on the left whose
         labels fill in as each entry plays
"""

import shutil
import subprocess
import uuid
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

import numpy as np

from src.concepts import (
    CALLBACK_S,
    CARD_S,
    FORESHADOW_S,
    TOP_RULES,
    order_entries,
    reaction_peak,
    segment_net_s,
)
from src.config import (
    OUTPUT_AUDIO_BITRATE,
    OUTPUT_AUDIO_CODEC,
    OUTPUT_FPS,
    OUTPUT_HEIGHT,
    OUTPUT_LOUDNESS_PEAK,
    OUTPUT_LOUDNESS_TARGET,
    OUTPUT_VIDEO_CODEC,
    OUTPUT_VIDEO_CRF,
    OUTPUT_VIDEO_PRESET,
    OUTPUT_WIDTH,
)
from src.pipeline.stage8_sections import ensure_segment_section
from src.pipeline.stage9b_captions import generate_ass, write_ass_file
from src.pipeline.stage9c_render import (
    _to_rel_path,
    map_timestamp_to_trimmed,
    read_section_start,
    render_single_vertical_clip,
    resolve_layout,
)


class ConceptRenderError(RuntimeError):
    pass


RANK_COLORS = {1: "&H0000C8FF&", 2: "&H00C0C0C0&", 3: "&H002A6ACD&"}   # gold, silver, bronze (ASS colours are BGR)
RANK_LIST_TOP_Y, RANK_ROW_H = 470, 108
RANK_CAPTION_Y = 0.74   # speech captions sit below the list


def ranking_overlay(title: str, highlight: str, segs: List[Dict[str, Any]], k: int) -> List[Dict[str, Any]]:
    """Overlay for entry k of a ranking (segs ordered #N first): the header for the whole piece, numbers 1..N down
    the left, and the labels of every entry shown so far, this one included. Labels stay once they appear."""
    end, n = 3600.0, len(segs)
    events = [{"start": 0, "end": end, "style": "rank_header", "text": title, "highlight": highlight}]
    shown = {s.get("rank") or (n - i): s.get("label", "") for i, s in enumerate(segs[:k + 1])}
    for r in range(1, n + 1):
        y = RANK_LIST_TOP_Y + (r - 1) * RANK_ROW_H
        events.append({"start": 0, "end": end, "style": "rank_num", "text": f"{r}.", "pos": (50, y),
                       "color": RANK_COLORS.get(r, "&H00FFFFFF&")})
        if shown.get(r):
            events.append({"start": 0, "end": end, "style": "rank_item", "text": shown[r], "pos": (150, y)})
    return events


def _ffmpeg(args: List[str]) -> None:
    res = subprocess.run(["ffmpeg", "-y", "-hide_banner", "-loglevel", "error", *args], capture_output=True, text=True)
    if res.returncode != 0:
        raise ConceptRenderError(f"ffmpeg failed: {res.stderr.strip()[-300:]}")


def _duration(path: Path) -> float:
    res = subprocess.run(["ffprobe", "-v", "error", "-show_entries", "format=duration", "-of", "csv=p=0", str(path)],
                         capture_output=True, text=True)
    try:
        return float(res.stdout.strip())
    except ValueError:
        return 0.0


def _encode() -> List[str]:
    """Same encode settings as every other render, so the pieces join without re-encoding."""
    return [
        "-c:v", OUTPUT_VIDEO_CODEC, "-preset", OUTPUT_VIDEO_PRESET, "-crf", str(OUTPUT_VIDEO_CRF),
        "-pix_fmt", "yuv420p", "-r", str(OUTPUT_FPS),
        "-c:a", OUTPUT_AUDIO_CODEC, "-b:a", OUTPUT_AUDIO_BITRATE, "-ar", "48000", "-ac", "2",
    ]


def make_card(text: str, out: Path, work: Path, dur: float = CARD_S) -> Path:
    """A 1 s skip card: plain text on a black frame, silent."""
    ass = write_ass_file(
        generate_ass([], 0, dur, profanity_mask=False, overlay_events=[{"start": 0, "end": dur, "style": "card", "text": text}]),
        work / f"{out.stem}.ass",
    )
    _ffmpeg([
        "-f", "lavfi", "-i", f"color=c=black:s={OUTPUT_WIDTH}x{OUTPUT_HEIGHT}:r={OUTPUT_FPS}:d={dur}",
        "-f", "lavfi", "-i", "anullsrc=r=48000:cl=stereo", "-t", str(dur),
        "-vf", f"ass={_to_rel_path(ass)}", *_encode(), "-shortest", str(out),
    ])
    return out


def cut_piece(src: Path, out: Path, start: float, dur: float) -> Path:
    """Cut dur seconds out of an already rendered piece (the story's foreshadow flash)."""
    start = max(0.0, min(start, max(0.0, _duration(src) - dur)))
    _ffmpeg(["-ss", f"{start:.3f}", "-t", f"{dur:.3f}", "-i", str(src)] + _encode() + [str(out)])
    return out


def join_pieces(pieces: List[Path], out: Path, work: Path) -> None:
    """Concat demuxer, hard cuts, then one loudnorm pass over the whole clip."""
    listing = work / "pieces.txt"
    listing.write_text("".join("file '" + str(p.resolve()).replace("\\", "/").replace("'", "'\\''") + "'\n" for p in pieces), encoding="utf-8")
    joined = work / "joined.mp4"
    _ffmpeg(["-f", "concat", "-safe", "0", "-i", str(listing), "-c", "copy", str(joined)])
    _ffmpeg([
        "-i", str(joined), "-c:v", "copy",
        "-af", f"loudnorm=I={OUTPUT_LOUDNESS_TARGET}:TP={OUTPUT_LOUDNESS_PEAK}:LRA=11,aresample=48000",
        "-c:a", OUTPUT_AUDIO_CODEC, "-b:a", OUTPUT_AUDIO_BITRATE, "-ac", "2", "-movflags", "+faststart", str(out),
    ])


def _peak_in_piece(seg: Dict[str, Any], video_dir: Path) -> float:
    """Seconds into the rendered segment where the reaction peaks (the loudest voice-jump second)."""
    mid = (seg["start_s"] + seg["end_s"]) / 2.0
    try:
        jump = np.load(video_dir / "signals.npz")["voice_jump"]
        peak = reaction_peak(jump, seg["start_s"], seg["end_s"], fallback=mid)
    except (OSError, KeyError, ValueError):
        peak = mid
    cuts = [tuple(c) for c in seg.get("remove") or []]
    return map_timestamp_to_trimmed(peak, seg["start_s"], cuts)


def render_concept_clip(
    *,
    concept: str,
    segs: List[Dict[str, Any]],
    overlay: Dict[str, Any],
    title: str,
    hook_text: str,
    video_dir: Path,
    meta: Dict[str, Any],
    cand_id: int,
    all_words: List[Dict[str, Any]],
    layout: str,
    caption_style: str,
    facecam_box: Optional[Dict[str, float]],
    profanity_mask: bool,
    letterbox_style: str,
    out_file: Path,
    thumb_file: Path,
) -> float:
    """Render a story, POV or countdown clip to out_file. Returns its length in seconds. Raises
    ConceptRenderError (or a section download error) when a piece cannot be made, leaving no half-made output."""
    if concept == "story":
        segs = sorted(segs, key=lambda s: s["start_s"])
    elif concept in TOP_RULES:
        segs = order_entries(segs)
    elif concept == "pov":
        segs = segs[:1]
    else:
        raise ConceptRenderError(f"{concept!r} is not a concept clip")
    if not segs:
        raise ConceptRenderError("a concept clip needs at least one segment")

    work = video_dir / "renders" / f"tmp_concept_{cand_id}_{uuid.uuid4().hex[:6]}"
    work.mkdir(parents=True, exist_ok=True)
    try:
        sections = [ensure_segment_section(video_dir, meta, cand_id, k, s["start_s"], s["end_s"]) for k, s in enumerate(segs)]
        # One layout for the whole clip, decided once
        layout, facecam_box = resolve_layout(layout, sections[0], facecam_box)

        def render_piece(k: int, name: str, hook: str = "", words_on: bool = True, events: Optional[List[Dict[str, Any]]] = None,
                         caption_y: Optional[float] = None) -> Path:
            seg, out = segs[k], work / f"{name}.mp4"
            ok = render_single_vertical_clip(
                sec_file=sections[k], out_file=out, thumb_file=work / f"{name}.jpg",
                clip_start=seg["start_s"], clip_end=seg["end_s"], layout=layout, caption_style=caption_style,
                hook_text=hook, all_words=all_words if words_on else [], facecam_box=facecam_box,
                profanity_mask=profanity_mask, silence_trim=False, letterbox_style=letterbox_style,
                title_text=hook, extra_cuts=[tuple(c) for c in seg.get("remove") or []], zooms=seg.get("zooms"),
                section_start_s=read_section_start(sections[k]), overlay_events=events, caption_y=caption_y,
            )
            if not ok or not out.exists():
                raise ConceptRenderError(f"segment {k + 1} failed to render")
            return out

        pieces: List[Path] = []
        thumb_at = 0.5
        elapsed = 0.0

        def add(p: Path) -> None:
            nonlocal elapsed
            pieces.append(p)
            elapsed += _duration(p)

        if concept == "pov":
            dur = segment_net_s(segs[0])
            only = render_piece(0, "pov", hook="", words_on=False, events=[
                {"start": 0, "end": dur + 1, "style": "pov", "text": overlay.get("pov_text", "")}])
            shutil.copyfile(only, out_file)       # one piece: it is already loudness-normalised
            if (work / "pov.jpg").exists():
                shutil.copyfile(work / "pov.jpg", thumb_file)
            return _duration(out_file)

        if concept == "story":
            first, last = 0, len(segs) - 1
            rendered: Dict[int, Path] = {}
            peak = _peak_in_piece(segs[last], video_dir)
            for k in range(len(segs)):
                events = None
                if k == last and overlay.get("callback_quote"):
                    events = [{"start": peak, "end": peak + CALLBACK_S, "style": "callback", "text": f"“{overlay['callback_quote']}”"}]
                rendered[k] = render_piece(k, f"seg{k}", hook=hook_text if k == first else "", events=events)
            if overlay.get("foreshadow"):
                add(cut_piece(rendered[last], work / "flash.mp4", peak - 0.2, FORESHADOW_S))
            for k in range(len(segs)):
                if k > 0:
                    add(make_card(overlay.get("skip_card") or "later", work / f"card{k}.mp4", work))
                if k == last:
                    thumb_at = elapsed + peak
                add(rendered[k])
        else:  # top3, top5: entries from #N down to #1, the list fills in as they play
            for k in range(len(segs)):
                if k == len(segs) - 1:
                    thumb_at = elapsed + _peak_in_piece(segs[k], video_dir)
                add(render_piece(k, f"entry{k}", events=ranking_overlay(title, meta.get("uploader") or "", segs, k),
                                 caption_y=RANK_CAPTION_Y))

        join_pieces(pieces, out_file, work)
        _ffmpeg(["-ss", f"{max(0.0, min(thumb_at, _duration(out_file) - 0.2)):.2f}", "-i", str(out_file), "-frames:v", "1", "-q:v", "2", str(thumb_file)])
        return _duration(out_file)
    finally:
        shutil.rmtree(work, ignore_errors=True)
