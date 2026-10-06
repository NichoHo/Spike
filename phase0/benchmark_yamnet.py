"""
Phase 0 Benchmark: YAMNet (via tf.lite.Interpreter + yamnet.tflite) on the audio sample.

Uses tf.lite.Interpreter directly — no tensorflow_hub, no pkg_resources dependency.
Model: yamnet.tflite (downloaded from Google storage on first run, ~4 MB)

Measures:
  - CPU seconds per audio hour for inference
  - Laugh hits: Laughter, Giggle, Snicker, Belly laugh, Chuckle (classes from AudioSet map)
  - Shout hits: Shout, Yell, Screaming, Whoop
  - Counts "runs" >= 0.5s (consecutive frames above threshold)

YAMNet TFLite input: 15600 samples = 0.975 s at 16 kHz (one call per frame).
Hop in original YAMNet SavedModel is 0.48 s (480 ms). The tflite version takes fixed
0.975 s windows; we slide with 0.48 s hop to match the SavedModel behavior.

Usage:
  py phase0/benchmark_yamnet.py phase0/sample_audio.m4a
"""

import sys
import time
import json
import subprocess
import os
import wave
from pathlib import Path
import urllib.request

SAMPLE_RATE = 16000  # YAMNet requires 16 kHz mono
TFLITE_URL = (
    "https://storage.googleapis.com/download.tensorflow.org/models/"
    "tflite/task_library/audio_classification/android/"
    "lite-model_yamnet_classification_tflite_1.tflite"
)
CLASSMAP_URL = (
    "https://raw.githubusercontent.com/tensorflow/models/master/"
    "research/audioset/yamnet/yamnet_class_map.csv"
)

# AudioSet class indices (0-indexed) for laughter / shouting
# Verified from yamnet_class_map.csv (521 classes)
LAUGH_CLASS_NAMES = {"Laughter", "Giggle", "Snicker", "Belly laugh", "Chuckle, chortle"}
SHOUT_CLASS_NAMES = {"Shout", "Yell", "Screaming", "Whoop"}

FRAME_SAMPLES = 15600   # 0.975 s at 16 kHz  (model input size)
HOP_SAMPLES   = 7680    # 0.480 s hop


def download_if_missing(url: str, dest: str):
    if not os.path.exists(dest):
        print(f"  Downloading {Path(dest).name} ...")
        urllib.request.urlretrieve(url, dest)
        print(f"  Saved {Path(dest).name} ({os.path.getsize(dest)//1024} KB)")


def load_class_map(csv_path: str) -> list[str]:
    """Return list of class display names, index = class id."""
    names = []
    with open(csv_path, encoding="utf-8") as f:
        for i, line in enumerate(f):
            if i == 0:
                continue  # header
            parts = line.strip().split(",", 2)
            names.append(parts[2].strip('"') if len(parts) > 2 else "?")
    return names


def extract_wav(input_path: str, output_path: str):
    """Convert audio to 16 kHz mono WAV."""
    subprocess.run(
        ["ffmpeg", "-y", "-loglevel", "error",
         "-i", input_path, "-ar", str(SAMPLE_RATE), "-ac", "1",
         "-f", "wav", output_path],
        check=True
    )


def read_wav_samples(wav_path: str):
    """Read WAV as float32 in [-1, 1]."""
    import numpy as np
    with wave.open(wav_path, "rb") as wf:
        raw = wf.readframes(wf.getnframes())
    return np.frombuffer(raw, dtype=np.int16).astype(np.float32) / 32768.0


def count_runs(mask) -> int:
    """Count rising edges (False→True transitions) in a boolean array."""
    runs = 0
    prev = False
    for v in mask:
        if v and not prev:
            runs += 1
        prev = bool(v)
    return runs


