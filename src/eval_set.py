"""
Spike: per-category eval set (reports/Funny moment detection by creator.md, phase 0).
Frozen Twitch VODs with community clips as labels, scored against baselines so every detection change is measured
as lift, per creator category.

- build: fetch each VOD's community clips and chat into data/eval/<vod>/ (VODs expire; labels are frozen once).
- run:   process each VOD's slice through Spike with the community clips held out (they are the answer key).
- score: HIT@1, Recall@5/10 and NDCG@10 for Spike, an untuned chat_users baseline and random picks, at a strict and
         a loose tolerance, macro-averaged per category.

Labels. A clip cut from the VOD later starts at the moment; a clip made live ends at it (the live capture runs
backward from the click). Each clip is reduced to that moment point, points within 20 s are one moment, and a
moment's weight is its number of distinct clippers. Moments with one clipper are dropped as noise.
"""

import json
import math
import random
from datetime import datetime
from pathlib import Path
from statistics import median
from typing import Any, Dict, List, Optional, Tuple

from src.config import DATA_DIR, PICK_SPACING_S

EVAL_DIR = DATA_DIR / "eval"
SET_FILE = EVAL_DIR / "set.json"
MERGE_S = 20.0
TOLERANCES = {"strict": 5.0, "loose": 20.0}
TOP_MOMENTS = 10      # Recall@K is measured against the VOD's 10 most-clipped moments
MIN_CLIPPERS = 2


def _ts(s: Optional[str]) -> Optional[float]:
    return datetime.fromisoformat(s.replace("Z", "+00:00")).timestamp() if s else None


def moment_point(clip: Dict[str, Any]) -> Optional[float]:
    """VOD second the clip is about: its end for a live clip, its start for one cut from the VOD later."""
    off = clip.get("vod_offset")
    if off is None:
        return None
    dur = float(clip.get("duration") or 30)
    made, vod_start = _ts(clip.get("created_at")), _ts(clip.get("vod_created_at"))
    live = made is not None and vod_start is not None and made <= vod_start + off + dur + 300
    return float(off) + (dur - 3.0 if live else 3.0)


def label_moments(clips: List[Dict[str, Any]], limit_s: Optional[float] = None) -> List[Dict[str, Any]]:
    """Clips merged into moments, most-clipped first: [{t, clippers, views}]."""
    pts = sorted(((p, c) for c in clips if (p := moment_point(c)) is not None and (limit_s is None or p <= limit_s)),
                 key=lambda pc: pc[0])
    groups: List[List[Tuple[float, Dict[str, Any]]]] = []
    for p, c in pts:
        if groups and p - groups[-1][0][0] <= MERGE_S:
            groups[-1].append((p, c))
        else:
            groups.append([(p, c)])
    out = []
    for g in groups:
        clippers = {c.get("creator_id") for _, c in g}
        if len(clippers) >= MIN_CLIPPERS:
            out.append({"t": round(median(p for p, _ in g), 1), "clippers": len(clippers),
                        "views": sum(int(c.get("view_count") or 0) for _, c in g)})
    return sorted(out, key=lambda m: (m["clippers"], m["views"]), reverse=True)


# ── Metrics ───────────────────────────────────────────────────────────────────

def _hit(pred: Tuple[float, float], t: float, tol: float) -> bool:
    return pred[0] - tol <= t <= pred[1] + tol


def score_ranking(preds: List[Tuple[float, float]], moments: List[Dict[str, Any]], tol: float) -> Dict[str, float]:
    """HIT@1, Recall@5/10 against the top moments, NDCG@10 with clippers as gain. A moment counts once."""
    top = moments[:TOP_MOMENTS]

    def found(k: int) -> int:
        return sum(any(_hit(p, m["t"], tol) for p in preds[:k]) for m in top)

    gains, used = [], set()
    for p in preds[:10]:
        g = 0.0
        for i, m in enumerate(moments):
            if i not in used and _hit(p, m["t"], tol):
                used.add(i)
                g = float(m["clippers"])
                break
        gains.append(g)
    dcg = sum(g / math.log2(i + 2) for i, g in enumerate(gains))
    ideal = sorted((float(m["clippers"]) for m in moments), reverse=True)[:10]
    idcg = sum(g / math.log2(i + 2) for i, g in enumerate(ideal))
    n = max(1, len(top))
    return {
        "hit@1": float(bool(preds) and any(_hit(preds[0], m["t"], tol) for m in moments)),
        "recall@5": found(5) / n, "recall@10": found(10) / n,
        "ndcg@10": dcg / idcg if idcg else 0.0,
    }


