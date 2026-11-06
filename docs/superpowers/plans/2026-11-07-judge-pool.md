# Judge Pool Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Run stage 7's LLM calls in parallel on Gemini, with one Claude worker that helps while Gemini is down, without changing results when Gemini is up.

**Architecture:** A new `src/judge_pool.py` runs a list of tasks on 3 Gemini worker threads and 1 Claude worker thread that share one shuffled queue. Stage 7 builds its chunk-scan, judge and video calls as tasks, runs them through the pool, then uses the answers in the original candidate order. Each judged moment records which model judged it, and the ranking compares transcript scores only within one model's group.

**Tech Stack:** Python 3.14, stdlib `threading` and `random`, google-genai, the `claude -p` CLI through `src/claude_cli.run_claude`, SQLite, FastAPI and Jinja2, pytest.

**Spec:** `docs/superpowers/specs/2026-11-07-judge-pool-design.md`

## Global Constraints

- No new dependencies. Threads come from the stdlib `threading` module.
- When Gemini is up, stage 7 output must not change. The snapshot check in Task 7 proves it.
- One moment runs on one provider. A Gemini score and a Claude score are never averaged.
- Video judge calls are Gemini only (`claude_ok=False`).
- Pool calls to Gemini pass `allow_claude=False`, so the old per-call Claude popup never starts from the pool.
- Transcript, chat and comment text stay untrusted data. Do not change the prompts.
- Default setting value: `claude_help` = `down`. Values: `down`, `always`, `off`.
- `GEMINI_LANE_WORKERS = 3`, `CLAUDE_LANE_DAILY_CAP = 100`, `POOL_STALL_S = 1800.0`, probe wait 60 s doubling to 300 s.
- Claude lane model: Haiku (`model="haiku"`), one run per moment. Its `judge_model` value is `claude-haiku`.
- Tests run on a copy of the database (`tests/conftest.py`). Tests must never call the real Gemini API or the real Claude CLI.
- Test command: `py -m pytest tests -q -p no:cacheprovider` (the full suite takes about 5.5 min; 328 passed before this plan).
- Commits: the user's name, sentence-case summary in the repo's style, no Claude co-author lines. Do not push.
- No em dashes or en dashes in UI text.

## File Structure

| File | Change | Responsibility |
|---|---|---|
| `scripts/stage7_snapshot.py` | Create | Run stage 7 on one frozen eval VOD with a fixed fake judge, save the result as JSON |
| `src/judge_pool.py` | Create | The queue, the Gemini and Claude lanes, the down/probe state, the `claude_help` setting |
| `src/config.py` | Modify | Pool constants |
| `tests/conftest.py` | Modify | Turn the Claude lane off in the test database; window-keyed fake judge fixture |
| `src/pipeline/stage7_moments.py` | Modify | `GeminiUnavailable`, `allow_claude`, Claude branches, pool use in the chunk scan, judge and video judge, per-model percentiles |
| `src/db.py` | Modify | `candidates.judge_model` column |
| `src/web/routes/settings.py`, `src/web/templates/pages/settings.html` | Modify | The "Claude help for the judge" select |
| `tests/test_judge_pool.py` | Create | Pool and settings tests |
| `tests/test_judge_v2.py`, `tests/test_editor.py` | Modify | New stage 7 tests; fake judges answer by window, not by call order |

---

### Task 1: Snapshot script and baseline

Record stage 7's output on real stream data **before** any code change, so Task 7 can prove the refactor did not change results.

**Files:**
- Create: `scripts/stage7_snapshot.py`

**Interfaces:**
- Consumes: `data/eval_rerun/57/` (frozen inputs for VOD 2896358710, made by `scripts/eval_stage7.py`), `data/eval/2896358710/chat.json`.
- Produces: `data/eval_rerun/snapshot_before.json`, used in Task 7.

- [ ] **Step 1: Create the script**

```python
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
```

- [ ] **Step 2: Record the baseline on the unchanged code**

Run: `py scripts/stage7_snapshot.py 2896358710 data/eval_rerun/snapshot_before.json`
Expected: last line `85 records, 1 blocked live calls -> data/eval_rerun/snapshot_before.json` (the one blocked call is the episode split, which has no cached answer).

- [ ] **Step 3: Check that it is repeatable**

Run: `py scripts/stage7_snapshot.py 2896358710 data/eval_rerun/snapshot_again.json` then `py -c "import filecmp; print(filecmp.cmp('data/eval_rerun/snapshot_before.json', 'data/eval_rerun/snapshot_again.json', shallow=False))"`
Expected: `True`

- [ ] **Step 4: Commit**

```bash
git add scripts/stage7_snapshot.py
git commit -m "Add a stage 7 snapshot script that replays a frozen eval VOD with a fixed fake judge"
```

---

### Task 2: The judge pool

**Files:**
- Create: `src/judge_pool.py`
- Modify: `src/config.py` (after `MIN_RAW_LLM_SCORE`, line 178)
- Modify: `tests/conftest.py`
- Test: `tests/test_judge_pool.py`

**Interfaces:**
- Consumes: `src.claude_fallback.ask(label, detail, model, kind) -> bool`, `src.db.get_setting/set_setting`, `src.gemini_budget.today() -> str`.
- Produces:
  - `class GeminiUnavailable(RuntimeError)`
  - `@dataclass Task(run: Callable[[str], Any], claude_ok: bool = True)`; `run` is called with `"gemini"` or `"claude"`.
  - `run_pool(tasks, seed=0, label="stage 7", down_errors=(GeminiUnavailable,), on_result=None, gemini_workers=None, stall_s=None) -> List[Tuple[str, Any]]`: `(provider, value)` per task, in task order. `on_result(i: int, provider: str, value: Any)` runs under the pool lock as each task finishes.
  - `help_mode() -> str` (`"down"`, `"always"` or `"off"`), `claude_used_today() -> int`, `HELP_KEY = "claude_help"`, `HELP_MODES`, `CLAUDE_USED_KEY`, module constants `PROBE_START_S`, `PROBE_MAX_S`, `CLAUDE_LANE_DAILY_CAP` (imported from config, patchable on the module).

- [ ] **Step 1: Add the config constants**

In `src/config.py`, after the line `MIN_RAW_LLM_SCORE = 65.0  # Floor to prevent dull VODs from passing`, add:

```python
GEMINI_LANE_WORKERS = 3  # parallel Gemini calls in stage 7 (src/judge_pool.py); use 2 if the free tier answers 429 often
CLAUDE_LANE_DAILY_CAP = 100  # judge pool calls on Claude per day: protects the Pro plan, which the user's own Claude use shares
POOL_STALL_S = 1800.0  # a stage 7 pool with no finished call for this long fails the job
```

- [ ] **Step 2: Keep tests away from the real Claude CLI**

Replace the whole of `tests/conftest.py` with:

```python
"""
Tests run against a throwaway copy of data/spike.db, so test rows never reach the real queue
(a running worker would otherwise pick them up and process them).
"""

import sqlite3
import sys
import tempfile
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import src.db as db

_test_db = Path(tempfile.mkdtemp(prefix="spike_test_")) / "spike.db"
if db.DB_PATH.exists():
    # backup() gives a consistent copy even while the real app has the DB open in WAL mode.
    with sqlite3.connect(db.DB_PATH) as src, sqlite3.connect(_test_db) as dst:
        src.backup(dst)
db.DB_PATH = _test_db
db.init_db()
db.set_setting("claude_help", "off")  # the judge pool never calls the real Claude CLI from a test


@pytest.fixture
def judge_by_window():
    """Stage 7 judges in parallel and in a shuffled order (src/judge_pool.py), so a fake call_llm_judge must answer by
    candidate window, not by call order. A window starts at peak - 90 s, and its first line's time picks the peak.
    make(peaks, answers, build) returns the fake; answers[i] belongs to peaks[i] and build(*answers[i]) makes it."""
    def make(peaks, answers, build):
        def fake(lines, comments, sigs, **kw):
            mm, ss = lines[0].split("[", 1)[1].split("]", 1)[0].split(":")
            t = int(mm) * 60 + float(ss)
            i = min(range(len(peaks)), key=lambda k: abs(max(0.0, peaks[k] - 90.0) - t))
            return build(*answers[i])
        return fake
    return make
```

- [ ] **Step 3: Write the failing tests**

