"""
Synthesize 5 high-quality royalty-free musical tracks for Spike's mood library:
- chill: Warm lofi chords with soft ambient groove
- hype: Driving 130 BPM electronic synth pulse
- funny: Playful bouncy pizzicato / marimba melody
- dramatic: Cinematic minor-key swell and tension drone
- wholesome: Bright acoustic piano / guitar progression

Encodes to .mp3 via FFmpeg and writes required license sidecar .json files.
"""

import json
import math
import subprocess
from pathlib import Path
import numpy as np
import scipy.io.wavfile as wavfile

SR = 44100
DURATION = 60.0  # 60-second loopable tracks
NUM_SAMPLES = int(SR * DURATION)
T = np.linspace(0, DURATION, NUM_SAMPLES, endpoint=False)

ROOT = Path(__file__).resolve().parent.parent
MUSIC_DIR = ROOT / "music"


def adsr(length_samples: int, a=0.05, d=0.1, s=0.7, r=0.2) -> np.ndarray:
    """Generate an ADSR envelope."""
    na = int(length_samples * a)
    nd = int(length_samples * d)
    nr = int(length_samples * r)
    ns = length_samples - (na + nd + nr)
    if ns < 0:
        ns = 0
    env = np.concatenate([
        np.linspace(0, 1, na),
        np.linspace(1, s, nd),
        np.full(ns, s),
        np.linspace(s, 0, nr),
    ])
    if len(env) < length_samples:
        env = np.pad(env, (0, length_samples - len(env)))
    return env[:length_samples]


def generate_chill() -> Tuple[np.ndarray, np.ndarray]:
    """Chill: warm lofi 7th chords (Cmaj7 - Am7 - Dm7 - G7) with vinyl warmth."""
    bpm = 75
    spb = 60.0 / bpm
    bar_dur = spb * 4.0
    bar_samples = int(SR * bar_dur)
    
    # Chords (frequencies in Hz)
    chords = [
        [130.81, 164.81, 196.00, 246.94, 293.66],  # Cmaj9
        [110.00, 130.81, 164.81, 196.00, 261.63],  # Am7/9
        [146.83, 174.61, 220.00, 261.63, 329.63],  # Dm9
        [98.00, 123.47, 174.61, 196.00, 246.94],   # G7/13
    ]
    
    left = np.zeros(NUM_SAMPLES)
    right = np.zeros(NUM_SAMPLES)
    
    num_bars = int(DURATION / bar_dur) + 1
    for bar_idx in range(num_bars):
        chord = chords[bar_idx % len(chords)]
        st = int(bar_idx * bar_samples)
        et = min(st + bar_samples, NUM_SAMPLES)
        dur_s = (et - st) / SR
        if dur_s <= 0:
            break
        t_sub = np.linspace(0, dur_s, et - st, endpoint=False)
        env = adsr(et - st, a=0.08, d=0.15, s=0.6, r=0.25)
        
        chord_wave = np.zeros(et - st)
        for i, freq in enumerate(chord):
            # Rich warm electric piano harmonics (odd/even harmonics decaying)
            wave = (
                0.50 * np.sin(2 * np.pi * freq * t_sub)
                + 0.25 * np.sin(2 * np.pi * 2 * freq * t_sub)
                + 0.12 * np.sin(2 * np.pi * 3 * freq * t_sub)
                + 0.06 * np.sin(2 * np.pi * 4 * freq * t_sub)
            )
            chord_wave += wave * (0.8 + 0.1 * i)
            
        chord_wave *= env
        left[st:et] += chord_wave * 0.45
        right[st:et] += chord_wave * 0.50
        
    # Add gentle vinyl warmth
    noise = np.random.normal(0, 0.008, NUM_SAMPLES)
    left += noise
    right += noise
    
    # Soft drum pulse on beat 2 and 4
    for b in range(int(DURATION / spb)):
        if b % 2 == 1:
            st = int(b * spb * SR)
            et = min(st + int(0.2 * SR), NUM_SAMPLES)
            if et > st:
                snare = np.random.normal(0, 0.05, et - st) * np.linspace(1, 0, et - st)
                left[st:et] += snare * 0.3
                right[st:et] += snare * 0.3
                
    return left, right


