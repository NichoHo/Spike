import pytest
import re
from pathlib import Path

from src.pipeline import stage9c_render as r


def test_auto_uses_ai_pick(monkeypatch):
    monkeypatch.setattr("src.layout_ai.choose_layout", lambda p: "letterbox")
    assert r.resolve_layout("auto", Path("x.mp4")) == ("letterbox", None)


def test_auto_split_uses_detected_facecam(monkeypatch):
    cam = {"x": 0.8, "y": 0.8, "w": 0.1, "h": 0.1}
    monkeypatch.setattr("src.layout_ai.choose_layout", lambda p: "split")
    monkeypatch.setattr(r, "detect_facecam", lambda p: cam)
    assert r.resolve_layout("auto", Path("x.mp4")) == ("split", cam)


def test_auto_falls_back_to_heuristic_when_ai_fails(monkeypatch):
    monkeypatch.setattr("src.layout_ai.choose_layout", lambda p: None)
    monkeypatch.setattr(r, "detect_facecam", lambda p: None)
    assert r.resolve_layout("auto", Path("x.mp4")) == ("face_track", None)


def test_explicit_layout_skips_ai(monkeypatch):
    monkeypatch.setattr("src.layout_ai.choose_layout", lambda p: 1 / 0)
    assert r.resolve_layout("center", Path("x.mp4")) == ("center", None)


def test_smooth_runs_drops_a_flicker_and_places_switch_between_frames():
    from src.layout_ai import smooth_runs
    times = [0, 2.5, 5, 7.5, 10, 12.5, 15]
    labels = ["split", "split", "letterbox", "split", "split", "face_track", "face_track"]
    # the single letterbox frame (under 3 s) is absorbed; face_track lasts 3.75 s so it stays
    assert smooth_runs(times, labels, clip_end=16.25) == [[0, "split"], [11.25, "face_track"]]


def test_smooth_runs_short_opening_merges_into_next():
    from src.layout_ai import smooth_runs
    assert smooth_runs([0, 2.5, 5, 7.5], ["center", "split", "split", "split"], 10) == [[0, "split"]]


def test_snap_to_pause_moves_to_nearby_gap_only():
    from src.layout_ai import snap_to_pause
    words = [{"start": 0, "end": 4.0}, {"start": 4.8, "end": 6}, {"start": 6.05, "end": 9}]
    assert snap_to_pause(4.6, words) == 4.4  # gap 4.0-4.8
    assert snap_to_pause(8.0, words) == 8.0  # nothing within 1 s


def test_layout_picker_auto_tile_is_opt_in():
    from src.web.app import templates
    ui = templates.env.get_template("macros/ui.html").module
    assert 'value="auto" checked' in str(ui.layout_picker("layout", "auto", "title", auto=True))
    assert 'value="auto"' not in str(ui.layout_picker("layout", "split", "title"))


def test_budget_counts_per_model_resets_daily_and_auto_stops_at_zero(monkeypatch):
    from src import gemini_budget as gb, layout_ai
    store = {}
    monkeypatch.setattr(gb, "get_setting", lambda k, d=None: store.get(k, d))
    monkeypatch.setattr(gb, "set_setting", lambda k, v: store.__setitem__(k, v))
    monkeypatch.setattr("src.config.GEMINI_DAILY_LIMIT", 2)
    monkeypatch.setattr("src.config.LAYOUT_GEMINI_MODEL", "flash")
    monkeypatch.setattr("src.config.GEMINI_API_KEY", "k")
    gb.spend("flash"); gb.spend("flash"); gb.spend("lite")  # other models have their own count
    assert gb.left("flash") == 0 and gb.left("lite") == 1
    assert layout_ai.calls_left() == 0
    assert layout_ai.plan_layouts(Path("x.mp4"), 0, 10, 0, []) is None  # no call made at 0
    assert layout_ai.choose_layout(Path("x.mp4")) is None
    store["gemini_used:flash"] = "2000-01-01|2"  # a new day resets the count
    assert gb.left("flash") == 2


def test_auto_tile_disabled_when_out_of_calls(monkeypatch):
    from src.web.app import templates
    monkeypatch.setitem(templates.env.globals, "layout_ai_left", lambda: 0)
    ui = templates.env.get_template("macros/ui.html").make_module()  # fresh: .module caches its globals
    html = str(ui.layout_picker("layout", "auto", "title", auto=True))
    assert re.search(r'value="auto"\s+disabled', html) and "layout-option__quota--out" in html
    monkeypatch.setitem(templates.env.globals, "layout_ai_left", lambda: 7)
    ui = templates.env.get_template("macros/ui.html").make_module()
    assert "7 of" in str(ui.layout_picker("layout", "auto", "title", auto=True))


def test_judge_falls_back_to_flash_lite_when_flash_quota_is_gone(monkeypatch):
    from src import gemini_budget as gb
    from src.pipeline import stage7_moments as s7
    store = {}
    monkeypatch.setattr(gb, "get_setting", lambda k, d=None: store.get(k, d))
    monkeypatch.setattr(gb, "set_setting", lambda k, v: store.__setitem__(k, v))
    monkeypatch.setattr(s7, "JUDGE_GEMINI_MODEL", "flash")
    monkeypatch.setattr(s7, "DEFAULT_GEMINI_MODEL", "lite")
    monkeypatch.setattr("src.config.GEMINI_DAILY_LIMITS", {"flash": 5})
    calls = []

    def fake(client, model, contents, config):
        calls.append(model)
        if model == "flash":
            raise s7.QuotaExhausted("429")
        return "ok"

    monkeypatch.setattr(s7, "generate_content_with_retry", fake)
    assert s7.judge_generate(None, "p", None) == "ok"
    assert calls == ["flash", "lite"]
    assert gb.left("flash") == 0
    assert s7.judge_generate(None, "p", None) == "ok"  # budget now spent: goes straight to Flash-Lite
    assert calls == ["flash", "lite", "lite"]


def test_second_gemini_key_takes_over_when_the_first_hits_its_daily_quota(monkeypatch):
    from src import config, gemini_budget as gb
    from src.pipeline import stage7_moments as s7
    used = []

    class Fake:
        def __init__(self, api_key):
            self.key, self.models = api_key, self

        def generate_content(self, model, **kw):
            used.append(self.key)
            if self.key == "a":
                raise RuntimeError("429 RESOURCE_EXHAUSTED. Please retry in 7h33m11s")
            if self.key == "slow":
                raise RuntimeError("429 RESOURCE_EXHAUSTED. Please retry in 20s")
            return "ok"

    monkeypatch.setattr(s7.genai, "Client", Fake)
    monkeypatch.setattr("src.config.GEMINI_API_KEY", "a, b")
    client = s7.get_gemini_client()
    assert client.models.generate_content(model="m", contents="x") == "ok"
    assert client.models.generate_content(model="m", contents="x") == "ok"
    assert used == ["a", "b", "b"]  # key a is skipped once its daily quota is gone
    assert gb.key_capped("m", "a")  # the cap is persisted (survives a restart; shared across users)
    assert gb.limit("m") == 2 * config.GEMINI_DAILY_LIMIT  # two keys, two quotas
    used.clear()
    monkeypatch.setattr("src.config.GEMINI_API_KEY", "slow, b")
    with pytest.raises(RuntimeError):
        s7.get_gemini_client().models.generate_content(model="m", contents="x")
    assert used == ["slow"]  # a per-minute 429 is retried by the caller, not handed to the next key
