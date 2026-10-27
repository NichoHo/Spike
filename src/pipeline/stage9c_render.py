"""
Stage 9c: vertical render — Phase 2 vertical formatting and Phase 5 music & effects polish.
Blueprint §7: one ffmpeg call per clip.

Filter graph (all in native ffmpeg, zero Python frame piping):
  video: trim (with optional silence removal) → layout crop/scale → punch-in zoom → ASS captions (with hook text)
  audio: trim → music mix with speech-activated sidechain ducking (-22 dB baseline) → loudnorm (-14 LUFS, tp -1.5 dBTP)

Layouts (§7.1):
  face_track  – sendcmd dynamic crop following MediaPipe face centres
  auto        – split when a small fixed facecam is detected, else face_track
  split       – facecam (top 960px, auto-detected) + content crop (bottom 960px), captions on the seam
  center      – static centre crop
  letterbox   – full frame scaled to width. letterbox_style "title": white bars with the
                hook title above the video (title_card.py); "blur": blurred+zoomed fill

Effects (§7.4):
  Hook title    – optional, manual edits only (hook_text shown for the first 2.5 s at the top)
  Punch-in zoom – 1.0x to 1.15x over 0.3 s at the peak second, back out over 1 s. Once per clip.
  Loudness      – loudnorm to -14 LUFS, true peak -1.5 dBTP
  Pause cuts    – natural (>1.2 s) or tight (>0.6 s); every other segment zoomed 1.08x to hide jump cuts
  Music ducking – music sits at -22 dB, sidechaincompress ducks it further while speech is active

Output: data/videos/<id>/renders/clip_<cand_id>.mp4 (1080×1920, H.264, AAC 160k)
"""

from __future__ import annotations

import json
import logging
import os
import subprocess
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

from src.config import (
    DEFAULT_LAYOUT,
    FACE_DETECT_FPS,
    FACECAM_OVERLAY_MAX_FACE_W,
    HOOK_DURATION_S,
    JUMP_CUT_ZOOM,
    MUSIC_DIR,
    MUSIC_DUCK_ATTACK_MS,
    MUSIC_DUCK_RATIO,
    MUSIC_DUCK_RELEASE_MS,
    MUSIC_DUCK_THRESHOLD,
    MUSIC_UNDER_DB,
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
    SILENCE_TRIM_BREATH_S,
    SILENCE_TRIM_S,
    SILENCE_TRIM_TIGHT_BREATH_S,
    SILENCE_TRIM_TIGHT_S,
    SPLIT_FACECAM_H,
    SPLIT_GAMEPLAY_H,
    ZOOM_FACTOR,
    ZOOM_IN_DURATION,
    ZOOM_MAX,
    ZOOM_OUT_DURATION,
)
from src.db import create_or_update_clip, set_clip_layout_changes
from src.music import (
    get_random_track_for_mood,
    resolve_music_path,
)
from src.pipeline.stage9a_face_track import (
    detect_facecam,
    get_video_dimensions,
    speaker_at,
    track_faces,
)
from src.pipeline.stage9b_captions import _mask_profanity, generate_ass, slur_intervals, write_ass_file
from src.pipeline.title_card import render_title_card, strip_emoji

logger = logging.getLogger("spike.render")


# ── Relative path helper for ffmpeg filter options ────────────────────────────
# ffmpeg's filtergraph parser on Windows treats colons as option separators.
# Passing relative POSIX paths avoids drive colons and spaces.

def _to_rel_path(path: "str | Path") -> str:
    """Return a relative POSIX-style path from current working directory."""
    p = Path(path).resolve()
    try:
        return p.relative_to(Path.cwd().resolve()).as_posix()
    except ValueError:
        return os.path.relpath(str(p), start=os.getcwd()).replace("\\", "/")


# ── Silence Trim Helpers (Blueprint §7.4) ─────────────────────────────────────

def find_silence_cut_intervals(
    words: List[Dict[str, Any]],
    clip_start: float,
    clip_end: float,
    threshold_s: float = SILENCE_TRIM_S,
    keep_breath_s: Optional[float] = None,
) -> List[Tuple[float, float]]:
    """
    Find internal pauses between consecutive words longer than threshold_s (1.2 s).
    Returns list of (cut_start_s, cut_end_s) in absolute video timeline seconds.
    Leaves keep_breath_s natural breath duration after speech finishes: 0.4 s, or a third of a shorter threshold.
    """
    if keep_breath_s is None:
        keep_breath_s = min(SILENCE_TRIM_BREATH_S, threshold_s / 3)
    clip_words = [
        w for w in words
        if float(w.get("start", 0)) >= clip_start - 0.2 and float(w.get("end", 0)) <= clip_end + 0.2
    ]
    clip_words.sort(key=lambda w: float(w.get("start", 0)))
    if len(clip_words) < 2:
        return []

    cuts: List[Tuple[float, float]] = []
    for i in range(len(clip_words) - 1):
        w_curr_end = float(clip_words[i].get("end", 0))
        w_next_start = float(clip_words[i + 1].get("start", 0))
        pause_dur = w_next_start - w_curr_end

        if pause_dur > threshold_s:
            cut_start = w_curr_end + keep_breath_s
            cut_end = max(cut_start, w_next_start)
            # Only cut if the removable window is at least 0.2s
            if cut_end - cut_start >= 0.2:
                c_st = max(clip_start, min(clip_end, cut_start))
                c_et = max(clip_start, min(clip_end, cut_end))
                if c_et - c_st >= 0.2:
                    cuts.append((round(c_st, 3), round(c_et, 3)))

    return cuts


def read_section_start(sec_file: Path) -> Optional[float]:
    """Stream time at second 0 of a section file, from the sidecar stage 8 writes. None for older sections."""
    try:
        return float(json.loads(sec_file.with_suffix(".json").read_text(encoding="utf-8"))["start_s"])
    except (OSError, ValueError, KeyError):
        return None


MIN_KEEP_S = 0.75


def merge_cut_intervals(
    *cut_lists: Optional[List[Tuple[float, float]]],
    clip_start: float,
    clip_end: float,
) -> List[Tuple[float, float]]:
    """Union of several cut lists (silence trim, judge cut_lines, manual cuts), clamped to the clip and
    sorted without overlaps, as compute_keep_intervals expects."""
    spans = sorted(
        (max(clip_start, float(s)), min(clip_end, float(e)))
        for cuts in cut_lists for s, e in (cuts or [])
        if min(clip_end, float(e)) - max(clip_start, float(s)) >= 0.2
    )
    merged: List[List[float]] = []
    for s, e in spans:
        # A keep shorter than MIN_KEEP_S between two cuts is a sliver of breath or silence, not content: cut it too
        if merged and s - merged[-1][1] < MIN_KEEP_S:
            merged[-1][1] = max(merged[-1][1], e)
        else:
            merged.append([s, e])
    return [(round(s, 3), round(e, 3)) for s, e in merged]


