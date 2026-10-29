"""
Spike: Review routes.
Blueprint §10.1 & DESIGN.md §10.1.
"""

import json
from typing import Optional, Dict, Any, List
from fastapi import APIRouter, Request, Depends, HTTPException
from fastapi.responses import HTMLResponse, RedirectResponse
from starlette.status import HTTP_303_SEE_OTHER, HTTP_404_NOT_FOUND

from src.concepts import CONCEPT_LABELS, CONCEPTS
from src.pov import load_bank
from src.db import (
    enqueue_candidate_render,
    get_candidate,
    get_clip_with_details,
    get_job,
    list_clip_ai_edits,
    list_other_moments,
    list_review_clips,
    list_sources,
)
from src.config import VIDEOS_DIR
from src.profile import streamer_name
from src.web.auth import get_current_user


router = APIRouter()


def _review_signature(source_id: Optional[int]) -> str:
    """Changes whenever a clip enters/leaves the review queue or is re-rendered (version bump)."""
    return ",".join(f"{c['id']}:{c['version']}" for c in list_review_clips(source_id=source_id, status="ready"))


def _real_title_and_streamer(video: Dict[str, Any]) -> None:
    """URL jobs store the pasted link as the title; swap in the stream's title and streamer from meta.json."""
    try:
        meta = json.loads((VIDEOS_DIR / str(video["id"]) / "meta.json").read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return
    if (video.get("title") or "").startswith(("http://", "https://")) and meta.get("title"):
        video["title"] = meta["title"]
    if not video.get("source_name"):
        video["source_name"] = streamer_name(None, meta)


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
                    "url": c["video_url"],
                },
                "clips": [],
            }
        job_groups[vid]["clips"].append(dict(c))

    # Candidates the pipeline found but did not pick (low_score, rejected), each renderable on demand.
    # A finished video with such moments but no clip waiting for review still gets a group.
    moments = list_other_moments(None)
    for vid in moments:
        if vid in job_groups:
            continue
        job = get_job(vid)
        if job and job["status"] == "ready" and (not source_id or job["source_id"] == source_id):
            job_groups[vid] = {
                "video": {"id": vid, "title": job["title"], "source_name": job["source_name"],
                          "created_at": job["created_at"], "url": job["url"], "duration_s": job["duration_s"]},
                "clips": [],
            }
    for vid, group in job_groups.items():
        group["moments"] = moments.get(vid, [])
        _real_title_and_streamer(group["video"])

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


@router.post("/candidates/{candidate_id}/render")
async def render_moment_action(
    candidate_id: int,
    request: Request,
    user: Dict[str, Any] = Depends(get_current_user),
):
    """Queue a worker job that fetches the section and renders this moment. Nothing renders in the request."""
    enqueue_candidate_render(candidate_id, user.get("id"))
    return RedirectResponse(url=request.headers.get("referer") or "/", status_code=HTTP_303_SEE_OTHER)


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
    from src.sfx import clean_sfx, list_sounds
    music_tracks = list_all_tracks()
    caption = clip.get("cand_caption") or clip.get("cand_title") or ""
    credit = music_credit(clip.get("music_track"))

    # Pause cuts in the current render, so the page can map player time <-> source time for layout switches
    from src.config import SILENCE_TRIM_S, VIDEOS_DIR
    from src.pipeline.stage9c_render import find_silence_cut_intervals
    from src.web.routes.clips import _load_words
    from src.pipeline.stage9c_render import default_zooms, merge_cut_intervals
    clip_start = clip.get("trim_start_s") or clip.get("orig_start_s") or 0
    clip_end = clip.get("trim_end_s") or clip.get("orig_end_s") or 0
    words = _load_words(VIDEOS_DIR / str(clip["video_id"]), clip["candidate_id"])
    # What pause trim cuts at this clip's setting, on or off: the cut list tells a stored pause cut from a manual one
    pause_all = find_silence_cut_intervals(words, clip_start, clip_end, clip.get("silence_trim_s") or SILENCE_TRIM_S)
    silence_cuts = pause_all if clip.get("silence_trim") == 1 else []
    stored_cuts = json.loads(clip.get("cuts") or "[]")
    cand = get_candidate(clip["candidate_id"])
    ai_cuts = json.loads(cand["cuts"] or "[]") if cand else []  # the AI editor's picks; a stored cut that matches one is the AI's
    # Everything cut out of the video being played now: the page maps player time to source time through these
    cuts = merge_cut_intervals(silence_cuts, stored_cuts, clip_start=clip_start, clip_end=clip_end)
    sec_file = VIDEOS_DIR / str(clip["video_id"]) / "sections" / f"section_{clip['candidate_id']}.mp4"
    zooms = json.loads(clip["zooms"]) if clip.get("zooms") is not None else default_zooms(sec_file, clip_start, clip_end, clip.get("payoff_t"))
    layout_changes = json.loads(clip.get("layout_changes") or "[]")
    # A single clip is one segment: switching it to a story or countdown starts from that segment
    concept = clip.get("concept") or "single"
    c_segments = json.loads(clip.get("segments") or "[]") if concept != "single" else [{
        "candidate_id": clip["candidate_id"], "start_s": clip_start, "end_s": clip_end, "remove": stored_cuts, "rank": None, "label": ""}]

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
            "sfx_sounds": list_sounds(),
            "sfx": clean_sfx(clip.get("sfx"), clip_start, clip_end),
            "copy_caption": f"{caption}\n\n{credit}" if credit else caption,
            "layout_changes": layout_changes,
            "cut_intervals": cuts,
            "manual_cuts": stored_cuts,
            "pause_cuts": silence_cuts,
            "pause_all": pause_all,
            "ai_cuts": ai_cuts,
            "silence_trim_s": clip.get("silence_trim_s") or SILENCE_TRIM_S,
            "zooms": zooms,
            "ai_edits": list_clip_ai_edits(clip_id),
            "concept": concept,
            "c_segments": c_segments,
            "overlay": json.loads(clip.get("overlay") or "{}"),
            "pov_bank": load_bank(),
            "concepts": [(c, CONCEPT_LABELS[c]) for c in CONCEPTS],
            "prev_clip_id": prev_id,
            "next_clip_id": next_id,
            "review_count": len(all_clips),
            "post": _approve_dialog_context(clip_id, clip),
        },
    )


def _approve_dialog_context(clip_id: int, clip: Dict[str, Any]) -> Dict[str, Any]:
    """What the Approve dialog needs: each platform with its accounts, or why it cannot be posted to yet."""
    from src.db import list_accounts
    from src.platform_auth import connect_options
    from src.posting import PermissionBlockedError, get_next_schedule_slot, parse_tags, verify_clip_posting_permission
    try:
        verify_clip_posting_permission(clip_id)
        blocked = ""
    except PermissionBlockedError as e:
        blocked = str(e)
    accounts = list_accounts(decrypt=False)
    return {
        "blocked": blocked,
        "platforms": [{**p, "accounts": [a for a in accounts if a["platform"] == p["key"]]} for p in connect_options()],
        "tags": " ".join(f"#{t}" for t in parse_tags(clip.get("cand_hashtags"))),
        "next_slot": get_next_schedule_slot().strftime("%Y-%m-%dT%H:%M"),
    }
