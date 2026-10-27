"""
Anime text track (report sections 5.2, stages 2 and 5).
Stage 2 part: extract text subtitle streams and sidecar files to data/videos/<id>/subs/.
Stage 5 part: for Japanese-audio ("sub") episodes with English subs, build transcript.json from the
cleaned cues and skip Whisper. Dubs, abridged and sub-less files fall through to faster-whisper.
Output: subs/*.{ass,srt,vtt}, transcript.json (source "subtitles")
"""

import json
import re
import subprocess
from pathlib import Path
from typing import Any, Dict, List, Optional

TEXT_CODECS = {"ass": "ass", "ssa": "ass", "subrip": "srt", "srt": "srt", "webvtt": "vtt", "mov_text": "srt", "text": "srt"}
SIDECAR_EXTS = (".ass", ".ssa", ".srt", ".vtt")
ENGLISH = {"en", "eng"}
# Style names that mark signs, songs and typesetting. op/ed match as whole words only ("Edited" is dialogue).
NON_DIALOGUE_STYLE = re.compile(r"sign|title|kara|romaji|song|insert|\b(op|ed)\b", re.I)


def _read_text(path: Path) -> str:
    """Decode to str. ffmpeg drops non-UTF-8 sidecars, so decode here: UTF-8/UTF-16 by BOM, then cp932, then cp1252."""
    raw = path.read_bytes()
    if raw.startswith((b"\xff\xfe", b"\xfe\xff")):
        return raw.decode("utf-16")
    for enc in ("utf-8-sig", "cp932", "cp1252"):
        try:
            return raw.decode(enc)
        except UnicodeDecodeError:
            continue
    return raw.decode("utf-8", errors="replace")


def _ts(s: str) -> float:
    """'1:02:03.45', '00:00:01,500' or '01:02.500' to seconds."""
    parts = s.strip().replace(",", ".").split(":")
    return sum(float(p) * 60 ** i for i, p in enumerate(reversed(parts)))


def _clean(text: str) -> str:
    text = re.sub(r"\{[^}]*\}", "", text)       # ASS override tags
    text = re.sub(r"<[^>]+>", "", text)          # SRT/VTT markup
    text = text.replace("\\N", " ").replace("\\n", " ").replace("\\h", " ")
    return re.sub(r"\s+", " ", text).strip()


def parse_ass(text: str) -> Dict[str, Any]:
    """Cues from the Events section. Sign and song lines are dropped; song spans are returned (they bound OP and ED)."""
    fields: List[str] = []
    rows = []
    for line in text.splitlines():
        if line.lower().startswith("format:") and not fields and "start" in line.lower():
            fields = [f.strip().lower() for f in line.split(":", 1)[1].split(",")]
        elif line.lower().startswith("dialogue:") and fields:
            vals = line.split(":", 1)[1].lstrip().split(",", len(fields) - 1)
            if len(vals) == len(fields):
                rows.append(dict(zip(fields, vals)))
    styles: Dict[str, int] = {}
    for r in rows:
        styles[r.get("style", "")] = styles.get(r.get("style", ""), 0) + 1
    main_style = max(styles, key=styles.get) if styles else ""
    cues, songs = [], []
    for r in rows:
        raw = r.get("text", "")
        start, end = _ts(r["start"]), _ts(r["end"])
        style = r.get("style", "")
        if "\\k" in raw or (NON_DIALOGUE_STYLE.search(style) and style != main_style):
            if "\\k" in raw or re.search(r"song|kara|\b(op|ed)\b", style, re.I):
                songs.append((start, end))
            continue
        if "\\pos(" in raw and style != main_style:
            continue
        t = _clean(raw)
        if t:
            cues.append({"start": start, "end": end, "text": t, "speaker": (r.get("name") or "").strip() or None})
    return {"cues": cues, "song_spans": songs}


_CUE_TIME = re.compile(r"(\d+:)?\d+:\d+[.,]\d+\s*-->\s*(\d+:)?\d+:\d+[.,]\d+")


