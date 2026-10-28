"""
Stage 1 (anime): identify the show and set source flags.
Report section 5.1. Output: data/videos/<id>/anime.json
Allowlist lookup (report section 4) is phase 0 and not built yet, so post_allowed is always False.
"""

import json
import re
import subprocess
import urllib.request
from pathlib import Path
from typing import Any, Dict, Optional

from src.config import DATA_DIR

ANILIST_URL = "https://graphql.anilist.co"
ANIME_CACHE_DIR = DATA_DIR / "anime_cache"
ANILIST_QUERY = """
query ($id: Int, $search: String) {
  Media(id: $id, search: $search, type: ANIME) {
    id idMal title { romaji english } format episodes duration genres isAdult
    tags { name rank category isMediaSpoiler isAdult }
    characters(sort: ROLE, perPage: 10) { nodes { name { full } } }
  }
}"""
PARODY_TAG_MIN_RANK = 50

# "[Group] Show Name - 12 [1080p].mkv", "Show.Name.S01E12.mkv", "Show Name - 12.mkv"
_EP_RES = [
    re.compile(r"[Ss]\d{1,2}[Ee](\d{1,4})"),
    re.compile(r"\s-\s(\d{1,4})(?:v\d)?(?:\s|$|\[|\()"),
    re.compile(r"[Ee]p?(?:isode)?[ ._]?(\d{1,4})\b"),
]


def parse_filename(stem: str) -> Dict[str, Any]:
    """Guess (title, episode) from a release-style filename. Either may be None."""
    s = re.sub(r"\[[^\]]*\]|\([^)]*\)", " ", stem)  # drop [Group] [1080p] (BD) tags
    s = s.replace("_", " ")
    s = re.sub(r"(?<=\w)\.(?=\w)", " ", s)
    episode = None
    cut = len(s)
    for rx in _EP_RES:
        m = rx.search(s + " ")
        if m:
            episode, cut = int(m.group(1)), m.start()
            break
    title = re.sub(r"\s+", " ", s[:cut]).strip(" -")
    return {"title": title or None, "episode": episode}


def query_anilist(anilist_id: Optional[int], search: Optional[str]) -> Dict[str, Any]:
    """One AniList call per show, cached forever by id (and by search string until the id is known)."""
    ANIME_CACHE_DIR.mkdir(parents=True, exist_ok=True)
    key = str(anilist_id) if anilist_id else "search_" + re.sub(r"\W+", "_", (search or "").lower())
    cache = ANIME_CACHE_DIR / f"{key}.json"
    if cache.exists():
        cached = json.loads(cache.read_text(encoding="utf-8"))
        if "characters" in cached:  # entries cached before the characters field was added are refetched
            return cached
    variables = {"id": anilist_id} if anilist_id else {"search": search}  # a null filter matches nothing
    body = json.dumps({"query": ANILIST_QUERY, "variables": variables}).encode()
    req = urllib.request.Request(
        ANILIST_URL, data=body, headers={"Content-Type": "application/json", "Accept": "application/json",
                 "User-Agent": "Spike/1.0"}
    )
    with urllib.request.urlopen(req, timeout=20) as r:
        media = json.loads(r.read())["data"]["Media"]
    cache.write_text(json.dumps(media, indent=2), encoding="utf-8")
    (ANIME_CACHE_DIR / f"{media['id']}.json").write_text(json.dumps(media, indent=2), encoding="utf-8")
    return media


def _default_audio_lang(local_path: Optional[str]) -> Optional[str]:
    """Language tag of the first audio stream, or None."""
    if not local_path:
        return None
    res = subprocess.run(
        ["ffprobe", "-v", "error", "-select_streams", "a", "-show_entries", "stream=index:stream_tags=language",
         "-of", "json", local_path],
        capture_output=True, text=True,
    )
    try:
        streams = json.loads(res.stdout).get("streams", [])
        return (streams[0].get("tags") or {}).get("language") if streams else None
    except (json.JSONDecodeError, AttributeError):
        return None


def build_anime_flags(meta: Dict[str, Any], media: Dict[str, Any], parsed: Dict[str, Any],
                      overrides: Dict[str, Any], audio_lang: Optional[str]) -> Dict[str, Any]:
    """Pure: combine AniList media, filename guess, user overrides and the audio tag into anime.json."""
    audio_kind = overrides.get("audio_kind")
    name = f"{meta.get('title', '')} {meta.get('uploader', '')}".lower()
    tags = media.get("tags") or []
    parody = (
        audio_kind == "abridged"
        or any(t["name"] == "Parody" and (t.get("rank") or 0) >= PARODY_TAG_MIN_RANK for t in tags)
        or "abridged" in name
    )
    dub = audio_kind == "dub" or audio_lang == "eng"
    if not audio_kind:
        audio_kind = "abridged" if parody and "abridged" in name else ("dub" if dub else "sub")
    return {
        "anilist_id": media["id"],
        "mal_id": media.get("idMal"),
        "title": (media.get("title") or {}).get("english") or (media.get("title") or {}).get("romaji"),
        "episode": overrides.get("episode") or parsed.get("episode"),
        "format": media.get("format"),
        "genres": media.get("genres") or [],
        "tags": [{k: t.get(k) for k in ("name", "rank", "category", "isMediaSpoiler")} for t in tags],
        "audio_kind": audio_kind,
        "dub": dub,
        "parody": parody,
        "hardsubbed": bool(overrides.get("hardsubbed", False)),
        "characters": [n["name"]["full"] for n in ((media.get("characters") or {}).get("nodes") or [])],
        "post_allowed": False,
        "allowlist": None,
    }