Create `tests/test_judge_pool.py`:

```python
"""Judge pool: stage 7 calls run in parallel on Gemini; Claude helps while Gemini is down (docs/superpowers/specs/
2026-11-07-judge-pool-design.md)."""

import threading
import time

import pytest

from src import judge_pool as jp
from src.db import set_setting


@pytest.fixture(autouse=True)
def fast_pool(monkeypatch):
    monkeypatch.setattr(jp, "PROBE_START_S", 0.01)
    monkeypatch.setattr(jp, "PROBE_MAX_S", 0.04)
    monkeypatch.setattr(jp.claude_fallback, "ask", lambda *a, **k: True)
    set_setting(jp.CLAUDE_USED_KEY, "")
    set_setting(jp.HELP_KEY, "down")
    yield
    set_setting(jp.HELP_KEY, "off")


def test_results_come_back_in_task_order_with_their_provider():
    tasks = [jp.Task(lambda p, i=i: i * 10) for i in range(20)]
    assert jp.run_pool(tasks, seed=1) == [("gemini", i * 10) for i in range(20)]


def test_no_tasks_returns_at_once():
    assert jp.run_pool([], seed=1) == []


def test_claude_never_runs_while_gemini_is_up_in_the_default_mode():
    out = jp.run_pool([jp.Task(lambda p: p) for _ in range(10)], seed=2)
    assert {p for p, _ in out} == {"gemini"}


def test_always_mode_shares_the_work_with_claude():
    set_setting(jp.HELP_KEY, "always")

    def slow(p):
        time.sleep(0.02)
        return p

    out = jp.run_pool([jp.Task(slow) for _ in range(30)], seed=3)
    assert {p for p, _ in out} == {"gemini", "claude"}


def test_gemini_outage_moves_work_to_claude_and_back():
    state = {"down": True, "claude": 0}
    lock = threading.Lock()

    def run(p):
        with lock:
            if p == "gemini" and state["down"]:
                raise jp.GeminiUnavailable("503 unavailable")
            if p == "claude":
                state["claude"] += 1
                if state["claude"] == 3:
                    state["down"] = False  # Gemini recovers
        time.sleep(0.005)
        return p

    out = jp.run_pool([jp.Task(run) for _ in range(40)], seed=4)
    providers = [p for p, _ in out]
    assert len(out) == 40
    assert 3 <= providers.count("claude") < 40 and "gemini" in providers


def test_gemini_only_tasks_wait_for_gemini():
    state = {"n": 0}

    def run(p):
        assert p == "gemini"
        state["n"] += 1
        if state["n"] <= 2:
            raise jp.GeminiUnavailable("503 unavailable")
        return "ok"

    assert jp.run_pool([jp.Task(run, claude_ok=False)], seed=5) == [("gemini", "ok")]


def test_denied_claude_leaves_gemini_to_finish(monkeypatch):
    monkeypatch.setattr(jp.claude_fallback, "ask", lambda *a, **k: False)
    state = {"n": 0}
    lock = threading.Lock()

    def run(p):
        assert p == "gemini"
        with lock:
            state["n"] += 1
            if state["n"] <= 3:
                raise jp.GeminiUnavailable("503 unavailable")
        return p

    out = jp.run_pool([jp.Task(run) for _ in range(6)], seed=6)
    assert {p for p, _ in out} == {"gemini"}


def test_a_claude_error_hands_the_task_back_to_gemini():
    set_setting(jp.HELP_KEY, "always")

    def run(p):
        if p == "claude":
            raise RuntimeError("claude exited 1")
        return p

    out = jp.run_pool([jp.Task(run) for _ in range(8)], seed=7)
    assert {p for p, _ in out} == {"gemini"}


def test_off_with_gemini_down_fails_after_the_stall_limit():
    set_setting(jp.HELP_KEY, "off")

    def run(p):
        raise jp.GeminiUnavailable("503 unavailable")

    with pytest.raises(RuntimeError, match="no call finished"):
        jp.run_pool([jp.Task(run)], seed=8, stall_s=0.3)


def test_claude_lane_stops_at_the_daily_cap(monkeypatch):
    monkeypatch.setattr(jp, "CLAUDE_LANE_DAILY_CAP", 2)
    set_setting(jp.HELP_KEY, "always")

    def run(p):
        if p == "gemini":
            raise jp.GeminiUnavailable("503 unavailable")
        return p

    with pytest.raises(RuntimeError, match="no call finished"):
        jp.run_pool([jp.Task(run) for _ in range(5)], seed=9, stall_s=0.3)
    assert jp.claude_used_today() == 2


def test_a_bug_in_a_gemini_task_stops_the_pool():
    def run(p):
        raise ValueError("bug")

    with pytest.raises(ValueError, match="bug"):
        jp.run_pool([jp.Task(run)], seed=10)


def test_on_result_sees_every_task_once():
    seen = []
    jp.run_pool([jp.Task(lambda p, i=i: i) for i in range(10)], seed=11,
                on_result=lambda i, p, v: seen.append((i, v)))
    assert sorted(seen) == [(i, i) for i in range(10)]


def test_unknown_stored_mode_reads_as_the_default():
    set_setting(jp.HELP_KEY, "bogus")
    assert jp.help_mode() == "down"
```

- [ ] **Step 4: Run the tests to verify they fail**

Run: `py -m pytest tests/test_judge_pool.py -q -p no:cacheprovider`
Expected: FAIL with `ModuleNotFoundError: No module named 'src.judge_pool'`

- [ ] **Step 5: Write the pool**

Create `src/judge_pool.py`:

