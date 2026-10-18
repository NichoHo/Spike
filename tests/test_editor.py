"""Editor pass: outputs per concept, the rules enforced in code, POV captions, episode rule, Gemini fallback."""

import json

import numpy as np
import pytest

import src.pipeline.stage7_moments as s7
from src.claude_cli import ClaudeError, require_all
from src.concepts import context_terms
from src.db import get_candidates, init_db, register_video
from src.editor import (
    EditorOut,
    apply_output,
    build_prompt,
    enforce_episode_rule,
    finalize_pov,
)
from src.models import LLMJudgeResponse

PRESET = {"setup_pad_s": 3, "end_extend_max_s": 8, "min_len": 12, "max_len": 40, "zoom_scale": 1.2}
TERMS = context_terms(streamer="Speed", game="EA Sports FC Mobile", names=["Kvaratskhelia"])
NO_SERIES = [(np.zeros(1, dtype=np.float32), 0.25), (np.zeros(1, dtype=np.float32), 0.3), (np.zeros(1, dtype=np.float32), 0.0)]


def make_lines(first_n, t0, count, step=3.0):
    return [{"n": first_n + i, "start": t0 + i * step, "end": t0 + i * step + step - 0.2, "text": f"line {first_n + i}", "words": []}
            for i in range(count)]


def cand(label, t0, count=10, score=80, humor="rage", jump=10.0, kind="cand"):
    lines = make_lines(1, t0, count)
    rec = {"start_s": t0 + 3, "end_s": t0 + count * 3, "title": "old title", "hook_text": "old hook", "llm_score": score,
           "raw_llm_score": float(score), "humor_type": humor, "why_funny": "because", "peak_jump": jump, "cuts": [],
           "payoff_t": t0 + 12}
    return {"label": label, "kind": kind, "rec": rec, "lines": lines, "ann": [f"L{l['n']} text" for l in lines], "episode": 0}


def hubris(label, t0):
    lines = make_lines(1, t0, 3)
    rec = {"clip_start": t0, "clip_end": t0 + 9, "topic": "I never lose"}
    return {"label": label, "kind": "hubris", "rec": rec, "lines": lines, "ann": [], "episode": 0}


def span(source, a, b, **kw):
    return {"source": source, "start_line": a, "end_line": b, **kw}


def answer(*outputs):
    return EditorOut.model_validate({"outputs": list(outputs)})


def out(concept, rank, segments, title="Speed does a thing", hook_text="Speed does it", **kw):
    return {"concept": concept, "rank": rank, "segments": segments, "title": title, "hook_text": hook_text, **kw}


def words_at(t, text):
    return [{"word": f" {w}", "start": t + i * 0.4, "end": t + i * 0.4 + 0.3} for i, w in enumerate(text.split())]


def apply(o, sources, allowed=None, words=(), series=None, terms=TERMS):
    return apply_output(o, sources, PRESET, series or NO_SERIES, "Speed", allowed, words, terms)


# ── single ────────────────────────────────────────────────────────────────────

def test_single_maps_lines_to_seconds_clamps_zooms_and_names_the_streamer():
    src = cand("C1", 100.0)
    o = answer(out("single", 1, [span("C1", 2, 9, cut_lines=[4, 9, 2], zooms=[
        {"at_line": 8, "scale": 3.0, "hold_s": 99}, {"at_line": 999, "scale": 1.2, "hold_s": 1}])],
        title="The streamer melts down", hook_text="streamer loses it"))
    [rec], notes = apply(o, [src])
    assert rec is src["rec"] and not notes                          # edited in place
    assert abs(rec["start_s"] - 102.85) < 1e-6
    assert rec["cuts"] == [[109.0, 111.8]]                           # line 4 only: first and last lines are never cut
    assert rec["zooms"] == [{"t": 121.0, "scale": 1.5, "hold_s": 4.0}]
    assert rec["title"] == "Speed melts down" and rec["hook_text"] == "Speed loses it" and rec["concept"] == "single"


