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


# ---- From anime tab ----------------------------------------------------------------------------------------------

def last_video():
    with get_connection() as conn:
        row = conn.execute("SELECT title, settings FROM videos ORDER BY id DESC LIMIT 1").fetchone()
    return row[0], json.loads(row[1] or "{}")


def test_anime_tab_has_picker_upload_and_no_stream_presets(client):
    html = client.get("/new?tab=anime").text
    assert 'id="field-anime-search"' in html and 'id="anime-shelf"' in html
    assert 'name="anime_source" value="file"' in html and 'id="field-file"' in html   # the user uploads the episode
    assert 'class="btn btn--primary btn--lg" disabled' not in html
    assert 'id="kind-anime"' not in html                       # the tab itself says it is anime
    assert 'id="render-presets" class="job-options" disabled hidden' in html


def test_search_and_seasons_endpoints(client, monkeypatch):
    from src import anilist
    seen = {}
    monkeypatch.setattr(anilist, "search", lambda q: seen.setdefault("q", q) and [{"id": 7, "title": "Show", "format": "TV", "episodes": 12, "year": 2020}])
    monkeypatch.setattr(anilist, "seasons", lambda i: [{"id": i, "title": "Show", "format": "TV", "episodes": 12, "year": 2020}])
    assert client.get("/new/anime/search", params={"q": "show"}).json()["results"][0]["id"] == 7
    assert client.get("/new/anime/seasons", params={"id": 7}).json()["seasons"][0]["episodes"] == 12
    assert client.get("/new/anime/seasons", params={"id": 0}).status_code == 400
    assert client.get("/new/anime/seasons", params={"id": "x"}).status_code == 422
    monkeypatch.setattr(anilist, "shelf", lambda k: [{"id": 9, "title": k, "aired": 4}])
    assert client.get("/new/anime/shelf", params={"kind": "popular"}).json()["results"][0]["title"] == "popular"
    assert client.get("/new/anime/shelf").json()["results"][0]["title"] == "trending"
    assert client.get("/new/anime/shelf", params={"kind": "random"}).status_code == 400

    from src import episode_scores
    monkeypatch.setattr(episode_scores, "episodes", lambda m: [{"n": 1, "score": 4.5, "mal": m}])
    assert client.get("/new/anime/episodes", params={"mal": 51009}).json()["episodes"][0]["mal"] == 51009
    assert client.get("/new/anime/episodes", params={"mal": 0}).status_code == 400

    def no_source(m):
        raise OSError("both sources down")
    monkeypatch.setattr(episode_scores, "episodes", no_source)
    assert client.get("/new/anime/episodes", params={"mal": 5}).status_code == 502

    def down(*a):
        raise OSError("offline")
    monkeypatch.setattr(anilist, "search", down)
    r = client.get("/new/anime/search", params={"q": "show"})
    assert r.status_code == 502 and "AniList" in r.json()["detail"]


def test_anime_tab_submit_by_link_stores_show_episode_and_title(client):
    r = client.post("/new/submit", follow_redirects=False, data={
        "tab": "anime", "anime_source": "url", "url": "https://www.youtube.com/watch?v=bbbbbbbbbbb",
        "anime_id": "145064", "anime_episode": "5", "anime_audio": "sub",
        "anime_label": "JUJUTSU KAISEN Season 2 episode 5\n\x00<b>x</b>"})
    assert r.status_code == 303
    title, s = last_video()
    assert s["anime"]["anilist_id"] == 145064 and s["anime"]["episode"] == 5 and s["anime"]["audio_kind"] == "sub"
    assert title == "JUJUTSU KAISEN Season 2 episode 5 <b>x</b>"       # one line, no control characters (the page escapes the rest)
    assert "layout" not in s


@pytest.mark.parametrize("data", [
    {"anime_id": "", "anime_episode": "3"},                              # no season chosen
    {"anime_id": "145064", "anime_episode": ""},                         # no episode
    {"anime_id": "145064", "anime_episode": "3", "anime_source": "ftp"},
    {"anime_id": "145064", "anime_episode": "-3"},
    {"anime_id": "abc", "anime_episode": "3"},
])
def test_anime_tab_refuses_incomplete_picks(client, data):
    body = {"tab": "anime", "anime_source": "url", "url": "https://www.youtube.com/watch?v=ccccccccccc", **data}
    assert client.post("/new/submit", data=body, follow_redirects=False).status_code == 400


def test_anime_tab_is_in_the_tab_bar(client):
    for tab in ("streamer", "url", "upload", "anime"):
        assert 'href="/new?tab=anime"' in client.get(f"/new?tab={tab}").text, tab
