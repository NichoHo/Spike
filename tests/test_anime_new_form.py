"""
The New page's Stream/Anime choice: the form shows it on Paste URL and Upload only, an anime job carries validated
`anime` settings and none of the stream render presets, and bad anime fields are refused with a message.
"""

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import pytest
from starlette.testclient import TestClient

from src.db import get_connection, init_db
from src.web.app import app

URL = "https://www.youtube.com/watch?v=dQw4w9WgXcQ"


@pytest.fixture(scope="module")
def client():
    init_db()
    with TestClient(app) as c:
        yield c


def last_settings():
    with get_connection() as conn:
        return json.loads(conn.execute("SELECT settings FROM videos ORDER BY id DESC LIMIT 1").fetchone()[0] or "{}")


def test_choice_shows_on_url_and_upload_not_streamer(client):
    for tab, expected in (("url", True), ("upload", True), ("streamer", False)):
        html = client.get(f"/new?tab={tab}").text
        assert ('id="kind-anime"' in html) is expected, tab
        assert ('id="anime-fields"' in html) is expected, tab


def test_anime_job_carries_validated_settings_and_skips_stream_presets(client):
    r = client.post("/new/submit", follow_redirects=False, data={
        "tab": "url", "url": URL, "kind": "anime", "anime_audio": "dub", "anime_id": "813", "anime_episode": "12",
        "anime_hardsubbed": "on", "anime_youtube_url": URL, "anime_youtube_offset": "2.5",
        "layout": "auto", "music": "on", "cut_pauses": "auto"})   # stream presets the page would have hidden
    assert r.status_code == 303
    s = last_settings()
    assert s["anime"] == {"audio_kind": "dub", "anilist_id": 813, "episode": 12, "hardsubbed": True, "title_match": False,
                          "youtube_url": URL, "youtube_offset_s": 2.5}
    assert "layout" not in s and "music" not in s and "cut_pauses" not in s


def test_stream_job_has_no_anime_settings(client):
    # a new URL: re-posting a known one returns the existing job, whose settings stay as they were
    client.post("/new/submit", follow_redirects=False,
                data={"tab": "url", "url": "https://www.youtube.com/watch?v=aaaaaaaaaaa", "kind": "stream", "anime_audio": "dub"})
    assert "anime" not in last_settings()


@pytest.mark.parametrize("field,value", [
    ("anime_id", "abc"), ("anime_episode", "-1"), ("anime_youtube_offset", "soon"),
    ("anime_youtube_url", "https://evil.example/watch?v=1"), ("anime_audio", "klingon"), ("kind", "movie"),
])
def test_bad_anime_fields_are_refused(client, field, value):
    data = {"tab": "url", "url": URL, "kind": "anime", "anime_audio": "sub", field: value}
    assert client.post("/new/submit", data=data, follow_redirects=False).status_code == 400

