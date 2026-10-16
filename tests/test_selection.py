"""
Phase 1 Self-Check: Test selection and boundary snapping on a fixed fake transcript.
Blueprint §13 Phase 1:
"One small self-check script: runs the selection logic on a fixed fake transcript and asserts the output windows."
"""

import sys
import unittest
import numpy as np
from pathlib import Path

# Add project root to path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from src.pipeline.stage7_moments import merge_candidate_sources
from src.eval import compute_iou, evaluate_video_moments


class TestMomentSelection(unittest.TestCase):

    def setUp(self):
        # Synthetic transcript: 40 seconds of speech
        # Setup starts at 15.5s after a 0.8s pause (pause between 14.7s and 15.5s)
        # Punchline is delivered at 28.0s to 31.0s
        # Host starts laughing at 31.5s, laugh run lasts until 35.0s
        self.words = [
            {"word": "Hey", "start": 10.0, "end": 10.4},
            {"word": "guys,", "start": 10.5, "end": 11.0},
            {"word": "welcome", "start": 11.1, "end": 11.5},
            {"word": "back.", "start": 11.6, "end": 12.0},  # pause 0.5s
            {"word": "So", "start": 12.5, "end": 12.8},
            {"word": "yesterday", "start": 12.9, "end": 13.5},
            {"word": "something", "start": 13.6, "end": 14.1},
            {"word": "happened.", "start": 14.2, "end": 14.7}, # PAUSE 0.8s (14.7s to 15.5s)
            {"word": "I", "start": 15.5, "end": 15.7},       # SETUP STARTS HERE
            {"word": "tried", "start": 15.8, "end": 16.1},
            {"word": "to", "start": 16.2, "end": 16.3},
            {"word": "fix", "start": 16.4, "end": 16.7},
            {"word": "the", "start": 16.8, "end": 16.9},
            {"word": "roof", "start": 17.0, "end": 17.4},
            {"word": "myself", "start": 17.5, "end": 18.0},
            {"word": "and", "start": 25.0, "end": 25.3},
            {"word": "fell", "start": 25.4, "end": 25.8},
            {"word": "straight", "start": 25.9, "end": 26.5},
            {"word": "into", "start": 26.6, "end": 27.0},
            {"word": "the", "start": 27.1, "end": 27.3},
            {"word": "pool!", "start": 27.4, "end": 28.0},   # PUNCHLINE ends at 28.0
        ]

        # Synthetic 50-second YAMNet laughter probability series
        # High laughter run from second 28 to second 34
        self.laugh_series = np.zeros(50, dtype=np.float32)
        self.laugh_series[28:35] = 0.85

    # Edge snapping moved to compute_edges (Quality v2); see tests/test_edges.py

    def test_merge_candidate_sources(self):
        """Test that signal peaks and transcript proposals merge with IoU > 0.5."""
        peaks = [
            {"clip_start": 10.0, "clip_end": 35.0, "origin": "signal"},
            {"clip_start": 60.0, "clip_end": 90.0, "origin": "signal"},
        ]
        props = [
            # High overlap with peak 1: [12.0, 34.0] vs [10.0, 35.0] -> IoU ~ 0.88
            {"clip_start": 12.0, "clip_end": 34.0, "origin": "llm_chunk"},
            # Distinct moment: [120.0, 150.0]
            {"clip_start": 120.0, "clip_end": 150.0, "origin": "llm_chunk"},
        ]

        merged = merge_candidate_sources(peaks, props)

        # Should have 3 total candidates (1 merged 'both', 1 original 'signal', 1 added 'llm_chunk')
        self.assertEqual(len(merged), 3)

        # First peak should now have origin='both'
        self.assertEqual(merged[0]["origin"], "both")
        self.assertEqual(merged[1]["origin"], "signal")
        self.assertEqual(merged[2]["origin"], "llm_chunk")

    def test_evaluation_metrics(self):
        """Test HIT@1, P@5, and NDCG@5 computation."""
        detected = [
            {"start_s": 15.0, "end_s": 35.0, "final_score": 90}, # Match GT 1
            {"start_s": 50.0, "end_s": 75.0, "final_score": 80}, # Match GT 2
            {"start_s": 100.0, "end_s": 125.0, "final_score": 70}, # No match
            {"start_s": 150.0, "end_s": 180.0, "final_score": 60}, # No match
            {"start_s": 200.0, "end_s": 220.0, "final_score": 50}, # No match
        ]
        ground_truth = [
            {"start_s": 14.0, "end_s": 36.0, "grade": 3},
            {"start_s": 52.0, "end_s": 74.0, "grade": 2},
        ]

        metrics = evaluate_video_moments(detected, ground_truth)

        # HIT@1 must be 1.0 because candidate 1 matched GT 1
        self.assertEqual(metrics["hit@1"], 1.0)
        # P@5 must be 2 / 5 = 0.40
        self.assertAlmostEqual(metrics["p@5"], 0.40, places=2)
        # NDCG@5 must be positive
        self.assertGreater(metrics["ndcg@5"], 0.5)


if __name__ == "__main__":
    unittest.main()
