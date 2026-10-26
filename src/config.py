"""
Spike: Central configuration and default settings.
"""

import os
from pathlib import Path
from dotenv import load_dotenv

# Base paths
ROOT_DIR = Path(__file__).resolve().parent.parent
DATA_DIR = ROOT_DIR / "data"
VIDEOS_DIR = DATA_DIR / "videos"
UPLOADS_DIR = DATA_DIR / "uploads"
BACKUPS_DIR = DATA_DIR / "backups"
DB_PATH = DATA_DIR / "spike.db"
# Outreach lead data is personal data (UU PDP), so it lives in its own file (OUTREACH.md §6.1)
OUTREACH_DB_PATH = DATA_DIR / "outreach.db"

# Ensure data directories exist
DATA_DIR.mkdir(exist_ok=True)
VIDEOS_DIR.mkdir(exist_ok=True)
UPLOADS_DIR.mkdir(exist_ok=True)
BACKUPS_DIR.mkdir(exist_ok=True)

# Load environment variables
load_dotenv(ROOT_DIR / ".env")

# API Keys & Webhooks
# One key per Google account, comma separated (GEMINI_API_KEY=key1,key2): each account has its own free daily quota.
GEMINI_API_KEY = os.environ.get("GEMINI_API_KEY", "")


def gemini_keys() -> list:
    return [k.strip() for k in GEMINI_API_KEY.split(",") if k.strip()]


# Comma separated like GEMINI_API_KEY. YouTube quota is per Google Cloud project, so extra keys only help when
# each is from its own project. Outreach moves to the next key when one's daily quota is used up; the rest of
# Spike uses the first.
YOUTUBE_API_KEY = os.environ.get("YOUTUBE_API_KEY", "")


def youtube_keys() -> list:
    return [k.strip() for k in YOUTUBE_API_KEY.split(",") if k.strip()]


TWITCH_CLIENT_ID = os.environ.get("TWITCH_CLIENT_ID", "")
TWITCH_CLIENT_SECRET = os.environ.get("TWITCH_CLIENT_SECRET", "")
DISCORD_WEBHOOK_URL = os.environ.get("DISCORD_WEBHOOK_URL", "")
# Google OAuth client (Web application type) for Outreach Gmail + Drive. Redirect URI: <SPIKE_PUBLIC_URL>/outreach/google/callback
GOOGLE_OAUTH_CLIENT_ID = os.environ.get("GOOGLE_OAUTH_CLIENT_ID", "")
GOOGLE_OAUTH_CLIENT_SECRET = os.environ.get("GOOGLE_OAUTH_CLIENT_SECRET", "")

# Web & Security settings (Blueprint §4, §8, §13)
WEB_HOST = os.environ.get("SPIKE_HOST", "127.0.0.1")
WEB_PORT = int(os.environ.get("SPIKE_PORT", "8000"))
# Address team members open in links (Discord). Set to the Tailscale URL, e.g. https://spike-pc.tailnet-name.ts.net
PUBLIC_URL = os.environ.get("SPIKE_PUBLIC_URL", f"http://{WEB_HOST}:{WEB_PORT}").rstrip("/")
MAX_UPLOAD_SIZE_BYTES = 2 * 1024 * 1024 * 1024  # 2 GB cap
ALLOWED_UPLOAD_EXTS = {".mp4", ".mov", ".mkv", ".webm", ".m4a", ".mp3", ".wav"}
ALLOWED_URL_DOMAINS = {"twitch.tv", "www.twitch.tv", "youtube.com", "www.youtube.com", "youtu.be"}

