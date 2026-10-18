"""Concepts in the web app: picker, switching, POV captions, re-render and Ask the editor through the real renderer."""

import json
import subprocess
from pathlib import Path

import numpy as np
import pytest
from starlette.testclient import TestClient

import src.worker as worker
from src.concept_build import FillOut
from src.db import (
    create_or_update_clip,
    create_source,
    get_candidate,
    get_clip,
    get_connection,
    get_json_column,
    init_db,
    insert_candidate,
    register_video,
)
from src.pov import load_bank
from src.web.app import app

YT = "https://www.youtube.com/watch?v=abc123xyz00"
GOOD_CAPTIONS = {"emotion": "fury", "options": ["POV: you said one more round at midnight", "me when the wifi dies mid download",
                                                  "when mom turns off the router at 10"], "text": "POV: you said one more round at midnight"}


def probe_duration(path) -> float:
    return float(subprocess.run(["ffprobe", "-v", "error", "-show_entries", "format=duration", "-of", "csv=p=0", str(path)],
                                capture_output=True, text=True, check=True).stdout)


@pytest.fixture()
def env(tmp_path, monkeypatch):
    """A video made from a 60 s local source, with five stored moments, a single clip and signals with a reaction at 30 s."""
    init_db()
    monkeypatch.chdir(Path(__file__).resolve().parent.parent)
    # tmp_path sits outside the project, but ffmpeg gets ASS files as relative paths: keep the video dir inside it
    vroot = Path(__file__).resolve().parent.parent / "data" / f"_test_videos_{tmp_path.name}"   # never the real data/videos
    vroot.mkdir(parents=True)
    monkeypatch.setattr("src.config.VIDEOS_DIR", vroot)
    vid = register_video("url", f"{YT}&{tmp_path.name}", title="Test stream")
    vdir = vroot / str(vid)
    (vdir / "sections").mkdir(parents=True)
    (vdir / "renders").mkdir()
    for mod in ("src.web.routes.clips", "src.moment_render", "src.concept_build"):
        monkeypatch.setattr(f"{mod}.VIDEOS_DIR", vroot, raising=False)
    source = vdir / "stream.mp4"
    subprocess.run(["ffmpeg", "-y", "-hide_banner", "-loglevel", "error", "-f", "lavfi", "-i", "testsrc=size=1280x720:rate=30:duration=60",
                    "-f", "lavfi", "-i", "sine=frequency=440:duration=60", "-c:v", "libx264", "-preset", "ultrafast", "-c:a", "aac",
                    "-shortest", str(source)], check=True)
    words = [{"word": f" w{i}", "start": 5.0 + i * 0.5, "end": 5.0 + i * 0.5 + 0.4} for i in range(100)]
    (vdir / "meta.json").write_text(json.dumps({"uploader": "Speed", "webpage_url": YT, "duration": 60, "is_local": True, "local_path": str(source)}))
    (vdir / "transcript.json").write_text(json.dumps({"segments": [{"start": 5, "end": 55, "text": "x", "words": words}]}))
    jump = np.zeros(80, dtype=np.float32)
    jump[30:32] = 20.0
    np.savez(vdir / "signals.npz", voice_jump=jump, jump_thr=np.float32(5.0))

    base = dict(origin="llm_chunk", punchline="p", hook_text="hook", post_caption="c", mood="laugh", humor_type="rage", status="low_score")
    ids = []
    for k, (a, b, score) in enumerate([(5, 14, 80), (16, 25, 70), (27, 36, 90), (38, 47, 60), (49, 58, 75)], 1):
        ids.append(insert_candidate(vid, {**base, "start_s": float(a), "end_s": float(b), "llm_score": score, "final_score": score,
                                          "title": f"Moment {k}", "payoff_t": float(a + 4)}))
    hubris = insert_candidate(vid, {**base, "start_s": 1.0, "end_s": 4.0, "status": "hubris", "title": "I never lose", "humor_type": "hubris"})
    cand = ids[2]
    with get_connection() as conn:
        conn.execute("UPDATE candidates SET status = 'selected' WHERE id = ?", (cand,))
    sec = vdir / "sections" / f"section_{cand}.mp4"
    subprocess.run(["ffmpeg", "-y", "-hide_banner", "-loglevel", "error", "-ss", "22", "-to", "41", "-i", str(source), "-c:v", "libx264",
                    "-preset", "ultrafast", "-c:a", "aac", str(sec)], check=True)
    sec.with_suffix(".json").write_text(json.dumps({"start_s": 22.0}))
    clip_file = vdir / "renders" / f"clip_{cand}.mp4"
    clip_file.write_bytes(sec.read_bytes())
    clip_id = create_or_update_clip(candidate_id=cand, file_path=str(clip_file), thumb_path="", trim_start_s=27.0, trim_end_s=36.0,
                                    zooms="[]", cuts="[]")
    yield {"c": TestClient(app), "vid": vid, "ids": ids, "hubris": hubris, "cand": cand, "clip": clip_id, "dir": vdir}
    import shutil
    shutil.rmtree(vroot, ignore_errors=True)


