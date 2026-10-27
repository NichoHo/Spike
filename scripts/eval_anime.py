"""
Anime eval (reports/Anime clippable moment detection.md, section 8): score the anime pipeline against a hand-built
answer key of 8 episodes, per group, next to a random and a loudness-only baseline.

    py scripts/eval_anime.py init     # create data/eval_anime/set.json (edit it) and one folder per episode
    py scripts/eval_anime.py run      # queue each episode as a worker job (anime mode, stops after stage 7)
    py scripts/eval_anime.py score    # print the per-group report
    py scripts/eval_anime.py selftest

data/eval_anime/set.json:
  {"episodes": [{"id": "dbza_12", "group": "abridged_comedy", "file": "D:/anime/dbza_12.mkv",
                 "anime": {"anilist_id": 813, "episode": 12, "audio_kind": "abridged"}}]}
Groups: abridged_comedy (2 episodes), shounen_action (2), romance_slice (2), drama_mystery (2). Use files you own.

data/eval_anime/<id>/targets.json: the answer key, 5 to 10 moments per episode, found from official or creator
Shorts cut from the episode (source start and end in the local file's time) and from timestamped comments:
  [{"start_s": 461.0, "end_s": 493.0, "archetype": "comedy_beat", "source": "youtube_short", "views": 4600000}]
"""

import json
import random
import sys
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import numpy as np

from src.config import DATA_DIR, PICK_SPACING_S

EVAL_DIR = DATA_DIR / "eval_anime"
SET_FILE = EVAL_DIR / "set.json"
TOLERANCES = {"loose": 20.0, "strict": 5.0}   # the Twitch TOL, and the boundary-accurate one
TOP_K = 10
IOU_MIN = 0.5
SKIP_MAX_OVERLAP = 0.20
Interval = Tuple[float, float]


# ---- metrics (pure) ---------------------------------------------------------------------------------------------

def hits(pred: Interval, target: Dict[str, Any], tol: float) -> bool:
    """The pick lies within tol seconds of the target's window."""
    return pred[0] - tol <= target["end_s"] and pred[1] + tol >= target["start_s"]


def iou(a: Interval, b: Interval) -> float:
    inter = max(0.0, min(a[1], b[1]) - max(a[0], b[0]))
    return inter / max(1e-9, max(a[1], b[1]) - min(a[0], b[0]))


def score_picks(picks: List[Interval], targets: List[Dict[str, Any]], tol: float) -> Dict[str, float]:
    """recall@5/10, hit@1 (any target) and, among the targets found in the top 10, the share whose best pick has
    IoU >= 0.5 with the target (boundary quality)."""
    top = picks[:TOP_K]
    n = max(1, len(targets))
    found = [t for t in targets if any(hits(p, t, tol) for p in top)]
    good = [t for t in found if max(iou(p, (t["start_s"], t["end_s"])) for p in top if hits(p, t, tol)) >= IOU_MIN]
    return {
        "recall@5": sum(any(hits(p, t, tol) for p in picks[:5]) for t in targets) / n,
        "recall@10": len(found) / n,
        "hit@1": float(bool(picks) and any(hits(picks[0], t, tol) for t in targets)),
        "boundary": len(good) / len(found) if found else 0.0,
    }


def candidate_recall(candidates: List[Interval], targets: List[Dict[str, Any]], tol: float) -> float:
    """Share of targets near any candidate, whatever its status: a miss here is a generator failure, not a ranking one."""
    return sum(any(hits(c, t, tol) for c in candidates) for t in targets) / max(1, len(targets))


def skip_share(picks: List[Interval], skip: List[Dict[str, Any]]) -> float:
    """Share of the top picks that overlap the skip mask by more than 20% (must be 0)."""
    from src.pipeline.anime_skip import overlap_fraction
    top = picks[:TOP_K]
    return sum(overlap_fraction(skip, a, b) > SKIP_MAX_OVERLAP for a, b in top) / max(1, len(top))


def random_picks(duration_s: float, seed: int, k: int = TOP_K, span: float = 35.0) -> List[Interval]:
    rng = random.Random(seed)
    return [(s, s + span) for s in (rng.uniform(0, max(1.0, duration_s - span)) for _ in range(k))]


