"""Re-render applies every setting from the clip page, face track never falls back to the whole wide frame,
and a clip being re-rendered stays on the Review page greyed out with a spinner."""

import json
import re
import shutil
import subprocess
from pathlib import Path

import pytest
from starlette.testclient import TestClient

from src.db import (create_or_update_clip, get_clip, get_clip_with_details, get_connection, init_db, insert_candidate,
                    register_video, set_clip_render_state)
from src.web.app import app


def test_face_track_without_a_face_crops_tall_not_the_whole_frame(monkeypatch):
    import src.pipeline.stage9a_face_track as ft
    from src.pipeline.stage9c_render import _layout_filters
    monkeypatch.setattr(ft, "_detect_faces_mediapipe", lambda *a, **k: [])
    keyframes, _ = ft.track_faces(Path("none.mp4"), 10.0, 1920, 1080)
    assert keyframes[0]["crop_h_px"] == 1080 and round(keyframes[0]["crop_w_px"]) == 608  # 9:16, not 1920 wide
    graph = _layout_filters("face_track", "v", "out", 1920, 1080, [{"t_s": 0, "cx_px": 960, "cy_px": 540}], "sc.txt", None)
    assert "crop@ft=607:1080:" in graph[0]  # a keyframe without a crop size still gets the tall crop


@pytest.fixture()
def env(tmp_path, monkeypatch):
    init_db()
    monkeypatch.chdir(Path(__file__).resolve().parent.parent)
    vroot = Path(__file__).resolve().parent.parent / "data" / f"_test_videos_{tmp_path.name}"   # never the real data/videos
    shutil.rmtree(vroot, ignore_errors=True)  # left by a run that crashed before its teardown
    vroot.mkdir(parents=True)
    for mod in ("src.config", "src.web.routes.clips", "src.web.routes.review"):
        monkeypatch.setattr(f"{mod}.VIDEOS_DIR", vroot, raising=False)
    vid = register_video("url", f"https://www.youtube.com/watch?v=rerender000&{tmp_path.name}", title="Rerender stream")
    vdir = vroot / str(vid)
    (vdir / "sections").mkdir(parents=True)
    (vdir / "renders").mkdir()
    words = [{"word": f" w{i}", "start": 22.0 + i * 0.5, "end": 22.0 + i * 0.5 + 0.4} for i in range(36)]
    (vdir / "meta.json").write_text(json.dumps({"uploader": "Speed", "duration": 60}))
    (vdir / "transcript.json").write_text(json.dumps({"segments": [{"start": 22, "end": 40, "text": "x", "words": words}]}))
    cand = insert_candidate(vid, dict(origin="llm_chunk", punchline="p", hook_text="old hook", post_caption="c", mood="laugh",
                                      humor_type="rage", status="selected", start_s=27.0, end_s=36.0, llm_score=90, final_score=90,
                                      title="Rerender me", payoff_t=31.0))
    sec = vdir / "sections" / f"section_{cand}.mp4"
    subprocess.run(["ffmpeg", "-y", "-hide_banner", "-loglevel", "error", "-f", "lavfi", "-i", "testsrc=size=1280x720:rate=30:duration=19",
                    "-f", "lavfi", "-i", "sine=frequency=440:duration=19", "-c:v", "libx264", "-preset", "ultrafast", "-c:a", "aac",
                    "-shortest", str(sec)], check=True)
    sec.with_suffix(".json").write_text(json.dumps({"start_s": 22.0}))
    clip_file = vdir / "renders" / f"clip_{cand}.mp4"
    clip_file.write_bytes(sec.read_bytes())
    thumb = vdir / "renders" / f"clip_{cand}_thumb.jpg"
    thumb.write_bytes(b"\xff\xd8\xff\xd9")
    clip_id = create_or_update_clip(candidate_id=cand, file_path=str(clip_file), thumb_path=str(thumb), layout="letterbox",
                                    letterbox_style="title", caption_style="bold_pop", trim_start_s=27.0, trim_end_s=36.0,
                                    zooms="[]", cuts="[]")
    yield {"c": TestClient(app), "clip": clip_id, "cand": cand}
    with get_connection() as conn:  # keep the shared test DB's review queue clean for other tests
        conn.execute("DELETE FROM clips WHERE id = ?", (clip_id,))
    shutil.rmtree(vroot, ignore_errors=True)


