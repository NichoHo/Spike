"""
Re-run stage 7 on the frozen eval VODs with live judge, video judge and editor calls, and score it against the stored
first run and the chat baseline (reports/Eval baseline 9 Twitch VODs.md).

Each VOD's saved inputs (transcript, chat, signals, cached judge answers) are copied to data/eval_rerun/<video id>/.
Nothing is written to the database or to data/videos/. Candidates are collected in memory, so no clips are rendered.
Re-running the script reuses the answers already saved in data/eval_rerun/, so a stop (quota, crash) costs nothing.

    py scripts/eval_stage7.py            # all VODs with saved inputs
    py scripts/eval_stage7.py 2896358710 # one VOD
"""

import json
import shutil
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import numpy as np

from src import gemini_budget
from src.config import DATA_DIR, DEFAULT_GEMINI_MODEL, JUDGE_GEMINI_MODEL
from src.eval_set import EVAL_DIR, chat_preds, find_video_id, label_moments, load_set, rank_preds, score_ranking, spike_preds
from src.profile import load_context
import src.pipeline.stage7_moments as stage7

OUT = DATA_DIR / "eval_rerun"
TOL = 20.0


def main(only=None):
    if not (gemini_budget.left(DEFAULT_GEMINI_MODEL) or gemini_budget.left(JUDGE_GEMINI_MODEL)):
        sys.exit("Gemini's daily quota is used up (it resets at midnight Pacific). Run this after the reset.")
    rows = {}
    for v in load_set():
        if only and v["vod"] != only:
            continue
        vid = find_video_id(v["vod"])
        src = DATA_DIR / "videos" / str(vid) if vid else None
        if not src or not (src / "signals.npz").exists():
            print(f"{v['who']}: no saved inputs, skipped")
            continue
        d = OUT / str(vid)
        d.mkdir(parents=True, exist_ok=True)
        for f in src.iterdir():
            if f.is_file() and f.name != "candidates.json" and not (d / f.name).exists():
                shutil.copy(f, d / f.name)
        (d / "candidates.json").unlink(missing_ok=True)

        read = lambda p: json.loads(p.read_text(encoding="utf-8"))
        meta, transcript, signals = read(d / "meta.json"), read(d / "transcript.json"), read(d / "signal_peaks.json")
        chat = read(EVAL_DIR / v["vod"] / "chat.json")
        crowd = {"comments": [], "clips": [], "emotes": read(d / "emotes.json")}  # clips are the answer key: hidden
        records = []
        stage7.insert_candidate = lambda _vid, c: (records.append(dict(c)), len(records))[1]
        print(f"\n=== {v['who']} (video {vid}) ===")
        stage7.run_stage7_moments(vid, d, meta, transcript, signals, crowd, chat_data=chat, profile_ctx=load_context(vid, d, meta))

        dur = int(v["slice_s"])
        moments = label_moments(read(EVAL_DIR / v["vod"] / "clips.json"), dur)
        arms = {"stored run": spike_preds(vid, None), "stored, spaced": spike_preds(vid),
                "re-run": rank_preds(records, None), "re-run, spaced": rank_preds(records),
                "chat": chat_preds(chat["comments"], dur)}
        for arm, preds in arms.items():
            rows.setdefault(arm, {}).setdefault(v["category"], []).append(score_ranking(preds, moments, TOL)["recall@10"])
        print(f"RESULT {v['who']}: " + "  ".join(f"{a} {rows[a][v['category']][-1]:.1f}" for a in rows))

    print("\nmacro recall@10, loose tolerance (mean of per-category means):")
    for arm, cats in rows.items():
        if cats:
            print(f"  {arm:<16} {np.mean([np.mean(x) for x in cats.values()]):.3f}")


if __name__ == "__main__":
    main(sys.argv[1] if len(sys.argv) > 1 else None)
