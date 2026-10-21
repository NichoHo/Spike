"""
Phase 0: Verify Gemini and YouTube Data API Keys

Tests:
1. Loads GEMINI_API_KEY from .env and verifies generate_content works.
2. Tests Gemini with a YouTube URL using start_offset and end_offset (Phase 0 check).
3. Loads YOUTUBE_API_KEY from .env and tests commentThreads.list for a public video.

Never prints or logs the raw API keys.
"""

import os
import sys
from dotenv import load_dotenv

# Reconfigure stdout for UTF-8
try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
except Exception:
    pass

load_dotenv()

TEST_YT_VIDEO_ID = "D1hIpF1C_r4"
TEST_YT_URL = f"https://www.youtube.com/watch?v={TEST_YT_VIDEO_ID}"


def test_gemini():
    print("\n--- 1. Testing Gemini API Key ---", flush=True)
    api_key = os.environ.get("GEMINI_API_KEY", "").split(",")[0].strip()  # first of the comma separated keys
    if not api_key:
        print("  FAIL: GEMINI_API_KEY is not set in .env", flush=True)
        return False

    print(f"  Key detected: length {len(api_key)}, starts with {api_key[:6]}...", flush=True)

    try:
        from google import genai
        from google.genai import types

        client = genai.Client(api_key=api_key)

        # Basic text test
        print("  Calling gemini-3.1-flash-lite with basic prompt...", flush=True)
        resp = client.models.generate_content(
            model="gemini-3.1-flash-lite",
            contents="Say 'Gemini API is working!' and nothing else."
        )
        print(f"  Gemini Response: {resp.text.strip()}", flush=True)
        print("  Basic text generation: PASS", flush=True)

        # YouTube URL test with start/end offset (Phase 0 verification)
        print("\n--- 2. Testing Gemini YouTube URL + VideoMetadata (Phase 0 Check) ---", flush=True)
        print(f"  Target URL: {TEST_YT_URL}", flush=True)
        print("  Passing window 10s to 25s via VideoMetadata...", flush=True)

        yt_content = types.Content(
            parts=[
                types.Part(
                    file_data=types.FileData(
                        file_uri=TEST_YT_URL,
                        mime_type="video/mp4"
                    ),
                    video_metadata=types.VideoMetadata(
                        start_offset="10s",
                        end_offset="25s"
                    )
                ),
                types.Part(text="Briefly describe what is happening in this clip in 1 sentence.")
            ]
        )

        yt_resp = client.models.generate_content(
            model="gemini-3.1-flash-lite",
            contents=[yt_content]
        )
        print(f"  Gemini Video Response: {yt_resp.text.strip()}", flush=True)
        print("  YouTube URL + offset processing: PASS", flush=True)
        return True

    except Exception as e:
        print(f"  Gemini test FAILED: {e}", flush=True)
        return False


def test_youtube():
    print("\n--- 3. Testing YouTube Data API Key ---", flush=True)
    api_key = os.environ.get("YOUTUBE_API_KEY")
    if not api_key:
        print("  FAIL: YOUTUBE_API_KEY is not set in .env", flush=True)
        return False

    print(f"  Key detected: length {len(api_key)}, starts with {api_key[:6]}...", flush=True)

    import urllib.request
    import urllib.parse
    import json

    params = {
        "part": "snippet",
        "videoId": TEST_YT_VIDEO_ID,
        "maxResults": 3,
        "key": api_key,
        "textFormat": "plainText",
    }
    url = f"https://www.googleapis.com/youtube/v3/commentThreads?{urllib.parse.urlencode(params)}"

    print(f"  Requesting commentThreads.list for video {TEST_YT_VIDEO_ID}...", flush=True)
    try:
        req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
        with urllib.request.urlopen(req) as resp:
            data = json.loads(resp.read().decode())

        items = data.get("items", [])
        print(f"  Successfully fetched {len(items)} comment threads!", flush=True)
        if items:
            top_comment = items[0]["snippet"]["topLevelComment"]["snippet"]["textDisplay"]
            print(f"  Sample comment: {top_comment[:80]}...", flush=True)
        print("  YouTube Data API: PASS", flush=True)
        return True

    except urllib.error.HTTPError as e:
        err_body = e.read().decode()
        print(f"  HTTP Error {e.code}: {err_body}", flush=True)
        return False
    except Exception as e:
        print(f"  YouTube API test FAILED: {e}", flush=True)
        return False


def main():
    print("========================================")
    print("  Phase 0 API Credentials Verification  ")
    print("========================================")

    gemini_ok = test_gemini()
    youtube_ok = test_youtube()

    print("\n========================================")
    print(f"  Gemini API:       {'✅ PASSED' if gemini_ok else '❌ FAILED'}")
    print(f"  YouTube Data API: {'✅ PASSED' if youtube_ok else '❌ FAILED'}")
    print("========================================")


if __name__ == "__main__":
    main()
