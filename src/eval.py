"""
Spike: Evaluation CLI command (spike eval)
Blueprint §6.5, §6.7 & §13:
- Loads every stored candidate of a video from the DB (selected, low_score, rejected, hubris) and compares
  it with the ground truth: Recall (found anywhere among stored candidates) and Precision (do the selected
  clips match the ground truth, inside the reviewed range only).
- Ground-truth items may carry `segments` (a story clip) and grade 0 (find it, but do not select it alone).
  A `kind` of top3, top5, story or pov asks for that concept (reports/Clip concepts.md): a compilation matches when
  at least 3 entries overlap the ground-truth segments and its last entry overlaps the last segment; a story when
  every segment overlaps one of its segments; a POV when it overlaps any listed segment and passes the concept
  checks (caption quality is graded by hand).
- Datasets that still list `detected_candidates` by hand are scored the same way; HIT@1, P@5 and NDCG@5 are
  printed for them too.
- Evaluates community-clip Recall@10 against the untuned chat_users baseline arm (§6.5).
"""

import json
import math
from pathlib import Path
from typing import Callable, Dict, Any, List, Optional, Tuple
import numpy as np


def compute_iou(st1: float, et1: float, st2: float, et2: float) -> float:
    inter = max(0.0, min(et1, et2) - max(st1, st2))
    union = max(1e-6, max(et1, et2) - min(st1, st2))
    return inter / union


def is_moment_match(cand_st: float, cand_et: float, gt_st: float, gt_et: float) -> bool:
    """Check if candidate matches ground-truth moment:
    IoU >= 0.30 or centers within 15 seconds.
    """
    iou = compute_iou(cand_st, cand_et, gt_st, gt_et)
    if iou >= 0.30:
        return True
    c1 = (cand_st + cand_et) / 2.0
    c2 = (gt_st + gt_et) / 2.0
    return abs(c1 - c2) <= 15.0


def dcg_at_k(relevances: List[float], k: int = 5) -> float:
    score = 0.0
    for i, rel in enumerate(relevances[:k]):
        score += (2 ** rel - 1.0) / math.log2(i + 2)
    return score


def evaluate_video_moments(
    detected_candidates: List[Dict[str, Any]],
    ground_truth_moments: List[Dict[str, Any]]
) -> Dict[str, float]:
    """Calculate HIT@1, P@5, and NDCG@5 for one video."""
    if not ground_truth_moments:
        return {"hit@1": 0.0, "p@5": 0.0, "ndcg@5": 0.0, "total_gt": 0, "matched": 0}

    sorted_cands = sorted(detected_candidates, key=lambda c: c.get("final_score", 0), reverse=True)
    top_5 = sorted_cands[:5]

    relevances = []
    matched_gt = set()

    for cand in top_5:
        c_st = cand["start_s"]
        c_et = cand["end_s"]
        rel = 0.0

        for idx, gt in enumerate(ground_truth_moments):
            if idx not in matched_gt:
                if is_moment_match(c_st, c_et, gt["start_s"], gt["end_s"]):
                    rel = float(gt.get("grade", 1.0))
                    matched_gt.add(idx)
                    break

        relevances.append(rel)

    while len(relevances) < 5:
        relevances.append(0.0)

    hit_1 = 1.0 if (relevances and relevances[0] >= 1.0) else 0.0
    p_5 = sum(1 for r in relevances if r >= 1.0) / 5.0

    actual_dcg = dcg_at_k(relevances, 5)
    ideal_grades = sorted([float(gt.get("grade", 1.0)) for gt in ground_truth_moments], reverse=True)
    ideal_dcg = dcg_at_k(ideal_grades, 5)
    ndcg_5 = (actual_dcg / ideal_dcg) if ideal_dcg > 0 else 0.0

    return {
        "hit@1": hit_1,
        "p@5": p_5,
        "ndcg@5": round(ndcg_5, 3),
        "total_gt": len(ground_truth_moments),
        "matched": len(matched_gt),
    }


def evaluate_community_clips_recall(
    detected_candidates: List[Dict[str, Any]],
    community_clips: List[Dict[str, Any]],
    k: int = 10,
) -> float:
    """
    Compute Recall@k against community clips (Blueprint §6.5):
    Fraction of community clips whose vod_offset lands inside a detected moment.
    """
    if not community_clips:
        return 0.0

    sorted_cands = sorted(detected_candidates, key=lambda c: c.get("final_score", 0), reverse=True)[:k]
    hits = 0

    for clip in community_clips:
        offset = clip.get("vod_offset")
        if offset is None:
            continue
        c_time = float(offset)
        # Check if offset falls within any of the top-k clips (with 5s boundary tolerance)
        for cand in sorted_cands:
            st = cand.get("start_s", 0.0) - 5.0
            et = cand.get("end_s", 0.0) + 5.0
            if st <= c_time <= et:
                hits += 1
                break

    valid_clips = sum(1 for c in community_clips if c.get("vod_offset") is not None)
    return round(hits / max(1, valid_clips), 3) if valid_clips > 0 else 0.0