def test_a_bad_single_length_keeps_the_judge_edges_and_unknown_labels_are_dropped():
    src = cand("C1", 100.0, count=10)
    o = answer(out("single", 1, [span("C9", 1, 2)]), out("single", 2, [span("C1", 2, 3)], title="t", hook_text="h"))
    [rec], notes = apply(o, [src])
    assert (rec["start_s"], rec["end_s"]) == (103.0, 130.0) and rec["title"] == "t"
    assert any("unknown" in n for n in notes)


# ── story ─────────────────────────────────────────────────────────────────────

def story_inputs():
    h1, c1 = hubris("H1", 400.0), cand("C1", 1000.0, count=8)
    words = words_at(401.0, "I'm literally thrashing this guy") + words_at(1010.0, "no way he scored")
    return h1, c1, words


def story(**kw):
    base = dict(skip_card="3 goals later", callback_quote="literally thrashing", foreshadow=True)
    base.update(kw)
    return out("story", 1, [span("C1", 3, 8), span("H1", 1, 2)], title="Speed was so confident", **base)


def test_story_is_ordered_in_time_with_overlay_and_anchor_on_the_payoff():
    h1, c1, words = story_inputs()
    [rec], notes = apply(answer(story()), [h1, c1], words=words)
    assert not notes and rec["concept"] == "story" and rec["origin"] == "concept"
    assert [round(s["start_s"]) for s in rec["segs"]] == [400, 1006]                 # the model listed the payoff first
    assert rec["overlay"]["skip_card"] == "3 goals later" and rec["overlay"]["foreshadow"] is True
    assert rec["start_s"] == rec["segs"][0]["start_s"] and rec["end_s"] == rec["segs"][-1]["end_s"]
    assert rec["segments"] == [[s["start_s"], s["end_s"]] for s in rec["segs"]]
    assert rec["story_sources"] == ["H1", "C1"] and rec["_seg_recs"] == [h1["rec"], c1["rec"]]
    assert rec["raw_llm_score"] == 80 and rec["title"] == "Speed was so confident"   # judge fields come from the payoff


@pytest.mark.parametrize("change,reason", [
    (dict(callback_quote="never said this"), "callback quote is not said"),
    (dict(skip_card=""), "skip card"),
    (dict(skip_card="a very long skip card with far too many words"), "skip card"),
])
def test_story_breaking_a_rule_is_dropped_not_repaired(change, reason):
    h1, c1, words = story_inputs()
    recs, notes = apply(answer(story(**change)), [h1, c1], words=words)
    assert recs == [] and reason in notes[0]


def test_story_with_a_long_setup_or_a_short_total_is_dropped():
    h1, c1, words = story_inputs()
    long_setup = out("story", 1, [span("H1", 1, 3), span("C1", 3, 8)], skip_card="3 goals later", callback_quote="literally thrashing")
    assert "setup" in apply(answer(long_setup), [h1, c1], words=words)[1][0]          # 9 s setup, limit 8
    short = out("story", 1, [span("H1", 1, 2), span("C1", 3, 4)], skip_card="later", callback_quote="literally thrashing")
    assert "total" in apply(answer(short), [h1, c1], words=words)[1][0]


# ── pov ───────────────────────────────────────────────────────────────────────

def pov_inputs(speech="no no no bro"):
    c = cand("C1", 1000.0, count=8, humor="rage")
    jump = np.zeros(2000, dtype=np.float32)
    jump[1010:1013] = 20.0
    series = [(np.zeros(1, dtype=np.float32), 0.25), (np.zeros(1, dtype=np.float32), 0.3), (jump, 3.0)]
    return c, words_at(1010.0, speech), series


def test_pov_starts_before_the_peak_ends_with_the_outburst_and_waits_for_a_caption():
    c, words, series = pov_inputs()
    [rec], notes = apply(answer(out("pov", 1, [span("C1", 3, 7)])), [c], words=words, series=series)
    seg = rec["segs"][0]
    assert not notes and rec["concept"] == "pov" and rec["needs_pov"] is True
    assert seg["start_s"] == pytest.approx(1009.6) and 4.0 <= seg["end_s"] - seg["start_s"] <= 12.0
    assert seg["remove"] == [] and seg["zooms"] == [] and rec["overlay"]["pov_text"] == ""


