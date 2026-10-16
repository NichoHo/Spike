"""Mid-clip layout switches: segment building and a real ffmpeg render."""

import json
import subprocess
from pathlib import Path

from src.pipeline.stage9c_render import layout_segments_for, render_single_vertical_clip


def test_layout_segments_for():
    changes = [
        {"t": 112.0, "layout": "split"},        # back to split: kept
        {"t": 105.0, "layout": "face_track"},
        {"t": 105.1, "layout": "center"},       # within 0.2 s: replaces face_track
        {"t": 99.0, "layout": "center"},        # before the clip: dropped
        {"t": 108.0, "layout": "bogus"},        # unknown layout: dropped
        {"t": 109.0, "layout": "center"},       # same as current: merged
    ]
    assert layout_segments_for("split", changes, 100.0, 120.0, []) == [
        (0.0, "split"), (5.0, "center"), (12.0, "split"),
    ]
    # a 2 s pause cut before the switch moves it 2 s earlier on the clip timeline
    assert layout_segments_for("split", changes[:2], 100.0, 120.0, [(101.0, 103.0)]) == [
        (0.0, "split"), (3.0, "face_track"), (10.0, "split"),
    ]
    assert layout_segments_for("center", None, 0.0, 10.0, []) == [(0.0, "center")]


def test_render_with_layout_switches(tmp_path: Path, capfd):
    sec = tmp_path / "section.mp4"
    subprocess.run([
        "ffmpeg", "-y", "-hide_banner", "-loglevel", "error",
        "-f", "lavfi", "-i", "testsrc=size=1280x720:rate=30:duration=14",
        "-f", "lavfi", "-i", "sine=frequency=440:duration=14",
        "-c:v", "libx264", "-preset", "ultrafast", "-c:a", "aac", "-shortest", str(sec),
    ], check=True)

    out = tmp_path / "clip.mp4"
    # section starts 5 s before the clip, so source t = 105 is 5 s into the section
    ok = render_single_vertical_clip(
        sec_file=sec, out_file=out, thumb_file=tmp_path / "thumb.jpg",
        clip_start=105.0, clip_end=113.0, layout="split",
        facecam_box={"x": 0.0, "y": 0.0, "w": 0.25, "h": 0.25},
        punch_in_zoom=False,
        layout_changes=[{"t": 107.0, "layout": "face_track"}, {"t": 110.0, "layout": "letterbox"}],
    )
    assert ok
    assert "primary render failed" not in capfd.readouterr().out  # not the center-crop fallback
    probe = json.loads(subprocess.run(
        ["ffprobe", "-v", "error", "-select_streams", "v:0", "-show_entries",
         "stream=width,height:format=duration", "-of", "json", str(out)],
        capture_output=True, text=True, check=True,
    ).stdout)
    assert (probe["streams"][0]["width"], probe["streams"][0]["height"]) == (1080, 1920)
    assert abs(float(probe["format"]["duration"]) - 8.0) < 0.3


def test_parse_layout_changes_drops_bad_input():
    from src.web.routes.clips import _parse_layout_changes
    raw = json.dumps([
        {"t": 12, "layout": "split"}, {"t": 5, "layout": "face_track"},
        {"t": 50, "layout": "split"}, {"t": "x", "layout": "center"}, {"layout": "center"},
        {"t": 7, "layout": "auto"}, "junk",
    ])
    assert _parse_layout_changes(raw, 0, 30) == [{"t": 5.0, "layout": "face_track"}, {"t": 12.0, "layout": "split"}]
    assert _parse_layout_changes("not json", 0, 30) == []
    assert _parse_layout_changes('{"t": 1}', 0, 30) == []
    assert _parse_layout_changes("", 0, 30) == []


def _section(tmp_path: Path) -> Path:
    sec = tmp_path / "section.mp4"
    subprocess.run([
        "ffmpeg", "-y", "-hide_banner", "-loglevel", "error",
        "-f", "lavfi", "-i", "testsrc=size=1280x720:rate=30:duration=20",
        "-f", "lavfi", "-i", "sine=frequency=440:duration=20",
        "-c:v", "libx264", "-preset", "ultrafast", "-c:a", "aac", "-shortest", str(sec),
    ], check=True)
    return sec


def _duration(path: Path) -> float:
    return float(subprocess.run(
        ["ffprobe", "-v", "error", "-show_entries", "format=duration", "-of", "csv=p=0", str(path)],
        capture_output=True, text=True, check=True,
    ).stdout)


def test_render_with_several_zooms_a_cut_and_a_moved_section_start(tmp_path: Path, capfd):
    """Zooms in split (facecam panel only) and center, a manual cut, and a section that starts 12 s before the clip."""
    sec = _section(tmp_path)
    for layout in ("split", "center"):
        out = tmp_path / f"clip_{layout}.mp4"
        ok = render_single_vertical_clip(
            sec_file=sec, out_file=out, thumb_file=tmp_path / f"t_{layout}.jpg",
            clip_start=112.0, clip_end=120.0, layout=layout,
            facecam_box={"x": 0.0, "y": 0.0, "w": 0.25, "h": 0.25},
            zooms=[{"t": 113.0, "scale": 1.2, "hold_s": 1.0}, {"t": 117.0, "scale": 1.35, "hold_s": 1.5}],
            extra_cuts=[(114.5, 115.5)],
            section_start_s=100.0,
        )
        assert ok and "primary render failed" not in capfd.readouterr().out
        assert abs(_duration(out) - 7.0) < 0.3   # 8 s clip minus the 1 s cut


def test_empty_zoom_list_means_no_zoom_and_none_means_a_default(tmp_path: Path):
    from src.pipeline.stage9c_render import default_zooms
    sec = tmp_path / "videos" / "1" / "sections" / "section_1.mp4"
    sec.parent.mkdir(parents=True)
    assert default_zooms(sec, 100.0, 130.0, 118.5) == [{"t": 118.5, "scale": 1.15, "hold_s": 1.5}]   # at the payoff
    assert default_zooms(sec, 100.0, 130.0, None) == []                                               # no payoff, no signals file
    import numpy as np
    jump = np.zeros(200, dtype=np.float32)
    jump[121] = 14.0
    np.savez(sec.parent.parent / "signals.npz", voice_jump=jump)
    assert default_zooms(sec, 100.0, 130.0, None) == [{"t": 121.0, "scale": 1.15, "hold_s": 1.5}]    # loudest voice-jump second