def compute_keep_intervals(
    clip_start: float,
    clip_end: float,
    cut_intervals: List[Tuple[float, float]],
) -> List[Tuple[float, float]]:
    """Convert clip window and cut intervals into keep intervals."""
    if not cut_intervals:
        return [(clip_start, clip_end)]

    keeps: List[Tuple[float, float]] = []
    curr = clip_start
    for c_st, c_et in cut_intervals:
        if c_st > curr:
            keeps.append((curr, c_st))
        curr = max(curr, c_et)
    if curr < clip_end:
        keeps.append((curr, clip_end))

    return keeps


def map_timestamp_to_trimmed(
    t: float,
    clip_start: float,
    cut_intervals: List[Tuple[float, float]],
) -> float:
    """Map an absolute timestamp t to the trimmed clip timeline (seconds from 0.0)."""
    if t < clip_start:
        return 0.0

    offset = t - clip_start
    cut_acc = 0.0
    for c_st, c_et in cut_intervals:
        if t <= c_st:
            break
        elif t >= c_et:
            cut_acc += (c_et - c_st)
        else:
            cut_acc += (t - c_st)
            break

    return max(0.0, offset - cut_acc)


def retime_words_for_cuts(
    words: List[Dict[str, Any]],
    clip_start: float,
    clip_end: float,
    cut_intervals: List[Tuple[float, float]],
) -> List[Dict[str, Any]]:
    """Remap word timestamps to the new trimmed timeline."""
    if not cut_intervals:
        return words

    retimed: List[Dict[str, Any]] = []
    for w in words:
        w_st = float(w.get("start", 0))
        w_et = float(w.get("end", 0))
        # Skip words entirely engulfed in a cut
        if any(c_st <= w_st and w_et <= c_et for c_st, c_et in cut_intervals):
            continue

        new_st = clip_start + map_timestamp_to_trimmed(w_st, clip_start, cut_intervals)
        new_et = clip_start + map_timestamp_to_trimmed(w_et, clip_start, cut_intervals)
        new_w = dict(w)
        new_w["start"] = round(new_st, 3)
        new_w["end"] = round(max(new_st + 0.05, new_et), 3)
        retimed.append(new_w)

    return retimed


# ── sendcmd file builder for face_track ──────────────────────────────────────

def _build_sendcmd_file(
    keyframes: List[Dict[str, Any]],
    src_w: int,
    src_h: int,
) -> str:
    """Build an ffmpeg sendcmd script for dynamic crop following face centres."""
    if not keyframes:
        return ""
    lines = []
    for kf in keyframes:
        t = kf["t_s"]
        cx = kf["cx_px"]
        cy = kf["cy_px"]
        cw = kf.get("crop_w_px", OUTPUT_WIDTH)
        ch = kf.get("crop_h_px", OUTPUT_HEIGHT)
        x = max(0, cx - cw / 2)
        y = max(0, cy - ch / 2)
        x = min(x, max(0, src_w - cw))
        y = min(y, max(0, src_h - ch))
        lines.append(f"{t:.3f} crop@ft x {int(x)};")
        lines.append(f"{t:.3f} crop@ft y {int(y)};")
    return "\n".join(lines) + "\n"


# ── Effect helpers ────────────────────────────────────────────────────────────

def _smoothstep(x: str) -> str:
    return f"(({x})*({x})*(3-2*({x})))"


def _zoom_expr(zooms: List[Dict[str, float]]) -> str:
    """
    zoompan 'z' expression: 1.0 plus the sum of eased pulses. Each pulse ramps up over ZOOM_IN_DURATION,
    holds for hold_s, then ramps down over ZOOM_OUT_DURATION. `t` is on the trimmed clip timeline.
    In zoompan, the input frame index variable is 'in'. No zooms gives "1.0".
    """
    f_in = max(1, round(OUTPUT_FPS * ZOOM_IN_DURATION))
    f_out = max(1, round(OUTPUT_FPS * ZOOM_OUT_DURATION))
    terms = []
    for z in zooms:
        f0 = int(z["t"] * OUTPUT_FPS)
        f1 = f0 + f_in
        f2 = f1 + max(0, int(z["hold_s"] * OUTPUT_FPS))
        f3 = f2 + f_out
        env = (
            f"if(lt(in,{f0}),0,if(lt(in,{f1}),{_smoothstep(f'(in-{f0})/{f_in}')},"
            f"if(lt(in,{f2}),1,if(lt(in,{f3}),{_smoothstep(f'1-(in-{f2})/{f_out}')},0))))"
        )
        terms.append(f"{float(z['scale']) - 1.0:.3f}*{env}")
    return f"min({ZOOM_MAX},1.0+{'+'.join(terms)})" if terms else "1.0"


def _zoompan(z_expr: str, w: int, h: int) -> str:
    """Zoom about the centre of the frame. Layouts put the face there (face_track follows it, split crops
    the facecam around it), so the zoom lands on the face."""
    return (f"zoompan=z='{z_expr}':x='iw/2-(iw/zoom/2)':y='ih/2-(ih/zoom/2)':d=1:fps={OUTPUT_FPS}:s={w}x{h}")


def default_zooms(sec_file: Path, clip_start: float, clip_end: float, payoff_t: Optional[float]) -> List[Dict[str, float]]:
    """One zoom for clips that have no zoom list yet: at the payoff, else the loudest voice-jump second."""
    t = payoff_t if payoff_t is not None and clip_start <= payoff_t <= clip_end else None
    if t is None:
        npz = sec_file.parent.parent / "signals.npz"
        try:
            import numpy as np
            jump = np.load(npz)["voice_jump"]
            a, b = int(clip_start), min(len(jump), int(clip_end) + 1)
            if b > a and jump[a:b].max() > 0:
                t = float(a + int(jump[a:b].argmax()))
        except Exception:
            t = None
    return [{"t": round(t, 2), "scale": ZOOM_FACTOR, "hold_s": 1.5}] if t is not None else []


def resolve_layout(
    layout: str,
    sec_file: Path,
    facecam_box: Optional[Dict[str, float]] = None,
    ai: bool = True,
) -> Tuple[str, Optional[Dict[str, float]]]:
    """
    Turn "auto" into a concrete layout and find the facecam for split.
    auto = a Gemini vision pick of any layout (src/layout_ai.py), unless ai is False. Without it, split when
    a small face stays put (a facecam overlay on gameplay or a video), otherwise face_track.
    """
    if layout not in ("auto", "split") or facecam_box:
        return layout, facecam_box
    if layout == "auto" and ai:
        from src.layout_ai import choose_layout
        picked = choose_layout(sec_file)
        if picked and picked != "split":
            return picked, None
        if picked == "split":
            cam = detect_facecam(sec_file)
            if cam:
                return "split", cam
            # no facecam found to crop: fall through to the heuristic below
    cam = detect_facecam(sec_file)
    if layout == "split":
        return "split", cam
    # ponytail: face-width threshold, swap for a real overlay-rectangle detector if it misjudges
    if cam and cam["w"] < FACECAM_OVERLAY_MAX_FACE_W:
        return "split", cam
    return "face_track", None


