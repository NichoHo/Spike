"""
Automation checks: the watcher skips a still-recording VOD and never re-queues a failed one.
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import src.db as db
import src.watcher as watcher


def test_watcher_skips_live_vod_and_failed_jobs(tmp_path, monkeypatch):
    monkeypatch.setattr(db, "DB_PATH", tmp_path / "test.db")
    db.init_db()
    with db.get_connection() as conn:
        conn.execute("INSERT INTO sources (kind, external_id, display_name, auto_process) VALUES ('twitch', 'chan', 'Chan', 1)")

    vods = [{"id": f"v{n}", "url": f"https://www.twitch.tv/videos/{n}", "title": f"VOD {n}"} for n in (3, 2, 1)]
    monkeypatch.setattr(watcher, "fetch_twitch_latest_vods", lambda name: vods)

    # Live: newest VOD (v3) is still recording, so only v2 and v1 are queued.
    monkeypatch.setattr(watcher, "twitch_channel_is_live", lambda name: True)
    assert watcher.check_and_queue_sources() == 2

    # v2 fails. Stream ends. Next cycle queues v3 only, and leaves v2 failed.
    with db.get_connection() as conn:
        conn.execute("UPDATE videos SET status = 'failed' WHERE external_id = 'v2'")
    monkeypatch.setattr(watcher, "twitch_channel_is_live", lambda name: False)
    assert watcher.check_and_queue_sources() == 1

    with db.get_connection() as conn:
        rows = dict(conn.execute("SELECT external_id, status FROM videos").fetchall())
        source_ids = {r[0] for r in conn.execute("SELECT source_id FROM videos")}
    assert rows == {"v1": "queued", "v2": "failed", "v3": "queued"}
    assert source_ids == {1}


def test_twitch_vod_id_drops_flat_listing_prefix():
    # yt-dlp 2026.08 flat listing: id 'v2899740602', but /videos/v2899740602 is not a valid VOD URL
    assert watcher.twitch_vod_id("v2899740602") == "2899740602"
    assert watcher.twitch_vod_id("2899740602") == "2899740602"
    assert watcher.twitch_vod_id("vod") == "vod"