# ── Arms ──────────────────────────────────────────────────────────────────────

def random_preds(duration_s: float, seed: int, k: int = 10, span: float = 35.0) -> List[Tuple[float, float]]:
    rng = random.Random(seed)
    out = []
    for _ in range(k):
        st = rng.uniform(0, max(1.0, duration_s - span))
        out.append((st, st + span))
    return out


def chat_preds(comments: List[Dict[str, Any]], duration_s: float) -> List[Tuple[float, float]]:
    from src.eval import compute_chat_users_baseline
    return [(c["start_s"], c["end_s"]) for c in compute_chat_users_baseline(comments, int(duration_s), k=10)]


def rank_preds(cands: List[Dict[str, Any]], gap_s: Optional[float] = PICK_SPACING_S) -> List[Tuple[float, float]]:
    """Spike's ranking: selected clips by final score, then every other judged moment by final score. A pick
    within gap_s of a better one (centre to centre) moves behind all the spaced picks; gap_s None keeps the plain
    order. Concept clips count by all their stretches; hubris lines are not moments."""
    from src.eval import _intervals
    cands = sorted((c for c in cands if c.get("status") != "hubris"),
                   key=lambda c: (c.get("status") == "selected", c.get("final_score") or 0), reverse=True)
    head: List[Tuple[float, float]] = []
    tail: List[Tuple[float, float]] = []
    centres: List[float] = []
    for c in cands:
        ivs = _intervals(c)
        mid = (min(a for a, _ in ivs) + max(b for _, b in ivs)) / 2.0
        if gap_s is None or all(abs(mid - x) >= gap_s for x in centres):
            centres.append(mid)
            head.extend(ivs)
        else:
            tail.extend(ivs)
    return head + tail


def spike_preds(video_id: int, gap_s: Optional[float] = PICK_SPACING_S) -> List[Tuple[float, float]]:
    from src.eval import load_db_candidates
    return rank_preds(load_db_candidates(video_id), gap_s)


# ── Commands ──────────────────────────────────────────────────────────────────

def load_set() -> List[Dict[str, Any]]:
    """data/eval/set.json: {"vods": [{"vod": "2896498763", "category": "irl", "slice_s": 5400}, ...]}"""
    return json.loads(SET_FILE.read_text(encoding="utf-8"))["vods"]


def build() -> None:
    from src.pipeline.stage3_chat import run_stage3_chat
    from src.pipeline.stage4_crowd import fetch_twitch_community_clips
    for v in load_set():
        d = EVAL_DIR / v["vod"]
        d.mkdir(parents=True, exist_ok=True)
        labels = d / "clips.json"
        if not labels.exists():
            clips = fetch_twitch_community_clips(v["vod"], max_pages=20)
            if not clips:
                print(f"  {v['vod']}: no clips returned (VOD gone or Twitch keys missing); skipped")
                continue
            labels.write_text(json.dumps(clips), encoding="utf-8")
        url = f"https://www.twitch.tv/videos/{v['vod']}"
        run_stage3_chat(d, {"webpage_url": url}, url, limit_s=v.get("slice_s"))
        n = len(label_moments(json.loads(labels.read_text(encoding="utf-8")), v.get("slice_s")))
        print(f"  {v['vod']} ({v['category']}): {n} labelled moments in the slice")


def find_video_id(vod: str) -> Optional[int]:
    from src.db import get_connection
    with get_connection() as conn:
        row = conn.execute("SELECT id FROM videos WHERE url LIKE ? AND status = 'ready' ORDER BY id DESC LIMIT 1",
                           (f"%/videos/{vod}%",)).fetchone()
    return int(row[0]) if row else None


