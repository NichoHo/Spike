"""
Anime skip mask (report sections 5.3 and 5.4): OP, ED, recap and preview spans that must never become clips.
Stage 4 part: fetch_aniskip -> aniskip.json (one API call per episode, cached).
Mask part: build_skip -> skip.json, from AniSkip, chapters, subtitle song lines, the preview rule and a
music-dominant fallback. drop_skipped removes candidates that overlap a skip span by more than 20%.
Not built: Chromaprint matching across a season (source 6) and the eyecatch heuristic (source 7).
"""

import json
import re
import subprocess
import urllib.error
import urllib.request
from pathlib import Path
from typing import Any, Dict, List, Optional

import numpy as np

ANISKIP_URL = "https://api.aniskip.com/v2/skip-times/{mal_id}/{episode}"
ANISKIP_TYPES = "types=op&types=ed&types=mixed-op&types=mixed-ed&types=recap"
LENGTH_TOLERANCE_S = 5.0
PAL_RATIO = 25 / 23.976          # 25 fps PAL speed-up of a 23.976 fps master
PAD_S = 2.0
MAX_OVERLAP = 0.20
CHAPTER_RE = re.compile(r"^(opening|op|intro|ending|ed|credits|preview|next episode|recap|previously)\b", re.I)
PARODY_MUSIC_MIN, PARODY_SPEECH_MAX = 0.6, 0.3
FALLBACK_MUSIC_MIN, FALLBACK_SPEECH_MAX = 0.7, 0.2


def _fetch(mal_id: int, episode: int, length_s: float) -> List[Dict[str, Any]]:
    url = f"{ANISKIP_URL.format(mal_id=mal_id, episode=episode)}?{ANISKIP_TYPES}&episodeLength={length_s}"
    req = urllib.request.Request(url, headers={"User-Agent": "Spike/1.0"})
    try:
        with urllib.request.urlopen(req, timeout=20) as r:
            return json.loads(r.read()).get("results") or []
    except urllib.error.HTTPError as e:
        if e.code == 404:  # nothing found; the API also answers 404 when episodeLength is off by more than it tolerates
            return []
        raise


def align_aniskip(results: List[Dict[str, Any]], local_s: float) -> List[Dict[str, Any]]:
    """Spans in local time. Same length (within 5 s): as is. PAL speed-up: scaled. Anything else cannot be aligned
    without a locally detected OP start, so it is dropped and the other skip sources cover it."""
    spans = []
    for r in results:
        length = float(r.get("episodeLength") or 0)
        if length <= 0 or abs(length - local_s) <= LENGTH_TOLERANCE_S:
            k = 1.0
        elif abs(local_s / length - PAL_RATIO) < 0.01 or abs(length / local_s - PAL_RATIO) < 0.01:
            k = local_s / length
        else:
            continue
        iv = r["interval"]
        spans.append({"kind": r["skipType"].replace("mixed-", ""), "start": iv["startTime"] * k,
                      "end": iv["endTime"] * k, "source": "aniskip"})
    return spans


def run_stage4_aniskip(video_dir: Path, meta: Dict[str, Any], anime: Dict[str, Any]) -> List[Dict[str, Any]]:
    """aniskip.json: skip spans in local time. A network failure returns [] without caching, so the next run retries."""
    out = video_dir / "aniskip.json"
    if out.exists():
        return json.loads(out.read_text(encoding="utf-8"))
    mal_id, episode, dur = anime.get("mal_id"), anime.get("episode"), float(meta.get("duration") or 0)
    if not (mal_id and episode and dur):
        return []
    try:
        results = _fetch(mal_id, episode, round(dur, 1)) or _fetch(mal_id, episode, 0)
    except Exception as e:
        print(f"  [stage 4] AniSkip skipped: {e}")
        return []
    spans = align_aniskip(results, dur)
    out.write_text(json.dumps(spans, indent=2), encoding="utf-8")
    print(f"  [stage 4] AniSkip: {len(spans)} span(s)")
    return spans