# LLM Models
# gemini-3.1-flash-lite is the fast default that supports YouTube URLs + VideoMetadata on free tier
DEFAULT_GEMINI_MODEL = os.environ.get("SPIKE_GEMINI_MODEL", "gemini-3.1-flash-lite")
FALLBACK_GEMINI_MODEL = "gemini-3.8-flash"
# Per-candidate judge and pairwise re-rank use Flash; Flash-Lite is only for the chunk scanner and session profile (§6.7)
JUDGE_GEMINI_MODEL = os.environ.get("SPIKE_JUDGE_MODEL", FALLBACK_GEMINI_MODEL)
# The "auto" framing layout runs on Flash-Lite: the judge's Flash quota is tiny (it ran out after 16 requests on
# 2026-10-15) and layout calls must not eat it. Set SPIKE_LAYOUT_MODEL=<flash model> to compare quality.
LAYOUT_GEMINI_MODEL = os.environ.get("SPIKE_LAYOUT_MODEL", DEFAULT_GEMINI_MODEL)
# Gemini does not report remaining quota, so Spike counts its own requests per model (src/gemini_budget.py)
# against this hardcoded daily limit. At 0 for the layout model, "auto" falls back to the face-size heuristic
# until the day resets. A guess: set it just under your key's real per-model daily limit.
GEMINI_DAILY_LIMIT = int(os.environ.get("SPIKE_GEMINI_DAILY_LIMIT", "250"))
# Per-model overrides. Flash returned 429 after 16 counted requests, so its real daily limit is at most about that.
GEMINI_DAILY_LIMITS = {JUDGE_GEMINI_MODEL: 15}

# Whisper ASR
DEFAULT_WHISPER_MODEL = os.environ.get("WHISPER_MODEL", "small")
WHISPER_COMPUTE_TYPE = "int8"
WHISPER_DEVICE = "cpu"

# YAMNet Paths
YAMNet_MODEL_PATH = ROOT_DIR / "phase0" / "yamnet.tflite"
YAMNet_CLASSMAP_PATH = ROOT_DIR / "phase0" / "yamnet_class_map.csv"

# Pipeline & Moment Detection Constraints (Blueprint §6, §11)
MAX_VIDEO_DURATION_S = 12 * 3600  # 12 hours max
MIN_CLIP_DURATION_S = 12.0        # seconds
MAX_CLIP_DURATION_S = 60.0        # seconds
DEFAULT_TARGET_CLIPS_PER_HOUR = 2
MAX_TARGET_CLIPS = 15
# Days a clip may sit ready/approved before its section source (needed for re-renders) is deleted
SECTION_RETENTION_DAYS = int(os.environ.get("SPIKE_SECTION_RETENTION_DAYS", "7"))

# Signal Weights without chat (§6.1)
# Quality v2 (§6.7): audio_loud is kept as a signal but replaced in the fusion by voice_jump
WEIGHTS_WITHOUT_CHAT = {
    "laugh": 0.20,
    "voice_jump": 0.20,
    "rage_words": 0.15,
    "shout": 0.15,
    "replay_heat": 0.15,
    "comment_heat": 0.10,
    "speech_rate": 0.05,
}

# Signal Weights with chat (§6.1)
WEIGHTS_WITH_CHAT = {
    "chat_users": 0.10,
    "voice_jump": 0.05,
    "rage_words": 0.05,
    "chat_laugh": 0.20,
    "clip_heat": 0.20,
    "laugh": 0.15,
    "chat_hype": 0.05,
    "chat_agree": 0.05,
    "audio_loud": 0.05,
    "shout": 0.05,
    "speech_rate": 0.05,
}

# Rage and shock words counted per second by the rage_words signal (§6.7); per-source terms are added
RAGE_WORDS = {
    "no", "bro", "what", "how", "why", "fuck", "fucking", "shit", "ref", "wtf", "bruh",
    "nah", "stop", "cheating", "scam", "rigged", "are you serious", "oh my god",
}

# A second counts as laughter/shouting/voice jump when it is in the VOD's top share (§6.7)
RELATIVE_TOP_PCT = 2.0

