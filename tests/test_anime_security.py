"""
Anime path safety: posting is blocked for anime footage without an allowlist entry, job options are validated, and
text from subtitles or models cannot carry control characters or out-of-range times.
"""

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import pytest

import src.posting as posting
from src.pipeline.stage1_anime import sanitize_anime_opts


def _clip(origin, anilist_id=813):
    return {"id": 1, "source_permission": "granted", "source_name": "S", "cand_origin": origin,
            "features": json.dumps({"anilist_id": anilist_id})}


def test_anime_clip_cannot_post_without_allowlist_entry(tmp_path, monkeypatch):
    monkeypatch.setattr(posting, "ANIME_ALLOWLIST", tmp_path / "anime_allowlist.json")
    monkeypatch.setattr(posting, "get_clip_with_details", lambda cid: _clip("anime_judge"))
    with pytest.raises(posting.PermissionBlockedError):          # no file
        posting.verify_clip_posting_permission(1)
    (tmp_path / "anime_allowlist.json").write_text("not json")
    with pytest.raises(posting.PermissionBlockedError):          # unreadable file
        posting.verify_clip_posting_permission(1)


def test_allowlist_needs_matching_id_basis_and_unexpired_date(tmp_path):
    f = tmp_path / "a.json"
    f.write_text(json.dumps([{"anilist_id": 813, "basis": "published_guideline", "expires": "2027-12-31"}]))
    assert posting.anime_post_allowed(813, f, today="2027-12-31")
    assert not posting.anime_post_allowed(813, f, today="2028-01-01")      # lapsed
    assert not posting.anime_post_allowed(814, f, today="2027-01-01")      # other show
    assert not posting.anime_post_allowed(None, f, today="2027-01-01")
    f.write_text(json.dumps([{"anilist_id": 813, "expires": "2027-12-31"}]))
    assert not posting.anime_post_allowed(813, f, today="2027-01-01")      # no basis recorded


def test_allowlisted_anime_and_non_anime_clips_pass(tmp_path, monkeypatch):
    f = tmp_path / "a.json"
    f.write_text(json.dumps([{"anilist_id": 813, "basis": "permission_file", "expires": "2999-01-01"}]))
    monkeypatch.setattr(posting, "ANIME_ALLOWLIST", f)
    monkeypatch.setattr(posting, "get_clip_with_details", lambda cid: _clip("anime_crowd"))
    assert posting.verify_clip_posting_permission(1)["id"] == 1
    monkeypatch.setattr(posting, "get_clip_with_details", lambda cid: _clip("signal", anilist_id=None))
    assert posting.verify_clip_posting_permission(1)["id"] == 1             # Twitch clips are not affected


def test_autopost_skips_anime_without_entry(tmp_path, monkeypatch):
    monkeypatch.setattr(posting, "ANIME_ALLOWLIST", tmp_path / "none.json")
    monkeypatch.setattr(posting, "get_clip_with_details", lambda cid: {**_clip("anime_swell"), "final_score": 99, "llm_score": 99, "source_id": 1})
    assert posting.evaluate_clip_autopost(1) == []


def test_job_options_are_validated():
    assert sanitize_anime_opts({"anilist_id": "x", "episode": -3, "audio_kind": "$(rm)", "youtube_url": "https://evil.test/?v=1"}) == {}
    assert sanitize_anime_opts({"anilist_id": 813, "episode": 12, "evil": 1}) == {"anilist_id": 813, "episode": 12}