def test_rerender_applies_every_setting(env, monkeypatch):
    import src.pipeline.stage9a_face_track as ft
    import src.pipeline.stage9c_render as r9
    # The test section is a colour chart; give it a face so Face track is kept (see the no-face test below)
    monkeypatch.setattr(ft, "_detect_faces_mediapipe", lambda path, dur, *a, **k: [(0.4, 0.3, 0.2, 0.3)] * int(dur * ft.FACE_DETECT_FPS))
    monkeypatch.setattr(ft, "_multi_face_share", lambda *a: 0.0)
    used = {}
    real_track = r9.track_faces
    monkeypatch.setattr(r9, "track_faces", lambda *a, **k: used.setdefault("faces", real_track(*a, **k)))
    res = env["c"].post(f"/clips/{env['clip']}/rerender", data={
        "start_s": "28", "end_s": "35", "layout": "face_track", "caption_style": "karaoke", "hook_text": "new hook",
        "show_hook": "1", "silence_trim": "1", "silence_trim_s": "2.0", "layout_changes": "[]",
        "zooms": json.dumps([{"t": 30.0, "scale": 1.3, "hold_s": 1.0}]), "cuts": json.dumps([[32.0, 33.0]]),
    }, follow_redirects=False)
    assert res.status_code == 303
    clip = get_clip(env["clip"])
    assert clip["status"] == "ready" and clip["version"] == 2
    assert "faces" in used  # the new render really used face track
    assert (clip["layout"], clip["caption_style"], clip["letterbox_style"]) == ("face_track", "karaoke", "blur")
    assert (clip["trim_start_s"], clip["trim_end_s"], clip["show_hook"], clip["silence_trim"], clip["silence_trim_s"]) == (28.0, 35.0, 1, 1, 2.0)
    assert json.loads(clip["cuts"]) == [[32.0, 33.0]] and json.loads(clip["zooms"])[0]["scale"] == 1.3
    assert Path(clip["file_path"]).name.endswith("_v2.mp4") and Path(clip["file_path"]).exists()

    # The page and the media point at the new version, and the browser is told to revalidate
    html = env["c"].get(f"/clips/{env['clip']}").text
    assert f"/media/clip/{env['clip']}/stream?v=2" in html
    assert env["c"].get(f"/media/clip/{env['clip']}/stream").headers["cache-control"] == "no-cache"


def test_face_track_with_no_face_falls_back_to_the_previous_layout(env):
    res = env["c"].post(f"/clips/{env['clip']}/rerender", data={
        "start_s": "28", "end_s": "35", "layout": "face_track", "caption_style": "bold_pop", "layout_changes": "[]",
    }, follow_redirects=False)
    assert res.status_code == 303
    clip = get_clip(env["clip"])
    assert clip["layout"] == "letterbox" and clip["no_face"] == 1   # the colour chart has no face
    assert re.search(r'value="face_track"[^>]*disabled', env["c"].get(f"/clips/{env['clip']}").text)


def test_clip_page_locks_while_rendering_and_a_locked_old_file_does_not_abort_the_job(env, monkeypatch):
    # An edit made while rendering used to block the reload forever, so the player kept the old version
    set_clip_render_state(env["clip"], "rendering")
    html = env["c"].get(f"/clips/{env['clip']}").text
    assert '<fieldset class="card__body edit-groups" disabled>' in html and "location.reload()" in html
    set_clip_render_state(env["clip"], "ready")
    assert '<fieldset class="card__body edit-groups" disabled>' not in env["c"].get(f"/clips/{env['clip']}").text

    # Windows refuses to delete the old render while the player still streams it
    real_unlink = Path.unlink
    def locked(self, *a, **k):
        if self.name == f"clip_{env['cand']}.mp4":
            raise PermissionError(32, "The process cannot access the file because it is being used by another process")
        return real_unlink(self, *a, **k)
    monkeypatch.setattr(Path, "unlink", locked)
    res = env["c"].post(f"/clips/{env['clip']}/rerender", data={
        "start_s": "27", "end_s": "36", "layout": "letterbox", "caption_style": "bold_pop", "hook_text": "new hook", "layout_changes": "[]",
    }, follow_redirects=False)
    assert res.status_code == 303
    clip = get_clip_with_details(env["clip"])
    assert clip["version"] == 2 and clip["cand_hook"] == "new hook"  # saved after the failed delete
    assert any(e["clip_id"] == env["clip"] and e["ok"] for e in env["c"].get("/api/render-events?after=0").json()["events"])


def test_review_page_keeps_a_rerendering_clip_with_a_spinner(env):
    set_clip_render_state(env["clip"], "rendering")
    html = env["c"].get("/").text
    card = re.search(r'<article class="clip-card clip-card--rendering".*?</article>', html, re.S)
    assert card, "the rendering clip vanished from Review"
    assert "clip-card__spinner" in card.group(0) and f'href="/clips/{env["clip"]}"' not in card.group(0)
    assert re.search(r'data-render-busy[^>]*>', html) and not re.search(r'data-render-busy[^>]*hidden', html)
    assert env["c"].get("/api/render-events").json()["rendering"] >= 1

    set_clip_render_state(env["clip"], "ready")
    html = env["c"].get("/").text
    assert "clip-card--rendering" not in html and f'href="/clips/{env["clip"]}"' in html
