from starlette.testclient import TestClient

from src.db import add_claude_usage, claude_usage_summary, get_connection, init_db
from src.web.app import app


def test_usage_summary_windows_and_labels():
    init_db()
    with get_connection() as conn:
        conn.execute("DELETE FROM claude_usage")
        conn.execute("INSERT INTO claude_usage (ts, label, tokens_in, tokens_out) VALUES (datetime('now', '-6 days'), 'editor', 900, 100)")
    add_claude_usage("editor", 10000, 3000, 0.05)
    add_claude_usage("pov_captions", 6000, 1000, 0.02)
    s = claude_usage_summary()
    assert s["h5"]["calls"] == 2 and s["h5"]["tokens"] == 20000     # the 6-day-old call is outside 5 hours
    assert s["d7"]["calls"] == 3 and s["d7"]["tokens"] == 21000
    assert s["by_label"][0] == {"label": "editor", "calls": 2, "tokens": 14000}


def test_jobs_page_shows_the_usage_card(monkeypatch):
    init_db()
    add_claude_usage("editor", 1234, 100, 0.01)
    monkeypatch.setattr("src.web.routes.jobs.CLAUDE_5H_TOKEN_CAP", 10000)
    html = TestClient(app).get("/jobs").text
    assert "Claude Pro usage by Spike" in html and "editor" in html and "%" in html
