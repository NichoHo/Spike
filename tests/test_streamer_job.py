from src import watcher


def test_vod_url_for_accepts_urls_and_bare_ids():
    assert watcher.vod_url_for("twitch", "2899740602") == "https://www.twitch.tv/videos/2899740602"
    assert watcher.vod_url_for("twitch", "v2899740602") == "https://www.twitch.tv/videos/2899740602"
    assert watcher.vod_url_for("youtube", "abc123DEF45") == "https://www.youtube.com/watch?v=abc123DEF45"
    assert watcher.vod_url_for("twitch", " https://www.twitch.tv/videos/1 ") == "https://www.twitch.tv/videos/1"


def test_latest_finished_vod_skips_the_live_twitch_archive(monkeypatch):
    vods = [{"id": "2", "url": "u2", "title": "live now"}, {"id": "1", "url": "u1", "title": "done"}]
    monkeypatch.setattr(watcher, "fetch_twitch_latest_vods", lambda c, n=5: vods)
    monkeypatch.setattr(watcher, "twitch_channel_is_live", lambda c: True)
    assert watcher.latest_finished_vod("twitch", "x")["id"] == "1"
    monkeypatch.setattr(watcher, "twitch_channel_is_live", lambda c: False)
    assert watcher.latest_finished_vod("twitch", "x")["id"] == "2"


def test_latest_finished_vod_youtube_skips_unfinished(monkeypatch):
    items = [{"id": "a", "url": "ua", "title": ""}, {"id": "b", "url": "ub", "title": ""}]
    monkeypatch.setattr(watcher, "fetch_youtube_channel_rss", lambda c: items)
    monkeypatch.setattr(watcher, "youtube_video_is_finished", lambda u: u == "ub")
    assert watcher.latest_finished_vod("youtube", "x")["id"] == "b"
    monkeypatch.setattr(watcher, "youtube_video_is_finished", lambda u: False)
    assert watcher.latest_finished_vod("youtube", "x") is None


def test_latest_finished_vod_reuses_a_given_listing(monkeypatch):
    monkeypatch.setattr(watcher, "fetch_youtube_channel_rss", lambda c: 1 / 0)  # must not refetch
    monkeypatch.setattr(watcher, "youtube_video_is_finished", lambda u: u == "ub")
    items = [{"id": "a", "url": "ua", "title": ""}, {"id": "b", "url": "ub", "title": ""}]
    assert watcher.latest_finished_vod("youtube", "x", items)["id"] == "b"


def test_resubmitting_a_cancelled_job_queues_it_again():
    from src.db import cancel_job, get_connection, register_video
    vid = register_video(origin="url", url_or_path="https://www.twitch.tv/videos/999001", external_id="999001")
    assert cancel_job(vid)
    assert register_video(origin="url", url_or_path="https://www.twitch.tv/videos/999001", external_id="999001") == vid
    with get_connection() as conn:
        row = conn.execute("SELECT status, stage, error FROM videos WHERE id = ?", (vid,)).fetchone()
        conn.execute("DELETE FROM videos WHERE id = ?", (vid,))
    assert (row[0], row[1], row[2]) == ("queued", "fetch_meta", None)


def test_youtube_falls_back_to_the_uploads_playlist_when_rss_fails(monkeypatch):
    import urllib.request
    monkeypatch.setattr(urllib.request, "urlopen", lambda *a, **k: (_ for _ in ()).throw(OSError("404")))
    monkeypatch.setattr(watcher, "fetch_youtube_uploads", lambda cid, n=10: [{"id": "v", "url": "u", "title": "t"}])
    assert watcher.fetch_youtube_channel_rss("UCabc")[0]["id"] == "v"


def test_uploads_playlist_only_for_uc_channel_ids():
    assert watcher.fetch_youtube_uploads("not-a-channel-id") == []


def test_continue_keeps_the_stage_and_retry_starts_over(tmp_path, monkeypatch):
    from starlette.testclient import TestClient
    from src.db import get_job, insert_candidate, register_video, update_video_stage, get_connection
    from src.web.app import app
    monkeypatch.setattr("src.web.routes.jobs.VIDEOS_DIR", tmp_path)
    vid = register_video("url", "https://youtube.com/watch?v=cont1nue0001", external_id="cont1nue0001")
    (tmp_path / str(vid)).mkdir()
    (tmp_path / str(vid) / "transcript.json").write_text("{}")
    insert_candidate(vid, {"peak_t": 1.0, "start_s": 0.0, "end_s": 5.0, "origin": "signal"})
    update_video_stage(vid, "moments", status="failed", error="boom")
    c = TestClient(app)
    assert c.post(f"/jobs/{vid}/continue", follow_redirects=False).status_code == 303
    j = get_job(vid)
    assert (j["status"], j["stage"], j["error"]) == ("queued", None, None)  # the table shows "queued", not "failed"
    assert (tmp_path / str(vid) / "transcript.json").exists()  # nothing deleted

    update_video_stage(vid, "moments", status="failed", error="boom")
    assert f"/jobs/{vid}/continue" in c.get("/jobs/table").text
    assert f"/jobs/{vid}/retry" in c.get("/jobs/table").text  # Continue was tried and failed again

    update_video_stage(vid, "moments", status="failed", error="boom")
    assert c.post(f"/jobs/{vid}/retry", follow_redirects=False).status_code == 303
    j = get_job(vid)
    assert (j["status"], j["stage"]) == ("queued", "fetch_meta")
    assert not (tmp_path / str(vid)).exists()
    with get_connection() as conn:
        assert conn.execute("SELECT COUNT(*) FROM candidates WHERE video_id = ?", (vid,)).fetchone()[0] == 0
        conn.execute("DELETE FROM videos WHERE id = ?", (vid,))
