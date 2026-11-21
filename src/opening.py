"""
Opening checks (clip analytics Step 2): plain numbers from a clip's timed words, no model. Computed at render time and
stored in clips.render_facts, so the Analytics tab can group Shorts by them. No check changes a render.
"""

import re
from typing import Any, Dict, List, Optional

LINE_GAP_S = 0.6      # a pause this long ends a caption line
LINE_MAX_WORDS = 10
_STOP = {"that", "this", "with", "have", "from", "they", "them", "what", "when", "were", "will", "your", "just", "like",
         "then", "than", "there", "their", "about", "would", "could", "should", "been", "into", "over", "very", "here"}


def _key(word: str) -> str:
    return re.sub(r"[^\w]", "", word.lower())


def _loops(lines: List[Dict[str, Any]]) -> bool:
    """The last line shares a word of 4 or more letters with the first line (stop words excluded)."""
    if len(lines) < 2:
        return False
    big = lambda t: {k for k in map(_key, t.split()) if len(k) >= 4 and k not in _STOP}  # noqa: E731
    return bool(big(lines[0]["text"]) & big(lines[-1]["text"]))


def opening_checks(words: List[Dict[str, Any]], clip_start: float, duration: float, hook_card: bool,
                   shown_words: Optional[List[Dict[str, Any]]] = None) -> Dict[str, Any]:
    """words: the spoken words on the output timeline (clip_start is output second 0), as retime_words_for_cuts returns them.
    shown_words: the same words as the captions show them (English mode), for the line text."""
    def inside(ws):
        out = [{**w, "t": float(w.get("start", 0)) - clip_start, "e": float(w.get("end", 0)) - clip_start}
               for w in ws if clip_start <= float(w.get("start", 0)) < clip_start + duration]
        return sorted(out, key=lambda w: w["t"])

    spoken = inside(words)
    lines: List[Dict[str, Any]] = []
    cur: List[Dict[str, Any]] = []
    for w in inside(shown_words if shown_words is not None else words):
        if cur and (w["t"] - cur[-1]["e"] > LINE_GAP_S or len(cur) >= LINE_MAX_WORDS or cur[-1]["word"].rstrip().endswith((".", "?", "!"))):
            lines.append({"start": round(cur[0]["t"], 2), "text": " ".join(x["word"].strip() for x in cur)})
            cur = []
        cur.append(w)
    if cur:
        lines.append({"start": round(cur[0]["t"], 2), "text": " ".join(x["word"].strip() for x in cur)})
    return {
        "first_word_s": round(spoken[0]["t"], 2) if spoken else None,
        "words_first_3s": sum(1 for w in spoken if w["t"] < 3.0),
        "longest_quiet_s": round(max((b["t"] - a["e"] for a, b in zip(spoken, spoken[1:])), default=0.0), 2),
        "loops": _loops(lines),
        "hook_card": bool(hook_card),
        "lines": lines,
    }


def summary(facts: Dict[str, Any]) -> str:
    """One line for the clip page."""
    if not facts:
        return ""
    first = facts.get("first_word_s")
    return (f"First word at {first}s" if first is not None else "No speech") + \
        f" · {facts.get('words_first_3s', 0)} words in 3 s · longest quiet {facts.get('longest_quiet_s', 0)}s" \
        f" · {'loops' if facts.get('loops') else 'no loop'} · {'hook card' if facts.get('hook_card') else 'no hook card'}"
