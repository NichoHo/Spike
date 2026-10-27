from src.pipeline.stage9b_captions import slur_intervals


def test_slur_intervals_only_slurs_and_shifted_to_clip_time():
    words = [
        {"word": "fuck", "start": 10.0, "end": 10.3},  # strong profanity is not bleeped
        {"word": "Nigga,", "start": 10.5, "end": 10.9},
    ]
    (a, b), = slur_intervals(words, clip_start=10.0, pad=0.0)
    assert (round(a, 2), round(b, 2)) == (0.5, 0.9)
