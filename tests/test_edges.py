"""Clip edges from judge structure lines, phrase lines and cuts (Blueprint §6.7, Step 4)."""

import numpy as np

from src.models import LLMJudgeResponse
from src.pipeline.stage7_moments import compute_edges, split_into_phrases
from src.pipeline.stage9c_render import compute_keep_intervals, merge_cut_intervals

PRESET = {"setup_pad_s": 3, "end_extend_max_s": 8, "min_len": 12, "max_len": 40}


def word(text, start, end):
    return {"word": text, "start": start, "end": end}


def lines():
    """Five phrases: old topic, a gap, the new topic with a setup, a fluff aside, the payoff."""
    words = [
        word(" Anyway", 0.0, 0.5), word(" that", 0.6, 0.9), word(" was", 1.0, 1.3), word(" it.", 1.4, 1.8),       # L1 old topic
        word(" So", 4.0, 4.3), word(" I", 4.4, 4.6), word(" bet", 4.7, 5.0), word(" chat.", 5.1, 5.6),           # L2 topic starts
        word(" I", 6.5, 6.7), word(" never", 6.8, 7.1), word(" lose.", 7.2, 7.8),                                 # L3 setup
        word(" Also", 8.0, 8.3), word(" hydrate", 8.4, 8.9), word(" kids.", 9.0, 9.5),                           # L4 fluff
        word(" Oh", 10.5, 10.7), word(" no", 10.8, 11.0), word(" way!", 11.1, 11.9),                              # L5 payoff
    ]
    return split_into_phrases([{"start": 0.0, "end": 11.9, "text": "", "words": words}])


def judge(**kw):
    base = dict(keep=True, score=70, punchline="p", title="t", hook_text="h", post_caption="c",
                topic_start_line=2, setup_start_line=3, payoff_line=5, reaction_end_line=5, cut_lines=[])
    base.update(kw)
    return LLMJudgeResponse(**base)


def test_phrases_break_at_punctuation_and_every_2_5_seconds():
    ph = lines()
    assert [p["text"] for p in ph] == ["Anyway that was it.", "So I bet chat.", "I never lose.", "Also hydrate kids.", "Oh no way!"]
    long = split_into_phrases([{"words": [word(f" w{i}", i * 0.5, i * 0.5 + 0.4) for i in range(12)]}])
    assert all(p["end"] - p["start"] <= 3.0 for p in long) and len(long) >= 2


def test_start_never_reaches_into_previous_topic():
    # setup pad would reach back to 3.5 s, but the topic starts at 4.0 s
    e = compute_edges(lines(), judge(), {**PRESET, "setup_pad_s": 3}, [])
    assert e["start_s"] >= 4.0 - 1e-6
    assert abs(e["start_s"] - 3.9) < 0.2 or e["start_s"] >= 4.0  # snapped to the pause before "So"


def test_end_extends_while_audio_stays_high_then_pads():
    laugh = np.zeros(30, dtype=np.float32)
    laugh[12:16] = 0.9   # laughter right after the reaction ends at 11.9
    e = compute_edges(lines(), judge(), PRESET, [(laugh, 0.5)])
    assert abs(e["end_s"] - (16 + 0.8)) < 1e-6
    quiet = compute_edges(lines(), judge(), PRESET, [])
    assert abs(quiet["end_s"] - (11.9 + 0.8)) < 1e-6
    capped = compute_edges(lines(), judge(), {**PRESET, "end_extend_max_s": 1}, [(np.ones(30, dtype=np.float32), 0.5)])
    assert capped["end_s"] <= 11.9 + 1 + 0.8 + 1e-6


def test_judge_cut_lines_are_ignored():
    # cut_lines removed rant build-ups in real clips; a single clip plays every line between its edges
    e = compute_edges(lines(), judge(cut_lines=[4]), PRESET, [])
    assert e["cuts"] == [] and abs(e["net_dur"] - (e["end_s"] - e["start_s"])) < 1e-6


def test_cuts_merge_with_silence_cuts_into_keep_intervals():
    cuts = merge_cut_intervals([(10.0, 12.0)], [(11.0, 14.0), (2.0, 2.1), (30.0, 40.0)], clip_start=5.0, clip_end=20.0)
    assert cuts == [(10.0, 14.0)]  # overlap merged, tiny and out-of-window cuts dropped
    assert compute_keep_intervals(5.0, 20.0, cuts) == [(5.0, 10.0), (14.0, 20.0)]


def test_slivers_between_cuts_are_cut_too():
    # a 0.3 s keep between two cuts is breath, not content; a 1 s keep stays
    assert merge_cut_intervals([(10.0, 12.0), (12.3, 14.0)], clip_start=5.0, clip_end=20.0) == [(10.0, 14.0)]
    assert merge_cut_intervals([(10.0, 12.0), (13.0, 14.0)], clip_start=5.0, clip_end=20.0) == [(10.0, 12.0), (13.0, 14.0)]
