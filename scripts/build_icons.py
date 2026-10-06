"""
Build SVG sprite from Phosphor icons per DESIGN.md §7 & §16.
"""

import os
import re
import urllib.request
from pathlib import Path

ICONS = [
    "film-strip", "plus", "broadcast", "queue", "paper-plane-tilt",
    "chart-line", "gear-six", "check", "x", "download-simple",
    "copy", "arrow-clockwise", "stop", "pencil-simple", "trash",
    "dots-three", "list", "arrow-up-right", "play", "pause",
    "upload-simple", "link-simple", "magnifying-glass", "calendar-blank",
    "info", "warning", "warning-circle", "check-circle",
    "caret-down", "caret-right", "caret-left", "sun", "moon", "sign-out"
]

OUT_FILE = Path(__file__).resolve().parent.parent / "src" / "web" / "static" / "icons" / "sprite.svg"


def build_sprite():
    OUT_FILE.parent.mkdir(parents=True, exist_ok=True)
    symbols = []

    for name in ICONS:
        url = f"https://unpkg.com/@phosphor-icons/core@2.1.1/assets/regular/{name}.svg"
        try:
            req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
            with urllib.request.urlopen(req, timeout=10) as resp:
                raw = resp.read().decode("utf-8")
                inner = re.sub(r"<\?xml.*?\?>", "", raw)
                inner = re.sub(r"<svg[^>]*>", "", inner)
                inner = inner.replace("</svg>", "").strip()
                symbols.append(f'  <symbol id="{name}" viewBox="0 0 256 256">\n    {inner}\n  </symbol>')
        except Exception as e:
            print(f"Warning: could not fetch {name}: {e}")

    sprite_content = (
        '<svg xmlns="http://www.w3.org/2000/svg" style="display: none;">\n'
        + "\n".join(symbols)
        + "\n</svg>\n"
    )

    OUT_FILE.write_text(sprite_content, encoding="utf-8")
    print(f"Sprite built successfully at {OUT_FILE} with {len(symbols)}/{len(ICONS)} icons.")


if __name__ == "__main__":
    build_sprite()