def test_pov_whose_speech_names_the_game_a_player_chat_or_the_streamer_is_dropped():
    for speech in ("chat is cooking me", "Kvaratskhelia scored", "this EA game is rigged", "Speed what is that"):
        c, words, series = pov_inputs(speech)
        recs, notes = apply(answer(out("pov", 1, [span("C1", 3, 7)])), [c], words=words, series=series)
        assert recs == [] and "names" in notes[0], speech


def test_pov_captions_are_checked_in_code_and_a_failed_caption_call_drops_the_clip(monkeypatch):
    c, words, series = pov_inputs()
    [rec], _ = apply(answer(out("pov", 1, [span("C1", 3, 7)])), [c], words=words, series=series)
    good = {"emotion": "fury", "options": ["POV: you said one more round at midnight", "me when the wifi dies", "when mom walks in"],
            "text": "POV: you said one more round at midnight"}
    monkeypatch.setattr("src.pov.generate_pov_captions", lambda *a, **k: good)
    kept, notes = finalize_pov([rec], words, TERMS, PRESET)
    assert not notes and kept[0]["overlay"]["pov_text"] == good["text"] and kept[0]["overlay"]["pov_options"] == good["options"]
    assert "needs_pov" not in kept[0]

    c, words, series = pov_inputs()
    [rec], _ = apply(answer(out("pov", 1, [span("C1", 3, 7)])), [c], words=words, series=series)
    monkeypatch.setattr("src.pov.generate_pov_captions", lambda *a, **k: (_ for _ in ()).throw(ValueError("no caption passed")))
    assert finalize_pov([rec], words, TERMS, PRESET)[0] == []


# ── top 3 / top 5 ─────────────────────────────────────────────────────────────

def entries(n, scores=None):
    srcs = [cand(f"C{i}", 1000.0 * i, count=6, score=(scores or [80] * n)[i - 1]) for i in range(1, n + 1)]
    ranked = [span(f"C{i}", 2, 4, rank=n - i + 1, label=f"entry {n - i + 1}") for i in range(1, n + 1)]   # C1 is the worst, rank n
    return srcs, ranked


def test_top3_runs_weakest_first_with_labels():
    srcs, spans = entries(3)
    [rec], notes = apply(answer(out("top3", 1, spans[::-1], title="Every goal Kvaratskhelia scored on Speed", hook_text="Wait for number one", theme="goals")),
                         srcs, allowed=["top3"])
    assert not notes and [s["rank"] for s in rec["segs"]] == [3, 2, 1]
    assert [s["label"] for s in rec["segs"]] == ["entry 3", "entry 2", "entry 1"]
    assert rec["theme"] == "goals" and rec["concept"] == "top3"


def test_top5_is_only_allowed_when_enabled_and_every_entry_passes_the_floor():
    srcs, spans = entries(5, scores=[80, 80, 54, 80, 80])
    five = answer(out("top5", 1, spans, hook_text="Wait", theme="goals"))
    assert "not enabled" in apply(five, srcs, allowed=["single", "top3"])[1][0]
    assert "floor" in apply(five, srcs, allowed=["top5"])[1][0]
    srcs, spans = entries(5)
    assert len(apply(answer(out("top5", 1, spans, hook_text="Wait", theme="goals")), srcs, allowed=["top5"])[0]) == 1


def test_a_compilation_that_loses_an_entry_is_dropped_whole_never_padded():
    srcs, spans = entries(3)
    spans[1]["end_line"] = 2     # 1 line, about 3 s: under the 6 s entry minimum
    recs, notes = apply(answer(out("top3", 1, spans, hook_text="Wait", theme="goals")), srcs, allowed=["top3"])
    assert recs == [] and "entry" in notes[0]
    recs, notes = apply(answer(out("top3", 1, spans[:2], hook_text="Wait", theme="goals")), srcs, allowed=["top3"])
    assert recs == [] and "exactly 3" in notes[0]