def _retime_keyframes(
    keyframes: List[Dict[str, Any]],
    sec_start: float,
    clip_start: float,
    cut_intervals: List[Tuple[float, float]],
) -> List[Dict[str, Any]]:
    """Face keyframes are timed from the section start; move them onto the trimmed clip timeline."""
    out: List[Dict[str, Any]] = []
    for kf in keyframes:
        t_abs = sec_start + kf["t_s"]
        if t_abs < clip_start:
            out = [dict(kf, t_s=0.0)]  # last position before the clip starts becomes the opening frame
            continue
        if any(c_st <= t_abs < c_et for c_st, c_et in cut_intervals):
            continue
        out.append(dict(kf, t_s=round(map_timestamp_to_trimmed(t_abs, clip_start, cut_intervals), 3)))
    return out or keyframes


def _jump_cut_zoom_expr(keep_intervals: List[Tuple[float, float]]) -> str:
    """zoompan 'z' term: every other kept segment sits at JUMP_CUT_ZOOM, so each cut changes framing."""
    terms, t = [], 0.0
    for idx, (k_st, k_et) in enumerate(keep_intervals):
        f0, t = int(t * OUTPUT_FPS), t + (k_et - k_st)
        if idx % 2 == 1:
            terms.append(f"between(in,{f0},{int(t * OUTPUT_FPS) - 1})")
    if not terms:
        return "1.0"
    return f"1.0+{JUMP_CUT_ZOOM - 1.0:.3f}*({'+'.join(terms)})"


def split_crops(
    facecam: Optional[Dict[str, float]],
    src_w: int,
    src_h: int,
) -> Tuple[Tuple[int, int, int, int], Tuple[int, int, int, int]]:
    """
    Source crop rectangles (x, y, w, h) for the split layout: (top facecam, bottom content).

    facecam is either a detected face {cx, cy, w, box} or a manual box {x, y, w, h} (all 0..1).
    Top: a box around the face, about 2.7x the face width, matching the top panel's shape,
    with the face a little above centre, kept inside the cam border (box) when one was found.
    Bottom: full-height content crop matching the bottom panel's shape, pushed away from
    the facecam's side so the cam does not show twice.
    """
    top_aspect = OUTPUT_WIDTH / SPLIT_FACECAM_H
    bot_aspect = OUTPUT_WIDTH / SPLIT_GAMEPLAY_H

    if facecam and "h" in facecam:  # manual box from source settings
        fc_w, fc_h = facecam["w"] * src_w, facecam["h"] * src_h
        fc_cx, fc_cy = facecam["x"] * src_w + fc_w / 2, facecam["y"] * src_h + fc_h / 2
        # widen or heighten to the panel shape around the box centre
        fc_w, fc_h = max(fc_w, fc_h * top_aspect), max(fc_h, fc_w / top_aspect)
    elif facecam:
        fc_cx, fc_cy = facecam["cx"] * src_w, facecam["cy"] * src_h
        fc_w = facecam["w"] * src_w * 2.7
        fc_h = fc_w / top_aspect
        fc_cy += fc_h * 0.15
    else:  # no facecam found: top shows the centre of the frame
        fc_cx, fc_cy, fc_h = src_w / 2, src_h / 2, src_h * 0.6
        fc_w = fc_h * top_aspect

    bx0, by0, bx1, by1 = (0, 0, src_w, src_h)
    if facecam and facecam.get("box"):
        b = facecam["box"]
        bx0, by0, bx1, by1 = b[0] * src_w, b[1] * src_h, b[2] * src_w, b[3] * src_h
    # shrink to fit inside the cam border, keeping the panel shape
    scale = min(1.0, (bx1 - bx0) / fc_w, (by1 - by0) / fc_h)
    fc_w, fc_h = fc_w * scale, fc_h * scale
    fc_x = int(max(bx0, min(bx1 - fc_w, fc_cx - fc_w / 2)))
    fc_y = int(max(by0, min(by1 - fc_h, fc_cy - fc_h / 2)))

    gp_h = src_h
    gp_w = min(src_w, int(gp_h * bot_aspect))
    gp_x = (src_w - gp_w) / 2
    if facecam:
        if fc_cx < src_w / 2:
            gp_x = max(gp_x, max(fc_x + fc_w, bx1 if bx1 < src_w else 0))
        else:
            gp_x = min(gp_x, min(fc_x, bx0 if bx0 > 0 else src_w) - gp_w)
    gp_x = int(max(0, min(src_w - gp_w, gp_x)))

    even = lambda v: int(v) // 2 * 2
    return (fc_x, fc_y, even(fc_w), even(fc_h)), (gp_x, 0, even(gp_w), even(gp_h))


SWITCH_LAYOUTS = ("split", "face_track", "center", "letterbox")


def layout_segments_for(
    base_layout: str,
    layout_changes: Optional[List[Dict[str, Any]]],
    clip_start: float,
    clip_end: float,
    cut_intervals: List[Tuple[float, float]],
) -> List[Tuple[float, str]]:
    """
    Turn user layout switches ({t: source seconds, layout}) into (start on the trimmed
    clip timeline, layout) segments. Drops switches outside the clip, merges repeats,
    and lets a switch within 0.2 s of the previous one replace it.
    """
    segs: List[Tuple[float, str]] = [(0.0, base_layout)]
    for ch in sorted(layout_changes or [], key=lambda c: float(c["t"])):
        t, lay = float(ch["t"]), ch.get("layout")
        if lay not in SWITCH_LAYOUTS or not clip_start < t < clip_end:
            continue
        t_out = round(map_timestamp_to_trimmed(t, clip_start, cut_intervals), 3)
        if t_out - segs[-1][0] < 0.2:
            segs[-1] = (segs[-1][0], lay)
        else:
            segs.append((t_out, lay))
    merged = [segs[0]]
    for seg in segs[1:]:
        if seg[1] != merged[-1][1]:
            merged.append(seg)
    return merged


