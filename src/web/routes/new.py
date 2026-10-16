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
            "active_tab": tab,
            "review_count": review_count,
        },
    )


_VOD_TTL = 300
_vod_cache: Dict[int, tuple] = {}


@router.get("/new/vods")
def recent_vods(
    source_id: int,
    user: Dict[str, Any] = Depends(get_current_user),
):
    """Recent videos for a source, used to autofill the VOD field."""
    src = get_source(source_id)
    if not src:
        raise HTTPException(status_code=HTTP_404_NOT_FOUND, detail="Source not found.")

    hit = _vod_cache.get(source_id)
    if hit and hit[0] > time.time():
        return {"results": hit[1]}

    from src.watcher import fetch_youtube_channel_rss, fetch_twitch_latest_vods  # lazy: pulls in yt_dlp

    fetch = fetch_youtube_channel_rss if src["kind"] == "youtube" else fetch_twitch_latest_vods
    results = fetch(src["external_id"])[:10]
    if results:  # don't cache a failed/empty fetch
        _vod_cache[source_id] = (time.time() + _VOD_TTL, results)
    return {"results": results}


@router.post("/new/submit")
async def submit_new_job(
    request: Request,
    tab: str = Form("upload"),
    url: Optional[str] = Form(None),
    source_id: Optional[int] = Form(None),
    vod_url: Optional[str] = Form(None),
    target_clips: str = Form(""),  # blank = auto (stage 6 scales it with video length)
    layout: str = Form("auto"),
    captions: str = Form("on"),
    music: str = Form("auto"),
    cut_pauses: str = Form("auto"),
    letterbox_style: str = Form("blur"),  # the toggle sends "title" when on
    file: Optional[UploadFile] = File(None),
    user: Dict[str, Any] = Depends(get_current_user),
):
    UPLOADS_DIR.mkdir(parents=True, exist_ok=True)

    if (
        not (target_clips.strip() == "" or target_clips.strip().isdigit())
        or layout not in VALID_LAYOUTS
        or captions not in ("on", "off")
        or music not in ("auto", "on", "off")
        or cut_pauses not in ("auto", "tight", "natural", "off")
        or letterbox_style not in ("title", "blur")
    ):
        raise HTTPException(status_code=HTTP_400_BAD_REQUEST, detail="Invalid processing option.")
    settings = {
        "layout": layout,
        "captions": captions == "on",
        "music": "auto" if music == "auto" else music == "on",
        "cut_pauses": cut_pauses,
        "letterbox_style": letterbox_style,
    }
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
            title=file.filename,
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
            title=raw_url,
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
