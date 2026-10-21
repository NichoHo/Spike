"""
Stage 5: transcribe
Blueprint §5 & §16:
faster-whisper small int8 on CPU, word timestamps, VAD filter.
Includes av.open patch for PyAV 19 compatibility and OpenShorts merge_continuation_words.
Output: data/videos/<id>/transcript.json
"""

import json
import subprocess
import time
from pathlib import Path
from typing import Dict, Any, List, Callable, Optional

# Monkeypatch av.open before importing faster_whisper to remove deprecated metadata_errors
import av
_orig_av_open = av.open
def _patched_av_open(*args, **kwargs):
    kwargs.pop("metadata_errors", None)
    return _orig_av_open(*args, **kwargs)
av.open = _patched_av_open

import numpy as np
from faster_whisper import WhisperModel
from src.config import DEFAULT_WHISPER_MODEL, WHISPER_COMPUTE_TYPE, WHISPER_DEVICE


def merge_continuation_words(words: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """Merge faster-whisper continuation fragments into their base word (from OpenShorts).
    Tokens without a leading space belong to the preceding word.
    """
    merged = []
    for word in words:
        text = word.get("word", "")
        if merged and isinstance(text, str) and text and not text.startswith(" "):
            prev = merged[-1]
            prev["word"] = f"{prev.get('word', '')}{text}"
            if word.get("end") is not None:
                prev["end"] = word["end"]
        else:
            merged.append(dict(word))
    return merged


CHUNK_S = 1800


def _audio_duration(audio_path: Path) -> float:
    res = subprocess.run(["ffprobe", "-v", "error", "-show_entries", "format=duration", "-of", "csv=p=0", str(audio_path)],
                         capture_output=True, text=True)
    try:
        return float(res.stdout.strip())
    except ValueError:
        return 0.0


def _decode_chunk(audio_path: Path, offset_s: float, length_s: float) -> np.ndarray:
    """[offset_s, offset_s + length_s] of the audio as 16 kHz mono float32, the input Whisper wants."""
    out = subprocess.run(["ffmpeg", "-v", "error", "-ss", str(offset_s), "-t", str(length_s), "-i", str(audio_path),
                          "-f", "f32le", "-ac", "1", "-ar", "16000", "pipe:1"], capture_output=True, check=True)
    return np.frombuffer(out.stdout, dtype=np.float32)


def run_stage5_transcribe(
    video_dir: Path,
    audio_path: Path,
    model_size: str = DEFAULT_WHISPER_MODEL,
    on_progress: Optional[Callable[[float], None]] = None,
) -> Dict[str, Any]:
    """Run Stage 5: transcribe. Resumes if transcript.json exists.
    on_progress gets the fraction of audio done (0..1), at most every 15 s.
    """
    transcript_path = video_dir / "transcript.json"
    if transcript_path.exists():
        print(f"  [stage 5] Resuming: found {transcript_path.name}")
        with open(transcript_path, "r", encoding="utf-8") as f:
            return json.load(f)

    print(f"  [stage 5] Loading faster-whisper model '{model_size}' ({WHISPER_COMPUTE_TYPE} on {WHISPER_DEVICE})...")
    t_load_start = time.perf_counter()
    model = WhisperModel(model_size, device=WHISPER_DEVICE, compute_type=WHISPER_COMPUTE_TYPE)
    t_load = time.perf_counter() - t_load_start
    print(f"  [stage 5] Model loaded in {t_load:.1f}s. Starting transcription...")

    t_start = time.perf_counter()
    total_dur = _audio_duration(audio_path)
    segments_out = []
    total_words = 0
    last_report = 0.0
    info = None

    # Whisper builds features for the whole input at once (7.9 h of audio asked for a 4.8 GiB array), so long
    # streams go through in 30-minute chunks. A word cut at a chunk edge can be lost; VAD trims most edges to silence.
    for offset in range(0, max(1, int(total_dur) + 1), CHUNK_S):
        chunk = _decode_chunk(audio_path, offset, CHUNK_S)
        if chunk.size < 16000:
            break
        segments_gen, chunk_info = model.transcribe(chunk, vad_filter=True, word_timestamps=True, multilingual=True)
        info = info or chunk_info
        for seg in segments_gen:
            if on_progress and total_dur and time.perf_counter() - last_report >= 15:
                last_report = time.perf_counter()
                try:
                    on_progress((offset + seg.end) / total_dur)
                except Exception as progress_err:
                    print(f"  [stage 5] Progress report failed: {progress_err}")
            words = []
            if seg.words:
                raw_words = [
                    {"word": w.word, "start": round(offset + w.start, 3), "end": round(offset + w.end, 3), "probability": round(w.probability, 3)}
                    for w in seg.words
                ]
                words = merge_continuation_words(raw_words)
                total_words += len(words)

            segments_out.append({
                "id": len(segments_out),
                "seek": seg.seek,
                "start": round(offset + seg.start, 3),
                "end": round(offset + seg.end, 3),
                "text": seg.text.strip(),
                "words": words,
            })

    elapsed = time.perf_counter() - t_start
    audio_dur = total_dur or (segments_out[-1]["end"] if segments_out else 0.0)
    rtf = elapsed / max(audio_dur, 1.0)

    transcript = {
        "language": info.language if info else None,
        "language_probability": round(info.language_probability, 3) if info else 0.0,
        "duration": round(audio_dur, 2),
        "transcription_time_s": round(elapsed, 1),
        "rtf": round(rtf, 3),
        "segment_count": len(segments_out),
        "word_count": total_words,
        "segments": segments_out,
    }

    with open(transcript_path, "w", encoding="utf-8") as f:
        json.dump(transcript, f, indent=2)

    print(
        f"  [stage 5] Transcribed {audio_dur:.0f}s audio in {elapsed:.1f}s "
        f"({1/rtf:.1f}x real-time). {len(segments_out)} segments, {total_words} words."
    )
    return transcript
