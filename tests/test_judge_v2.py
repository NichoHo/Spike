"""Judge, scores and stored candidates (Blueprint §6.7, Step 3)."""

import json

import pytest

import src.pipeline.stage7_moments as s7
from src import judge_pool
from src.db import get_candidates, init_db, register_video, set_setting
from src.judge_pool import GeminiUnavailable
from src.models import LLMJudgeResponse, VideoVerdict


def test_ties_share_average_rank():
    assert s7.percentile_avg_rank([50, 50]) == [75.0, 75.0]  # average rank 1.5 of 2
    p = s7.percentile_avg_rank([10, 20, 30])
    assert p[2] == 100.0 and p[0] < p[1] < p[2]


def test_streamer_name_replaces_generic_word():
    assert s7.fix_streamer("The streamer rages", "Speed") == "Speed rages"
    assert s7.fix_streamer("Streamer's loss", "Speed") == "Speed's loss"
    assert s7.fix_streamer("nothing here", "") == "nothing here"


def test_baseline_cap_needs_missing_contrast():
    base = ["rages at every conceded goal"]
    assert s7.apply_baseline_cap(90, "rage", False, base) == 55
    assert s7.apply_baseline_cap(90, "rage", True, base) == 90
    assert s7.apply_baseline_cap(90, "absurd", False, base) == 90
    assert s7.apply_baseline_cap(40, "rage", False, base) == 40


def test_hubris_before_uses_the_same_episode():
    eps = [{"start_s": 0, "end_s": 1000, "label": "m1"}, {"start_s": 1000, "end_s": 2000, "label": "m2"}]
    hub = [{"clip_start": 100, "clip_end": 120}]
    assert s7.has_hubris_before(500, hub, eps)
    assert not s7.has_hubris_before(1500, hub, eps)   # different episode
    assert not s7.has_hubris_before(90, hub, eps)     # hubris comes after


def test_judge_fields_are_ordered_and_coerced():
    fields = list(LLMJudgeResponse.model_fields)
    assert fields.index("why_funny") < fields.index("humor_type") < fields.index("needs_context") < fields.index("score")
    r = LLMJudgeResponse.model_validate({"keep": True, "humor_type": "Meltdown", "score": 70,
                                         "punchline": "p", "title": "t", "hook_text": "h", "post_caption": "c"})
    assert r.humor_type == "other"
    assert LLMJudgeResponse.model_validate({**r.model_dump(), "humor_type": "Skill"}).humor_type == "skill"


def test_stage7_stores_every_judged_candidate(tmp_path, monkeypatch, judge_by_window):
    init_db()
    vid = register_video("url", f"https://example.test/{tmp_path.name}")
    transcript = {"duration": 400, "segments": [
        {"start": i * 2.0, "end": i * 2.0 + 2.0, "text": f"line {i}", "words": []} for i in range(200)]}
    peaks = [{"peak_t": float(t), "signal_score_raw": 1.0 + t / 1000, "context_start": t - 40.0, "context_end": t + 40.0,
              "clip_start": t - 10.0, "clip_end": t + 10.0, "origin": "signal", "signals_at_peak": {}}
             for t in (60, 140, 220, 300)]
    # judge answers per peak: great, mediocre, not funny, plain rage with no contrast
    answers = [(80, True, "absurd"), (60, True, "absurd"), (30, False, "other"), (90, True, "rage")]

    def build(score, keep, humor):
        return LLMJudgeResponse(keep=keep, why_funny="because", humor_type=humor, score=score, topic_start_line=8, setup_start_line=10,
                                payoff_line=18, reaction_end_line=22,
                                punchline="p", title="The streamer loses", hook_text="h", post_caption="c")

    monkeypatch.setattr(s7, "call_llm_judge", judge_by_window([60, 140, 220, 300], answers, build))
    monkeypatch.setattr(s7, "read_whole_stream", lambda *a, **k: ("", []))
    monkeypatch.setattr(s7, "propose_transcript_chunks", lambda *a, **k: [
        {"type": "hubris", "peak_t": 390.0, "clip_start": 385.0, "clip_end": 395.0, "topic": "I never lose"}])
    monkeypatch.setattr(s7, "build_episodes", lambda *a, **k: [])
    monkeypatch.setattr(s7, "pairwise_rerank", lambda c, name="": c)
    monkeypatch.setattr("src.editor.run_claude", lambda *a, **k: (_ for _ in ()).throw(RuntimeError("no editor in this test")))
    ctx = {"profile": {"display_name": "Speed", "baseline_behaviors": ["rages at every loss"]}}

    picked = s7.run_stage7_moments(vid, tmp_path, {"duration": 400, "webpage_url": ""}, transcript,
                                   {"peaks": peaks, "has_chat": False}, [], profile_ctx=ctx)
    assert [c["title"] for c in picked] == ["Speed loses"]  # name replaced, only one above the 65 floor

    by_status = {}
    for row in get_candidates(vid):
        by_status.setdefault(row["status"], []).append(row)
    assert len(by_status["selected"]) == 1 and by_status["selected"][0]["llm_score"] == 80
    assert sorted(r["llm_score"] for r in by_status["low_score"]) == [55, 60]  # the rage 90 was capped to 55
    assert by_status["rejected"][0]["status_reason"].startswith("judge")
    assert len(by_status["hubris"]) == 1
    assert json.loads((tmp_path / "candidates.json").read_text())[0]["id"] == by_status["selected"][0]["id"]