def parse_srt_vtt(text: str) -> Dict[str, Any]:
    cues = []
    for block in re.split(r"\n\s*\n", text.replace("\r\n", "\n")):
        lines = block.strip().split("\n")
        i = next((n for n, l in enumerate(lines) if _CUE_TIME.search(l)), None)
        if i is None:
            continue
        a, b = lines[i].split("-->")
        t = _clean(" ".join(lines[i + 1:]))
        if t:
            cues.append({"start": _ts(a), "end": _ts(b.split()[0]), "text": t, "speaker": None})
    return {"cues": cues, "song_spans": []}


def parse_subtitle_file(path: Path) -> Dict[str, Any]:
    text = _read_text(path)
    return parse_ass(text) if path.suffix.lower() in (".ass", ".ssa") else parse_srt_vtt(text)


def _sane(c: Dict[str, Any]) -> bool:
    """A cue with finite, ordered, non-negative times. Subtitle files are untrusted: 'nan', 'inf' or reversed times
    would otherwise reach the judge and the clip cutter."""
    s, e = c["start"], c["end"]
    return s == s and e == e and 0 <= s < e < 86400


def cues_to_segments(cues: List[Dict[str, Any]], limit_s: Optional[float] = None) -> List[Dict[str, Any]]:
    """Transcript segments. Word timings are spread over the cue in proportion to character count, so captions still work."""
    segs = []
    for c in sorted((c for c in cues if _sane(c)), key=lambda c: c["start"]):
        if limit_s and c["start"] >= limit_s:
            break
        toks = c["text"].split()
        total = sum(len(t) for t in toks) or 1
        words, t0 = [], c["start"]
        for tok in toks:
            t1 = t0 + (c["end"] - c["start"]) * len(tok) / total
            words.append({"word": " " + tok, "start": round(t0, 3), "end": round(t1, 3), "probability": 1.0})
            t0 = t1
        segs.append({"id": len(segs), "seek": 0, "start": round(c["start"], 3), "end": round(c["end"], 3),
                     "text": c["text"], "speaker": c["speaker"], "words": words})
    return segs


def _probe_sub_streams(path: str) -> List[Dict[str, Any]]:
    res = subprocess.run(
        ["ffprobe", "-v", "error", "-select_streams", "s", "-show_entries",
         "stream=index,codec_name:stream_tags=language,title", "-of", "json", path],
        capture_output=True, text=True,
    )
    try:
        return json.loads(res.stdout).get("streams", [])
    except json.JSONDecodeError:
        return []


def run_stage2_subs(video_dir: Path, meta: Dict[str, Any]) -> List[Dict[str, Any]]:
    """Copy text subtitle tracks out of the file into subs/. Returns [{path, lang, source}]. Resumes via subs/index.json."""
    subs_dir = video_dir / "subs"
    index = subs_dir / "index.json"
    if index.exists():
        return json.loads(index.read_text(encoding="utf-8"))
    local = meta.get("local_path")
    if not local or not Path(local).exists():
        return []
    subs_dir.mkdir(exist_ok=True)
    found: List[Dict[str, Any]] = []
    for s in _probe_sub_streams(local):
        ext = TEXT_CODECS.get(s.get("codec_name", ""))
        if not ext:  # PGS, VobSub and other image subs cannot become text
            continue
        idx = int(s["index"])
        out = subs_dir / f"{idx}.{ext}"
        r = subprocess.run(["ffmpeg", "-y", "-v", "error", "-i", local, "-map", f"0:{idx}", str(out)])
        if r.returncode == 0 and out.exists():
            lang = ((s.get("tags") or {}).get("language") or "").lower() or None
            found.append({"path": str(out), "lang": lang, "source": "embedded"})
    src = Path(local)
    for side in sorted(src.parent.glob(src.stem + ".*")):
        if side.suffix.lower() in SIDECAR_EXTS:
            tags = {t.lower() for t in side.name[len(src.stem):].split(".")}
            lang = next((t for t in tags if t in ENGLISH), None)
            copy = subs_dir / f"side_{side.name}"
            copy.write_bytes(side.read_bytes())
            found.append({"path": str(copy), "lang": lang, "source": "sidecar"})
    index.write_text(json.dumps(found, indent=2), encoding="utf-8")
    print(f"  [stage 2] Subtitles: {len(found)} text track(s)")
    return found


