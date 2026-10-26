"""Eval set labels and metrics: live clips mark their end, VOD clips their start; one clipper is noise."""

from src.eval_set import label_moments, rank_preds, score_ranking

VOD_START = "2026-10-01T00:00:00Z"


def clip(off, dur, creator, made, views=1):
    return {"vod_offset": off, "duration": dur, "creator_id": creator, "view_count": views,
            "created_at": made, "vod_created_at": VOD_START}


def test_live_clips_mark_their_end_and_vod_clips_their_start():
    clips = [
        clip(100, 30, "a", "2026-10-01T00:02:10Z"),   # made live at 130 s: moment ~127 s
        clip(105, 25, "b", "2026-10-01T00:02:11Z"),   # live: ~127 s
        clip(124, 60, "c", "2026-10-05T00:00:00Z"),   # cut from the VOD days later: starts at the moment, ~127 s
        clip(500, 30, "d", "2026-10-05T00:00:00Z"),   # one clipper: noise
    ]
    m = label_moments(clips)
    assert len(m) == 1 and m[0]["clippers"] == 3 and abs(m[0]["t"] - 127) < 1


def test_metrics_count_each_moment_once():
    moments = [{"t": 100.0, "clippers": 5, "views": 0}, {"t": 400.0, "clippers": 2, "views": 0}]
    s = score_ranking([(90, 120), (95, 125), (390, 420)], moments, tol=5)
    assert s["hit@1"] == 1.0 and s["recall@5"] == 1.0
    # the duplicate second pick earns no gain: (5 + 0 + 2/2) / (5 + 2/log2(3))
    assert abs(s["ndcg@10"] - 6 / (5 + 2 / 1.58496)) < 1e-3
    miss = score_ranking([(200, 230)], moments, tol=5)
    assert miss["hit@1"] == 0.0 and miss["recall@10"] == 0.0


def test_spacing_moves_near_picks_behind_the_spaced_ones():
    cands = [{"start_s": 100, "end_s": 130, "final_score": 90, "status": "low_score"},
             {"start_s": 110, "end_s": 140, "final_score": 80, "status": "low_score"},   # centre 125, 10 s from the first
             {"start_s": 300, "end_s": 330, "final_score": 50, "status": "low_score"}]
    assert rank_preds(cands, None) == [(100, 130), (110, 140), (300, 330)]
    assert rank_preds(cands, 45.0) == [(100, 130), (300, 330), (110, 140)]


def test_dedupe_drops_a_candidate_within_the_gap_of_a_kept_one():
    from src.pipeline.stage7_moments import dedupe
    a, b, c = ({"start_s": s, "end_s": s + 20} for s in (100, 140, 300))   # a and b do not overlap, centres 40 s apart
    assert dedupe([a, b, c])[0] == [a, b, c]
    assert dedupe([a, b, c], gap_s=45.0) == ([a, c], [b])


def test_a_failed_video_check_ranks_under_every_clip_that_passed():
    from src.pipeline.stage7_moments import ranking_score
    assert ranking_score(100, True, False) <= ranking_score(0, False, False)
    assert ranking_score(50, False, True) > ranking_score(50, False, False)
    assert ranking_score(100, False, True) == 100
