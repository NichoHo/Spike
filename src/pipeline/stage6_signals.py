"""
Stage 6: signals
Blueprint §6.1 & §6.2:
Compute per-second signal series:
- laugh & shout (YAMNet tflite with laughter gate)
- audio_loud (per-second RMS dBFS), voice_jump (loudness above rolling median), rage_words
- speech_rate (words/sec smoothed over 5s)
- replay_heat (yt-dlp heatmap)
- comment_heat (YouTube comments with laugh weighting)
- chat signals (Twitch chat replay):
  - chat_users (unique chatters per second, rolling median z-score)
  - chat_laugh (share of chatters posting laugh tokens, add-k shrunk)
  - chat_hype (share of chatters posting hype tokens)
  - chat_agree (emote walls & common message agreement)
  - clip_heat (community clips coverage and view weighting)
  - chat cleaning (bots, commands, sub notices, polls, raid silence)
  - per-VOD chat lag estimation via audio-chat cross-correlation
Fuses signals into hype(t), normalizes with robust z-score, and picks peaks via scipy.
Output: data/videos/<id>/signals.npz and data/videos/<id>/signal_peaks.json
"""

import csv
import json
import os
import re
import subprocess
import tempfile
from pathlib import Path
from typing import Dict, Any, List, Tuple, Optional, Set
import numpy as np
from scipy.signal import find_peaks

from src.config import (
    YAMNet_MODEL_PATH,
    YAMNet_CLASSMAP_PATH,
    WEIGHTS_WITHOUT_CHAT,
    WEIGHTS_WITH_CHAT,
    DEFAULT_TARGET_CLIPS_PER_HOUR,
    MAX_TARGET_CLIPS,
    RAGE_WORDS,
    RELATIVE_TOP_PCT,
    CHAT_BOT_NAMES,
    CHAT_LAUGH_TOKENS,
    CHAT_HYPE_TOKENS,
    CHAT_CONFUSION_TOKENS,
    CHAT_SAD_TOKENS,
    DEFAULT_CHAT_OFFSET_S,
    MAX_LAG_SEARCH_S,
    RAID_SILENCE_WINDOW_S,
)


