"""
Phase 0: Inspect a TwitchDownloaderCLI chat replay JSON.

Checks:
  1. msg_id values present (for sub/raid detection)
  2. Whether raid and sub lines appear
  3. Precision of content_offset_seconds
  4. Whether 7TV emote names appear in message text
  5. user_notice_params.msg_id field presence

Usage:
  py phase0/inspect_chat_replay.py <chat.json>

Get a chat replay with:
  TwitchDownloaderCLI chatdownload --id <VOD_ID> -o phase0/sample_chat.json
"""

import sys
import json
from pathlib import Path
from collections import Counter


def inspect_chat(path: str):
    print(f"Loading {path}...")
    with open(path, encoding="utf-8") as f:
        data = json.load(f)

    comments = data.get("comments", [])
    print(f"Total comments: {len(comments)}")

    if not comments:
        print("ERROR: No comments found in file.")
        return

    # Sample a few
    print(f"\nFirst comment keys: {list(comments[0].keys())}")
    print(f"First comment message keys: {list(comments[0].get('message', {}).keys())}")

    # 1. content_offset_seconds precision
    offsets = [c.get("content_offset_seconds", 0) for c in comments[:100]]
    is_float = any(isinstance(o, float) and o != int(o) for o in offsets)
    print(f"\n1. content_offset_seconds: {'float (sub-second precision)' if is_float else 'integer (whole seconds)'}")
    print(f"   Sample offsets: {offsets[:5]}")

    # 2. user_notice_params.msg_id
    msg_ids = []
    for c in comments:
        unp = c.get("message", {}).get("user_notice_params", {})
        mid = unp.get("msg-id") or unp.get("msg_id")
        if mid:
            msg_ids.append(mid)

    print(f"\n2. user_notice_params.msg_id: {len(msg_ids)} messages have it")
    if msg_ids:
        counts = Counter(msg_ids)
        print(f"   msg_id values: {dict(counts.most_common(10))}")
    else:
        print("   Field is absent or null in all messages")

    # 3. Raid detection (burst of new users)
    # Look for messages with "is raiding" or "raid" in system context
    raid_hints = []
    for c in comments:
        body = c.get("message", {}).get("body", "")
        if "raid" in body.lower():
            raid_hints.append(body[:80])
    print(f"\n3. 'raid' in message body: {len(raid_hints)} messages")
    for r in raid_hints[:3]:
        print(f"   {r!r}")

    # 4. Sub-related messages (bits_spent, sub notices)
    bits_messages = [c for c in comments if c.get("message", {}).get("bits_spent", 0) > 0]
    print(f"\n4. messages with bits_spent > 0: {len(bits_messages)}")

    # 5. Emote fragments
    all_emotes = []
    for c in comments:
        for frag in c.get("message", {}).get("fragments", []):
            if frag.get("emoticon"):
                all_emotes.append(frag.get("emoticon", {}).get("emoticon_id", "unknown"))
    print(f"\n5. Total emote fragments across all messages: {len(all_emotes)}")
    if all_emotes:
        print(f"   Top emote IDs: {Counter(all_emotes).most_common(10)}")

    # 6. 7TV emote names — check if names in text match known 7TV style (no spaces)
    # 7TV emotes appear as plain text tokens (no emoticon fragment)
    # Check a sample of words for common 7TV emotes
    KNOWN_7TV = {"KEKW", "KEKL", "ICANT", "PauseChamp", "Pog", "POGGERS", "FeelsOkayMan",
                 "5Head", "monkaW", "OMEGALUL", "Clap", "pepeLaugh", "catJAM", "FeelsDankMan"}
    seven_tv_found = Counter()
    for c in comments[:2000]:  # check first 2000
        body = c.get("message", {}).get("body", "")
        for token in body.split():
            if token in KNOWN_7TV:
                seven_tv_found[token] += 1

    print(f"\n6. Known 7TV emote tokens found in first 2000 messages: {dict(seven_tv_found.most_common(10))}")

    # 7. user_badges
    badge_types = Counter()
    for c in comments[:500]:
        for badge in c.get("message", {}).get("user_badges", []):
            badge_types[badge.get("_id", "?")] += 1
    print(f"\n7. Badge types in first 500 messages: {dict(badge_types.most_common(10))}")

    # Summary
    print("\n=== SUMMARY FOR §16 ===")
    print(f"  content_offset_seconds: {'float with sub-second precision' if is_float else 'integer, whole seconds only'}")
    print(f"  user_notice_params.msg_id: {'PRESENT' if msg_ids else 'ABSENT / NULL'}")
    print(f"  Raid messages in body: {len(raid_hints)}")
    print(f"  Bits spent messages: {len(bits_messages)}")
    print(f"  Emote fragments: {len(all_emotes)}")
    print(f"  7TV emotes in text: {sum(seven_tv_found.values())} occurrences")


if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("Usage: py phase0/inspect_chat_replay.py <chat.json>")
        print("\nGet a chat replay with:")
        print("  TwitchDownloaderCLI chatdownload --id <VOD_ID> -o phase0/sample_chat.json")
        sys.exit(1)

    path = sys.argv[1]
    if not Path(path).exists():
        print(f"Error: {path} not found")
        sys.exit(1)

    inspect_chat(path)
