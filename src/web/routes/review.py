"""
Spike: Review routes.
Blueprint §10.1 & DESIGN.md §10.1.
"""

import json
from typing import Optional, Dict, Any, List
from fastapi import APIRouter, Request, Depends, HTTPException
from fastapi.responses import HTMLResponse
from starlette.status import HTTP_404_NOT_FOUND

from src.db import (
    list_review_clips,
    get_clip_with_details,
    list_sources,
)
from src.web.auth import get_current_user


router = APIRouter()


def _review_signature(source_id: Optional[int]) -> str:
    """Changes whenever a clip enters/leaves the review queue or is re-rendered (version bump)."""
    return ",".join(f"{c['id']}:{c['version']}" for c in list_review_clips(source_id=source_id, status="ready"))


@router.get("/api/review-signature")
async def review_signature(source_id: Optional[int] = None, user: Dict[str, Any] = Depends(get_current_user)):
    return {"sig": _review_signature(source_id)}


@router.get("/", response_class=HTMLResponse)
async def review_home(
    request: Request,
    source_id: Optional[int] = None,
    user: Dict[str, Any] = Depends(get_current_user),
):
    templates = request.app.state.templates
    sources = [dict(s) for s in list_sources()]
    clips_raw = list_review_clips(source_id=source_id, status="ready")

    # Group clips by video job
    job_groups: Dict[int, Dict[str, Any]] = {}
    for c in clips_raw:
        vid = c["video_id"]
        if vid not in job_groups:
            job_groups[vid] = {
                "video": {
                    "id": vid,
                    "title": c["video_title"],
                    "source_name": c["source_name"],
                    "created_at": c["video_created_at"],
                },
                "clips": [],
            }
        job_groups[vid]["clips"].append(dict(c))

    # Review count across all ready clips
    all_ready = list_review_clips(status="ready")

    return templates.TemplateResponse(
        request=request,
        name="pages/review.html",
        context={
            "page_title": "Review",
            "active_nav": "review",
            "page_width": "wide",
            "user": user,
            "sources": sources,
            "selected_source_id": source_id,
            "job_groups": list(job_groups.values()),
            "total_clips": len(clips_raw),
            "review_count": len(all_ready),
            "review_sig": _review_signature(source_id),
        },
    )


@router.get("/clips/{clip_id}", response_class=HTMLResponse)
async def clip_detail(
    request: Request,
    clip_id: int,
    user: Dict[str, Any] = Depends(get_current_user),
):
    templates = request.app.state.templates
    clip_row = get_clip_with_details(clip_id)
    if not clip_row:
        raise HTTPException(status_code=HTTP_404_NOT_FOUND, detail="Clip not found.")

    clip = dict(clip_row)

    # Find prev and next clip IDs in current ready queue
    all_clips = list_review_clips(status="ready")
    clip_ids = [c["id"] for c in all_clips]

    prev_id = None
    next_id = None
    if clip_id in clip_ids:
        idx = clip_ids.index(clip_id)
        if idx > 0:
            prev_id = clip_ids[idx - 1]
        if idx < len(clip_ids) - 1:
            next_id = clip_ids[idx + 1]

    from src.music import list_all_tracks, music_credit
    music_tracks = list_all_tracks()
    caption = clip.get("cand_caption") or clip.get("cand_title") or ""
    credit = music_credit(clip.get("music_track"))

    # Pause cuts in the current render, so the page can map player time <-> source time
    # for layout switches. ponytail: assumes "natural" pacing; a first render made with
    # "tight" maps a little off until it is re-rendered from this page.
    from src.config import VIDEOS_DIR
    from src.pipeline.stage9c_render import find_silence_cut_intervals
    from src.web.routes.clips import _load_words
    clip_start = clip.get("trim_start_s") or clip.get("orig_start_s") or 0
    clip_end = clip.get("trim_end_s") or clip.get("orig_end_s") or 0
    cuts = []
    if clip.get("silence_trim") == 1:
        words = _load_words(VIDEOS_DIR / str(clip["video_id"]), clip["candidate_id"])
        cuts = find_silence_cut_intervals(words, clip_start, clip_end)
    layout_changes = json.loads(clip.get("layout_changes") or "[]")

    return templates.TemplateResponse(
        request=request,
        name="pages/clip_detail.html",
        context={
            "page_title": clip.get("cand_title") or "Clip Detail",
            "active_nav": "review",
            "page_width": "default",
            "user": user,
            "clip": clip,
            "music_tracks": music_tracks,
            "copy_caption": f"{caption}\n\n{credit}" if credit else caption,
            "layout_changes": layout_changes,
            "cut_intervals": cuts,
            "prev_clip_id": prev_id,
            "next_clip_id": next_id,
            "review_count": len(all_clips),
        },
    )