def compute_chat_users_baseline(
    comments: List[Dict[str, Any]],
    duration_s: int,
    k: int = 10,
) -> List[Dict[str, Any]]:
    """
    Untuned chat_users baseline arm (Blueprint §6.5):
    Picks top k peaks purely from unique chatters per second without any fusion,
    filtering, audio events, or LLM evaluation.
    """
    if not comments:
        return []

    bin_users = [set() for _ in range(duration_s)]
    for c in comments:
        t = int(c.get("content_offset_seconds", 0))
        if 0 <= t < duration_s:
            u = c.get("commenter", {}).get("display_name", "")
            bin_users[t].add(u)

    counts = np.array([len(u) for u in bin_users], dtype=np.float32)
    # Smooth over 5s
    kernel = np.ones(5) / 5.0
    smoothed = np.convolve(counts, kernel, mode="same")

    # Pick top k peaks at least 45s apart
    peaks = []
    used = np.zeros(duration_s, dtype=bool)

    for _ in range(k):
        avail = smoothed.copy()
        avail[used] = -1.0
        best_t = int(np.argmax(avail))
        if avail[best_t] <= 0:
            break
        peaks.append({
            "start_s": max(0.0, float(best_t - 20)),
            "end_s": min(float(duration_s), float(best_t + 15)),
            "final_score": int(smoothed[best_t] * 10),
        })
        # Mask out 45s around peak
        m_start = max(0, best_t - 22)
        m_end = min(duration_s, best_t + 23)
        used[m_start:m_end] = True

    return peaks


# ── Stored candidates vs ground truth (§6.7) ─────────────────────────────────

def load_db_candidates(video_id: int) -> List[Dict[str, Any]]:
    """All stored candidates of a video, whatever their status (selected, low_score, rejected, hubris)."""
    from src.db import get_connection, init_db

    init_db()  # adds columns older databases lack (segments); safe to repeat
    with get_connection() as conn:
        rows = conn.execute(
            "SELECT id, start_s, end_s, status, llm_score, final_score, title, humor_type, segments, concept, concept_spec "
            "FROM candidates WHERE video_id = ?",
            (video_id,),
        ).fetchall()
    out = []
    for r in rows:
        d = dict(r)
        d["segments"] = json.loads(d["segments"]) if d["segments"] else None
        out.append(d)
    return out


def _intervals(c: Dict[str, Any]) -> List[Tuple[float, float]]:
    """A story clip is several stretches of the stream; any other candidate is one."""
    return [tuple(s) for s in c["segments"]] if c.get("segments") else [(c["start_s"], c["end_s"])]


def _overlap(a: Tuple[float, float], b: Tuple[float, float]) -> float:
    return max(0.0, min(a[1], b[1]) - max(a[0], b[0]))


def gt_matches(cand: Dict[str, Any], gt: Dict[str, Any], pov_ok: Optional[Callable[[Dict[str, Any]], bool]] = None) -> bool:
    """A single-window ground truth matches when any stretch of the candidate matches (IoU or centers).
    A ground truth with `segments` matches a story clip only when every one of its segments overlaps one of
    the clip's segments. With a `kind` the candidate must also be that concept; a compilation or a POV is judged
    by the rules in the module docstring (pov_ok runs the concept checks on a POV; without it any POV overlap counts)."""
    if not gt.get("segments"):
        return any(is_moment_match(s, e, gt["start_s"], gt["end_s"]) for s, e in _intervals(cand))
    stretches = [tuple(s) for s in cand.get("segments") or []]
    if not stretches:
        return False
    kind, concept = gt.get("kind"), cand.get("concept") or "single"
    wanted = [tuple(g) for g in gt["segments"]]
    if kind in ("top3", "top5", "compilation"):
        if concept not in ("top3", "top5"):
            return False
        overlapping = sum(1 for s in stretches if any(_overlap(s, g) > 0 for g in wanted))
        return overlapping >= 3 and _overlap(stretches[-1], wanted[-1]) > 0     # entries run weakest first, #1 last
    if kind == "pov":
        return concept == "pov" and any(_overlap(s, g) > 0 for s in stretches for g in wanted) and (pov_ok is None or pov_ok(cand))
    if kind == "story" and concept != "story":
        return False
    return all(any(_overlap(g, s) > 0 for s in stretches) for g in wanted)