def generate_hype() -> Tuple[np.ndarray, np.ndarray]:
    """Hype: 130 BPM energetic bassline and driving synth arpeggios."""
    bpm = 130
    spb = 60.0 / bpm
    step_dur = spb / 4.0  # 16th notes
    step_samples = int(SR * step_dur)
    
    scale = [110.0, 130.81, 146.83, 164.81, 196.0, 220.0, 261.63, 293.66]  # A minor
    arp_pattern = [0, 2, 4, 7, 5, 4, 2, 0, 7, 5, 4, 2, 4, 5, 7, 9]
    
    left = np.zeros(NUM_SAMPLES)
    right = np.zeros(NUM_SAMPLES)
    
    total_steps = int(DURATION / step_dur)
    for s in range(total_steps):
        st = int(s * step_samples)
        et = min(st + step_samples, NUM_SAMPLES)
        if et <= st:
            break
        note_idx = arp_pattern[s % len(arp_pattern)]
        freq = scale[note_idx % len(scale)]
        t_sub = np.linspace(0, (et - st) / SR, et - st, endpoint=False)
        
        # Plucked synth wave (sawtooth approximation)
        saw = 0.4 * np.sin(2 * np.pi * freq * t_sub) + 0.2 * np.sin(4 * np.pi * freq * t_sub) + 0.1 * np.sin(6 * np.pi * freq * t_sub)
        env = adsr(et - st, a=0.01, d=0.4, s=0.2, r=0.3)
        tone = saw * env
        
        pan = 0.5 + 0.25 * math.sin(s * 0.5)
        left[st:et] += tone * pan * 0.35
        right[st:et] += tone * (1 - pan) * 0.35
        
    # Kick drum on every beat
    for b in range(int(DURATION / spb)):
        st = int(b * spb * SR)
        et = min(st + int(0.18 * SR), NUM_SAMPLES)
        if et > st:
            t_k = np.linspace(0, (et - st) / SR, et - st, endpoint=False)
            freq_k = 150 * np.exp(-t_k * 30) + 45
            kick = 0.6 * np.sin(2 * np.pi * freq_k * t_k) * np.linspace(1, 0, et - st) ** 2
            left[st:et] += kick
            right[st:et] += kick

    return left, right


def generate_funny() -> Tuple[np.ndarray, np.ndarray]:
    """Funny: quirky bouncy marimba / pizzicato motif at 115 BPM."""
    bpm = 115
    spb = 60.0 / bpm
    step_dur = spb / 2.0  # 8th notes
    step_samples = int(SR * step_dur)
    
    notes = [261.63, 329.63, 392.00, 523.25, 493.88, 392.00, 329.63, 293.66,
             261.63, 349.23, 440.00, 523.25, 440.00, 349.23, 293.66, 246.94]
    
    left = np.zeros(NUM_SAMPLES)
    right = np.zeros(NUM_SAMPLES)
    
    total_steps = int(DURATION / step_dur)
    for s in range(total_steps):
        st = int(s * step_samples)
        et = min(st + step_samples, NUM_SAMPLES)
        if et <= st:
            break
        freq = notes[s % len(notes)]
        t_sub = np.linspace(0, (et - st) / SR, et - st, endpoint=False)
        # Bouncy marimba harmonic structure with fast decay
        marimba = (
            0.6 * np.sin(2 * np.pi * freq * t_sub)
            + 0.25 * np.sin(2 * np.pi * 3.8 * freq * t_sub)
            + 0.15 * np.sin(2 * np.pi * 9.2 * freq * t_sub)
        )
        env = np.exp(-t_sub * 18)
        left[st:et] += marimba * env * 0.35
        right[st:et] += marimba * env * 0.35
        
        # Bouncy acoustic walking bass on alternating steps
        if s % 2 == 0:
            bass_freq = freq / 4.0
            bass_wave = 0.4 * np.sin(2 * np.pi * bass_freq * t_sub) * np.exp(-t_sub * 8)
            left[st:et] += bass_wave
            right[st:et] += bass_wave
            
    return left, right


def generate_dramatic() -> Tuple[np.ndarray, np.ndarray]:
    """Dramatic: cinematic low cello drone, pulsing tension, dark brass swell."""
    bpm = 70
    spb = 60.0 / bpm
    bar_dur = spb * 4.0
    bar_samples = int(SR * bar_dur)
    
    # Progression: Dm - Bb - Gm - A
    roots = [73.42, 58.27, 49.00, 55.00]
    
    left = np.zeros(NUM_SAMPLES)
    right = np.zeros(NUM_SAMPLES)
    
    num_bars = int(DURATION / bar_dur) + 1
    for b in range(num_bars):
        root = roots[b % len(roots)]
        st = int(b * bar_samples)
        et = min(st + bar_samples, NUM_SAMPLES)
        if et <= st:
            break
        dur = (et - st) / SR
        t_sub = np.linspace(0, dur, et - st, endpoint=False)
        env = adsr(et - st, a=0.25, d=0.2, s=0.7, r=0.3)
        
        # Deep bowed string drone
        drone = (
            0.40 * np.sin(2 * np.pi * root * t_sub)
            + 0.30 * np.sin(2 * np.pi * 2 * root * t_sub)
            + 0.20 * np.sin(2 * np.pi * 3 * root * t_sub)
            + 0.10 * np.sin(2 * np.pi * 4 * root * t_sub)
        )
        # Subtle slow chorus modulation
        l_mod = 1.0 + 0.15 * np.sin(2 * np.pi * 0.3 * t_sub)
        r_mod = 1.0 + 0.15 * np.cos(2 * np.pi * 0.3 * t_sub)
        
        left[st:et] += drone * env * l_mod * 0.4
        right[st:et] += drone * env * r_mod * 0.4
        
    return left, right


