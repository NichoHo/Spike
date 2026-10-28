"""
Per-episode fan data for the New page's "From anime" tab, from MyAnimeList through Jikan (no API key).
MAL users rate each episode out of 5 and flag filler and recap episodes. No public source has per-episode view counts,
so the score and the episode's forum replies (how much people talked about it) stand in for them.
Sources in order: the official Jikan, then jikan-edge, a third-party Jikan copy that also returns forum replies.
Each season is cached for an hour (anilist._cached); when the official Jikan fails it is skipped for 10 minutes.
"""

import datetime
import json
import time
import urllib.request
from typing import Any, Callable, Dict, List, Optional

from src.anilist import _cached

MAX_PAGES = 15         # 100 episodes a page: enough for One Piece; longer shows list their first 1,500
NEW_DAYS = 7           # an episode aired this recently is "new": clip demand peaks the week it airs
SKIP_S = 600
_down_until = 0.0      # the official Jikan failed: try the copy first until then


def _get(url: str, timeout: float) -> Dict[str, Any]:
    req = urllib.request.Request(url, headers={"Accept": "application/json", "User-Agent": "Spike/1.0"})
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return json.loads(r.read())


def _date(text: Optional[str]) -> Optional[str]:
    """ISO date from "2023-07-06T00:00:00+00:00" (Jikan) or "Jul 6, 2023" (jikan-edge), else None."""
    if not text:
        return None
    try:
        return datetime.date.fromisoformat(text[:10]).isoformat()
    except ValueError:
        pass
    try:
        return datetime.datetime.strptime(text.strip(), "%b %d, %Y").date().isoformat()
    except ValueError:
        return None


def _row(n: Any, e: Dict[str, Any], replies: Optional[int]) -> Dict[str, Any]:
    score = e.get("score")
    return {"n": int(n), "title": e.get("title") or None, "score": round(float(score), 2) if score else None,
            "replies": replies, "filler": bool(e.get("filler")), "recap": bool(e.get("recap")), "aired": _date(e.get("aired"))}


def _jikan(mal_id: int, get: Callable[[str, float], Dict[str, Any]]) -> List[Dict[str, Any]]:
    # Shape recalled from Jikan v4, not seen live (it was down when this was written): episode number in mal_id
    rows: List[Dict[str, Any]] = []
    for page in range(1, MAX_PAGES + 1):
        d = get(f"https://api.jikan.moe/v4/anime/{mal_id}/episodes?page={page}", 6)
        rows += [_row(e["mal_id"], e, None) for e in d.get("data") or []]
        if not (d.get("pagination") or {}).get("has_next_page"):
            break
    return rows


def _edge(mal_id: int, get: Callable[[str, float], Dict[str, Any]]) -> List[Dict[str, Any]]:
    rows: List[Dict[str, Any]] = []
    for page in range(1, MAX_PAGES + 1):
        d = get(f"https://jikan.lucashdo.com/v1/anime/{mal_id}/episodes?page={page}", 15)
        rows += [_row(e["number"], e, e.get("forumReplies")) for e in d.get("data") or []]
        if not ((d.get("meta") or {}).get("pagination") or {}).get("hasNextPage"):
            break
    return rows


def episodes(mal_id: int, get: Callable[[str, float], Dict[str, Any]] = _get,
             today: Optional[datetime.date] = None) -> List[Dict[str, Any]]:
    """The season's episodes in order, each as {n, title, score, replies, filler, recap, aired, new}.
    score: MAL fan rating out of 5, None before anyone rated it. replies: forum replies, None from the official Jikan."""
    global _down_until

    def fetch() -> List[Dict[str, Any]]:
        global _down_until
        if time.time() >= _down_until:
            try:
                return _jikan(mal_id, get)
            except Exception:
                _down_until = time.time() + SKIP_S
        return _edge(mal_id, get)

    rows = _cached(f"ep:{mal_id}", fetch)
    cutoff = ((today or datetime.date.today()) - datetime.timedelta(days=NEW_DAYS)).isoformat()
    return [{**r, "new": bool(r["aired"] and r["aired"] >= cutoff)} for r in rows]


if __name__ == "__main__":
    import src.anilist as anilist
    edge_pages = {
        1: {"data": [{"number": 1, "title": "One", "aired": "Jul 6, 2023", "score": 4.25, "forumReplies": 593, "filler": False, "recap": False},
                     {"number": 2, "title": "Two", "aired": "Oct 25, 2026", "score": None, "forumReplies": 3, "filler": True, "recap": False}],
            "meta": {"pagination": {"hasNextPage": True}}},
        2: {"data": [{"number": 3, "title": None, "aired": None, "score": 3.9, "forumReplies": None, "filler": False, "recap": True}],
            "meta": {"pagination": {"hasNextPage": False}}},
    }
    calls: List[str] = []

    def fake(url: str, timeout: float) -> Dict[str, Any]:
        calls.append(url)
        if "api.jikan.moe" in url:
            raise OSError("down")
        return edge_pages[int(url.rsplit("=", 1)[1])]

    today = datetime.date(2026, 10, 28)
    eps = episodes(5, fake, today)
    assert [e["n"] for e in eps] == [1, 2, 3]                                  # both pages, after the official Jikan failed
    assert eps[0] == {"n": 1, "title": "One", "score": 4.25, "replies": 593, "filler": False, "recap": False,
                      "aired": "2023-07-06", "new": False}
    assert eps[1]["new"] and eps[1]["score"] is None and eps[1]["filler"]       # aired 3 days ago, not rated yet
    assert eps[2]["recap"] and eps[2]["aired"] is None and not eps[2]["new"]
    n = len(calls)
    anilist._cache.clear()
    episodes(6, fake, today)
    assert not any("api.jikan.moe" in u for u in calls[n:]), "the official Jikan is skipped for a while after it fails"

    _down_until = 0.0
    anilist._cache.clear()
    jikan_page = {"data": [{"mal_id": 1, "title": "One", "aired": "2026-10-27T00:00:00+00:00", "score": 4.6, "filler": False, "recap": False}],
                  "pagination": {"has_next_page": False}}
    eps = episodes(7, lambda url, t: jikan_page, today)
    assert eps == [{"n": 1, "title": "One", "score": 4.6, "replies": None, "filler": False, "recap": False, "aired": "2026-10-27", "new": True}]
    print("ok")