def test_clip_page_has_the_concept_section_picker_and_bank(env):
    html = env["c"].get(f"/clips/{env['clip']}").text
    for needle in ('id="concept-radios"', 'name="concept_choice"', 'id="panel-pov"', 'id="panel-story"', 'id="panel-top"', 'id="concept-ai-tag"',
                   'id="pov-new"', 'id="pov-bank-btn"', 'id="moment-picker"', 'id="bank-dialog"', 'name="concept"', 'name="segments"',
                   'name="overlay"', 'name="concept_source"', 'data-for="single"', 'Ask the editor'):
        assert needle in html, needle
    assert html.index('id="concept-section"') < html.index('Framing layout')    # its own section, not inside Layout


def test_moments_endpoint_lists_every_stored_candidate(env):
    moments = env["c"].get(f"/videos/{env['vid']}/moments").json()["moments"]
    assert len(moments) == 6 and {m["status"] for m in moments} == {"low_score", "selected", "hubris"}
    first = moments[1]
    assert first["time"] == "0:05" and first["link"].endswith("&t=5s") and first["title"] == "Moment 1"


def test_picker_enforces_the_count_rule_keeps_the_order_and_queues_a_worker_job(env, monkeypatch):
    c, vid, ids = env["c"], env["vid"], env["ids"]
    r = c.post(f"/videos/{vid}/concept", json={"concept": "top3", "candidate_ids": ids[:2]})
    assert r.status_code == 400 and "exactly 3" in r.json()["error"]
    assert c.post(f"/videos/{vid}/concept", json={"concept": "story", "candidate_ids": ids[:1]}).status_code == 400
    assert c.post(f"/videos/{vid}/concept", json={"concept": "nope", "candidate_ids": ids[:1]}).status_code == 400

    monkeypatch.setattr("src.concept_build.fill_text", lambda *a, **k: FillOut(
        title="Every goal Speed conceded", hook_text="Speed, wait for #1", theme="goals", labels=["he blamed chat", "he blamed the ref", "the loss"]))
    r = c.post(f"/videos/{vid}/concept", json={"concept": "top3", "candidate_ids": [ids[3], ids[0], ids[4]]})   # picked in this order
    body = r.json()
    assert r.status_code == 200 and body["ok"]
    cand = get_candidate(body["candidate_id"])
    spec = json.loads(cand["concept_spec"])
    assert cand["concept"] == "top3" and cand["status"] == "selected" and spec["concept_source"] == "user"
    assert [s["candidate_id"] for s in spec["segments"]] == [ids[3], ids[0], ids[4]]       # the user's order
    assert [s["rank"] for s in spec["segments"]] == [3, 2, 1] and [s["label"] for s in spec["segments"]][-1] == "the loss"
    with get_connection() as conn:
        assert conn.execute("SELECT status FROM candidate_renders WHERE candidate_id = ?", (body["candidate_id"],)).fetchone()[0] == "queued"

    # the worker renders it for real: three entries under the ranking header, joined and loudness-normalised
    assert worker.run_render_cycle() is True
    clip = get_clip(_clip_for(body["candidate_id"]))
    assert clip["concept"] == "top3" and clip["status"] == "ready" and clip["concept_source"] == "user"
    assert [s["rank"] for s in json.loads(clip["segments"])] == [3, 2, 1] and json.loads(clip["overlay"])["pov_text"] == ""
    assert abs(probe_duration(clip["file_path"]) - 9.0 * 3) < 2.0
    assert clip["theme"] == "goals"
    html = c.get("/").text
    assert "Top 3" in html


def _clip_for(candidate_id):
    with get_connection() as conn:
        return conn.execute("SELECT id FROM clips WHERE candidate_id = ?", (candidate_id,)).fetchone()[0]