# Creator presets (§6.7). The AI picks creator_type; it never writes these numbers.
# weight_mult multiplies the stage 6 signal weights and stays within 0.5 to 2.
CREATOR_TYPES = ("gaming", "irl", "just_chatting", "podcast", "comedy", "reaction", "sports", "educational", "other")
HUMOR_STYLES = ("rage", "hubris", "roast", "banter", "storytelling", "absurd", "cringe", "wholesome", "deadpan")
CREATOR_PRESETS = {
    "gaming": {"min_len": 12, "max_len": 40, "setup_pad_s": 3, "end_extend_max_s": 8,
               "weight_mult": {"voice_jump": 1.5, "rage_words": 1.5}, "zoom_scale": 1.20},
    "irl": {"min_len": 15, "max_len": 45, "setup_pad_s": 4, "end_extend_max_s": 5,
            "weight_mult": {"voice_jump": 1.2, "laugh": 1.2}, "zoom_scale": 1.15},
    "just_chatting": {"min_len": 15, "max_len": 50, "setup_pad_s": 6, "end_extend_max_s": 5,
                      "weight_mult": {"laugh": 1.3, "rage_words": 0.8}, "zoom_scale": 1.15},
    "podcast": {"min_len": 20, "max_len": 90, "setup_pad_s": 8, "end_extend_max_s": 3,
                "weight_mult": {"laugh": 1.5, "voice_jump": 0.7}, "zoom_scale": 1.10},
    "comedy": {"min_len": 15, "max_len": 60, "setup_pad_s": 6, "end_extend_max_s": 4,
               "weight_mult": {"laugh": 1.5}, "zoom_scale": 1.15},
    "reaction": {"min_len": 12, "max_len": 45, "setup_pad_s": 4, "end_extend_max_s": 5,
                 "weight_mult": {"laugh": 1.3, "shout": 1.2}, "zoom_scale": 1.20},
    "sports": {"min_len": 12, "max_len": 40, "setup_pad_s": 3, "end_extend_max_s": 6,
               "weight_mult": {"voice_jump": 1.4, "shout": 1.3}, "zoom_scale": 1.20},
    "educational": {"min_len": 20, "max_len": 75, "setup_pad_s": 8, "end_extend_max_s": 3,
                    "weight_mult": {"laugh": 1.2, "voice_jump": 0.7, "rage_words": 0.5}, "zoom_scale": 1.10},
    "other": {"min_len": 12, "max_len": 60, "setup_pad_s": 5, "end_extend_max_s": 4,
              "weight_mult": {}, "zoom_scale": 1.15},
}

# Blend weights (§6.4)
LLM_WEIGHT_WITHOUT_CHAT = 0.70
LLM_WEIGHT_WITH_CHAT = 0.30  # 0.5 ranked worse on the 9-VOD eval set; chat activity carries more of the order
MIN_RAW_LLM_SCORE = 65.0  # Floor to prevent dull VODs from passing
AUTO_POST_MIN_LLM_SCORE = 70.0

# ─── Phase 2: Vertical edit settings (Blueprint §7) ────────────────────────
# Output format
OUTPUT_WIDTH = 1080
OUTPUT_HEIGHT = 1920
OUTPUT_FPS = 30
OUTPUT_VIDEO_CODEC = "libx264"
OUTPUT_VIDEO_PRESET = "veryfast"
OUTPUT_VIDEO_CRF = 18
OUTPUT_AUDIO_CODEC = "aac"
OUTPUT_AUDIO_BITRATE = "160k"
OUTPUT_LOUDNESS_TARGET = -14.0   # LUFS (loudnorm two-pass)
OUTPUT_LOUDNESS_PEAK = -1.5      # dBTP true peak

# MediaPipe face tracking
FACE_DETECT_FPS = 4              # Sample face positions at 4 fps
FACE_TRACK_EMA_ALPHA = 0.12      # Exponential moving average smoothing (lower = smoother)

# Layouts (§7.1)
# face_track: follow largest face; split: facecam top + gameplay below;
# center: center crop; letterbox: full frame + blurred bg;
# auto: split when a small, fixed facecam overlay is found, else face_track
VALID_LAYOUTS = ("auto", "face_track", "split", "center", "letterbox")
DEFAULT_LAYOUT = "auto"

# Split layout: streamer on top half, content on bottom half; captions sit on the seam
SPLIT_FACECAM_H = 960
SPLIT_GAMEPLAY_H = 960
# auto layout picks split when the steady face is narrower than this share of frame width
FACECAM_OVERLAY_MAX_FACE_W = 0.12

