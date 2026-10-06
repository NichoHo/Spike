"""
Spike: New job submission routes.
Blueprint §10.4, §8 (Security T2: upload verification & URL whitelist).
"""

import os
import uuid
import subprocess
from urllib.parse import urlparse
from pathlib import Path
from typing import Optional, Dict, Any

from fastapi import APIRouter, Request, Depends, Form, UploadFile, File, HTTPException
from fastapi.responses import HTMLResponse, RedirectResponse
from starlette.status import HTTP_400_BAD_REQUEST, HTTP_303_SEE_OTHER

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
    tab: str = "upload",
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


@router.post("/new/submit")
async def submit_new_job(
    request: Request,
    tab: str = Form("upload"),
    url: Optional[str] = Form(None),
    source_id: Optional[int] = Form(None),
    vod_url: Optional[str] = Form(None),
    target_clips: int = Form(3),
    layout: str = Form("auto"),
    captions: str = Form("on"),
    music: str = Form("auto"),
    cut_pauses: str = Form("auto"),
    file: Optional[UploadFile] = File(None),
    user: Dict[str, Any] = Depends(get_current_user),
):
    UPLOADS_DIR.mkdir(parents=True, exist_ok=True)

    if (
        layout not in VALID_LAYOUTS
        or captions not in ("on", "off")
        or music not in ("auto", "on", "off")
        or cut_pauses not in ("auto", "tight", "natural", "off")
    ):
        raise HTTPException(status_code=HTTP_400_BAD_REQUEST, detail="Invalid processing option.")
    settings = {
        "target_clips": max(1, min(MAX_TARGET_CLIPS, target_clips)),
        "layout": layout,
        "captions": captions == "on",
        "music": "auto" if music == "auto" else music == "on",
        "cut_pauses": cut_pauses,
    }

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

        target_url = vod_url.strip() if vod_url and vod_url.strip() else f"streamer:{source_id}"
        video_id = register_video(
            origin="streamer",
            url_or_path=target_url,
            source_id=source_id,
            title=target_url,
            submitted_by=user.get("id"),
            priority=10,
            settings=settings,
        )
        log_event("info", f"User {user['login']} queued streamer source #{source_id} (Job #{video_id})", video_id=video_id)

    else:
        raise HTTPException(status_code=HTTP_400_BAD_REQUEST, detail="Invalid submission tab.")

    response = RedirectResponse(url="/jobs", status_code=HTTP_303_SEE_OTHER)
    return response
