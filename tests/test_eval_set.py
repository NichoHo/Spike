"""Eval set labels and metrics: live clips mark their end, VOD clips their start; one clipper is noise."""

from src.eval_set import label_moments, score_ranking

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