def read_chapters(path: Optional[str]) -> List[Dict[str, Any]]:
    if not path:
        return []
    res = subprocess.run(["ffprobe", "-v", "error", "-show_chapters", "-of", "json", path], capture_output=True, text=True)
    try:
        chs = json.loads(res.stdout).get("chapters", [])
    except json.JSONDecodeError:
        return []
    return [{"title": (c.get("tags") or {}).get("title", ""), "start": float(c["start_time"]), "end": float(c["end_time"])}
            for c in chs]


def _kind_of_title(title: str) -> str:
    t = title.strip().lower()
    if t.startswith(("opening", "op", "intro")):
        return "op"
    if t.startswith(("ending", "ed", "credits")):
        return "ed"
    return "other"  # preview, next episode, recap


def song_spans_to_skips(song_spans: List[Any], duration: float) -> List[Dict[str, Any]]:
    """Group karaoke/song subtitle lines (gap <= 5 s) into runs of at least 30 s; a run in the first half is the OP."""
    out, cur = [], None
    for s, e in sorted(map(tuple, song_spans)):
        if cur and s - cur[1] <= 5:
            cur[1] = max(cur[1], e)
        else:
            if cur:
                out.append(cur)
            cur = [s, e]
    if cur:
        out.append(cur)
    return [{"kind": "op" if (a + b) / 2 < duration / 2 else "ed", "start": a, "end": b, "source": "subtitle_songs"}
            for a, b in out if b - a >= 30]


def music_fallback(music_p: np.ndarray, speech_p: np.ndarray, duration: float,
                   have_op: bool, have_ed: bool) -> List[Dict[str, Any]]:
    """A 60 to 120 s music-dominant run inside the first or last 25% is a likely OP or ED."""
    n = min(len(music_p), len(speech_p), int(duration))
    ok = (music_p[:n] > FALLBACK_MUSIC_MIN) & (speech_p[:n] < FALLBACK_SPEECH_MAX)
    # close 5 s holes so a quiet beat inside the song does not split it
    ok = np.convolve(ok.astype(float), np.ones(5) / 5, mode="same") >= 0.4
    runs, i = [], 0
    while i < n:
        if ok[i]:
            j = i
            while j < n and ok[j]:
                j += 1
            runs.append((i, j))
            i = j
        else:
            i += 1
    out = []
    for a, b in runs:
        if not 60 <= b - a <= 120:
            continue
        if a < 0.25 * n and not have_op:
            out.append({"kind": "op", "start": float(a), "end": float(b), "source": "music_fallback"})
            have_op = True
        elif b > 0.75 * n and not have_ed:
            out.append({"kind": "ed", "start": float(a), "end": float(b), "source": "music_fallback"})
            have_ed = True
    return out


