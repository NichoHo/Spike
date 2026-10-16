"""
Stage 9b: captions — word-by-word ASS subtitle generation.
Blueprint §7.2:
- 1 to 3 words per line, broken at punctuation and pauses, placed by the render layout.
- Three style presets: bold_pop, clean, karaoke.
- Each word group has exact start/end timestamps from faster-whisper.
- Escape {, }, and \\ in every word (ASS control characters).
- Profanity masking if enabled per source.

Output: data/videos/<id>/clips/clip_<id>.ass (sidecar next to each clip)
"""

from __future__ import annotations

import re
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional

# ASS style presets (Blueprint §7.2). All use Alignment 5 (centre) and are placed with \pos,
# so the style's MarginV is unused.
# bold_pop: Shorts-style. Impact, UPPERCASE, thick outline, the word being spoken turns yellow.
# clean: white + soft shadow, sentence case
# karaoke: words fill in as spoken (highlighted word turns yellow)

_ASS_HEADER_TEMPLATE = """\
[Script Info]
ScriptType: v4.00+
WrapStyle: 0
ScaledBorderAndShadow: yes
PlayResX: 1080
PlayResY: 1920
YCbCr Matrix: None

[V4+ Styles]
Format: Name, Fontname, Fontsize, PrimaryColour, SecondaryColour, OutlineColour, BackColour, Bold, Italic, Underline, StrikeOut, ScaleX, ScaleY, Spacing, Angle, BorderStyle, Outline, Shadow, Alignment, MarginL, MarginR, MarginV, Encoding
{style_lines}

[Events]
Format: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text
"""

_STYLE_DEFS = {
    "bold_pop": (
        "Style: bold_pop,Impact,104,&H00FFFFFF,&H0000FFFF,&H00000000,&H96000000,"
        "0,0,0,0,100,100,1,0,1,7,2,5,60,60,0,1"
    ),
    "clean": (
        "Style: clean,Arial,72,&H00FFFFFF,&H000000FF,&H00303030,&H64000000,"
        "1,0,0,0,100,100,0,0,1,2,3,5,80,80,0,1"
    ),
    "karaoke": (
        "Style: karaoke,Arial,72,&H00FFFFFF,&H0000FFFF,&H00000000,&H96000000,"
        "1,0,0,0,100,100,0,0,1,3,0,5,80,80,0,1"
    ),
    "hook": (
        "Style: hook,Arial,60,&H00FFFFFF,&H00000000,&H00000000,&H96000000,"
        "1,0,0,0,100,100,0,0,1,4,0,8,80,80,100,1"
    ),
    # Concept overlays (reports/Clip concepts.md). All sit at the top centre, below the platform's top UI (about 220 px).
    # pov: the caption for the whole clip. Large, bold, white, thick black outline.
    "pov": (
        "Style: pov,Arial,84,&H00FFFFFF,&H00000000,&H00000000,&H96000000,"
        "1,0,0,0,100,100,0,0,1,7,2,8,90,90,230,1"
    ),
    # rank: the big "#2" of a countdown entry, with its label under it
    "rank": (
        "Style: rank,Impact,200,&H00FFFFFF,&H00000000,&H00000000,&H96000000,"
        "0,0,0,0,100,100,0,0,1,9,2,8,60,60,210,1"
    ),
    "rank_label": (
        "Style: rank_label,Arial,64,&H00FFFFFF,&H00000000,&H00000000,&H96000000,"
        "1,0,0,0,100,100,0,0,1,6,2,8,90,90,470,1"
    ),
    # callback: the setup quote shown on the payoff
    "callback": (
        "Style: callback,Arial,66,&H00FFFFFF,&H00000000,&H00000000,&H96000000,"
        "1,1,0,0,100,100,0,0,1,6,2,8,90,90,230,1"
    ),
    # card: plain text in the middle of a black frame (the story's skip card)
    "card": (
        "Style: card,Arial,96,&H00FFFFFF,&H00000000,&H00000000,&H96000000,"
        "1,0,0,0,100,100,0,0,1,0,0,5,100,100,0,1"
    ),
}
OVERLAY_STYLES = ("pov", "rank", "rank_label", "callback", "card")
_HIGHLIGHT = "&H0000FFFF&"  # ASS colours are BGR: this is yellow

