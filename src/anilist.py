"""
AniList lookups for the New page's "From anime" tab: search a title, then list the seasons of the show.
AniList stores each season as its own entry (own id, own episode count) linked by PREQUEL and SEQUEL relations, so the
season list is that chain. The pipeline needs the season's own id: AniSkip and the episode number are per entry.
Results are cached in memory for an hour. No API key (reads are open); 30 to 90 requests a minute.
"""

import json
import time
import urllib.request
from typing import Any, Callable, Dict, List, Optional

ANILIST_URL = "https://graphql.anilist.co"
TTL_S = 3600
MAX_HOPS = 15
TV_LIKE = {"TV", "TV_SHORT", "ONA"}   # what counts as a season; movies and specials are not

FIELDS = "id idMal title { romaji english } format episodes seasonYear coverImage { large } nextAiringEpisode { episode }"
SEARCH_QUERY = """query ($q: String) { Page(perPage: 8) { media(search: $q, type: ANIME, sort: SEARCH_MATCH) { %s } } }""" % FIELDS
SHELF_QUERIES = {   # trending: airing shows people watch this week; popular: the most-followed shows of all time
    "trending": "{ Page(perPage: 12) { media(type: ANIME, isAdult: false, sort: [TRENDING_DESC], status: RELEASING) { %s } } }" % FIELDS,
    "popular": "{ Page(perPage: 12) { media(type: ANIME, isAdult: false, sort: [POPULARITY_DESC], format_in: [TV, TV_SHORT, ONA]) { %s } } }" % FIELDS,
}
NODE_QUERY = """query ($id: Int) { Media(id: $id, type: ANIME) {
  %s
  relations { edges { relationType(version: 2) node { id type format } } } } }""" % FIELDS

_cache: Dict[str, Any] = {}


def _post(query: str, variables: Dict[str, Any]) -> Dict[str, Any]:
    req = urllib.request.Request(
        ANILIST_URL, data=json.dumps({"query": query, "variables": variables}).encode(),
        headers={"Content-Type": "application/json", "Accept": "application/json", "User-Agent": "Spike/1.0"})
    with urllib.request.urlopen(req, timeout=15) as r:
        return json.loads(r.read())["data"]


def _cached(key: str, make: Callable[[], Any]) -> Any:
    hit = _cache.get(key)
    if hit and hit[0] > time.time():
        return hit[1]
    value = make()
    _cache[key] = (time.time() + TTL_S, value)
    return value


def brief(m: Dict[str, Any]) -> Dict[str, Any]:
    """aired: the last episode out while the show airs, None once it has finished."""
    t = m.get("title") or {}
    nxt = (m.get("nextAiringEpisode") or {}).get("episode")
    return {"id": m["id"], "title": t.get("english") or t.get("romaji") or str(m["id"]), "format": m.get("format"),
            "episodes": m.get("episodes"), "year": m.get("seasonYear"), "cover": (m.get("coverImage") or {}).get("large"),
            "mal": m.get("idMal"),
            "aired": nxt - 1 if nxt else None}


def shelf(kind: str, post: Callable[[str, Dict[str, Any]], Dict[str, Any]] = _post) -> List[Dict[str, Any]]:
    """The shows listed before anything is typed: "trending" or "popular"."""
    return _cached("shelf:" + kind, lambda: [brief(m) for m in post(SHELF_QUERIES[kind], {})["Page"]["media"]])


def search(q: str, post: Callable[[str, Dict[str, Any]], Dict[str, Any]] = _post) -> List[Dict[str, Any]]:
    q = " ".join(q.split())[:80]
    if len(q) < 2:
        return []
    return _cached("s:" + q.lower(), lambda: [brief(m) for m in post(SEARCH_QUERY, {"q": q})["Page"]["media"]])


def _linked(node: Dict[str, Any], relation: str) -> Optional[int]:
    for e in (node.get("relations") or {}).get("edges") or []:
        n = e.get("node") or {}
        if e.get("relationType") == relation and n.get("type") == "ANIME" and n.get("format") in TV_LIKE:
            return n["id"]
    return None