def _layout_filters(
    layout: str,
    src: str,
    dst: str,
    src_w: int,
    src_h: int,
    keyframes: Optional[List[Dict[str, Any]]],
    sc_rel: Optional[str],
    facecam_box: Optional[Dict[str, float]],
    letterbox_style: str = "blur",
    zoom_z: str = "",
) -> List[str]:
    """Filters turning [src] into a 1080x1920 [dst] for one layout. zoom_z is a zoompan 'z' expression
    ("" for none): split zooms only the facecam panel, every other layout zooms the whole frame."""
    if zoom_z and layout != "split":
        inner = _layout_filters(layout, src, f"{dst}_nz", src_w, src_h, keyframes, sc_rel, facecam_box, letterbox_style)
        return inner + [f"[{dst}_nz]{_zoompan(zoom_z, OUTPUT_WIDTH, OUTPUT_HEIGHT)}[{dst}]"]
    if layout == "face_track" and sc_rel:
        first_kf = keyframes[0] if keyframes else {
            "cx_px": src_w / 2, "cy_px": src_h / 2, "crop_w_px": src_w, "crop_h_px": src_h
        }
        cw = int(first_kf.get("crop_w_px", src_w))
        ch = int(first_kf.get("crop_h_px", src_h))
        init_x = int(max(0, first_kf["cx_px"] - cw / 2))
        init_y = int(max(0, first_kf["cy_px"] - ch / 2))
        # Named crop so sendcmd only moves this one, not the split layout's crops
        return [
            f"[{src}]crop@ft={cw}:{ch}:{init_x}:{init_y},sendcmd=f={sc_rel},"
            f"scale={OUTPUT_WIDTH}:{OUTPUT_HEIGHT}:force_original_aspect_ratio=decrease,"
            f"pad={OUTPUT_WIDTH}:{OUTPUT_HEIGHT}:(ow-iw)/2:(oh-ih)/2,setsar=1[{dst}]"
        ]
    if layout == "split":
        (fc_x, fc_y, fc_w, fc_h), (gp_x, gp_y, gp_w, gp_h) = split_crops(facecam_box, src_w, src_h)
        return [
            f"[{src}]split=2[fc_in][gp_in]",
            f"[fc_in]crop={fc_w}:{fc_h}:{fc_x}:{fc_y},scale={OUTPUT_WIDTH}:{SPLIT_FACECAM_H},setsar=1[facecam{'_nz' if zoom_z else ''}]",
            *([f"[facecam_nz]{_zoompan(zoom_z, OUTPUT_WIDTH, SPLIT_FACECAM_H)}[facecam]"] if zoom_z else []),
            f"[gp_in]crop={gp_w}:{gp_h}:{gp_x}:{gp_y},scale={OUTPUT_WIDTH}:{SPLIT_GAMEPLAY_H},setsar=1[gameplay]",
            f"[facecam][gameplay]vstack=inputs=2[{dst}]",
        ]
    if layout == "letterbox" and letterbox_style == "title":  # title card is overlaid after the zoom
        return [
            f"[{src}]scale={OUTPUT_WIDTH}:{OUTPUT_HEIGHT}:force_original_aspect_ratio=decrease,"
            f"pad={OUTPUT_WIDTH}:{OUTPUT_HEIGHT}:(ow-iw)/2:(oh-ih)/2:color=white,setsar=1[{dst}]"
        ]
    if layout == "letterbox":
        return [
            f"[{src}]split=2[bg_in][fg_in]",
            f"[bg_in]scale={OUTPUT_WIDTH}:{OUTPUT_HEIGHT}:force_original_aspect_ratio=increase,crop={OUTPUT_WIDTH}:{OUTPUT_HEIGHT},boxblur=20:5,setsar=1[bg]",
            f"[fg_in]scale={OUTPUT_WIDTH}:-1,setsar=1[fg]",
            f"[bg][fg]overlay=(W-w)/2:(H-h)/2[{dst}]",
        ]
    # center
    crop_h = src_h
    crop_w = int(src_h * OUTPUT_WIDTH / OUTPUT_HEIGHT)
    if crop_w > src_w:
        crop_w = src_w
        crop_h = int(src_w * OUTPUT_HEIGHT / OUTPUT_WIDTH)
    cx = int((src_w - crop_w) / 2)
    cy = int((src_h - crop_h) / 2)
    return [f"[{src}]crop={crop_w}:{crop_h}:{cx}:{cy},scale={OUTPUT_WIDTH}:{OUTPUT_HEIGHT},setsar=1[{dst}]"]


# ── Unified Filtergraph Builder ───────────────────────────────────────────────