```python
"""
Spike: the judge pool (docs/superpowers/specs/2026-11-07-judge-pool-design.md).
Stage 7's LLM calls run in parallel on GEMINI_LANE_WORKERS Gemini threads. One Claude thread helps while Gemini is
down (the default), all the time, or never: the "claude_help" setting. One task is one moment and runs on one
provider. Tasks start in a shuffled order, so each provider judges a random sample of the stream, not one stretch.
"""

import random
import threading
import time
from dataclasses import dataclass
from typing import Any, Callable, List, Optional, Sequence, Tuple, Type

from src import claude_fallback
from src.config import CLAUDE_LANE_DAILY_CAP, GEMINI_LANE_WORKERS, POOL_STALL_S
from src.db import get_setting, set_setting
from src.gemini_budget import today

HELP_KEY = "claude_help"
HELP_MODES = ("down", "always", "off")
CLAUDE_USED_KEY = "claude_lane_used"
PROBE_START_S = 60.0  # wait after Gemini goes down before one probe call; each failed probe doubles it
PROBE_MAX_S = 300.0
TICK_S = 0.05  # how often a waiting worker looks again


class GeminiUnavailable(RuntimeError):
    """Gemini answered 503 / unavailable through every retry of one call."""


@dataclass
class Task:
    run: Callable[[str], Any]  # run("gemini") or run("claude") returns the task's value
    claude_ok: bool = True  # False for calls only Gemini can make (the video judge)


def help_mode() -> str:
    """When the Claude lane helps: "down" (default), "always" or "off". An unknown stored value reads as "down"."""
    mode = get_setting(HELP_KEY) or "down"
    return mode if mode in HELP_MODES else "down"


def claude_used_today() -> int:
    day, _, n = (get_setting(CLAUDE_USED_KEY) or "").partition("|")
    return int(n) if day == today() and n.isdigit() else 0


def run_pool(
    tasks: Sequence[Task],
    seed: int = 0,
    label: str = "stage 7",
    down_errors: Tuple[Type[BaseException], ...] = (GeminiUnavailable,),
    on_result: Optional[Callable[[int, str, Any], None]] = None,
    gemini_workers: Optional[int] = None,
    stall_s: Optional[float] = None,
) -> List[Tuple[str, Any]]:
    """Run every task once and return [(provider, value)] in task order.

    A Gemini error in down_errors puts the task back and marks Gemini down; any other Gemini error is a bug and is
    raised. A Claude error puts the task back and stops the Claude lane for this run. on_result(i, provider, value)
    runs under the pool lock as each task finishes. Raises RuntimeError when no task finished for stall_s."""
    gemini_workers = gemini_workers or GEMINI_LANE_WORKERS
    stall_s = POOL_STALL_S if stall_s is None else stall_s
    mode = help_mode()
    order = list(range(len(tasks)))
    random.Random(seed).shuffle(order)
    results: List[Any] = [None] * len(tasks)
    cond = threading.Condition()
    # down_until > 0: Gemini is down or waits for its probe. claude: None = not asked yet, True = go, False = stopped
    st = {"left": len(tasks), "down_until": 0.0, "backoff": PROBE_START_S, "probing": False,
          "claude": True if mode == "always" else None, "error": None, "progress": time.monotonic()}

    def finished() -> bool:
        return st["left"] == 0 or st["error"] is not None

    def finish(i: int, provider: str, value: Any) -> None:  # holds cond
        results[i] = (provider, value)
        st["left"] -= 1
        st["progress"] = time.monotonic()
        if on_result:
            try:
                on_result(i, provider, value)
            except Exception as e:  # a failed cache write stops the run instead of killing a worker silently
                st["error"] = e
        cond.notify_all()

    def gemini_worker() -> None:
        while True:
            with cond:
                while not finished() and not (order and not st["probing"] and time.monotonic() >= st["down_until"]):
                    cond.wait(TICK_S)
                if finished():
                    return
                i = order.pop(0)
                probe = st["down_until"] > 0
                st["probing"] = probe
            try:
                value = tasks[i].run("gemini")
            except down_errors as e:
                with cond:
                    order.insert(0, i)
                    if probe:
                        st["backoff"] = min(st["backoff"] * 2, PROBE_MAX_S)
                    st.update(probing=False, down_until=time.monotonic() + st["backoff"])
                    print(f"  [pool] Gemini is down ({str(e)[:100]}); next try in {st['backoff']:.0f}s")
                    cond.notify_all()
                continue
            except Exception as e:
                with cond:
                    st["error"] = e
                    cond.notify_all()
                return
            with cond:
                if st["down_until"]:
                    print("  [pool] Gemini is back")
                st.update(probing=False, down_until=0.0, backoff=PROBE_START_S)
                finish(i, "gemini", value)

    def claude_turn() -> bool:  # holds cond
        return (mode == "always" or st["down_until"] > 0) and any(tasks[t].claude_ok for t in order)

    def claude_worker() -> None:
        while True:
            with cond:
                while not finished() and st["claude"] is not False and not claude_turn():
                    cond.wait(TICK_S)
                if finished() or st["claude"] is False:
                    return
                ask = st["claude"] is None
            if ask:  # the first help in a run asks once; "Don't ask again today" in the popup skips it
                ok = claude_fallback.ask(f"{label} (Claude Haiku)",
                                         "Gemini is unavailable. Claude judges some moments until it is back.",
                                         None, "overload")
                with cond:
                    st["claude"] = ok
                continue
            if claude_used_today() >= CLAUDE_LANE_DAILY_CAP:
                print(f"  [pool] Claude lane stopped: {CLAUDE_LANE_DAILY_CAP} calls today (CLAUDE_LANE_DAILY_CAP)")
                with cond:
                    st["claude"] = False
                return
            with cond:
                i = next((t for t in order if tasks[t].claude_ok), None)
                if i is None or not (mode == "always" or st["down_until"] > 0):
                    continue
                order.remove(i)
            set_setting(CLAUDE_USED_KEY, f"{today()}|{claude_used_today() + 1}")  # one Claude thread: no race
            try:
                value = tasks[i].run("claude")
            except Exception as e:  # ClaudeError, paused, plan limit: Gemini takes the task back
                with cond:
                    order.insert(0, i)
                    st["claude"] = False
                    print(f"  [pool] Claude lane stopped for this run: {str(e)[:120]}")
                    cond.notify_all()
                return
            with cond:
                finish(i, "claude", value)

    workers = [threading.Thread(target=gemini_worker, daemon=True) for _ in range(gemini_workers)]
    if mode != "off" and any(t.claude_ok for t in tasks):
        # not joined: it can sit in the approval popup for minutes after the work is done
        threading.Thread(target=claude_worker, daemon=True).start()
    for w in workers:
        w.start()
    with cond:
        while not finished():
            if time.monotonic() - st["progress"] > stall_s:
                st["error"] = RuntimeError(
                    f"{label}: no call finished for {stall_s / 60:.0f} min. Gemini is down and Claude cannot help "
                    "(the setting is Off, the popup was denied, Claude is paused or failed, or its daily cap is used up).")
                cond.notify_all()
                break
            cond.wait(TICK_S * 10)
    if st["error"] is not None:
        raise st["error"]
    for w in workers:
        w.join()
    return results
```

- [ ] **Step 6: Run the tests to verify they pass**

Run: `py -m pytest tests/test_judge_pool.py -q -p no:cacheprovider`
Expected: `13 passed`

- [ ] **Step 7: Commit**

```bash
git add src/judge_pool.py src/config.py tests/conftest.py tests/test_judge_pool.py
git commit -m "Add the judge pool: parallel Gemini workers and a Claude worker that helps while Gemini is down"
```

---

### Task 3: Gemini and Claude call plumbing in stage 7

**Files:**
- Modify: `src/pipeline/stage7_moments.py` (imports; `generate_content_with_retry` lines 149-195; `call_llm_judge` lines 718-857; `video_judge` line 932)
- Test: `tests/test_judge_v2.py`

**Interfaces:**
- Consumes: `GeminiUnavailable` from Task 2; `src.claude_cli.run_claude(system, prompt, schema, video_id=None, label="", model="sonnet", images=None) -> dict` and `require_all(schema) -> schema`.
- Produces:
  - `generate_content_with_retry(..., allow_claude: bool = True)`: raises `GeminiUnavailable` (a `RuntimeError`) when 503 lasts through every retry.
  - `call_llm_judge(..., provider: str = "gemini") -> Optional[LLMJudgeResponse]`: re-raises `QuotaExhausted` and `GeminiUnavailable` when it has no answer yet; on `"claude"`, one Haiku run with the strict schema; `ClaudeError` propagates.
  - `video_judge` re-raises `GeminiUnavailable`.

- [ ] **Step 1: Write the failing tests**

In `tests/test_judge_v2.py`, add to the imports:

```python
from src.judge_pool import GeminiUnavailable
```

Append at the end of the file:

```python
def test_503_through_every_retry_raises_gemini_unavailable(monkeypatch):
    monkeypatch.setattr(s7.time, "sleep", lambda s: None)
    with pytest.raises(GeminiUnavailable):
        s7.generate_content_with_retry(_FakeClient("503 unavailable high demand"), "m", "x", None, max_retries=2)


def test_pool_calls_never_start_the_old_claude_popup(monkeypatch):
    monkeypatch.setattr(s7.time, "sleep", lambda s: None)
    monkeypatch.setattr(s7, "claude_instead", lambda *a, **k: pytest.fail("the per-call Claude popup started"))
    quota = "429 RESOURCE_EXHAUSTED quota exceeded. Please retry in 7h33m11s."
    with pytest.raises(s7.QuotaExhausted):
        s7.generate_content_with_retry(_FakeClient(quota), s7.DEFAULT_GEMINI_MODEL, "x", None, allow_claude=False)


def test_judge_hands_a_gemini_outage_to_the_pool(monkeypatch):
    def down(*a, **k):
        raise GeminiUnavailable("503 unavailable")

    monkeypatch.setattr(s7, "get_gemini_client", lambda: None)
    monkeypatch.setattr(s7, "generate_content_with_retry", down)
    with pytest.raises(GeminiUnavailable):
        s7.call_llm_judge(["L1 [00:01.0] hello"], "", {})


def test_judge_on_claude_runs_once_on_haiku_with_the_strict_schema(monkeypatch):
    seen = []
    answer = LLMJudgeResponse(keep=True, why_funny="w", humor_type="absurd", score=72, punchline="p", title="t",
                              hook_text="h", post_caption="c")

    def fake_claude(system, prompt, schema, **kw):
        seen.append((schema, kw.get("model")))
        return answer.model_dump()

    monkeypatch.setattr(s7, "get_gemini_client", lambda: None)
    monkeypatch.setattr("src.claude_cli.run_claude", fake_claude)
    res = s7.call_llm_judge(["L1 [00:01.0] hello"], "", {}, provider="claude")
    assert res.score == 72 and len(seen) == 1
    schema, model = seen[0]
    assert model == "haiku" and set(schema["required"]) == set(LLMJudgeResponse.model_fields)
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `py -m pytest tests/test_judge_v2.py -q -p no:cacheprovider -k "gemini_unavailable or popup or outage or haiku"`
Expected: FAIL. `test_503...` fails because a plain `RuntimeError` is raised; the others fail with `TypeError: ... unexpected keyword argument 'allow_claude'` / `'provider'`.

- [ ] **Step 3: Import the pool names**

In `src/pipeline/stage7_moments.py`, after the line `from src import gemini_budget`, add:

```python
from src.judge_pool import GeminiUnavailable, Task, run_pool
```

- [ ] **Step 4: Raise `GeminiUnavailable` and add `allow_claude`**

In `generate_content_with_retry`, replace the signature line `    claude_model: str = "haiku",` (the last parameter, line 157) with:

```python
    claude_model: str = "haiku",
    allow_claude: bool = True,
