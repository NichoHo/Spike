"""
Stage 9a: face_track — MediaPipe face position sampling.
Blueprint §7.1: MediaPipe face detection at 4 fps, crop center follows the
largest face, smoothed with an exponential moving average so the frame does
not jitter. Hold position when no face is found.

Returns a list of (cx, cy) crop centers in source-pixel coordinates,
one entry per second of the clip (not per video frame), ready for
the ffmpeg sendcmd filter.

With two or more people on camera the crop follows whoever is talking: mouth movement
picks the speaker, and the crop cuts to them instead of panning (see _speaker_track).
"""

from __future__ import annotations

import json
import math
import subprocess
import tempfile
from pathlib import Path
from typing import List, Optional, Tuple, Dict, Any, Sequence

from src.config import FACE_DETECT_FPS, FACE_TRACK_EMA_ALPHA


DETECT_WIDTH = 640  # face boxes are found on frames downscaled to this width; ratios are scale-free

# Speaker tracking (only runs when the quick pass sees two faces at once)
MULTI_FACE_MIN_SHARE = 0.15   # share of probe frames with 2+ faces that turns speaker tracking on
PROBE_FPS = 0.5               # the probe looks at one frame every 2 s
SPEAKER_FPS = 10              # mouth movement needs more samples than the 4 fps position pass
SPEAKER_WIDTH = 960
SPEAKER_WINDOW = 5            # frames per decision (0.5 s)
SPEAKER_MIN_HOLD_S = 1.5      # stay on a speaker at least this long before cutting away
SPEAKER_SWITCH_RATIO = 1.5    # challenger must out-move the current speaker by this factor
SPEAKER_MIN_ACTIVITY = 1.5    # mouth change, as a multiple of that face's resting level, below which nobody is talking
SPEAKER_MIN_TRACK_SHARE = 0.25  # a face seen in less than this share of frames is ignored (poster, game character)
SPEAKER_MATCH_DIST = 0.18     # max centre jump (frame fraction) between frames for the same face
SPEAKER_LAG_S = 0.75           # the pick trails the true speaker by this much (two-window rule), see speaker_at
SPEAKER_REST_FLOOR = 0.05     # smallest resting mouth change per window, so a perfectly still face does not divide by ~0


def _download_face_detector_model(model_path: Path) -> bool:
    """Download the MediaPipe face detector tflite model if not already present."""
    import urllib.request
    # The Tasks API accepts plain .tflite files. The .task bundle URL 404s in all
    # tested versions; the .tflite URL at /1/ is confirmed live (229 KB).
    MODEL_URL = (
        "https://storage.googleapis.com/mediapipe-models/face_detector/"
        "blaze_face_short_range/float16/1/blaze_face_short_range.tflite"
    )
    if model_path.exists():
        return True
    try:
        print(f"  [face_track] Downloading face detector model to {model_path.name}...")
        urllib.request.urlretrieve(MODEL_URL, str(model_path))
        print(f"  [face_track] Downloaded {model_path.stat().st_size:,} bytes")
        return True
    except Exception as e:
        print(f"  [face_track] Could not download face detector model: {e}")
        return False


