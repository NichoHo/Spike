"""
Spike: Jobs monitoring and control routes.
Blueprint §10.4, §10.7 & DESIGN.md §10.7.
"""

import shutil
from typing import Dict, Any
from fastapi import APIRouter, Request, Depends, HTTPException
from fastapi.responses import HTMLResponse, RedirectResponse
from starlette.status import HTTP_303_SEE_OTHER

from src.config import CLAUDE_5H_TOKEN_CAP, CLAUDE_WEEK_TOKEN_CAP, DATA_DIR, VIDEOS_DIR
from src.db import (
    claude_usage_summary,
    list_jobs,
    continue_job,
    restart_job,
    cancel_job,
    list_review_clips,
    estimate_remaining_seconds,
)
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
    for j in jobs:
        j["eta_s"] = eta.get(j["id"])
    return jobs


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


@router.post("/jobs/{job_id}/cancel")
async def cancel_job_action(
    job_id: int,
    user: Dict[str, Any] = Depends(get_current_user),
):
    cancel_job(job_id)
    return RedirectResponse(url="/jobs", status_code=HTTP_303_SEE_OTHER)