def pick_english_track(tracks: List[Dict[str, Any]]) -> Optional[Dict[str, Any]]:
    """English track with the most dialogue characters (sign-only tracks lose). An untagged sidecar counts only when nothing is tagged."""
    tagged = [t for t in tracks if t["lang"] in ENGLISH]
    pool = tagged or [t for t in tracks if t["source"] == "sidecar" and t["lang"] is None]
    best, best_n = None, 0
    for t in pool:
        parsed = parse_subtitle_file(Path(t["path"]))
        n = sum(len(c["text"]) for c in parsed["cues"])
        if n > best_n:
            best, best_n = {**t, "parsed": parsed}, n
    return best


def subtitle_transcript(video_dir: Path, anime: Dict[str, Any], tracks: List[Dict[str, Any]],
                        duration: float) -> Optional[Dict[str, Any]]:
    """transcript.json from English subs, or None to let faster-whisper run.
    Priority (report 5.2): English subs for sub audio; whisper for dubs (dubtitles drift from the dub), abridged,
    hard-subbed files and files with no English text track."""
    path = video_dir / "transcript.json"
    if path.exists() or anime.get("audio_kind") != "sub" or anime.get("hardsubbed"):
        return None
    track = pick_english_track(tracks)
    if not track:
        return None
    segs = cues_to_segments(track["parsed"]["cues"], duration or None)
    transcript = {
        "language": "en", "language_probability": 1.0, "duration": round(duration, 2),
        "source": "subtitles", "subtitle_track": track["path"],
        "song_spans": track["parsed"]["song_spans"],
        "transcription_time_s": 0.0, "rtf": 0.0,
        "segment_count": len(segs), "word_count": sum(len(s["words"]) for s in segs),
        "segments": segs,
    }
    path.write_text(json.dumps(transcript, indent=2), encoding="utf-8")
    print(f"  [stage 5] Text track from subtitles ({track['source']}): {len(segs)} segments, whisper skipped")
    return transcript


if __name__ == "__main__":
    ass = (
        "[Events]\nFormat: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text\n"
        "Dialogue: 0,0:00:01.00,0:00:03.00,Default,Goku,0,0,0,,{\\i1}Hello,\\Nworld{\\i0}\n"
        "Dialogue: 0,0:00:04.00,0:00:05.00,Default,,0,0,0,,Edited line\n"
        "Dialogue: 0,0:00:06.00,0:00:07.00,Sign,,0,0,0,,{\\pos(10,10)}SHOP\n"
        "Dialogue: 0,0:01:00.00,0:01:05.00,OP-romaji,,0,0,0,,{\\k20}ka{\\k30}ra\n"
        "Dialogue: 0,0:00:08.00,0:00:09.00,Top,,0,0,0,,{\\pos(1,1)}floating\n"
    )
    p = parse_ass(ass)
    assert [c["text"] for c in p["cues"]] == ["Hello, world", "Edited line"], p
    assert p["cues"][0]["speaker"] == "Goku" and p["song_spans"] == [(60.0, 65.0)]
    srt = parse_srt_vtt("1\n00:00:01,000 --> 00:00:02,500\n<i>Hi</i>\nthere\n\n2\n00:01:00,000 --> 00:01:01,000\nBye\n")
    assert [c["text"] for c in srt["cues"]] == ["Hi there", "Bye"] and srt["cues"][1]["start"] == 60.0
    segs = cues_to_segments(p["cues"], limit_s=3.5)
    assert len(segs) == 1 and segs[0]["words"][0]["word"] == " Hello," and abs(segs[0]["words"][-1]["end"] - 3.0) < 1e-6
    assert pick_english_track([{"path": "x", "lang": "jpn", "source": "embedded"}]) is None
    bad = [{"start": float("nan"), "end": 5.0, "text": "a b", "speaker": None}, {"start": 9.0, "end": 3.0, "text": "c d", "speaker": None},
           {"start": -2.0, "end": 1.0, "text": "e f", "speaker": None}, {"start": 1.0, "end": float("inf"), "text": "g h", "speaker": None},
           {"start": 1.0, "end": 2.0, "text": "ok fine", "speaker": None}]
    assert [s["text"] for s in cues_to_segments(bad)] == ["ok fine"]
    print("ok")
