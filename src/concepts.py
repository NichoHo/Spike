"""
Spike: clip concepts and their rules (reports/Clip concepts.md, Blueprint §6.7 addendum).

A concept is the shape of one finished clip: single, story, pov, top3 or top5. The editor model proposes
outputs; everything here is the code that enforces the rules after the model answers. Pure functions, no
LLM calls and no I/O, so the same checks run for the pipeline, the clip page and "Ask the editor".

Segments are dicts: {candidate_id, start_s, end_s, remove: [[s, e]], rank, label}, stream seconds.
Overlay is a dict: {pov_text, pov_options, emotion, skip_card, callback_quote, foreshadow}.
"""

import re
from typing import Any, Dict, Iterable, List, Optional, Set, Tuple

import numpy as np

CONCEPTS = ("single", "story", "pov", "top3", "top5")
CONCEPT_LABELS = {"single": "Single", "story": "Story", "pov": "POV", "top3": "Top 3", "top5": "Top 5"}
DEFAULT_AUTO_CONCEPTS = ["single", "story", "pov", "top3"]   # top5 is off by default
EMOTIONS = ("fury", "despair", "disbelief", "panic", "smug joy", "hysterical laughing", "slow realization")

STORY_TOTAL_S = (20.0, 45.0)
STORY_SETUP_MAX_S = 8.0
STORY_SKIP_CARD_MAX_WORDS = 6
POV_LEN_S = (4.0, 12.0)
POV_LEAD_S = 0.4           # a POV starts this long before the reaction peak (0.3 to 0.5 allowed)
POV_MAX_WORDS = 10
TOP_RULES = {
    "top3": {"n": 3, "entry": (6.0, 15.0), "total_max": 60.0},
    "top5": {"n": 5, "entry": (6.0, 12.0), "total_max": 100.0},
}
TOP5_FLOOR = 55.0          # every top 5 entry must pass the judge's floor
CARD_S = 1.0               # skip card length
CALLBACK_S = 1.5
FORESHADOW_S = 0.6
END_PAD_S = 0.8

# Words that tie a clip to its context. A POV clip must not contain them.
CONTEXT_WORDS = {"chat", "donation", "donations", "donate", "donated", "subscribe", "subscribed"}

_STOP = set("""
a about above after again all also am an and any are as at be because been before being below between both but by
can could did do does doing down during each else even ever few for from further get gets got had has have having he
her here hers him his how i if in into is it its itself just like me more most my myself no nor not now of off on once
one only or other our ours out over own pov same she should so some such than that the their theirs them then there
these they this those through to too under until up us very was we were what when where which while who whom why will
with would you your yours yourself nobody when still every thing things way back
""".split())


# ── Small helpers ────────────────────────────────────────────────────────────

def words_of(text: str) -> List[str]:
    return re.findall(r"[a-z0-9']+", (text or "").lower())


def _stem(w: str) -> str:
    for suf in ("ing", "ed", "es", "s"):
        if w.endswith(suf) and len(w) - len(suf) >= 3:
            return w[: -len(suf)]
    return w


def content_words(text: str) -> Set[str]:
    """Words that carry meaning (stopwords and very short words dropped, crude stemming). A stand-in for 'nouns':
    nothing here needs a part-of-speech tagger, and sharing any content word is enough to reject a caption."""
    return {_stem(w) for w in words_of(text) if len(w) >= 3 and w not in _STOP}


def segment_net_s(seg: Dict[str, Any]) -> float:
    """Length of a segment after its removed stretches."""
    cut = sum(max(0.0, min(e, seg["end_s"]) - max(s, seg["start_s"])) for s, e in seg.get("remove") or [])
    return max(0.0, seg["end_s"] - seg["start_s"] - cut)


def segment_text(words: Iterable[Dict[str, Any]], seg: Dict[str, Any]) -> str:
    """What is said inside a segment, without its removed stretches."""
    removed = seg.get("remove") or []
    out = []
    for w in words:
        t = float(w.get("start", 0))
        if seg["start_s"] <= t < seg["end_s"] and not any(a <= t < b for a, b in removed):
            out.append(w.get("word", "").strip())
    return " ".join(x for x in out if x)


def count_problem(concept: str, n: int) -> Optional[str]:
    """The moment picker's rule: Single 1, POV 1, Story 2 to 3, Top 3 exactly 3, Top 5 exactly 5."""
    if concept in ("single", "pov"):
        return None if n == 1 else f"{CONCEPT_LABELS[concept]} needs exactly 1 moment"
    if concept == "story":
        return None if 2 <= n <= 3 else "Story needs 2 or 3 moments"
    rules = TOP_RULES[concept]
    return None if n == rules["n"] else f"{CONCEPT_LABELS[concept]} needs exactly {rules['n']} moments"


# ── POV checks ───────────────────────────────────────────────────────────────