```

Replace the docstring:

```python
    """Gemini call with retries. Raises QuotaExhausted for long quota waits and re-raises the last error
    when retries run out (it never returns None). When Flash-Lite, the last Gemini option, is out of quota for
    the day, a text-only call runs on Claude instead, after the user approves it (src/claude_fallback.py)."""
```

with:

```python
    """Gemini call with retries. Raises QuotaExhausted for long quota waits, GeminiUnavailable when 503 lasts through
    every retry, and re-raises any other last error (it never returns None). When Flash-Lite, the last Gemini option,
    is out of quota for the day, a text-only call runs on Claude instead, after the user approves it
    (src/claude_fallback.py). allow_claude=False skips that: the judge pool picks the provider itself."""
```

Replace:

```python
                    if model == DEFAULT_GEMINI_MODEL:
                        out = claude_instead(contents, config, purpose or "a Gemini text call", claude_model)
```

with:

```python
                    if model == DEFAULT_GEMINI_MODEL and allow_claude:
                        out = claude_instead(contents, config, purpose or "a Gemini text call", claude_model)
```

Replace the last line of the function:

```python
    raise RuntimeError(f"Gemini call to {model} failed after {max_retries} attempts: {last_err}")
```

with:

```python
    if last_err is not None and any(s in str(last_err).lower() for s in ("503", "unavailable", "high demand")):
        raise GeminiUnavailable(f"503 unavailable: {model} after {max_retries} attempts: {str(last_err)[:200]}") from last_err
    raise RuntimeError(f"Gemini call to {model} failed after {max_retries} attempts: {last_err}")
```

- [ ] **Step 5: Give the judge a provider**

In `call_llm_judge`, replace the signature lines:

```python
    story: str = "",
) -> Optional[LLMJudgeResponse]:
    """Call the LLM judge (Gemini Flash) to evaluate a candidate clip window (Blueprint §6.3, §6.7)."""
```

with:

```python
    story: str = "",
    provider: str = "gemini",
) -> Optional[LLMJudgeResponse]:
    """Call the LLM judge to evaluate a candidate clip window (Blueprint §6.3, §6.7). provider is the judge pool lane:
    "gemini" (Flash-Lite, two runs averaged) or "claude" (Haiku, one run; the CLI has no temperature setting)."""
```

Replace:

```python
    # Blueprint §6.3: Run twice and average the scores to reduce noise
    responses = []
```

with:

```python
    if provider == "claude":  # a ClaudeError goes to the judge pool, which hands the moment back to Gemini
        from src.claude_cli import require_all, run_claude
        out = run_claude(system_instruction, prompt, require_all(LLMJudgeResponse.model_json_schema()),
                         label="judge one moment", model="haiku")
        try:
            return LLMJudgeResponse.model_validate(out)
        except ValidationError as e:
            print(f"  [stage 7] Claude judge answer did not fit the schema: {e}")
            return None

    # Blueprint §6.3: Run twice and average the scores to reduce noise
    responses = []
```

Inside the `for _ in range(2):` loop, replace:

```python
                purpose="score one candidate moment" + (f" near {formatted_lines[0].split(']')[0].split('[')[-1]}" if formatted_lines else ""),
            )
            responses.append(LLMJudgeResponse.model_validate_json(resp.text))
        except QuotaExhausted:
            raise
```

with:

```python
                purpose="score one candidate moment" + (f" near {formatted_lines[0].split(']')[0].split('[')[-1]}" if formatted_lines else ""),
                allow_claude=False,
            )
            responses.append(LLMJudgeResponse.model_validate_json(resp.text))
        except (QuotaExhausted, GeminiUnavailable):
            if not responses:
                raise  # the judge pool waits for Gemini or gives the moment to Claude
            break  # keep the one answer: the pool must not judge this moment again
```

- [ ] **Step 6: Let the video judge hand outages to the pool**

In `video_judge`, replace:

```python
        return VideoVerdict.model_validate_json(resp.text)
    except QuotaExhausted:
        raise
```

with:

```python
        return VideoVerdict.model_validate_json(resp.text)
    except (QuotaExhausted, GeminiUnavailable):
        raise  # the judge pool waits for Gemini: Claude cannot watch video
```

- [ ] **Step 7: Run the tests to verify they pass**

Run: `py -m pytest tests/test_judge_v2.py tests/test_layout_ai.py tests/test_claude_fallback.py -q -p no:cacheprovider`
Expected: all pass.

- [ ] **Step 8: Commit**

```bash
git add src/pipeline/stage7_moments.py tests/test_judge_v2.py
git commit -m "Raise GeminiUnavailable after 503 retries and let the judge run on Claude Haiku for the judge pool"
```

---

### Task 4: Judge every moment through the pool and record its judge

**Files:**
- Modify: `src/db.py` (migration list near line 271; `insert_candidate` lines 561-605)
- Modify: `src/pipeline/stage7_moments.py` (new helpers next to `percentile_avg_rank`; judge loop lines 1248-1286; record dict line 1327; percentiles lines 1367 and 1402)
- Modify: `tests/test_judge_v2.py`, `tests/test_editor.py` (fake judges answer by window)
- Test: `tests/test_judge_v2.py`

**Interfaces:**
- Consumes: `run_pool`, `Task`, `GeminiUnavailable` (Task 2); `call_llm_judge(..., provider=)` (Task 3); fixture `judge_by_window` (Task 2, `tests/conftest.py`).
- Produces:
  - `CLAUDE_JUDGE = "claude-haiku"`, `judge_model_name(provider: str) -> str`
  - `percentile_by_group(values: List[float], groups: List[str]) -> List[float]`
  - every judged record and DB candidate row carries `judge_model`; judge cache entries carry `"judge_model"`.

- [ ] **Step 1: Make the existing stage 7 tests independent of call order**

In `tests/test_judge_v2.py`, in `test_stage7_stores_every_judged_candidate`, change the signature to:

```python
def test_stage7_stores_every_judged_candidate(tmp_path, monkeypatch, judge_by_window):
```

and replace:

```python
    # judge answers in order: great, mediocre, not funny, plain rage with no contrast
    answers = iter([(80, True, "absurd"), (60, True, "absurd"), (30, False, "other"), (90, True, "rage")])

    def fake_judge(lines, comments, sigs, **kw):
        score, keep, humor = next(answers)
        return LLMJudgeResponse(keep=keep, why_funny="because", humor_type=humor, score=score, topic_start_line=8, setup_start_line=10,
                                payoff_line=18, reaction_end_line=22,
                                punchline="p", title="The streamer loses", hook_text="h", post_caption="c")

    monkeypatch.setattr(s7, "call_llm_judge", fake_judge)
```

with:

```python
    # judge answers per peak: great, mediocre, not funny, plain rage with no contrast
    answers = [(80, True, "absurd"), (60, True, "absurd"), (30, False, "other"), (90, True, "rage")]

    def build(score, keep, humor):
        return LLMJudgeResponse(keep=keep, why_funny="because", humor_type=humor, score=score, topic_start_line=8, setup_start_line=10,
                                payoff_line=18, reaction_end_line=22,
                                punchline="p", title="The streamer loses", hook_text="h", post_caption="c")

    monkeypatch.setattr(s7, "call_llm_judge", judge_by_window([60, 140, 220, 300], answers, build))
