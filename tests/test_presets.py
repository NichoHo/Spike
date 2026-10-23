"""Render presets shared by the New page and the source form."""

import json

import pytest
from fastapi import HTTPException

from src.moment_render import DEFAULT_PRESETS, source_presets
from src.web.routes.new import parse_presets


def test_source_presets_use_the_saved_ones_else_the_old_columns():
    assert source_presets(None) == DEFAULT_PRESETS
    old = source_presets({"layout": "split", "music": 0, "silence_trim": 1, "caption_style": "clean"})
    assert old["layout"] == "split" and old["music"] is False and old["cut_pauses"] == "natural" and old["caption_style"] == "clean"
    saved = source_presets({"presets": json.dumps({**DEFAULT_PRESETS, "cut_pauses": "tight"}), "music": 0, "silence_trim": 0})
    assert saved["music"] == "auto" and saved["cut_pauses"] == "tight"   # the saved presets win over the old columns


def test_switches_count_as_on_only_when_sent_and_profanity_is_always_masked():
    p = parse_presets("split", None, "on", "off", "title", "karaoke")
    assert p == {"layout": "split", "letterbox_style": "title", "captions": False, "caption_style": "karaoke",
                 "profanity_mask": True, "music": True, "cut_pauses": "off"}
    assert parse_presets("auto", "on", "auto", "auto", "blur", "bold_pop")["captions"] is True
    with pytest.raises(HTTPException):
        parse_presets("nope", "on", "auto", "auto", "blur", "bold_pop")


def test_a_new_source_starts_on_auto():
    from fastapi.testclient import TestClient
    from src.db import list_sources
    from src.web.app import app
    c = TestClient(app)
    assert c.post("/sources/new", data={"kind": "twitch", "external_id": "presets_test_src", "display_name": "Presets"},
                  follow_redirects=False).status_code == 303
    src = next(dict(s) for s in list_sources() if s["external_id"] == "presets_test_src")
    assert json.loads(src["presets"]) == DEFAULT_PRESETS
    c.post(f"/sources/{src['id']}/delete", follow_redirects=False)
