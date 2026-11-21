"""Clip analytics, Step 1 (docs/superpowers/specs/2026-11-21-clip-analytics-design.md). Platform calls are faked."""

import json
import urllib.parse
from datetime import date, datetime, timedelta, timezone

import pytest

from src import analytics
from src.db import (create_or_update_clip, create_post, get_connection, init_db, insert_candidate, register_video,
                    save_connected_account)

TODAY = date(2026, 11, 21)


def _iso(days_ago: int) -> str:
    return (datetime(2026, 11, 21, 12, tzinfo=timezone.utc) - timedelta(days=days_ago)).isoformat().replace("+00:00", "Z")


@pytest.fixture
def acct():
    init_db()
    with get_connection() as conn:
        for t in ("published_stats", "published", "posts", "clips", "candidates", "accounts"):
            conn.execute(f"DELETE FROM {t}")
    far = (datetime.now(timezone.utc) + timedelta(days=30)).isoformat()
    return save_connected_account("youtube", "UC1", "Chan", "tok", "ref", far)


def _clip(title, hook="hook", voice="relatable", score=82):
    vid = register_video("url", f"https://example.com/{title}")
    cand = insert_candidate(vid, {"start_s": 1.0, "end_s": 9.0, "title": title, "hook_text": hook, "final_score": score,
                                  "llm_score": 70, "signal_score": 60, "status": "selected",
                                  "hook_options": {voice: hook, "plain": "other"}})
    clip = create_or_update_clip(candidate_id=cand, file_path="", thumb_path="", trim_start_s=1.0, trim_end_s=9.0, frame="medium")
    with get_connection() as conn:
        conn.execute("UPDATE clips SET created_at = '2020-01-01T00:00:00+00:00' WHERE id = ?", (clip,))
    return cand, clip


def _published(acct_id, vid, days_ago, title="t", duration=30):
    with get_connection() as conn:
        return conn.execute("INSERT INTO published (account_id, platform_video_id, title, published_at, duration_s) VALUES (?, ?, ?, ?, ?)",
                            (acct_id, vid, title, _iso(days_ago), duration)).lastrowid


def _row(pid):
    with get_connection() as conn:
        return dict(conn.execute("SELECT * FROM published WHERE id = ?", (pid,)).fetchone())


