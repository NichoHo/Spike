"""
Stage 5: transcribe
Blueprint §5 & §16:
faster-whisper small int8 on CPU, word timestamps, VAD filter.
Includes av.open patch for PyAV 19 compatibility and OpenShorts merge_continuation_words.
Output: data/videos/<id>/transcript.json
"""

import json
import time
from pathlib import Path
from typing import Dict, Any, List

# Monkeypatch av.open before importing faster_whisper to remove deprecated metadata_errors
import av
_orig_av_open = av.open
def _patched_av_open(*args, **kwargs):
    kwargs.pop("metadata_errors", None)
    return _orig_av_open(*args, **kwargs)
av.open = _patched_av_open

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


def run_stage5_transcribe(video_dir: Path, audio_path: Path, model_size: str = DEFAULT_WHISPER_MODEL) -> Dict[str, Any]:
    """Run Stage 5: transcribe. Resumes if transcript.json exists."""
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
    segments_gen, info = model.transcribe(
        str(audio_path),
        vad_filter=True,
        word_timestamps=True,
        multilingual=True,
    )

    segments_out = []
    total_words = 0

    for seg in segments_gen:
        words = []
        if seg.words:
            raw_words = [
                {"word": w.word, "start": round(w.start, 3), "end": round(w.end, 3), "probability": round(w.probability, 3)}
                for w in seg.words
            ]
            words = merge_continuation_words(raw_words)
            total_words += len(words)

        segments_out.append({
            "id": seg.id,
            "seek": seg.seek,
            "start": round(seg.start, 3),
            "end": round(seg.end, 3),
            "text": seg.text.strip(),
            "words": words,
        })

    elapsed = time.perf_counter() - t_start
    audio_dur = info.duration or (segments_out[-1]["end"] if segments_out else 0.0)
    rtf = elapsed / max(audio_dur, 1.0)

    transcript = {
        "language": info.language,
        "language_probability": round(info.language_probability, 3),
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
