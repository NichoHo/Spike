"""Concept renders with real ffmpeg on a synthetic local source: story, pov, top3, top5."""

import json
import subprocess
from pathlib import Path

import numpy as np
import pytest

from src.pipeline.concept_render import make_card, render_concept_clip
from src.pipeline.stage8_sections import ensure_segment_section, section_bounds


@pytest.fixture(scope="module")
def source(tmp_path_factory):
    """A 60 s test pattern with a tone, as a 'local upload' so no download is needed."""
    root = tmp_path_factory.mktemp("concept_src")
    video = root / "stream.mp4"
    subprocess.run(["ffmpeg", "-y", "-hide_banner", "-loglevel", "error", "-f", "lavfi", "-i", "testsrc=size=1280x720:rate=30:duration=60",
                    "-f", "lavfi", "-i", "sine=frequency=440:duration=60", "-c:v", "libx264", "-preset", "ultrafast", "-c:a", "aac",
                    "-shortest", str(video)], check=True)
    return video


@pytest.fixture()
def env(source, tmp_path, monkeypatch):
    monkeypatch.chdir(Path(__file__).resolve().parent.parent)   # ASS files are passed to ffmpeg as relative paths
    vdir = Path(__file__).resolve().parent.parent / "data" / "videos" / f"_test_{tmp_path.name}"
    (vdir / "renders").mkdir(parents=True)
    jump = np.zeros(100, dtype=np.float32)
    jump[[36, 37]] = 15.0
    np.savez(vdir / "signals.npz", voice_jump=jump)
    meta = {"is_local": True, "local_path": str(source), "webpage_url": str(source)}
    words = [{"word": " hello", "start": 6.0, "end": 6.4}, {"word": " there", "start": 36.0, "end": 36.4}]
    yield {"vdir": vdir, "meta": meta, "words": words}
    import shutil
    shutil.rmtree(vdir, ignore_errors=True)


def seg(a, b, rank=None, label="", remove=None):
    return {"candidate_id": None, "start_s": a, "end_s": b, "remove": remove or [], "rank": rank, "label": label}


def run(env, concept, segs, overlay=None, out_name="out", **kw):
    out = env["vdir"] / "renders" / f"{out_name}.mp4"
    dur = render_concept_clip(
        concept=concept, segs=segs, overlay=overlay or {}, title="Speed does a thing", hook_text="Speed was so sure",
        video_dir=env["vdir"], meta=env["meta"], cand_id=1, all_words=env["words"], layout="center", caption_style="bold_pop",
        facecam_box=None, profanity_mask=True, letterbox_style="blur", out_file=out, thumb_file=out.with_suffix(".jpg"), **kw)
    return out, dur


def probe(path):
    info = json.loads(subprocess.run(["ffprobe", "-v", "error", "-show_entries", "stream=codec_type,width,height,channels:format=duration",
                                      "-of", "json", str(path)], capture_output=True, text=True, check=True).stdout)
    v = next(s for s in info["streams"] if s["codec_type"] == "video")
    a = next(s for s in info["streams"] if s["codec_type"] == "audio")
    return float(info["format"]["duration"]), (v["width"], v["height"]), a["channels"]


def band(video: Path, t: float) -> np.ndarray:
    """The top band of the frame (8% to 35% down) at time t, where captions, quotes and rank cards sit."""
    raw = subprocess.run(["ffmpeg", "-v", "error", "-ss", str(t), "-i", str(video), "-frames:v", "1", "-vf", "crop=iw:ih*0.27:0:ih*0.08",
                          "-f", "rawvideo", "-pix_fmt", "gray", "-"], capture_output=True, check=True).stdout
    return np.frombuffer(raw, dtype=np.uint8).astype(int)


def changed(a: Path, b: Path, t: float) -> float:
    """How much the top band differs between two renders at time t (mean absolute pixel difference)."""
    return float(np.abs(band(a, t) - band(b, t)).mean())