def test_a_moment_appears_in_one_output_but_a_ranking_may_reuse_it():
    srcs, spans = entries(3)
    o = answer(
        out("top3", 1, spans, title="Ranking Speed's Funniest Moments"),
        out("single", 2, [span("C1", 2, 9)]),                      # also in the ranking: allowed
        out("single", 3, [span("C1", 2, 9)]),                      # C1 is already a single
    )
    recs, notes = apply(o, srcs, allowed=["single", "top3"])
    assert [r["concept"] for r in recs] == ["top3", "single"] and "already used" in notes[0]


# ── rules around the outputs ──────────────────────────────────────────────────

def test_episode_rule_covers_singles_and_stories_but_not_countdowns_or_pov():
    eps = [{"start_s": 0, "end_s": 1000, "label": "m1"}]

    def rec(start, score, concept="single", humor="rage", **kw):
        return {"start_s": start, "end_s": start + 20, "raw_llm_score": score, "humor_type": humor, "peak_jump": 5.0, "concept": concept, **kw}

    a, b = rec(100, 70), rec(300, 90)
    assert enforce_episode_rule([a, b], eps)[0] == [b]
    story_rec = rec(500, 60, concept="story", segs=[{"start_s": 500, "end_s": 520}])
    assert enforce_episode_rule([rec(600, 95), story_rec], eps)[0] == [story_rec]       # a story beats a single
    top, pov = rec(200, 60, concept="top3"), rec(400, 60, concept="pov")
    assert enforce_episode_rule([a, b, top, pov], eps)[0] == [b, top, pov]             # compilations and POV stay
    assert enforce_episode_rule([a, b], [])[0] == [a, b]


def test_prompt_lists_every_source_kind_and_the_schema_requires_every_field():
    eps = [{"start_s": 0, "end_s": 1000, "label": "FIFA match 1"}]
    text = build_prompt([cand("C1", 100.0), cand("R1", 500.0, kind="reaction"), hubris("H1", 50.0)], eps, "Creator: Speed")
    assert "Episode 1: FIFA match 1" in text and "C1:" in text and "R1 (plain reaction, POV only)" in text and "H1 (hubris line" in text
    schema = require_all(EditorOut.model_json_schema())
    assert schema["required"] == ["outputs"]
    assert {"concept", "segments", "theme", "skip_card", "callback_quote", "foreshadow"} <= set(schema["$defs"]["OutputOut"]["required"])


# ── stage 7 end to end with a fake Claude ─────────────────────────────────────

def _stage7_inputs(tmp_path):
    init_db()
    vid = register_video("url", f"https://example.test/{tmp_path.name}")
    transcript = {"duration": 3000, "segments": [
        {"start": i * 2.0, "end": i * 2.0 + 2.0, "text": f"line {i}", "words": [
            {"word": " literally", "start": i * 2.0, "end": i * 2.0 + 0.5}, {"word": " thrashing", "start": i * 2.0 + 0.6, "end": i * 2.0 + 1.1}]}
        for i in range(1500)]}
    peaks = [{"peak_t": float(t), "signal_score_raw": 1.0, "context_start": 0, "context_end": 1, "clip_start": t - 5.0,
              "clip_end": t + 5.0, "origin": "signal", "signals_at_peak": {}} for t in (200, 400, 1300, 1700)]
    return vid, transcript, peaks


