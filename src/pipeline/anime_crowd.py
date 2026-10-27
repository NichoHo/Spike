"""
Anime crowd seeds (report section 5.3, phase 7). Two legal, download-free sources:
  title match   viral Shorts of the show (YouTube search + view counts) whose titles quote a line of this episode
  comments      timestamped comments on an official upload of the same episode
Both are opt-in through the job's `anime` settings: {"title_match": true, "youtube_url": "...", "youtube_offset_s": 0}.
Output: data/videos/<id>/anime_crowd.json (fetched once), seeds built per run from it.
A seed is {id, t, weight 0..1, source, label}. Stage 7 marks them for the judge, scores candidates with C, and sends
unjudged seeds to the video check.
"""

import difflib
import json
import math
import re
import urllib.parse
import urllib.request
from pathlib import Path
from typing import Any, Dict, List, Optional

from src.config import DATA_DIR, youtube_keys

MIN_VIEWS = 50_000
MATCH_MIN = 0.85
MIN_MATCH_CHARS = 12      # a shorter string matches almost any window
MAX_SEEDS = 10
CLUSTER_S = 15.0
SEED_HALF_WINDOW_S = 15.0
CACHE_DIR = DATA_DIR / "anime_cache"


def _api(endpoint: str, params: Dict[str, Any]) -> Dict[str, Any]:
    url = f"https://www.googleapis.com/youtube/v3/{endpoint}?{urllib.parse.urlencode({**params, 'key': youtube_keys()[0]})}"
    with urllib.request.urlopen(urllib.request.Request(url, headers={"User-Agent": "Spike/1.0"}), timeout=20) as r:
        return json.loads(r.read())


def fetch_title_clips(show_title: str, anilist_id: int) -> List[Dict[str, Any]]:
    """[{title, views, id}] of short videos about the show with at least MIN_VIEWS views. 101 quota units, cached per show."""
    CACHE_DIR.mkdir(parents=True, exist_ok=True)
    cache = CACHE_DIR / f"{anilist_id}_clips.json"
    if cache.exists():
        return json.loads(cache.read_text(encoding="utf-8"))
    found = _api("search", {"part": "snippet", "q": f'"{show_title} clip"', "type": "video",
                            "videoDuration": "short", "maxResults": 50}).get("items", [])
    ids = [i["id"]["videoId"] for i in found if i.get("id", {}).get("videoId")]
    titles = {i["id"]["videoId"]: i["snippet"]["title"] for i in found if i.get("id", {}).get("videoId")}
    out = []
    if ids:
        for v in _api("videos", {"part": "statistics", "id": ",".join(ids)}).get("items", []):
            views = int(v.get("statistics", {}).get("viewCount", 0))
            if views >= MIN_VIEWS:
                out.append({"id": v["id"], "title": titles.get(v["id"], ""), "views": views})
    cache.write_text(json.dumps(out), encoding="utf-8")
    return out


def clean_title(t: str) -> str:
    """Drop [channel tags], anything after | or (, then lower-case and strip punctuation."""
    t = re.sub(r"\[[^\]]*\]", " ", t)
    t = re.split(r"[|(]", t)[0]
    return re.sub(r"\s+", " ", re.sub(r"[^\w\s]", "", t.lower())).strip()


def partial_ratio(a: str, b: str) -> float:
    """Best similarity of the shorter string against equal-length windows of the longer (rapidfuzz's partial_ratio, stdlib)."""
    short, long_ = (a, b) if len(a) <= len(b) else (b, a)
    if len(short) < MIN_MATCH_CHARS:
        return 0.0
    n = len(short)
    best = 0.0
    for i in range(0, max(1, len(long_) - n + 1)):
        sm = difflib.SequenceMatcher(None, short, long_[i:i + n], autojunk=False)
        if sm.real_quick_ratio() > best and sm.quick_ratio() > best:
            best = max(best, sm.ratio())
            if best >= 1.0:
                break
    return best