# Punch-in zoom (§7.4)
ZOOM_FACTOR = 1.15        # strength of the default zoom when a clip has no zoom list yet
ZOOM_IN_DURATION = 0.2    # seconds
ZOOM_OUT_DURATION = 0.5   # seconds
ZOOM_MAX = 1.5            # overlapping pulses never zoom past this

# Hook title (§7.4): shown for first 2.5 s at top of frame
HOOK_DURATION_S = 2.5

# Internal silence trim threshold (§7.4, optional per-source)
SILENCE_TRIM_S = 1.2
SILENCE_TRIM_BREATH_S = 0.4  # Natural breath duration retained when trimming pauses
# "tight" pace: cut every pause longer than this, keep a shorter breath (jump-cut style)
SILENCE_TRIM_TIGHT_S = 0.6
SILENCE_TRIM_TIGHT_BREATH_S = 0.2
JUMP_CUT_ZOOM = 1.08  # alternate segments are zoomed by this to hide jump cuts

# Music folder & ducking (§7.3)
MUSIC_DIR = ROOT_DIR / "music"
MUSIC_MOODS = ("hype", "funny", "chill", "dramatic", "wholesome")
MUSIC_UNDER_DB = -22.0    # dB below speech baseline
MUSIC_DUCK_THRESHOLD = 0.03  # detection threshold for speech sidechain
MUSIC_DUCK_RATIO = 5.0       # compression ratio when speech active
MUSIC_DUCK_ATTACK_MS = 15    # fast attack
MUSIC_DUCK_RELEASE_MS = 250  # smooth release back to baseline

# ─── Phase 3: Streams, Chat & Watcher Settings (Blueprint §5, §6.1, §13) ────
TOOLS_DIR = ROOT_DIR / "tools"
TWITCH_DOWNLOADER_PATH = TOOLS_DIR / "TwitchDownloaderCLI.exe"

# Bot accounts to drop during chat cleaning (§6.1)
CHAT_BOT_NAMES = {
    "nightbot", "streamelements", "moobot", "fossabot",
    "soundalerts", "streamlabs", "wizebot", "stay_hydrated_bot",
    # YouTube chat display names keep the "@" handle prefix
    "@nightbot", "@streamelements", "@moobot", "@fossabot", "@streamlabs",
}

# Chat token dictionaries (§6.1)
CHAT_LAUGH_TOKENS = {
    "lul", "lulw", "kekw", "kekl", "omegalul", "icant", "pepelaugh",
    "lol", "lmao", "lmfao", "xd", "💀", "😂", "jaja", "kkkk", "rsrs",
    "555", "ㅋㅋㅋ", "www", "wkwk", "rofl", "dead",
    "🤣", ":face-with-tears-of-joy:", ":rolling-on-the-floor-laughing:",
}

CHAT_HYPE_TOKENS = {
    "pog", "pogchamp", "poggers", "w", "ez", "clap", "no way", "letsgo",
    "hype", "sheesh", "insane", "holy", "goat", "clutch", "fire", "🔥",
}

CHAT_CONFUSION_TOKENS = {
    "?", "???", "wutface", "monkas", "huh", "what", "monkaw", "wait", "sus",
}

CHAT_SAD_TOKENS = {
    "sadge", "f", "o7", "rip", "biblethump", "pepehands", "feelsbadman",
}

# Chat lag estimation (§6.1)
DEFAULT_CHAT_OFFSET_S = 12.0
MAX_LAG_SEARCH_S = 30
RAID_SILENCE_WINDOW_S = 60

# Watcher polling interval in minutes (§5)
WATCHER_INTERVAL_MINUTES = 15


# Optional Claude Pro caps, in tokens, so the Jobs page can show a percentage of Spike's own usage. Anthropic does not
# publish these. Calibrate: note Spike's token count, then check `/usage` in a claude terminal and divide.
CLAUDE_5H_TOKEN_CAP = int(os.environ.get("SPIKE_CLAUDE_5H_TOKEN_CAP", "0"))
CLAUDE_WEEK_TOKEN_CAP = int(os.environ.get("SPIKE_CLAUDE_WEEK_TOKEN_CAP", "0"))
