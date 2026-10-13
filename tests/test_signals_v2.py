import numpy as np

from src.pipeline.stage6_signals import (
    compute_rage_words,
    compute_voice_jump,
    relative_threshold,
    rms_db_per_second,
)


def test_loud_second_reads_above_quiet():
    sr = 16000
    t = np.arange(sr * 2) / sr
    wave = np.sin(2 * np.pi * 220 * t).astype(np.float32)
    wave[:sr] *= 0.01   # quiet second
    wave[sr:] *= 0.5    # loud second
    db = rms_db_per_second(wave, 2)
    assert db[1] > db[0] + 20


def test_voice_jump_flags_burst_only():
    db = np.full(120, -40.0, dtype=np.float32)
    db[60] = -20.0
    vj = compute_voice_jump(db)
    assert vj[60] == 20.0 and vj[10] == 0.0


def test_rage_words_counts_phrases_and_single():
    words = [{"word": " No", "start": 3.1}, {"word": " are", "start": 10.0},
             {"word": " you", "start": 10.2}, {"word": " serious", "start": 10.4}]
    r = compute_rage_words(words, 20)
    assert r[3] > 0 and r[10] > 0 and r[16] == 0


def test_relative_threshold_top_two_percent():
    s = np.arange(100, dtype=np.float32) / 100
    assert 0.97 <= relative_threshold(s) <= 0.99