def build_vertical_filtergraph(
    sec_start: float,
    keep_intervals: List[Tuple[float, float]],
    layout: str,
    src_w: int,
    src_h: int,
    effective_dur: float,
    ass_rel: str,
    keyframes: Optional[List[Dict[str, Any]]] = None,
    sc_rel: Optional[str] = None,
    facecam_box: Optional[Dict[str, float]] = None,
    zooms: Optional[List[Dict[str, float]]] = None,
    has_music: bool = False,
    layout_segments: Optional[List[Tuple[float, str]]] = None,
    letterbox_style: str = "blur",
    title_input: Optional[int] = None,
    bleeps: Optional[List[Tuple[float, float]]] = None,
) -> str:
    """
    Build complete native FFmpeg filtergraph:
    1. Trims and optional silence removal (via trim/atrim + concat)
    2. Layout transformation (face_track, split, center, letterbox)
    3. Punch-in zooms (eased pulses from the clip's zoom list, inside the layout step)
    4. ASS captions overlay (including hook title event)
    5. Speech-ducked music mix (at -22 dB baseline, ducked via sidechaincompress)
    6. EBU R128 loudness normalization (-14 LUFS, -1.5 dBTP)
    """
    filters: List[str] = []

    # 1. Trimming & Keep Interval Concatenation
    k_count = len(keep_intervals)
    if k_count > 1:
        for idx, (k_st, k_et) in enumerate(keep_intervals):
            in_sec_start = max(0.0, k_st - sec_start)
            dur = max(0.1, k_et - k_st)
            filters.append(
                f"[0:v]trim=start={in_sec_start:.3f}:end={in_sec_start + dur:.3f},setpts=PTS-STARTPTS,fps={OUTPUT_FPS}[v_raw_{idx}]"
            )
            filters.append(
                f"[0:a]atrim=start={in_sec_start:.3f}:end={in_sec_start + dur:.3f},asetpts=PTS-STARTPTS[a_raw_{idx}]"
            )
        concat_inputs = "".join(f"[v_raw_{idx}][a_raw_{idx}]" for idx in range(k_count))
        filters.append(f"{concat_inputs}concat=n={k_count}:v=1:a=1[v_cat][a_trimmed]")
        # concat leaves off-by-a-tick timestamps; without re-snapping, vstack (split) emits near-duplicate frames
        # and the jump-cut zoompan plays them all, so the video runs longer than the audio
        filters.append(f"[v_cat]fps={OUTPUT_FPS}[v_trimmed]")
    else:
        k_st, k_et = keep_intervals[0]
        in_sec_start = max(0.0, k_st - sec_start)
        dur = max(0.1, k_et - k_st)
        filters.append(
            f"[0:v]trim=start={in_sec_start:.3f}:end={in_sec_start + dur:.3f},setpts=PTS-STARTPTS,fps={OUTPUT_FPS}[v_trimmed]"
        )
        filters.append(
            f"[0:a]atrim=start={in_sec_start:.3f}:end={in_sec_start + dur:.3f},asetpts=PTS-STARTPTS[a_trimmed]"
        )

    # 2. Layout Transformation. With layout switches, each layout used runs over the whole
    # trimmed clip, then each segment is cut from its layout's output and the pieces joined.
    segments = layout_segments or [(0.0, layout)]
    lay_args = (src_w, src_h, keyframes, sc_rel, facecam_box, letterbox_style, _zoom_expr(zooms) if zooms else "")
    if len(segments) == 1:
        filters += _layout_filters(segments[0][1], "v_trimmed", "v_layout", *lay_args)
    else:
        used = list(dict.fromkeys(lay for _, lay in segments))
        filters.append(f"[v_trimmed]split={len(used)}" + "".join(f"[lin_{lay}]" for lay in used))
        for lay in used:
            filters += _layout_filters(lay, f"lin_{lay}", f"lout_{lay}", *lay_args)
            idxs = [i for i, (_, l) in enumerate(segments) if l == lay]
            filters.append(f"[lout_{lay}]split={len(idxs)}" + "".join(f"[lseg_{i}]" for i in idxs))
        for i, (t0, _) in enumerate(segments):
            end = f":end={segments[i + 1][0]:.3f}" if i + 1 < len(segments) else ""
            filters.append(f"[lseg_{i}]trim=start={t0:.3f}{end},setpts=PTS-STARTPTS,setsar=1[lp_{i}]")
        filters.append("".join(f"[lp_{i}]" for i in range(len(segments))) + f"concat=n={len(segments)}:v=1:a=0[v_layout]")

    # 3. A small zoom on every other kept segment so jump cuts read as edits (the punch-in zooms are in the layout step)
    if k_count > 1:
        filters.append(
            f"[v_layout]zoompan=z='{_jump_cut_zoom_expr(keep_intervals)}':x='iw/2-(iw/zoom/2)':y='ih/2-(ih/zoom/2)'"
            f":d=1:fps={OUTPUT_FPS}:s={OUTPUT_WIDTH}x{OUTPUT_HEIGHT}[v_zoomed]"
        )
    else:
        filters.append("[v_layout]null[v_zoomed]")

    # 4. Letterbox title card (after the zoom so the punch-in never crops it), then ASS captions
    if title_input is not None:
        spans = [
            (t0, segments[i + 1][0] if i + 1 < len(segments) else None)
            for i, (t0, lay) in enumerate(segments) if lay == "letterbox"
        ]
        enable = ""
        if len(segments) > 1:
            terms = [f"gte(t,{a:.3f})" if b is None else f"between(t,{a:.3f},{b:.3f})" for a, b in spans]
            enable = f":enable='{'+'.join(terms)}'"
        filters.append(f"[v_zoomed][{title_input}:v]overlay=0:0{enable}[v_titled]")
        filters.append(f"[v_titled]ass={ass_rel}[vout]")
    else:
        filters.append(f"[v_zoomed]ass={ass_rel}[vout]")

    # 5. Bleep slurs: mute the word and lay a generated 1 kHz sine over it (synthesized, so no licensing to track)
    a_in = "a_trimmed"
    if bleeps:
        gate = "+".join(f"between(t,{a:.3f},{b:.3f})" for a, b in bleeps)
        filters += [
            f"[a_trimmed]volume=enable='{gate}':volume=0[a_muted]",
            f"aevalsrc='0.3*sin(2*PI*1000*t)*min(1,{gate})':s=48000:d={effective_dur:.3f}[a_tone]",
            "[a_muted][a_tone]amix=inputs=2:duration=first:normalize=0[a_bleeped]",
        ]
        a_in = "a_bleeped"

    # 6. Audio Processing & Ducking
    if has_music:
        base_vol = 10.0 ** (MUSIC_UNDER_DB / 20.0)  # ~0.0794 (-22 dB)
        filters.append(f"[1:a]atrim=start=0:end={effective_dur:.3f},asetpts=PTS-STARTPTS,volume={base_vol:.4f}[bgm_base]")
        filters.append(f"[{a_in}]asplit=2[sp_main][sp_key]")
        filters.append(
            f"[bgm_base][sp_key]sidechaincompress=threshold={MUSIC_DUCK_THRESHOLD}:ratio={MUSIC_DUCK_RATIO}:"
            f"attack={MUSIC_DUCK_ATTACK_MS}:release={MUSIC_DUCK_RELEASE_MS}:detection=rms[bgm_duck]"
        )
        filters.append(f"[sp_main][bgm_duck]amix=inputs=2:duration=first:dropout_transition=2[a_mixed]")
        filters.append(f"[a_mixed]loudnorm=I={OUTPUT_LOUDNESS_TARGET}:TP={OUTPUT_LOUDNESS_PEAK}:LRA=11,aresample=48000[aout]")
    else:
        filters.append(f"[{a_in}]loudnorm=I={OUTPUT_LOUDNESS_TARGET}:TP={OUTPUT_LOUDNESS_PEAK}:LRA=11,aresample=48000[aout]")

    return ";".join(filters)


def _render_center_fallback(
    sec_file: Path,
    out_file: Path,
    ss: str,
    t: str,
    ass_rel_path: str,
) -> None:
    """Minimal fallback: center crop + captions, single-pass loudnorm."""
    cmd = [
        "ffmpeg", "-y", "-hide_banner", "-loglevel", "error",
        "-ss", ss, "-t", t,
        "-i", str(sec_file),
        "-vf", (
            f"crop=ih*{OUTPUT_WIDTH}/{OUTPUT_HEIGHT}:ih:(iw-ih*{OUTPUT_WIDTH}/{OUTPUT_HEIGHT})/2:0,"
            f"scale={OUTPUT_WIDTH}:{OUTPUT_HEIGHT}:force_original_aspect_ratio=decrease,"
            f"pad={OUTPUT_WIDTH}:{OUTPUT_HEIGHT}:(ow-iw)/2:(oh-ih)/2,setsar=1,"
            f"ass={ass_rel_path}"
        ),
        "-af", f"loudnorm=I={OUTPUT_LOUDNESS_TARGET}:TP={OUTPUT_LOUDNESS_PEAK}:LRA=11,aresample=48000",
        "-c:v", OUTPUT_VIDEO_CODEC,
        "-preset", OUTPUT_VIDEO_PRESET,
        "-crf", str(OUTPUT_VIDEO_CRF),
        "-c:a", OUTPUT_AUDIO_CODEC,
        "-b:a", OUTPUT_AUDIO_BITRATE,
        "-r", str(OUTPUT_FPS),
        "-pix_fmt", "yuv420p",
        "-movflags", "+faststart",
        str(out_file),
    ]
    subprocess.run(cmd, check=False)