def test_switching_to_pov_finds_the_peak_and_writes_captions(env, monkeypatch):
    monkeypatch.setattr("src.pov.generate_pov_captions", lambda *a, **k: GOOD_CAPTIONS)
    r = env["c"].post(f"/clips/{env['clip']}/concept/to-pov")
    body = r.json()
    assert r.status_code == 200, r.text
    assert body["concept"] == "pov"
    seg = body["segments"][0]
    assert seg["start_s"] == pytest.approx(29.6) and 4.0 <= seg["end_s"] - seg["start_s"] <= 12.0     # 0.4 s before the 30 s peak
    assert body["overlay"]["pov_text"] == GOOD_CAPTIONS["text"] and body["overlay"]["emotion"] == "fury"

    monkeypatch.setattr("src.pov.generate_pov_captions", lambda *a, **k: (_ for _ in ()).throw(ValueError("no caption passed")))
    assert env["c"].post(f"/clips/{env['clip']}/concept/to-pov").status_code == 400


def test_new_captions_are_saved_on_the_clip_so_they_survive_a_reload(env, monkeypatch):
    monkeypatch.setattr("src.pov.generate_pov_captions", lambda *a, **k: GOOD_CAPTIONS)
    r = env["c"].post(f"/clips/{env['clip']}/pov/captions", json={"start_s": 29.6, "end_s": 35.0})
    assert r.status_code == 200 and r.json()["options"] == GOOD_CAPTIONS["options"]
    assert json.loads(get_clip(env["clip"])["overlay"])["pov_options"] == GOOD_CAPTIONS["options"]
    monkeypatch.setattr("src.pov.generate_pov_captions", lambda *a, **k: (_ for _ in ()).throw(RuntimeError("down")))
    assert env["c"].post(f"/clips/{env['clip']}/pov/captions", json={"start_s": 29.6, "end_s": 35.0}).status_code == 502


def test_rerender_as_pov_then_back_to_single_goes_through_the_one_render_path(env):
    c, cid = env["c"], env["clip"]
    pov_seg = [{"candidate_id": env["cand"], "start_s": 29.6, "end_s": 36.0, "remove": [], "rank": None, "label": ""}]
    form = {"start_s": "27", "end_s": "36", "layout": "center", "caption_style": "bold_pop", "letterbox_style": "blur",
            "concept": "pov", "segments": json.dumps(pov_seg), "concept_source": "user",
            "overlay": json.dumps({"pov_text": "POV: you said one more round at midnight", "emotion": "fury", "pov_options": GOOD_CAPTIONS["options"]})}
    assert c.post(f"/clips/{cid}/rerender", data=form, follow_redirects=False).status_code == 303
    row = get_clip(cid)
    assert row["status"] == "ready" and row["concept"] == "pov" and row["concept_source"] == "user"
    assert json.loads(row["segments"])[0]["start_s"] == 29.6 and json.loads(row["overlay"])["pov_text"].startswith("POV:")
    assert abs(probe_duration(row["file_path"]) - 6.4) < 0.5
    page = c.get(f"/clips/{cid}").text
    assert 'POV: you said one more round at midnight' in page and 'is-on' not in page.split('id="pov-chips"')[0]

    back = {**form, "concept": "single", "start_s": "29.6", "end_s": "36.0"}
    c.post(f"/clips/{cid}/rerender", data=back, follow_redirects=False)
    row = get_clip(cid)
    assert row["status"] == "ready" and row["concept"] == "single" and row["segments"] == "[]"