class _FakeClient:
    def __init__(self, err):
        self.models = self
        self.err = err

    def generate_content(self, **kw):
        raise RuntimeError(self.err)


def test_daily_quota_raises_at_once_and_exhausted_retries_never_return_none(monkeypatch):
    monkeypatch.setattr(s7.time, "sleep", lambda s: None)
    quota = "429 RESOURCE_EXHAUSTED quota exceeded. Please retry in 7h33m11s."
    with pytest.raises(s7.QuotaExhausted):
        s7.generate_content_with_retry(_FakeClient(quota), "m", "x", None)
    with pytest.raises(RuntimeError):
        s7.generate_content_with_retry(_FakeClient("503 unavailable high demand"), "m", "x", None, max_retries=2)


def test_stage7_aborts_without_storing_when_the_judge_mostly_fails(tmp_path, monkeypatch):
    init_db()
    vid = register_video("url", f"https://example.test/{tmp_path.name}")
    transcript = {"duration": 400, "segments": [{"start": i * 2.0, "end": i * 2.0 + 2.0, "text": "x", "words": []} for i in range(200)]}
    peaks = [{"peak_t": float(t), "signal_score_raw": 1.0, "context_start": 0, "context_end": 1, "clip_start": t - 5.0,
              "clip_end": t + 5.0, "origin": "signal", "signals_at_peak": {}} for t in (60, 140, 220, 300)]
    monkeypatch.setattr(s7, "call_llm_judge", lambda *a, **k: None)
    monkeypatch.setattr(s7, "read_whole_stream", lambda *a, **k: ("", []))
    monkeypatch.setattr(s7, "propose_transcript_chunks", lambda *a, **k: [])
    monkeypatch.setattr(s7, "build_episodes", lambda *a, **k: [])
    with pytest.raises(RuntimeError, match="Nothing was stored"):
        s7.run_stage7_moments(vid, tmp_path, {"duration": 400, "webpage_url": ""}, transcript, {"peaks": peaks}, [])
    assert get_candidates(vid) == [] and not (tmp_path / "candidates.json").exists()


def test_skill_clip_starts_at_the_play_but_never_later_or_past_max_len():
    rec = {"start_s": 100.0, "end_s": 120.0, "cuts": [[110.0, 112.0]], "play_start_s": 90.0}
    s7.start_at_play(rec, 40.0)
    assert rec["start_s"] == 90.0
    rec.update(start_s=100.0, play_start_s=60.0)  # 120 - 2 s of cuts - 40 = 78 is as early as it may go
    s7.start_at_play(rec, 40.0)
    assert rec["start_s"] == 78.0
    rec.update(start_s=100.0, play_start_s=105.0)  # a play after the start never moves it later
    s7.start_at_play(rec, 40.0)
    assert rec["start_s"] == 100.0
    story = {"start_s": 100.0, "end_s": 120.0, "play_start_s": 90.0, "concept": "story"}
    s7.start_at_play(story, 40.0)
    assert story["start_s"] == 100.0


def test_video_judge_asks_for_the_play_start_only_on_skill_clips(monkeypatch):
    from types import SimpleNamespace
    from google.genai import types
    prompts = []

    def fake_generate(client, contents, config, **kw):
        prompts.append(contents[0].parts[1].text)
        return SimpleNamespace(text='{"what_happens": "x", "play_start": 9, "visible": true, "standalone": true, "score": 70}')

    monkeypatch.setattr(s7, "clip_video_part", lambda *a: types.Part(text="video"))
    monkeypatch.setattr(s7, "get_gemini_client", lambda: None)
    monkeypatch.setattr(s7, "judge_generate", fake_generate)
    assert s7.video_judge({}, 0.0, 30.0, "", "Kai", find_play=True).play_start == 9
    s7.video_judge({}, 0.0, 30.0, "", "Kai")
    assert '"play_start": 9' in prompts[0] and "play_start" not in prompts[1]


