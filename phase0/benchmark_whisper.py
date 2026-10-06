"""
Phase 0 Benchmark: faster-whisper (base, small, medium) on a 30-min audio sample.
Usage: py benchmark_whisper.py <audio_file>

Outputs a JSON results file alongside this script.
"""

import sys
import time
import json
import os
from pathlib import Path

MODELS = ["base", "small", "medium"]
AUDIO_DURATION_S = None  # filled in from ffprobe

# Patch av.open to remove metadata_errors keyword argument incompatible with av 19+
import av
_orig_av_open = av.open
def _patched_av_open(*args, **kwargs):
    kwargs.pop("metadata_errors", None)
    return _orig_av_open(*args, **kwargs)
av.open = _patched_av_open

def get_audio_duration(path: str) -> float:
    """Return audio duration in seconds via ffprobe."""
    import subprocess
    result = subprocess.run(
        [
            "ffprobe", "-v", "error",
            "-show_entries", "format=duration",
            "-of", "json",
            path
        ],
        capture_output=True, text=True
    )
    info = json.loads(result.stdout)
    return float(info["format"]["duration"])


def run_benchmark(audio_path: str, model_name: str) -> dict:
    """Transcribe with the given model and return timing info."""
    from faster_whisper import WhisperModel

    print(f"\n--- Benchmarking: {model_name} ---")
    print("  Loading model...")
    load_start = time.perf_counter()
    model = WhisperModel(model_name, device="cpu", compute_type="int8")
    load_elapsed = time.perf_counter() - load_start
    print(f"  Model loaded in {load_elapsed:.1f}s")

    print("  Transcribing (VAD filter on)...")
    t_start = time.perf_counter()
    segments, info = model.transcribe(
        audio_path,
        vad_filter=True,
        word_timestamps=True,
    )
    # Consume the generator to complete transcription
    word_count = 0
    segment_count = 0
    for seg in segments:
        segment_count += 1
        if seg.words:
            word_count += len(seg.words)
    t_elapsed = time.perf_counter() - t_start

    audio_dur = get_audio_duration(audio_path)
    rtf = t_elapsed / audio_dur

    # Reconfigure stdout to UTF-8 for safe printing on Windows
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass

    result = {
        "model": model_name,
        "audio_duration_s": round(audio_dur, 1),
        "transcription_time_s": round(t_elapsed, 1),
        "model_load_time_s": round(load_elapsed, 1),
        "rtf": round(rtf, 3),
        "real_time_factor_description": f"{1/rtf:.1f}x faster than real-time" if rtf < 1 else f"{rtf:.1f}x real-time (SLOWER than real-time)",
        "segments": segment_count,
        "words": word_count,
        "detected_language": info.language,
        "language_probability": round(info.language_probability, 3),
    }

    print(f"  Done: {t_elapsed:.1f}s for {audio_dur:.0f}s of audio -> RTF={rtf:.3f} ({result['real_time_factor_description']})")
    return result


def main():
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass

    if len(sys.argv) < 2:
        print("Usage: py benchmark_whisper.py <audio_file>", flush=True)
        print("  e.g.: py benchmark_whisper.py sample_30min.m4a", flush=True)
        sys.exit(1)

    audio_path = sys.argv[1]
    if not os.path.exists(audio_path):
        print(f"Error: file not found: {audio_path}", flush=True)
        sys.exit(1)

    models_to_test = sys.argv[2:] if len(sys.argv) > 2 else MODELS

    print(f"Phase 0 Whisper Benchmark", flush=True)
    print(f"Audio: {audio_path}", flush=True)
    print(f"Models: {models_to_test}", flush=True)

    results = []
    for model_name in models_to_test:
        try:
            r = run_benchmark(audio_path, model_name)
            results.append(r)
        except Exception as e:
            results.append({"model": model_name, "error": str(e)})
            print(f"  ERROR: {e}", flush=True)

    out_path = Path(__file__).parent / "whisper_benchmark_results.json"
    existing = []
    if out_path.exists():
        try:
            with open(out_path, "r") as f:
                existing = json.load(f)
        except Exception:
            existing = []
    
    # Merge existing results with new results by model name
    merged = {r.get("model"): r for r in existing if isinstance(r, dict)}
    for r in results:
        merged[r.get("model")] = r
    final_list = list(merged.values())

    with open(out_path, "w") as f:
        json.dump(final_list, f, indent=2)

    print(f"\n=== RESULTS ===")
    print(f"{'Model':<10} {'Audio (s)':<12} {'Transc. (s)':<14} {'RTF':<8} {'Speed'}")
    print("-" * 65)
    for r in results:
        if "error" in r:
            print(f"{r['model']:<10} ERROR: {r['error']}")
        else:
            print(
                f"{r['model']:<10} {r['audio_duration_s']:<12.0f} {r['transcription_time_s']:<14.1f} "
                f"{r['rtf']:<8.3f} {r['real_time_factor_description']}"
            )
    print(f"\nFull results written to: {out_path}")


if __name__ == "__main__":
    main()
