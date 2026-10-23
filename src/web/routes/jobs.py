"""
Spike: Jobs monitoring and control routes.
Blueprint §10.4, §10.7 & DESIGN.md §10.7.
"""

import shutil
from datetime import datetime, timedelta
from typing import Dict, Any
from fastapi import APIRouter, Request, Depends, HTTPException
from fastapi.responses import HTMLResponse, JSONResponse, RedirectResponse
from starlette.status import HTTP_303_SEE_OTHER

from src.config import CLAUDE_5H_TOKEN_CAP, CLAUDE_WEEK_TOKEN_CAP, DATA_DIR, VIDEOS_DIR, PUBLIC_URL
from src.db import (
    claude_usage_summary,
    list_jobs,
    continue_job,
    restart_job,
    cancel_job,
    list_review_clips,
    estimate_remaining_seconds,
    log_event,
    reorder_queue,
)
from src import oversize_gate
from src.web.auth import get_current_user


router = APIRouter()


def _get_disk_stats():
    """Retrieve system disk usage for data directory."""
    total, used, free = shutil.disk_usage(DATA_DIR)
    pct = int(round((used / total) * 100))
    used_gb = used / (1024 * 1024 * 1024)
    total_gb = total / (1024 * 1024 * 1024)
    if total_gb >= 1000:
        total_str = f"{total_gb / 1024:.1f} TB"
    else:
        total_str = f"{int(total_gb)} GB"
    used_str = f"{used_gb:.1f} GB" if used_gb < 1000 else f"{used_gb / 1024:.2f} TB"
    return used_str, total_str, pct


def _with_eta(jobs):
    eta = estimate_remaining_seconds(jobs)
    now = datetime.now().astimezone()
    for j in jobs:
        j["eta_s"] = eta.get(j["id"])
        if j["eta_s"] is not None:
            done = now + timedelta(seconds=j["eta_s"])
            j["eta_at"] = done.strftime("%H:%M" if done.date() == now.date() else "%a %H:%M")
    return jobs


def _gate_ctx():
    """The oversized-input gate waiting for an answer, with its rendered message, or None."""
    req = oversize_gate.pending()
    if not req:
        return None
    return {
        "id": req["id"],
        "video_id": req["video_id"],
        "title": req.get("title") or f"Video #{req['video_id']}",
        "level": req.get("level", 1),
        "message": oversize_gate.build_message(
            req["video_id"], req.get("title") or f"Video #{req['video_id']}",
            float(req.get("duration_s") or 0.0), req.get("level", 1), PUBLIC_URL,
        ),
    }


@router.get("/jobs", response_class=HTMLResponse)
async def jobs_page(
    request: Request,
    user: Dict[str, Any] = Depends(get_current_user),
):
    templates = request.app.state.templates
    jobs = _with_eta([dict(j) for j in list_jobs()])
    review_count = len(list_review_clips(status="ready"))
    used_str, total_str, pct = _get_disk_stats()

    return templates.TemplateResponse(
        request=request,
        name="pages/jobs.html",
        context={
            "page_title": "Jobs",
            "active_nav": "jobs",
            "page_width": "wide",
            "user": user,
            "jobs": jobs,
            "disk_used_str": used_str,
            "disk_total_str": total_str,
            "disk_pct": pct,
            "claude": claude_usage_summary(),
            "claude_5h_cap": CLAUDE_5H_TOKEN_CAP,
            "claude_week_cap": CLAUDE_WEEK_TOKEN_CAP,
            "review_count": review_count,
            "gate": _gate_ctx(),
        },
    )


@router.get("/jobs/table", response_class=HTMLResponse)
async def jobs_table_partial(
    request: Request,
    user: Dict[str, Any] = Depends(get_current_user),
):
    """HTMX polling endpoint for table auto-refresh every 5s."""
    templates = request.app.state.templates
    jobs = _with_eta([dict(j) for j in list_jobs()])
    return templates.TemplateResponse(
        request=request,
        name="pages/jobs_table.html",
        context={
            "jobs": jobs,
            "user": user,
            "gate": _gate_ctx(),
        },
    )


@router.post("/jobs/{job_id}/continue")
async def continue_job_action(
    job_id: int,
    user: Dict[str, Any] = Depends(get_current_user),
):
    """Pick the failed job up where it stopped: finished stages are skipped."""
    continue_job(job_id)
    return RedirectResponse(url="/jobs", status_code=HTTP_303_SEE_OTHER)


@router.post("/jobs/{job_id}/retry")
async def retry_job_action(
    job_id: int,
    user: Dict[str, Any] = Depends(get_current_user),
):
    """Run the failed job again from the start: its saved files and results are deleted first."""
    if restart_job(job_id):
        shutil.rmtree(VIDEOS_DIR / str(job_id), ignore_errors=True)
    return RedirectResponse(url="/jobs", status_code=HTTP_303_SEE_OTHER)


@router.post("/jobs/reorder")
async def reorder_jobs_action(
    request: Request,
    user: Dict[str, Any] = Depends(get_current_user),
):
    """Set the queue order. Body: {"order": [job ids, first runs first], "confirm_pause": bool}.
    409 with needs_confirm when the running job would lose first place and the pause was not confirmed."""
    try:
        body = await request.json()
        order = [int(i) for i in body.get("order", [])]
    except (ValueError, TypeError, AttributeError):
        raise HTTPException(status_code=400, detail="order must be a list of job ids")
    result = reorder_queue(order, allow_pause=bool(body.get("confirm_pause")))
    if "needs_confirm" in result:
        return JSONResponse(result, status_code=409)
    who = user.get("login", "someone")
    paused = result["paused"]
    log_event("info", f"Queue reordered by {who}" + (f"; job #{paused} paused" if paused else ""), video_id=paused)
    return JSONResponse(result)


@router.post("/jobs/{job_id}/cancel")
async def cancel_job_action(
    job_id: int,
    user: Dict[str, Any] = Depends(get_current_user),
):
    cancel_job(job_id)
    return RedirectResponse(url="/jobs", status_code=HTTP_303_SEE_OTHER)


@router.post("/jobs/gate/answer")
async def gate_answer_action(
    request: Request,
    user: Dict[str, Any] = Depends(get_current_user),
):
    """Answer the oversized-input gate: Continue (decision=continue) lets the pipeline into the moments stage,
    Stop (decision=stop) stops the job. The waiting worker/pipeline process reads the answer from settings."""
    form = await request.form()
    req_id = str(form.get("req_id", ""))
    decision = str(form.get("decision", ""))
    if decision in ("continue", "stop"):
        oversize_gate.answer(req_id, approve=(decision == "continue"))
    return RedirectResponse(url="/jobs", status_code=HTTP_303_SEE_OTHER)