def test_video_gates_trim_and_line_proposals():
    from src.models import VideoVerdict
    v = lambda **k: VideoVerdict(**{"visible": True, "standalone": True, "reaction": "peak", "score": 85, **k})
    base = ["rages at every loss"]
    rec = {"humor_type": "rage"}
    s7.apply_video_verdict(rec, v(), base, contrast=False)
    assert rec["raw_llm_score"] == 85  # a peak meltdown passes even for a creator who rages often
    s7.apply_video_verdict(rec, v(reaction="routine"), base, contrast=False)
    assert rec["raw_llm_score"] == s7.BASELINE_CAP
    for bad in ({"visible": False}, {"standalone": False}, {"reaction": "reading_chat"}, {"reaction": "none"}):
        s7.apply_video_verdict(rec, v(**bad), [], contrast=False)
        assert rec["raw_llm_score"] == s7.GATED_SCORE

    lines = [{"start": i * 5.0, "end": i * 5.0 + 5.0} for i in range(30)]
    edges = {"start_s": 0.0, "end_s": 120.0, "payoff_t": 100.0, "cuts": [[5.0, 10.0], [60.0, 62.0]], "net_dur": 113.0}
    t = s7.trim_to_max(lines, edges, 40.0)
    assert t["end_s"] == 120.0 and t["start_s"] == 80.0 and t["cuts"] == [] and t["net_dur"] == 40.0

    meta = [{"start": i * 2.0, "end": i * 2.0 + 2.0} for i in range(100)]
    p = s7.line_proposal({"start_line": 11, "end_line": 12, "topic": "x"}, meta, 200.0, "stream")
    assert p["origin"] == "stream_read" and p["clip_end"] - p["clip_start"] == s7.MIN_CLIP_DURATION_S
    assert s7.line_proposal({"start_line": 0, "end_line": 3}, meta, 200.0, "moment") is None
    assert s7.line_proposal({"start_line": 5, "end_line": 500}, meta, 200.0, "moment") is None


def test_503_through_every_retry_raises_gemini_unavailable(monkeypatch):
    monkeypatch.setattr(s7.time, "sleep", lambda s: None)
    with pytest.raises(GeminiUnavailable):
        s7.generate_content_with_retry(_FakeClient("503 unavailable high demand"), "m", "x", None, max_retries=2)


def test_pool_calls_never_start_the_old_claude_popup(monkeypatch):
    monkeypatch.setattr(s7.time, "sleep", lambda s: None)
    monkeypatch.setattr(s7, "claude_instead", lambda *a, **k: pytest.fail("the per-call Claude popup started"))
    quota = "429 RESOURCE_EXHAUSTED quota exceeded. Please retry in 7h33m11s."
    with pytest.raises(s7.QuotaExhausted):
        s7.generate_content_with_retry(_FakeClient(quota), s7.DEFAULT_GEMINI_MODEL, "x", None, allow_claude=False)


def test_judge_hands_a_gemini_outage_to_the_pool(monkeypatch):
    def down(*a, **k):
        raise GeminiUnavailable("503 unavailable")

    monkeypatch.setattr(s7, "get_gemini_client", lambda: None)
    monkeypatch.setattr(s7, "generate_content_with_retry", down)
    with pytest.raises(GeminiUnavailable):
        s7.call_llm_judge(["L1 [00:01.0] hello"], "", {})


def test_judge_on_claude_runs_once_on_haiku_with_the_strict_schema(monkeypatch):
    seen = []
    answer = LLMJudgeResponse(keep=True, why_funny="w", humor_type="absurd", score=72, punchline="p", title="t",
                              hook_text="h", post_caption="c")

    def fake_claude(system, prompt, schema, **kw):
        seen.append((schema, kw.get("model")))
        return answer.model_dump()

    monkeypatch.setattr(s7, "get_gemini_client", lambda: None)
    monkeypatch.setattr("src.claude_cli.run_claude", fake_claude)
    res = s7.call_llm_judge(["L1 [00:01.0] hello"], "", {}, provider="claude")
    assert res.score == 72 and len(seen) == 1
    schema, model = seen[0]
    assert model == "haiku" and set(schema["required"]) == set(LLMJudgeResponse.model_fields)


def test_percentiles_rank_each_judge_against_itself():
    vals, groups = [10, 20, 30, 70, 80, 90], ["g", "g", "g", "c", "c", "c"]
    assert s7.percentile_by_group(vals, groups) == s7.percentile_avg_rank([10, 20, 30]) * 2
    assert s7.percentile_by_group([5, 1, 3], ["g", "g", "g"]) == s7.percentile_avg_rank([5, 1, 3])


