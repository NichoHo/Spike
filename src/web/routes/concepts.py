"""
Spike: concept routes (story, POV, Top 3 / Top 5): the moment picker, switching a clip to a concept, POV captions.
Rendering never happens in a request: building a concept queues a worker job (the same queue as "Other moments").
"""

import json
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import JSONResponse
from pydantic import BaseModel
from starlette.status import HTTP_404_NOT_FOUND

from src.concept_build import build_concept, pov_captions_for, pov_from_range
from src.concepts import CONCEPTS, count_problem
from src.db import (
    enqueue_candidate_render,
    get_clip_with_details,
    get_connection,
    get_job,
    insert_candidate,
    set_candidate_concept,
    set_clip_overlay,
    set_clip_render_state,
)
from src.web.auth import get_current_user
from src.web.filters import filter_stream_link, filter_stream_time

router = APIRouter()


@router.get("/videos/{video_id}/moments")
async def list_moments(video_id: int, user: Dict[str, Any] = Depends(get_current_user)):
    """Every stored candidate of the video for the moment picker. Concept outputs are left out: they are made of
    these moments, not moments themselves."""
    job = get_job(video_id)
    if not job:
        raise HTTPException(status_code=HTTP_404_NOT_FOUND, detail="Video not found.")
    with get_connection() as conn:
        rows = conn.execute(
            "SELECT id, title, start_s, end_s, llm_score, humor_type, status FROM candidates "
            "WHERE video_id = ? AND COALESCE(concept, 'single') = 'single' ORDER BY start_s", (video_id,)).fetchall()
    return {"moments": [
        {"id": r["id"], "title": r["title"] or "Untitled moment", "start_s": r["start_s"], "time": filter_stream_time(r["start_s"]),
         "link": filter_stream_link(job["url"], r["start_s"]), "score": r["llm_score"], "humor": r["humor_type"] or "", "status": r["status"]}
        for r in rows]}


class BuildIn(BaseModel):
    concept: str
    candidate_ids: List[int]
    clip_id: Optional[int] = None


def _existing_spec(clip: Dict[str, Any]) -> Dict[str, Any]:
    """What a clip already says, so a swap keeps its title, theme, labels and caption."""
    segs = json.loads(clip.get("segments") or "[]")
    return {
        "concept": clip.get("concept") or "single", "title": clip.get("cand_title") or "", "hook_text": clip.get("cand_hook") or "",
        "theme": clip.get("theme") or "", "overlay": json.loads(clip.get("overlay") or "{}"),
        "labels": {s.get("candidate_id"): s.get("label", "") for s in segs}, "candidate_ids": [s.get("candidate_id") for s in segs],
    }


@router.post("/videos/{video_id}/concept")
def build_from_moments(video_id: int, body: BuildIn, user: Dict[str, Any] = Depends(get_current_user)):
    """Moment picker: build a concept from the ticked moments (the user's order is kept; the model fills in only the
    missing text) and queue the render as a worker job. With clip_id the clip is re-made, otherwise a new clip is."""
    if body.concept not in CONCEPTS:
        return JSONResponse({"error": "Unknown concept."}, status_code=400)
    problem = count_problem(body.concept, len(body.candidate_ids))
    if problem:
        return JSONResponse({"error": problem}, status_code=400)
    clip = None
    if body.clip_id:
        row = get_clip_with_details(body.clip_id)
        if not row or row["video_id"] != video_id:
            raise HTTPException(status_code=HTTP_404_NOT_FOUND, detail="Clip not found.")
        clip = dict(row)
        if clip["status"] == "rendering":
            return JSONResponse({"error": "This clip is rendering. Try again when it is done."}, status_code=409)
    try:
        spec = build_concept(video_id, body.concept, body.candidate_ids, _existing_spec(clip) if clip else None)
    except ValueError as e:
        return JSONResponse({"error": str(e)}, status_code=400)
    stored = {"segments": spec["segments"], "overlay": spec["overlay"], "theme": spec["theme"], "concept_source": "user"}
    if clip:
        cand_id = clip["candidate_id"]
        set_candidate_concept(cand_id, body.concept, stored, spec["title"] or None, spec["hook_text"] or None)
        set_clip_render_state(clip["id"], "rendering")
    else:
        segs = spec["segments"]
        cand_id = insert_candidate(video_id, {
            "origin": "concept", "status": "selected", "title": spec["title"], "hook_text": spec["hook_text"], "concept": body.concept,
            "concept_spec": stored, "start_s": min(s["start_s"] for s in segs), "end_s": max(s["end_s"] for s in segs),
            "segments": [[s["start_s"], s["end_s"]] for s in segs], "llm_score": 0, "final_score": 0,
        })
    enqueue_candidate_render(cand_id, user.get("id"))
    return {"ok": True, "candidate_id": cand_id, "clip_id": body.clip_id, "warnings": spec["warnings"]}


def _clip_or_404(clip_id: int) -> Dict[str, Any]:
    row = get_clip_with_details(clip_id)
    if not row:
        raise HTTPException(status_code=HTTP_404_NOT_FOUND, detail="Clip not found.")
    return dict(row)


@router.post("/clips/{clip_id}/concept/to-pov")
def switch_to_pov(clip_id: int, user: Dict[str, Any] = Depends(get_current_user)):
    """Switching a clip to POV: find the reaction peak inside the current clip, then write captions. Returns the
    spec for the page to fill in; nothing is saved or rendered until the user re-renders."""
    clip = _clip_or_404(clip_id)
    if (clip.get("concept") or "single") == "single":
        start, end = clip.get("trim_start_s") or clip["orig_start_s"], clip.get("trim_end_s") or clip["orig_end_s"]
    else:  # from a concept clip: use the part of the stream its last segment covers
        segs = json.loads(clip.get("segments") or "[]")
        if not segs:
            return JSONResponse({"error": "This clip has no segments to take a reaction from."}, status_code=400)
        start, end = segs[-1]["start_s"], segs[-1]["end_s"]
    try:
        return pov_from_range(clip["video_id"], clip["candidate_id"], start, end, clip.get("cand_title") or "", clip.get("cand_hook") or "")
    except ValueError as e:
        return JSONResponse({"error": str(e)}, status_code=400)


class CaptionIn(BaseModel):
    start_s: Optional[float] = None
    end_s: Optional[float] = None
    hint: str = ""


@router.post("/clips/{clip_id}/pov/captions")
def new_pov_captions(clip_id: int, body: CaptionIn, user: Dict[str, Any] = Depends(get_current_user)):
    """The "New captions" button: rerun the caption call for the clip's reaction. Saved on the clip at once, so the
    chips are still there after a reload."""
    clip = _clip_or_404(clip_id)
    segs = json.loads(clip.get("segments") or "[]")
    a = body.start_s if body.start_s is not None else (segs[0]["start_s"] if segs else None)
    b = body.end_s if body.end_s is not None else (segs[0]["end_s"] if segs else None)
    if a is None or b is None:
        return JSONResponse({"error": "This clip is not a POV."}, status_code=400)
    try:
        cap = pov_captions_for(clip["video_id"], a, b, clip.get("cand_title") or "", clip.get("cand_hook") or "", body.hint[:200])
    except Exception as e:
        return JSONResponse({"error": f"No captions: {str(e)[:200]}"}, status_code=502)
    overlay = json.loads(clip.get("overlay") or "{}")
    overlay.update(emotion=cap["emotion"], pov_options=cap["options"], pov_text=cap["text"])
    set_clip_overlay(clip_id, overlay)
    return {"emotion": cap["emotion"], "options": cap["options"], "text": cap["text"]}
