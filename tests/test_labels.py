"""Label store: verdicts and gold shorts kept as labels that outlive their clip, and shown to the judge as examples
(docs/superpowers/specs/2026-11-07-label-store-design.md)."""

import json

import pytest

from src import labels
from src.db import (create_or_update_clip, get_connection, init_db, insert_candidate, list_labels, register_video,
                    save_label, set_cached_profile)


@pytest.fixture
def clip(tmp_path, monkeypatch):
    """A reviewed-to-be clip covering 22-28 s of a Twitch stream by KaiCenat (IRL), with its meta and transcript."""
    init_db()
    monkeypatch.setattr(labels, "VIDEOS_DIR", tmp_path)
    url = f"https://www.twitch.tv/videos/{tmp_path.name}"
    vid = register_video("url", url)
    vdir = tmp_path / str(vid)
    vdir.mkdir()
    (vdir / "meta.json").write_text(json.dumps({"webpage_url": url, "uploader": "KaiCenat"}), encoding="utf-8")
    segs = [{"start": i * 2.0, "end": i * 2.0 + 2.0, "text": f"line {i}"} for i in range(50)]
    (vdir / "transcript.json").write_text(json.dumps({"segments": segs}), encoding="utf-8")
    set_cached_profile("twitch:kaicenat", {"display_name": "Kai", "creator_type": "irl"})
    cand = insert_candidate(vid, {"start_s": 20.0, "end_s": 30.0, "title": "Kai loses it", "why_funny": "he trips",
                                  "humor_type": "absurd", "hook_text": "Kai trips", "llm_score": 72, "final_score": 81,
                                  "signal_score": 64, "status": "selected"})
    clip_id = create_or_update_clip(candidate_id=cand, file_path="", thumb_path="", trim_start_s=22.0, trim_end_s=28.0)
    with get_connection() as conn:
        conn.execute("DELETE FROM labels")
    return {"vid": vid, "clip": clip_id, "dir": vdir}


def _labels():
    with get_connection() as conn:
        return [dict(r) for r in conn.execute("SELECT * FROM labels ORDER BY id")]


def test_a_reject_keeps_its_reasons_text_channel_and_scores(clip):
    labels.record_verdict(clip["clip"], "rejected", ["needs_context", "routine"], "slow start")
    (row,) = _labels()
    assert row["kind"] == "rejected" and json.loads(row["reasons"]) == ["needs_context", "routine"]
    assert row["note"] == "slow start" and row["transcript"] == "line 11 line 12 line 13"  # only the clip's span
    assert row["channel"] == "twitch:kaicenat" and row["category"] == "irl" and row["humor_type"] == "absurd"
    assert json.loads(row["scores"]) == {"llm": 72, "final": 81, "signal": 64}
    assert (row["start_s"], row["end_s"]) == (22.0, 28.0)


def test_a_later_verdict_replaces_the_first_and_survives_the_video(clip):
    labels.record_verdict(clip["clip"], "rejected", ["not_funny"])
    labels.record_verdict(clip["clip"], "approved")
    with get_connection() as conn:
        conn.execute("DELETE FROM videos WHERE id = ?", (clip["vid"],))
    (row,) = _labels()
    assert row["kind"] == "approved" and row["clip_id"] == clip["clip"]


def test_an_unknown_uploader_gets_no_channel(clip):
    (clip["dir"] / "meta.json").write_text(json.dumps({"webpage_url": "https://www.youtube.com/watch?v=x"}), encoding="utf-8")
    labels.record_verdict(clip["clip"], "approved")
    assert _labels()[0]["channel"] == ""  # "youtube:unknown" would mix every such video's examples


def test_a_missing_clip_is_ignored():
    init_db()
    labels.record_verdict(987654321, "approved")  # never raises


