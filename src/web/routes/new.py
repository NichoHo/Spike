"""
Spike: New job submission routes.
Blueprint §10.4, §8 (Security T2: upload verification & URL whitelist).
"""

import os
import time
import uuid
import subprocess
from urllib.parse import urlparse
from pathlib import Path
from typing import Optional, Dict, Any

from fastapi import APIRouter, Request, Depends, Form, UploadFile, File, HTTPException
from fastapi.responses import HTMLResponse, RedirectResponse
from starlette.status import HTTP_400_BAD_REQUEST, HTTP_404_NOT_FOUND, HTTP_303_SEE_OTHER

from src import anilist, episode_scores
from src.pipeline.stage1_anime import sanitize_anime_opts
from src.config import (
    UPLOADS_DIR,
    MAX_UPLOAD_SIZE_BYTES,
    ALLOWED_UPLOAD_EXTS,
    ALLOWED_URL_DOMAINS,
    MAX_TARGET_CLIPS,
    VALID_LAYOUTS,
)
from src.db import (
    register_video,
    list_sources,
    get_source,
    list_review_clips,
    log_event,
)
from src import requirements
from src.web.auth import get_current_user


router = APIRouter()


def _verify_video_file(file_path: Path) -> bool:
    """Use ffprobe to verify the uploaded file contains valid video/audio streams."""
    try:
        cmd = [
            "ffprobe", "-v", "error",
            "-show_entries", "stream=codec_type",
            "-of", "csv=p=0",
            str(file_path)
        ]
        res = subprocess.run(cmd, capture_output=True, text=True, timeout=15)
        streams = res.stdout.strip().splitlines()
        # Accept if at least one stream is video or audio
        return any(s in ("video", "audio") for s in streams)
    except Exception:
        return False


@router.get("/new", response_class=HTMLResponse)
async def new_job_page(
    request: Request,
    tab: str = "streamer",
    user: Dict[str, Any] = Depends(get_current_user),
):
    templates = request.app.state.templates
    from src.moment_render import DEFAULT_PRESETS, source_presets
    sources = [dict(s) for s in list_sources()]
    review_count = len(list_review_clips(status="ready"))

    return templates.TemplateResponse(
        request=request,
        name="pages/new.html",
        context={
            "page_title": "New Job",
            "active_nav": "new",
            "page_width": "narrow",
            "user": user,
            "sources": sources,
            "presets": DEFAULT_PRESETS,
            "source_presets": {s["id"]: source_presets(s) for s in sources},  # the form refills when a source is picked
            "active_tab": tab,
            "review_count": review_count,
        },
    )


def parse_presets(layout: str, captions: Optional[str], music: str, cut_pauses: str, letterbox_style: str,
                  caption_style: str, ai_cuts: Optional[str] = None) -> Dict[str, Any]:
    """Render options from the New page or the source form, in the shape a job's settings use.
    Switches send their value when on and nothing when off. Profanity is always masked."""
    if (
        layout not in VALID_LAYOUTS
        or music not in ("auto", "on", "off")
        or cut_pauses not in ("auto", "natural", "off")
        or caption_style not in ("bold_pop", "karaoke", "clean")
    ):
        raise HTTPException(status_code=HTTP_400_BAD_REQUEST, detail="Invalid processing option.")
    return {
        "layout": layout,
        "letterbox_style": "title" if letterbox_style == "title" else "blur",
        "captions": captions not in (None, "off"),
        "caption_style": caption_style,
        "profanity_mask": True,
        "music": "auto" if music == "auto" else music == "on",
        "cut_pauses": cut_pauses,
        "ai_cuts": ai_cuts not in (None, "off"),
    }


