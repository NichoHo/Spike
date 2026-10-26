from src.pipeline.stage9a_face_track import (
    SPEAKER_MIN_ACTIVITY,
    _ema_smooth_centers,
    _pick_speakers,
)

LOUD, QUIET = 3.0, 1.0  # mouth movement as a multiple of the face's resting level


def win(a, b):
    return {0: a, 1: b}


def test_silence_picks_nobody_then_first_talker():
    out = _pick_speakers([win(QUIET, QUIET)] * 3 + [win(LOUD, QUIET)] * 2)
    assert out == [None, None, None, 0, 0]


def test_cuts_to_the_other_speaker_after_two_winning_windows():
    # 0 talks for 4 windows, then 1 takes over: the switch needs two windows in a row
    out = _pick_speakers([win(LOUD, QUIET)] * 4 + [win(QUIET, LOUD)] * 4)
    assert out[:5] == [0, 0, 0, 0, 0]
    assert out[5] == 1 and out[-1] == 1


def test_one_loud_window_does_not_switch():
    out = _pick_speakers([win(LOUD, QUIET)] * 4 + [win(QUIET, LOUD)] + [win(LOUD, QUIET)] * 4)
    assert set(out) == {0}


def test_minimum_hold_blocks_rapid_ping_pong():
    # 0 starts, 1 wins two windows straight right away: still inside the 1.5 s hold, so no switch yet
    out = _pick_speakers([win(LOUD, QUIET), win(QUIET, LOUD), win(QUIET, LOUD)] + [win(QUIET, LOUD)] * 4)
    assert out[1] == 0 and out[2] == 0
    assert out[-1] == 1


def test_close_call_keeps_current_speaker():
    # 1 is louder but not by SWITCH_RATIO
    out = _pick_speakers([win(LOUD, QUIET)] * 4 + [win(LOUD, LOUD * 1.2)] * 6)
    assert set(out) == {0}


def test_below_activity_floor_never_triggers():
    assert SPEAKER_MIN_ACTIVITY > QUIET
    assert _pick_speakers([win(QUIET, QUIET * 1.2)] * 6) == [None] * 6


def test_ema_jumps_on_a_cut_instead_of_panning():
    raw = [(0.1, 0.4, 0.1, 0.1)] * 3 + [(0.8, 0.4, 0.1, 0.1)] * 2
    panned = _ema_smooth_centers(raw)
    cut = _ema_smooth_centers(raw, cuts=[3])
    assert panned[3][0] < 0.6           # eased only part of the way to the new face
    assert abs(cut[3][0] - 0.85) < 0.01  # landed on it at the cut


def test_ambiguous_start_picks_nobody_until_one_face_clearly_leads():
    out = _pick_speakers([win(LOUD, LOUD * 0.9)] * 2 + [win(LOUD, QUIET)])
    assert out == [None, None, 0]


def _words(speaker_by_word):
    return [{"word": f"w{i}", "start": i * 0.4, "end": i * 0.4 + 0.3, "speaker": s} for i, s in enumerate(speaker_by_word)]


def test_caption_line_takes_the_majority_speakers_colour():
    from src.pipeline.stage9b_captions import _SPEAKER_COLORS, generate_ass
    ass = generate_ass(_words([0, 0, 1, 1, 1, 1]), 0.0, 5.0, style="clean", words_per_line=3)
    lines = [l for l in ass.splitlines() if l.startswith("Dialogue")]
    assert _SPEAKER_COLORS[0] not in lines[0]       # first speaker stays the default white: no tag
    assert _SPEAKER_COLORS[1] in lines[1]           # second speaker, light cyan


def test_bold_pop_highlight_returns_to_the_speakers_colour_not_white():
    from src.pipeline.stage9b_captions import _HIGHLIGHT, _SPEAKER_COLORS, generate_ass
    ass = generate_ass(_words([1, 1]), 0.0, 3.0, style="bold_pop")
    first = [l for l in ass.splitlines() if l.startswith("Dialogue")][0]
    assert rf"\c{_SPEAKER_COLORS[1]}" in first and _HIGHLIGHT in first
    assert "&H00FFFFFF&" not in first


def test_no_speakers_leaves_captions_exactly_as_before():
    from src.pipeline.stage9b_captions import generate_ass
    plain = [{k: v for k, v in w.items() if k != "speaker"} for w in _words([0, 1, 1])]
    ass = generate_ass(plain, 0.0, 3.0, style="clean")
    assert "FFE76E" not in ass and "C78FFF" not in ass


def test_speaker_at_looks_ahead_to_cover_the_switch_delay():
    from src.pipeline.stage9a_face_track import speaker_at
    speakers = [0] * 8 + [1] * 8     # the pick flips at 2.0 s, about 0.75 s after the person really started talking
    # so a word at 1.5 s (after the true change at ~1.25 s) already gets speaker 1, and one at 1.0 s keeps speaker 0
    assert speaker_at(speakers, 1.0) == 0
    assert speaker_at(speakers, 1.5) == 1
    assert speaker_at([], 1.0) is None