def load_yamnet_classmap() -> Tuple[List[int], List[int]]:
    """Get indices for laugh and shout classes from class map CSV."""
    laugh_indices = []
    shout_indices = []
    laugh_names = {"laughter", "giggle", "snicker", "belly laugh", "chuckle, chortle"}
    shout_names = {"shout", "whoop", "yell", "screaming"}

    with open(YAMNet_CLASSMAP_PATH, "r", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        for row in reader:
            idx = int(row["index"])
            name = row["display_name"].lower()
            if any(ln in name for ln in laugh_names):
                laugh_indices.append(idx)
            if any(sn in name for sn in shout_names):
                shout_indices.append(idx)

    return laugh_indices, shout_indices


def compute_yamnet_series(audio_path: Path, duration_s: int) -> Tuple[np.ndarray, np.ndarray, np.ndarray]:
    """Run YAMNet tflite inference; return per-second laugh, shout and loudness (dBFS) series."""
    import tensorflow as tf

    laugh_idxs, shout_idxs = load_yamnet_classmap()

    # Convert audio to 16 kHz mono WAV in temp file
    with tempfile.NamedTemporaryFile(suffix=".wav", delete=False) as tmp:
        tmp_wav = tmp.name

    try:
        cmd = [
            "ffmpeg", "-y", "-v", "error",
            "-i", str(audio_path),
            "-ac", "1",
            "-ar", "16000",
            tmp_wav
        ]
        subprocess.run(cmd, check=True)

        audio_raw = tf.io.read_file(tmp_wav)
        waveform, _ = tf.audio.decode_wav(audio_raw, desired_channels=1)
        waveform = tf.squeeze(waveform, axis=-1).numpy()
    finally:
        if os.path.exists(tmp_wav):
            try:
                os.remove(tmp_wav)
            except Exception:
                pass

    interpreter = tf.lite.Interpreter(model_path=str(YAMNet_MODEL_PATH))
    interpreter.allocate_tensors()
    input_details = interpreter.get_input_details()
    output_details = interpreter.get_output_details()

    window_size = 15600  # 0.975s at 16kHz
    hop_size = 7680     # 0.48s
    n_frames = (len(waveform) - window_size) // hop_size + 1

    laugh_max_per_sec = np.zeros(duration_s, dtype=np.float32)
    shout_max_per_sec = np.zeros(duration_s, dtype=np.float32)

    for i in range(n_frames):
        start = i * hop_size
        patch = waveform[start:start + window_size]
        if len(patch) < window_size:
            break
        interpreter.set_tensor(input_details[0]['index'], patch.astype(np.float32))
        interpreter.invoke()
        scores = interpreter.get_tensor(output_details[0]['index'])[0]

        t_sec = int(i * hop_size / 16000)
        if t_sec < duration_s:
            l_prob = max(scores[idx] for idx in laugh_idxs)
            s_prob = max(scores[idx] for idx in shout_idxs)
            if l_prob > laugh_max_per_sec[t_sec]:
                laugh_max_per_sec[t_sec] = l_prob
            if s_prob > shout_max_per_sec[t_sec]:
                shout_max_per_sec[t_sec] = s_prob

    return laugh_max_per_sec, shout_max_per_sec, rms_db_per_second(waveform, duration_s)


def relative_threshold(series: np.ndarray, top_pct: float = RELATIVE_TOP_PCT, floor: float = 0.05) -> float:
    """Value a second must reach to be in this video's top `top_pct` percent (§6.7)."""
    if len(series) == 0:
        return floor
    return max(float(np.percentile(series, 100.0 - top_pct)), floor)


def apply_laughter_gate(raw_laugh: np.ndarray, words: List[Dict[str, Any]]) -> np.ndarray:
    """
    Laughter counts only when the second is in the video's top 2% for laugh probability
    and transcript words fall within 3s of it (drops canned meme laughs played over silence).
    """
    gated = np.zeros_like(raw_laugh)
    word_times = np.array([w.get("start", 0.0) for w in words])
    threshold = relative_threshold(raw_laugh)

    for t in np.nonzero(raw_laugh >= threshold)[0]:
        if len(word_times) == 0 or np.any(np.abs(word_times - t) <= 3.0):
            gated[t] = raw_laugh[t]

    return gated


def rms_db_per_second(waveform: np.ndarray, duration_s: int, sr: int = 16000) -> np.ndarray:
    """Per-second RMS loudness in dBFS from a mono waveform. Silence reads -90."""
    out = np.full(duration_s, -90.0, dtype=np.float32)
    for sec in range(min(duration_s, len(waveform) // sr + 1)):
        chunk = waveform[sec * sr:(sec + 1) * sr]
        if len(chunk):
            rms = float(np.sqrt(np.mean(np.square(chunk, dtype=np.float64))))
            out[sec] = max(-90.0, 20.0 * np.log10(rms + 1e-9))
    return out


def compute_voice_jump(loudness_db: np.ndarray, window_s: int = 30) -> np.ndarray:
    """Loudness minus its rolling median, clipped at 0. A sudden +10 dB is a scream or rage burst."""
    n = len(loudness_db)
    out = np.zeros(n, dtype=np.float32)
    half = window_s // 2
    for t in range(n):
        med = np.median(loudness_db[max(0, t - half):min(n, t + half + 1)])
        out[t] = max(0.0, float(loudness_db[t]) - med)
    return out


def compute_rage_words(words: List[Dict[str, Any]], duration_s: int, extra_terms: Optional[Set[str]] = None) -> np.ndarray:
    """Per-second count of rage and shock words from word timestamps, smoothed over 5s."""
    terms = {t.lower() for t in RAGE_WORDS} | {t.lower() for t in (extra_terms or set())}
    toks = [(re.sub(r"[^\w']", "", w.get("word", "").lower()), w.get("start", 0.0)) for w in words]
    counts = np.zeros(duration_s, dtype=np.float32)
    for i, (tok, start) in enumerate(toks):
        hit = tok in terms
        for n in (2, 3):  # multi-word terms such as "are you serious"
            if not hit and i + n <= len(toks):
                hit = " ".join(t for t, _ in toks[i:i + n]) in terms
        sec = int(start)
        if hit and 0 <= sec < duration_s:
            counts[sec] += 1.0
    return np.convolve(counts, np.ones(5) / 5.0, mode="same").astype(np.float32)


def compute_speech_rate(words: List[Dict[str, Any]], duration_s: int) -> np.ndarray:
    """Compute words per second, smoothed over 5s."""
    counts = np.zeros(duration_s, dtype=np.float32)
    for w in words:
        sec = int(w.get("start", 0.0))
        if 0 <= sec < duration_s:
            counts[sec] += 1.0

    kernel = np.ones(5) / 5.0
    smoothed = np.convolve(counts, kernel, mode="same")
    return smoothed.astype(np.float32)


def compute_replay_heat(meta: Dict[str, Any], duration_s: int) -> np.ndarray:
    """Extract YouTube heatmap from meta.json, held flat across bins, zeroed first 60s."""
    heat = np.zeros(duration_s, dtype=np.float32)
    raw_bins = meta.get("heatmap")
    if not raw_bins:
        return heat

    for b in raw_bins:
        st = int(b.get("start_time", 0.0))
        et = int(b.get("end_time", 0.0))
        val = float(b.get("value", 0.0))
        for t in range(st, min(duration_s, et)):
            heat[t] = val

    if duration_s > 60:
        heat[:60] = 0.0

    return heat


def compute_comment_heat(comments: List[Dict[str, Any]], duration_s: int) -> np.ndarray:
    """Compute comment heat: timestamp counts, weight 2 for laugh terms, smoothed over 5s."""
    heat = np.zeros(duration_s, dtype=np.float32)
    for c in comments:
        w = 2.0 if c.get("is_laugh") else 1.0
        for ts in c.get("timestamps", []):
            sec = int(ts)
            if 0 <= sec < duration_s:
                heat[sec] += w

    kernel = np.ones(5) / 5.0
    smoothed = np.convolve(heat, kernel, mode="same")
    return smoothed.astype(np.float32)


# ─── Chat Cleaning & Signals Engine (Blueprint §6.1) ─────────────────────────

SUB_PATTERNS = re.compile(
    r'\b(subscribed at tier|gifted a tier|re-subscribed|gifted a sub|prime gaming|sub train)\b',
    re.IGNORECASE
)
POLL_PATTERNS = re.compile(r'^(?:[0-9]|yes|no|y|n)$', re.IGNORECASE)


def clean_twitch_chat(
    comments: List[Dict[str, Any]],
    duration_s: int,
) -> Tuple[List[Dict[str, Any]], List[Tuple[int, int]]]:
    """
    Clean chat per Blueprint §6.1:
    - Drop bot messages
    - Drop messages starting with '!'
    - Drop sub / gift-sub patterns
    - Raid detection: burst of never-seen-before chatters -> zero for 60s
    - Return cleaned comments and list of raid blackout windows [start_s, end_s]
    """
    cleaned = []
    seen_users: Set[str] = set()
    user_first_seen: Dict[str, int] = {}

    for c in comments:
        commenter = c.get("commenter", {}).get("display_name", "").lower()
        if commenter in CHAT_BOT_NAMES:
            continue

        body = c.get("message", {}).get("body", "").strip()
        if not body or body.startswith("!"):
            continue

        unp = c.get("message", {}).get("user_notice_params", {})
        if unp.get("msg_id") or unp.get("msg-id"):
            continue

        if SUB_PATTERNS.search(body):
            continue

        cleaned.append(c)

        t = int(c.get("content_offset_seconds", 0))
        if commenter not in user_first_seen:
            user_first_seen[commenter] = t

    # Raid detection: check 5-second windows for sudden burst of new users
    # ponytail: heuristic for raid burst detection tuned in Phase 3.
    raid_windows = []
    window_step = 5
    for t_win in range(0, duration_s, window_step):
        new_users_in_win = sum(
            1 for u, first_t in user_first_seen.items()
            if t_win <= first_t < t_win + window_step
        )
        # If >= 15 brand new users suddenly appear in a 5s window
        if new_users_in_win >= 15:
            raid_windows.append((t_win, min(duration_s, t_win + RAID_SILENCE_WINDOW_S)))

    return cleaned, raid_windows


def compute_chat_signals(
    cleaned_comments: List[Dict[str, Any]],
    raid_windows: List[Tuple[int, int]],
    emotes_data: Dict[str, List[str]],
    clips_data: List[Dict[str, Any]],
    duration_s: int,
) -> Dict[str, np.ndarray]:
    """
    Compute raw per-second chat series per Blueprint §6.1:
    - chat_users: unique chatters / sec, smoothed over 5s, z-scored against rolling 10m median
    - chat_laugh: share of unique chatters with laugh tokens, smoothed over 5s, add-k shrunk
    - chat_hype: share of unique chatters with hype tokens, smoothed over 5s
    - chat_agree: share of messages equal to most common message in 5s window, smoothed over 5s
    - clip_heat: sum of 1 + log(1 + views) over distinct clip creators covering second t
    """
    # Merge tokens from config and 3rd-party emote set
    laugh_tokens = set(CHAT_LAUGH_TOKENS) | set(emotes_data.get("laugh", []))
    hype_tokens = set(CHAT_HYPE_TOKENS) | set(emotes_data.get("hype", []))

    # Bin chatters and messages by integer second
    bin_users: List[Set[str]] = [set() for _ in range(duration_s)]
    bin_msgs: List[List[str]] = [[] for _ in range(duration_s)]
    bin_laugh_users: List[Set[str]] = [set() for _ in range(duration_s)]
    bin_hype_users: List[Set[str]] = [set() for _ in range(duration_s)]

    for c in cleaned_comments:
        t = int(c.get("content_offset_seconds", 0))
        if 0 <= t < duration_s:
            user = c.get("commenter", {}).get("display_name", "")
            body = c.get("message", {}).get("body", "").strip()
            bin_users[t].add(user)
            bin_msgs[t].append(body)

            tokens = set(body.lower().split())
            if tokens & laugh_tokens:
                bin_laugh_users[t].add(user)
            if tokens & hype_tokens:
                bin_hype_users[t].add(user)

    # 1. chat_users: unique chatters per second, smoothed over 5s
    raw_users = np.array([len(u) for u in bin_users], dtype=np.float32)
    k5 = np.ones(5) / 5.0
    users_smoothed = np.convolve(raw_users, k5, mode="same")

    # Zero when window has fewer than 3 unique chatters
    users_smoothed[users_smoothed < 3.0] = 0.0

    # z-score on log1p against rolling 10-minute (600s) median
    log_users = np.log1p(users_smoothed)
    chat_users = np.zeros(duration_s, dtype=np.float32)
    half_win = 300
    for t in range(duration_s):
        w_start = max(0, t - half_win)
        w_end = min(duration_s, t + half_win)
        local_med = np.median(log_users[w_start:w_end])
        local_mad = np.median(np.abs(log_users[w_start:w_end] - local_med))
        if local_mad > 1e-4:
            chat_users[t] = (log_users[t] - local_med) / (1.4826 * local_mad)
        else:
            chat_users[t] = max(0.0, log_users[t] - local_med)

    # 2. chat_laugh: share of chatters with laugh tokens, shrunk toward mean (add-k)
    raw_laugh_cnt = np.array([len(lu) for lu in bin_laugh_users], dtype=np.float32)
    mean_laugh_rate = float(np.sum(raw_laugh_cnt) / max(1.0, np.sum(raw_users)))
    k_add = 3.0
    # add-k smoothing
    shrunk_laugh_rate = (raw_laugh_cnt + k_add * mean_laugh_rate) / (raw_users + k_add)
    chat_laugh = np.convolve(shrunk_laugh_rate, k5, mode="same").astype(np.float32)

    # 3. chat_hype: share of unique chatters posting hype tokens, smoothed over 5s
    raw_hype_cnt = np.array([len(hu) for hu in bin_hype_users], dtype=np.float32)
    hype_rate = np.zeros(duration_s, dtype=np.float32)
    nonzero_u = raw_users > 0
    hype_rate[nonzero_u] = raw_hype_cnt[nonzero_u] / raw_users[nonzero_u]
    chat_hype = np.convolve(hype_rate, k5, mode="same").astype(np.float32)

    # 4. chat_agree: share of messages equal to most common message in 5s window
    chat_agree = np.zeros(duration_s, dtype=np.float32)
    for t in range(duration_s):
        w_msgs = []
        for dt in range(max(0, t - 2), min(duration_s, t + 3)):
            w_msgs.extend(bin_msgs[dt])
        if len(w_msgs) >= 3:
            counts = {}
            for m in w_msgs:
                counts[m] = counts.get(m, 0) + 1
            max_c = max(counts.values())
            chat_agree[t] = max_c / len(w_msgs)

    # 5. clip_heat: sum over distinct clip creators covering second t of 1 + log(1 + views)
    clip_heat = np.zeros(duration_s, dtype=np.float32)
    for clip in clips_data:
        offset = clip.get("vod_offset")
        if offset is not None:
            c_dur = int(clip.get("duration", 30))
            views = float(clip.get("view_count", 0))
            w = 1.0 + np.log1p(views)
            st = int(offset)
            et = min(duration_s, st + c_dur)
            for t in range(max(0, st), et):
                clip_heat[t] += w

    # Apply raid blackout windows (zero chat signals)
    for r_start, r_end in raid_windows:
        chat_users[r_start:r_end] = 0.0
        chat_laugh[r_start:r_end] = 0.0
        chat_hype[r_start:r_end] = 0.0
        chat_agree[r_start:r_end] = 0.0

    # Poll filter: windows where >60% of messages are digits or yes/no are zeroed
    for t in range(0, duration_s, 10):
        w_msgs = []
        for dt in range(t, min(duration_s, t + 10)):
            w_msgs.extend(bin_msgs[dt])
        if len(w_msgs) >= 5:
            poll_cnt = sum(1 for m in w_msgs if POLL_PATTERNS.match(m.strip()))
            if poll_cnt / len(w_msgs) > 0.60:
                chat_users[t:min(duration_s, t + 10)] = 0.0
                chat_laugh[t:min(duration_s, t + 10)] = 0.0
                chat_hype[t:min(duration_s, t + 10)] = 0.0
                chat_agree[t:min(duration_s, t + 10)] = 0.0

    # Halve chat signals in first and last 5 minutes ("hi" and "bye" floods)
    if duration_s > 600:
        chat_users[:300] *= 0.5
        chat_laugh[:300] *= 0.5
        chat_hype[:300] *= 0.5
        chat_agree[:300] *= 0.5

        end_5m = max(300, duration_s - 300)
        chat_users[end_5m:] *= 0.5
        chat_laugh[end_5m:] *= 0.5
        chat_hype[end_5m:] *= 0.5
        chat_agree[end_5m:] *= 0.5

    return {
        "chat_users": chat_users,
        "chat_laugh": chat_laugh,
        "chat_hype": chat_hype,
        "chat_agree": chat_agree,
        "clip_heat": clip_heat,
    }


def estimate_chat_lag(
    audio_laugh: np.ndarray,
    chat_laugh: np.ndarray,
    max_shift: int = MAX_LAG_SEARCH_S,
    default_offset: float = DEFAULT_CHAT_OFFSET_S,
) -> float:
    """
    Estimate per-VOD chat lag by cross-correlating chat_laugh with audio laugh over 0..30s.
    Returns best shift when peak is clear, otherwise default_offset (§6.1).
    """
    best_shift = default_offset
    max_corr = -1.0
    corrs = []
    T = min(len(audio_laugh), len(chat_laugh))

    for shift in range(0, max_shift + 1):
        if T - shift <= 10:
            continue
        a = audio_laugh[:T - shift]
        c = chat_laugh[shift:T]
        corr = float(np.dot(a, c))
        corrs.append(corr)
        if corr > max_corr:
            max_corr = corr
            best_shift = float(shift)

    mean_corr = float(np.mean(corrs)) if corrs else 0.0
    # Peak must be prominent (at least 1.25x mean correlation and non-trivial)
    if max_corr > 1.25 * (mean_corr + 1e-6) and max_corr > 0.1:
        return best_shift
    return default_offset


def shift_chat_signals(signals: Dict[str, np.ndarray], lag_s: float, duration_s: int) -> Dict[str, np.ndarray]:
    """Shift chat signals back in time by lag_s seconds (§6.1)."""
    shift = int(round(lag_s))
    if shift <= 0:
        return signals

    shifted = {}
    for name, series in signals.items():
        # Do not shift clip_heat (clips carry their own offset)
        if name == "clip_heat":
            shifted[name] = series
            continue
        s_new = np.zeros(duration_s, dtype=np.float32)
        if shift < duration_s:
            s_new[:duration_s - shift] = series[shift:]
        shifted[name] = s_new
    return shifted


def robust_z_score(series: np.ndarray) -> np.ndarray:
    """Convert series to robust z-score: (x - median) / (1.4826 * MAD)."""
    med = np.median(series)
    mad = np.median(np.abs(series - med))
    if mad < 1e-6:
        std = np.std(series)
        return (series - med) / (std + 1e-6) if std > 1e-6 else np.zeros_like(series)
    return (series - med) / (1.4826 * mad)


def run_stage6_signals(
    video_dir: Path,
    meta: Dict[str, Any],
    audio_path: Path,
    transcript: Dict[str, Any],
    crowd_data: Any,
    chat_data: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    """
    Run Stage 6: compute signals and candidate peaks.
    Supports both with-chat (Twitch) and without-chat (YouTube/upload) modes.
    Resumes if signals.npz exists.
    """
    signals_npz_path = video_dir / "signals.npz"
    peaks_json_path = video_dir / "signal_peaks.json"

    if signals_npz_path.exists() and peaks_json_path.exists():
        try:
            with open(peaks_json_path, "r", encoding="utf-8") as f:
                peaks_data = json.load(f)
            print(f"  [stage 6] Resuming: found {signals_npz_path.name} and {peaks_json_path.name}")
            return peaks_data
        except Exception as e:
            print(f"  [stage 6] Note: could not load existing {peaks_json_path.name} ({e}), recomputing...")

    duration_s = int(meta.get("duration") or transcript.get("duration", 0.0))
    if duration_s <= 0:
        duration_s = 60

    print(f"  [stage 6] Computing signals for {duration_s}s timeline...")

    # Flatten transcript words
    all_words = []
    for s in transcript.get("segments", []):
        all_words.extend(s.get("words", []))

    # 1. YAMNet audio events (laugh, shout)
    print("  [stage 6] Running YAMNet audio event detection...")
    raw_laugh, shout, audio_loud = compute_yamnet_series(audio_path, duration_s)
    laugh = apply_laughter_gate(raw_laugh, all_words)
    laugh_thr = relative_threshold(raw_laugh)
    shout_thr = relative_threshold(shout)

    # 2. Loudness-derived signals
    voice_jump = compute_voice_jump(audio_loud)
    rage_words = compute_rage_words(all_words, duration_s, set(meta.get("rage_terms") or []))
    jump_thr = relative_threshold(voice_jump, floor=3.0)

    # 3. Speech rate
    speech_rate = compute_speech_rate(all_words, duration_s)

    # 4. Crowd & chat signals
    # Unpack crowd_data (can be list of comments or dict with platform/emotes/clips)
    if isinstance(crowd_data, dict):
        yt_comments = crowd_data.get("comments", [])
        emotes_data = crowd_data.get("emotes", {})
        clips_data = crowd_data.get("clips", [])
    else:
        yt_comments = crowd_data or []
        emotes_data = {}
        clips_data = []

    replay_heat = compute_replay_heat(meta, duration_s)
    comment_heat = compute_comment_heat(yt_comments, duration_s)

    # Check if chat data is available
    has_chat = chat_data is not None and bool(chat_data.get("comments"))
    chat_offset_s = DEFAULT_CHAT_OFFSET_S

    if has_chat:
        print("  [stage 6] Processing Twitch chat replay...")
        raw_comments = chat_data.get("comments", [])
        cleaned_comments, raid_windows = clean_twitch_chat(raw_comments, duration_s)
        print(f"  [stage 6] Cleaned chat: {len(cleaned_comments):,} of {len(raw_comments):,} messages ({len(raid_windows)} raid windows).")

        raw_chat_sigs = compute_chat_signals(
            cleaned_comments, raid_windows, emotes_data, clips_data, duration_s
        )

        # Estimate lag per VOD
        chat_offset_s = estimate_chat_lag(laugh, raw_chat_sigs["chat_laugh"])
        print(f"  [stage 6] Estimated chat lag: {chat_offset_s:.1f}s")

        # Shift chat signals back in time
        chat_sigs = shift_chat_signals(raw_chat_sigs, chat_offset_s, duration_s)

        # Build full signal dictionary
        all_signals = {
            "chat_users": chat_sigs["chat_users"],
            "chat_laugh": chat_sigs["chat_laugh"],
            "chat_hype": chat_sigs["chat_hype"],
            "chat_agree": chat_sigs["chat_agree"],
            "clip_heat": chat_sigs["clip_heat"],
            "laugh": laugh,
            "shout": shout,
            "audio_loud": audio_loud,
            "voice_jump": voice_jump,
            "rage_words": rage_words,
            "speech_rate": speech_rate,
            "replay_heat": replay_heat,
            "comment_heat": comment_heat,
        }

        # Robust z-score normalization
        z_signals = {k: robust_z_score(v) for k, v in all_signals.items()}

        # Fusion with chat (§6.1)
        weights = dict(WEIGHTS_WITH_CHAT)

        # Small chat check: when median < 0.5 msg/s, halve chat weights
        msg_per_sec = len(cleaned_comments) / max(1.0, float(duration_s))
        if msg_per_sec < 0.5:
            for k in ["chat_users", "chat_laugh", "clip_heat", "chat_hype", "chat_agree"]:
                if k in weights:
                    weights[k] *= 0.5

    else:
        print("  [stage 6] Processing without chat...")
        all_signals = {
            "laugh": laugh,
            "shout": shout,
            "audio_loud": audio_loud,
            "voice_jump": voice_jump,
            "rage_words": rage_words,
            "speech_rate": speech_rate,
            "replay_heat": replay_heat,
            "comment_heat": comment_heat,
        }
        z_signals = {k: robust_z_score(v) for k, v in all_signals.items()}
        weights = dict(WEIGHTS_WITHOUT_CHAT)

        if np.all(replay_heat == 0):
            weights["replay_heat"] = 0.0
        if np.all(comment_heat == 0):
            weights["comment_heat"] = 0.0

    # Rescale active weights to sum to 1.0
    w_sum = sum(weights.values())
    norm_weights = {k: v / w_sum for k, v in weights.items()} if w_sum > 0 else weights

    # Combine into hype(t)
    hype = np.zeros(duration_s, dtype=np.float32)
    for sig_name, w in norm_weights.items():
        if w > 0 and sig_name in z_signals:
            hype += w * np.maximum(0, z_signals[sig_name])

    # Smooth hype over 10s for peak finding
    k10 = np.ones(10) / 10.0
    hype_smoothed = np.convolve(hype, k10, mode="same")

    # Peak finding
    # No height cut: always return the top 3 x target by prominence (§6.7)
    peaks, props = find_peaks(hype_smoothed, distance=45, prominence=0)

    hours = max(1.0, duration_s / 3600.0)
    target_clips = min(MAX_TARGET_CLIPS, max(2, int(round(hours * DEFAULT_TARGET_CLIPS_PER_HOUR))))
    n_propose = target_clips * 3

    ranked = sorted(zip(peaks, props["prominences"]), key=lambda x: x[1], reverse=True)
    selected_peaks = [(int(p), float(hype_smoothed[p])) for p, _ in ranked[:n_propose]]

    # Generate candidate peak records
    candidates_from_peaks = []
    for p, score in selected_peaks:
        ctx_start = max(0.0, float(p - 60))
        ctx_end = min(float(duration_s), float(p + 30))

        is_laugh_dominant = bool(
            z_signals["laugh"][p] > z_signals.get("audio_loud", np.zeros(duration_s))[p]
            and z_signals["laugh"][p] > 1.0
        )
        if is_laugh_dominant:
            clip_start = max(0.0, float(p - 30))
            clip_end = min(float(duration_s), float(p + 8))
        else:
            clip_start = max(0.0, float(p - 25))
            clip_end = min(float(duration_s), float(p + 10))

        # chat_mood determination (§6.1)
        chat_mood = None
        if has_chat:
            family_scores = {
                "laugh": float(z_signals["chat_laugh"][p]),
                "hype": float(z_signals["chat_hype"][p]),
            }
            best_fam = max(family_scores, key=family_scores.get)
            if family_scores[best_fam] > 0.5:
                chat_mood = best_fam

        # Count families that agree (chat, clips, audio)
        families_agree = 0
        if float(z_signals["laugh"][p]) > 1.0 or float(z_signals["shout"][p]) > 1.0:
            families_agree += 1
        if has_chat and (float(z_signals["chat_users"][p]) > 1.0 or float(z_signals["chat_laugh"][p]) > 1.0):
            families_agree += 1
        if has_chat and float(z_signals.get("clip_heat", np.zeros(duration_s))[p]) > 1.0:
            families_agree += 1
        if not has_chat and (float(z_signals["replay_heat"][p]) > 1.0 or float(z_signals["comment_heat"][p]) > 1.0):
            families_agree += 1

        candidates_from_peaks.append({
            "peak_t": float(p),
            "signal_score_raw": float(score),
            "context_start": float(ctx_start),
            "context_end": float(ctx_end),
            "clip_start": float(clip_start),
            "clip_end": float(clip_end),
            "is_laugh_dominant": bool(is_laugh_dominant),
            "chat_mood": chat_mood,
            "families_agree": int(families_agree),
            "origin": "signal",
            "signals_at_peak": {
                k: round(float(v[p]), 3) for k, v in z_signals.items()
            }
        })

    # Save signals.npz
    np.savez_compressed(
        signals_npz_path,
        hype=hype,
        hype_smoothed=hype_smoothed,
        laugh_thr=np.float32(laugh_thr),
        shout_thr=np.float32(shout_thr),
        jump_thr=np.float32(jump_thr),
        **all_signals
    )

    result_data = {
        "duration_s": duration_s,
        "has_chat": has_chat,
        "chat_offset_s": float(chat_offset_s),
        "target_clip_count": target_clips,
        "peak_count": len(candidates_from_peaks),
        "peaks": candidates_from_peaks,
    }

    with open(peaks_json_path, "w", encoding="utf-8") as f:
        json.dump(result_data, f, indent=2)

    print(f"  [stage 6] Done: found {len(candidates_from_peaks)} candidate peaks (chat={has_chat}, target {target_clips} clips).")
    return result_data