def test_pov_is_one_piece_with_the_caption_on_top_for_the_whole_clip(env):
    plain, _ = run(env, "pov", [seg(35.6, 41.6)], {"pov_text": ""}, out_name="plain")
    out, dur = run(env, "pov", [seg(35.6, 41.6)], {"pov_text": "POV: you said one more round at midnight"})
    length, size, channels = probe(out)
    assert abs(length - 6.0) < 0.4 and size == (1080, 1920) and channels == 2
    # The caption is the only text: it changes the top band at the start and at the end, compared with no caption
    assert changed(out, plain, 0.5) > 3 and changed(out, plain, length - 0.7) > 3


def test_story_has_a_skip_card_between_segments_and_the_callback_on_the_payoff(env):
    segs = [seg(5.0, 11.0), seg(30.0, 45.0)]
    ov = {"skip_card": "3 goals later", "callback_quote": "I never lose", "foreshadow": False}
    out, dur = run(env, "story", segs, ov)
    assert abs(dur - (6.0 + 1.0 + 15.0)) < 0.6
    assert band(out, 6.2).mean() < 8                      # the skip card is a black frame with centred text: nothing at the top
    no_quote, _ = run(env, "story", segs, {**ov, "callback_quote": ""}, out_name="noquote")
    peak_rel = 7.0 + (36.0 - 30.0)                        # the reaction peak is the voice-jump second at 36 s
    assert changed(out, no_quote, peak_rel + 0.5) > 3 and changed(out, no_quote, peak_rel + 3.0) < 1.5   # shown for 1.5 s, then gone
    foreshadow, dur2 = run(env, "story", segs, {**ov, "foreshadow": True}, out_name="flash")
    assert abs(dur2 - (dur + 0.6)) < 0.5                 # the 0.6 s flash opens the clip


def test_top3_teases_number_one_then_counts_down_with_rank_cards(env):
    segs = [seg(3.0, 10.0, rank=3, label="he blamed the controller"), seg(12.0, 20.0, rank=2, label="he blamed chat"), seg(30.0, 39.0, rank=1, label="the loss")]
    out, dur = run(env, "top3", segs[::-1])              # given best first: the renderer orders them
    assert abs(dur - (1.5 + 7.0 + 8.0 + 9.0)) < 0.8
    assert probe(out)[1] == (1080, 1920)
    # the rank card shows on the first entry (which starts after the 1.5 s tease) for 1.5 s, then it is gone
    nocard, _ = run(env, "top3", [dict(s, rank=s["rank"], label="") for s in segs], out_name="nolabel")
    assert changed(out, nocard, 2.2) > 3 and changed(out, nocard, 4.5) < 1.5


def test_top5_and_a_removed_stretch_shorten_the_clip(env):
    segs = [seg(2.0 + 10 * i, 9.0 + 10 * i, rank=5 - i, label=f"entry {5 - i}") for i in range(4)] + [seg(44.0, 53.0, rank=1, label="the loss", remove=[[47.0, 48.0]])]
    out, dur = run(env, "top5", segs)
    assert abs(dur - (1.5 + 4 * 7.0 + 8.0)) < 1.0        # tease, four 7 s entries, #1 minus its 1 s cut
    assert not any(p.name.startswith("tmp_concept") for p in (env["vdir"] / "renders").iterdir())   # work files are cleaned up


def test_segment_sections_are_fetched_wide_enough_and_refetched_when_an_edit_moves_out(env):
    vdir, meta = env["vdir"], env["meta"]
    first = ensure_segment_section(vdir, meta, 7, 0, 20.0, 26.0)
    lo, hi = section_bounds(first, 20.0, 26.0)
    assert lo == 17.0 and hi >= 29.0 - 0.3
    assert ensure_segment_section(vdir, meta, 7, 0, 21.0, 25.0) == first              # inside: kept as is
    m1 = first.stat().st_mtime_ns
    ensure_segment_section(vdir, meta, 7, 0, 10.0, 26.0)                                # moved earlier: fetched again
    assert section_bounds(first, 10.0, 26.0)[0] == 7.0 and first.stat().st_mtime_ns != m1


def test_skip_card_is_a_silent_black_frame_with_text(env):
    card = make_card("3 goals later", env["vdir"] / "renders" / "card.mp4", env["vdir"] / "renders")
    length, size, channels = probe(card)
    assert abs(length - 1.0) < 0.15 and size == (1080, 1920) and channels == 2
