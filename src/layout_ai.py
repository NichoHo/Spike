"""
Spike: the "auto" framing layout. A Gemini vision call looks at frames of a clip and picks the vertical layout
for each moment, so a streamer who goes from a facecam overlay to full-screen mid-clip gets a switch.
Any failure returns None and the caller falls back to the face-size heuristic.
"""

import subprocess
import tempfile
from pathlib import Path
from typing import Any, Dict, List, Literal, Optional, Tuple

from pydantic import BaseModel

from src import config, gemini_budget

FRAME_EVERY_S = 2.5
MAX_FRAMES = 24
MIN_DWELL_S = 3.0  # a layout shorter than this is merged into its neighbour
SNAP_WINDOW_S = 1.0  # a switch moves to the nearest speech pause within this distance
MIN_PAUSE_S = 0.25

_cache: Dict[Tuple[str, float], Optional[str]] = {}  # one call per section file for choose_layout

LAYOUT_RULES = """- split: a small webcam overlay of the creator sits over gameplay, a screen or another video. Top shows the face, bottom shows the content.
- face_track: the creator's face fills much of the frame (a full-frame camera, vlog, podcast) and nothing else on screen matters.
- center: one subject or action sits in the middle and a centre crop loses nothing important.
- letterbox: the whole frame matters (wide scene, text, UI, several subjects spread out), so show it uncropped."""

Layout = Literal["split", "face_track", "center", "letterbox"]


class LayoutChoice(BaseModel):
    layout: Layout
    reason: str = ""


class FrameLabel(BaseModel):
    i: int
    layout: Layout


class FrameLabels(BaseModel):
    frames: List[FrameLabel]


def _duration(path: Path) -> float:
    res = subprocess.run(
        ["ffprobe", "-v", "error", "-show_entries", "format=duration", "-of", "csv=p=0", str(path)],
        capture_output=True, text=True,
    )
    return float(res.stdout.strip())


def _frame_at(path: Path, t: float, jpg: Path) -> bytes:
    """One 480 px wide JPEG at t seconds, as bytes."""
    subprocess.run(
        ["ffmpeg", "-v", "error", "-y", "-ss", f"{t:.2f}", "-i", str(path),
         "-frames:v", "1", "-vf", "scale=480:-2", str(jpg)],
        check=True, capture_output=True,
    )
    return jpg.read_bytes()


def calls_left() -> int:
    """Gemini requests left today on the layout model (shared with every other Spike Gemini call)."""
    return gemini_budget.left(config.LAYOUT_GEMINI_MODEL)


def _ask(frames: List[Tuple[str, bytes]], prompt: str, model_cls):
    """Gemini first; when it is out of calls or fails, the same frames go to Claude (Pro plan), after the user's OK."""
    if config.GEMINI_API_KEY and calls_left() > 0:
        try:
            from google.genai import types
            from src.pipeline.stage7_moments import generate_content_with_retry, get_gemini_client

            contents: list = []
            for label, jpg in frames:
                contents += ([label] if label else []) + [types.Part.from_bytes(data=jpg, mime_type="image/jpeg")]
            resp = generate_content_with_retry(
                client=get_gemini_client(), model=config.LAYOUT_GEMINI_MODEL, contents=contents + [prompt],
                config=types.GenerateContentConfig(response_mime_type="application/json", temperature=0.1),
            )
            return model_cls.model_validate_json(resp.text)
        except Exception as e:
            print(f"  [layout] Gemini failed ({e}); trying Claude")
    from src import claude_fallback
    from src.claude_cli import require_all, run_claude

    if not claude_fallback.ask("Auto layout (Claude Sonnet)", "Auto layout looks at video frames."):
        raise RuntimeError("Claude fallback not approved")
    labels = "".join(f"f{i}.jpg = {label}\n" for i, (label, _) in enumerate(frames) if label)
    out = run_claude("You pick video framing layouts from frames.", labels + prompt, require_all(model_cls.model_json_schema()),
                     label="auto layout", model="sonnet", images=[jpg for _, jpg in frames])
    return model_cls.model_validate(out)


def choose_layout(sec_file: Path) -> Optional[str]:
    """One layout for a whole section (concept clips): split | face_track | center | letterbox, or None."""
    sec_file = Path(sec_file)
    try:
        key = (str(sec_file), sec_file.stat().st_mtime)
        if key in _cache:
            return _cache[key]
        dur = _duration(sec_file)
        with tempfile.TemporaryDirectory() as tmp:
            parts = [("", _frame_at(sec_file, dur * f, Path(tmp) / f"f{i}.jpg")) for i, f in enumerate((0.2, 0.5, 0.8))]
        prompt = ("These 3 frames come from one section of a landscape video that will be cut into a 9:16 vertical short.\n"
                  f"Pick the framing layout that shows the most important content:\n{LAYOUT_RULES}\n"
                  'Return JSON {"layout": "...", "reason": "<one short sentence>"}.')
        choice = _ask(parts, prompt, LayoutChoice)
        print(f"  [layout] auto -> {choice.layout}: {choice.reason}")
        _cache[key] = choice.layout
        return choice.layout
    except Exception as e:
        print(f"  [layout] AI pick failed ({e}); using the face-size heuristic")
        return None