```

In `tests/test_editor.py`, replace:

```python
def _patch_stage7(monkeypatch, scores):
    answers = iter(scores)

    def fake_judge(lines, comments, sigs, **kw):
        score, humor = next(answers)
        return LLMJudgeResponse(keep=True, why_funny="because", humor_type=humor, score=score, topic_start_line=30,
                                setup_start_line=32, payoff_line=45, reaction_end_line=48, punchline="p",
                                title="Speed loses", hook_text="h", post_caption="c", contrast=True)

    monkeypatch.setattr(s7, "call_llm_judge", fake_judge)
```

with:

```python
def _patch_stage7(monkeypatch, scores, judge_by_window):
    def build(score, humor):
        return LLMJudgeResponse(keep=True, why_funny="because", humor_type=humor, score=score, topic_start_line=30,
                                setup_start_line=32, payoff_line=45, reaction_end_line=48, punchline="p",
                                title="Speed loses", hook_text="h", post_caption="c", contrast=True)

    # scores[i] belongs to the i-th peak of _stage7_inputs; stage 7 judges in parallel, so not in call order
    monkeypatch.setattr(s7, "call_llm_judge", judge_by_window([200, 400, 1300, 1700], scores, build))
```

Then update the two callers. Replace:

```python
def test_stage7_stores_a_story_with_segment_ids_and_marks_its_components(tmp_path, monkeypatch):
    vid, transcript, peaks = _stage7_inputs(tmp_path)
    _patch_stage7(monkeypatch, [(80, "rage"), (75, "rage"), (70, "absurd"), (90, "rage")])
```

with:

```python
def test_stage7_stores_a_story_with_segment_ids_and_marks_its_components(tmp_path, monkeypatch, judge_by_window):
    vid, transcript, peaks = _stage7_inputs(tmp_path)
    _patch_stage7(monkeypatch, [(80, "rage"), (75, "rage"), (70, "absurd"), (90, "rage")], judge_by_window)
```

and, in the second test at line 311 (open the file to read its name), add `judge_by_window` as the last parameter of its signature and replace:

```python
    _patch_stage7(monkeypatch, [(80, "absurd"), (75, "cringe"), (70, "roast"), (90, "deadpan")])
```

with:

```python
    _patch_stage7(monkeypatch, [(80, "absurd"), (75, "cringe"), (70, "roast"), (90, "deadpan")], judge_by_window)
```

Run: `py -m pytest tests/test_judge_v2.py tests/test_editor.py -q -p no:cacheprovider`
Expected: all pass (the code still judges in order; the fakes now work for any order).

- [ ] **Step 2: Write the failing tests**

In `tests/test_judge_v2.py`, add to the imports:

```python
from src import judge_pool
from src.db import set_setting
```

Append:

```python
def test_percentiles_rank_each_judge_against_itself():
    vals, groups = [10, 20, 30, 70, 80, 90], ["g", "g", "g", "c", "c", "c"]
    assert s7.percentile_by_group(vals, groups) == s7.percentile_avg_rank([10, 20, 30]) * 2
    assert s7.percentile_by_group([5, 1, 3], ["g", "g", "g"]) == s7.percentile_avg_rank([5, 1, 3])


def test_stage7_judges_on_claude_while_gemini_is_down_and_stores_the_judge(tmp_path, monkeypatch):
    init_db()
    vid = register_video("url", f"https://example.test/{tmp_path.name}")
    transcript = {"duration": 400, "segments": [
        {"start": i * 2.0, "end": i * 2.0 + 2.0, "text": f"line {i}", "words": []} for i in range(200)]}
    peaks = [{"peak_t": float(t), "signal_score_raw": 1.0, "context_start": t - 40.0, "context_end": t + 40.0,
              "clip_start": t - 10.0, "clip_end": t + 10.0, "origin": "signal", "signals_at_peak": {}}
             for t in (60, 140, 220, 300)]

    def judge(lines, comments, sigs, provider="gemini", **kw):
        if provider == "gemini":
            raise GeminiUnavailable("503 unavailable")
        return LLMJudgeResponse(keep=True, why_funny="w", humor_type="absurd", score=70, topic_start_line=8,
                                setup_start_line=10, payoff_line=18, reaction_end_line=22, punchline="p",
                                title="t", hook_text="h", post_caption="c")

    monkeypatch.setattr(s7, "call_llm_judge", judge)
    monkeypatch.setattr(s7, "read_whole_stream", lambda *a, **k: ("", []))
    monkeypatch.setattr(s7, "propose_transcript_chunks", lambda *a, **k: [])
    monkeypatch.setattr(s7, "build_episodes", lambda *a, **k: [])
    monkeypatch.setattr(s7, "pairwise_rerank", lambda c, name="": c)
    monkeypatch.setattr("src.editor.run_claude", lambda *a, **k: (_ for _ in ()).throw(RuntimeError("no editor in this test")))
    monkeypatch.setattr(judge_pool, "PROBE_START_S", 0.01)
    monkeypatch.setattr(judge_pool, "PROBE_MAX_S", 0.02)
    monkeypatch.setattr(judge_pool.claude_fallback, "ask", lambda *a, **k: True)
    set_setting(judge_pool.CLAUDE_USED_KEY, "")
    set_setting(judge_pool.HELP_KEY, "down")
    try:
        s7.run_stage7_moments(vid, tmp_path, {"duration": 400, "webpage_url": ""}, transcript,
                              {"peaks": peaks, "has_chat": False}, [])
    finally:
        set_setting(judge_pool.HELP_KEY, "off")
    rows = [r for r in get_candidates(vid) if r["status"] != "hubris"]
    assert len(rows) == 4 and {r["judge_model"] for r in rows} == {"claude-haiku"}
    cache = json.loads((tmp_path / "judge_cache.json").read_text())
    assert {v["judge_model"] for k, v in cache.items() if k.startswith("v3:")} == {"claude-haiku"}
```

- [ ] **Step 3: Run the tests to verify they fail**

Run: `py -m pytest tests/test_judge_v2.py -q -p no:cacheprovider -k "percentiles_rank or stores_the_judge"`
Expected: FAIL with `AttributeError: module 'src.pipeline.stage7_moments' has no attribute 'percentile_by_group'`, and the stage 7 test fails because the serial loop drops every moment (`Judge failed for 4 of 4 candidates`).

- [ ] **Step 4: Add the `judge_model` column**

In `src/db.py`, in `migration_statements`, after the line `"ALTER TABLE candidates ADD COLUMN status_reason TEXT",  # why a candidate is low_score or rejected`, add:

```python
            "ALTER TABLE candidates ADD COLUMN judge_model TEXT",  # model that judged the transcript (src/judge_pool.py); NULL before it
```

In `insert_candidate`, replace:

```python
                hashtags, reason, mood, needs_context, status, humor_type, why_funny, status_reason, cuts, payoff_t, segments, zooms, concept, concept_spec
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
```

with:

```python
                hashtags, reason, mood, needs_context, status, humor_type, why_funny, status_reason, cuts, payoff_t, segments, zooms, concept, concept_spec, judge_model
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
```

and replace:

```python
                json.dumps(cand["concept_spec"]) if cand.get("concept_spec") else None,
            )
        )
        return cur.fetchone()[0]
```

with:

```python
                json.dumps(cand["concept_spec"]) if cand.get("concept_spec") else None,
                cand.get("judge_model"),
            )
        )
        return cur.fetchone()[0]
```

- [ ] **Step 5: Add the helpers**

In `src/pipeline/stage7_moments.py`, directly after the `percentile_avg_rank` function, add:

```python
def percentile_by_group(values: List[float], groups: List[str]) -> List[float]:
    """percentile_avg_rank within each group. Gemini and Claude score on different scales, and the judge pool gives
    each a random sample of moments, so a moment is ranked against moments of its own judge."""
    out = [0.0] * len(values)
    for g in set(groups):
        idx = [i for i, x in enumerate(groups) if x == g]
        for i, p in zip(idx, percentile_avg_rank([values[i] for i in idx])):
            out[i] = p
    return out


CLAUDE_JUDGE = "claude-haiku"  # judge_model of a moment the judge pool's Claude lane judged


def judge_model_name(provider: str) -> str:
    return CLAUDE_JUDGE if provider == "claude" else DEFAULT_GEMINI_MODEL
```

- [ ] **Step 6: Judge through the pool**

In `run_stage7_moments`, replace this block (from the `for` line through the first `continue` after `if not judge_res:`):

