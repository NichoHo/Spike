"""Concept rules and POV captions (reports/Clip concepts.md)."""

import json

import numpy as np
import pytest

from src import pov
from src.claude_cli import ClaudeError
from src.concepts import (
    context_terms,
    count_problem,
    pov_caption_problems,
    pov_context_problems,
    pov_edges,
    reaction_peak,
    segment_net_s,
    segment_text,
    validate_concept,
)

TERMS = context_terms(streamer="IShowSpeed", aliases=["Speed"], game="EA Sports FC Mobile", names=["Kvaratskhelia"])
CLIP_TEXT = "no no no he scored again bro unbelievable"


def test_the_moment_picker_count_rules():
    assert count_problem("single", 1) is None and count_problem("pov", 2) == "POV needs exactly 1 moment"
    assert count_problem("story", 1) and count_problem("story", 2) is None and count_problem("story", 3) is None and count_problem("story", 4)
    assert count_problem("top3", 3) is None and "exactly 3" in count_problem("top3", 4)
    assert count_problem("top5", 5) is None and "exactly 5" in count_problem("top5", 3)


@pytest.mark.parametrize("speech", ["chat said so", "thanks for the donation", "Speed is cooked", "the EA servers", "Kvaratskhelia again"])
def test_pov_speech_with_context_words_is_rejected(speech):
    assert pov_context_problems(speech, TERMS)


def test_pov_speech_without_context_words_passes():
    assert pov_context_problems(CLIP_TEXT, TERMS) == []


@pytest.mark.parametrize("caption,fails", [
    ("POV: you said one more round at midnight", False),
    ("me when the group project is due at 8am", False),
    ("POV: you scored again and nobody clapped", True),                     # shares "scored" with the clip
    ("me when EA servers crash", True),                                      # names the game
    ("POV: Speed finds out his phone is at two percent", True),             # names the streamer
    ("POV: you stayed up all night finishing a project that was never due", True),   # 11 words
    ("", True),
])
def test_pov_caption_rules(caption, fails):
    assert bool(pov_caption_problems(caption, CLIP_TEXT, ["Speed rages"], TERMS)) is fails


def test_reaction_peak_and_pov_edges():
    jump = np.zeros(100, dtype=np.float32)
    jump[40:44] = 18.0
    jump[41] = 25.0
    peak = reaction_peak(jump, 30, 60)
    assert peak == 41.0 and reaction_peak(np.zeros(100), 30, 60, fallback=45.0) == 45.0
    start, end = pov_edges(peak, jump, 3.0, 30.0, 60.0)
    assert start == pytest.approx(40.6) and end == pytest.approx(44.6)        # starts 0.4 s early, minimum 4 s
    jump[41:60] = 18.0                                                         # a long outburst is capped at 12 s
    start, end = pov_edges(41.0, jump, 3.0, 30.0, 60.0)
    assert end - start <= 12.0
    assert pov_edges(41.0, jump, 3.0, 30.0, 42.0) is None                     # not enough room for 4 s


def test_story_and_top_validation_need_the_report_rules():
    words = [{"word": w, "start": 100.0 + i * 0.4, "end": 100.3 + i * 0.4} for i, w in enumerate("I am literally thrashing this".split())]
    setup = {"start_s": 99.9, "end_s": 105.0, "remove": [], "rank": None, "label": "", "score": None}
    payoff = {"start_s": 500.0, "end_s": 520.0, "remove": [[505.0, 506.0]], "rank": None, "label": "", "score": 80}
    ov = {"callback_quote": "literally thrashing", "skip_card": "3 goals later"}
    assert segment_net_s(payoff) == 19.0 and segment_text(words, setup).startswith("I am literally")
    assert validate_concept("story", [setup, payoff], ov, title="t", words=words) == []
    assert validate_concept("story", [payoff, setup], ov, title="t", words=words)                      # out of time order
    three = [setup, {**payoff, "start_s": 200.0, "end_s": 210.0, "score": 90}, payoff]
    assert any("escalates" in p for p in validate_concept("story", three, ov, title="t", words=words))  # middle scores above the payoff

    def entry(rank, length, score=80):
        return {"start_s": 0.0, "end_s": length, "remove": [], "rank": rank, "label": f"entry {rank}", "score": score}

    good = [entry(3, 10), entry(2, 10), entry(1, 12)]
    assert validate_concept("top3", good, None, title="Ranking Speed's Funniest Moments") == []
    assert any("weakest" in p for p in validate_concept("top3", good[::-1], None, hook_text="wait", theme="goals"))
    assert any("over 60" in p for p in validate_concept("top3", [entry(3, 15), entry(2, 15), entry(1, 15), ][:3] + [], None, hook_text="w", theme="t")) is False
    assert any("header" in p for p in validate_concept("top3", good, None))
    five = [entry(5, 8), entry(4, 8), entry(3, 8), entry(2, 8), entry(1, 11, score=54)]
    assert any("floor" in p for p in validate_concept("top5", five, None, hook_text="w", theme="t"))
    assert any("over 100" in p for p in validate_concept("top5", [entry(r, 12) for r in (5, 4, 3, 2, 1)] + [], None, hook_text="w", theme="t")) is False