def context_terms(streamer: str = "", aliases: Iterable[str] = (), game: str = "", names: Iterable[str] = ()) -> Dict[str, Set[str]]:
    """Words and phrases that tie a clip to its context: the game, player and team names, the streamer."""
    phrases, tokens = set(), set(CONTEXT_WORDS)
    for item in [streamer, game, *aliases, *names]:
        item = (item or "").strip()
        if not item:
            continue
        phrases.add(item.lower())
        for w in re.findall(r"[A-Za-z0-9']+", item):
            if len(w) >= 4 or (w.isupper() and len(w) >= 2):   # distinctive words, and short all-caps ones like EA or FC
                tokens.add(w.lower())
    return {"phrases": phrases, "tokens": tokens}


def pov_context_problems(text: str, terms: Dict[str, Set[str]]) -> List[str]:
    """A POV clip must not say the game, a player or team, 'chat', a donation, or the streamer's own name."""
    low = " " + " ".join(words_of(text)) + " "
    hits = {p for p in terms["phrases"] if p and f" {' '.join(words_of(p))} " in low}
    hits |= {t for t in terms["tokens"] if f" {t} " in low}
    return [f"the speech names {h!r}" for h in sorted(hits)]


def pov_caption_problems(caption: str, clip_text: str, extra_text: Iterable[str], terms: Dict[str, Set[str]]) -> List[str]:
    """Why a POV caption fails: too long, or guessable from the clip. It must share no content word with the clip
    transcript, the title, the game or the streamer name, and must not name them."""
    problems = []
    n = len(words_of(caption))
    if n == 0:
        return ["the caption is empty"]
    if n > POV_MAX_WORDS:
        problems.append(f"the caption has {n} words, the limit is {POV_MAX_WORDS}")
    shared = content_words(caption) & content_words(" ".join([clip_text, *extra_text, *terms["phrases"], *terms["tokens"]]))
    if shared:
        problems.append("the caption shares words with the clip: " + ", ".join(sorted(shared)))
    problems += [p.replace("the speech names", "the caption names") for p in pov_context_problems(caption, terms)]
    return problems


def reaction_peak(jump: np.ndarray, start_s: float, end_s: float, fallback: Optional[float] = None) -> Optional[float]:
    """Loudest voice-jump second inside [start_s, end_s], else the fallback. This is the reaction peak."""
    a, b = max(0, int(start_s)), min(len(jump), int(end_s) + 1)
    if b > a and float(jump[a:b].max()) > 0:
        return float(a + int(jump[a:b].argmax()))
    return fallback


def pov_edges(peak_t: float, jump: np.ndarray, thr: float, lo_s: float, hi_s: float) -> Optional[Tuple[float, float]]:
    """POV window: starts 0.4 s before the reaction peak and ends where the outburst ends (the last second still
    above the voice-jump threshold, plus half a second), never in silence. Stretched to the 4 s minimum when the
    outburst is short. None when it cannot fit inside [lo_s, hi_s]."""
    thr = thr or 3.0   # no stored threshold: 3 dB above the 30 s median still counts as an outburst
    start = max(lo_s, peak_t - POV_LEAD_S)
    last = int(peak_t)
    while last + 1 < min(len(jump), int(hi_s)) and last + 1 <= peak_t + POV_LEN_S[1] and jump[last + 1] >= thr:
        last += 1
    end = min(hi_s, last + 1.0 + 0.5)
    end = max(end, start + POV_LEN_S[0])
    end = min(end, start + POV_LEN_S[1])
    if end > hi_s or end - start < POV_LEN_S[0]:
        return None
    return round(start, 2), round(end, 2)


# ── Concept validation ───────────────────────────────────────────────────────

def _norm(text: str) -> str:
    return " ".join(words_of(text))