def loudness_picks(voice_jump: np.ndarray, k: int = TOP_K, gap_s: float = PICK_SPACING_S) -> List[Interval]:
    """The loudest-jump seconds, at least gap_s apart, each as a window from 25 s before to 10 s after."""
    out, taken = [], []
    for t in np.argsort(voice_jump)[::-1]:
        if all(abs(int(t) - x) >= gap_s for x in taken):
            taken.append(int(t))
            out.append((max(0.0, t - 25.0), float(t) + 10.0))
            if len(out) == k:
                break
    return out


# ---- commands ---------------------------------------------------------------------------------------------------

def load_set() -> List[Dict[str, Any]]:
    return json.loads(SET_FILE.read_text(encoding="utf-8"))["episodes"]


def _state() -> Dict[str, int]:
    p = EVAL_DIR / "state.json"
    return json.loads(p.read_text(encoding="utf-8")) if p.exists() else {}


def init() -> None:
    EVAL_DIR.mkdir(parents=True, exist_ok=True)
    if not SET_FILE.exists():
        SET_FILE.write_text(json.dumps({"episodes": []}, indent=2), encoding="utf-8")
    for e in load_set():
        d = EVAL_DIR / e["id"]
        d.mkdir(exist_ok=True)
        if not (d / "targets.json").exists():
            (d / "targets.json").write_text("[]", encoding="utf-8")
    print(f"{SET_FILE}: {len(load_set())} episode(s). Fill in set.json and each targets.json (see the script's docstring).")


def run() -> None:
    from src.db import init_db, register_video
    init_db()
    state = _state()
    for e in load_set():
        if e["id"] in state:
            continue
        if not Path(e["file"]).is_file() or Path(e["file"]).suffix.lower() not in (".mkv", ".mp4", ".avi", ".webm", ".mov", ".m4v"):
            print(f"  {e['id']}: not an existing video file, skipped")
            continue
        state[e["id"]] = register_video("upload", e["file"], title=e["id"], settings={
            "anime": e.get("anime") or {}, "stop_after": "moments"})
        print(f"  queued {e['id']} ({e['group']}) as video {state[e['id']]}")
    (EVAL_DIR / "state.json").write_text(json.dumps(state), encoding="utf-8")
    print("The worker runs them (start it with `py spike.py web` or `py spike.py worker`).")


def _episode_inputs(e: Dict[str, Any], vid: int) -> Optional[Dict[str, Any]]:
    from src.eval import load_db_candidates
    from src.eval_set import rank_preds
    vdir = DATA_DIR / "videos" / str(vid)
    meta_p = vdir / "meta.json"
    if not meta_p.exists() or not (vdir / "candidates.json").exists():
        return None
    cands = load_db_candidates(vid)
    sig = np.load(vdir / "signals.npz") if (vdir / "signals.npz").exists() else {}
    skip_p = vdir / "skip.json"
    return {
        "duration": float(json.loads(meta_p.read_text(encoding="utf-8")).get("duration") or 0),
        "picks": rank_preds(cands),
        "candidates": [(c["start_s"], c["end_s"]) for c in cands if c.get("status") != "hubris"],
        "skip": json.loads(skip_p.read_text(encoding="utf-8")) if skip_p.exists() else [],
        "voice_jump": sig["voice_jump"] if "voice_jump" in sig else None,
    }


def score() -> Dict[str, Any]:
    """group -> arm@tol -> metric -> mean over the group's episodes."""
    acc: Dict[str, Dict[str, Dict[str, List[float]]]] = {}
    state = _state()
    for e in load_set():
        tp = EVAL_DIR / e["id"] / "targets.json"
        targets = json.loads(tp.read_text(encoding="utf-8")) if tp.exists() else []
        inp = _episode_inputs(e, state[e["id"]]) if e["id"] in state else None
        if not targets or not inp:
            print(f"  {e['id']}: {'no targets' if not targets else 'not processed yet'}, skipped")
            continue
        cells = acc.setdefault(e["group"], {})
        arms = {"anime": inp["picks"],
                "random": None,
                "loudness": loudness_picks(inp["voice_jump"]) if inp["voice_jump"] is not None else None}
        for tol_name, tol in TOLERANCES.items():
            for arm, picks in arms.items():
                if arm == "random":
                    runs = [score_picks(random_picks(inp["duration"], s), targets, tol) for s in range(20)]
                    sc = {k: float(np.mean([r[k] for r in runs])) for k in runs[0]}
                elif picks is None:
                    continue
                else:
                    sc = score_picks(picks, targets, tol)
                for k, v in sc.items():
                    cells.setdefault(f"{arm}@{tol_name}", {}).setdefault(k, []).append(v)
            cells.setdefault(f"anime@{tol_name}", {}).setdefault("candidate_recall", []).append(
                candidate_recall(inp["candidates"], targets, tol))
        cells.setdefault("anime@loose", {}).setdefault("skip_share", []).append(skip_share(inp["picks"], inp["skip"]))
    return {g: {arm: {k: float(np.mean(v)) for k, v in m.items()} | {"n": len(next(iter(m.values())))}
                for arm, m in arms.items()} for g, arms in acc.items()}


