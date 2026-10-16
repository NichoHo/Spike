"""spike eval: stored candidates, recall, precision, story segments, grade 0 and the reviewed range (Step 8)."""

import json
from pathlib import Path

from src.db import init_db, insert_candidate, register_video
from src.eval import evaluate_stored, gt_matches, load_db_candidates, run_evaluation

ROOT = Path(__file__).resolve().parent.parent


def cand(start, end, status="selected", score=70, segments=None, title="c"):
    return {"start_s": start, "end_s": end, "status": status, "llm_score": score, "final_score": score, "title": title, "segments": segments}


GT = [
    {"start_s": 1820, "end_s": 1855, "grade": 0, "note": "goal 1"},
    {"start_s": 1987, "end_s": 2037, "grade": 3, "note": "cocky"},
    {"start_s": 2388, "end_s": 2423, "grade": 0, "note": "goal 3"},
    {"start_s": 2600, "end_s": 2635, "grade": 2, "note": "loss"},
    {"grade": 3, "note": "story: cocky then loss", "segments": [[1987, 2037], [2600, 2635]]},
    {"start_s": 4076, "end_s": 4110, "grade": 2, "note": "indonesian, outside the reviewed range"},
]
RANGE = (1740, 2640)


def test_segments_ground_truth_matches_only_a_story_covering_every_segment():
    story = cand(1990, 2640, segments=[[1990, 2035], [2602, 2640]])
    assert gt_matches(story, GT[4])
    assert not gt_matches(cand(1987, 2037), GT[4])                                   # a solo clip is not a story
    assert not gt_matches(cand(1990, 2640, segments=[[1990, 2035], [2200, 2230]]), GT[4])  # second segment misses
    assert gt_matches(story, GT[1]) and gt_matches(story, GT[3])                     # its stretches still find single moments


def test_recall_counts_any_stored_status_and_grade_zero_items():
    cands = [
        cand(1822, 1850, status="low_score"),     # goal 1 found, but never selected
        cand(2390, 2420, status="rejected"),      # goal 3 found in a rejected candidate
        cand(1990, 2035, status="selected"),
        cand(2330, 2340, status="hubris"),        # found nothing
    ]
    r = evaluate_stored(cands, GT, RANGE)
    assert (r["found"], r["total"]) == (3, 6)      # goal 1, cocky, goal 3; not the loss, story or Indonesian
    assert [bool(row["found_by"]) for row in r["gt_rows"]] == [True, True, True, False, False, False]


def test_precision_counts_grade_zero_alone_duplicates_and_noise_but_not_unknown_picks():
    picks = [
        cand(1990, 2035, score=90),                                      # right: the cocky moment
        cand(1992, 2030, score=60),                                      # wrong: same moment again
        cand(2390, 2420, score=80),                                      # wrong: grade 0 moment on its own
        cand(2100, 2130, score=50),                                      # wrong: matches nothing
        cand(1990, 2640, score=85, segments=[[1990, 2035], [2602, 2640]]),  # right: the story
        cand(4076, 4110, score=95),                                      # outside the reviewed range: unknown
        cand(1822, 1850, status="low_score", score=99),                  # not a pick, ignored by precision
    ]
    r = evaluate_stored(picks, GT, RANGE)
    assert (r["right"], r["wrong"], r["unknown"]) == (2, 3, 1)
    assert abs(r["precision"] - 0.4) < 1e-9
    verdicts = {round(row["cand"]["start_s"]): row["verdict"] for row in r["pick_rows"]}
    assert verdicts[2390].startswith("wrong (grade 0") and verdicts[1992].startswith("wrong (a pick already")
    assert verdicts[4076].startswith("unknown")
    # a story is credited to its story ground truth, so the solo cocky pick still counts on its own
    assert verdicts[1990] .startswith("right")


def test_no_picks_in_range_gives_no_precision_and_recall_still_works():
    r = evaluate_stored([cand(4076, 4110)], GT, RANGE)
    assert r["precision"] is None and r["unknown"] == 1 and r["found"] == 1
    assert evaluate_stored([], [], None)["recall"] is None


def test_run_evaluation_reads_every_stored_candidate_from_the_db(tmp_path, capsys):
    init_db()
    vid = register_video("url", f"https://example.test/{tmp_path.name}")
    base = dict(origin="llm_chunk", title="t")
    insert_candidate(vid, {**base, "start_s": 1990.0, "end_s": 2035.0, "status": "selected", "llm_score": 80, "final_score": 80})
    insert_candidate(vid, {**base, "start_s": 1822.0, "end_s": 1850.0, "status": "low_score", "llm_score": 50, "final_score": 50})
    insert_candidate(vid, {**base, "start_s": 2392.0, "end_s": 2420.0, "status": "hubris", "title": "I never lose"})
    insert_candidate(vid, {**base, "start_s": 1990.0, "end_s": 2640.0, "status": "selected", "llm_score": 75, "final_score": 75,
                           "segments": [[1990.0, 2035.0], [2602.0, 2640.0]]})
    assert {c["status"] for c in load_db_candidates(vid)} == {"selected", "low_score", "hubris"}

    dataset = tmp_path / "eval.json"
    dataset.write_text(json.dumps({"videos": [{"id": str(vid), "name": "db video", "reviewed_range_s": list(RANGE), "ground_truth": GT}]}))
    run_evaluation(str(dataset))
    out = capsys.readouterr().out
    assert "Recall:    5/6" in out or "Recall:    4/6" in out          # everything but the out-of-range Indonesian is findable
    assert "Precision: 2/2 (100%)" in out and "MISSED" in out and "grade 0" in out


