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
