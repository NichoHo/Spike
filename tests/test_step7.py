"""Step 7: stream time chips, Other moments, zooms, manual cuts, Ask the editor, moment render jobs."""

import json
import subprocess
from pathlib import Path

import pytest
from starlette.testclient import TestClient

import src.worker as worker
from src.claude_cli import ClaudeError
from src.db import (
    create_or_update_clip,
    get_candidate,
    get_clip,
    get_connection,
    init_db,
    insert_candidate,
    list_clip_ai_edits,
    register_video,
)
from src.web.app import app
from src.web.filters import filter_stream_link, filter_stream_time

YT = "https://www.youtube.com/watch?v=abc123xyz00"


def test_stream_time_and_links():
    assert filter_stream_time(952) == "15:52"
    assert filter_stream_time(952.9) == "15:52"           # rounded down, like the &t= second
    assert filter_stream_time(4552) == "1:15:52"
    assert filter_stream_time(5) == "0:05"
    assert filter_stream_link(YT + "&", 952) == YT + "&t=952s"
    assert filter_stream_link("https://youtu.be/abc123xyz00?t=3", 70) == "https://youtu.be/abc123xyz00?t=70s"
    assert filter_stream_link("https://www.twitch.tv/videos/12345", 952) == "https://www.twitch.tv/videos/12345?t=0h15m52s"
    assert filter_stream_link("https://www.twitch.tv/videos/12345", 4552) == "https://www.twitch.tv/videos/12345?t=1h15m52s"
    assert filter_stream_link("C:/videos/my stream.mp4", 5) == "" and filter_stream_link(None, 5) == ""


@pytest.fixture()
def clip(tmp_path, monkeypatch):
    """A finished video with one rendered clip, one stored low_score moment, and a real 20 s section (stream 100 to 120)."""
    init_db()
    for mod in ("src.web.routes.clips", "src.config", "src.moment_render"):
        monkeypatch.setattr(f"{mod}.VIDEOS_DIR", tmp_path, raising=False)
    vid = register_video("url", f"{YT}&{tmp_path.name}", title="Test stream")
    vdir = tmp_path / str(vid)
    (vdir / "sections").mkdir(parents=True)
    (vdir / "renders").mkdir()
    sec = vdir / "sections" / "section_X.mp4"
    subprocess.run(["ffmpeg", "-y", "-hide_banner", "-loglevel", "error", "-f", "lavfi", "-i", "testsrc=size=1280x720:rate=30:duration=20",
                    "-f", "lavfi", "-i", "sine=frequency=440:duration=20", "-c:v", "libx264", "-preset", "ultrafast", "-c:a", "aac",
                    "-shortest", str(sec)], check=True)
    words = [{"word": f" w{i}", "start": 100.0 + i * 0.5, "end": 100.0 + i * 0.5 + 0.4} for i in range(40)]
    (vdir / "meta.json").write_text(json.dumps({"uploader": "Speed", "webpage_url": YT, "duration": 3000}))
    (vdir / "transcript.json").write_text(json.dumps({"segments": [{"start": 100, "end": 120, "text": "x", "words": words}]}))
    base = dict(origin="llm_chunk", punchline="p", hook_text="hook", post_caption="c", mood="laugh", humor_type="rage")
    cand = insert_candidate(vid, {**base, "start_s": 105.0, "end_s": 113.0, "status": "selected", "llm_score": 82, "final_score": 80,
                                  "title": "Speed loses it", "payoff_t": 108.0, "zooms": [{"t": 108.0, "scale": 1.2, "hold_s": 1.5}]})
    low = insert_candidate(vid, {**base, "start_s": 900.0, "end_s": 930.0, "status": "low_score", "llm_score": 58, "final_score": 58,
                                 "title": "Quiet bit", "status_reason": "raw score 58 below 65"})
    sec.rename(vdir / "sections" / f"section_{cand}.mp4")
    (vdir / "sections" / f"section_{cand}.json").write_text(json.dumps({"start_s": 100.0}))
    clip_file = vdir / "renders" / f"clip_{cand}.mp4"
    clip_file.write_bytes((vdir / "sections" / f"section_{cand}.mp4").read_bytes())
    clip_id = create_or_update_clip(candidate_id=cand, file_path=str(clip_file), thumb_path="", trim_start_s=105.0, trim_end_s=113.0,
                                    zooms=json.dumps([{"t": 108.0, "scale": 1.2, "hold_s": 1.5}]), cuts=json.dumps([]))
    return {"client": TestClient(app), "video": vid, "cand": cand, "low": low, "clip": clip_id, "dir": vdir}


