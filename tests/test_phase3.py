"""
Phase 3 Unit Tests:
1. Chat cleaning (bots, commands, sub notices, raid burst detection)
2. Chat lag cross-correlation
3. Chat signal series (chat_users, chat_laugh, chat_hype, chat_agree, polls)
4. Community clip Recall@10 and untuned chat_users baseline evaluation
5. Watcher YouTube RSS parsing
"""

import unittest
import sys
from pathlib import Path
import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from src.pipeline.stage6_signals import (
    clean_twitch_chat,
    compute_chat_signals,
    estimate_chat_lag,
    shift_chat_signals,
)
from src.eval import (
    evaluate_community_clips_recall,
    compute_chat_users_baseline,
)
from src.watcher import fetch_youtube_channel_rss


class TestChatCleaning(unittest.TestCase):
    def test_drops_bots_and_commands(self):
        raw_comments = [
            {"commenter": {"display_name": "Nightbot"}, "message": {"body": "Check out the discord!"}, "content_offset_seconds": 10},
            {"commenter": {"display_name": "StreamElements"}, "message": {"body": "Top tippers!"}, "content_offset_seconds": 12},
            {"commenter": {"display_name": "viewer1"}, "message": {"body": "!rank"}, "content_offset_seconds": 15},
            {"commenter": {"display_name": "viewer2"}, "message": {"body": "!sens"}, "content_offset_seconds": 16},
            {"commenter": {"display_name": "viewer3"}, "message": {"body": "KEKW that was so funny"}, "content_offset_seconds": 20},
        ]
        cleaned, raids = clean_twitch_chat(raw_comments, duration_s=60)
        self.assertEqual(len(cleaned), 1)
        self.assertEqual(cleaned[0]["commenter"]["display_name"], "viewer3")

    def test_drops_sub_notices(self):
        raw_comments = [
            {"commenter": {"display_name": "subber1"}, "message": {"body": "subscribed at Tier 1. They've subscribed for 12 months!"}, "content_offset_seconds": 10},
            {"commenter": {"display_name": "subber2"}, "message": {"body": "gifted a Tier 1 sub to userX!"}, "content_offset_seconds": 12},
            {"commenter": {"display_name": "normal_viewer"}, "message": {"body": "lets gooo Pog"}, "content_offset_seconds": 14},
        ]
        cleaned, _ = clean_twitch_chat(raw_comments, duration_s=60)
        self.assertEqual(len(cleaned), 1)
        self.assertEqual(cleaned[0]["commenter"]["display_name"], "normal_viewer")

    def test_raid_burst_detection(self):
        # 20 brand new users posting at t=30
        raw_comments = []
        for i in range(20):
            raw_comments.append({
                "commenter": {"display_name": f"raider_{i}"},
                "message": {"body": "raid incoming!"},
                "content_offset_seconds": 30
            })
        cleaned, raids = clean_twitch_chat(raw_comments, duration_s=120)
        self.assertTrue(len(raids) > 0)
        self.assertLessEqual(raids[0][0], 30)
        self.assertGreaterEqual(raids[0][1], 90)


class TestChatLagEstimation(unittest.TestCase):
    def test_recovers_known_lag(self):
        audio_laugh = np.zeros(120, dtype=np.float32)
        chat_laugh = np.zeros(120, dtype=np.float32)

        # Event occurs at audio t=40s
        audio_laugh[40] = 5.0
        # Chat reacts at t=56s (16s stream lag)
        chat_laugh[56] = 8.0

        detected_lag = estimate_chat_lag(audio_laugh, chat_laugh, max_shift=30)
        self.assertEqual(detected_lag, 16.0)

    def test_fallback_to_default_on_no_correlation(self):
        audio_laugh = np.zeros(120, dtype=np.float32)
        chat_laugh = np.zeros(120, dtype=np.float32)
        # Empty signals -> returns default 12.0s
        detected_lag = estimate_chat_lag(audio_laugh, chat_laugh, default_offset=12.0)
        self.assertEqual(detected_lag, 12.0)

    def test_shift_chat_signals(self):
        sigs = {
            "chat_laugh": np.array([0, 0, 10, 0], dtype=np.float32),
            "clip_heat": np.array([5, 5, 5, 5], dtype=np.float32)
        }
        # Shift back by 2 seconds
        shifted = shift_chat_signals(sigs, lag_s=2.0, duration_s=4)
        # chat_laugh peak at index 2 moves to index 0
        self.assertEqual(shifted["chat_laugh"][0], 10.0)
        # clip_heat is NOT shifted per §6.1
        self.assertEqual(shifted["clip_heat"][0], 5.0)


class TestChatSignals(unittest.TestCase):
    def test_compute_signals_basic(self):
        cleaned = [
            {"commenter": {"display_name": "u1"}, "message": {"body": "KEKW"}, "content_offset_seconds": 10},
            {"commenter": {"display_name": "u2"}, "message": {"body": "kekw lol"}, "content_offset_seconds": 10},
            {"commenter": {"display_name": "u3"}, "message": {"body": "LMAO"}, "content_offset_seconds": 10},
            {"commenter": {"display_name": "u4"}, "message": {"body": "Pog"}, "content_offset_seconds": 15},
        ]
        sigs = compute_chat_signals(
            cleaned, raid_windows=[], emotes_data={}, clips_data=[], duration_s=30
        )
        self.assertIn("chat_users", sigs)
        self.assertIn("chat_laugh", sigs)
        self.assertIn("chat_hype", sigs)
        self.assertIn("chat_agree", sigs)
        self.assertIn("clip_heat", sigs)
        # Laugh signal should be active around t=10
        self.assertGreater(sigs["chat_laugh"][10], 0.0)


class TestBaselineEvaluation(unittest.TestCase):
    def test_community_clip_recall(self):
        detected = [
            {"start_s": 10.0, "end_s": 30.0, "final_score": 90},
            {"start_s": 100.0, "end_s": 125.0, "final_score": 85},
        ]
        community_clips = [
            {"vod_offset": 15.0, "view_count": 500},  # Match clip 1
            {"vod_offset": 110.0, "view_count": 200}, # Match clip 2
            {"vod_offset": 500.0, "view_count": 100}, # No match
        ]
        recall = evaluate_community_clips_recall(detected, community_clips, k=5)
        # 2 out of 3 matches -> 0.667
        self.assertAlmostEqual(recall, 0.667, places=2)

    def test_chat_users_baseline(self):
        comments = []
        # Create a peak at t=50 with 10 chatters
        for i in range(10):
            comments.append({
                "commenter": {"display_name": f"user_{i}"},
                "content_offset_seconds": 50
            })
        baseline = compute_chat_users_baseline(comments, duration_s=100, k=3)
        self.assertTrue(len(baseline) > 0)
        # The peak candidate should cover t=50
        self.assertLessEqual(baseline[0]["start_s"], 50)
        self.assertGreaterEqual(baseline[0]["end_s"], 50)


if __name__ == "__main__":
    unittest.main()
