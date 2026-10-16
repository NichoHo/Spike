"""Creator profile, presets, learned preferences and the Sources profile editor (Blueprint §6.7)."""

import json

import pytest
from starlette.testclient import TestClient

import src.profile as profile
from src.config import CREATOR_PRESETS, CREATOR_TYPES
from src.db import create_source, delete_source, get_json_column, init_db, set_json_column
from src.web.app import app


def test_bad_enums_are_coerced_not_fatal():
    out = profile.CreatorProfileOut.model_validate({
        "creator_type": "Let's Player", "energy": "yelling", "humor_styles": ["rage", "bogus"], "notes": "x" * 900,
    })
    assert out.creator_type == "other" and out.energy == "medium"
    assert out.humor_styles == ["rage"] and len(out.notes) == 600


def test_every_creator_type_has_a_bounded_preset():
    for t in CREATOR_TYPES:
        p = CREATOR_PRESETS[t]
        assert p["min_len"] < p["max_len"]
        assert all(0.5 <= m <= 2 for m in p["weight_mult"].values())
    assert profile.get_preset(None) is CREATOR_PRESETS["other"]


def test_profile_block_stays_under_budget():
    ctx = {
        "profile": {"display_name": "Speed", "creator_type": "gaming", "energy": "loud",
                    "fans_clip": ["a long fan clip description " * 5] * 6, "notes": "n" * 600},
        "session": {"activity": "FIFA", "reaction_triggers": ["conceding a goal"]},
        "prefs": ["cut straight to the donation question"] * 10,
    }
    block = profile.profile_block(ctx)
    assert "Speed" in block and len(block) <= profile.BLOCK_MAX_CHARS
    assert profile.profile_block(None) == ""


def test_rebuild_keeps_user_edited_fields(monkeypatch):
    init_db()
    sid = create_source({"kind": "youtube", "external_id": "UC_test_profile", "display_name": "T"})
    try:
        set_json_column(sid, "creator_profile", {"display_name": "Speed", "creator_type": "gaming"})
        profile.save_user_edits(sid, {"display_name": "IShowSpeed", "notes": "hand written"})
        stored = get_json_column(sid, "creator_profile", {})
        assert set(stored["edited"]) == {"display_name", "notes"}

        monkeypatch.setattr("src.claude_cli.run_claude", lambda *a, **k: {
            "display_name": "Wrong", "creator_type": "podcast", "notes": "model notes"})
        monkeypatch.setattr(profile, "recent_titles", lambda meta: [])
        rebuilt = profile.build_creator_profile({"uploader": "x"}, {"segments": []}, stored)
        assert rebuilt["display_name"] == "IShowSpeed" and rebuilt["notes"] == "hand written"
        assert rebuilt["creator_type"] == "podcast"  # not edited, so the model's value wins
    finally:
        delete_source(sid)


def test_every_fifth_feedback_item_summarizes(monkeypatch):
    init_db()
    sid = create_source({"kind": "youtube", "external_id": "UC_test_prefs", "display_name": "T"})
    calls = []
    monkeypatch.setattr(profile, "_gemini_json", lambda prompt, cls: calls.append(prompt) or cls(prefs=["Skip sponsor reads"]))
    try:
        for i in range(4):
            profile.record_feedback(sid, f"too long {i}")
        assert not calls and get_json_column(sid, "learned_prefs", []) == []
        profile.record_feedback(sid, "too long 4")
        assert len(calls) == 1 and get_json_column(sid, "learned_prefs", []) == ["Skip sponsor reads"]
    finally:
        delete_source(sid)


def test_sources_page_edits_profile():
    init_db()
    sid = create_source({"kind": "youtube", "external_id": "UC_test_page", "display_name": "T"})
    try:
        with TestClient(app) as client:
            r = client.post(f"/sources/{sid}/profile", data={
                "display_name": "Speed", "creator_type": "gaming", "energy": "loud",
                "humor_styles": ["rage", "hubris"], "baseline_behaviors": "rages at every loss\nscreams",
            }, follow_redirects=False)
            assert r.status_code == 303
            page = client.get(f"/sources/{sid}")
            assert page.status_code == 200 and "rages at every loss" in page.text and "Rebuild profile" in page.text
            no_vod = client.post(f"/sources/{sid}/profile/rebuild", follow_redirects=False)
            assert no_vod.headers["location"].endswith("profile=no_vod")
        assert json.loads(json.dumps(get_json_column(sid, "creator_profile", {})))["baseline_behaviors"][1] == "screams"
    finally:
        delete_source(sid)


def test_episodes_saved_and_looked_up(tmp_path, monkeypatch):
    (tmp_path / "session_profile.json").write_text(profile.SessionProfile(activity="FIFA").model_dump_json())
    monkeypatch.setattr(profile, "_gemini_json", lambda prompt, cls: cls(episodes=[
        {"start_s": 600, "end_s": 1200, "label": "match 2"}, {"start_s": 0, "end_s": 600, "label": "match 1"}]))
    topics = [{"clip_start": 30, "topic": "rage"}]
    eps = profile.build_episodes(tmp_path, {"segments": []}, topics)
    assert [e["label"] for e in eps] == ["match 1", "match 2"]
    assert profile.episode_of(eps, 650) == 1 and profile.episode_of(eps, 5000) == -1
    # second call reads the saved file, no new model call
    monkeypatch.setattr(profile, "_gemini_json", lambda *a: 1 / 0)
    assert len(profile.build_episodes(tmp_path, {"segments": []}, topics)) == 2