def test_stage7_judges_on_claude_while_gemini_is_down_and_stores_the_judge(tmp_path, monkeypatch):
    init_db()
    vid = register_video("url", f"https://example.test/{tmp_path.name}")
    transcript = {"duration": 400, "segments": [
        {"start": i * 2.0, "end": i * 2.0 + 2.0, "text": f"line {i}", "words": []} for i in range(200)]}
    peaks = [{"peak_t": float(t), "signal_score_raw": 1.0, "context_start": t - 40.0, "context_end": t + 40.0,
              "clip_start": t - 10.0, "clip_end": t + 10.0, "origin": "signal", "signals_at_peak": {}}
             for t in (60, 140, 220, 300)]

    def judge(lines, comments, sigs, provider="gemini", **kw):
        if provider == "gemini":
            raise GeminiUnavailable("503 unavailable")
        return LLMJudgeResponse(keep=True, why_funny="w", humor_type="absurd", score=70, topic_start_line=8,
                                setup_start_line=10, payoff_line=18, reaction_end_line=22, punchline="p",
                                title="t", hook_text="h", post_caption="c")

    monkeypatch.setattr(s7, "call_llm_judge", judge)
    monkeypatch.setattr(s7, "read_whole_stream", lambda *a, **k: ("", []))
    monkeypatch.setattr(s7, "propose_transcript_chunks", lambda *a, **k: [])
    monkeypatch.setattr(s7, "build_episodes", lambda *a, **k: [])
    monkeypatch.setattr(s7, "pairwise_rerank", lambda c, name="": c)
    monkeypatch.setattr("src.editor.run_claude", lambda *a, **k: (_ for _ in ()).throw(RuntimeError("no editor in this test")))
    monkeypatch.setattr(judge_pool, "PROBE_START_S", 0.01)
    monkeypatch.setattr(judge_pool, "PROBE_MAX_S", 0.02)
    monkeypatch.setattr(judge_pool.claude_fallback, "ask", lambda *a, **k: True)
    set_setting(judge_pool.CLAUDE_USED_KEY, "")
    set_setting(judge_pool.HELP_KEY, "down")
    try:
        s7.run_stage7_moments(vid, tmp_path, {"duration": 400, "webpage_url": ""}, transcript,
                              {"peaks": peaks, "has_chat": False}, [])
    finally:
        set_setting(judge_pool.HELP_KEY, "off")
    rows = [r for r in get_candidates(vid) if r["status"] != "hubris"]
    assert len(rows) == 4 and {r["judge_model"] for r in rows} == {"claude-haiku"}
    cache = json.loads((tmp_path / "judge_cache.json").read_text())
    assert {v["judge_model"] for k, v in cache.items() if k.startswith("v3:")} == {"claude-haiku"}


def test_chunk_scan_runs_on_claude_while_gemini_is_down(monkeypatch):
    transcript = {"segments": [{"start": i * 2.0, "end": i * 2.0 + 2.0, "text": f"line {i}", "words": []}
                               for i in range(150)]}

    def down(*a, **k):
        raise GeminiUnavailable("503 unavailable")

    seen = []

    def fake_claude(system, prompt, schema, **kw):
        seen.append(schema)
        return {"moments": [{"start_line": 3, "end_line": 12, "topic": "a bit"}], "hubris": []}

    monkeypatch.setattr(s7, "get_gemini_client", lambda: None)
    monkeypatch.setattr(s7, "generate_content_with_retry", down)
    monkeypatch.setattr("src.claude_cli.run_claude", fake_claude)
    monkeypatch.setattr(judge_pool, "PROBE_START_S", 0.01)
    monkeypatch.setattr(judge_pool, "PROBE_MAX_S", 0.02)
    monkeypatch.setattr(judge_pool.claude_fallback, "ask", lambda *a, **k: True)
    set_setting(judge_pool.CLAUDE_USED_KEY, "")
    set_setting(judge_pool.HELP_KEY, "down")
    try:
        props = s7.propose_transcript_chunks(transcript, 300.0)
    finally:
        set_setting(judge_pool.HELP_KEY, "off")
    assert props and all(p["type"] == "moment" for p in props)
    assert seen and seen[0] is s7.CHUNK_SCHEMA


def test_video_judge_waits_for_gemini_instead_of_skipping(monkeypatch):
    calls = []

    def flaky(meta, start_s, end_s, story, streamer, find_play=False):
        calls.append(start_s)
        if len(calls) == 1:
            raise GeminiUnavailable("503 unavailable")
        return VideoVerdict(visible=True, standalone=True, reaction="peak", ends_on_reaction=True, score=80)

    monkeypatch.setattr(s7, "video_judge", flaky)
    monkeypatch.setattr(judge_pool, "PROBE_START_S", 0.01)
    out = s7.run_pool([s7.Task(lambda p: s7.video_judge({}, 1.0, 20.0, "", ""), claude_ok=False)], seed=1,
                      down_errors=(s7.QuotaExhausted, GeminiUnavailable))
    assert out[0][0] == "gemini" and out[0][1].score == 80 and len(calls) == 2
