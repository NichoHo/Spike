"""
Download Spike's background-music library from the composers' official sites
and write a license sidecar (.json) next to each track.

Only CC BY 4.0 tracks are listed: free for commercial use on any platform,
as long as every post credits the track. The sidecar's "attribution" field is
the credit line; src/posting.py appends it to every post caption.

Source of the picks: the "Background Music for Youtube Videos" playlist
(PLya__OBTLMkONuQDu0kHDCrml2xuEINSi), keeping only tracks with a clear free
license. Files come from incompetech.com / audionautix.com, never from the
YouTube re-uploads.

Usage: py scripts/fetch_music.py
"""

import json
import sys
import urllib.parse
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
MUSIC_DIR = ROOT / "music"
CC_BY = "http://creativecommons.org/licenses/by/4.0/"
INCOMPETECH = "https://incompetech.com/music/royalty-free/mp3-royaltyfree/"
PIECES_JSON = "https://incompetech.com/music/royalty-free/pieces.json"

# (mood folder, incompetech filename stem, when to use it). Mood is the fallback when the
# AI pick is missing; "use_for" is what the AI reads to choose.
MACLEOD = [
    ("funny", "Sneaky Snitch",
     "Someone is up to something: scheming, sneaking, getting caught, sus behaviour, a plan forming."),
    ("funny", "Scheming Weasel faster",
     "Cartoonish chaos with a dark edge: trolling, petty revenge, a plan going wrong fast."),
    ("funny", "Investigations",
     "Laid-back comedic talking: rambling takes, confused 'wait, what?' moments, breaking down a play."),
    ("funny", "Fluffing a Duck",
     "Pure goofy fail or blooper: someone trips, misses, flops. Short (about 30 s per version)."),
    ("funny", "Marty Gots a Plan",
     "Cheeky plotting and hijinks: 'I've got an idea', bad plans, sneaky bets."),
    ("funny", "Divertissement",
     "Light, playful classic pizzicato: dainty or overly careful moments, ironic politeness, roasting gently."),
    ("funny", "Hidden Agenda",
     "Suspicious and sneaky with stops and hits: accusations, catching someone lying, slow-reveal jokes."),
    ("funny", "Sneaky Adventure",
     "Short tiptoe vibe: creeping up on something, trying not to get caught. About 1 minute long."),
    ("wholesome", "Monkeys Spinning Monkeys",
     "Happy, silly and harmless: wholesome chaos, wins, cute moments, feel-good bits."),
    ("wholesome", "Dance of the Sugar Plum Fairy",
     "Whimsical and ironic-delicate: 'magical' moments, mock-elegance, something too perfect to be true."),
    ("chill", "Local Forecast - Elevator",
     "Elevator music: awkward silence, waiting, deadpan reactions, 'this is fine', ironic calm."),
    ("hype", "RetroFuture Clean",
     "Groovy, cocky rock-funk: flexing, swagger, big plays, smooth wins, confident trash talk."),
    ("hype", "Ghostpocalypse - 7 Master",
     "Big intense percussion: clutch moments, rage, chaos, a fight or a huge comeback."),
    ("dramatic", "Hitman",
     "Dark, cinematic and serious: menacing takes, 'it's over for him', villain arcs, revenge."),
    ("dramatic", "Hall of the Mountain King",
     "Builds from quiet to loud chaos: escalating rants, situations spiralling out of control."),
]

# Audionautix publishes no tag feed, so feel is written by hand from the title.
SHAW = [
    ("funny", "SneakySnooper", "Sneaky Snooper", "Humorous, Mysterious",
     "Snooping and spying: reading chat, checking someone's phone, eavesdropping. About 1 minute."),
    ("dramatic", "HighTension", "High Tension", "Suspenseful, Intense",
     "Nail-biting suspense: close calls, waiting on a result, 'he's not going to make it' moments."),
]


def _get(url: str) -> bytes:
    req = urllib.request.Request(url, headers={"User-Agent": "Spike music fetch"})
    with urllib.request.urlopen(req, timeout=60) as r:
        return r.read()


def _save(mood: str, stem: str, audio_url: str, sidecar: dict) -> None:
    folder = MUSIC_DIR / mood
    folder.mkdir(parents=True, exist_ok=True)
    mp3 = folder / f"{stem}.mp3"
    if not mp3.exists():
        print(f"  downloading {mp3.relative_to(ROOT)}")
        mp3.write_bytes(_get(audio_url))
    (folder / f"{stem}.json").write_text(json.dumps(sidecar, indent=2), encoding="utf-8")


def main() -> int:
    pieces = {p["filename"][:-4]: p for p in json.loads(_get(PIECES_JSON).decode("utf-8", "replace"))}

    for mood, stem, use_for in MACLEOD:
        p = pieces.get(stem)
        if not p:
            print(f"  skip {stem}: not in incompetech's catalogue")
            continue
        title = p["title"]
        _save(mood, stem, INCOMPETECH + urllib.parse.quote(stem) + ".mp3", {
            "title": title,
            "artist": "Kevin MacLeod",
            "mood": mood,
            "feel": p.get("feel", ""),
            "bpm": p.get("bpm", ""),
            "use_for": use_for,
            "description": p.get("description", "")[:300],
            "license": "CC BY 4.0",
            "source": "incompetech.com",
            "url": CC_BY,
            "attribution": f"{title} Kevin MacLeod (incompetech.com)\n"
                           f"Licensed under Creative Commons: By Attribution 4.0 License\n{CC_BY}",
        })

    for mood, stem, title, feel, use_for in SHAW:
        _save(mood, stem, f"https://audionautix.com/Music/{stem}.mp3", {
            "title": title,
            "artist": "Jason Shaw",
            "mood": mood,
            "feel": feel,
            "bpm": "",
            "use_for": use_for,
            "description": "",
            "license": "CC BY 4.0",
            "source": "audionautix.com",
            "url": CC_BY,
            "attribution": f"{title}: Creative Commons Music by Jason Shaw on Audionautix.com",
        })

    print("Done.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
