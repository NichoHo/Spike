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
  letterbox   – full frame scaled to width, blurred+zoomed background fill

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
    ZOOM_OUT_DURATION,
)
from src.db import create_or_update_clip
from src.music import (
    get_random_track_for_mood,
    resolve_music_path,
)
from src.pipeline.stage9a_face_track import (
    detect_facecam,
    get_video_dimensions,
    run_face_track,
)
from src.pipeline.stage9b_captions import generate_ass, write_ass_file

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
    keep_breath_s: float = SILENCE_TRIM_BREATH_S,
) -> List[Tuple[float, float]]:
    """
    Find internal pauses between consecutive words longer than threshold_s (1.2 s).
    Returns list of (cut_start_s, cut_end_s) in absolute video timeline seconds.
    Leaves keep_breath_s (0.4 s) natural breath duration after speech finishes.
    """
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
        lines.append(f"{t:.3f} crop x {int(x)};")
        lines.append(f"{t:.3f} crop y {int(y)};")
    return "\n".join(lines) + "\n"


# ── Effect helpers ────────────────────────────────────────────────────────────

def _zoom_expr(peak_t: float) -> str:
    """
    Build a zoompan 'z' expression that ramps up to ZOOM_FACTOR (1.15x) over 0.3s
    at the peak second and ramps back down over 1.0s.
    In zoompan, the input frame index variable is 'in'.
    """
    z_max = ZOOM_FACTOR
    z_in_frames = max(1, int(OUTPUT_FPS * ZOOM_IN_DURATION))
    z_out_frames = max(1, int(OUTPUT_FPS * ZOOM_OUT_DURATION))
    peak_frame = max(1, int(peak_t * OUTPUT_FPS))
    in_start = peak_frame
    in_end = peak_frame + z_in_frames
    out_end = in_end + z_out_frames

    expr = (
        f"if(between(in,{in_start},{in_end}),"
        f"1.0+(in-{in_start})*({z_max}-1.0)/{z_in_frames},"
        f"if(between(in,{in_end},{out_end}),"
        f"{z_max}-(in-{in_end})*({z_max}-1.0)/{z_out_frames},"
        f"1.0))"
    )
    return expr


def resolve_layout(
    layout: str,
    sec_file: Path,
    facecam_box: Optional[Dict[str, float]] = None,
) -> Tuple[str, Optional[Dict[str, float]]]:
    """
    Turn "auto" into a concrete layout and find the facecam for split.
    auto = split when a small face stays put (a facecam overlay on gameplay or a video),
    otherwise face_track (a full-frame camera, or no face at all).
    """
    if layout not in ("auto", "split") or facecam_box:
        return layout, facecam_box
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


# ── Unified Filtergraph Builder ───────────────────────────────────────────────