# ── Main Vertical Render Function ─────────────────────────────────────────────

def _render_concept_candidate(cand, cand_id, video_dir, sec_file, all_words, layout, facecam_box, caption_style,
                              profanity_mask, letterbox_style, out_file, thumb_file, rendered) -> None:
    """Story, POV and countdown clips: the concept renderer makes the file, the clip row records the concept."""
    from src.concepts import stored_segments
    from src.pipeline.concept_render import render_concept_clip

    meta = json.loads((video_dir / "meta.json").read_text(encoding="utf-8"))
    clip_layout, clip_facecam = resolve_layout(layout, sec_file, facecam_box)
    try:
        duration = render_concept_clip(
            concept=cand["concept"], segs=cand["segs"], overlay=cand.get("overlay") or {}, title=cand.get("title") or "",
            hook_text=cand.get("hook_text") or "", video_dir=video_dir, meta=meta, cand_id=cand_id, all_words=all_words,
            layout=clip_layout, caption_style=caption_style, facecam_box=clip_facecam, profanity_mask=profanity_mask,
            letterbox_style=letterbox_style, out_file=out_file, thumb_file=thumb_file,
        )
    except Exception as e:
        print(f"  [stage 9c] {cand['concept']} clip {cand_id} failed: {e}")
        return
    cand["trim_start_s"], cand["trim_end_s"] = 0.0, duration
    cand["layout"], cand["caption_style"] = clip_layout, caption_style
    cand["render_file"], cand["thumbnail_file"] = str(out_file), str(thumb_file)
    rendered.append(out_file)
    try:
        create_or_update_clip(
            candidate_id=cand_id, file_path=str(out_file), thumb_path=str(thumb_file), layout=clip_layout,
            caption_style=caption_style, trim_start_s=0.0, trim_end_s=duration, status="ready",
            letterbox_style=letterbox_style, cuts="[]", zooms="[]", concept=cand["concept"],
            segments=json.dumps(stored_segments(cand["segs"])), overlay=json.dumps(cand.get("overlay") or {}),
            theme=cand.get("theme") or "", concept_source=(cand.get("concept_source") or "ai"),
        )
    except Exception as e:
        logger.warning(f"Failed to record clip in DB: {e}")


def run_stage9c_render(
    video_dir: Path,
    candidates: List[Dict[str, Any]],
    transcript: Dict[str, Any],
    source_settings: Optional[Dict[str, Any]] = None,
    update_candidates_json: bool = True,
) -> List[Path]:
    """
    Phase 2 & Phase 5 vertical render:
    - 9:16 reframing (auto, face_track, split, center, letterbox)
    - Word-by-word captions (optional)
    - Pause cutting: off, natural (>1.2 s) or tight (>0.6 s)
    - Speech-activated audio ducking for background music (-22 dB baseline)
    - Two-pass or integrated EBU R128 loudness normalization (-14 LUFS)

    "auto" settings (music, cut_pauses) use the LLM judge's per-clip pick
    (cand["music"], cand["pace"]) from stage 7.
    """
    renders_dir = video_dir / "renders"
    renders_dir.mkdir(exist_ok=True)

    src_settings = source_settings or {}
    layout = src_settings.get("layout", DEFAULT_LAYOUT)
    caption_style = src_settings.get("caption_style", "bold_pop")
    captions_on = bool(src_settings.get("captions", True))
    profanity_mask = bool(src_settings.get("profanity_mask", True))
    facecam_box = src_settings.get("facecam_box")
    if isinstance(facecam_box, str):
        facecam_box = json.loads(facecam_box) if facecam_box.strip() else None

    music_setting = src_settings.get("music", "auto")  # True, False or "auto"
    default_mood = src_settings.get("default_music_mood", "chill")
    # Sources store a legacy on/off silence_trim; jobs store cut_pauses
    if "cut_pauses" in src_settings:
        cut_setting = src_settings["cut_pauses"]
    elif "silence_trim" in src_settings:
        cut_setting = "natural" if src_settings["silence_trim"] else "off"
    else:
        cut_setting = "auto"
    letterbox_style = src_settings.get("letterbox_style", "title")

    all_words = []
    for seg in transcript.get("segments", []):
        all_words.extend(seg.get("words", []))

    rendered: List[Path] = []

    for idx, cand in enumerate(candidates, 1):
        cand_id = cand.get("id") or idx
        out_file = renders_dir / f"clip_{cand_id}.mp4"
        thumb_file = renders_dir / f"clip_{cand_id}_thumb.jpg"

        if out_file.exists() and out_file.stat().st_size > 1000:
            print(f"  [stage 9c] Resuming: found renders/clip_{cand_id}.mp4")
            cand["render_file"] = str(out_file)
            if thumb_file.exists():
                cand["thumbnail_file"] = str(thumb_file)
            rendered.append(out_file)
            continue

        sec_file_str = cand.get("section_file")
        if not sec_file_str or not Path(sec_file_str).exists():
            print(f"  [stage 9c] Error: no section file for candidate {cand_id}, skipping.")
            continue

        sec_file = Path(sec_file_str)
        if cand.get("segs") and cand.get("concept", "single") != "single":
            _render_concept_candidate(cand, cand_id, video_dir, sec_file, all_words, layout, facecam_box, caption_style,
                                      profanity_mask, letterbox_style, out_file, thumb_file, rendered)
            continue
        clip_start = float(cand["start_s"])
        clip_end = float(cand["end_s"])
        cand_words = all_words
        cand["trim_start_s"], cand["trim_end_s"] = clip_start, clip_end
        # Per-clip choices: an explicit setting wins, "auto" follows the judge
        # "auto" plans the layout per moment: the opening layout plus mid-clip switches (a streamer who goes
        # from a facecam overlay to full-screen). A failed plan falls back to the face-size heuristic.
        base_layout, layout_changes, plan = layout, None, None
        if layout == "auto":
            from src.layout_ai import plan_layouts
            plan = plan_layouts(sec_file, clip_start, clip_end, read_section_start(sec_file), cand_words)
            if plan:
                base_layout, layout_changes = plan[0]["layout"], plan[1:]
        clip_layout, clip_facecam = resolve_layout(base_layout, sec_file, facecam_box, ai=layout != "auto")
        pace = (cand.get("pace") or "natural") if cut_setting == "auto" else cut_setting
        use_music = cand.get("music", True) if music_setting == "auto" else bool(music_setting)
        cand["layout"], cand["caption_style"] = clip_layout, caption_style  # runner re-registers clips from these

        chosen_track_path: Optional[Path] = None
        if use_music:
            # The judge's pick from the catalogue, else a random track of the clip's mood
            chosen_track_path = (
                resolve_music_path(cand["music_track"]) if cand.get("music_track") else None
            ) or get_random_track_for_mood(cand.get("mood") or default_mood)

        success = render_single_vertical_clip(
            sec_file=sec_file,
            out_file=out_file,
            thumb_file=thumb_file,
            clip_start=clip_start,
            clip_end=clip_end,
            layout=clip_layout,
            caption_style=caption_style,
            all_words=cand_words if captions_on else [],
            facecam_box=clip_facecam,
            profanity_mask=profanity_mask,
            music_track=str(chosen_track_path) if chosen_track_path else None,
            silence_trim=pace,
            letterbox_style=letterbox_style,
            title_text=cand.get("hook_text") or cand.get("title") or "",
            extra_cuts=cand.get("cuts"),
            zooms=cand.get("zooms"),
            payoff_t=cand.get("payoff_t"),
            section_start_s=read_section_start(sec_file),
            layout_changes=layout_changes,
        )

        if success and out_file.exists():
            cand["render_file"] = str(out_file)
            cand["thumbnail_file"] = str(thumb_file)
            rendered.append(out_file)

            # Record into database clips table
            try:
                music_str = _to_rel_path(chosen_track_path) if chosen_track_path else None
                clip_id = create_or_update_clip(
                    candidate_id=cand_id,
                    file_path=str(out_file),
                    thumb_path=str(thumb_file),
                    layout=clip_layout,
                    caption_style=caption_style,
                    trim_start_s=clip_start,
                    trim_end_s=clip_end,
                    music_track=music_str,
                    silence_trim=0 if pace == "off" else 1,
                    silence_trim_s=SILENCE_TRIM_TIGHT_S if pace == "tight" else None,
                    status="ready",
                    letterbox_style=letterbox_style,
                    cuts=json.dumps(cand.get("cuts") or []),
                    zooms=json.dumps(cand.get("zooms") or []),
                )
                cand["clip_id"] = clip_id
                if layout_changes:  # the review editor shows and edits these like hand-made switches
                    set_clip_layout_changes(clip_id, json.dumps(layout_changes))
            except Exception as e:
                logger.warning(f"Failed to record clip in DB: {e}")

    # Update candidates.json
    cand_file = video_dir / "candidates.json"
    if update_candidates_json and cand_file.exists():
        try:
            cand_file.write_text(json.dumps(candidates, indent=2), encoding="utf-8")
        except Exception:
            pass

    print(f"  [stage 9c] Vertical render complete: {len(rendered)} clips in {renders_dir}")
    return rendered


