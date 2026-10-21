"""Crowd-first detection: chat laugh token forms and community-clip seeds."""

from src.config import CHAT_LAUGH_TOKENS
from src.pipeline.stage6_signals import squeeze, token_forms
from src.pipeline.stage7_moments import crowd_proposals


def test_laugh_forms_catch_repeats_but_not_single_letters():
    forms = token_forms(set(CHAT_LAUGH_TOKENS) | {"LuL"})
    hit = lambda w: bool({w.lower(), squeeze(w.lower())} & forms)
    assert hit("LMAOOO") and hit("😂😂😂😂") and hit("lolll") and hit("LuL")
    assert not hit("w") and not hit("hello")


def test_crowd_seeds_group_by_clip_start_and_rank_by_clippers():
    clips = [  # three viewers clip the same moment (starts near 100 s), one clips another
        {"vod_offset": 100, "duration": 17, "creator_id": "a", "view_count": 4},
        {"vod_offset": 105, "duration": 60, "creator_id": "b", "view_count": 4},
        {"vod_offset": 101, "duration": 30, "creator_id": "c", "view_count": 1},
        {"vod_offset": 500, "duration": 30, "creator_id": "d", "view_count": 25},
        {"vod_offset": None, "duration": 30, "creator_id": "e", "view_count": 1},
    ]
    seeds = crowd_proposals(clips, 1000.0)
    assert len(seeds) == 2
    first = seeds[0]  # 3 * 3 + sqrt(9) = 12 beats 3 * 1 + sqrt(25) = 8
    assert first["crowd"] and first["origin"] == "crowd"
    assert first["clip_start"] == 90 and first["clip_end"] == 135  # 10 s of setup, 45 s window
    assert seeds[1]["clip_start"] == 490


def test_chat_laugh_seeds_pick_biggest_bursts_a_minute_apart():
    import numpy as np
    from src.pipeline.stage7_moments import chat_laugh_proposals
    s = np.zeros(1000)
    s[200], s[230], s[700] = 0.9, 0.5, 0.6  # 230 is within a minute of the bigger 200
    seeds = chat_laugh_proposals(s, 1000.0)
    assert [x["peak_t"] for x in seeds] == [200, 700]
    assert chat_laugh_proposals(np.zeros(50), 50.0) == []
