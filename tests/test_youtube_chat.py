"""YouTube live chat replay lines convert to the Twitch comment shape stage 6/7 read."""

import json
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from src.pipeline.stage3_chat import convert_youtube_live_chat


def _line(offset_ms, author, runs):
    return json.dumps({"replayChatItemAction": {
        "videoOffsetTimeMsec": str(offset_ms),
        "actions": [{"addChatItemAction": {"item": {"liveChatTextMessageRenderer": {
            "authorName": {"simpleText": author},
            "message": {"runs": runs},
        }}}}],
    }})


class TestConvertYoutubeLiveChat(unittest.TestCase):
    def test_converts_text_and_emoji(self):
        lines = [
            _line(12345, "@alice", [{"text": "no way"}, {"emoji": {"emojiId": "😂", "shortcuts": [":joy:"]}}]),
            _line(20000, "@bob", [{"emoji": {"emojiId": "UC/x", "shortcuts": [":_hololiveLaugh:"], "isCustomEmoji": True}}]),
            "",
            # Non-message actions (super chat tickers, membership notices) are dropped
            json.dumps({"replayChatItemAction": {"videoOffsetTimeMsec": "1", "actions": [{"addLiveChatTickerItemAction": {}}]}}),
        ]
        out = convert_youtube_live_chat(lines)
        self.assertEqual(len(out), 2)
        self.assertEqual(out[0], {
            "content_offset_seconds": 12.345,
            "commenter": {"display_name": "@alice"},
            "message": {"body": "no way 😂"},
        })
        self.assertEqual(out[1]["message"]["body"], ":_hololiveLaugh:")


if __name__ == "__main__":
    unittest.main()
