"""Claude fallback: each call waits for the user's answer; "don't ask again today" skips the rest of the day."""

import json
import threading
import time

from src import claude_fallback as cf
from src.db import set_setting
from src.pipeline import stage7_moments as s7

_real_sleep = time.sleep


def _answer_when_pending(approve, skip_today=False):
    def run():
        for _ in range(200):
            req = cf.pending()
            if req:
                cf.answer(req["id"], approve, skip_today)
                return
            _real_sleep(0.05)
    t = threading.Thread(target=run)
    t.start()
    return t


def test_each_call_waits_for_an_answer_and_skip_today_stops_asking(monkeypatch):
    monkeypatch.setattr(cf, "_notify", lambda label: None)
    real_sleep = time.sleep
    monkeypatch.setattr(cf.time, "sleep", lambda s: real_sleep(0.05))
    set_setting(cf.SKIP_KEY, "")
    set_setting(cf.REQUEST_KEY, "null")

    t = _answer_when_pending(False)
    assert cf.ask("score one moment", "") is False
    t.join()

    t = _answer_when_pending(True)  # approved, but not for the day
    assert cf.ask("score one moment", "") is True
    t.join()
    assert cf.pending() is None

    t = _answer_when_pending(True, skip_today=True)
    assert cf.ask("score one moment", "") is True
    t.join()
    assert cf.ask("score another", "") is True  # no request made: today is skipped
    assert cf.pending() is None
    set_setting(cf.SKIP_KEY, "")


def test_claude_instead_returns_gemini_shaped_text_and_skips_video(monkeypatch):
    from types import SimpleNamespace
    import src.claude_cli
    monkeypatch.setattr(cf, "ask", lambda purpose, detail: True)
    used = []
    monkeypatch.setattr(src.claude_cli, "run_claude",
                        lambda system, prompt, schema, label="", model="sonnet": used.append(model) or {"keep": True})
    out = s7.claude_instead("judge this", SimpleNamespace(system_instruction="rules"), "score one moment")
    assert json.loads(out.text) == {"keep": True}
    s7.claude_instead("read the stream", None, "read the stream", claude_model="sonnet")
    assert used == ["haiku", "sonnet"]  # Flash-Lite calls -> Haiku, Flash calls -> Sonnet
    assert s7.claude_instead(["video part", "text"], None, "watch a clip") is None
    monkeypatch.setattr(cf, "ask", lambda purpose, detail: False)
    assert s7.claude_instead("judge this", None, "score one moment") is None


def test_pause_stops_every_claude_call_and_denies_a_waiting_one(monkeypatch):
    import pytest
    from src import claude_cli
    monkeypatch.setattr(cf, "_notify", lambda label: None)
    monkeypatch.setattr(cf.time, "sleep", lambda s: _real_sleep(0.05))
    set_setting(cf.SKIP_KEY, "")
    set_setting(cf.REQUEST_KEY, "null")

    def pause_when_pending():
        for _ in range(200):
            if cf.pending():
                cf.set_paused(True)
                return
            _real_sleep(0.05)
    t = threading.Thread(target=pause_when_pending)
    t.start()
    assert cf.ask("score one moment", "") is False  # the job waiting for the OK stops waiting
    t.join()
    assert cf.paused() and cf.ask("score another", "") is False and cf.pending() is None  # no new popup
    with pytest.raises(claude_cli.ClaudeError, match="paused"):
        claude_cli.run_claude("s", "p", {"type": "object"})  # the editor, profile etc. fall back to Gemini on this
    cf.set_paused(False)
    assert not cf.paused()


def test_running_mark_expires():
    cf.mark_running("editor pass", 60)
    assert cf.running() == "editor pass"
    cf.clear_running()
    assert cf.running() is None
    cf.mark_running("crashed call", -1)  # the process died mid-call: the mark lapses on its own
    assert cf.running() is None


def test_list_values_returned_as_strings_are_decoded():
    # Haiku under the loose schema: '["twitch", "kai"]' as a string, "[laughter]" stays text
    out = s7._unstring({"hashtags": '["twitch", "kai"]', "score": "28", "punchline": "[laughter] no way",
                        "moments": '[{"start_line": "3"}]'})
    assert out["hashtags"] == ["twitch", "kai"] and out["moments"] == [{"start_line": "3"}]
    assert out["punchline"] == "[laughter] no way" and out["score"] == "28"
