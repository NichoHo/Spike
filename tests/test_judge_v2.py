"""Judge, scores and stored candidates (Blueprint §6.7, Step 3)."""

import json

import pytest

import src.pipeline.stage7_moments as s7
from src.db import get_candidates, init_db, register_video
from src.models import LLMJudgeResponse


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


def test_stage7_stores_every_judged_candidate(tmp_path, monkeypatch):
    init_db()
    vid = register_video("url", f"https://example.test/{tmp_path.name}")
    transcript = {"duration": 400, "segments": [
        {"start": i * 2.0, "end": i * 2.0 + 2.0, "text": f"line {i}", "words": []} for i in range(200)]}
    peaks = [{"peak_t": float(t), "signal_score_raw": 1.0 + t / 1000, "context_start": t - 40.0, "context_end": t + 40.0,
              "clip_start": t - 10.0, "clip_end": t + 10.0, "origin": "signal", "signals_at_peak": {}}
             for t in (60, 140, 220, 300)]
    # judge answers in order: great, mediocre, not funny, plain rage with no contrast
    answers = iter([(80, True, "absurd"), (60, True, "absurd"), (30, False, "other"), (90, True, "rage")])

    def fake_judge(lines, comments, sigs, **kw):
        score, keep, humor = next(answers)
        return LLMJudgeResponse(keep=keep, why_funny="because", humor_type=humor, score=score, topic_start_line=8, setup_start_line=10,
                                payoff_line=18, reaction_end_line=22,
                                punchline="p", title="The streamer loses", hook_text="h", post_caption="c")

    monkeypatch.setattr(s7, "call_llm_judge", fake_judge)
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
    monkeypatch.setattr(s7, "propose_transcript_chunks", lambda *a, **k: [])
    monkeypatch.setattr(s7, "build_episodes", lambda *a, **k: [])
    with pytest.raises(RuntimeError, match="Nothing was stored"):
        s7.run_stage7_moments(vid, tmp_path, {"duration": 400, "webpage_url": ""}, transcript, {"peaks": peaks}, [])
    assert get_candidates(vid) == [] and not (tmp_path / "candidates.json").exists()