def build_skip(video_dir: Path, meta: Dict[str, Any], anime: Dict[str, Any], transcript: Dict[str, Any],
               aniskip: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """Merge every source into skip.json (a list of {kind, start, end, source}) and return it."""
    dur = float(meta.get("duration") or 0)
    sig = video_dir / "signals.npz"
    arch = np.load(sig) if sig.exists() else {}
    music_p, speech_p = arch.get("music_p"), arch.get("speech_p")
    have_series = music_p is not None and speech_p is not None

    spans: List[Dict[str, Any]] = []
    for s in aniskip:
        a, b = int(s["start"]), max(int(s["end"]), int(s["start"]) + 1)
        if anime.get("parody") and have_series:  # parody dubs often change or drop the OP
            if not (music_p[a:b].mean() > PARODY_MUSIC_MIN and speech_p[a:b].mean() < PARODY_SPEECH_MAX):
                continue
        spans.append({**s, "start": max(0.0, s["start"] - PAD_S), "end": min(dur, s["end"] + PAD_S)})
    for c in read_chapters(meta.get("local_path")):
        if CHAPTER_RE.match(c["title"].strip()):
            spans.append({"kind": _kind_of_title(c["title"]), "start": c["start"], "end": c["end"], "source": "chapter"})
    spans += song_spans_to_skips(transcript.get("song_spans") or [], dur)
    if have_series:
        spans += music_fallback(music_p, speech_p, dur, any(s["kind"] == "op" for s in spans),
                                any(s["kind"] == "ed" for s in spans))
    # preview rule: everything after the last ED to the end of the episode
    eds = [s["end"] for s in spans if s["kind"] == "ed"]
    if eds and dur and dur - max(eds) > 1:
        spans.append({"kind": "preview", "start": max(eds), "end": dur, "source": "preview_rule"})
    (video_dir / "skip.json").write_text(json.dumps(spans, indent=2), encoding="utf-8")
    print(f"  [skip] {len(spans)} skip span(s): " + ", ".join(f"{s['kind']}@{s['start']:.0f}-{s['end']:.0f}" for s in spans))
    return spans


def overlap_fraction(spans: List[Dict[str, Any]], start: float, end: float) -> float:
    """Share of [start, end] inside the union of the skip spans."""
    if end <= start:
        return 0.0
    merged: List[List[float]] = []
    for s in sorted(spans, key=lambda s: s["start"]):
        if merged and s["start"] <= merged[-1][1]:
            merged[-1][1] = max(merged[-1][1], s["end"])
        else:
            merged.append([s["start"], s["end"]])
    return sum(max(0.0, min(end, b) - max(start, a)) for a, b in merged) / (end - start)


def drop_skipped(candidates: List[Dict[str, Any]], video_dir: Path) -> List[Dict[str, Any]]:
    """Remove candidates whose window overlaps a skip span by more than 20%. No skip.json (not an anime run): unchanged."""
    path = video_dir / "skip.json"
    if not path.exists():
        return candidates
    spans = json.loads(path.read_text(encoding="utf-8"))
    kept = [c for c in candidates if overlap_fraction(spans, c["clip_start"], c["clip_end"]) <= MAX_OVERLAP]
    if len(kept) != len(candidates):
        print(f"  [skip] Dropped {len(candidates) - len(kept)} candidate(s) inside OP/ED/recap/preview.")
    return kept


if __name__ == "__main__":
    # alignment: same length, PAL, unalignable
    r = [{"interval": {"startTime": 60, "endTime": 150}, "skipType": "mixed-op", "episodeLength": 1440}]
    assert align_aniskip(r, 1442)[0]["kind"] == "op"
    pal = align_aniskip(r, 1440 / PAL_RATIO)[0]
    assert abs(pal["start"] - 60 / PAL_RATIO) < 1e-6
    assert align_aniskip(r, 1200) == []
    # chapters and songs
    assert CHAPTER_RE.match("Opening") and CHAPTER_RE.match("Next Episode Preview") and not CHAPTER_RE.match("Part A")
    assert _kind_of_title("Credits") == "ed" and _kind_of_title("Intro") == "op"
    songs = [(10, 40), (42, 100), (1300, 1400), (700, 705)]
    assert [s["kind"] for s in song_spans_to_skips(songs, 1440)] == ["op", "ed"]
    # overlap and drop
    sp = [{"kind": "op", "start": 60, "end": 150, "source": "x"}]
    assert overlap_fraction(sp, 100, 200) == 0.5 and overlap_fraction(sp, 200, 300) == 0.0
    # music fallback finds a 90 s OP in the first quarter, ignores a 30 s music burst
    m, sp_ = np.zeros(1400), np.ones(1400)
    m[30:120], sp_[30:120] = 0.9, 0.0
    m[600:630], sp_[600:630] = 0.9, 0.0
    fb = music_fallback(m, sp_, 1400, False, False)
    assert len(fb) == 1 and fb[0]["kind"] == "op" and 28 <= fb[0]["start"] <= 32, fb
    print("ok")