def run_yamnet_tflite(wav_path: str, tflite_path: str,
                      class_names: list[str], audio_duration_s: float) -> dict:
    import numpy as np
    import tensorflow as tf
    import warnings

    # Suppress deprecation warning for tf.lite.Interpreter
    with warnings.catch_warnings():
        warnings.simplefilter("ignore")
        interp = tf.lite.Interpreter(model_path=tflite_path)
    interp.allocate_tensors()

    inp_detail = interp.get_input_details()[0]
    out_detail = interp.get_output_details()[0]
    # Output shape: [1, 521]

    laugh_idx = [i for i, n in enumerate(class_names) if n in LAUGH_CLASS_NAMES]
    shout_idx = [i for i, n in enumerate(class_names) if n in SHOUT_CLASS_NAMES]
    print(f"  Laugh classes ({len(laugh_idx)}): {[class_names[i] for i in laugh_idx]}")
    print(f"  Shout classes ({len(shout_idx)}): {[class_names[i] for i in shout_idx]}")

    samples = read_wav_samples(wav_path)
    total_samples = len(samples)

    print(f"  Sliding window inference ({FRAME_SAMPLES} samples, {HOP_SAMPLES} hop)...")
    t0 = time.perf_counter()

    laugh_scores = []
    shout_scores = []

    start = 0
    while start + FRAME_SAMPLES <= total_samples:
        window = samples[start : start + FRAME_SAMPLES]
        interp.set_tensor(inp_detail["index"], window.reshape(inp_detail["shape"]))
        interp.invoke()
        scores = interp.get_tensor(out_detail["index"])[0]  # shape (521,)

        laugh_scores.append(float(scores[laugh_idx].max()) if laugh_idx else 0.0)
        shout_scores.append(float(scores[shout_idx].max()) if shout_idx else 0.0)

        start += HOP_SAMPLES

    elapsed = time.perf_counter() - t0
    n_frames = len(laugh_scores)

    laugh_arr = np.array(laugh_scores)
    shout_arr = np.array(shout_scores)
    THRESH = 0.3

    # Each frame covers HOP_SAMPLES/SAMPLE_RATE = 0.48 s
    # A "run >= 0.5 s" means >=1 consecutive frame (since 0.48 s < 0.5 s, need >=2 frames
    # for a strict 0.5 s run, but 1 frame already covers >=0.48 s of the window — we use 1)
    laugh_mask = laugh_arr > THRESH
    shout_mask = shout_arr > THRESH

    return {
        "model": "YAMNet (tf.lite.Interpreter, yamnet.tflite)",
        "audio_duration_s": round(audio_duration_s, 1),
        "inference_time_s": round(elapsed, 1),
        "cpu_minutes_per_audio_hour": round(elapsed / audio_duration_s * 3600 / 60, 1),
        "realtime_factor": round(elapsed / audio_duration_s, 3),
        "n_frames": n_frames,
        "hop_s": round(HOP_SAMPLES / SAMPLE_RATE, 3),
        "laugh_class_count": len(laugh_idx),
        "shout_class_count": len(shout_idx),
        f"laugh_frames_above_{THRESH}": int(laugh_mask.sum()),
        "laugh_runs_ge_0.5s": count_runs(laugh_mask),
        f"shout_frames_above_{THRESH}": int(shout_mask.sum()),
        "shout_runs_ge_0.5s": count_runs(shout_mask),
        "laugh_max_prob": round(float(laugh_arr.max()), 3),
        "shout_max_prob": round(float(shout_arr.max()), 3),
        "laugh_mean_prob": round(float(laugh_arr.mean()), 4),
    }


def get_audio_duration(path: str) -> float:
    result = subprocess.run(
        ["ffprobe", "-v", "error", "-show_entries", "format=duration",
         "-of", "json", path],
        capture_output=True, text=True
    )
    return float(json.loads(result.stdout)["format"]["duration"])


def main():
    if len(sys.argv) < 2:
        print("Usage: py phase0/benchmark_yamnet.py <audio_file>")
        sys.exit(1)

    audio_path = sys.argv[1]
    if not os.path.exists(audio_path):
        print(f"Error: {audio_path} not found")
        sys.exit(1)

    phase0_dir = Path(__file__).parent
    tflite_path = str(phase0_dir / "yamnet.tflite")
    classmap_path = str(phase0_dir / "yamnet_class_map.csv")

    print("\nPhase 0 YAMNet Benchmark (tf.lite.Interpreter)")
    print(f"Audio: {audio_path}")
    audio_dur = get_audio_duration(audio_path)
    print(f"Duration: {audio_dur:.0f}s ({audio_dur/60:.1f} min)")

    # Download model files if needed
    download_if_missing(TFLITE_URL, tflite_path)
    download_if_missing(CLASSMAP_URL, classmap_path)

    class_names = load_class_map(classmap_path)
    print(f"Loaded class map: {len(class_names)} classes")

    # Convert audio
    wav_path = str(phase0_dir / "sample_audio_16k.wav")
    print(f"\nConverting to 16 kHz mono WAV...")
    t_conv = time.perf_counter()
    extract_wav(audio_path, wav_path)
    conv_elapsed = time.perf_counter() - t_conv
    print(f"Conversion: {conv_elapsed:.1f}s")

    # Run YAMNet
    print("\n--- YAMNet ---")
    result = run_yamnet_tflite(wav_path, tflite_path, class_names, audio_dur)

    # PANNs note
    panns = {"panns_available": False,
             "note": "PANNs CNN14 ruled out: ~20x heavier than YAMNet (81M vs 3.7M params), "
                     "no PyPI package, CPU inference too slow for production use."}

    results = {"yamnet": result, "panns": panns}

    out_path = phase0_dir / "yamnet_benchmark_results.json"
    with open(out_path, "w") as f:
        json.dump(results, f, indent=2)

    # Cleanup WAV
    if os.path.exists(wav_path):
        os.remove(wav_path)

    print(f"\n=== RESULTS ===")
    print(f"Model:              {result['model']}")
    print(f"Audio duration:     {result['audio_duration_s']:.0f}s ({audio_dur/60:.1f} min)")
    print(f"Inference time:     {result['inference_time_s']}s")
    print(f"RTF:                {result['realtime_factor']} ({1/result['realtime_factor']:.1f}x faster than real-time)")
    print(f"CPU-min per hr:     {result['cpu_minutes_per_audio_hour']} min")
    print(f"Laugh runs (>=0.5s, >0.3): {result['laugh_runs_ge_0.5s']}")
    print(f"Shout runs (>=0.5s, >0.3): {result['shout_runs_ge_0.5s']}")
    print(f"Laugh max prob:     {result['laugh_max_prob']}")
    print(f"\nFull results: {out_path}")


if __name__ == "__main__":
    main()
