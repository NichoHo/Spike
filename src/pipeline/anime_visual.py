"""
Anime visual series (report section 5.4): shot cuts, motion, cut_rate, flash and the audio-visual swell.
Frames come from ffmpeg as 320 px grayscale at 12 fps and are compared with numpy, so no scene-detection package is
needed. Cuts follow PySceneDetect's AdaptiveDetector rule (score over the rolling mean of its neighbours, width 2,
ratio 3.0, minimum 15), on luma instead of HSV.
Output: data/videos/<id>/anime_signals.npz with per-second motion, cut_rate, flash, swell and the cut times.
"""

import subprocess
from pathlib import Path
from typing import Any, Dict, Iterator, Tuple

import numpy as np

FPS = 12
WIDTH = 320
ADAPTIVE_RATIO, MIN_CONTENT, WINDOW = 3.0, 15.0, 2
FLASH_Z, FLASH_MAX_FRAMES = 4.0, 2


def _frames(path: str, duration_s: float) -> Iterator[np.ndarray]:
    """Gray frames, one per 1/FPS s, as 2-D uint8 arrays."""
    proc = subprocess.Popen(
        ["ffmpeg", "-v", "error", "-t", str(duration_s), "-i", path, "-an",
         "-vf", f"fps={FPS},scale={WIDTH}:-2,format=gray", "-f", "rawvideo", "pipe:1"],
        stdout=subprocess.PIPE)
    height = None
    try:
        while True:
            if height is None:  # the first frame's size is not known until ffprobe says so
                height = _frame_height(path)
            buf = proc.stdout.read(WIDTH * height)
            if len(buf) < WIDTH * height:
                return
            yield np.frombuffer(buf, dtype=np.uint8).reshape(height, WIDTH)
    finally:
        proc.stdout.close()
        proc.kill()


def _frame_height(path: str) -> int:
    out = subprocess.run(["ffprobe", "-v", "error", "-select_streams", "v:0", "-show_entries", "stream=width,height",
                          "-of", "csv=p=0:s=x", path], capture_output=True, text=True).stdout.strip()
    w, h = (int(x) for x in out.split("x"))
    h = round(WIDTH * h / w)
    return h + (h % 2)  # ffmpeg's scale=-2 rounds to an even height


def frame_stats(path: str, duration_s: float) -> Tuple[np.ndarray, np.ndarray]:
    """(content, luma): mean absolute luma change to the previous frame, and mean luma, per frame."""
    content, luma, prev = [0.0], [], None
    for f in _frames(path, duration_s):
        f32 = f.astype(np.float32)
        luma.append(float(f32.mean()))
        if prev is not None:
            content.append(float(np.abs(f32 - prev).mean()))
        prev = f32
    return np.array(content[:len(luma)], dtype=np.float32), np.array(luma, dtype=np.float32)


def detect_cuts(content: np.ndarray) -> np.ndarray:
    """Cut times in seconds. A frame is a cut when its change is 3x the mean of the 2 frames before and after it
    and at least 15. Drawn-on-twos animation repeats frames, so the neighbour mean has a floor of 1."""
    n = len(content)
    cuts = []
    for i in range(n):
        if content[i] < MIN_CONTENT:
            continue
        nb = np.concatenate([content[max(0, i - WINDOW):i], content[i + 1:i + 1 + WINDOW]])
        if content[i] / max(1.0, float(nb.mean()) if len(nb) else 1.0) >= ADAPTIVE_RATIO:
            cuts.append(i)
    merged = []  # two flagged frames within 0.25 s are one cut: keep the stronger
    for i in cuts:
        if merged and (i - merged[-1]) / FPS < 0.25:
            if content[i] > content[merged[-1]]:
                merged[-1] = i
        else:
            merged.append(i)
    return np.array(merged, dtype=np.float32) / FPS


def per_second(values: np.ndarray, duration_s: int) -> np.ndarray:
    """Mean of per-frame values in each second."""
    out = np.zeros(duration_s, dtype=np.float32)
    sec = (np.arange(len(values)) / FPS).astype(int)
    for s in range(duration_s):
        m = sec == s
        if m.any():
            out[s] = values[m].mean()
    return out


def motion_series(content: np.ndarray, duration_s: int) -> np.ndarray:
    """Per-second change, then a 2 s moving average (anime on twos and threes is spiky frame to frame)."""
    return np.convolve(per_second(content, duration_s), np.ones(2) / 2, mode="same").astype(np.float32)


def cut_rate_series(cuts: np.ndarray, duration_s: int) -> np.ndarray:
    """Cuts in a centered 10 s window."""
    counts = np.bincount(np.minimum(cuts.astype(int), duration_s - 1), minlength=duration_s).astype(np.float32)
    return np.convolve(counts, np.ones(10), mode="same").astype(np.float32)