```python
    for cand_idx, cand in enumerate(all_candidates, 1):
        peak_t = cand.get("peak_t", (cand["context_start"] + cand["context_end"]) / 2.0)
        ctx_st, ctx_et = max(0.0, peak_t - 90.0), min(duration_s, peak_t + 45.0)  # [p-90, p+45]

        lines, line_meta = build_annotated_lines(segments, ctx_st, ctx_et, signals_npz_path)
        if not lines:
            continue

        # Extract crowd/chat reaction in this window
        if has_chat and chat_comments:
            comments_str = format_chat_excerpt(
                chat_comments, peak_t, chat_offset_s=chat_offset_s, window_s=15.0
            )
        else:
            relevant_comments = [
                f"- {c['text']}" for c in yt_comments
                if any(ctx_st <= ts <= ctx_et for ts in c.get("timestamps", []))
            ][:10]
            comments_str = "\n".join(relevant_comments)

        print(f"  [stage 7] Judging candidate {cand_idx}/{len(all_candidates)} ({format_timestamp(ctx_st)}-{format_timestamp(ctx_et)})...")
        # Judge answers are saved as they come in, so a retry after a crash or quota stop does not ask again
        cache_key = f"v3:{ctx_st:.1f}-{ctx_et:.1f}"  # v3: answers from the funny-only prompt are not reused
        if cache_key in judge_cache:
            judge_res = LLMJudgeResponse.model_validate(judge_cache[cache_key])
        else:
            judge_res = call_llm_judge(
                lines, comments_str, cand.get("signals_at_peak", {}), has_chat=has_chat,
                music_catalog=music_catalog, creator_block=creator_block, streamer=streamer, story=story,
            )
            if judge_res:
                judge_cache[cache_key] = judge_res.model_dump()
                judge_cache_path.write_text(json.dumps(judge_cache), encoding="utf-8")

        if not judge_res:
            unjudged += 1
            continue
```

with:

```python
    # Each candidate's window, transcript lines and chat excerpt
    prepared = []
    for cand in all_candidates:
        peak_t = cand.get("peak_t", (cand["context_start"] + cand["context_end"]) / 2.0)
        ctx_st, ctx_et = max(0.0, peak_t - 90.0), min(duration_s, peak_t + 45.0)  # [p-90, p+45]

        lines, line_meta = build_annotated_lines(segments, ctx_st, ctx_et, signals_npz_path)
        if not lines:
            continue

        # Extract crowd/chat reaction in this window
        if has_chat and chat_comments:
            comments_str = format_chat_excerpt(
                chat_comments, peak_t, chat_offset_s=chat_offset_s, window_s=15.0
            )
        else:
            relevant_comments = [
                f"- {c['text']}" for c in yt_comments
                if any(ctx_st <= ts <= ctx_et for ts in c.get("timestamps", []))
            ][:10]
            comments_str = "\n".join(relevant_comments)
        prepared.append({"cand": cand, "lines": lines, "line_meta": line_meta, "comments": comments_str,
                         "window": f"{format_timestamp(ctx_st)}-{format_timestamp(ctx_et)}",
                         "key": f"v3:{ctx_st:.1f}-{ctx_et:.1f}"})  # v3: answers from the funny-only prompt are not reused

    # Judge the windows with no saved answer, in parallel on Gemini and Claude (src/judge_pool.py). Answers are saved
    # as they come in, so a retry after a crash or quota stop does not ask again.
    todo = [p for p in prepared if p["key"] not in judge_cache]

    def judge_one(p: Dict[str, Any], provider: str) -> Optional[LLMJudgeResponse]:
        print(f"  [stage 7] Judging {p['window']} on {provider}...")
        return call_llm_judge(
            p["lines"], p["comments"], p["cand"].get("signals_at_peak", {}), has_chat=has_chat,
            music_catalog=music_catalog, creator_block=creator_block, streamer=streamer, story=story, provider=provider,
        )

    def save_judge(i: int, provider: str, res: Optional[LLMJudgeResponse]) -> None:
        if res:
            judge_cache[todo[i]["key"]] = {**res.model_dump(), "judge_model": judge_model_name(provider)}
            judge_cache_path.write_text(json.dumps(judge_cache), encoding="utf-8")

    print(f"  [stage 7] Judging {len(todo)} of {len(prepared)} candidates ({len(prepared) - len(todo)} answers saved)...")
    run_pool([Task(lambda prov, p=p: judge_one(p, prov)) for p in todo], seed=video_id, label="judge calls",
             down_errors=(QuotaExhausted, GeminiUnavailable), on_result=save_judge)

    # In the original candidate order, so the result never depends on which call finished first
    for p in prepared:
        cand, lines, line_meta = p["cand"], p["lines"], p["line_meta"]
        entry = judge_cache.get(p["key"])
        if not entry:
            unjudged += 1
            continue
        judge_res = LLMJudgeResponse.model_validate(entry)
```

The rest of the loop body (from `edges = compute_edges(line_meta, judge_res, preset, series)` to `evaluated.append(record)`) stays as it is.

- [ ] **Step 7: Store the judge on each record**

In the `record = {...}` dict, replace:

```python
            "crowd": bool(cand.get("crowd")),
        }
```

with:

```python
            "crowd": bool(cand.get("crowd")),
            "judge_model": entry.get("judge_model", DEFAULT_GEMINI_MODEL),  # answers saved before the pool are Gemini's
        }
```

- [ ] **Step 8: Rank transcript scores within each judge**

Replace:

```python
        evaluated, percentile_avg_rank([c["text_score"] for c in evaluated]),
```

with:

```python
        evaluated, percentile_by_group([c["text_score"] for c in evaluated], [c["judge_model"] for c in evaluated]),
```

and replace:

```python
        txt_pcts = percentile_avg_rank([c["text_score"] for c in evaluated])
```

with:

```python
        txt_pcts = percentile_by_group([c["text_score"] for c in evaluated], [c["judge_model"] for c in evaluated])
```

- [ ] **Step 9: Run the tests to verify they pass**

Run: `py -m pytest tests/test_judge_v2.py tests/test_editor.py tests/test_judge_pool.py -q -p no:cacheprovider`
Expected: all pass.

- [ ] **Step 10: Commit**

```bash
git add src/db.py src/pipeline/stage7_moments.py tests/test_judge_v2.py tests/test_editor.py
git commit -m "Judge stage 7 moments through the pool, store which model judged each, and rank within each judge"
```

---

### Task 5: Chunk scan and video judge through the pool

**Files:**
- Modify: `src/pipeline/stage7_moments.py` (`propose_transcript_chunks` lines 400-481; its call at line 1199; the video loop lines 1371-1389)
- Test: `tests/test_judge_v2.py`

**Interfaces:**
- Consumes: `run_pool`, `Task`, `GeminiUnavailable`; `run_claude`.
- Produces: `propose_transcript_chunks(..., story="", seed: int = 0)`; `CHUNK_SCHEMA` (dict). Video tasks use `claude_ok=False`.

- [ ] **Step 1: Write the failing tests**

Append to `tests/test_judge_v2.py`:

```python
def test_chunk_scan_runs_on_claude_while_gemini_is_down(monkeypatch):
    transcript = {"segments": [{"start": i * 2.0, "end": i * 2.0 + 2.0, "text": f"line {i}", "words": []}
                               for i in range(150)]}

    def down(*a, **k):
        raise GeminiUnavailable("503 unavailable")

    seen = []

    def fake_claude(system, prompt, schema, **kw):
        seen.append(schema)
        return {"moments": [{"start_line": 3, "end_line": 12, "topic": "a bit"}], "hubris": []}

    monkeypatch.setattr(s7, "get_gemini_client", lambda: None)
    monkeypatch.setattr(s7, "generate_content_with_retry", down)
    monkeypatch.setattr("src.claude_cli.run_claude", fake_claude)
    monkeypatch.setattr(judge_pool, "PROBE_START_S", 0.01)
    monkeypatch.setattr(judge_pool, "PROBE_MAX_S", 0.02)
    monkeypatch.setattr(judge_pool.claude_fallback, "ask", lambda *a, **k: True)
    set_setting(judge_pool.CLAUDE_USED_KEY, "")
    set_setting(judge_pool.HELP_KEY, "down")
    try:
        props = s7.propose_transcript_chunks(transcript, 300.0)
    finally:
        set_setting(judge_pool.HELP_KEY, "off")
    assert props and all(p["type"] == "moment" for p in props)
    assert seen and seen[0] is s7.CHUNK_SCHEMA


def test_video_judge_waits_for_gemini_instead_of_skipping(monkeypatch):
    calls = []

    def flaky(meta, start_s, end_s, story, streamer, find_play=False):
        calls.append(start_s)
        if len(calls) == 1:
            raise GeminiUnavailable("503 unavailable")
        return VideoVerdict(visible=True, standalone=True, reaction="peak", ends_on_reaction=True, score=80)

    monkeypatch.setattr(s7, "video_judge", flaky)
    monkeypatch.setattr(judge_pool, "PROBE_START_S", 0.01)
    out = s7.run_pool([s7.Task(lambda p: s7.video_judge({}, 1.0, 20.0, "", ""), claude_ok=False)], seed=1,
                      down_errors=(s7.QuotaExhausted, GeminiUnavailable))
    assert out[0][0] == "gemini" and out[0][1].score == 80 and len(calls) == 2
```