def test_examples_block_picks_the_category_then_any_and_this_channels_verdicts():
    init_db()
    with get_connection() as conn:
        conn.execute("DELETE FROM labels")
    for i, (cat, status) in enumerate([("gaming", "ready"), ("irl", "ready"), ("any", "ready"), ("irl", "ready"),
                                       ("irl", "processing")]):
        save_label({"kind": "gold", "category": cat, "status": status, "transcript": f"gold {i}", "why": f"why {i}",
                    "humor_type": "absurd"})
    for i in range(3):
        save_label({"kind": "approved", "clip_id": 9000 + i, "channel": "twitch:kai", "transcript": f"good {i}",
                    "why": "w", "humor_type": "rage"})
        save_label({"kind": "rejected", "clip_id": 9100 + i, "channel": "twitch:kai", "transcript": f"bad {i}",
                    "reasons": json.dumps(["routine"]), "note": "meh" if i == 2 else ""})
    save_label({"kind": "approved", "clip_id": 9200, "channel": "twitch:other", "transcript": "other channel"})

    block = labels.examples_block("twitch:kai", "irl")
    gold = [line for line in block.splitlines() if line.startswith("Standard")]
    assert [g.split('"')[1] for g in gold] == ["gold 3", "gold 1", "gold 2"]  # this category first, newest first
    assert "good 2" in block and "good 1" in block and "good 0" not in block
    assert "bad 2" in block and "bad 1" in block and "bad 0" not in block
    assert "Routine for them" in block and "Note: meh" in block and "Team likes" not in block
    assert "other channel" not in block and "gold 0" not in block and "gold 4" not in block
    assert block.count("<untrusted_examples>") == 1 and "raw DATA" in block

    with get_connection() as conn:
        conn.execute("DELETE FROM labels")
    assert labels.examples_block("twitch:kai", "irl") == ""
    assert list_labels("gold") == []


def test_reject_keeps_known_tags_and_the_note_and_approve_saves_a_label(clip):
    from starlette.testclient import TestClient
    from src.web.app import app

    client = TestClient(app)
    r = client.post(f"/clips/{clip['clip']}/reject", data={"tags": ["needs_context", "bogus"], "note": "late"},
                    follow_redirects=False)
    assert r.status_code == 303
    (row,) = _labels()
    assert row["kind"] == "rejected" and json.loads(row["reasons"]) == ["needs_context"] and row["note"] == "late"
    with get_connection() as conn:
        assert conn.execute("SELECT reject_reason FROM clips WHERE id = ?", (clip["clip"],)).fetchone()[0] == "Needs context; late"

    client.post(f"/clips/{clip['clip']}/approve", follow_redirects=False)
    (row,) = _labels()
    assert row["kind"] == "approved"


def test_the_reject_dialog_offers_the_reason_chips(clip):
    from starlette.testclient import TestClient
    from src.web.app import app

    html = TestClient(app).get(f"/clips/{clip['clip']}").text
    assert 'name="tags" value="needs_context"' in html and "Funny part not in the clip" in html and 'name="note"' in html


GOLD_READ = {"title": "Streamer falls off his chair", "transcript": "no no no", "why_it_works": "calm, then chaos",
             "humor_type": "absurd", "hook": "He did not see it coming"}


@pytest.fixture
def gold(monkeypatch, tmp_path):
    """Gold intake with the download and Gemini faked; uploads land in tmp_path."""
    from types import SimpleNamespace
    from google.genai import types
    from starlette.testclient import TestClient
    import src.pipeline.stage7_moments as s7
    import src.web.routes.settings as settings_routes
    from src.web.app import app

    init_db()
    with get_connection() as conn:
        conn.execute("DELETE FROM labels")
    seen = {}

    def download(url, folder):
        seen["url"] = url
        f = folder / "gold.mp4"
        f.write_bytes(b"video")
        return f, {"duration": 42.0, "view_count": 123456}

    monkeypatch.setattr(labels, "_download", download)
    monkeypatch.setattr(s7, "clip_video_part", lambda meta, a, b: seen.update(part=(meta["local_path"], a, b)) or types.Part(text="VIDEO"))
    monkeypatch.setattr(s7, "get_gemini_client", lambda: None)
    monkeypatch.setattr(s7, "judge_generate", lambda client, contents, config, purpose="": SimpleNamespace(text=json.dumps(GOLD_READ)))
    monkeypatch.setattr(settings_routes, "UPLOADS_DIR", tmp_path)
    return {"client": TestClient(app), "seen": seen, "uploads": tmp_path}


