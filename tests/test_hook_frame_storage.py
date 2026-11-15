"""Hook options live on the candidate. The frame size lives on the clip."""

import json
import uuid

import pytest

from src.db import create_or_update_clip, get_candidate, get_clip, get_connection, insert_candidate, register_video


@pytest.fixture()
def video():
    vid = register_video("url", f"https://www.youtube.com/watch?v=hookframe&{uuid.uuid4().hex}", title="Hook and frame")
    yield vid
    with get_connection() as conn:  # keep the shared test DB's review queue clean for other tests
        conn.execute("DELETE FROM clips WHERE candidate_id IN (SELECT id FROM candidates WHERE video_id = ?)", (vid,))
        conn.execute("DELETE FROM candidates WHERE video_id = ?", (vid,))


def _cand(vid, **extra):
    return insert_candidate(vid, dict(origin="anime_judge", punchline="p", hook_text="h", post_caption="c", mood="laugh",
                                      humor_type="comedy_beat", status="selected", start_s=1.0, end_s=9.0,
                                      llm_score=80, final_score=80, title="t", **extra))


def test_a_candidate_keeps_its_hook_options(video):
    opts = {"relatable": "When the dirt wins:", "plain": "Krillin ranks below dirt"}
    assert json.loads(get_candidate(_cand(video, hook_options=opts))["hook_options"]) == opts
    assert get_candidate(_cand(video))["hook_options"] is None


def test_a_clip_starts_on_fit_and_none_keeps_the_stored_frame(video):
    cand = _cand(video)
    clip = create_or_update_clip(candidate_id=cand, file_path="a.mp4", thumb_path="a.jpg", layout="letterbox")
    assert get_clip(clip)["frame"] == "fit"
    create_or_update_clip(candidate_id=cand, file_path="a.mp4", thumb_path="a.jpg", layout="letterbox", frame="medium")
    assert get_clip(clip)["frame"] == "medium"
    create_or_update_clip(candidate_id=cand, file_path="a.mp4", thumb_path="a.jpg", layout="letterbox")
    assert get_clip(clip)["frame"] == "medium"