Also add `VideoVerdict` to the `src.models` import at the top of `tests/test_judge_v2.py` if it is not there yet (it is used by the existing play-start test, so check first).

- [ ] **Step 2: Run the tests to verify they fail**

Run: `py -m pytest tests/test_judge_v2.py -q -p no:cacheprovider -k "chunk_scan_runs_on_claude or waits_for_gemini"`
Expected: the chunk test FAILS (the serial loop catches the outage and returns no proposals, and `CHUNK_SCHEMA` does not exist). The video test passes already (it tests the pool with the Task 3 change); keep it as a guard.

- [ ] **Step 3: Run the chunk scan through the pool**

In `src/pipeline/stage7_moments.py`, directly before `def propose_transcript_chunks(`, add:

```python
_LINE_SPAN = {"type": "object", "properties": {"start_line": {"type": "integer"}, "end_line": {"type": "integer"},
                                               "topic": {"type": "string"}},
              "required": ["start_line", "end_line", "topic"]}
CHUNK_SCHEMA = {"type": "object", "properties": {"moments": {"type": "array", "items": _LINE_SPAN},
                                                 "hubris": {"type": "array", "items": _LINE_SPAN}},
                "required": ["moments", "hubris"]}  # the chunk scan's answer, for the judge pool's Claude lane
```

Change the signature end of `propose_transcript_chunks` from:

```python
    story: str = "",
) -> List[Dict[str, Any]]:
    """Propose candidate moments by scanning 5-minute chunks with 1-minute overlap (§6.7).
    Each chunk is sent whole, with the same audio markers the judge sees, plus the whole-stream story."""
```

to:

```python
    story: str = "",
    seed: int = 0,
) -> List[Dict[str, Any]]:
    """Propose candidate moments by scanning 5-minute chunks with 1-minute overlap (§6.7).
    Each chunk is sent whole, with the same audio markers the judge sees, plus the whole-stream story.
    The chunks run in parallel through the judge pool; seed sets the pool's shuffle."""
```

Replace `    proposals = []` (the line after `overlap = 60`) with `    specs = []  # (chunk start, chunk end, prompt, line metadata)`.

The prompt text stays the same. Replace everything from the line `        try:` that follows the prompt's closing `"""` down to the end of the function:

```python
        try:
            for attempt in range(2):  # Flash-Lite sometimes returns malformed JSON; one retry
                resp = generate_content_with_retry(
                    client=client,
                    model=DEFAULT_GEMINI_MODEL,
                    contents=prompt,
                    config=types.GenerateContentConfig(
                        response_mime_type="application/json"
                    ),
                    purpose=f"scan the transcript from {format_timestamp(curr_start)} to {format_timestamp(curr_end)} for moments",
                )
                try:
                    data = json.loads(resp.text)
                    break
                except (ValueError, TypeError):
                    if attempt == 1:
                        raise
            for kind, key in (("moment", "moments"), ("hubris", "hubris")):
                for m in data.get(key, []) or []:
                    p = line_proposal(m, line_meta, video_duration, kind)
                    if p:
                        proposals.append(p)
        except QuotaExhausted:
            raise
        except Exception as e:
            print(f"  [stage 7] Note: chunk proposal at {curr_start}s skipped: {e}")

        curr_start += (chunk_len - overlap)

    return proposals
```

with:

```python
        specs.append((curr_start, curr_end, prompt, line_meta))
        curr_start += (chunk_len - overlap)

    def scan(spec, provider: str) -> Optional[Dict[str, Any]]:
        start, end, prompt, _ = spec
        purpose = f"scan the transcript from {format_timestamp(start)} to {format_timestamp(end)} for moments"
        if provider == "claude":  # a ClaudeError goes to the judge pool, which hands the chunk back to Gemini
            from src.claude_cli import run_claude
            return run_claude("Follow the task and answer with the JSON it asks for.", prompt, CHUNK_SCHEMA,
                              label=purpose[:80], model="haiku")
        try:
            for attempt in range(2):  # Flash-Lite sometimes returns malformed JSON; one retry
                resp = generate_content_with_retry(
                    client=client,
                    model=DEFAULT_GEMINI_MODEL,
                    contents=prompt,
                    config=types.GenerateContentConfig(response_mime_type="application/json"),
                    purpose=purpose,
                    allow_claude=False,
                )
                try:
                    return json.loads(resp.text)
                except (ValueError, TypeError):
                    if attempt == 1:
                        raise
        except (QuotaExhausted, GeminiUnavailable):
            raise  # the judge pool waits for Gemini or gives the chunk to Claude
        except Exception as e:
            print(f"  [stage 7] Note: chunk proposal at {start}s skipped: {e}")
        return None

    results = run_pool([Task(lambda prov, s=s: scan(s, prov)) for s in specs], seed=seed, label="chunk scan",
                       down_errors=(QuotaExhausted, GeminiUnavailable))
    proposals = []
    for (_, _, _, line_meta), (_, data) in zip(specs, results):
        for kind, key in (("moment", "moments"), ("hubris", "hubris")):
            for m in (data or {}).get(key, []) or []:
                p = line_proposal(m, line_meta, video_duration, kind)
                if p:
                    proposals.append(p)
    return proposals
```

In `run_stage7_moments`, replace:

```python
        chunk_props = propose_transcript_chunks(transcript, duration_s, video_dir / "signals.npz", meta, profile_ctx, story)
```

with:

```python
        chunk_props = propose_transcript_chunks(transcript, duration_s, video_dir / "signals.npz", meta, profile_ctx, story,
                                                seed=video_id)
```

- [ ] **Step 4: Run the video judge through the pool**

In `run_stage7_moments`, replace:

```python
    watched = 0
    shortlist, _ = dedupe(sorted(evaluated, key=lambda c: (c["crowd"], blend[id(c)]), reverse=True), gap_s=PICK_SPACING_S)
    for c in shortlist[:VIDEO_POOL]:
        find_play = c.get("humor_type") == "skill"
        watch_st = max(0.0, c["start_s"] - PLAY_LEAD_S) if find_play else c["start_s"]
        key = f"video:{watch_st:.1f}-{c['end_s']:.1f}"
        if key in judge_cache:
            verdict = VideoVerdict.model_validate(judge_cache[key])
        else:
            print(f"  [stage 7] Watching {format_timestamp(watch_st)}-{format_timestamp(c['end_s'])}...")
            verdict = video_judge(meta, watch_st, c["end_s"], story, streamer, find_play)
            if verdict:
                judge_cache[key] = verdict.model_dump()
                judge_cache_path.write_text(json.dumps(judge_cache), encoding="utf-8")
        if verdict:
            apply_video_verdict(c, verdict, baseline, c["contrast"])
```

with:

```python
    watched = 0
    shortlist, _ = dedupe(sorted(evaluated, key=lambda c: (c["crowd"], blend[id(c)]), reverse=True), gap_s=PICK_SPACING_S)
    to_watch = []  # (candidate, skill clip, watch start, cache key)
    for c in shortlist[:VIDEO_POOL]:
        find_play = c.get("humor_type") == "skill"
        watch_st = max(0.0, c["start_s"] - PLAY_LEAD_S) if find_play else c["start_s"]
        to_watch.append((c, find_play, watch_st, f"video:{watch_st:.1f}-{c['end_s']:.1f}"))
    todo_v = [w for w in to_watch if w[3] not in judge_cache]

    def watch_one(w, provider: str) -> Optional[VideoVerdict]:
        c, find_play, watch_st, _ = w
        print(f"  [stage 7] Watching {format_timestamp(watch_st)}-{format_timestamp(c['end_s'])}...")
        return video_judge(meta, watch_st, c["end_s"], story, streamer, find_play)

    def save_video(i: int, provider: str, verdict: Optional[VideoVerdict]) -> None:
        if verdict:
            judge_cache[todo_v[i][3]] = verdict.model_dump()
            judge_cache_path.write_text(json.dumps(judge_cache), encoding="utf-8")

    # Gemini only (Claude cannot watch video): an outage waits for Gemini instead of skipping the clip
    run_pool([Task(lambda prov, w=w: watch_one(w, prov), claude_ok=False) for w in todo_v], seed=video_id,
             label="video judge calls", down_errors=(QuotaExhausted, GeminiUnavailable), on_result=save_video)
    for c, find_play, watch_st, key in to_watch:
        verdict = VideoVerdict.model_validate(judge_cache[key]) if key in judge_cache else None
        if verdict:
            apply_video_verdict(c, verdict, baseline, c["contrast"])
```

The lines after it (`            if find_play and verdict.play_start is not None:` through `            watched += 1`) stay as they are; they are still inside the new `for` loop at the same indentation.

- [ ] **Step 5: Run the tests to verify they pass**

Run: `py -m pytest tests/test_judge_v2.py tests/test_editor.py tests/test_judge_pool.py tests/test_step7.py -q -p no:cacheprovider`
Expected: all pass.

- [ ] **Step 6: Commit**

```bash
git add src/pipeline/stage7_moments.py tests/test_judge_v2.py
git commit -m "Run the chunk scan and the video judge through the judge pool"
```

---

### Task 6: "Claude help for the judge" setting

**Files:**
- Modify: `src/web/routes/settings.py`
- Modify: `src/web/templates/pages/settings.html` (after the Discord card, line 30)
- Test: `tests/test_judge_pool.py`

**Interfaces:**
- Consumes: `HELP_KEY`, `HELP_MODES`, `help_mode()` from `src/judge_pool.py`; `CLAUDE_LANE_DAILY_CAP` from config.
- Produces: `POST /settings/claude-help` with form field `mode`.

- [ ] **Step 1: Write the failing test**

Append to `tests/test_judge_pool.py`:

```python
def test_settings_saves_only_known_claude_help_modes():
    from starlette.testclient import TestClient
    from src.web.app import app

    client = TestClient(app)
    client.post("/settings/claude-help", data={"mode": "always"}, follow_redirects=False)
    assert jp.help_mode() == "always"
    client.post("/settings/claude-help", data={"mode": "everything"}, follow_redirects=False)
    assert jp.help_mode() == "always"  # an unknown value from the form is ignored
    page = client.get("/settings").text
    assert "Claude help for the judge" in page and '<option value="always" selected>' in page
```

- [ ] **Step 2: Run the test to verify it fails**

Run: `py -m pytest tests/test_judge_pool.py -q -p no:cacheprovider -k settings`
Expected: FAIL (`405 Method Not Allowed` leaves the mode at `down`).

- [ ] **Step 3: Add the route**

In `src/web/routes/settings.py`, add to the `from src.config import (` list:

```python
    CLAUDE_LANE_DAILY_CAP,
```

After `from src import platform_auth`, add:

```python
from src.judge_pool import HELP_KEY, HELP_MODES, help_mode
```

In `settings_page`, add two entries to the `context={...}` dict, after `"accounts_error": request.query_params.get("error", ""),`:

```python
            "claude_help": help_mode(),
            "claude_lane_cap": CLAUDE_LANE_DAILY_CAP,
```

After the `save_discord_webhook` route, add:

```python
@router.post("/settings/claude-help")
async def save_claude_help(
    mode: str = Form("down"),
    user: Dict[str, Any] = Depends(require_admin),
):
    if mode in HELP_MODES:  # form values are untrusted: only the three known modes are stored
        set_setting(HELP_KEY, mode)
    return RedirectResponse(url="/settings", status_code=HTTP_303_SEE_OTHER)
```

- [ ] **Step 4: Add the card**

In `src/web/templates/pages/settings.html`, after the closing `</form>` of the Discord card (line 30), add:

```html

  <!-- Judge pool: when Claude helps Gemini judge moments -->
  <form method="post" action="/settings/claude-help" class="card">
    <div class="card__header">
      <h2 class="card__title">Claude help for the judge</h2>
      <p class="card__description">When Claude Haiku judges moments next to Gemini. Claude uses your Pro plan, up to {{ claude_lane_cap }} calls a day.</p>
    </div>
    <div class="card__body stack">
      <div class="field">
        <label class="field__label" for="field-claude-help">Claude helps</label>
        <select name="mode" id="field-claude-help" class="select">
          <option value="down"{% if claude_help == 'down' %} selected{% endif %}>When Gemini is down</option>
          <option value="always"{% if claude_help == 'always' %} selected{% endif %}>Always</option>
          <option value="off"{% if claude_help == 'off' %} selected{% endif %}>Off</option>
        </select>
        <p class="field__help">"Always" finishes sooner but uses more of your plan. "Off" waits for Gemini.</p>
      </div>
    </div>
    <div class="card__footer">
      <button type="submit" class="btn btn--primary">Save changes</button>
    </div>
  </form>
```

- [ ] **Step 5: Run the test to verify it passes**

Run: `py -m pytest tests/test_judge_pool.py -q -p no:cacheprovider`
Expected: `14 passed`

- [ ] **Step 6: Check the card in the app**

Start the app with `preview_start` (or `py spike.py web`), open `/settings`, and confirm the card renders in the same style as the Discord card, the saved value is selected after Save, and the layout holds at 375 px wide. Run the `web-design-guidelines` skill on the card's markup.

- [ ] **Step 7: Commit**

```bash
git add src/web/routes/settings.py src/web/templates/pages/settings.html tests/test_judge_pool.py
git commit -m "Add the Claude help setting for the judge pool"
```

---

### Task 7: Verify

**Files:** none changed.

- [ ] **Step 1: Run the full suite**

Run: `py -m pytest tests -q -p no:cacheprovider`
Expected: `350 passed` (328 before, plus 14 in `test_judge_pool.py`, plus 8 new in `test_judge_v2.py`). If the count differs, read the summary line and account for every test.

- [ ] **Step 2: Prove the results did not change**

Run: `py scripts/stage7_snapshot.py 2896358710 data/eval_rerun/snapshot_after.json` then `py -c "import filecmp; print(filecmp.cmp('data/eval_rerun/snapshot_before.json', 'data/eval_rerun/snapshot_after.json', shallow=False))"`
Expected: `True`. If `False`, diff the two files and find the cause before going on. A difference means the refactor changed results.

- [ ] **Step 3: One cold run on one eval VOD (uses about 200 Gemini calls and 1 Claude editor call)**

Ask the user before this step: it spends Gemini quota.

```bash
py -c "from pathlib import Path; [Path('data/eval_rerun/57', n).unlink(missing_ok=True) for n in ('judge_cache.json', 'chunk_props.json', 'stream_read.json')]"
```

```bash
py scripts/eval_stage7.py 2896358710 > data/eval_rerun/cold_run.log 2>&1
```

Then report:
- the run's wall time (time the command), against this VOD's first `moments` stage time: `py -c "import sqlite3; from datetime import datetime as d; c=sqlite3.connect('data/spike.db'); r=c.execute(\"select started_at, finished_at from stage_timings where video_id=57 and stage='moments'\").fetchone(); print((d.fromisoformat(r[1])-d.fromisoformat(r[0])).total_seconds()/60, 'min')"`
- counts from the log: `grep -c "on gemini" data/eval_rerun/cold_run.log`, `grep -c "on claude" data/eval_rerun/cold_run.log`, `grep -c "(503)" data/eval_rerun/cold_run.log`, `grep -c "(429)" data/eval_rerun/cold_run.log`, `grep -c "Gemini is down" data/eval_rerun/cold_run.log`
- if the 429 count is high, set `GEMINI_LANE_WORKERS = 2` and say so.
```