def test_ask_the_editor_can_make_a_pov_and_ask_for_new_captions(env, monkeypatch):
    c, cid = env["c"], env["clip"]
    seen = {}

    def fake_claude(system, prompt, schema, video_id=None, label=""):
        seen["prompt"] = prompt
        return {"start_s": 27, "end_s": 36, "remove": [], "zooms": [], "title": "", "explanation": "Made it a POV on the scream.",
                "concept": "pov", "segments": [{"candidate_id": env["cand"], "start_s": 29.0, "end_s": 36.0, "remove": [], "rank": 0, "label": ""}],
                "overlay": {"pov_text": "", "skip_card": "", "callback_quote": "", "foreshadow": False}, "theme": "", "new_caption": False, "caption_hint": ""}

    monkeypatch.setattr("src.ai_edit.run_claude", fake_claude)
    monkeypatch.setattr("src.pov.generate_pov_captions", lambda *a, **k: GOOD_CAPTIONS)
    c.post(f"/clips/{cid}/ai-edit", data={"comment": "make it a POV"}, follow_redirects=False)
    row = get_clip(cid)
    assert "Moments of this stream" in seen["prompt"] and "Moment 3" in seen["prompt"] and "concept single" in seen["prompt"]
    assert row["status"] == "ready" and row["concept"] == "pov" and row["concept_source"] == "user"
    assert json.loads(row["overlay"])["pov_text"] == GOOD_CAPTIONS["text"]

    asked = {}
    monkeypatch.setattr("src.concept_build.pov_captions_for", lambda *a, **k: asked.update(hint=a[-1]) or
                        {"emotion": "fury", "options": ["me when school starts again", "x", "y"], "text": "me when school starts again"})
    monkeypatch.setattr("src.ai_edit.run_claude", lambda *a, **k: {
        "start_s": 29, "end_s": 36, "remove": [], "zooms": [], "title": "", "explanation": "New caption about school.", "concept": "pov",
        "segments": [{"candidate_id": env["cand"], "start_s": json.loads(get_clip(cid)["segments"])[0]["start_s"], "end_s": json.loads(get_clip(cid)["segments"])[0]["end_s"],
                      "remove": [], "rank": 0, "label": ""}],
        "overlay": {"pov_text": "", "skip_card": "", "callback_quote": "", "foreshadow": False}, "theme": "", "new_caption": True, "caption_hint": "more about school"})
    c.post(f"/clips/{cid}/ai-edit", data={"comment": "new caption, more about school"}, follow_redirects=False)
    assert asked["hint"] == "more about school" and json.loads(get_clip(cid)["overlay"])["pov_text"] == "me when school starts again"


def test_ask_the_editor_rejects_a_concept_with_the_wrong_number_of_segments(env, monkeypatch):
    monkeypatch.setattr("src.ai_edit.run_claude", lambda *a, **k: {
        "start_s": 27, "end_s": 36, "remove": [], "zooms": [], "title": "", "explanation": "x", "concept": "top3",
        "segments": [{"candidate_id": None, "start_s": 5, "end_s": 14, "remove": [], "rank": 0, "label": ""}] * 2,
        "overlay": {"pov_text": "", "skip_card": "", "callback_quote": "", "foreshadow": False}, "theme": "", "new_caption": False, "caption_hint": ""})
    env["c"].post(f"/clips/{env['clip']}/ai-edit", data={"comment": "make it a top 3"}, follow_redirects=False)
    row = get_clip(env["clip"])
    assert row["status"] == "ready" and (row["concept"] or "single") == "single"
    assert "exactly 3" in env["c"].get(f"/clips/{env['clip']}").text


def test_sources_choose_which_concepts_the_pipeline_proposes(env):
    sid = create_source({"kind": "youtube", "external_id": "UC_concepts_test", "display_name": "Concept test"})
    try:
        c = env["c"]
        html = c.get(f"/sources/{sid}").text
        assert 'name="auto_concepts" value="top5"' in html and 'value="top5" ' in html
        top5_box = html.split('value="top5"')[1].split(">")[0]
        assert "checked" not in top5_box                                             # off by default
        c.post(f"/sources/{sid}/edit", data={"display_name": "Concept test", "auto_concepts": ["pov", "top5"]}, follow_redirects=False)
        assert get_json_column(sid, "auto_concepts", None) == ["single", "pov", "top5"]    # single is always on
    finally:
        from src.db import delete_source
        delete_source(sid)


def test_settings_pov_bank_adds_and_deletes_captions_by_hand(env):
    c = env["c"]
    before = len(load_bank())
    r = c.post("/settings/pov-bank/add", data={"text": "POV: your charger is at 1 percent", "emotion": "panic"}, follow_redirects=False)
    assert r.status_code == 303 and len(load_bank()) == before + 1
    assert "POV: your charger is at 1 percent" in c.get("/settings").text
    assert c.post("/settings/pov-bank/add", data={"text": "POV: your charger is at 1 percent", "emotion": "panic"}, follow_redirects=False).headers["location"].endswith("rejected#pov-captions")
    idx = [b["text"] for b in load_bank()].index("POV: your charger is at 1 percent")
    c.post(f"/settings/pov-bank/{idx}/delete", follow_redirects=False)
    assert len(load_bank()) == before


def test_review_grid_shows_a_concept_badge_and_the_pov_caption(env):
    create_or_update_clip(candidate_id=env["cand"], file_path=get_clip(env["clip"])["file_path"], thumb_path="", concept="pov",
                          overlay=json.dumps({"pov_text": "POV: you said one more round at midnight"}))
    html = env["c"].get("/").text
    assert ">POV<" in html and "POV: you said one more round at midnight" in html