def build_vertical_filtergraph(
    sec_start: float,
    keep_intervals: List[Tuple[float, float]],
    layout: str,
    src_w: int,
    src_h: int,
    peak_t_in_trimmed: float,
    effective_dur: float,
    ass_rel: str,
    keyframes: Optional[List[Dict[str, Any]]] = None,
    sc_rel: Optional[str] = None,
    facecam_box: Optional[Dict[str, float]] = None,
    punch_in_zoom: bool = True,
    has_music: bool = False,
) -> str:
    """
    Build complete native FFmpeg filtergraph:
    1. Trims and optional silence removal (via trim/atrim + concat)
    2. Layout transformation (face_track, split, center, letterbox)
    3. Punch-in zoom (1.0x to 1.15x at peak second)
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
        filters.append(f"{concat_inputs}concat=n={k_count}:v=1:a=1[v_trimmed][a_trimmed]")
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

    # 2. Layout Transformation
    if layout == "face_track" and sc_rel:
        first_kf = keyframes[0] if keyframes else {
            "cx_px": src_w / 2, "cy_px": src_h / 2, "crop_w_px": src_w, "crop_h_px": src_h
        }
        cw = int(first_kf.get("crop_w_px", src_w))
        ch = int(first_kf.get("crop_h_px", src_h))
        init_x = int(max(0, first_kf["cx_px"] - cw / 2))
        init_y = int(max(0, first_kf["cy_px"] - ch / 2))
        filters.append(
            f"[v_trimmed]crop={cw}:{ch}:{init_x}:{init_y},sendcmd=f={sc_rel},"
            f"scale={OUTPUT_WIDTH}:{OUTPUT_HEIGHT}:force_original_aspect_ratio=decrease,"
            f"pad={OUTPUT_WIDTH}:{OUTPUT_HEIGHT}:(ow-iw)/2:(oh-ih)/2,setsar=1[v_layout]"
        )
    elif layout == "split":
        (fc_x, fc_y, fc_w, fc_h), (gp_x, gp_y, gp_w, gp_h) = split_crops(facecam_box, src_w, src_h)
        filters.append(f"[v_trimmed]split=2[fc_in][gp_in]")
        filters.append(f"[fc_in]crop={fc_w}:{fc_h}:{fc_x}:{fc_y},scale={OUTPUT_WIDTH}:{SPLIT_FACECAM_H},setsar=1[facecam]")
        filters.append(f"[gp_in]crop={gp_w}:{gp_h}:{gp_x}:{gp_y},scale={OUTPUT_WIDTH}:{SPLIT_GAMEPLAY_H},setsar=1[gameplay]")
        filters.append(f"[facecam][gameplay]vstack=inputs=2[v_layout]")
    elif layout == "letterbox":
        filters.append(f"[v_trimmed]split=2[bg_in][fg_in]")
        filters.append(f"[bg_in]scale={OUTPUT_WIDTH}:-1,crop={OUTPUT_WIDTH}:{OUTPUT_HEIGHT},boxblur=20:5,setsar=1[bg]")
        filters.append(f"[fg_in]scale={OUTPUT_WIDTH}:-1,setsar=1[fg]")
        filters.append(f"[bg][fg]overlay=(W-w)/2:(H-h)/2[v_layout]")
    else:  # center
        crop_h = src_h
        crop_w = int(src_h * OUTPUT_WIDTH / OUTPUT_HEIGHT)
        if crop_w > src_w:
            crop_w = src_w
            crop_h = int(src_w * OUTPUT_HEIGHT / OUTPUT_WIDTH)
        cx = int((src_w - crop_w) / 2)
        cy = int((src_h - crop_h) / 2)
        filters.append(f"[v_trimmed]crop={crop_w}:{crop_h}:{cx}:{cy},scale={OUTPUT_WIDTH}:{OUTPUT_HEIGHT},setsar=1[v_layout]")

    # 3. Punch-in zoom, plus a small zoom on every other segment so jump cuts read as edits
    z_parts = []
    if punch_in_zoom:
        z_parts.append(_zoom_expr(peak_t_in_trimmed))
    if k_count > 1:
        z_parts.append(_jump_cut_zoom_expr(keep_intervals))
    if z_parts:
        z_expr = z_parts[0] if len(z_parts) == 1 else f"max({z_parts[0]},{z_parts[1]})"
        filters.append(
            f"[v_layout]zoompan=z='{z_expr}':x='iw/2-(iw/zoom/2)':y='ih/2-(ih/zoom/2)':d=1:fps={OUTPUT_FPS}:s={OUTPUT_WIDTH}x{OUTPUT_HEIGHT}[v_zoomed]"
        )
    else:
        filters.append(f"[v_layout]null[v_zoomed]")

    # 4. ASS Captions Overlay
    filters.append(f"[v_zoomed]ass={ass_rel}[vout]")

    # 5. Audio Processing & Ducking
    if has_music:
        base_vol = 10.0 ** (MUSIC_UNDER_DB / 20.0)  # ~0.0794 (-22 dB)
        filters.append(f"[1:a]atrim=start=0:end={effective_dur:.3f},asetpts=PTS-STARTPTS,volume={base_vol:.4f}[bgm_base]")
        filters.append(f"[a_trimmed]asplit=2[sp_main][sp_key]")
        filters.append(
            f"[bgm_base][sp_key]sidechaincompress=threshold={MUSIC_DUCK_THRESHOLD}:ratio={MUSIC_DUCK_RATIO}:"
            f"attack={MUSIC_DUCK_ATTACK_MS}:release={MUSIC_DUCK_RELEASE_MS}:detection=rms[bgm_duck]"
        )
        filters.append(f"[sp_main][bgm_duck]amix=inputs=2:duration=first:dropout_transition=2[a_mixed]")
        filters.append(f"[a_mixed]loudnorm=I={OUTPUT_LOUDNESS_TARGET}:TP={OUTPUT_LOUDNESS_PEAK}:LRA=11,aresample=48000[aout]")
    else:
        filters.append(f"[a_trimmed]loudnorm=I={OUTPUT_LOUDNESS_TARGET}:TP={OUTPUT_LOUDNESS_PEAK}:LRA=11,aresample=48000[aout]")

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

def run_stage9c_render(
    video_dir: Path,
    candidates: List[Dict[str, Any]],
    transcript: Dict[str, Any],
    source_settings: Optional[Dict[str, Any]] = None,
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
    punch_in_zoom = bool(src_settings.get("punch_in_zoom", True))

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
        clip_start = float(cand["start_s"])
        clip_end = float(cand["end_s"])
        # Per-clip choices: an explicit setting wins, "auto" follows the judge
        clip_layout, clip_facecam = resolve_layout(layout, sec_file, facecam_box)
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
            all_words=all_words if captions_on else [],
            facecam_box=clip_facecam,
            profanity_mask=profanity_mask,
            music_track=str(chosen_track_path) if chosen_track_path else None,
            silence_trim=pace,
            punch_in_zoom=punch_in_zoom,
        )

        if success and out_file.exists():
            cand["render_file"] = str(out_file)
            cand["thumbnail_file"] = str(thumb_file)
            rendered.append(out_file)

            # Record into database clips table
            try:
                music_str = _to_rel_path(chosen_track_path) if chosen_track_path else None
                create_or_update_clip(
                    candidate_id=cand_id,
                    file_path=str(out_file),
                    thumb_path=str(thumb_file),
                    layout=clip_layout,
                    caption_style=caption_style,
                    trim_start_s=clip_start,
                    trim_end_s=clip_end,
                    music_track=music_str,
                    silence_trim=0 if pace == "off" else 1,
                    punch_in_zoom=1 if punch_in_zoom else 0,
                    status="ready",
                )
            except Exception as e:
                logger.warning(f"Failed to record clip in DB: {e}")

    # Update candidates.json
    cand_file = video_dir / "candidates.json"
    if cand_file.exists():
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
    punch_in_zoom: bool = True,
) -> bool:
    """
    Renders a single vertical clip from a downloaded section video file.
    Supports interactive adjustments to trims, layout, captions, music, silence trim, and zoom.
    silence_trim: False/"off", True/"natural" (cut pauses > 1.2 s) or "tight" (> 0.6 s).
    caption_y: None places captions on the split seam, or at 68% height for other layouts.
    """
    if not sec_file.exists():
        print(f"  [stage 9c] Error: section file {sec_file} does not exist.")
        return False

    out_file.parent.mkdir(parents=True, exist_ok=True)
    thumb_file.parent.mkdir(parents=True, exist_ok=True)

    words = all_words or []
    clip_dur = max(1.0, clip_end - clip_start)
    section_clip_offset = 5.0 if clip_start >= 5.0 else clip_start
    sec_start = clip_start - section_clip_offset

    layout, facecam_box = resolve_layout(layout, sec_file, facecam_box)
    if caption_y is None:
        caption_y = SPLIT_FACECAM_H / OUTPUT_HEIGHT if layout == "split" else 0.68

    # 1. Silence trimming calculation
    pace = {True: "natural", False: "off"}.get(silence_trim, silence_trim)
    cut_intervals: List[Tuple[float, float]] = []
    if pace == "tight":
        cut_intervals = find_silence_cut_intervals(
            words, clip_start, clip_end, SILENCE_TRIM_TIGHT_S, SILENCE_TRIM_TIGHT_BREATH_S
        )
    elif pace == "natural":
        cut_intervals = find_silence_cut_intervals(words, clip_start, clip_end)

    keep_intervals = compute_keep_intervals(clip_start, clip_end, cut_intervals)
    effective_dur = sum(et - st for st, et in keep_intervals)
    if effective_dur < 1.0:
        keep_intervals = [(clip_start, clip_end)]
        effective_dur = clip_dur
        cut_intervals = []

    # Map peak time into trimmed timeline
    raw_peak_t = clip_start + clip_dur / 2.0
    peak_t_in_trimmed = map_timestamp_to_trimmed(raw_peak_t, clip_start, cut_intervals)

    # Remap words for ASS captions
    retimed_words = retime_words_for_cuts(words, clip_start, clip_end, cut_intervals)

    # 2. Generate ASS Captions
    ass_path = out_file.parent / f"{out_file.stem}.ass"
    ass_content = generate_ass(
        words=retimed_words,
        clip_start_s=clip_start,
        clip_end_s=clip_start + effective_dur,
        style=caption_style,
        profanity_mask=profanity_mask,
        caption_y_fraction=caption_y,
        hook_text=hook_text,
        hook_duration_s=HOOK_DURATION_S,
    )
    write_ass_file(ass_content, ass_path)
    ass_rel = _to_rel_path(ass_path)

    # 3. MediaPipe Face Tracking if needed
    src_w, src_h = get_video_dimensions(sec_file)
    keyframes: List[Dict[str, Any]] = []
    sc_path: Optional[Path] = None
    sc_rel: Optional[str] = None

    if layout == "face_track":
        keyframes = _retime_keyframes(
            run_face_track(sec_file, effective_dur + 10, src_w, src_h), sec_start, clip_start, cut_intervals
        )
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
        peak_t_in_trimmed=peak_t_in_trimmed,
        effective_dur=effective_dur,
        ass_rel=ass_rel,
        keyframes=keyframes,
        sc_rel=sc_rel,
        facecam_box=facecam_box,
        punch_in_zoom=punch_in_zoom,
        has_music=has_music,
    )

    # 6. Execute FFmpeg Render Command (No Shell)
    cmd = [
        "ffmpeg", "-y", "-hide_banner", "-loglevel", "error",
        "-i", str(sec_file),
    ]
    if has_music:
        cmd.extend(["-stream_loop", "-1", "-i", str(resolved_music)])

    cmd.extend([
        "-filter_complex", filtergraph,
        "-map", "[vout]",
        "-map", "[aout]",
        "-c:v", OUTPUT_VIDEO_CODEC,
        "-preset", OUTPUT_VIDEO_PRESET,
        "-crf", str(OUTPUT_VIDEO_CRF),
        "-c:a", OUTPUT_AUDIO_CODEC,
        "-b:a", OUTPUT_AUDIO_BITRATE,
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

    # Cleanup temporary sendcmd file
    if sc_path and sc_path.exists():
        try:
            sc_path.unlink()
        except OSError:
            pass

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