def flash_series(luma: np.ndarray, duration_s: int) -> np.ndarray:
    """1 in seconds with an impact-frame flash: a brightness jump above 4 robust z that falls back within 2 frames."""
    d = np.abs(np.diff(luma, prepend=luma[:1]))
    med = np.median(d)
    mad = float(np.median(np.abs(d - med))) * 1.4826 or float(d.std()) or 1.0
    z = (d - med) / mad
    out = np.zeros(duration_s, dtype=np.float32)
    for i in np.nonzero(z > FLASH_Z)[0]:
        base = luma[i - 1] if i > 0 else luma[i]
        jump = abs(luma[i] - base)
        back = any(i + k < len(luma) and abs(luma[i + k] - base) < 0.5 * jump for k in range(1, FLASH_MAX_FRAMES + 1))
        sec = int(i / FPS)
        if back and sec < duration_s:
            out[sec] = 1.0
    return out


def swell_series(audio_loud: np.ndarray, music_p: np.ndarray, speech_p: np.ndarray) -> np.ndarray:
    """Rise in loudness over 3 s (dB), counted only where music is up and speech is down.
    ponytail: per-second RMS stands in for short-term LUFS (ebur128); switch if swells prove noisy."""
    n = min(len(audio_loud), len(music_p), len(speech_p))
    loud = np.nan_to_num(audio_loud[:n].astype(np.float32), neginf=-90.0)
    slope = np.zeros(n, dtype=np.float32)
    slope[3:] = loud[3:] - loud[:-3]
    gate = (music_p[:n] > 0.5) & (speech_p[:n] < 0.4)
    return np.where(gate, np.maximum(slope, 0.0), 0.0).astype(np.float32)


def run_anime_signals(video_dir: Path, meta: Dict[str, Any]) -> Dict[str, np.ndarray]:
    """anime_signals.npz, or {} when there is no local file. Resumes if the file exists."""
    out = video_dir / "anime_signals.npz"
    if out.exists():
        return dict(np.load(out))
    local = meta.get("local_path")
    dur = int(meta.get("duration") or 0)
    if not local or not Path(local).exists() or dur <= 0:
        return {}
    print(f"  [stage 6] Anime visual series ({FPS} fps, {WIDTH} px)...")
    content, luma = frame_stats(local, dur)
    cuts = detect_cuts(content)
    sig_path = video_dir / "signals.npz"
    audio = np.load(sig_path) if sig_path.exists() else {}
    series = {
        "motion": motion_series(content, dur), "cut_rate": cut_rate_series(cuts, dur),
        "flash": flash_series(luma, dur), "cuts": cuts,
    }
    if all(k in audio for k in ("audio_loud", "music_p", "speech_p")):
        series["swell"] = swell_series(audio["audio_loud"], audio["music_p"], audio["speech_p"])
    np.savez_compressed(out, **series)
    print(f"  [stage 6] {len(cuts)} cuts, mean motion {series['motion'].mean():.1f}")
    return series


if __name__ == "__main__":
    # a synthetic content series: quiet, one hard cut, a scroll of moderate motion (not a cut), a second cut
    c = np.full(240, 2.0, dtype=np.float32)
    c[60] = 45.0
    c[120:160] = 20.0          # steady 20: ratio to its neighbours is ~1, so not a cut
    c[200], c[201] = 50.0, 30.0   # one cut flagged twice within 0.25 s
    cuts = detect_cuts(c)
    assert list(np.round(cuts * FPS).astype(int)) == [60, 200], cuts
    rate = cut_rate_series(cuts, 20)
    assert rate[0] == 0.0 and rate[5] == 1.0 and rate[11] == 0.0 and rate[17] == 1.0, rate
    assert motion_series(c, 20).shape == (20,)
    luma = np.full(240, 100.0, dtype=np.float32)
    luma[30] = 200.0           # one-frame white flash
    luma[100:] = 140.0         # a lasting change is a lighting change, not a flash
    fl = flash_series(luma, 20)
    assert fl[2] == 1.0 and fl[8] == 0.0 and fl.sum() == 1.0, fl
    loud = np.concatenate([np.full(10, -40.0), np.linspace(-40, -10, 10), np.full(10, -10.0)])
    sw = swell_series(loud, np.full(30, 0.9), np.full(30, 0.1))
    assert sw[12] > 0 and sw[5] == 0 and sw[25] == 0
    assert swell_series(loud, np.full(30, 0.9), np.full(30, 0.9)).sum() == 0   # speech on: not a swell
    print("ok")
