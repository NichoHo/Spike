"""
Re-run stage 7 on one frozen eval VOD with a fixed fake judge and every live LLM call blocked, and save the judged
moments as JSON. The fake judge answers from a hash of each window, so two runs of the same code give the same file:
a stage 7 change that must not alter results (a refactor) gives the same file before and after.
The real stream inputs (transcript, signals, chat, cached chunk scan and stream read) come from
data/eval_rerun/<video id>/ (made by scripts/eval_stage7.py) and are copied to a temp folder, so nothing on disk or
in the database changes. It costs no LLM calls.

    py scripts/stage7_snapshot.py 2896358710 data/eval_rerun/snapshot_before.json
"""

import json
import shutil
import sys
import tempfile
import zlib
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from src.config import DATA_DIR
from src.eval_set import EVAL_DIR, find_video_id
from src.models import LLMJudgeResponse, VideoVerdict
from src.profile import load_context
import src.pipeline.stage7_moments as stage7
import src.profile as profile

FIELDS = ("start_s", "end_s", "origin", "status", "status_reason", "humor_type", "raw_llm_score", "text_score",
          "final_score")
HUMOR = ("absurd", "rage", "cringe", "skill", "wholesome", "roast")


def _h(text: str) -> int:
    return zlib.crc32(text.encode("utf-8"))


def fake_judge(lines, comments, sigs, **kw):
    h, n = _h(lines[0]), len(lines)
    mid = max(1, n // 2)
    return LLMJudgeResponse(
        keep=h % 4 != 0, why_funny="fake", humor_type=HUMOR[h % len(HUMOR)], score=h % 101,
        topic_start_line=1, setup_start_line=max(1, mid - 3), payoff_line=mid, reaction_end_line=min(n, mid + 4),
        punchline="p", title="t", hook_text="h", post_caption="c")


def fake_video(meta, start_s, end_s, story, streamer, find_play=False):
    h = _h(f"{start_s:.1f}-{end_s:.1f}")
    return VideoVerdict(visible=h % 5 != 0, standalone=h % 7 != 0, reaction=("peak", "routine", "none")[h % 3],
                        ends_on_reaction=True, score=h % 101, play_start=3.0 if find_play else None)


def main(vod: str, out_path: str) -> None:
    vid = find_video_id(vod)
    src = DATA_DIR / "eval_rerun" / str(vid)
    if not vid or not (src / "transcript.json").exists():
        sys.exit(f"No frozen inputs in {src}: run scripts/eval_stage7.py {vod} once first.")
    live = []

    def blocked(*a, **k):
        live.append(1)
        raise RuntimeError("live LLM call blocked by stage7_snapshot")

    stage7.call_llm_judge = fake_judge
    stage7.video_judge = fake_video
    stage7.generate_content_with_retry = blocked         # chunk scan, when chunk_props.json is missing
    stage7.judge_generate = blocked
    stage7.run_editor = blocked                          # the editor fails over to the pairwise ranking...
    stage7.pairwise_rerank = lambda c, streamer="": c    # ...which keeps the score order
    stage7.store_chat_picks = lambda *a, **k: 0          # it writes to the database
    profile._gemini_json = blocked                       # episodes, when the cached session has none
    records = []
    stage7.insert_candidate = lambda _vid, c: (records.append(dict(c)), len(records))[1]

    read = lambda p: json.loads(p.read_text(encoding="utf-8"))
    with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as tmp:  # Windows: numpy keeps signals.npz open
        d = Path(tmp) / str(vid)
        shutil.copytree(src, d)
        for name in ("candidates.json", "judge_cache.json"):  # the fake judge answers every window
            (d / name).unlink(missing_ok=True)
        meta = read(d / "meta.json")
        stage7.run_stage7_moments(
            vid, d, meta, read(d / "transcript.json"), read(d / "signal_peaks.json"),
            {"comments": [], "clips": [], "emotes": read(d / "emotes.json")},
            chat_data=read(EVAL_DIR / vod / "chat.json"), profile_ctx=load_context(vid, d, meta))
    rows = sorted(({k: r.get(k) for k in FIELDS} for r in records),
                  key=lambda r: (r["start_s"], r["end_s"], r["origin"] or ""))
    Path(out_path).write_text(json.dumps({"live_calls": len(live), "records": rows}, indent=1), encoding="utf-8")
    print(f"{len(rows)} records, {len(live)} blocked live calls -> {out_path}")


if __name__ == "__main__":
    main(sys.argv[1], sys.argv[2])