def test_review_page_shows_stream_time_and_other_moments(clip):
    html = clip["client"].get("/").text
    assert 'href="' + YT + '&amp;t=105s"' in html or YT + "&t=105s" in html   # 1:45 links to the source
    assert ">1:45" in html
    assert "Other moments (1)" in html and "Quiet bit" in html and "raw score 58 below 65" in html
    assert f'action="/candidates/{clip["low"]}/render"' in html


def test_clip_page_has_zoom_cut_and_editor_controls(clip):
    html = clip["client"].get(f"/clips/{clip['clip']}").text
    for needle in ('id="btn-zoom"', 'id="zoom-popover"', 'id="edit-strip"', "Cut this part", "Mark start", "Mark end",
                   "Ask the editor", f'action="/clips/{clip["clip"]}/ai-edit"', "Use playhead", "Apply &amp; re-render", 't=105s'):
        assert needle in html, needle
    assert "punch_in_zoom" not in html and "controls" not in html.split('id="main-clip-player"')[1].split(">")[0]
    assert '"t": 108' in html or '"t":108' in html   # the stored zoom reaches the page


def test_moment_render_is_queued_once_and_runs_in_the_worker(clip, monkeypatch):
    c = clip["client"]
    assert c.post(f"/candidates/{clip['low']}/render", follow_redirects=False).status_code == 303
    c.post(f"/candidates/{clip['low']}/render", follow_redirects=False)
    with get_connection() as conn:
        assert conn.execute("SELECT COUNT(*), MAX(status) FROM candidate_renders WHERE candidate_id = ?", (clip["low"],)).fetchone()[:] == (1, "queued")
    assert "Queued" in c.get("/").text

    ran = []
    monkeypatch.setattr(worker, "render_candidate", lambda cid: ran.append(cid))
    assert worker.run_render_cycle() is True and ran == [clip["low"]]
    assert worker.run_render_cycle() is False
    assert get_candidate(clip["low"])["status"] == "selected"      # a real pick now, no longer in Other moments

    # a failed render shows its error and offers another try
    with get_connection() as conn:
        conn.execute("UPDATE candidates SET status = 'low_score' WHERE id = ?", (clip["low"],))
    c.post(f"/candidates/{clip['low']}/render", follow_redirects=False)
    monkeypatch.setattr(worker, "render_candidate", lambda cid: (_ for _ in ()).throw(RuntimeError("video files are gone")))
    worker.run_render_cycle()
    html = c.get("/").text
    assert "Try again" in html and "video files are gone" in html