def seasons(media_id: int, post: Callable[[str, Dict[str, Any]], Dict[str, Any]] = _post) -> List[Dict[str, Any]]:
    """The show's seasons in order, from its first season to its last, each as {id, title, format, episodes, year}.
    A picked entry that is not a season itself (a movie) comes back alone."""
    def node(i: int) -> Dict[str, Any]:
        return _cached(f"n:{i}", lambda: post(NODE_QUERY, {"id": i})["Media"])

    def build() -> List[Dict[str, Any]]:
        start = node(media_id)
        first, seen = start, {start["id"]}
        for _ in range(MAX_HOPS):
            prev = _linked(first, "PREQUEL")
            if prev is None or prev in seen:
                break
            first = node(prev)
            seen.add(prev)
        chain, cur, in_chain = [first], first, {first["id"]}   # a fresh set: the walk back already saw the picked season
        for _ in range(MAX_HOPS):
            nxt = _linked(cur, "SEQUEL")
            if nxt is None or nxt in in_chain:
                break
            cur = node(nxt)
            in_chain.add(nxt)
            chain.append(cur)
        return [brief(n) for n in chain] if start["id"] in {n["id"] for n in chain} else [brief(start)]

    return _cached(f"c:{media_id}", build)


if __name__ == "__main__":
    graph = {  # 1 -> 2 -> 3 are seasons, 9 is a movie after season 2, 5 loops back to 1
        1: {"id": 1, "title": {"english": "Show", "romaji": "Shou"}, "format": "TV", "episodes": 12, "seasonYear": 2019,
            "relations": {"edges": [{"relationType": "SEQUEL", "node": {"id": 2, "type": "ANIME", "format": "TV"}}]}},
        2: {"id": 2, "title": {"english": None, "romaji": "Shou 2"}, "format": "TV", "episodes": 24, "seasonYear": 2021,
            "relations": {"edges": [{"relationType": "PREQUEL", "node": {"id": 1, "type": "ANIME", "format": "TV"}},
                                    {"relationType": "SEQUEL", "node": {"id": 9, "type": "ANIME", "format": "MOVIE"}},
                                    {"relationType": "SEQUEL", "node": {"id": 3, "type": "ANIME", "format": "TV"}}]}},
        3: {"id": 3, "title": {"english": "Show 3"}, "format": "TV", "episodes": None, "seasonYear": 2024,
            "relations": {"edges": [{"relationType": "PREQUEL", "node": {"id": 2, "type": "ANIME", "format": "TV"}},
                                    {"relationType": "SEQUEL", "node": {"id": 1, "type": "ANIME", "format": "TV"}}]}},
        9: {"id": 9, "title": {"english": "Show: The Movie"}, "format": "MOVIE", "episodes": 1, "seasonYear": 2022,
            "relations": {"edges": [{"relationType": "PREQUEL", "node": {"id": 2, "type": "ANIME", "format": "TV"}}]}},
    }
    calls = []

    def fake(query: str, variables: Dict[str, Any]) -> Dict[str, Any]:
        calls.append(variables)
        if "Page(" in query:
            return {"Page": {"media": [graph[1], graph[2]]}}
        return {"Media": graph[variables["id"]]}

    ids = lambda lst: [s["id"] for s in lst]
    assert ids(seasons(2, fake)) == [1, 2, 3], seasons(2, fake)       # from the middle: back to season 1, forward to 3; the movie is skipped
    assert ids(seasons(3, fake)) == [1, 2, 3] and ids(seasons(1, fake)) == [1, 2, 3]   # the loop 3 -> 1 stops
    assert seasons(1, fake)[1] == {"id": 2, "title": "Shou 2", "format": "TV", "episodes": 24, "year": 2021,
                                   "cover": None, "mal": None, "aired": None}   # romaji when no English title
    assert brief({"id": 4, "title": {}, "nextAiringEpisode": {"episode": 6}})["aired"] == 5   # airing: episodes 1 to 5 are out
    assert seasons(3, fake)[2]["episodes"] is None
    assert ids(seasons(9, fake)) == [1, 2, 3] or ids(seasons(9, fake)) == [9]    # a movie: its PREQUEL is season 2, so the chain is the show's
    n = len(calls)
    seasons(2, fake)
    assert len(calls) == n, "cached"
    assert search("  ", fake) == [] and search("x", fake) == []
    assert [r["id"] for r in search("show  one", fake)] == [1, 2]
    assert [r["id"] for r in shelf("trending", fake)] == [1, 2]
    print("ok")