_PROFANITY_LIST = [
    "fuck", "fucking", "fuckin", "fucked", "fucker", "fuckers", "motherfucker", "motherfucking",
    "shit", "shitty", "bullshit", "bitch", "bitches", "ass", "asshole", "cunt",
    "dick", "cock", "pussy", "nigga", "niggas", "nigger", "niggers", "faggot",
]
_PROFANITY_RE = re.compile(
    r"\b(" + "|".join(re.escape(w) for w in _PROFANITY_LIST) + r")\b",
    re.IGNORECASE,
)


def _ts_to_ass(t_s: float) -> str:
    """Convert float seconds to ASS timestamp H:MM:SS.cc"""
    t_s = max(0.0, t_s)
    h = int(t_s // 3600)
    m = int((t_s % 3600) // 60)
    s = int(t_s % 60)
    cs = int(round((t_s - int(t_s)) * 100))
    return f"{h}:{m:02d}:{s:02d}.{cs:02d}"


def _escape_ass(text: str) -> str:
    """Escape ASS control characters in user-supplied text."""
    text = text.replace("\\", "\\\\ ").replace("{", "\\{").replace("}", "\\}")
    return text.strip()


def _mask_profanity(text: str) -> str:
    """Censor profanity by replacing its second letter: fuck -> f*ck, nigga -> n*gga."""
    def mask(m: re.Match) -> str:
        w = m.group(0)
        # Compounds: censor the profane root, not the "mother" / "bull" in front of it
        p = next((len(pre) for pre in ("mother", "bull") if w.lower().startswith(pre)), 0)
        return w[:p + 1] + "*" + w[p + 2:]
    return _PROFANITY_RE.sub(mask, text)


_BREAK_AFTER = (".", ",", "!", "?", ";", ":")


def _group_words(
    words: List[Dict[str, Any]],
    words_per_line: int = 3,
    clip_start: float = 0.0,
    clip_end: float = 999999.0,
    max_chars: int = 18,
    max_gap_s: float = 0.4,
) -> List[Dict[str, Any]]:
    """
    Group words into short caption lines that follow speech, not a fixed count.
    A line ends at words_per_line words, at max_chars, after punctuation
    (so "happened. This" never shares a line), or before a pause > max_gap_s.
    Only includes words whose start time falls within [clip_start, clip_end).
    Each group ends at the next group's start or 0.25 s after its last word,
    whichever comes first, so a line never lingers through a pause.
    Returns list of {start, end, words: List[{word, start, end}]}.
    """
    window = [
        w for w in words
        if w.get("start", 0) >= clip_start and w.get("start", 0) < clip_end
        and w.get("word", "").strip()
    ]
    chunks: List[List[Dict[str, Any]]] = []
    cur: List[Dict[str, Any]] = []
    for i, w in enumerate(window):
        cur.append(w)
        text = " ".join(x["word"].strip() for x in cur)
        nxt = window[i + 1] if i + 1 < len(window) else None
        nxt_len = len(text) + 1 + len(nxt["word"].strip()) if nxt else 0
        gap = (nxt["start"] - w.get("end", w["start"])) if nxt else 0.0
        if (
            nxt is None
            or len(cur) >= words_per_line
            or nxt_len > max_chars
            or w["word"].strip().endswith(_BREAK_AFTER)
            or gap > max_gap_s
        ):
            chunks.append(cur)
            cur = []

    groups = []
    for i, chunk in enumerate(chunks):
        end = chunk[-1].get("end", chunk[-1]["start"] + 0.3) + 0.25
        if i + 1 < len(chunks):
            end = min(end, chunks[i + 1][0]["start"])
        groups.append({"start": chunk[0]["start"], "end": end, "words": chunk})
    return groups


def _display_word(word: str, style: str, profanity_mask: bool) -> str:
    """Clean one word for display. bold_pop is UPPERCASE and drops trailing , and . like Shorts captions."""
    txt = word.strip()
    if profanity_mask:
        txt = _mask_profanity(txt)
    if style == "bold_pop":
        txt = txt.upper()
        if not txt.endswith(".."):
            txt = txt.rstrip(",.")
    return _escape_ass(txt)


def generate_ass(
    words: List[Dict[str, Any]],
    clip_start_s: float,
    clip_end_s: float,
    style: str = "bold_pop",
    profanity_mask: bool = True,
    caption_y_fraction: "float | Callable[[float], float]" = 0.68,
    words_per_line: int = 3,
    hook_text: str = "",
    hook_duration_s: float = 2.5,
    overlay_events: Optional[List[Dict[str, Any]]] = None,
) -> str:
    """
    Generate ASS subtitle content for a clip.

    Args:
        words: List of word dicts from faster-whisper: {word, start, end}
        clip_start_s: Clip start time in the original video seconds
        clip_end_s: Clip end time in the original video seconds
        style: One of 'bold_pop', 'clean', 'karaoke'
        profanity_mask: If True, apply profanity masking
        caption_y_fraction: Vertical centre of the caption line as a fraction of frame height,
            or a function of seconds into the clip (layout switches move the captions)
        words_per_line: Max words per subtitle line
        hook_text: Optional title shown for the first hook_duration_s seconds at top (manual edits only)
        hook_duration_s: Duration in seconds for hook text overlay
        overlay_events: Optional [{start, end, style, text}] in seconds from the clip start, drawn in one of the
            OVERLAY_STYLES (POV caption, rank card, callback quote, skip card)
    """
    if style not in _STYLE_DEFS:
        style = "bold_pop"

    style_lines = _STYLE_DEFS[style]
    if hook_text:
        style_lines = style_lines + "\n" + _STYLE_DEFS["hook"]
    events = [e for e in (overlay_events or []) if e.get("style") in OVERLAY_STYLES and str(e.get("text", "")).strip()]
    for used in dict.fromkeys(e["style"] for e in events):
        style_lines = style_lines + "\n" + _STYLE_DEFS[used]
    header = _ASS_HEADER_TEMPLATE.format(style_lines=style_lines)

    y_at = caption_y_fraction if callable(caption_y_fraction) else (lambda _t: caption_y_fraction)
    lines = []
    if hook_text:
        safe_hook = _escape_ass(hook_text)
        if profanity_mask:
            safe_hook = _mask_profanity(safe_hook)
        hook_end = min(hook_duration_s, max(0.5, clip_end_s - clip_start_s))
        lines.append(f"Dialogue: 1,0:00:00.00,{_ts_to_ass(hook_end)},hook,,0,0,0,,{safe_hook}")

    for e in events:
        text = _escape_ass(str(e["text"]))
        if profanity_mask:
            text = _mask_profanity(text)
        lines.append(f"Dialogue: 2,{_ts_to_ass(e['start'])},{_ts_to_ass(e['end'])},{e['style']},,0,0,0,,{text}")

    def event(st: float, et: float, text: str) -> str:
        # Exactly 10 fields: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text
        return f"Dialogue: 0,{_ts_to_ass(st - clip_start_s)},{_ts_to_ass(et - clip_start_s)},{style},,0,0,0,,{text}"

    words_per_line = 2 if style == "bold_pop" and words_per_line == 3 else words_per_line
    max_chars = 14 if style == "bold_pop" else 24
    for group in _group_words(words, words_per_line, clip_start_s, clip_end_s, max_chars=max_chars):
        gw = group["words"]
        shown = [_display_word(w.get("word", ""), style, profanity_mask) for w in gw]
        pos = f"\\pos(540,{int(1920 * y_at(group['start'] - clip_start_s))})"

        if style == "bold_pop":
            # One event per word so the spoken word lights up. The line pops in on its first word.
            for i, w in enumerate(gw):
                st = group["start"] if i == 0 else w["start"]
                et = gw[i + 1]["start"] if i + 1 < len(gw) else group["end"]
                if et <= st:
                    continue
                pop = r"\fscx85\fscy85\t(0,90,\fscx100\fscy100)" if i == 0 else ""
                txt = " ".join(
                    f"{{\\c{_HIGHLIGHT}}}{t}{{\\c&H00FFFFFF&}}" if j == i else t
                    for j, t in enumerate(shown)
                )
                lines.append(event(st, et, f"{{{pos}{pop}}}{txt}"))
        elif style == "karaoke":
            parts = []
            for w, t in zip(gw, shown):
                w_dur_cs = max(1, int(round((w.get("end", w["start"] + 0.2) - w["start"]) * 100)))
                parts.append(f"{{\\k{w_dur_cs}}}{t}")
            lines.append(event(group["start"], group["end"], f"{{{pos}}}" + " ".join(parts)))
        else:  # clean
            lines.append(event(group["start"], group["end"], f"{{{pos}}}" + " ".join(shown)))

    return header + "\n".join(lines) + "\n"


def write_ass_file(ass_content: str, out_path: Path) -> Path:
    """Write the ASS content to a file and return its path."""
    out_path.write_text(ass_content, encoding="utf-8-sig")
    return out_path