def build_anime_settings(audio: str, anilist_id: str, episode: str, hardsubbed: Optional[str], title_match: Optional[str],
                         youtube_url: str, youtube_offset: str) -> Dict[str, Any]:
    """The job's `anime` settings from the New page, or a 400 that names the bad field. The runner validates again."""
    def bad(field: str) -> HTTPException:
        return HTTPException(status_code=HTTP_400_BAD_REQUEST, detail=f"Invalid anime option: {field}.")

    opts: Dict[str, Any] = {"audio_kind": audio, "hardsubbed": hardsubbed not in (None, "off"), "title_match": title_match not in (None, "off")}
    for key, raw, name in (("anilist_id", anilist_id, "AniList ID"), ("episode", episode, "episode")):
        if raw.strip():
            if not raw.strip().isdigit():
                raise bad(name)
            opts[key] = int(raw)
    if youtube_offset.strip():
        try:
            opts["youtube_offset_s"] = float(youtube_offset)
        except ValueError:
            raise bad("time offset")
    if youtube_url.strip():
        opts["youtube_url"] = youtube_url.strip()
    clean = sanitize_anime_opts(opts)
    for key, name in (("audio_kind", "audio"), ("anilist_id", "AniList ID"), ("episode", "episode"),
                      ("youtube_url", "YouTube link (use an https youtube.com or youtu.be link)"), ("youtube_offset_s", "time offset")):
        if key in opts and key not in clean:
            raise bad(name)
    return clean


@router.get("/new/anime/search")
async def anime_search(q: str, user: Dict[str, Any] = Depends(get_current_user)):
    """Titles matching q, for the From anime tab."""
    from starlette.concurrency import run_in_threadpool
    try:
        return {"results": await run_in_threadpool(anilist.search, q)}
    except Exception:
        raise HTTPException(status_code=502, detail="AniList did not answer. Try again in a moment.")


@router.get("/new/anime/shelf")
async def anime_shelf(kind: str = "trending", user: Dict[str, Any] = Depends(get_current_user)):
    """Trending or popular shows, listed on the From anime tab before anything is typed."""
    from starlette.concurrency import run_in_threadpool
    if kind not in anilist.SHELF_QUERIES:
        raise HTTPException(status_code=HTTP_400_BAD_REQUEST, detail="Invalid list.")
    try:
        return {"results": await run_in_threadpool(anilist.shelf, kind)}
    except Exception:
        raise HTTPException(status_code=502, detail="AniList did not answer. Try again in a moment.")


@router.get("/new/anime/seasons")
async def anime_seasons(id: int, user: Dict[str, Any] = Depends(get_current_user)):
    """The seasons of the show that title belongs to, each with its own AniList id and episode count."""
    from starlette.concurrency import run_in_threadpool
    if id < 1:
        raise HTTPException(status_code=HTTP_400_BAD_REQUEST, detail="Invalid anime.")
    try:
        return {"seasons": await run_in_threadpool(anilist.seasons, id)}
    except Exception:
        raise HTTPException(status_code=502, detail="AniList did not answer. Try again in a moment.")


@router.get("/new/anime/episodes")
async def anime_episodes(mal: int, user: Dict[str, Any] = Depends(get_current_user)):
    """A season's episodes with MyAnimeList fan scores, forum replies and filler/recap flags, by its MyAnimeList id."""
    from starlette.concurrency import run_in_threadpool
    if mal < 1:
        raise HTTPException(status_code=HTTP_400_BAD_REQUEST, detail="Invalid anime.")
    try:
        return {"episodes": await run_in_threadpool(episode_scores.episodes, mal)}
    except Exception:
        raise HTTPException(status_code=502, detail="Episode ratings are not available right now.")


def clean_label(text: str) -> str:
    """A job title from the form: one line, no control characters, at most 120 characters."""
    return " ".join("".join(c if c.isprintable() else " " for c in text).split())[:120]


_VOD_TTL = 300
_vod_cache: Dict[int, tuple] = {}


@router.get("/new/vods")
def recent_vods(
    source_id: int,
    user: Dict[str, Any] = Depends(get_current_user),
):
    """Recent videos for a source, used to autofill the VOD field, plus the one an empty field would pick."""
    src = get_source(source_id)
    if not src:
        raise HTTPException(status_code=HTTP_404_NOT_FOUND, detail="Source not found.")

    hit = _vod_cache.get(source_id)
    if hit and hit[0] > time.time():
        return hit[1]

    from src.watcher import fetch_youtube_channel_rss, fetch_twitch_latest_vods, latest_finished_vod  # lazy: pulls in yt_dlp

    fetch = fetch_youtube_channel_rss if src["kind"] == "youtube" else fetch_twitch_latest_vods
    results = fetch(src["external_id"])[:10]
    data = {"results": results, "latest": latest_finished_vod(src["kind"], src["external_id"], results) if results else None}
    if results:  # don't cache a failed/empty fetch
        _vod_cache[source_id] = (time.time() + _VOD_TTL, data)
    return data


