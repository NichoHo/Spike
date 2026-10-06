"""
Stage 9a: face_track — MediaPipe face position sampling.
Blueprint §7.1: MediaPipe face detection at 4 fps, crop center follows the
largest face, smoothed with an exponential moving average so the frame does
not jitter. Hold position when no face is found.

Returns a list of (cx, cy) crop centers in source-pixel coordinates,
one entry per second of the clip (not per video frame), ready for
the ffmpeg sendcmd filter.
"""

from __future__ import annotations

import json
import subprocess
import tempfile
from pathlib import Path
from typing import List, Optional, Tuple, Dict, Any

from src.config import FACE_DETECT_FPS, FACE_TRACK_EMA_ALPHA


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

    cap = cv2.VideoCapture(str(section_path))
    src_fps = cap.get(cv2.CAP_PROP_FPS) or 30.0
    frame_step = max(1, int(src_fps / sample_fps))

    results: List[Optional[Tuple[float, float, float, float]]] = []
    frame_idx = 0

    with vision.FaceDetector.create_from_options(options) as detector:
        while True:
            ret, frame = cap.read()
            if not ret:
                break
            if frame_idx % frame_step == 0:
                rgb = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
                mp_image = mp.Image(image_format=mp.ImageFormat.SRGB, data=rgb)
                det_result = detector.detect(mp_image)
                if det_result.detections:
                    # Use largest face by area
                    best = max(
                        det_result.detections,
                        key=lambda d: (
                            d.bounding_box.width * d.bounding_box.height
                        ),
                    )
                    bb = best.bounding_box
                    img_h, img_w = frame.shape[:2]
                    results.append((
                        max(0.0, bb.origin_x / img_w),
                        max(0.0, bb.origin_y / img_h),
                        min(1.0, bb.width / img_w),
                        min(1.0, bb.height / img_h),
                    ))
                else:
                    results.append(None)
            frame_idx += 1

    cap.release()
    return results


def _ema_smooth_centers(
    raw: List[Optional[Tuple[float, float, float, float]]],
    alpha: float = FACE_TRACK_EMA_ALPHA,
) -> List[Tuple[float, float]]:
    """
    Convert raw bounding boxes to (cx, cy) face-center ratios (0..1),
    apply EMA smoothing, hold last position when face not detected.
    """
    centers: List[Tuple[float, float]] = []
    last_cx, last_cy = 0.5, 0.3  # Default: centre-left for talking heads

    for bb in raw:
        if bb is not None:
            x, y, w, h = bb
            raw_cx = x + w / 2.0
            raw_cy = y + h / 2.0
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
    """
    Run face tracking on the section file and return a list of crop keyframes.
    Each entry: {t_s, cx_px, cy_px, crop_w_px, crop_h_px}
    where cx/cy are the source-pixel crop-rectangle centres.

    The crop is always out_w x out_h pixels in source resolution (no scaling
    yet — scaling is done by ffmpeg). When the source is wider than tall
    (landscape), the crop rectangle is out_w x out_h scaled to fit the source
    height, then centered on the face.
    """
    raw = _detect_faces_mediapipe(section_path, duration_s)
    if not raw:
        # Fallback: static center crop keyframe
        cx = src_w / 2.0
        cy = src_h / 2.0
        return [{"t_s": 0.0, "cx_px": cx, "cy_px": cy}]

    smooth = _ema_smooth_centers(raw)
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

    return keyframes


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
