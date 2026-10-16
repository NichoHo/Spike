"""
Phase 2 unit tests:
1. ASS caption generation — word grouping, timestamp formatting, profanity masking
2. Face-track EMA smoothing — verifies None hold and alpha convergence
3. Zoom expression — verifies it contains the peak frame correctly
"""

import unittest
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from src.pipeline.stage9b_captions import (
    _ts_to_ass,
    _group_words,
    _escape_ass,
    _mask_profanity,
    generate_ass,
)
from src.pipeline.stage9a_face_track import _ema_smooth_centers
from src.pipeline.stage9c_render import _zoom_expr


class TestCaptions(unittest.TestCase):
    def _make_words(self, texts, start=0.0, dur=0.5):
        """Helper: build fake word list."""
        words = []
        for i, t in enumerate(texts):
            words.append({
                "word": t,
                "start": start + i * dur,
                "end": start + i * dur + dur - 0.05,
            })
        return words

    def test_ts_to_ass_zero(self):
        self.assertEqual(_ts_to_ass(0.0), "0:00:00.00")

    def test_ts_to_ass_normal(self):
        # 65.5 seconds = 1:05.50
        self.assertEqual(_ts_to_ass(65.5), "0:01:05.50")

    def test_ts_to_ass_hours(self):
        # 3661.0 = 1h 1m 1s
        self.assertEqual(_ts_to_ass(3661.0), "1:01:01.00")

    def test_escape_ass(self):
        raw = "he said {wow} and \\yeah"
        escaped = _escape_ass(raw)
        self.assertNotIn("{", escaped.replace("\\{", ""))
        self.assertNotIn("}", escaped.replace("\\}", ""))

    def test_profanity_mask_applied(self):
        result = _mask_profanity("what the fuck man")
        self.assertIn("f*ck", result)
        self.assertNotIn("fuck", result)
        self.assertEqual(_mask_profanity("nigga"), "n*gga")
        self.assertEqual(_mask_profanity("Motherfucker"), "Motherf*cker")

    def test_profanity_mask_short_word(self):
        # Short words (<=2 chars) get fully masked
        # 'ass' is 3 chars -> a*s
        result = _mask_profanity("ass")
        self.assertEqual(result, "a*s")

    def test_group_words_size(self):
        words = self._make_words(["hello", "world", "this", "is", "a", "test"], start=10.0)
        groups = _group_words(words, words_per_line=3, clip_start=10.0, clip_end=25.0)
        self.assertEqual(len(groups), 2)
        self.assertEqual(len(groups[0]["words"]), 3)
        self.assertEqual(len(groups[1]["words"]), 3)

    def test_group_words_filters_outside_window(self):
        words = self._make_words(["hello", "world"], start=5.0)
        groups = _group_words(words, words_per_line=3, clip_start=10.0, clip_end=20.0)
        # Words start at 5.0 and 5.5, both < clip_start 10.0, so no groups
        self.assertEqual(len(groups), 0)

    def test_generate_ass_karaoke_has_k_tags(self):
        words = self._make_words(["wait", "for", "it"], start=100.0)
        ass = generate_ass(words, clip_start_s=100.0, clip_end_s=105.0, style="karaoke")
        self.assertIn("\\k", ass)

    def test_generate_ass_clean_no_k_tags(self):
        words = self._make_words(["wait", "for", "it"], start=100.0)
        ass = generate_ass(words, clip_start_s=100.0, clip_end_s=105.0, style="clean")
        self.assertNotIn("\\k", ass)

    def test_generate_ass_timestamps_start_at_zero(self):
        """Captions must be relative to clip start, first line should start near 0."""
        words = self._make_words(["hello", "world"], start=200.0, dur=0.5)
        ass = generate_ass(words, clip_start_s=200.0, clip_end_s=205.0)
        # The first Dialogue line start time should be 0:00:00.XX
        lines = [l for l in ass.splitlines() if l.startswith("Dialogue:")]
        self.assertTrue(len(lines) > 0)
        first_start = lines[0].split(",")[1]
        self.assertTrue(first_start.startswith("0:00:00"), f"Unexpected start: {first_start}")