# ── caption bank and the caption call ─────────────────────────────────────────

def test_bank_add_dedupe_delete_and_prompt(tmp_path):
    path = tmp_path / "bank.json"
    assert pov.add_to_bank("POV: your mom walks in", "panic", path) and not pov.add_to_bank("pov: your mom walks in", "panic", path)
    assert not pov.add_to_bank("", "fury", path) and not pov.add_to_bank("x", "not an emotion", path)
    pov.add_to_bank("me when the wifi dies", "fury", path)
    assert [b["text"] for b in pov.load_bank(path)] == ["POV: your mom walks in", "me when the wifi dies"]
    text = pov.bank_for_prompt(pov.load_bank(path))
    assert "fury:\n- me when the wifi dies" in text and "panic:" in text
    assert pov.delete_from_bank(0, path) and not pov.delete_from_bank(9, path) and len(pov.load_bank(path)) == 1
    path.write_text("not json")
    assert pov.load_bank(path) == [] and "bank is empty" in pov.bank_for_prompt([])


def caption(text, a=4, r=4, s=4, su=4, src=""):
    return {"text": text, "adapted_from": src, "aptness": a, "relatability": r, "specificity": s, "surprise": su}


def test_caption_call_keeps_the_top_three_that_pass_the_code_rules(monkeypatch):
    answer = {"emotion": "fury", "captions": [
        caption("me when EA servers crash", 5, 5, 5, 5),                        # best score but names the game
        caption("POV: you scored again", 5, 5, 5, 4),                          # shares a word with the clip
        caption("POV: you said one more round at midnight", 5, 4, 4, 4),
        caption("me when the wifi dies mid download", 4, 5, 4, 4, "me when the wifi dies"),
        caption("when mom turns off the router at 10", 4, 4, 5, 4),
        caption("POV: you said one more round at midnight", 3, 3, 3, 3),       # duplicate
        caption("POV: group project, you did all of it", 3, 4, 3, 3),
    ]}
    monkeypatch.setattr("src.claude_cli.run_claude", lambda *a, **k: answer)
    r = pov.generate_pov_captions("L1 NO NO NO [shouting]", CLIP_TEXT, ["Speed rages"], TERMS, bank=[])
    assert r["emotion"] == "fury" and len(r["options"]) == 3 and r["text"] == r["options"][0]
    assert r["options"][0] == "POV: you said one more round at midnight"
    assert all(not pov_caption_problems(o, CLIP_TEXT, [], TERMS) for o in r["options"]) and r["rejected"] == 2


def test_caption_call_falls_back_to_gemini_and_fails_when_nothing_passes(monkeypatch):
    monkeypatch.setattr("src.claude_cli.run_claude", lambda *a, **k: (_ for _ in ()).throw(ClaudeError("plan limit")))
    seen = {}
    monkeypatch.setattr("src.profile._gemini_json", lambda prompt, cls, model=None: seen.update(model=model) or cls(
        emotion="panic", captions=[caption("POV: your mom walks in mid call")]))
    r = pov.generate_pov_captions("L1 no", CLIP_TEXT, [], TERMS, bank=[])
    assert r["emotion"] == "panic" and seen["model"]
    monkeypatch.setattr("src.profile._gemini_json", lambda prompt, cls, model=None: cls(emotion="fury", captions=[caption("me when EA lags")]))
    with pytest.raises(ValueError, match="no caption passed"):
        pov.generate_pov_captions("L1 no", CLIP_TEXT, [], TERMS, bank=[])
    with pytest.raises(ValueError):
        pov.PovOut.model_validate({"emotion": "happiness", "captions": []})