class FakeYouTube:
    """Answers the calls analytics makes. shorts: [(video_id, title, seconds, days_ago)]."""

    def __init__(self, shorts, views=100):
        self.shorts, self.views, self.calls = shorts, views, []

    def __call__(self, method, url, token=None, **kw):
        self.calls.append(url)
        parts = urllib.parse.urlsplit(url)
        q = {k: v[0] for k, v in urllib.parse.parse_qs(parts.query).items()}
        if "/channels" in parts.path:
            return 200, {}, {"items": [{"contentDetails": {"relatedPlaylists": {"uploads": "UU1"}}}]}
        if "/playlistItems" in parts.path:
            return 200, {}, {"items": [{"contentDetails": {"videoId": s[0]}} for s in self.shorts]}
        if parts.path.endswith("/videos"):
            return 200, {}, {"items": [{"id": s[0], "snippet": {"title": s[1], "publishedAt": _iso(s[3])},
                                        "contentDetails": {"duration": f"PT{s[2]}S"}} for s in self.shorts if s[0] in q["id"].split(",")]}
        if q["dimensions"] == "elapsedVideoTimeRatio":
            return 200, {}, {"rows": [[(i + 1) / 100, 1.0 - i * 0.004 - (0.3 if i == 40 else 0)] for i in range(100)]}
        vids = q["filters"].removeprefix("video==").split(",")
        start = date.fromisoformat(q["startDate"])
        rows = []
        for v in vids:
            for d in range((date.today() - start).days + 1):
                rows.append([(start + timedelta(d)).isoformat(), v, self.views, self.views // 2, 3, 1, 2, 1, 55.0, 12.0])
        return 200, {}, {"rows": rows}


def test_a_spike_upload_creates_a_linked_row_with_the_facts(acct):
    cand, clip = _clip("Goku roars")
    post = create_post(clip, acct)
    analytics.record_upload(acct, post, cand, clip, "vid1", "https://youtube.com/shorts/vid1", "Goku roars")
    with get_connection() as conn:
        row = dict(conn.execute("SELECT * FROM published WHERE platform_video_id = 'vid1'").fetchone())
    assert row["post_id"] == post
    facts = json.loads(row["facts"])
    assert row["link_state"] == "auto" and row["candidate_id"] == cand
    assert facts["hook_voice"] == "relatable" and facts["frame"] == "medium" and facts["final_score"] == 82


def test_import_links_one_match_and_leaves_two_unlinked(acct, monkeypatch):
    _clip("Goku  Roars")  # case and spacing are ignored
    _clip("Twin title")
    _clip("twin title")
    fake = FakeYouTube([("a", "goku roars", 30, 10), ("b", "Twin Title", 30, 10), ("c", "Something else", 30, 10), ("d", "Long one", 400, 10)])
    monkeypatch.setattr(analytics, "_http", fake)
    monkeypatch.setattr(analytics, "pull_stats", lambda *a: None)
    analytics.sync_account(__import__("src.db", fromlist=["get_account"]).get_account(acct))
    with get_connection() as conn:
        states = {r["platform_video_id"]: r["link_state"] for r in conn.execute("SELECT * FROM published")}
    assert states == {"a": "auto", "b": "none", "c": "none"}  # "d" is over 180 s: not a Short


def test_a_pick_confirms_the_link(acct):
    cand, _ = _clip("Pick me")
    pid = _published(acct, "x", 10)
    assert analytics.link(pid, cand)
    assert _row(pid)["link_state"] == "confirmed" and json.loads(_row(pid)["facts"])["title"] == "Pick me"


def test_stats_become_day_rows_and_a_second_run_does_not_duplicate_them(acct, monkeypatch):
    monkeypatch.setattr(analytics, "date", type("D", (date,), {"today": staticmethod(lambda: TODAY)}))
    fake = FakeYouTube([("a", "One", 30, 3)])
    monkeypatch.setattr(analytics, "_http", fake)
    from src.db import get_account
    analytics.sync_account(get_account(acct))
    analytics.sync_account(get_account(acct))
    with get_connection() as conn:
        days = [r["day"] for r in conn.execute("SELECT day FROM published_stats ORDER BY day")]
    assert days == ["2026-11-18", "2026-11-19", "2026-11-20", "2026-11-21"]
    assert fake.calls and not [u for u in fake.calls if "elapsedVideoTimeRatio" in u]  # 3 days old: no retention yet


def test_views_7d_sums_days_0_to_6_and_is_blank_until_then():
    days = {f"2026-11-{d:02d}": {"views": 10} for d in range(10, 21)}  # 11 days of 10 views
    assert analytics.views_n(days, "2026-11-10T08:00:00Z", 7, TODAY) == 70
    assert analytics.views_n(days, "2026-11-18T08:00:00Z", 7, TODAY) is None


def test_multiple_needs_five_other_shorts(acct):
    ids = [_published(acct, f"v{i}", 20 + i * 5) for i in range(6)]  # 20, 25, ... 45 days old
    old, new = ids[1:], ids[0]
    with get_connection() as conn:
        for pid in ids:
            for d in range(7):
                day = (datetime.fromisoformat(_row(pid)["published_at"].replace("Z", "+00:00")) + timedelta(d)).date().isoformat()
                conn.execute("INSERT INTO published_stats (published_id, day, views, engaged_views) VALUES (?, ?, ?, 5)",
                             (pid, day, 100 if pid != new else 300))
    rows = {r["id"]: r for r in analytics.shorts_table(TODAY)}
    assert rows[new]["multiple"] == pytest.approx(3.0)  # 2100 against the median 700
    assert rows[old[0]]["multiple"] is None  # fewer than 5 earlier Shorts
    assert rows[new]["stayed"] == pytest.approx(5 / 300)


def test_drop_finds_the_largest_fall_and_its_line():
    points = [1.0 - i * 0.004 - (0.3 if i >= 40 else 0) for i in range(100)]  # one big step at index 40
    lines = [{"start": 0, "text": "intro"}, {"start": 10, "text": "the turn"}, {"start": 25, "text": "end"}]
    d = analytics.find_drop(points, 30.0, lines)
    assert d["at_s"] == pytest.approx(12.3) and d["line"] == "the turn"
    assert analytics.find_drop(points, 30.0)["line"] is None  # no lines yet: seconds only
    assert analytics.find_drop([1.0] * 100, 30.0) is None


def test_the_tab_renders_empty_with_rows_and_in_group_view(acct):
    from starlette.testclient import TestClient
    from src.web.app import app
    cand, _ = _clip("Tab clip")
    pid = _published(acct, "tab1", 12, title="Tab clip")
    analytics.link(pid, cand)
    with TestClient(app) as client:
        page = client.get("/analytics?sort=multiple")
        assert page.status_code == 200 and "Tab clip" in page.text and "Linked" in page.text
        by_voice = client.get("/analytics?group=voice")
        assert by_voice.status_code == 200 and "relatable" in by_voice.text
        assert client.post(f"/analytics/{pid}/link", data={"candidate_id": cand}, follow_redirects=False).status_code == 303


# ── Step 2: opening checks and watch notes ────────────────────────────────────

def _words(spec, offset=100.0):
    return [{"word": w, "start": offset + s, "end": offset + e} for w, s, e in spec]


def test_opening_checks_on_a_fixed_word_list():
    from src.opening import opening_checks, summary
    words = _words([("Nobody", 1.2, 1.6), ("expected", 1.7, 2.1), ("that.", 2.2, 2.6), ("Wait", 5.0, 5.3), ("nobody", 5.4, 5.9)])
    rf = opening_checks(words, 100.0, 10.0, True)
    assert rf["first_word_s"] == 1.2 and rf["words_first_3s"] == 3 and rf["longest_quiet_s"] == 2.4
    assert rf["loops"] is True and rf["hook_card"] is True  # "nobody" opens and closes the Short
    assert [ln["start"] for ln in rf["lines"]] == [1.2, 5.0] and rf["lines"][0]["text"] == "Nobody expected that."
    assert "First word at 1.2s" in summary(rf)
    quiet = opening_checks(_words([("Hello", 0.1, 0.4), ("there", 0.5, 0.8), ("friend", 8.0, 8.5)]), 100.0, 10.0, False)
    assert quiet["loops"] is False and quiet["longest_quiet_s"] == 7.2 and quiet["hook_card"] is False
    assert opening_checks([], 100.0, 10.0, False)["first_word_s"] is None


def test_render_facts_are_stored_and_copied_into_the_facts(acct):
    from src.db import set_clip_render_facts
    cand, clip = _clip("Facts clip")
    set_clip_render_facts(clip, {"first_word_s": 0.4, "loops": False, "lines": []})
    assert analytics.candidate_facts(cand, clip)["render_facts"]["first_word_s"] == 0.4
    set_clip_render_facts(clip, None)
    assert analytics.candidate_facts(cand, clip)["render_facts"] is None


def test_watch_notes_are_stored_once_and_capped_per_day(acct, monkeypatch):
    from src import gemini_budget
    from src.db import set_setting
    from src.pipeline import stage7_moments as s7
    calls = []

    class Resp:
        text = json.dumps({"opening": "a roar", "hook_card": "none", "subject": "s", "pacing": "p", "style": "st", "ending": "loops"})

    monkeypatch.setattr(s7, "clip_video_part", lambda meta, a, b: object())
    monkeypatch.setattr(s7, "get_gemini_client", lambda: None)
    monkeypatch.setattr(s7, "generate_content_with_retry", lambda **kw: calls.append(kw["purpose"]) or Resp())
    from google.genai import types
    monkeypatch.setattr(types, "Content", lambda parts: parts)
    monkeypatch.setattr(types, "Part", lambda **kw: kw)
    set_setting(f"analytics_watches:{gemini_budget.today()}", "0")
    ids = [_published(acct, f"w{i}", i + 1) for i in range(12)]
    assert analytics.watch_pending() == 10 and len(calls) == 10  # the cap
    assert analytics.watch_pending() == 0 and len(calls) == 10   # nothing left today
    notes = json.loads(_row(ids[0])["watch_notes"])
    assert notes["opening"] == "a roar" and _row(ids[11])["watch_notes"] is None  # the newest were watched first
