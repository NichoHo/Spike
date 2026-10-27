"""Meme sound effects: cleaning the page's list and mixing them into the render's audio graph."""

from src.ai_edit import AiEditOut, build_prompt, clamp
from src.pipeline.stage9c_render import build_vertical_filtergraph
from src.sfx import SFX_MAX, clean_sfx


def test_clean_sfx_keeps_known_sounds_inside_the_clip_sorted():
    raw = [{"t": 105.123, "id": "bonk"}, {"t": 101, "id": "fart"}, {"t": 99, "id": "bonk"},
           {"t": 102, "id": "nope"}, {"t": "x", "id": "bonk"}, {"id": "fart"}, {"t": 130, "id": "thud"}]
    assert clean_sfx(raw, 100, 120) == [{"t": 101.0, "id": "fart"}, {"t": 105.12, "id": "bonk"}]
    assert clean_sfx('[{"t": 110, "id": "thud"}]', 100, 120) == [{"t": 110.0, "id": "thud"}]
    assert clean_sfx(None, 100, 120) == [] and clean_sfx("not json", 100, 120) == []
    assert len(clean_sfx([{"t": 100 + i * 0.1, "id": "bonk"} for i in range(60)], 100, 120)) == SFX_MAX


def test_filtergraph_delays_each_sound_and_mixes_before_loudnorm():
    g = build_vertical_filtergraph(
        sec_start=0, keep_intervals=[(5, 25)], layout="center", src_w=1920, src_h=1080,
        effective_dur=20, ass_rel="x.ass", sfx_at=[(1, 2.5), (2, 10.0)],
    )
    assert "[1:a]" in g and "adelay=delays=2500:all=1[sfx_0]" in g
    assert "[2:a]" in g and "adelay=delays=10000:all=1[sfx_1]" in g
    assert "amix=inputs=3:duration=first:normalize=0[a_sfx]" in g
    assert "[a_sfx]loudnorm" in g
    # without sound effects the audio path is unchanged
    assert "sfx" not in build_vertical_filtergraph(
        sec_start=0, keep_intervals=[(5, 25)], layout="center", src_w=1920, src_h=1080, effective_dur=20, ass_rel="x.ass")


STATE = {"concept": "single", "start_s": 100.0, "end_s": 120.0, "title": "T", "cuts": [], "zooms": [], "layout": "split",
         "sfx": [{"t": 104.0, "id": "bonk"}]}


def test_ask_the_editor_sees_the_sound_list_and_the_current_sounds():
    _, prompt = build_prompt(STATE, [{"word": "no", "start": 110.2}], "add a sound when he loses", "", "Speed")
    assert "sad_trombone: a fail" in prompt and "sounds [{'t': 104.0, 'id': 'bonk'}]" in prompt


def test_ask_the_editor_sounds_are_clamped_to_known_ids_inside_the_clip():
    out = AiEditOut.model_validate({
        "start_s": 100, "end_s": 120, "remove": [], "zooms": [], "title": "T", "explanation": "Added a trombone.",
        "sounds": [{"t": 110.2, "id": "sad_trombone"}, {"t": 111, "id": "airhorn"}, {"t": 150, "id": "bonk"}]})
    assert clamp(out, STATE, "Speed")["sfx"] == [{"t": 110.2, "id": "sad_trombone"}]
