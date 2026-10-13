"""
Letterbox title card: the hook title drawn in black above the video, on a transparent
1080x1920 PNG that is overlaid on the white-barred letterbox frame.

Emoji come from Twemoji (graphics CC-BY 4.0, Twitter Inc. and other contributors),
downloaded once per emoji and cached in data/emoji. Apple's emoji have no license for
use in videos, so they are not used.
"""

from __future__ import annotations

import logging
import urllib.request
from pathlib import Path
from typing import List, Optional, Tuple

from PIL import Image, ImageDraw, ImageFont

from src.config import DATA_DIR, OUTPUT_HEIGHT, OUTPUT_WIDTH

logger = logging.getLogger("spike.title_card")

TWEMOJI_URL = "https://cdn.jsdelivr.net/gh/jdecked/twemoji@15.1.0/assets/72x72/{}.png"
EMOJI_DIR = DATA_DIR / "emoji"
FONT_PATHS = ("C:/Windows/Fonts/arialbd.ttf", "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf")
MAX_TEXT_W = 960
GAP_ABOVE_VIDEO = 48


def _is_emoji(ch: str) -> bool:
    o = ord(ch)
    return (
        0x1F000 <= o <= 0x1FAFF or 0x2600 <= o <= 0x27BF or 0x2300 <= o <= 0x23FF
        or 0x2B00 <= o <= 0x2BFF or o in (0x203C, 0x2049, 0x3030, 0x303D)
    )


def _tokens(text: str) -> List[Tuple[bool, str]]:
    """Split text into (is_emoji, piece). One emoji piece holds a whole sequence:
    variation selector, skin tone, ZWJ joins, keycap, or a flag's two letters."""
    out: List[Tuple[bool, str]] = []
    i = 0
    while i < len(text):
        if not _is_emoji(text[i]):
            j = i
            while j < len(text) and not _is_emoji(text[j]):
                j += 1
            out.append((False, text[i:j]))
            i = j
            continue
        j = i + 1
        if 0x1F1E6 <= ord(text[i]) <= 0x1F1FF and j < len(text) and 0x1F1E6 <= ord(text[j]) <= 0x1F1FF:
            j += 1  # flag
        while j < len(text):
            c = text[j]
            if c in "\ufe0f\u20e3" or 0x1F3FB <= ord(c) <= 0x1F3FF:
                j += 1
            elif c == "\u200d" and j + 1 < len(text):
                j += 2
            else:
                break
        out.append((True, text[i:j]))
        i = j
    return out


def strip_emoji(text: str) -> str:
    """Text without emoji, for places that can't draw them (ASS captions)."""
    return " ".join("".join(p for is_e, p in _tokens(text) if not is_e).split())


def _emoji_image(seq: str) -> Optional[Image.Image]:
    # Twemoji file names drop U+FE0F unless the sequence has a ZWJ
    keep_fe0f = "\u200d" in seq
    name = "-".join(f"{ord(c):x}" for c in seq if c != "\ufe0f" or keep_fe0f)
    path = EMOJI_DIR / f"{name}.png"
    if not path.exists():
        try:
            with urllib.request.urlopen(TWEMOJI_URL.format(name), timeout=5) as r:
                data = r.read()
            EMOJI_DIR.mkdir(parents=True, exist_ok=True)
            path.write_bytes(data)
        except Exception as e:
            logger.warning(f"Emoji {name} unavailable, leaving it out: {e}")
            return None
    return Image.open(path).convert("RGBA")


def _font(size: int) -> ImageFont.FreeTypeFont:
    for p in FONT_PATHS:
        if Path(p).exists():
            return ImageFont.truetype(p, size)
    return ImageFont.load_default(size)


def _word_width(tokens: List[Tuple[bool, str]], font: ImageFont.FreeTypeFont, size: int) -> float:
    return sum(size * 1.1 if is_e else font.getlength(p) for is_e, p in tokens)


def _wrap(words: List[List[Tuple[bool, str]]], font, size: int) -> List[List[List[Tuple[bool, str]]]]:
    space = font.getlength(" ")
    lines: List[list] = [[]]
    width = 0.0
    for w in words:
        ww = _word_width(w, font, size)
        if lines[-1] and width + space + ww > MAX_TEXT_W:
            lines.append([])
            width = 0.0
        width += (space if lines[-1] else 0) + ww
        lines[-1].append(w)
    return lines


def render_title_card(text: str, video_h: int, out_path: Path) -> bool:
    """Draw `text` centred above a video of height video_h (centred in the frame). False if no text."""
    text = " ".join(text.split())
    if not text:
        return False
    words = [_tokens(w) for w in text.split(" ")]

    size = 76
    while True:
        font = _font(size)
        lines = _wrap(words, font, size)
        if len(lines) <= 3 or size <= 48:
            break
        size -= 6

    line_h = int(size * 1.25)
    block_h = line_h * len(lines)
    video_top = (OUTPUT_HEIGHT - video_h) // 2
    # ponytail: a tall source leaves no room above the video, so the title then overlaps it
    top = max(40, video_top - GAP_ABOVE_VIDEO - block_h)

    img = Image.new("RGBA", (OUTPUT_WIDTH, OUTPUT_HEIGHT), (0, 0, 0, 0))
    draw = ImageDraw.Draw(img)
    space = font.getlength(" ")
    for li, line in enumerate(lines):
        line_w = sum(_word_width(w, font, size) for w in line) + space * (len(line) - 1)
        x = (OUTPUT_WIDTH - line_w) / 2
        mid_y = top + li * line_h + line_h / 2
        for wi, word in enumerate(line):
            if wi:
                x += space
            for is_e, piece in word:
                if is_e:
                    em = _emoji_image(piece)
                    if em:
                        em = em.resize((size, size), Image.LANCZOS)
                        img.alpha_composite(em, (int(x + size * 0.05), int(mid_y - size / 2)))
                    x += size * 1.1
                else:
                    draw.text((x, mid_y), piece, font=font, fill=(0, 0, 0, 255), anchor="lm")
                    x += font.getlength(piece)

    out_path.parent.mkdir(parents=True, exist_ok=True)
    img.save(out_path)
    return True