def evaluate_stored(
    candidates: List[Dict[str, Any]],
    ground_truth: List[Dict[str, Any]],
    reviewed_range_s: Optional[Tuple[float, float]] = None,
    pov_ok: Optional[Callable[[Dict[str, Any]], bool]] = None,
) -> Dict[str, Any]:
    """
    Recall: share of ground-truth moments matched by ANY stored candidate. Grade 0 items count: they must
    be found.
    Precision: share of selected clips inside the reviewed range that are right. A pick is right when it
    matches a grade 1+ ground truth it has not already been credited to. It is wrong when it matches
    nothing, only a grade 0 moment on its own, or a moment another pick already covers. Picks outside the
    reviewed range are unknown (nobody watched that part), so they are counted separately.
    """
    gt_rows = []
    for gt in ground_truth:
        gt_rows.append({"gt": gt, "found_by": [c for c in candidates if gt_matches(c, gt, pov_ok)]})
    found_n = sum(1 for r in gt_rows if r["found_by"])

    lo, hi = reviewed_range_s if reviewed_range_s else (float("-inf"), float("inf"))
    picks = sorted((c for c in candidates if c.get("status") == "selected"), key=lambda c: c.get("final_score") or 0, reverse=True)
    credited: set = set()
    pick_rows, tp, fp, unknown = [], 0, 0, 0
    for c in picks:
        spans = _intervals(c)
        if not (lo <= min(s for s, _ in spans) and max(e for _, e in spans) <= hi):
            unknown += 1
            pick_rows.append({"cand": c, "verdict": "unknown (outside the reviewed range)"})
            continue
        is_story = bool(c.get("segments"))
        matched = [i for i, gt in enumerate(ground_truth) if gt_matches(c, gt, pov_ok)]
        story_gt = [i for i in matched if ground_truth[i].get("segments")]
        good = [i for i in matched if ground_truth[i].get("grade", 1) >= 1]
        if is_story and story_gt:
            good = story_gt  # a story is credited to its story, not to the single moments inside it
        fresh = [i for i in good if i not in credited]
        if fresh:
            credited.add(fresh[0])
            tp += 1
            verdict = f"right (matches: {ground_truth[fresh[0]].get('note', 'a ground-truth moment')[:50]})"
        else:
            fp += 1
            if good:
                verdict = "wrong (a pick already covers that moment)"
            elif matched and not is_story:
                verdict = "wrong (grade 0 moment selected alone)"
            else:
                verdict = "wrong (matches no ground truth)"
        pick_rows.append({"cand": c, "verdict": verdict})

    return {
        "recall": found_n / len(ground_truth) if ground_truth else None, "found": found_n, "total": len(ground_truth),
        "precision": tp / (tp + fp) if tp + fp else None, "right": tp, "wrong": fp, "unknown": unknown,
        "gt_rows": gt_rows, "pick_rows": pick_rows,
    }


def make_pov_checker(video_id: int) -> Callable[[Dict[str, Any]], bool]:
    """Runs the concept rules on a stored POV: its speech must not name the game, a player, chat or the streamer, and
    its caption must pass the caption rules. Whether the caption is funny is graded by hand. If the video's files are
    gone the structure is checked without the speech."""
    from src.concepts import validate_concept
    from src.config import VIDEOS_DIR
    from src.profile import concept_terms, load_context

    vdir = VIDEOS_DIR / str(video_id)
    try:
        meta = json.loads((vdir / "meta.json").read_text(encoding="utf-8"))
        transcript = json.loads((vdir / "transcript.json").read_text(encoding="utf-8"))
        words = [w for s in transcript.get("segments", []) for w in s.get("words", [])]
        terms = concept_terms(load_context(video_id, vdir, meta), meta)
    except OSError:
        words, terms = [], None

    def ok(cand: Dict[str, Any]) -> bool:
        spec = json.loads(cand["concept_spec"]) if cand.get("concept_spec") else {}
        segs = spec.get("segments") or []
        if len(segs) != 1:
            return False
        problems = validate_concept("pov", segs, spec.get("overlay") or {}, title=cand.get("title") or "", words=words, terms=terms)
        return not problems

    return ok


def _pct(x: Optional[float]) -> str:
    return "n/a" if x is None else f"{x * 100:.0f}%"


def _describe(c: Dict[str, Any]) -> str:
    spans = " + ".join(f"{int(s) // 60}:{int(s) % 60:02d}" for s, _ in _intervals(c))
    return f"{c.get('status', '?')} at {spans}, score {c.get('llm_score', c.get('final_score', '?'))}, '{(c.get('title') or '')[:40]}'"