def smooth_runs(times: List[float], labels: List[str], clip_end: float) -> List[List[Any]]:
    """Frame labels -> [[start_t, layout]] runs. A switch lands halfway between the two frames that differ.
    Runs shorter than MIN_DWELL_S merge into the previous run (the first one into the next)."""
    runs: List[List[Any]] = []
    for i, (t, lay) in enumerate(zip(times, labels)):
        if not runs:
            runs.append([times[0], lay])
        elif lay != runs[-1][1]:
            runs.append([round((times[i - 1] + t) / 2, 2), lay])
    while len(runs) > 1:
        durs = [(runs[k + 1][0] if k + 1 < len(runs) else clip_end) - runs[k][0] for k in range(len(runs))]
        k = min(range(len(runs)), key=lambda j: durs[j])
        if durs[k] >= MIN_DWELL_S:
            break
        if k == 0:
            runs[1][0] = runs[0][0]  # the second run now starts at the clip start
            del runs[0]
        else:
            del runs[k]
        merged = [runs[0]]
        for r in runs[1:]:
            if r[1] != merged[-1][1]:
                merged.append(r)
        runs = merged
    return runs


def snap_to_pause(t: float, words: List[Dict[str, Any]]) -> float:
    """Move t to the middle of the nearest gap between words (>= MIN_PAUSE_S) within SNAP_WINDOW_S."""
    ws = sorted(words, key=lambda w: float(w.get("start", 0)))
    best, best_d = t, SNAP_WINDOW_S
    for a, b in zip(ws, ws[1:]):
        end, start = float(a.get("end", 0)), float(b.get("start", 0))
        if start - end >= MIN_PAUSE_S:
            mid = (end + start) / 2
            if abs(mid - t) < best_d:
                best, best_d = mid, abs(mid - t)
    return round(best, 2)


def plan_layouts(
    sec_file: Path, clip_start: float, clip_end: float, sec_start: Optional[float], words: List[Dict[str, Any]],
) -> Optional[List[Dict[str, Any]]]:
    """[{t, layout}] in stream seconds; the first entry is the opening layout (t = clip_start), the rest are
    switches. None when the AI is unavailable, out of calls for today, or fails."""
    try:
        if sec_start is None:
            sec_start = clip_start - (5.0 if clip_start >= 5.0 else clip_start)  # same guess the renderer makes
        sec_dur = _duration(Path(sec_file))
        span = max(0.1, clip_end - clip_start)
        step = max(FRAME_EVERY_S, span / MAX_FRAMES)
        n = max(1, int(span // step) + 1)
        times = [round(clip_start + min(i * step, span - 0.1) if span > 0.1 else clip_start, 2) for i in range(n)]
        frames: List[Tuple[str, bytes]] = []
        with tempfile.TemporaryDirectory() as tmp:
            for i, t in enumerate(times):
                jpg = _frame_at(Path(sec_file), min(max(0.0, t - sec_start), sec_dur - 0.1), Path(tmp) / f"f{i}.jpg")
                frames.append((f"Frame {i} (at {t - clip_start:.1f}s into the clip):", jpg))
        prompt = (
            f"These {n} frames come from one clip of a landscape stream that will be cut into a 9:16 vertical short.\n"
            f"For each frame pick the framing layout that shows its most important content:\n{LAYOUT_RULES}\n"
            "A streamer can switch between these during a clip. Label every frame on its own merits. "
            'Return JSON {"frames": [{"i": 0, "layout": "..."}, ...]} with one entry per frame.'
        )
        got = {f.i: f.layout for f in _ask(frames, prompt, FrameLabels).frames}
        labels = [got.get(i) for i in range(n)]
        if None in labels:
            raise ValueError("model skipped frames")
        runs = smooth_runs(times, labels, clip_end)
        plan = [{"t": round(clip_start, 2), "layout": runs[0][1]}]
        plan += [{"t": snap_to_pause(t, words), "layout": lay} for t, lay in runs[1:]]
        print("  [layout] auto plan: " + ", ".join(f"{p['layout']}@{p['t'] - clip_start:.1f}s" for p in plan))
        return plan
    except Exception as e:
        print(f"  [layout] AI plan failed ({e}); using the face-size heuristic")
        return None