def _detect_faces_mediapipe(
    section_path: Path,
    duration_s: float,
    sample_fps: int = FACE_DETECT_FPS,
) -> List[Optional[Tuple[float, float, float, float]]]:
    """
    Run MediaPipe Tasks FaceDetector on a video at sample_fps frames per second.
    Returns a list of (x, y, w, h) bounding boxes in 0..1 normalized coords,
    one per sampled frame (sample_fps * duration_s entries), or None when no
    face was found at that sample.
    """
    try:
        import mediapipe as mp
        import cv2
        import numpy as np
        from mediapipe.tasks import python
        from mediapipe.tasks.python import vision
    except ImportError as e:
        print(f"  [face_track] Import error: {e}, falling back to center crop.")
        return []

    # Model file location — uses .tflite (Tasks API accepts plain tflite files)
    model_path = Path(__file__).resolve().parent.parent.parent / "phase0" / "face_detector.tflite"
    if not _download_face_detector_model(model_path):
        return []

    base_options = python.BaseOptions(model_asset_path=str(model_path))
    options = vision.FaceDetectorOptions(
        base_options=base_options,
        min_detection_confidence=0.5,
    )

    # ffmpeg samples at sample_fps and downscales, so we never decode-convert the frames we skip
    cap = cv2.VideoCapture(str(section_path))
    src_w = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH))
    src_h = int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT))
    cap.release()
    if not src_w or not src_h:
        return []
    img_w = min(src_w, DETECT_WIDTH)
    img_h = max(2, round(src_h * img_w / src_w))
    proc = subprocess.Popen(
        ["ffmpeg", "-v", "error", "-i", str(section_path), "-an", "-sn",
         "-vf", f"fps={sample_fps},scale={img_w}:{img_h}", "-f", "rawvideo", "-pix_fmt", "rgb24", "-"],
        stdout=subprocess.PIPE, stderr=subprocess.DEVNULL,
    )
    frame_bytes = img_w * img_h * 3
    results: List[Optional[Tuple[float, float, float, float]]] = []

    with vision.FaceDetector.create_from_options(options) as detector:
        while True:
            buf = proc.stdout.read(frame_bytes)
            if len(buf) < frame_bytes:
                break
            rgb = np.frombuffer(buf, np.uint8).reshape(img_h, img_w, 3)
            det_result = detector.detect(mp.Image(image_format=mp.ImageFormat.SRGB, data=rgb))
            if det_result.detections:
                # Use largest face by area
                best = max(
                    det_result.detections,
                    key=lambda d: d.bounding_box.width * d.bounding_box.height,
                )
                bb = best.bounding_box
                results.append((
                    max(0.0, bb.origin_x / img_w),
                    max(0.0, bb.origin_y / img_h),
                    min(1.0, bb.width / img_w),
                    min(1.0, bb.height / img_h),
                ))
            else:
                results.append(None)

    proc.stdout.close()
    proc.wait()
    return results


# Full frame plus the four quadrants: the short-range detector misses small (background) faces in the full
# frame, and each quadrant magnifies them 2x.
_SPEAKER_TILES = ((0, 0, 1, 1), (0, 0, .5, .5), (.5, 0, 1, .5), (0, .5, .5, 1), (.5, .5, 1, 1))


def _faces_in_frame(detector, mp, np, rgb) -> List[Tuple[float, float, float, float, Tuple[float, float]]]:
    """All faces as (x, y, w, h, mouth_xy), 0..1 of the frame, biggest first, duplicates across tiles merged."""
    h, w = rgb.shape[:2]
    found = []
    for x0, y0, x1, y1 in _SPEAKER_TILES:
        crop = np.ascontiguousarray(rgb[int(y0 * h):int(y1 * h), int(x0 * w):int(x1 * w)])
        ch, cw = crop.shape[:2]
        for d in detector.detect(mp.Image(image_format=mp.ImageFormat.SRGB, data=crop)).detections:
            bb, mouth = d.bounding_box, d.keypoints[3]  # keypoint 3 is the mouth centre
            found.append((
                (x0 * w + bb.origin_x) / w, (y0 * h + bb.origin_y) / h, bb.width / w, bb.height / h,
                ((x0 * w + mouth.x * cw) / w, (y0 * h + mouth.y * ch) / h),
            ))
    kept: list = []
    for f in sorted(found, key=lambda f: -f[2] * f[3]):
        cx, cy = f[0] + f[2] / 2, f[1] + f[3] / 2
        # the same face seen by two tiles lands less than ~3/4 of a face size away from the bigger box
        if not any(
            math.hypot((cx - k[0] - k[2] / 2) / k[2], (cy - k[1] - k[3] / 2) / k[3]) < 0.75 for k in kept
        ):
            kept.append(f)
    return kept