def test_rerender_keeps_stored_zooms_and_cuts_unless_the_form_sends_new_ones(clip):
    c, cid = clip["client"], clip["clip"]
    form = {"start_s": "105", "end_s": "113", "layout": "center", "caption_style": "bold_pop", "letterbox_style": "blur"}
    assert c.post(f"/clips/{cid}/rerender", data=form, follow_redirects=False).status_code == 303
    row = get_clip(cid)
    assert row["status"] == "ready" and json.loads(row["zooms"]) == [{"t": 108.0, "scale": 1.2, "hold_s": 1.5}]

    new = {**form, "zooms": json.dumps([{"t": 107, "scale": 9, "hold_s": 0.1}, {"t": 500, "scale": 1.2, "hold_s": 1}]),
           "cuts": json.dumps([[109.0, 110.0], [109.5, 111.0], [300, 301]])}
    c.post(f"/clips/{cid}/rerender", data=new, follow_redirects=False)
    row = get_clip(cid)
    assert json.loads(row["zooms"]) == [{"t": 107.0, "scale": 1.5, "hold_s": 0.3}]   # clamped, out-of-clip zoom dropped
    assert json.loads(row["cuts"]) == [[109.0, 111.0]]                                # merged, out-of-clip cut dropped
    # the page now treats those cuts as part of the video it plays
    assert "109.0" in c.get(f"/clips/{cid}").text


def test_ask_the_editor_applies_the_answer_and_learns_from_the_comment(clip, monkeypatch):
    c, cid = clip["client"], clip["clip"]
    seen = {}

    def fake_claude(system, prompt, schema, video_id=None, label=""):
        seen["prompt"] = prompt
        return {"start_s": 104.0, "end_s": 114.0, "remove": [[108.0, 109.0]], "zooms": [{"t": 110.0, "scale": 1.35, "hold_s": 2.0}],
                "title": "The streamer reacts", "explanation": "Moved the start 1 s earlier and cut the pause."}

    monkeypatch.setattr("src.ai_edit.run_claude", fake_claude)
    noted = []
    monkeypatch.setattr("src.profile.record_feedback", lambda sid, text: noted.append(text))
    r = c.post(f"/clips/{cid}/ai-edit", data={"comment": "start a bit earlier and cut the pause"}, follow_redirects=False)
    assert r.status_code == 303

    assert "start a bit earlier" in seen["prompt"] and "w5@" in seen["prompt"]    # word-level transcript is in the prompt
    row = get_clip(cid)
    assert row["status"] == "ready" and (row["trim_start_s"], row["trim_end_s"]) == (104.0, 114.0)
    assert json.loads(row["cuts"]) == [[108.0, 109.0]] and json.loads(row["zooms"])[0]["scale"] == 1.35
    assert get_candidate(clip["cand"])["title"] == "Speed reacts"                    # name fixed, title applied
    assert noted == ["Edit request: start a bit earlier and cut the pause"]
    [h] = list_clip_ai_edits(cid)
    assert h["ok"] and h["comment"].startswith("start a bit") and "Moved the start" in h["result"]["explanation"]
    assert "Moved the start 1 s earlier" in c.get(f"/clips/{cid}").text


def test_ask_the_editor_widens_the_section_when_the_edges_leave_it(clip, monkeypatch):
    calls = []
    monkeypatch.setattr("src.ai_edit.run_claude", lambda *a, **k: {
        "start_s": 90.0, "end_s": 114.0, "remove": [], "zooms": [], "title": "", "explanation": "Starts earlier."})
    monkeypatch.setattr("src.pipeline.stage8_sections.refetch_section", lambda *a, **k: calls.append(a[2:]) or None)
    clip["client"].post(f"/clips/{clip['clip']}/ai-edit", data={"comment": "start 15 s earlier"}, follow_redirects=False)
    assert calls and calls[0][1] == 90.0           # section 100 to 120 does not cover 90, so it is fetched again first


def test_ask_the_editor_failure_keeps_the_old_render_and_says_why(clip, monkeypatch):
    monkeypatch.setattr("src.ai_edit.run_claude", lambda *a, **k: (_ for _ in ()).throw(ClaudeError("plan limit reached")))
    c, cid = clip["client"], clip["clip"]
    before = get_clip(cid)["file_path"]
    c.post(f"/clips/{cid}/ai-edit", data={"comment": "make it shorter"}, follow_redirects=False)
    row = get_clip(cid)
    assert row["status"] == "ready" and row["file_path"] == before
    assert "Could not apply: plan limit reached" in c.get(f"/clips/{cid}").text