class TestFaceTrackEMA(unittest.TestCase):
    def test_hold_on_no_detection(self):
        """When None appears, the last position is held."""
        raw = [(0.3, 0.3, 0.1, 0.1), None, None]
        centers = _ema_smooth_centers(raw, alpha=1.0)  # alpha=1 = no smoothing
        # All should be (0.35, 0.35) since after the first detection,
        # the center is held on None
        self.assertAlmostEqual(centers[1][0], centers[0][0], places=4)
        self.assertAlmostEqual(centers[2][0], centers[0][0], places=4)

    def test_ema_converges_toward_new_position(self):
        """EMA should move toward a new face position over multiple frames."""
        initial = (0.5, 0.5, 0.1, 0.1)
        new_pos = (0.9, 0.5, 0.1, 0.1)
        raw = [initial] + [new_pos] * 20
        centers = _ema_smooth_centers(raw, alpha=0.5)
        # After 20 steps with alpha=0.5, the x should be very close to 0.95 (center of 0.9+0.1/2)
        final_x = centers[-1][0]
        self.assertGreater(final_x, 0.80)

    def test_default_position_before_any_detection(self):
        """If all are None, holds the default (0.5, 0.3)."""
        raw = [None, None, None]
        centers = _ema_smooth_centers(raw)
        for cx, cy in centers:
            self.assertAlmostEqual(cx, 0.5, places=4)
            self.assertAlmostEqual(cy, 0.3, places=4)


class TestZoomExpr(unittest.TestCase):
    def test_contains_pulse_frames(self):
        """A pulse at 5 s starts at frame 150 (30 fps)."""
        expr = _zoom_expr([{"t": 5.0, "scale": 1.2, "hold_s": 1.0}])
        self.assertIn("150", expr)
        self.assertIn("0.200", expr)  # strength is scale - 1

    def test_pulses_add_and_are_capped(self):
        from src.config import ZOOM_MAX
        expr = _zoom_expr([{"t": 1.0, "scale": 1.2, "hold_s": 1.0}, {"t": 4.0, "scale": 1.35, "hold_s": 1.0}])
        self.assertIn("0.200*", expr)
        self.assertIn("0.350*", expr)
        self.assertTrue(expr.startswith(f"min({ZOOM_MAX},"))

    def test_no_zooms_is_a_constant(self):
        self.assertEqual(_zoom_expr([]), "1.0")


if __name__ == "__main__":
    unittest.main()


class TestShortsEdit(unittest.TestCase):
    """Captions follow speech, split crops land on the facecam, jump cuts alternate zoom."""

    def test_dialogue_lines_have_ten_fields(self):
        # An 11th field pushed a stray "," onto the screen before every caption
        words = [{"word": " Oh,", "start": 0.0, "end": 0.3}, {"word": " man", "start": 0.3, "end": 0.6}]
        for style in ("bold_pop", "karaoke", "clean"):
            ass = generate_ass(words, 0.0, 2.0, style=style)
            for line in (l for l in ass.splitlines() if l.startswith("Dialogue:")):
                text = line.split(",", 9)[9]
                self.assertFalse(text.startswith(","), f"{style}: {line}")

    def test_group_breaks_after_sentence_end_and_pause(self):
        words = [
            {"word": " happened.", "start": 0.0, "end": 0.4},
            {"word": " This", "start": 0.45, "end": 0.6},
            {"word": " is", "start": 0.6, "end": 0.7},
            {"word": " wild", "start": 2.0, "end": 2.3},  # after a 1.3 s pause
        ]
        groups = [[w["word"].strip() for w in g["words"]] for g in _group_words(words, 3)]
        self.assertEqual(groups, [["happened."], ["This", "is"], ["wild"]])

    def test_group_does_not_linger_through_pause(self):
        words = [{"word": " hi", "start": 0.0, "end": 0.3}, {"word": " there", "start": 5.0, "end": 5.3}]
        self.assertLessEqual(_group_words(words, 3)[0]["end"], 0.6)

    def test_split_crops_face_on_top_content_avoids_cam(self):
        from src.pipeline.stage9c_render import split_crops
        # Facecam bottom-left, like a reaction stream
        (fx, fy, fw, fh), (gx, gy, gw, gh) = split_crops({"cx": 0.146, "cy": 0.873, "w": 0.067}, 1920, 1080)
        self.assertTrue(fx <= 0.146 * 1920 <= fx + fw)
        self.assertTrue(fy <= 0.873 * 1080 <= fy + fh)
        self.assertLessEqual(fy + fh, 1080)
        self.assertGreaterEqual(gx, fx + fw - 1)  # content crop starts right of the cam
        self.assertEqual(gh, 1080)

    def test_jump_cut_zoom_only_on_odd_segments(self):
        from src.pipeline.stage9c_render import _jump_cut_zoom_expr
        expr = _jump_cut_zoom_expr([(0.0, 2.0), (3.0, 5.0), (6.0, 7.0)])
        self.assertIn("between(in,60,119)", expr)  # 2nd segment = frames 60..119 at 30 fps
        self.assertEqual(expr.count("between"), 1)