ANIME_OPT_KEYS = ("anilist_id", "episode", "audio_kind", "hardsubbed", "title_match", "youtube_url", "youtube_offset_s")
YOUTUBE_HOSTS = {"www.youtube.com", "youtube.com", "m.youtube.com", "youtu.be"}


def sanitize_anime_opts(opts: Any) -> Dict[str, Any]:
    """The job's `anime` settings, keeping only valid values of known keys. Anything else is dropped, not guessed at."""
    o = opts if isinstance(opts, dict) else {}
    out: Dict[str, Any] = {}

    def num(v: Any, lo: float, hi: float, as_int: bool) -> Optional[float]:
        try:
            x = float(v)
        except (TypeError, ValueError):
            return None
        if x != x or not lo <= x <= hi or (as_int and x != int(x)) or isinstance(v, bool):
            return None
        return int(x) if as_int else x

    for key, lo, hi in (("anilist_id", 1, 10**9), ("episode", 0, 9999)):
        if (v := num(o.get(key), lo, hi, True)) is not None:
            out[key] = v
    if (v := num(o.get("youtube_offset_s"), -3600.0, 3600.0, False)) is not None:
        out["youtube_offset_s"] = v
    if o.get("audio_kind") in ("dub", "sub", "abridged"):
        out["audio_kind"] = o["audio_kind"]
    for key in ("hardsubbed", "title_match"):
        if isinstance(o.get(key), bool):
            out[key] = o[key]
    url = o.get("youtube_url")
    if isinstance(url, str) and len(url) < 300:
        from urllib.parse import urlparse
        u = urlparse(url)
        if u.scheme == "https" and u.hostname in YOUTUBE_HOSTS:
            out["youtube_url"] = url
    return out


def run_stage1_anime(video_dir: Path, meta: Dict[str, Any], overrides: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
    """Resumes if anime.json exists. overrides: anilist_id, episode, audio_kind, hardsubbed."""
    out = video_dir / "anime.json"
    if out.exists():
        print(f"  [stage 1] Resuming: found {out.name}")
        return json.loads(out.read_text(encoding="utf-8"))

    overrides = overrides or {}
    parsed = parse_filename(Path(meta.get("local_path") or meta.get("title") or "").stem or meta.get("title", ""))
    media = query_anilist(overrides.get("anilist_id"), None if overrides.get("anilist_id") else parsed["title"])
    audio_lang = _default_audio_lang(meta.get("local_path"))
    anime = build_anime_flags(meta, media, parsed, overrides, audio_lang)
    out.write_text(json.dumps(anime, indent=2), encoding="utf-8")
    print(f"  [stage 1] Anime: {anime['title']!r} ep {anime['episode']} ({anime['audio_kind']}, parody={anime['parody']})")
    return anime


if __name__ == "__main__":
    assert parse_filename("[SubsPlease] Frieren - 12 (1080p) [ABC123]") == {"title": "Frieren", "episode": 12}
    assert parse_filename("Cowboy.Bebop.S01E01.1080p") == {"title": "Cowboy Bebop", "episode": 1}
    assert parse_filename("Dragon Ball Z Abridged Episode 12")["episode"] == 12
    m = {"id": 1, "idMal": 1, "title": {"english": "X"}, "tags": [{"name": "Parody", "rank": 60}], "genres": []}
    a = build_anime_flags({"title": "x"}, m, {"episode": 3}, {}, "eng")
    assert a["parody"] and a["dub"] and a["episode"] == 3 and a["post_allowed"] is False
    b = build_anime_flags({"title": "x"}, {**m, "tags": []}, {}, {"audio_kind": "abridged"}, None)
    assert b["parody"] and b["audio_kind"] == "abridged"
    ok = sanitize_anime_opts({"anilist_id": "813", "episode": 12, "audio_kind": "abridged", "hardsubbed": True, "title_match": 1,
                              "youtube_url": "https://www.youtube.com/watch?v=dQw4w9WgXcQ", "youtube_offset_s": "5", "evil": "x"})
    assert ok == {"anilist_id": 813, "episode": 12, "audio_kind": "abridged", "hardsubbed": True,
                  "youtube_url": "https://www.youtube.com/watch?v=dQw4w9WgXcQ", "youtube_offset_s": 5.0}, ok
    assert sanitize_anime_opts({"anilist_id": -1, "episode": 1.5, "audio_kind": "x; rm", "youtube_offset_s": "nan",
                                "youtube_url": "https://evil.example/watch?v=1"}) == {}
    assert sanitize_anime_opts({"youtube_url": "http://youtu.be/abc"}) == {} and sanitize_anime_opts(None) == {}
    assert sanitize_anime_opts({"anilist_id": True}) == {}
    print("ok")
