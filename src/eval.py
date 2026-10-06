"""
Spike: Evaluation CLI command (spike eval)
Blueprint §6.5 & §13 Phase 1 and Phase 3:
- Runs detection on the ground-truth set and prints HIT@1, P@5, and NDCG@5.
- Evaluates community-clip Recall@10 against the untuned chat_users baseline arm (§6.5).
"""

import json
import math
from pathlib import Path
from typing import Dict, Any, List, Tuple
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
    print(f"{'Video ID / Title':<30} {'HIT@1':<8} {'P@5':<8} {'NDCG@5':<10} {'Matches'}")
    print("-" * 65)

    all_hit1 = []
    all_p5 = []
    all_ndcg = []

    for v in videos:
        vid_name = v.get("name") or v.get("id") or "video"
        cands = v.get("detected_candidates", [])
        gts = v.get("ground_truth", [])

        metrics = evaluate_video_moments(cands, gts)
        all_hit1.append(metrics["hit@1"])
        all_p5.append(metrics["p@5"])
        all_ndcg.append(metrics["ndcg@5"])

        matches_str = f"{metrics['matched']}/{metrics['total_gt']}"
        print(
            f"{vid_name[:28]:<30} "
            f"{metrics['hit@1']:<8.2f} "
            f"{metrics['p@5']:<8.2f} "
            f"{metrics['ndcg@5']:<10.3f} "
            f"{matches_str}"
        )

        # If community clips or chat are present, evaluate community clip Recall@10 (§6.5)
        com_clips = v.get("community_clips", [])
        raw_chat = v.get("chat_comments", [])
        if com_clips:
            spike_recall = evaluate_community_clips_recall(cands, com_clips, k=10)
            dur = int(v.get("duration_s", 1800))
            baseline_cands = compute_chat_users_baseline(raw_chat, dur, k=10)
            base_recall = evaluate_community_clips_recall(baseline_cands, com_clips, k=10)
            print(f"   -> Community-clip Recall@10: Spike={spike_recall:.3f} vs chat_users baseline={base_recall:.3f}")

    print("-" * 65)
    mean_hit1 = sum(all_hit1) / len(all_hit1)
    mean_p5 = sum(all_p5) / len(all_p5)
    mean_ndcg = sum(all_ndcg) / len(all_ndcg)
    print(f"{'MEAN AVERAGE':<30} {mean_hit1:<8.2f} {mean_p5:<8.2f} {mean_ndcg:<10.3f}")
    print("========================================================\n")