def generate_wholesome() -> Tuple[np.ndarray, np.ndarray]:
    """Wholesome: bright acoustic piano / guitar progression (G - D - Em - C)."""
    bpm = 90
    spb = 60.0 / bpm
    bar_dur = spb * 4.0
    bar_samples = int(SR * bar_dur)
    
    # Chords (G major, D major, E minor, C major)
    chords = [
        [196.00, 246.94, 293.66, 392.00],  # G
        [146.83, 220.00, 293.66, 369.99],  # D
        [164.81, 196.00, 246.94, 329.63],  # Em
        [130.81, 164.81, 196.00, 261.63],  # C
    ]
    
    left = np.zeros(NUM_SAMPLES)
    right = np.zeros(NUM_SAMPLES)
    
    num_bars = int(DURATION / bar_dur) + 1
    for b in range(num_bars):
        chord = chords[b % len(chords)]
        st = int(b * bar_samples)
        et = min(st + bar_samples, NUM_SAMPLES)
        if et <= st:
            break
        dur = (et - st) / SR
        
        # Arpeggiate 4 notes across the bar
        note_dur = spb
        for ni, freq in enumerate(chord):
            n_st = st + int(ni * note_dur * SR)
            n_et = min(n_st + int(note_dur * 1.8 * SR), NUM_SAMPLES)
            if n_et <= n_st:
                continue
            t_n = np.linspace(0, (n_et - n_st) / SR, n_et - n_st, endpoint=False)
            piano = (
                0.55 * np.sin(2 * np.pi * freq * t_n)
                + 0.25 * np.sin(2 * np.pi * 2 * freq * t_n)
                + 0.12 * np.sin(2 * np.pi * 3 * freq * t_n)
                + 0.05 * np.sin(2 * np.pi * 4 * freq * t_n)
            )
            env = np.exp(-t_n * 2.5)
            left[n_st:n_et] += piano * env * 0.35
            right[n_st:n_et] += piano * env * 0.38

    return left, right


def write_track(mood: str, stem: str, title: str, artist: str, left: np.ndarray, right: np.ndarray):
    """Write WAV, convert to MP3 via ffmpeg, and write sidecar JSON."""
    mood_dir = MUSIC_DIR / mood
    mood_dir.mkdir(parents=True, exist_ok=True)
    
    wav_path = mood_dir / f"{stem}.wav"
    mp3_path = mood_dir / f"{stem}.mp3"
    json_path = mood_dir / f"{stem}.json"
    
    # Normalize peak to -1.0 dB
    peak = max(np.max(np.abs(left)), np.max(np.abs(right)), 1e-6)
    target_peak = 0.89  # -1 dB
    left = (left / peak) * target_peak
    right = (right / peak) * target_peak
    
    stereo = np.column_stack([left, right])
    stereo_int16 = (stereo * 32767).astype(np.int16)
    wavfile.write(str(wav_path), SR, stereo_int16)
    
    # Encode to MP3 via ffmpeg
    cmd = [
        "ffmpeg", "-y", "-hide_banner", "-loglevel", "error",
        "-i", str(wav_path),
        "-c:a", "libmp3lame",
        "-b:a", "192k",
        str(mp3_path),
    ]
    subprocess.run(cmd, check=True)
    wav_path.unlink()  # Remove temporary WAV
    
    # Write license sidecar JSON
    sidecar = {
        "title": title,
        "artist": artist,
        "mood": mood,
        "source": "Spike Royalty-Free Library",
        "license": "CC0 1.0 Universal (Public Domain)",
        "url": "https://creativecommons.org/publicdomain/zero/1.0/",
    }
    json_path.write_text(json.dumps(sidecar, indent=2), encoding="utf-8")
    print(f"Created {mood}/{stem}.mp3 ({mp3_path.stat().st_size // 1024} KB) + .json")


def main():
    print("Generating Spike royalty-free music library...")
    write_track("chill", "midnight_lofi", "Midnight Lofi", "Spike Library", *generate_chill())
    write_track("hype", "neon_pulse", "Neon Pulse", "Spike Library", *generate_hype())
    write_track("funny", "quirky_bounce", "Quirky Bounce", "Spike Library", *generate_funny())
    write_track("dramatic", "cinematic_tension", "Cinematic Tension", "Spike Library", *generate_dramatic())
    write_track("wholesome", "sunny_acoustic", "Sunny Acoustic", "Spike Library", *generate_wholesome())
    print("Music library generated successfully!")


if __name__ == "__main__":
    from typing import Tuple
    main()