def _pick_speakers(windows: List[Dict[int, float]]) -> List[Optional[int]]:
    """
    Pick the speaking face per window from {face id: mouth movement}. Stay on the current speaker unless
    another face out-moves them by SPEAKER_SWITCH_RATIO for two windows in a row, and only after the minimum
    hold. None until someone first talks.
    """
    hold = max(1, round(SPEAKER_MIN_HOLD_S * SPEAKER_FPS / SPEAKER_WINDOW))
    current: Optional[int] = None
    since, challenger, streak = hold, None, 0
    out: List[Optional[int]] = []
    for win in windows:
        best = max(win, key=win.get) if win else None
        if best is not None and win[best] >= SPEAKER_MIN_ACTIVITY:
            if current is None:
                others = [v for k, v in win.items() if k != best]
                if not others or win[best] > SPEAKER_SWITCH_RATIO * max(others):
                    current, since = best, 0
            elif best != current and win[best] > SPEAKER_SWITCH_RATIO * win.get(current, 0.0):
                streak = streak + 1 if challenger == best else 1
                challenger = best
                if streak >= 2 and since >= hold:
                    current, since, streak = best, 0, 0
            else:
                challenger, streak = None, 0
        since += 1
        out.append(current)
    return out


def _frames(section_path: Path, fps: float, width: int):
    """Yield RGB frames (numpy arrays) sampled by ffmpeg at `fps`, scaled to at most `width` wide."""
    import cv2
    import numpy as np
    cap = cv2.VideoCapture(str(section_path))
    src_w, src_h = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH)), int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT))
    cap.release()
    if not src_w or not src_h:
        return
    img_w = min(src_w, width)
    img_h = max(2, round(src_h * img_w / src_w))
    proc = subprocess.Popen(
        ["ffmpeg", "-v", "error", "-i", str(section_path), "-an", "-sn",
         "-vf", f"fps={fps},scale={img_w}:{img_h}", "-f", "rawvideo", "-pix_fmt", "rgb24", "-"],
        stdout=subprocess.PIPE, stderr=subprocess.DEVNULL,
    )
    frame_bytes = img_w * img_h * 3
    try:
        while True:
            buf = proc.stdout.read(frame_bytes)
            if len(buf) < frame_bytes:
                break
            yield np.frombuffer(buf, np.uint8).reshape(img_h, img_w, 3)
    finally:
        proc.stdout.close()
        proc.wait()


def _detector_options():
    from mediapipe.tasks import python
    from mediapipe.tasks.python import vision
    model_path = Path(__file__).resolve().parent.parent.parent / "phase0" / "face_detector.tflite"
    if not _download_face_detector_model(model_path):
        return None
    return vision.FaceDetectorOptions(
        base_options=python.BaseOptions(model_asset_path=str(model_path)), min_detection_confidence=0.5
    )


def _multi_face_share(section_path: Path) -> float:
    """Share of sparse probe frames showing two or more faces (tiles included, so background faces count)."""
    try:
        import mediapipe as mp
        import numpy as np
        from mediapipe.tasks.python import vision
    except ImportError:
        return 0.0
    options = _detector_options()
    if options is None:
        return 0.0
    hits = total = 0
    with vision.FaceDetector.create_from_options(options) as detector:
        for rgb in _frames(section_path, PROBE_FPS, SPEAKER_WIDTH):
            total += 1
            hits += len(_faces_in_frame(detector, mp, np, rgb)) > 1
    return hits / max(1, total)