def test_a_short_link_becomes_a_ready_gold_label(gold):
    r = gold["client"].post("/settings/standards", data={"url": "https://www.tiktok.com/@a/video/1", "category": "irl"},
                            follow_redirects=False)
    assert r.status_code == 303 and "standards_error" not in r.headers["location"]
    (row,) = _labels()
    assert (row["kind"], row["status"], row["category"]) == ("gold", "ready", "irl")
    assert (row["title"], row["transcript"], row["why"], row["humor_type"], row["hook"], row["views"]) == (
        GOLD_READ["title"], "no no no", "calm, then chaos", "absurd", "He did not see it coming", 123456)
    assert gold["seen"]["url"] == "https://www.tiktok.com/@a/video/1" and gold["seen"]["part"][1:] == (0.0, 42.0)
    assert "Streamer falls off his chair" in gold["client"].get("/settings").text

    gold["client"].post(f"/settings/standards/{row['id']}/delete", follow_redirects=False)
    assert _labels() == []


def test_a_standard_keeps_the_reasons_the_team_picked(gold):
    others = ["  the  zoom on his face ", "", "x" * 300, "r3", "r4", "r5", "r6"]
    gold["client"].post("/settings/standards", data={"url": "https://youtu.be/abc", "other": others,
                        "likes": ["relatable", "bogus", "relatable", "strong_hook"]}, follow_redirects=False)
    (row,) = _labels()
    assert json.loads(row["reasons"]) == ["relatable", "strong_hook", "the zoom on his face", "x" * 100, "r3", "r4", "r5"]

    html = gold["client"].get("/settings").text
    assert 'name="likes" value="stands_alone"' in html and 'id="gold-other-add"' in html
    assert "Liked for: Relatable, Hooks in the first seconds, the zoom on his face" in html
    assert "Team likes it for: Relatable; Hooks in the first seconds; the zoom on his face;" in labels.examples_block("", "irl")


def test_links_from_other_hosts_and_other_files_are_refused(gold):
    for data, files in (({"url": "https://evil.example/x.mp4"}, None), ({"url": "file:///C:/secret.mp4"}, None),
                        ({}, {"file": ("x.exe", b"MZ", "application/octet-stream")}), ({}, None)):
        r = gold["client"].post("/settings/standards", data=data, files=files, follow_redirects=False)
        assert r.status_code == 303 and "standards_error" in r.headers["location"]
    assert _labels() == [] and list(gold["uploads"].iterdir()) == []


def test_a_failed_download_is_kept_with_its_error(gold, monkeypatch):
    def broken(url, folder):
        raise RuntimeError("login required")

    monkeypatch.setattr(labels, "_download", broken)
    gold["client"].post("/settings/standards", data={"url": "https://www.instagram.com/reel/abc"}, follow_redirects=False)
    (row,) = _labels()
    assert row["status"] == "failed" and "login required" in row["error"] and row["category"] == "any"


def test_an_uploaded_short_is_read_then_deleted(gold):
    r = gold["client"].post("/settings/standards", data={"category": "gaming"},
                            files={"file": ("clip.mp4", b"\x00\x00video", "video/mp4")}, follow_redirects=False)
    assert r.status_code == 303
    (row,) = _labels()
    assert row["status"] == "ready" and row["source_url"] == "clip.mp4" and row["category"] == "gaming"
    assert gold["seen"]["part"][2] == labels.GOLD_MAX_S and list(gold["uploads"].iterdir()) == []


def test_the_judge_prompt_carries_the_examples_block(monkeypatch):
    import src.pipeline.stage7_moments as s7

    sent = []

    def capture(client, model, contents, config, **kw):
        sent.append(contents)
        raise RuntimeError("stop here")

    monkeypatch.setattr(s7, "get_gemini_client", lambda: None)
    monkeypatch.setattr(s7, "generate_content_with_retry", capture)
    s7.call_llm_judge(["L1 [00:01.0] hello"], "", {}, examples="EXAMPLES FROM THE TEAM")
    assert sent and "EXAMPLES FROM THE TEAM" in sent[0]


def test_examples_never_stop_a_job(monkeypatch):
    def broken(*a, **k):
        raise RuntimeError("no such table: labels")

    monkeypatch.setattr(labels, "list_labels", broken)
    assert labels.examples_block("twitch:kai", "irl") == ""