def _patch_stage7(monkeypatch, scores):
    answers = iter(scores)

    def fake_judge(lines, comments, sigs, **kw):
        score, humor = next(answers)
        return LLMJudgeResponse(keep=True, why_funny="because", humor_type=humor, score=score, topic_start_line=30,
                                setup_start_line=32, payoff_line=45, reaction_end_line=48, punchline="p",
                                title="Speed loses", hook_text="h", post_caption="c", contrast=True)

    monkeypatch.setattr(s7, "call_llm_judge", fake_judge)
    monkeypatch.setattr(s7, "read_whole_stream", lambda *a, **k: ("", []))
    monkeypatch.setattr(s7, "propose_transcript_chunks", lambda *a, **k: [
        {"type": "hubris", "peak_t": 334.0, "clip_start": 330.0, "clip_end": 338.0, "topic": "I never lose"}])
    monkeypatch.setattr(s7, "build_episodes", lambda *a, **k: [
        {"start_s": 0, "end_s": 1000, "label": "match 1"}, {"start_s": 1000, "end_s": 3000, "label": "match 2"}])
    monkeypatch.setattr(s7, "pairwise_rerank", lambda c, name="": c)


def test_stage7_stores_a_story_with_segment_ids_and_marks_its_components(tmp_path, monkeypatch):
    vid, transcript, peaks = _stage7_inputs(tmp_path)
    _patch_stage7(monkeypatch, [(80, "rage"), (75, "rage"), (70, "absurd"), (90, "rage")])
    captured = {}

    def fake_claude(system, prompt, schema, video_id=None, label=""):
        captured["prompt"], captured["system"] = prompt, system
        return {"outputs": [
            out("story", 1, [span("H1", 1, 2), span("C1", 31, 46)], title="The streamer talks then loses",
                skip_card="3 goals later", callback_quote="literally thrashing"),
            out("single", 2, [span("C3", 31, 46)], title="solo", hook_text="solo"),
        ]}

    monkeypatch.setattr("src.editor.run_claude", fake_claude)
    ctx = {"profile": {"display_name": "Speed"}, "preset": PRESET}
    picked = s7.run_stage7_moments(vid, tmp_path, {"duration": 3000, "webpage_url": ""}, transcript,
                                   {"peaks": peaks, "has_chat": False}, [], profile_ctx=ctx)
    assert "Episode 1: match 1" in captured["prompt"] and "H1 (hubris line" in captured["prompt"] and "allowed: single, story, pov, top3" in captured["system"]
    story_rec = next(c for c in picked if c["concept"] == "story")
    assert story_rec["title"] == "Speed talks then loses" and len(story_rec["segs"]) == 2

    rows = {r["id"]: r for r in get_candidates(vid)}
    row = next(r for r in rows.values() if r["concept"] == "story")
    spec = json.loads(row["concept_spec"])
    assert row["status"] == "selected" and spec["concept_source"] == "ai" and spec["overlay"]["skip_card"] == "3 goals later"
    assert spec["segments"][0]["candidate_id"] in rows and rows[spec["segments"][0]["candidate_id"]]["status"] == "hubris"
    assert spec["segments"][1]["candidate_id"] in rows and json.loads(row["segments"]) == [[s["start_s"], s["end_s"]] for s in spec["segments"]]
    assert "part of a Story clip" in {r["status_reason"] for r in rows.values() if r["status"] == "low_score"}
    assert json.loads((tmp_path / "candidates.json").read_text())[0]["id"] in rows


def test_stage7_falls_back_to_the_gemini_ranking_when_claude_fails(tmp_path, monkeypatch):
    vid, transcript, peaks = _stage7_inputs(tmp_path)
    _patch_stage7(monkeypatch, [(80, "absurd"), (75, "cringe"), (70, "roast"), (90, "deadpan")])
    monkeypatch.setattr("src.editor.run_claude", lambda *a, **k: (_ for _ in ()).throw(ClaudeError("plan limit reached")))
    ctx = {"profile": {"display_name": "Speed"}, "preset": PRESET}
    picked = s7.run_stage7_moments(vid, tmp_path, {"duration": 3000, "webpage_url": ""}, transcript,
                                   {"peaks": peaks, "has_chat": False}, [], profile_ctx=ctx)
    assert len(picked) == 4 and all(c["zooms"] and c["zooms"][0]["scale"] == 1.2 for c in picked)  # default zoom at the payoff