def print_stored_report(name: str, result: Dict[str, Any]) -> None:
    print(f"\n{name}")
    print(f"  Recall:    {result['found']}/{result['total']} ({_pct(result['recall'])}) of the ground-truth moments are among the stored candidates")
    if result["precision"] is None:
        prec = "n/a (no selected clips in the reviewed range)"
    else:
        prec = f"{result['right']}/{result['right'] + result['wrong']} ({_pct(result['precision'])})"
    print(f"  Precision: {prec}; {result['unknown']} selected clip(s) outside the reviewed range are unknown, not wrong")
    print("  Ground truth:")
    for r in result["gt_rows"]:
        gt = r["gt"]
        where = " + ".join(f"{int(a)}-{int(b)}s" for a, b in gt["segments"]) if gt.get("segments") else f"{int(gt['start_s'])}-{int(gt['end_s'])}s"
        best = next((c for c in r["found_by"] if c.get("status") == "selected"), r["found_by"][0] if r["found_by"] else None)
        kind = f" {gt['kind']}" if gt.get("kind") else ""
        line = f"    [{'found' if best else 'MISSED':<6}] grade {gt.get('grade', 1)}{kind} {where:<22} {gt.get('note', '')[:46]}"
        print(line + (f"\n             by {_describe(best)}" if best else ""))
    print("  Selected clips:")
    for r in result["pick_rows"]:
        print(f"    {_describe(r['cand'])}: {r['verdict']}")
    if not result["pick_rows"]:
        print("    none")


def run_evaluation(dataset_file: str):
    """Run evaluation across all videos in the ground-truth dataset file."""
    path = Path(dataset_file)
    if not path.exists():
        print(f"Error: Dataset file not found: {dataset_file}")
        return

    with open(path, "r", encoding="utf-8") as f:
        data = json.load(f)

    videos = data.get("videos", [])
    if not videos:
        print("No videos found in evaluation dataset.")
        return

    print("\n========================================================")
    print("  Spike Evaluation: Moment Detection vs Ground Truth   ")
    print("========================================================")

    legacy_rows = []
    recalls, precisions = [], []

    for v in videos:
        vid_name = v.get("name") or v.get("id") or "video"
        gts = v.get("ground_truth", [])
        rng = tuple(v["reviewed_range_s"]) if v.get("reviewed_range_s") else None

        # Datasets that list detected_candidates are scored as given (all of them count as selected).
        # Otherwise every stored candidate of that video id comes from the DB.
        if "detected_candidates" in v:
            cands = [{**c, "status": "selected"} for c in v["detected_candidates"]]
        else:
            try:
                cands = load_db_candidates(int(v["id"]))
            except (KeyError, ValueError):
                print(f"\n{vid_name}: needs a numeric video id or detected_candidates")
                continue
            if not cands:
                print(f"\n{vid_name}: no stored candidates for video {v['id']}; run the pipeline first.")

        pov_ok = make_pov_checker(int(v["id"])) if "detected_candidates" not in v and str(v.get("id", "")).isdigit() else None
        result = evaluate_stored(cands, gts, rng, pov_ok)
        print_stored_report(vid_name, result)
        if result["recall"] is not None:
            recalls.append(result["recall"])
        if result["precision"] is not None:
            precisions.append(result["precision"])

        if "detected_candidates" in v:
            singles = [g for g in gts if not g.get("segments") and "start_s" in g]
            legacy_rows.append((vid_name, evaluate_video_moments(v["detected_candidates"], singles)))

        # If community clips or chat are present, evaluate community clip Recall@10 (§6.5)
        com_clips = v.get("community_clips", [])
        raw_chat = v.get("chat_comments", [])
        if com_clips:
            spike_recall = evaluate_community_clips_recall(cands, com_clips, k=10)
            dur = int(v.get("duration_s", 1800))
            baseline_cands = compute_chat_users_baseline(raw_chat, dur, k=10)
            base_recall = evaluate_community_clips_recall(baseline_cands, com_clips, k=10)
            print(f"   -> Community-clip Recall@10: Spike={spike_recall:.3f} vs chat_users baseline={base_recall:.3f}")

    if legacy_rows:
        print(f"\n{'Ranking metrics':<30} {'HIT@1':<8} {'P@5':<8} {'NDCG@5':<10} {'Matches'}")
        print("-" * 65)
        for vid_name, m in legacy_rows:
            print(f"{vid_name[:28]:<30} {m['hit@1']:<8.2f} {m['p@5']:<8.2f} {m['ndcg@5']:<10.3f} {m['matched']}/{m['total_gt']}")
        n = len(legacy_rows)
        print(f"{'MEAN AVERAGE':<30} {sum(m['hit@1'] for _, m in legacy_rows) / n:<8.2f} "
              f"{sum(m['p@5'] for _, m in legacy_rows) / n:<8.2f} {sum(m['ndcg@5'] for _, m in legacy_rows) / n:<10.3f}")

    if len(recalls) > 1:
        mean_p = _pct(sum(precisions) / len(precisions)) if precisions else "n/a"
        print(f"\nMean recall {_pct(sum(recalls) / len(recalls))}, mean precision {mean_p}")
    print("========================================================\n")
