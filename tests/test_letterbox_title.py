from src.pipeline.stage9c_render import build_vertical_filtergraph
from src.pipeline.title_card import _tokens, strip_emoji


def _graph(**kw):
    return build_vertical_filtergraph(
        sec_start=0.0, keep_intervals=[(0.0, 10.0)], layout="letterbox", src_w=1920, src_h=1080,
        effective_dur=10.0, ass_rel="x.ass", **kw
    )


def test_emoji_sequences_stay_whole():
    pieces = [p for is_e, p in _tokens("hi 👨‍💻 🇮🇩 ❤️ 👍🏽") if is_e]
    assert pieces == ["👨‍💻", "🇮🇩", "❤️", "👍🏽"]
    assert strip_emoji("He rage quits 😭") == "He rage quits"


def test_title_style_pads_white_and_overlays_card():
    g = _graph(letterbox_style="title", title_input=1)
    assert "color=white" in g and "boxblur" not in g
    assert "[v_zoomed][1:v]overlay=0:0[v_titled]" in g


def test_blur_style_unchanged():
    g = _graph()
    assert "boxblur" in g and "overlay=0:0" not in g


def test_card_only_shows_during_letterbox_segments():
    g = _graph(letterbox_style="title", title_input=2, layout_segments=[(0.0, "center"), (3.0, "letterbox")])
    assert "[2:v]overlay=0:0:enable='gte(t,3.000)'" in g