# ── Interactive Single-Clip Re-Renderer ───────────────────────────────────────

def render_single_vertical_clip(
    sec_file: Path,
    out_file: Path,
    thumb_file: Path,
    clip_start: float,
    clip_end: float,
    layout: str = "split",
    caption_style: str = "bold_pop",
    hook_text: str = "",
    all_words: Optional[List[Dict[str, Any]]] = None,
    facecam_box: Optional[Dict[str, float]] = None,
    caption_y: Optional[float] = None,
    profanity_mask: bool = True,
    music_track: Optional[str] = None,
    silence_trim: "bool | str" = False,
    silence_trim_s: Optional[float] = None,
    punch_in_zoom: Optional[bool] = None,
    layout_changes: Optional[List[Dict[str, Any]]] = None,
    letterbox_style: str = "blur",
    title_text: str = "",
    extra_cuts: Optional[List[Tuple[float, float]]] = None,
    zooms: Optional[List[Dict[str, float]]] = None,
    payoff_t: Optional[float] = None,
    section_start_s: Optional[float] = None,
    overlay_events: Optional[List[Dict[str, Any]]] = None,
) -> bool:
    """
    Renders a single vertical clip from a downloaded section video file.
    Supports interactive adjustments to trims, layout, captions, music, silence trim, and zoom.
    silence_trim: False/"off", True/"natural" (cut pauses > 1.2 s, or > silence_trim_s) or "tight" (> 0.6 s).
    caption_y: None places captions on the split seam, or at 68% height for other layouts.
    layout_changes: [{t, layout}] switches at source seconds, for streams that change
    mid-clip (e.g. a reaction ends and the streamer goes full-cam).
    letterbox_style: "title" draws title_text above the video on white bars while
    letterbox shows; "blur" keeps the blurred fill. The title card replaces the 2.5 s hook.
    """
    if not sec_file.exists():
        print(f"  [stage 9c] Error: section file {sec_file} does not exist.")
        return False

    out_file.parent.mkdir(parents=True, exist_ok=True)
    thumb_file.parent.mkdir(parents=True, exist_ok=True)

    words = all_words or []
    clip_dur = max(1.0, clip_end - clip_start)
    # Stream time at second 0 of the section file. Stage 8 records it next to the section, because trims and
    # AI edits move clip_start away from the original start. Without it, assume 5 s of padding before clip_start.
    sec_start = section_start_s if section_start_s is not None else clip_start - (5.0 if clip_start >= 5.0 else clip_start)
    section_clip_offset = clip_start - sec_start

    layout, facecam_box = resolve_layout(layout, sec_file, facecam_box)

    # 1. Silence trimming calculation
    pace = {True: "natural", False: "off"}.get(silence_trim, silence_trim)
    cut_intervals: List[Tuple[float, float]] = []
    if pace == "tight":
        cut_intervals = find_silence_cut_intervals(
            words, clip_start, clip_end, SILENCE_TRIM_TIGHT_S, SILENCE_TRIM_TIGHT_BREATH_S
        )
    elif pace == "natural":
        cut_intervals = find_silence_cut_intervals(words, clip_start, clip_end, silence_trim_s or SILENCE_TRIM_S)

    # Editor cuts and manual cuts join the silence cuts, then everything goes through one keep-interval path
    cut_intervals = merge_cut_intervals(cut_intervals, extra_cuts, clip_start=clip_start, clip_end=clip_end)
    keep_intervals = compute_keep_intervals(clip_start, clip_end, cut_intervals)
    effective_dur = sum(et - st for st, et in keep_intervals)
    if effective_dur < 1.0:
        keep_intervals = [(clip_start, clip_end)]
        effective_dur = clip_dur
        cut_intervals = []

    segments = layout_segments_for(layout, layout_changes, clip_start, clip_end, cut_intervals)
    used = {lay for _, lay in segments}
    if "split" in used and not facecam_box:
        facecam_box = detect_facecam(sec_file)
    if caption_y is None:
        seam = SPLIT_FACECAM_H / OUTPUT_HEIGHT

        def caption_y(t: float) -> float:  # captions sit on the seam only while split is showing
            lay = [l for t0, l in segments if t0 <= t + 0.05][-1]
            return seam if lay == "split" else 0.68

    # Letterbox title card
    src_w, src_h = get_video_dimensions(sec_file)
    title_png: Optional[Path] = None
    if letterbox_style == "title" and "letterbox" in used:
        card_text = _mask_profanity(title_text) if profanity_mask else title_text
        video_h = min(OUTPUT_HEIGHT, int(OUTPUT_WIDTH * src_h / src_w))
        title_png = out_file.parent / f"title_{out_file.stem}.png"
        if render_title_card(card_text, video_h, title_png):
            hook_text = ""  # the card already shows it
        else:
            title_png = None

    # Zooms: None means this clip has no list yet (default: one at the payoff); [] means no zoom (§6.7).
    # punch_in_zoom=False is the old on/off switch and still turns zooms off for callers that pass it.
    if zooms is None:
        zooms = [] if punch_in_zoom is False else default_zooms(sec_file, clip_start, clip_end, payoff_t)
    zooms_trimmed = [
        {"t": map_timestamp_to_trimmed(z["t"], clip_start, cut_intervals), "scale": z["scale"], "hold_s": z["hold_s"]}
        for z in zooms
        if clip_start <= z["t"] <= clip_end and not any(a <= z["t"] < b for a, b in cut_intervals)
    ]
    peak_t_in_trimmed = zooms_trimmed[0]["t"] if zooms_trimmed else effective_dur / 2.0  # thumbnail frame

    # Face tracking runs before the captions: with two people on camera it also says who talks when,
    # and each caption line takes that speaker's colour
    raw_keyframes: List[Dict[str, Any]] = []
    caption_words = words
    if "face_track" in used:
        raw_keyframes, speakers = track_faces(sec_file, effective_dur + 10, src_w, src_h)
        if speakers:
            caption_words = [{**w, "speaker": speaker_at(speakers, float(w.get("start", 0)) - sec_start)} for w in words]

    # Remap words for ASS captions
    retimed_words = retime_words_for_cuts(caption_words, clip_start, clip_end, cut_intervals)

    # 2. Generate ASS Captions
    ass_path = out_file.parent / f"{out_file.stem}.ass"
    ass_content = generate_ass(
        words=retimed_words,
        clip_start_s=clip_start,
        clip_end_s=clip_start + effective_dur,
        style=caption_style,
        profanity_mask=profanity_mask,
        caption_y_fraction=caption_y,
        hook_text=strip_emoji(hook_text),  # libass can't draw colour emoji
        hook_duration_s=HOOK_DURATION_S,
        overlay_events=overlay_events,
    )
    write_ass_file(ass_content, ass_path)
    ass_rel = _to_rel_path(ass_path)

    # 3. MediaPipe Face Tracking if needed
    keyframes: List[Dict[str, Any]] = []
    sc_path: Optional[Path] = None
    sc_rel: Optional[str] = None

    if "face_track" in used:
        keyframes = _retime_keyframes(raw_keyframes, sec_start, clip_start, cut_intervals)
        sc_path = out_file.parent / f"sc_{out_file.stem}.txt"
        sendcmd_content = _build_sendcmd_file(keyframes, src_w, src_h)
        sc_path.write_text(sendcmd_content, encoding="utf-8")
        sc_rel = _to_rel_path(sc_path)

    # 4. Resolve Music Track
    resolved_music = resolve_music_path(music_track) if music_track else None
    has_music = bool(resolved_music and resolved_music.exists())

    # 5. Build Unified Filtergraph
    filtergraph = build_vertical_filtergraph(
        sec_start=sec_start,
        keep_intervals=keep_intervals,
        layout=layout,
        src_w=src_w,
        src_h=src_h,
        effective_dur=effective_dur,
        ass_rel=ass_rel,
        keyframes=keyframes,
        sc_rel=sc_rel,
        facecam_box=facecam_box,
        zooms=zooms_trimmed,
        has_music=has_music,
        layout_segments=segments,
        letterbox_style=letterbox_style,
        title_input=(2 if has_music else 1) if title_png else None,
        bleeps=[(a, b) for a, b in slur_intervals(retimed_words, clip_start) if b > 0 and a < effective_dur],
    )

    # 6. Execute FFmpeg Render Command (No Shell)
    cmd = [
        "ffmpeg", "-y", "-hide_banner", "-loglevel", "error",
        "-i", str(sec_file),
    ]
    if has_music:
        cmd.extend(["-stream_loop", "-1", "-i", str(resolved_music)])
    if title_png:
        cmd.extend(["-i", str(title_png)])  # one still frame; overlay holds it for the whole clip

    cmd.extend([
        "-filter_complex", filtergraph,
        "-map", "[vout]",
        "-map", "[aout]",
        "-c:v", OUTPUT_VIDEO_CODEC,
        "-preset", OUTPUT_VIDEO_PRESET,
        "-crf", str(OUTPUT_VIDEO_CRF),
        "-c:a", OUTPUT_AUDIO_CODEC,
        "-b:a", OUTPUT_AUDIO_BITRATE,
        "-ac", "2",  # same audio layout for every clip, so concept pieces join with the concat demuxer
        "-r", str(OUTPUT_FPS),
        "-pix_fmt", "yuv420p",
        "-movflags", "+faststart",
        str(out_file),
    ])

    try:
        subprocess.run(cmd, check=True)
    except subprocess.CalledProcessError as e:
        print(f"  [stage 9c] Warning: primary render failed: {e}. Attempting fallback...")
        ss = str(section_clip_offset)
        t = str(effective_dur)
        _render_center_fallback(sec_file, out_file, ss, t, ass_rel)

    # Cleanup temporary sendcmd file and title card
    for tmp in (sc_path, title_png):
        if tmp:
            Path(tmp).unlink(missing_ok=True)

    if out_file.exists() and out_file.stat().st_size > 1000:
        # Extract representative thumbnail
        thumb_t = min(peak_t_in_trimmed, max(0.5, effective_dur - 0.5))
        cmd_thumb = [
            "ffmpeg", "-y", "-hide_banner", "-loglevel", "error",
            "-ss", str(thumb_t),
            "-i", str(out_file),
            "-frames:v", "1",
            "-q:v", "2",
            str(thumb_file),
        ]
        subprocess.run(cmd_thumb, check=False)
        return True

    return False