def test_eval_38_dataset_has_the_agreed_shape():
    data = json.loads((ROOT / "data" / "eval_38.json").read_text(encoding="utf-8"))
    [video] = data["videos"]
    assert video["id"] == "38" and video["reviewed_range_s"] == [1740, 2640]
    gt = video["ground_truth"]
    assert len(gt) == 13 and sum(1 for g in gt if g["grade"] == 0) == 3
    plain_story = next(g for g in gt if g.get("segments") and "kind" not in g)
    assert plain_story["segments"] == [[1987, 2037], [2600, 2635]] and "start_s" not in plain_story
    kinds = {g["kind"]: g for g in gt if g.get("kind")}
    assert set(kinds) == {"top5", "story", "pov"} and kinds["top5"]["grade"] == 3 and kinds["pov"]["grade"] == 2
    assert kinds["top5"]["segments"][-1] == [2600, 2635] and len(kinds["pov"]["segments"]) == 3


# ── concept kinds ─────────────────────────────────────────────────────────────

COMPILATION_GT = {"grade": 3, "kind": "top5", "segments": [[1820, 1855], [1960, 1995], [1987, 2037], [2388, 2423], [2600, 2635]]}
POV_GT = {"grade": 2, "kind": "pov", "segments": [[1820, 1855], [1960, 1995], [2388, 2423]]}
STORY_GT = {"grade": 3, "kind": "story", "segments": [[1987, 2037], [2600, 2635]]}


def concept(kind, spans, **kw):
    first, last = spans[0][0], spans[-1][1]
    return {**cand(first, last, segments=spans, **kw), "concept": kind}


def test_a_compilation_needs_three_overlapping_entries_and_a_last_entry_on_the_loss():
    entries = [[1822, 1850], [1962, 1990], [2390, 2420], [2602, 2630]]            # 4 entries, last one is the loss
    assert gt_matches(concept("top3", entries), COMPILATION_GT)
    assert gt_matches(concept("top5", entries), COMPILATION_GT)
    assert not gt_matches(concept("top3", entries[:2] + [[3000, 3030]]), COMPILATION_GT)               # only 2 entries overlap
    assert not gt_matches(concept("top3", [[1822, 1850], [1962, 1990], [2390, 2420]]), COMPILATION_GT)   # last entry is not the loss
    assert not gt_matches(concept("story", entries), COMPILATION_GT)                                    # wrong concept
    assert not gt_matches(cand(1820, 2640), COMPILATION_GT)


def test_a_story_ground_truth_asks_for_a_story_concept():
    story = concept("story", [[1990, 2035], [2602, 2630]])
    assert gt_matches(story, STORY_GT)
    assert not gt_matches(concept("top3", [[1990, 2035], [2602, 2630], [2700, 2720]]), STORY_GT)


def test_a_pov_matches_when_it_overlaps_a_listed_segment_and_passes_the_checks():
    pov = concept("pov", [[1822, 1830]], status="selected")
    assert gt_matches(pov, POV_GT) and not gt_matches(concept("pov", [[3000, 3008]]), POV_GT)
    assert not gt_matches(cand(1822, 1850), POV_GT)                                                    # a single is not a POV
    assert not gt_matches(pov, POV_GT, pov_ok=lambda c: False)                                          # fails the code checks
    r = evaluate_stored([pov], [POV_GT, COMPILATION_GT], RANGE, pov_ok=lambda c: True)
    assert (r["found"], r["right"], r["wrong"]) == (1, 1, 0)


def test_compilations_story_and_pov_picks_count_toward_precision():
    entries = [[1822, 1850], [1962, 1990], [2390, 2420], [2602, 2630]]
    picks = [concept("top3", entries, score=90), concept("story", [[1990, 2035], [2602, 2630]], score=80),
             concept("pov", [[2500, 2508]], score=70)]            # a POV on a moment nobody listed
    for p in picks:
        p["status"] = "selected"
    r = evaluate_stored(picks, [COMPILATION_GT, STORY_GT, POV_GT], RANGE, pov_ok=lambda c: True)
    assert (r["right"], r["wrong"]) == (2, 1)


def test_the_pov_checker_runs_the_concept_rules_on_the_stored_overlay(tmp_path, monkeypatch):
    import src.config
    from src.eval import make_pov_checker

    monkeypatch.setattr(src.config, "VIDEOS_DIR", tmp_path)
    vdir = tmp_path / "7"
    vdir.mkdir()
    (vdir / "meta.json").write_text(json.dumps({"uploader": "Speed"}))
    words = [{"word": " bro", "start": 10.0, "end": 10.3}, {"word": " unbelievable", "start": 10.4, "end": 10.9}]
    (vdir / "transcript.json").write_text(json.dumps({"segments": [{"words": words}]}))

    def pov(text, emotion="fury"):
        seg = {"candidate_id": 1, "start_s": 9.6, "end_s": 14.0, "remove": [], "rank": None, "label": ""}
        return {"title": "t", "concept_spec": json.dumps({"segments": [seg], "overlay": {"pov_text": text, "emotion": emotion}})}

    check = make_pov_checker(7)
    assert check(pov("POV: you said one more round at midnight"))
    assert not check(pov("POV: you called your brother bro again"))     # shares "bro" with the clip
    assert not check(pov("me when the wifi dies", emotion=""))              # no emotion label