def run(only: Optional[str] = None) -> None:
    """Queue each unfinished eval VOD as a worker job, oldest VOD first (lower priority number runs later, so
    priority falls along the list). The eval settings live on the job row: a worker that restarts and requeues
    the job keeps them. Running the pipeline in this process instead let a restarted worker start a second copy
    of the same VOD without the settings, so it saw the held-out clips."""
    from src.db import register_video
    todo = [v for v in load_set() if (not only or v["vod"] == only) and not find_video_id(v["vod"])]
    for i, v in enumerate(todo):
        chat = EVAL_DIR / v["vod"] / "chat.json"
        vid = register_video("url", f"https://www.twitch.tv/videos/{v['vod']}", priority=len(todo) - i, settings={
            "max_process_s": v.get("slice_s"), "holdout_clips": True, "stop_after": "moments",
            **({"chat_file": str(chat)} if chat.exists() else {}),
        })
        print(f"  queued {v['vod']} ({v['category']}) as video {vid}")
    print("The worker runs them (start it with `py spike.py web` or `py spike.py worker`).")


def score() -> Dict[str, Any]:
    rows: Dict[str, Dict[str, Dict[str, List[float]]]] = {}  # category -> arm@tol -> metric -> values
    for v in load_set():
        d = EVAL_DIR / v["vod"]
        if not (d / "clips.json").exists():
            continue
        moments = label_moments(json.loads((d / "clips.json").read_text(encoding="utf-8")), v.get("slice_s"))
        if not moments:
            continue
        chat_file = d / "chat.json"
        comments = json.loads(chat_file.read_text(encoding="utf-8")).get("comments", []) if chat_file.exists() else []
        dur = float(v.get("slice_s") or max(m["t"] for m in moments) + 60)
        arms = {"chat": chat_preds(comments, dur) if comments else None}
        vid = find_video_id(v["vod"])
        arms["spike"] = spike_preds(vid) if vid else None
        for tol_name, tol in TOLERANCES.items():
            scored = {arm: score_ranking(preds, moments, tol) for arm, preds in arms.items() if preds is not None}
            for arm, sc in scored.items():
                cell = rows.setdefault(v["category"], {}).setdefault(f"{arm}@{tol_name}", {})
                for k, val in sc.items():
                    cell.setdefault(k, []).append(val)
            if "spike" in scored and "chat" in scored:  # lift is paired: the same VODs on both sides
                cell = rows[v["category"]][f"spike@{tol_name}"]
                cell.setdefault("lift", []).append(scored["spike"]["recall@10"] - scored["chat"]["recall@10"])
            rand = [score_ranking(random_preds(dur, s), moments, tol) for s in range(20)]
            cell = rows.setdefault(v["category"], {}).setdefault(f"random@{tol_name}", {})
            for k in rand[0]:
                cell.setdefault(k, []).append(sum(r[k] for r in rand) / len(rand))
    return {cat: {arm: {k: sum(x) / len(x) for k, x in m.items()} | {"n": len(m["recall@10"])}
                  for arm, m in arms.items()} for cat, arms in rows.items()}


def print_report(result: Dict[str, Any]) -> None:
    for tol in TOLERANCES:
        print(f"\n== {tol} tolerance (±{TOLERANCES[tol]:.0f} s) ==")
        print(f"{'category':<16}{'arm':<8}{'n':>3}{'HIT@1':>8}{'R@5':>7}{'R@10':>7}{'NDCG@10':>9}{'lift R@10 vs chat':>19}")
        macro: Dict[str, List[float]] = {}
        for cat, arms in sorted(result.items()):
            for arm in ("spike", "chat", "random"):
                m = arms.get(f"{arm}@{tol}")
                if not m:
                    continue
                lift = f"{m['lift']:+.3f}" if "lift" in m else ""
                print(f"{cat:<16}{arm:<8}{m['n']:>3}{m['hit@1']:>8.2f}{m['recall@5']:>7.2f}{m['recall@10']:>7.2f}{m['ndcg@10']:>9.3f}{lift:>19}")
                macro.setdefault(arm, []).append(m["recall@10"])
        print("macro R@10: " + ", ".join(f"{a} {sum(x) / len(x):.3f}" for a, x in macro.items()))