def report(result: Dict[str, Any]) -> None:
    for tol in TOLERANCES:
        print(f"\n== {tol} tolerance (±{TOLERANCES[tol]:.0f} s) ==")
        print(f"{'group':<18}{'arm':<10}{'n':>3}{'HIT@1':>7}{'R@5':>6}{'R@10':>6}{'bound.':>8}{'cand.R':>8}{'skip':>6}")
        macro: Dict[str, List[float]] = {}
        for g, arms in sorted(result.items()):
            for arm in ("anime", "random", "loudness"):
                m = arms.get(f"{arm}@{tol}")
                if not m:
                    continue
                cr = f"{m['candidate_recall']:.2f}" if "candidate_recall" in m else ""
                sk = f"{arms['anime@loose']['skip_share']:.2f}" if arm == "anime" and tol == "loose" else ""
                print(f"{g:<18}{arm:<10}{m['n']:>3}{m['hit@1']:>7.2f}{m['recall@5']:>6.2f}{m['recall@10']:>6.2f}{m['boundary']:>8.2f}{cr:>8}{sk:>6}")
                macro.setdefault(arm, []).append(m["recall@10"])
            a, r, l = (arms.get(f"{x}@{tol}", {}).get("recall@10") for x in ("anime", "random", "loudness"))
            if a is not None and r is not None:
                beats = a > r and (l is None or a > l)
                print(f"{'':<18}{'-> ' + ('beats both baselines' if beats else 'DOES NOT beat both baselines')}")
        print("macro R@10 (mean of group means): " + ", ".join(f"{a} {np.mean(x):.3f}" for a, x in macro.items()))
    print("\nTune in this order, one group of numbers per run: candidate counts, J weights, profile weights, P slope (0.3 +/- 0.1, 0.3).")


def selftest() -> None:
    T = [{"start_s": 100, "end_s": 130}, {"start_s": 400, "end_s": 430}, {"start_s": 900, "end_s": 930}]
    picks = [(105, 128), (50, 60), (445, 460)]
    loose, strict = score_picks(picks, T, 20.0), score_picks(picks, T, 5.0)
    assert abs(loose["recall@10"] - 2 / 3) < 1e-9 and loose["hit@1"] == 1.0, loose      # T0 and T1 (445-20 <= 430)
    assert abs(loose["boundary"] - 0.5) < 1e-9, loose                                   # T0 IoU .77, T1 IoU 0
    assert abs(strict["recall@10"] - 1 / 3) < 1e-9 and strict["boundary"] == 1.0, strict  # 440 > 430
    assert candidate_recall([(890, 905)], T, 20.0) == 1 / 3
    skip = [{"kind": "op", "start": 0, "end": 90, "source": "x"}]
    assert skip_share([(10, 40), (200, 230)], skip) == 0.5
    jump = np.zeros(300)
    jump[100], jump[110], jump[200] = 5, 4, 3
    assert [round(a + 25) for a, _ in loudness_picks(jump, k=2)] == [100, 200]   # 110 is within 45 s of 100
    assert len(random_picks(1440, 1)) == TOP_K
    print("ok")


if __name__ == "__main__":
    cmd = sys.argv[1] if len(sys.argv) > 1 else ""
    {"init": init, "run": run, "score": lambda: report(score()), "selftest": selftest}.get(cmd, lambda: print(__doc__))()