def validate_concept(
    concept: str,
    segments: List[Dict[str, Any]],
    overlay: Optional[Dict[str, Any]],
    *,
    title: str = "",
    hook_text: str = "",
    theme: str = "",
    words: Iterable[Dict[str, Any]] = (),
    preset: Optional[Dict[str, Any]] = None,
    terms: Optional[Dict[str, Set[str]]] = None,
    peak_t: Optional[float] = None,
    captions: bool = True,
) -> List[str]:
    """Problems with a proposed output, empty when it is allowed. `words` is the stream's word list with timings.
    Segment dicts may carry `score` (the judge's raw score) for the top 5 floor and the story escalation check.
    captions=False skips the POV emotion and caption checks (used before the caption call has run)."""
    ov = overlay or {}
    words = list(words)
    terms = terms or context_terms()
    n = len(segments)
    problems: List[str] = []
    if concept not in CONCEPTS:
        return [f"unknown concept {concept!r}"]
    cp = count_problem(concept, n)
    if cp:
        return [cp]
    if any(s["end_s"] <= s["start_s"] for s in segments):
        return ["a segment ends before it starts"]
    lens = [segment_net_s(s) for s in segments]

    if concept == "single":
        lo, hi = ((preset or {}).get("min_len", 12), (preset or {}).get("max_len", 60))
        if not lo <= lens[0] <= hi:
            problems.append(f"length {lens[0]:.0f}s is outside {lo} to {hi}s")
        if not (hook_text or title).strip():
            problems.append("it has no hook title")

    elif concept == "story":
        ordered = all(a["end_s"] <= b["start_s"] for a, b in zip(segments, segments[1:]))
        if not ordered:
            problems.append("the segments are not in time order")
        if n == 3:
            scores = [float(s.get("score") or 0) for s in segments]
            if not (scores[0] <= scores[1] <= scores[2]):
                problems.append("a middle step is only allowed when it escalates")
        total = sum(lens)
        if not STORY_TOTAL_S[0] <= total <= STORY_TOTAL_S[1]:
            problems.append(f"total {total:.0f}s is outside {STORY_TOTAL_S[0]:.0f} to {STORY_TOTAL_S[1]:.0f}s")
        if lens[0] > STORY_SETUP_MAX_S:
            problems.append(f"the setup is {lens[0]:.0f}s, the limit is {STORY_SETUP_MAX_S:.0f}s")
        quote = _norm(ov.get("callback_quote", ""))
        if not quote:
            problems.append("it has no callback quote")
        elif quote not in _norm(segment_text(words, segments[0])):
            problems.append("the callback quote is not said in the setup segment")
        skip = (ov.get("skip_card") or "").strip()
        if not skip or len(words_of(skip)) > STORY_SKIP_CARD_MAX_WORDS:
            problems.append(f"it needs a skip card of 1 to {STORY_SKIP_CARD_MAX_WORDS} words")
        if not (hook_text or title).strip():
            problems.append("it has no hook title")

    elif concept == "pov":
        if not POV_LEN_S[0] <= lens[0] <= POV_LEN_S[1]:
            problems.append(f"length {lens[0]:.1f}s is outside {POV_LEN_S[0]:.0f} to {POV_LEN_S[1]:.0f}s")
        if peak_t is not None:
            lead = peak_t - segments[0]["start_s"]
            if not 0.25 <= lead <= 0.55:
                problems.append(f"it starts {lead:.2f}s before the peak, it should be 0.3 to 0.5s")
        text = segment_text(words, segments[0])
        problems += pov_context_problems(text, terms)
        if captions:
            if ov.get("emotion") not in EMOTIONS:
                problems.append("it has no emotion label")
            problems += pov_caption_problems(ov.get("pov_text", ""), text, [title, hook_text], terms)

    else:  # top3, top5
        rules = TOP_RULES[concept]
        ranks = sorted(s.get("rank") or 0 for s in segments)
        if ranks != list(range(1, rules["n"] + 1)):
            problems.append(f"entries must be ranked 1 to {rules['n']}")
        elif [s["rank"] for s in segments] != sorted((s["rank"] for s in segments), reverse=True):
            problems.append("entries must run from the weakest to #1")
        for s, ln in zip(segments, lens):
            if not rules["entry"][0] <= ln <= rules["entry"][1]:
                problems.append(f"entry #{s.get('rank')} is {ln:.0f}s, it should be {rules['entry'][0]:.0f} to {rules['entry'][1]:.0f}s")
            if not (s.get("label") or "").strip():
                problems.append(f"entry #{s.get('rank')} has no label")
            if concept == "top5" and float(s.get("score") or 0) < TOP5_FLOOR:
                problems.append(f"entry #{s.get('rank')} is under the judge's floor of {TOP5_FLOOR:.0f}")
        if sum(lens) > rules["total_max"]:
            problems.append(f"total {sum(lens):.0f}s is over {rules['total_max']:.0f}s")
        if not title.strip():
            problems.append("it has no header title")
    return problems


def clean_segments(items: Any) -> List[Dict[str, Any]]:
    """Segment list from untrusted input (the clip page, the model): bad items dropped, numbers made numbers, removed
    stretches and zooms cleaned and kept inside their segment."""
    from src.edges import clean_cuts, clean_zooms

    out: List[Dict[str, Any]] = []
    for it in items if isinstance(items, list) else []:
        try:
            a, b = float(it["start_s"]), float(it["end_s"])
        except (TypeError, KeyError, ValueError):
            continue
        if b - a < 0.5:
            continue
        seg = {
            "candidate_id": it.get("candidate_id") if isinstance(it.get("candidate_id"), int) else None,
            "start_s": round(max(0.0, a), 2), "end_s": round(b, 2), "remove": clean_cuts(it.get("remove"), a, b),
            "rank": it.get("rank") if isinstance(it.get("rank"), int) and it.get("rank") > 0 else None,
            "label": str(it.get("label") or "")[:60],
        }
        if isinstance(it.get("zooms"), list):
            seg["zooms"] = clean_zooms(it["zooms"], a, b)
        out.append(seg)
    return out


SEGMENT_FIELDS = ("candidate_id", "start_s", "end_s", "remove", "rank", "label", "zooms")


def stored_segments(segs: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """The segment fields saved on a clip. Working keys the editor adds (source label, judge score) stay behind."""
    return [{k: s[k] for k in SEGMENT_FIELDS if k in s} for s in segs]


def order_entries(segments: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """Compilation order: weakest first, #1 last."""
    return sorted(segments, key=lambda s: -(s.get("rank") or 0))
