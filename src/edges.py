"""
Spike: clip edge helpers (Blueprint §6.7): phrase lines, start/end edges, cut lines.
Shared by the stage 7 judge pass and the Claude editor pass.
"""

from typing import Any, Dict, Iterable, List, Tuple

import numpy as np

from src.models import LLMJudgeResponse

ZOOM_SCALE_RANGE = (1.05, 1.5)
ZOOM_HOLD_RANGE = (0.3, 4.0)
MAX_ZOOMS = 3
PHRASE_MAX_S = 2.5
END_PAD_S = 0.8
PAUSE_SNAP_S = 0.4
# A model that wants to cut more than a quarter of a clip has misread a rant or a build-up as fluff
# (Ludwig VOD ml1-FLS-yfQ: 24 s of a 49 s rant marked as filler). Above this share no line is cut.
MAX_CUT_SHARE = 0.25


def split_into_phrases(segments: List[Dict[str, Any]], max_s: float = PHRASE_MAX_S) -> List[Dict[str, Any]]:
    """Split Whisper segments into phrases (break at punctuation, or every 2.5 s) so judge lines are short
    enough for precise edges (§6.7). Segments without word timings stay whole."""
    out: List[Dict[str, Any]] = []
    for seg in segments:
        words = seg.get("words") or []
        if not words:
            out.append(seg)
            continue
        cur: List[Dict[str, Any]] = []

        def flush():
            if cur:
                out.append({
                    "start": cur[0]["start"], "end": cur[-1]["end"],
                    "text": "".join(w.get("word", "") for w in cur).strip(), "words": list(cur),
                })
                cur.clear()

        for w in words:
            cur.append(w)
            tail = w.get("word", "").rstrip()
            dur = w["end"] - cur[0]["start"]
            if tail.endswith((".", "?", "!", "\u2026", ";", ":")) or dur >= max_s or (tail.endswith(",") and dur >= 1.5):
                flush()
        flush()
    return out


def snap_start_to_pause(start_s: float, lowest_s: float, words: List[Dict[str, Any]]) -> float:
    """Move the start to the nearest word that follows a pause of 0.4 s or more, never earlier than lowest_s
    (the topic start) and at most 1 s later than asked."""
    best, best_gap = start_s, None
    for prev, w in zip(words, words[1:]):
        ws = float(w.get("start", 0))
        if ws - float(prev.get("end", 0)) >= PAUSE_SNAP_S and lowest_s <= ws <= start_s + 1.0:
            gap = abs(ws - start_s)
            if best_gap is None or gap < best_gap:
                best, best_gap = ws, gap
    return max(lowest_s, best - 0.1) if best_gap is not None else start_s


def extend_end(end_s: float, max_ext_s: float, series: List[Tuple[np.ndarray, float]]) -> float:
    """Keep the clip running while voice jump, shout or laughter stays high, up to max_ext_s, then pad."""
    limit = end_s + max_ext_s

    def high(sec: int) -> bool:
        return any(thr > 0 and sec < len(a) and a[sec] >= thr for a, thr in series)

    sec = int(end_s)
    if not high(sec) and high(sec + 1):  # laughter or a shout often starts the second after the last word
        sec += 1
    while sec < limit and high(sec):
        sec += 1
    return max(end_s, min(float(sec), limit)) + END_PAD_S


def lines_to_cuts(
    line_meta: List[Dict[str, Any]],
    positions: Iterable[int],
    start_s: float,
    end_s: float,
) -> List[List[float]]:
    """Removed intervals for the given line positions, clamped to the clip. Neighbouring lines merge.
    Returns [] when the cuts would remove more than MAX_CUT_SHARE of the clip (the model misjudged what is fluff)."""
    cuts: List[List[float]] = []
    for i in sorted(set(positions)):
        lo, hi = max(start_s, line_meta[i]["start"]), min(end_s, line_meta[i]["end"])
        if hi - lo < 0.3:
            continue
        if cuts and lo - cuts[-1][1] <= 0.3:
            cuts[-1][1] = hi
        else:
            cuts.append([round(lo, 2), round(hi, 2)])
    if sum(h - l for l, h in cuts) > MAX_CUT_SHARE * (end_s - start_s):
        return []
    return cuts


def compute_edges(
    line_meta: List[Dict[str, Any]],
    judge: LLMJudgeResponse,
    preset: Dict[str, Any],
    series: List[Tuple[np.ndarray, float]],
) -> Dict[str, Any]:
    """Clip edges from the judge's structure lines (§6.7), replacing the old snap_boundaries:
    start = later of topic start and (setup start - setup pad), snapped to a pause;
    end = reaction end, extended while the audio stays high, plus 0.8 s;
    no lines are cut: the judge's cut_lines cut the build-up before the punchline in every clip of Ludwig VOD
    ml1-FLS-yfQ (8 to 24 s per clip), which is the funny part of a rant. Pauses are still trimmed at render.
    Returns start_s, end_s, cuts, payoff_t, net_dur."""
    n = len(line_meta)

    def idx(v: int) -> int:
        return max(1, min(int(v), n)) - 1

    topic = idx(judge.topic_start_line)
    setup = max(topic, idx(judge.setup_start_line))
    payoff = max(setup, idx(judge.payoff_line))
    reaction = max(payoff, idx(judge.reaction_end_line))

    topic_t = line_meta[topic]["start"]
    start = max(topic_t, line_meta[setup]["start"] - preset["setup_pad_s"])
    words = [w for lm in line_meta for w in lm.get("words", [])]
    start = snap_start_to_pause(start, topic_t, words)
    end = extend_end(line_meta[reaction]["end"], preset["end_extend_max_s"], series)

    return {
        "start_s": start, "end_s": end, "cuts": [], "payoff_t": line_meta[payoff]["start"],
        "net_dur": end - start,
        "payoff": payoff, "topic": topic, "reaction": reaction,
    }


def clean_zooms(items: Any, start_s: float, end_s: float) -> List[Dict[str, float]]:
    """Zoom list [{t, scale, hold_s}] from untrusted input (the model, a form): bad items dropped, values clamped,
    sorted by time. t must lie inside the clip."""
    out: List[Dict[str, float]] = []
    for it in items if isinstance(items, list) else []:
        try:
            t, scale, hold = float(it["t"]), float(it["scale"]), float(it["hold_s"])
        except (TypeError, KeyError, ValueError):
            continue
        if start_s <= t <= end_s:
            out.append({
                "t": round(t, 2),
                "scale": round(min(max(scale, ZOOM_SCALE_RANGE[0]), ZOOM_SCALE_RANGE[1]), 2),
                "hold_s": round(min(max(hold, ZOOM_HOLD_RANGE[0]), ZOOM_HOLD_RANGE[1]), 2),
            })
    return sorted(out, key=lambda z: z["t"])[:MAX_ZOOMS]


def clean_cuts(items: Any, start_s: float, end_s: float) -> List[List[float]]:
    """Cut list [[start_s, end_s]] from untrusted input: clamped to the clip, 0.2 s or longer, merged, sorted."""
    spans = []
    for it in items if isinstance(items, list) else []:
        try:
            a, b = float(it[0]), float(it[1])
        except (TypeError, IndexError, ValueError):
            continue
        a, b = max(start_s, min(a, b)), min(end_s, max(a, b))
        if b - a >= 0.2:
            spans.append([a, b])
    merged: List[List[float]] = []
    for a, b in sorted(spans):
        if merged and a <= merged[-1][1]:
            merged[-1][1] = max(merged[-1][1], b)
        else:
            merged.append([a, b])
    return [[round(a, 2), round(b, 2)] for a, b in merged]
