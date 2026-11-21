"""
The default hook voice (clip analytics Step 5). The anime judge writes one hook per voice. The title card starts on the first
filled voice in the order below. Once each voice has enough Shorts with results, the Analytics tab offers to make the voice with
the best median `stayed` the default. Every fifth clip starts on the next voice, so the others keep getting tested.
"""

import json
import statistics
from datetime import date
from typing import Any, Dict, List, Optional, Tuple

from src.config import ROOT_DIR
from src.db import get_setting, log_event, set_setting

HOOK_VOICES = ("relatable", "curious", "plain")  # the order before anyone approves a change
ORDER_KEY = "hook_voice_order"
MIN_SHORTS = 10      # linked Shorts, 7 days or older, needed for each voice
TEST_EVERY = 5       # candidate_id % 5 == 0 starts on another voice


def voice_order() -> Tuple[str, ...]:
    """The approved order, always holding every known voice once."""
    try:
        saved = json.loads(get_setting(ORDER_KEY) or "[]")
    except ValueError:
        saved = []
    first = [v for v in saved if v in HOOK_VOICES] if isinstance(saved, list) else []
    first = list(dict.fromkeys(first))
    return tuple(first + [v for v in HOOK_VOICES if v not in first])


def first_filled(options: Dict[str, str]) -> Optional[str]:
    return next((v for v in voice_order() if options.get(v)), None)


def rotated_hook(options: Dict[str, str], candidate_id: int) -> Optional[str]:
    """The hook text a clip should start on instead of the default: the next filled voice after the leading one, for every
    fifth candidate. None when the default stays (not a fifth one, or only one voice is filled)."""
    filled = [v for v in voice_order() if options.get(v)]
    if candidate_id % TEST_EVERY or len(filled) < 2:
        return None
    return options[filled[1]]


def offer(rows: List[Dict[str, Any]]) -> Optional[Dict[str, Any]]:
    """{voice, stats} when every voice has 10 or more linked Shorts of 7 days or older and one voice alone has the highest median
    stayed, and it is not the default already. rows come from analytics.shorts_table."""
    by_voice: Dict[str, List[float]] = {v: [] for v in HOOK_VOICES}
    for r in rows:
        if r["voice"] in by_voice and (r["age"] or 0) >= 7 and r["stayed"] is not None:
            by_voice[r["voice"]].append(r["stayed"])
    if any(len(x) < MIN_SHORTS for x in by_voice.values()):
        return None
    medians = {v: statistics.median(x) for v, x in by_voice.items()}
    best = max(medians.values())
    leaders = [v for v, m in medians.items() if m == best]
    if len(leaders) != 1 or leaders[0] == voice_order()[0]:
        return None
    return {"voice": leaders[0], "stats": {v: {"n": len(by_voice[v]), "median_stayed": round(medians[v], 3)} for v in HOOK_VOICES}}


def make_default(voice: str, stats: Dict[str, Any]) -> bool:
    """Put the voice first, and log the change as an event and in LEARNINGS.md with the numbers behind it."""
    if voice not in HOOK_VOICES:
        return False
    old = voice_order()
    set_setting(ORDER_KEY, json.dumps([voice] + [v for v in old if v != voice]))
    numbers = ", ".join(f"{v}: n={s['n']}, median stayed {s['median_stayed']:.1%}" for v, s in stats.items())
    log_event("info", f"Default hook voice changed from {old[0]} to {voice} ({numbers})")
    try:  # best effort: the setting is already saved
        path = ROOT_DIR / "LEARNINGS.md"
        text = path.read_text(encoding="utf-8")
        entry = (f"## {date.today().isoformat()}: Default hook voice is now {voice}\n\n"
                 f"- **Decided (approved on the Analytics tab):** the title card starts on {voice} instead of {old[0]}. "
                 f"Every fifth clip starts on the next voice, so the others keep being tested.\n"
                 f"- **Numbers:** {numbers}.\n\n")
        head, sep, rest = text.partition("\n\n")
        path.write_text(head + sep + entry + rest, encoding="utf-8")
    except OSError:
        pass
    return True