@router.post("/new/submit")
async def submit_new_job(
    request: Request,
    tab: str = Form("upload"),
    url: Optional[str] = Form(None),
    source_id: Optional[int] = Form(None),
    vod_url: Optional[str] = Form(None),
    target_clips: str = Form(""),  # blank = auto (stage 6 scales it with video length)
    layout: Optional[str] = Form(None),  # absent when the options are hidden: the job follows the source's presets
    captions: Optional[str] = Form(None),  # switch: "on" when on
    music: str = Form("auto"),
    cut_pauses: str = Form("off"),
    ai_cuts: Optional[str] = Form(None),  # switch: "on" when on
    letterbox_style: str = Form("blur"),  # the toggle sends "title" when on
    caption_style: str = Form("bold_pop"),
    kind: str = Form("stream"),  # "stream" or "anime"; only the Paste URL and Upload tabs send it
    anime_audio: str = Form("sub"),
    anime_id: str = Form(""),
    anime_episode: str = Form(""),
    anime_hardsubbed: Optional[str] = Form(None),
    anime_title_match: Optional[str] = Form(None),
    anime_youtube_url: str = Form(""),
    anime_youtube_offset: str = Form(""),
    anime_source: str = Form("file"),   # From anime tab: where the video comes from, "file" or "url"
    anime_label: str = Form(""),        # From anime tab: the job's title, such as "Show Season 2 E5"
    file: Optional[UploadFile] = File(None),
    user: Dict[str, Any] = Depends(get_current_user),
):
    UPLOADS_DIR.mkdir(parents=True, exist_ok=True)

    label = clean_label(anime_label) if tab == "anime" else ""
    if tab == "anime":  # the picked show and episode, then the same upload or link handling as those two tabs
        if anime_source not in ("file", "url"):
            raise HTTPException(status_code=HTTP_400_BAD_REQUEST, detail="Invalid video choice.")
        if not anime_id.strip() or not anime_episode.strip():
            raise HTTPException(status_code=HTTP_400_BAD_REQUEST, detail="Choose an anime, a season and an episode first.")
        kind, tab = "anime", ("url" if anime_source == "url" else "upload")

    if (todo := requirements.missing("video", source_id=source_id if tab == "streamer" else None, url=url or "" if tab == "url" else "")):
        raise HTTPException(status_code=HTTP_400_BAD_REQUEST, detail="Finish setup first: " + ", ".join(i["title"] for i in todo) + ".")
    if not (target_clips.strip() == "" or target_clips.strip().isdigit()):
        raise HTTPException(status_code=HTTP_400_BAD_REQUEST, detail="Invalid processing option.")
    if kind not in ("stream", "anime"):
        raise HTTPException(status_code=HTTP_400_BAD_REQUEST, detail="Invalid video type.")
    anime = kind == "anime" and tab in ("url", "upload")
    # Anime jobs ignore the stream render presets: the runner applies the anime defaults (letterbox, no added music, no pause cuts)
    settings = parse_presets(layout, captions, music, cut_pauses, letterbox_style, caption_style, ai_cuts) if layout and not anime else {}
    if anime:
        settings["anime"] = build_anime_settings(anime_audio, anime_id, anime_episode, anime_hardsubbed, anime_title_match,
                                                 anime_youtube_url, anime_youtube_offset)
    if target_clips.strip():
        settings["target_clips"] = max(1, min(MAX_TARGET_CLIPS, int(target_clips)))

    if tab == "upload":
        if not file or not file.filename:
            raise HTTPException(status_code=HTTP_400_BAD_REQUEST, detail="No file selected for upload.")

        ext = Path(file.filename).suffix.lower()
        if ext not in ALLOWED_UPLOAD_EXTS:
            raise HTTPException(
                status_code=HTTP_400_BAD_REQUEST,
                detail=f"Unsupported file format '{ext}'. Allowed: {', '.join(sorted(ALLOWED_UPLOAD_EXTS))}"
            )

        dest_name = f"{uuid.uuid4()}{ext}"
        dest_path = UPLOADS_DIR / dest_name

        # Stream write with size limit
        bytes_written = 0
        try:
            with open(dest_path, "wb") as f_out:
                while chunk := await file.read(1024 * 1024):  # 1MB chunks
                    bytes_written += len(chunk)
                    if bytes_written > MAX_UPLOAD_SIZE_BYTES:
                        f_out.close()
                        dest_path.unlink(missing_ok=True)
                        raise HTTPException(
                            status_code=HTTP_400_BAD_REQUEST,
                            detail=f"Uploaded file exceeds maximum size limit of {MAX_UPLOAD_SIZE_BYTES // (1024*1024*1024)} GB."
                        )
                    f_out.write(chunk)
        except Exception as e:
            dest_path.unlink(missing_ok=True)
            if isinstance(e, HTTPException):
                raise
            raise HTTPException(status_code=HTTP_400_BAD_REQUEST, detail=f"File upload failed: {e}")

        # Security check: ffprobe type verification (Blueprint §8)
        if not _verify_video_file(dest_path):
            dest_path.unlink(missing_ok=True)
            raise HTTPException(
                status_code=HTTP_400_BAD_REQUEST,
                detail="Security check failed: File is not a valid video or audio format."
            )

        video_id = register_video(
            origin="upload",
            url_or_path=str(dest_path),
            external_id=dest_name,
            title=label or file.filename,
            submitted_by=user.get("id"),
            priority=10,  # Manual submissions beat watcher jobs
            settings=settings,
        )
        log_event("info", f"User {user['login']} uploaded file '{file.filename}' (Job #{video_id})", video_id=video_id)

    elif tab == "url":
        if not url or not url.strip():
            raise HTTPException(status_code=HTTP_400_BAD_REQUEST, detail="Please enter a valid video URL.")

        raw_url = url.strip()
        parsed = urlparse(raw_url)
        hostname = (parsed.hostname or "").lower()

        # Security check: Domain allowlist (Blueprint §8)
        if not any(hostname == d or hostname.endswith("." + d) for d in ALLOWED_URL_DOMAINS):
            raise HTTPException(
                status_code=HTTP_400_BAD_REQUEST,
                detail=f"URL host '{hostname}' is not supported. Allowed: {', '.join(sorted(ALLOWED_URL_DOMAINS))}"
            )

        video_id = register_video(
            origin="url",
            url_or_path=raw_url,
            title=label or raw_url,
            submitted_by=user.get("id"),
            priority=10,
            settings=settings,
        )
        log_event("info", f"User {user['login']} queued URL '{raw_url}' (Job #{video_id})", video_id=video_id)

    elif tab == "streamer":
        if not source_id:
            raise HTTPException(status_code=HTTP_400_BAD_REQUEST, detail="Please select a streamer source.")

        src = get_source(source_id)
        if not src:
            raise HTTPException(status_code=HTTP_404_NOT_FOUND, detail="Source not found.")

        from starlette.concurrency import run_in_threadpool
        from src.watcher import latest_finished_vod, vod_url_for  # lazy: pulls in yt_dlp

        vod_id, vod_title = None, None
        if vod_url and vod_url.strip():
            target_url = vod_url_for(src["kind"], vod_url)
        else:  # "leave empty to fetch the latest past broadcast"
            item = await run_in_threadpool(latest_finished_vod, src["kind"], src["external_id"])
            if not item:
                raise HTTPException(
                    status_code=HTTP_400_BAD_REQUEST,
                    detail=f"No finished stream found for {src['display_name'] or src['external_id']} yet. Pick a video or paste a link.",
                )
            target_url, vod_id, vod_title = item["url"], item["id"], item.get("title")

        hostname = (urlparse(target_url).hostname or "").lower()
        if not any(hostname == d or hostname.endswith("." + d) for d in ALLOWED_URL_DOMAINS):
            raise HTTPException(
                status_code=HTTP_400_BAD_REQUEST,
                detail=f"URL host '{hostname}' is not supported. Allowed: {', '.join(sorted(ALLOWED_URL_DOMAINS))}"
            )
        video_id = register_video(
            origin="streamer",
            url_or_path=target_url,
            external_id=vod_id,
            source_id=source_id,
            title=vod_title or target_url,
            submitted_by=user.get("id"),
            priority=10,
            settings=settings,
        )
        log_event("info", f"User {user['login']} queued streamer source #{source_id} (Job #{video_id})", video_id=video_id)

    else:
        raise HTTPException(status_code=HTTP_400_BAD_REQUEST, detail="Invalid submission tab.")

    response = RedirectResponse(url="/jobs", status_code=HTTP_303_SEE_OTHER)
    return response
