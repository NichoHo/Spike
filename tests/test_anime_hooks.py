"""The anime judge writes three hook captions per clip; the title card starts with the first one that is filled in."""

from src.models import AnimeCandidate
from src.pipeline.anime_moments import build_prompt, pick_hooks


def _cand(**kw):
    base = {"punchline_line_idx": 1, "archetype": "comedy_beat",
            "scores": {"self_contained": 8, "payoff": 8, "setup_present": 8, "delivery": 8, "quotability": 8}}
    return AnimeCandidate.model_validate({**base, **kw})


def test_the_relatable_hook_is_the_default_and_the_others_are_kept():
    hook, opts = pick_hooks(_cand(hooks={"relatable": "When the dirt wins:", "curious": "Why is Krillin below the dirt?",
                                         "plain": "Krillin ranks below dirt"}))
    assert hook == "When the dirt wins:"
    assert list(opts) == ["relatable", "curious", "plain"]


def test_a_blank_voice_is_dropped_and_the_next_one_is_the_default():
    hook, opts = pick_hooks(_cand(hooks={"relatable": "  ", "curious": "Why?", "plain": "He loses"}))
    assert hook == "Why?" and list(opts) == ["curious", "plain"]


def test_hooks_are_one_line_and_at_most_80_characters():
    hook, opts = pick_hooks(_cand(hooks={"relatable": "When\nthe\x00dirt wins:", "plain": "x" * 200}))
    assert hook == "When the dirt wins:" and len(opts["plain"]) == 80


def test_an_older_single_hook_still_works_and_null_hooks_do_not_drop_the_clip():
    assert pick_hooks(_cand(hook_text="Old hook")) == ("Old hook", {})
    assert pick_hooks(_cand(hooks=None, hook_text="Old hook")) == ("Old hook", {})


def test_the_prompt_asks_for_the_three_voices():
    p = build_prompt([{"start": 1.0, "end": 3.0, "text": "Hello.", "speaker": None}], {},
                     {"title": "Dragon Ball Z", "characters": []}, {})
    assert "hooks (an object with relatable, curious and plain)" in p
    for voice in ("- relatable:", "- curious:", "- plain:"):
        assert voice in p
    assert "hook_text" not in p