def title_seeds(clips: List[Dict[str, Any]], lines: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """A clip title that matches a transcript line, or two joined lines, at 0.85 or more seeds that line's time.
    Weight is log10(views) over the largest log10(views) among the matches. Titles that quote nothing do not match."""
    texts = [clean_title(ln["text"]) for ln in lines]
    units = [(texts[i], lines[i]["start"]) for i in range(len(lines))]
    units += [(texts[i] + " " + texts[i + 1], lines[i]["start"]) for i in range(len(lines) - 1)]
    hits = []
    for c in clips:
        title = clean_title(c["title"])
        if len(title) < MIN_MATCH_CHARS:
            continue
        best = max(((partial_ratio(title, u), t) for u, t in units if u), default=(0.0, 0.0))
        if best[0] >= MATCH_MIN:
            hits.append({"t": float(best[1]), "views": c["views"], "label": c["title"]})
    top = max((math.log10(h["views"]) for h in hits), default=1.0)
    return [{"id": f"title_{i}", "t": h["t"], "weight": math.log10(h["views"]) / top, "source": "title_match", "label": h["label"]}
            for i, h in enumerate(hits)]


def comment_seeds(comments: List[Dict[str, Any]], duration: float) -> List[Dict[str, Any]]:
    """Timestamps quoted in comments (already on the local timeline), clustered within 15 s; weight is the cluster's
    likes-and-count mass over the largest cluster's."""
    pts = sorted((ts, 1.0 + math.log1p(c.get("likes", 0))) for c in comments for ts in c.get("timestamps", [])
                 if 0 <= ts < duration)
    clusters: List[List[Any]] = []
    for ts, w in pts:
        if clusters and ts - clusters[-1][-1][0] <= CLUSTER_S:
            clusters[-1].append((ts, w))
        else:
            clusters.append([(ts, w)])
    scored = [(sum(w for _, w in c), sum(t * w for t, w in c) / sum(w for _, w in c)) for c in clusters]
    top = max((m for m, _ in scored), default=1.0)
    return [{"id": f"cmt_{i}", "t": t, "weight": m / top, "source": "comment", "label": ""}
            for i, (m, t) in enumerate(sorted(scored, reverse=True))]


def build_seeds(crowd: Dict[str, Any], lines: List[Dict[str, Any]], duration: float,
                skip: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """Up to 10 seeds, heaviest first, none inside the skip mask."""
    from src.pipeline.anime_skip import overlap_fraction
    seeds = title_seeds(crowd.get("clips", []), lines) + comment_seeds(crowd.get("comments", []), duration)
    seeds = [s for s in seeds if overlap_fraction(skip, s["t"] - 2, s["t"] + 2) <= 0.2]
    return sorted(seeds, key=lambda s: s["weight"], reverse=True)[:MAX_SEEDS]


def crowd_score(seeds: List[Dict[str, Any]], start: float, end: float) -> float:
    """C, 0 to 100: the heaviest seed whose window (seed +/- 15 s) overlaps the candidate, else 0."""
    hit = [s["weight"] for s in seeds if s["t"] - SEED_HALF_WINDOW_S < end and s["t"] + SEED_HALF_WINDOW_S > start]
    return 100.0 * max(hit, default=0.0)


def _video_id(url: str) -> Optional[str]:
    m = re.search(r"(?:v=|youtu\.be/|shorts/)([\w-]{11})", url or "")
    return m.group(1) if m else None


def run_stage4_anime_crowd(video_dir: Path, anime: Dict[str, Any], opts: Dict[str, Any]) -> Dict[str, Any]:
    """anime_crowd.json: {"clips": [...], "comments": [...]} with comment timestamps shifted onto the local file's
    timeline by opts["youtube_offset_s"]. Resumes if the file exists; {} when neither source is switched on or keyed.
    ponytail: the offset is the user's (the upload's OP start minus the local file's); auto-aligning needs a second
    AniSkip call for the upload's length."""
    out = video_dir / "anime_crowd.json"
    if out.exists():
        return json.loads(out.read_text(encoding="utf-8"))
    vid = _video_id(opts.get("youtube_url", ""))
    if not (opts.get("title_match") or vid):
        return {}
    if not youtube_keys():
        print("  [stage 4] No YOUTUBE_API_KEY configured; skipping anime crowd seeds.")
        return {}
    crowd: Dict[str, Any] = {"clips": [], "comments": []}
    try:
        if opts.get("title_match") and anime.get("title") and anime.get("anilist_id"):
            crowd["clips"] = fetch_title_clips(anime["title"], anime["anilist_id"])
        if vid:
            from src.pipeline.stage4_crowd import fetch_youtube_comments
            off = float(opts.get("youtube_offset_s", 0.0))
            crowd["comments"] = [{**c, "timestamps": [t - off for t in c.get("timestamps", [])]}
                                 for c in fetch_youtube_comments(vid) if c.get("timestamps")]
    except Exception as e:
        print(f"  [stage 4] Anime crowd seeds skipped: {e}")
        return {}
    out.write_text(json.dumps(crowd), encoding="utf-8")
    print(f"  [stage 4] Anime crowd: {len(crowd['clips'])} viral clip title(s), {len(crowd['comments'])} timestamped comment(s)")
    return crowd


if __name__ == "__main__":
    assert clean_title("[Chan] Piccolo takes WAY too long to charge! | Dragon Ball (2020)") == "piccolo takes way too long to charge"
    assert partial_ratio("takes way too long", "i said that piccolo takes way too long to charge") >= 0.99
    assert partial_ratio("ok", "ok then") == 0.0                      # too short to trust
    assert partial_ratio("completely unrelated title here", "the weather is nice today friend") < 0.85
    lines = [{"start": 10.0, "end": 12.0, "text": "Hey, what are you doing?"},
             {"start": 12.5, "end": 15.0, "text": "I'm waiting for my power to charge up, just give me a minute!"},
             {"start": 40.0, "end": 42.0, "text": "Unrelated."}]
    clips = [{"id": "a", "title": "I'm waiting for my power to charge up (Dub)", "views": 4_000_000},
             {"id": "b", "title": "Totally different joke about cats", "views": 90_000}]
    ts = title_seeds(clips, lines)
    assert len(ts) == 1 and abs(ts[0]["t"] - 12.5) < 1e-9 and ts[0]["weight"] == 1.0, ts
    cm = [{"timestamps": [100.0, 104.0], "likes": 50}, {"timestamps": [101.0], "likes": 0}, {"timestamps": [500.0], "likes": 2},
          {"timestamps": [9999.0], "likes": 9}]
    cs = comment_seeds(cm, 1440)
    assert len(cs) == 2 and cs[0]["weight"] == 1.0 and 100 <= cs[0]["t"] <= 104 and cs[1]["weight"] < 0.5, cs
    seeds = build_seeds({"clips": clips, "comments": cm}, lines, 1440, [{"kind": "op", "start": 490, "end": 510, "source": "x"}])
    assert [s["source"] for s in seeds] == ["title_match", "comment"] and len(seeds) == 2, seeds   # cmt at 500 is in the OP
    assert crowd_score(seeds, 120, 150) == 0.0 and crowd_score(seeds, 20, 60) == 100.0 and crowd_score([], 0, 10) == 0.0
    assert _video_id("https://www.youtube.com/watch?v=dQw4w9WgXcQ&t=5") == "dQw4w9WgXcQ" and _video_id("nope") is None
    print("ok")
