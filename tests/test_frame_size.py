"""Frame size crops the sides of the picture before it is scaled into the 1080x1920 letterbox."""

import subprocess

import pytest
from PIL import Image

from src.pipeline.anime_moments import ANIME_RENDER_DEFAULTS
from src.pipeline.stage9c_render import _layout_filters, build_vertical_filtergraph, footage_height, frame_crop


def test_frame_crop_keeps_the_middle_at_the_frame_ratio():
    assert frame_crop("fit", 1920, 1080) is None
    assert frame_crop("medium", 1920, 1080) == (1440, 1080)  # 4:3
    assert frame_crop("close", 1920, 1080) == (1080, 1080)   # square
    assert frame_crop("medium", 1280, 720) == (960, 720)
    assert frame_crop("medium", 1440, 1080) is None          # already 4:3: nothing to crop
    assert frame_crop("medium", 1080, 1920) is None          # a tall source is never cropped
    assert frame_crop("huge", 1920, 1080) is None            # an unknown name means fit


def test_the_title_card_sits_above_the_cropped_picture():
    assert [footage_height(f, 1920, 1080) for f in ("fit", "medium", "close")] == [607, 810, 1080]


def _graph(**kw):
    return build_vertical_filtergraph(sec_start=0.0, keep_intervals=[(0.0, 10.0)], layout="letterbox", src_w=1920,
                                      src_h=1080, effective_dur=10.0, ass_rel="x.ass", **kw)


def test_the_crop_comes_before_the_scale_in_both_letterbox_styles():
    assert "[v_trimmed]crop=1440:1080,scale=1080:1920" in _graph(letterbox_style="title", title_input=1, frame="medium")
    assert "[v_trimmed]crop=1080:1080,split=2[bg_in][fg_in]" in _graph(letterbox_style="blur", frame="close")
    assert "crop=1440" not in _graph(letterbox_style="title", title_input=1)  # fit is the default


@pytest.mark.parametrize("frame,rows", [("fit", 607), ("medium", 810), ("close", 1080)])
def test_ffmpeg_fills_the_expected_height(tmp_path, frame, rows):
    graph = ";".join(["[0:v]null[v]"] + _layout_filters("letterbox", "v", "out", 1920, 1080, None, None, None, "title", "", frame))
    png = tmp_path / "f.png"
    subprocess.run(["ffmpeg", "-y", "-hide_banner", "-loglevel", "error", "-f", "lavfi", "-i",
                    "color=c=red:size=1920x1080:rate=5:duration=1", "-filter_complex", graph, "-map", "[out]",
                    "-frames:v", "1", str(png)], check=True)
    img = Image.open(png).convert("RGB")
    assert img.size == (1080, 1920)
    red = sum(1 for y in range(1920) if img.getpixel((540, y))[0] > 200 and img.getpixel((540, y))[1] < 80)  # white bars are not red
    assert abs(red - rows) <= 2


def test_anime_clips_start_on_the_medium_frame():
    assert ANIME_RENDER_DEFAULTS["frame"] == "medium"