def _speaker_track(section_path: Path, n_samples: int):
    """
    Follow the person who is talking. Samples at SPEAKER_FPS, finds every face, matches faces from frame to
    frame, and scores each by how much its mouth region changes (the patch follows the face, so head movement
    mostly cancels). Returns (raw boxes at FACE_DETECT_FPS, cut sample indices) or None when fewer than two
    steady faces show up, so the caller keeps its single-face behaviour. The third value is the speaker at
    each sample: 0 for whoever talks first, 1 for the next new face, and so on.
    """
    try:
        import mediapipe as mp
        import cv2
        import numpy as np
        from mediapipe.tasks.python import vision
    except ImportError:
        return None
    options = _detector_options()
    if options is None:
        return None

    tracks: List[Dict[str, Any]] = []   # {"pos": (cx, cy), "patch": array, "seen": int}
    boxes: List[Dict[int, Tuple[float, float, float, float]]] = []
    activity: List[Dict[int, float]] = []
    with vision.FaceDetector.create_from_options(options) as detector:
        for rgb in _frames(section_path, SPEAKER_FPS, SPEAKER_WIDTH):
            img_h, img_w = rgb.shape[:2]
            gray = cv2.cvtColor(rgb, cv2.COLOR_RGB2GRAY)
            frame_boxes: Dict[int, Tuple[float, float, float, float]] = {}
            frame_act: Dict[int, float] = {}
            for x, y, w, h, (mx, my) in _faces_in_frame(detector, mp, np, rgb):
                pos = (x + w / 2, y + h / 2)
                free = [i for i in range(len(tracks)) if i not in frame_boxes]
                dist = lambda i: float(np.hypot(pos[0] - tracks[i]["pos"][0], pos[1] - tracks[i]["pos"][1]))
                tid = min(free, key=dist, default=None)
                if tid is None or dist(tid) > SPEAKER_MATCH_DIST:
                    tid = len(tracks)
                    tracks.append({"pos": pos, "patch": None, "seen": 0})
                tr = tracks[tid]
                # anchor the patch on a smoothed mouth position so detector jitter does not read as movement
                sm = tr.get("mouth")
                tr["mouth"] = (mx, my, w) if sm is None else tuple(0.3 * a + 0.7 * b for a, b in zip((mx, my, w), sm))
                smx, smy, smw = tr["mouth"]
                hw, hh = max(2, int(0.35 * smw * img_w)), max(2, int(0.2 * smw * img_w))
                px, py = int(smx * img_w), int(smy * img_h)
                crop = gray[max(0, py - hh):py + hh, max(0, px - hw):px + hw]
                patch = cv2.resize(crop, (24, 12), interpolation=cv2.INTER_AREA).astype(np.float32) if crop.size else None
                if patch is not None and tr["patch"] is not None:
                    # best match over a 2-patch-pixel shift, so the head drifting is not counted as the mouth moving
                    old, new = tr["patch"][2:-2, 2:-2], patch
                    frame_act[tid] = float(min(
                        np.abs(old - new[2 + dy:10 + dy, 2 + dx:22 + dx]).mean() for dy in range(-2, 3) for dx in range(-2, 3)
                    ) / 255.0)
                tr["pos"], tr["patch"] = pos, patch
                tr["seen"] += 1
                frame_boxes[tid] = (x, y, w, h)
            boxes.append(frame_boxes)
            activity.append(frame_act)

    n = len(boxes)
    steady = {i for i, tr in enumerate(tracks) if tr["seen"] >= SPEAKER_MIN_TRACK_SHARE * n}
    if n == 0 or len(steady) < 2:
        return None
    # One person can end up as two tracks (a jump in position starts a new one). Merge tracks that sit in the
    # same place and never share a frame, so each person keeps a single identity (and a single caption colour).
    mean = {
        i: np.mean([(fb[i][0] + fb[i][2] / 2, fb[i][1] + fb[i][3] / 2) for fb in boxes if i in fb], axis=0)
        for i in steady
    }
    canon = {i: i for i in sorted(steady)}
    for j in canon:
        for i in canon:
            if (i < j and canon[i] == i and np.hypot(*(mean[i] - mean[j])) < SPEAKER_MATCH_DIST
                    and not any(i in fb and j in fb for fb in boxes)):
                canon[j] = i
                break
    boxes = [{canon.get(k, k): v for k, v in fb.items()} for fb in boxes]
    activity = [{canon.get(k, k): v for k, v in fa.items()} for fa in activity]
    steady = set(canon.values())
    if len(steady) < 2:
        return None
    windows = []
    for w0 in range(0, n, SPEAKER_WINDOW):
        win: Dict[int, float] = {i: 0.0 for i in steady}
        for fa in activity[w0:w0 + SPEAKER_WINDOW]:
            for i in steady & fa.keys():
                win[i] += fa[i]
        windows.append(win)
    for i in steady:  # score each face against its own resting level, so a noisy face cannot out-shout a clean one
        rest = max(SPEAKER_REST_FLOOR, float(np.percentile([w[i] for w in windows], 25)))
        for w in windows:
            w[i] /= rest
    chosen = _pick_speakers(windows)
    first = next((c for c in chosen if c is not None), max(steady, key=lambda i: tracks[i]["seen"]))
    chosen = [first if c is None else c for c in chosen]

    # last known box per face, so a missed detection holds position
    last: Dict[int, Optional[Tuple[float, float, float, float]]] = {i: None for i in steady}
    held: List[Dict[int, Optional[Tuple[float, float, float, float]]]] = []
    for fb in boxes:
        for i in steady & fb.keys():
            last[i] = fb[i]
        held.append(dict(last))

    raw: List[Optional[Tuple[float, float, float, float]]] = []
    cuts: List[int] = []
    speakers: List[int] = []
    rank: Dict[int, int] = {}
    prev = None
    for k in range(n_samples):
        i = min(n - 1, int(k / FACE_DETECT_FPS * SPEAKER_FPS))
        spk = chosen[i // SPEAKER_WINDOW]
        raw.append(held[i][spk])
        speakers.append(rank.setdefault(spk, len(rank)))
        if spk != prev:
            cuts.append(k)
        prev = spk
    return raw, cuts, speakers


def speaker_at(speakers: List[int], t_s: float) -> Optional[int]:
    """Speaker (0 = first to talk) at `t_s` seconds into the section, or None without a timeline.
    Looks SPEAKER_LAG_S ahead because the pick only flips after two winning windows."""
    if not speakers:
        return None
    return speakers[max(0, min(len(speakers) - 1, int((t_s + SPEAKER_LAG_S) * FACE_DETECT_FPS)))]


def _ema_smooth_centers(
    raw: List[Optional[Tuple[float, float, float, float]]],
    alpha: float = FACE_TRACK_EMA_ALPHA,
    cuts: Sequence[int] = (),
) -> List[Tuple[float, float]]:
    """
    Convert raw bounding boxes to (cx, cy) face-center ratios (0..1),
    apply EMA smoothing, hold last position when face not detected.
    At a sample index in `cuts` the position jumps to the new face instead of easing there.
    """
    cut_set = set(cuts)
    centers: List[Tuple[float, float]] = []
    last_cx, last_cy = 0.5, 0.3  # Default: centre-left for talking heads

    for i, bb in enumerate(raw):
        if bb is not None:
            x, y, w, h = bb
            raw_cx = x + w / 2.0
            raw_cy = y + h / 2.0
            if i in cut_set:
                last_cx, last_cy = raw_cx, raw_cy
            last_cx = alpha * raw_cx + (1.0 - alpha) * last_cx
            last_cy = alpha * raw_cy + (1.0 - alpha) * last_cy
        # else: hold last position
        centers.append((last_cx, last_cy))

    return centers


def run_face_track(
    section_path: Path,
    duration_s: float,
    src_w: int,
    src_h: int,
    out_w: int = 1080,
    out_h: int = 1920,
) -> List[Dict[str, Any]]:
    """Crop keyframes only; see track_faces."""
    return track_faces(section_path, duration_s, src_w, src_h, out_w, out_h)[0]


def track_faces(
    section_path: Path,
    duration_s: float,
    src_w: int,
    src_h: int,
    out_w: int = 1080,
    out_h: int = 1920,
) -> Tuple[List[Dict[str, Any]], List[int]]:
    """
    Run face tracking on the section file. Returns (crop keyframes, speaker per sample at FACE_DETECT_FPS).
    The speaker list is empty unless two or more people were told apart (use speaker_at to read it).

    Each keyframe: {t_s, cx_px, cy_px, crop_w_px, crop_h_px}
    Each entry: {t_s, cx_px, cy_px, crop_w_px, crop_h_px}
    where cx/cy are the source-pixel crop-rectangle centres.

    The crop is always out_w x out_h pixels in source resolution (no scaling
    yet — scaling is done by ffmpeg). When the source is wider than tall
    (landscape), the crop rectangle is out_w x out_h scaled to fit the source
    height, then centered on the face.
    """
    raw = _detect_faces_mediapipe(section_path, duration_s)
    cuts: List[int] = []
    speakers: List[int] = []
    if raw and _multi_face_share(section_path) >= MULTI_FACE_MIN_SHARE:
        followed = _speaker_track(section_path, len(raw))
        if followed:
            raw, cuts, speakers = followed
            if len(set(speakers)) < 2:
                speakers = []
    if not raw:
        # Fallback: static center crop keyframe
        cx = src_w / 2.0
        cy = src_h / 2.0
        return [{"t_s": 0.0, "cx_px": cx, "cy_px": cy}], []

    smooth = _ema_smooth_centers(raw, cuts=cuts)
    sample_fps = FACE_DETECT_FPS

    # Crop rectangle: keep aspect ratio of output (9:16) in source pixels
    # Fit within source dimensions
    crop_h_px = float(src_h)
    crop_w_px = crop_h_px * (out_w / out_h)
    if crop_w_px > src_w:
        crop_w_px = float(src_w)
        crop_h_px = crop_w_px * (out_h / out_w)

    keyframes: List[Dict[str, Any]] = []
    for idx, (cx_ratio, cy_ratio) in enumerate(smooth):
        t_s = idx / sample_fps
        cx_px = cx_ratio * src_w
        cy_px = cy_ratio * src_h
        # Clamp so rectangle stays within source
        cx_px = max(crop_w_px / 2, min(src_w - crop_w_px / 2, cx_px))
        cy_px = max(crop_h_px / 2, min(src_h - crop_h_px / 2, cy_px))
        keyframes.append({
            "t_s": round(t_s, 3),
            "cx_px": round(cx_px, 1),
            "cy_px": round(cy_px, 1),
            "crop_w_px": round(crop_w_px, 1),
            "crop_h_px": round(crop_h_px, 1),
        })

    return keyframes, speakers


def detect_facecam(section_path: Path, sample_fps: float = 1.0) -> Optional[Dict[str, float]]:
    """
    Find the streamer's facecam: the face that stays in one place across the section.
    Faces inside the watched content move around; the facecam face does not.

    The short-range MediaPipe model misses small faces, so each sampled frame is
    scanned as a 3x3 grid of overlapping tiles (each tile makes faces ~3x larger).
    Returns {cx, cy, w, box} (face centre and width, cam border [x0, y0, x1, y1], all 0..1)
    or None when no face shows up in the same spot in at least half of the samples.
    """
    try:
        import mediapipe as mp
        import cv2
        from mediapipe.tasks import python
        from mediapipe.tasks.python import vision
    except ImportError:
        return None

    model_path = Path(__file__).resolve().parent.parent.parent / "phase0" / "face_detector.tflite"
    if not _download_face_detector_model(model_path):
        return None

    options = vision.FaceDetectorOptions(
        base_options=python.BaseOptions(model_asset_path=str(model_path)),
        min_detection_confidence=0.6,
    )
    import numpy as np

    cap = cv2.VideoCapture(str(section_path))
    step = max(1, int((cap.get(cv2.CAP_PROP_FPS) or 30.0) / sample_fps))
    frames: List[List[Tuple[float, float, float]]] = []
    avg = None  # time-averaged small greyscale frame, for finding the cam border
    idx = 0
    with vision.FaceDetector.create_from_options(options) as detector:
        while cap.grab():
            if idx % step == 0:
                _, frame = cap.retrieve()
                img_h, img_w = frame.shape[:2]
                small = cv2.cvtColor(cv2.resize(frame, (480, 270)), cv2.COLOR_BGR2GRAY).astype(np.float32)
                avg = small if avg is None else avg + small
                tw, th = img_w // 3, img_h // 3
                found = []
                for ty in range(0, img_h - th + 1, th // 2):
                    for tx in range(0, img_w - tw + 1, tw // 2):
                        tile = cv2.cvtColor(frame[ty:ty + th, tx:tx + tw], cv2.COLOR_BGR2RGB).copy()
                        res = detector.detect(mp.Image(image_format=mp.ImageFormat.SRGB, data=tile))
                        for d in res.detections:
                            bb = d.bounding_box
                            found.append((
                                (tx + bb.origin_x + bb.width / 2) / img_w,
                                (ty + bb.origin_y + bb.height / 2) / img_h,
                                bb.width / img_w,
                            ))
                frames.append(found)
            idx += 1
    cap.release()

    if not frames:
        return None
    # ponytail: O(n^2) over detections; a 60 s section at 1 fps is a few hundred points.
    all_dets = [d for f in frames for d in f]
    best, best_hits = None, 0
    for d in all_dets:
        hits = sum(
            1 for f in frames
            if any(abs(o[0] - d[0]) < 0.05 and abs(o[1] - d[1]) < 0.05 for o in f)
        )
        if hits > best_hits:
            best, best_hits = d, hits
    if best is None or best_hits < len(frames) / 2:
        return None
    near = sorted(
        (d for d in all_dets if abs(d[0] - best[0]) < 0.05 and abs(d[1] - best[1]) < 0.05),
        key=lambda d: d[2],
    )
    mid = near[len(near) // 2]
    cam = {"cx": mid[0], "cy": mid[1], "w": mid[2]}
    cam["box"] = _facecam_border(avg / len(frames), cam)
    return cam


def _facecam_border(avg, cam: Dict[str, float], min_ratio: float = 6.0) -> List[float]:
    """
    Find the cam overlay's edges around the face as [x0, y0, x1, y1] (0..1).
    In a time-averaged frame the moving content blurs out but the cam's fixed border
    stays sharp, so each side's border is the strongest steady edge next to the face.
    A side with no clear edge (min_ratio x the typical edge strength) stays at the frame edge.
    """
    import numpy as np

    h, w = avg.shape
    cx, cy, fw = cam["cx"] * w, cam["cy"] * h, cam["w"] * w
    dx = np.abs(np.diff(avg, axis=1))[max(0, int(cy - fw * 1.5)):int(cy + fw * 1.5)].mean(axis=0)
    dy = np.abs(np.diff(avg, axis=0))[:, max(0, int(cx - fw * 1.5)):int(cx + fw * 1.5)].mean(axis=1)

    def edge(score, lo, hi, default):
        lo, hi = max(0, int(lo)), min(len(score), int(hi))
        if hi <= lo:
            return default
        i = lo + int(np.argmax(score[lo:hi]))
        return i + 1 if score[i] > min_ratio * (np.median(score) + 1e-6) else default

    # search out to 3 face-widths from the face, never inside the face itself
    x0 = edge(dx, cx - fw * 3, cx - fw * 0.75, 0)
    x1 = edge(dx, cx + fw * 0.75, cx + fw * 3, w)
    y0 = edge(dy, cy - fw * 3, cy - fw * 0.9, 0)
    y1 = edge(dy, cy + fw * 0.9, cy + fw * 3, h)
    return [x0 / w, y0 / h, x1 / w, y1 / h]


def get_video_dimensions(video_path: Path) -> Tuple[int, int]:
    """Return (width, height) of a video file using ffprobe."""
    cmd = [
        "ffprobe", "-v", "error",
        "-select_streams", "v:0",
        "-show_entries", "stream=width,height",
        "-of", "json",
        str(video_path),
    ]
    result = subprocess.run(cmd, capture_output=True, text=True)
    if result.returncode != 0:
        return 1920, 1080  # fallback
    data = json.loads(result.stdout)
    streams = data.get("streams", [{}])
    w = int(streams[0].get("width", 1920))
    h = int(streams[0].get("height", 1080))
    return w, h
