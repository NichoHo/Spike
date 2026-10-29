"""
Spike: Platform Posting and Scheduling Routes.
Blueprint §8, §9, §10.8 & DESIGN.md §10.8 (Phase 6).
"""

import json
from datetime import datetime, timezone
from typing import Optional, Dict, Any, List

from fastapi import APIRouter, BackgroundTasks, Request, Depends, Form, HTTPException
from fastapi.responses import HTMLResponse, JSONResponse, RedirectResponse
from starlette.status import HTTP_404_NOT_FOUND, HTTP_403_FORBIDDEN, HTTP_303_SEE_OTHER

from src.db import (
    get_clip_with_details,
    list_posts,
    get_post,
    create_post,
    update_post_status,
    update_clip_status,
    list_accounts,
    get_account,
    log_event,
    now_utc_iso,
)
from src.posting import (
    verify_clip_posting_permission,
    dispatch_post,
    get_next_schedule_slot,
    parse_tags,
    failure_hint,
    PermissionBlockedError,
)
from src.music import music_credit
from src.web.auth import get_current_user


router = APIRouter()


@router.get("/posts", response_class=HTMLResponse)
async def posts_page(
    request: Request,
    tab: str = "scheduled",
    watch: str = "",
    done: int = 0,
    failed: int = 0,
    user: Dict[str, Any] = Depends(get_current_user),
):
    templates = request.app.state.templates
    all_posts_raw = list_posts()
    all_posts = [dict(p) for p in all_posts_raw]
    for p in all_posts:
        if p["status"] == "failed":
            p["hint"], p["hint_href"] = failure_hint(p.get("error"))

    scheduled_posts = [p for p in all_posts if p["status"] in ("scheduled", "uploading")]
    posted_posts = [p for p in all_posts if p["status"] in ("posted", "sent_to_inbox")]
    failed_posts = [p for p in all_posts if p["status"] == "failed"]

    tab = tab.lower()
    if tab == "posted":
        display_posts = posted_posts
    elif tab == "failed":
        display_posts = failed_posts
    else:
        tab = "scheduled"
        display_posts = scheduled_posts

    return templates.TemplateResponse(
        request=request,
        name="pages/posts.html",
        context={
            "page_title": "Posts",
            "active_nav": "posts",
            "page_width": "wide",
            "user": user,
            "tab": tab,
            "posts": display_posts,
            "scheduled_count": len(scheduled_posts),
            "posted_count": len(posted_posts),
            "failed_count": len(failed_posts),
            "watch": watch,
            "done": done,
            "failed": failed,
            "next_slot": get_next_schedule_slot().strftime("%Y-%m-%dT%H:%M"),
        },
    )


@router.get("/clips/{clip_id}/post", response_class=HTMLResponse)
async def post_clip_page(
    request: Request,
    clip_id: int,
    user: Dict[str, Any] = Depends(get_current_user),
):
    templates = request.app.state.templates
    clip_row = get_clip_with_details(clip_id)
    if not clip_row:
        raise HTTPException(status_code=HTTP_404_NOT_FOUND, detail="Clip not found.")

    clip = dict(clip_row)
    source_perm = (clip.get("source_permission") or "none").strip().lower()
    blocked = (source_perm == "none")

    accounts = list_accounts(decrypt=False)
    next_slot = get_next_schedule_slot()

    # Pre-populate suggested caption and hashtags
    caption = clip.get("cand_caption") or clip.get("cand_title") or ""
    credit = music_credit(clip.get("music_track"))
    if credit:
        caption = f"{caption}\n\n{credit}"  # CC BY music credit; keep it when editing
    tags = parse_tags(clip.get("cand_hashtags"))

    return templates.TemplateResponse(
        request=request,
        name="pages/post_clip.html",
        context={
            "page_title": f"Post: {clip.get('cand_title', 'Clip')}",
            "active_nav": "posts",
            "page_width": "narrow",
            "user": user,
            "clip": clip,
            "blocked": blocked,
            "accounts": accounts,
            "next_slot": next_slot.strftime("%Y-%m-%d %H:%M"),
            "prefilled_caption": caption,
            "prefilled_tags": " ".join(f"#{t}" for t in tags),
        },
    )


def _dispatch_all(post_ids: List[int]) -> None:
    """Upload one post after another; each failure is saved on its own post row."""
    for post_id in post_ids:
        try:
            dispatch_post(post_id)
        except Exception:
            pass


@router.post("/clips/{clip_id}/post")
async def post_clip_action(
    clip_id: int,
    background_tasks: BackgroundTasks,
    account_ids: List[int] = Form(...),
    timing: str = Form("now"),
    scheduled_for: Optional[str] = Form(None),
    caption: str = Form(""),
    hashtags: Optional[str] = Form(""),
    approve: bool = Form(False),
    user: Dict[str, Any] = Depends(get_current_user),
):
    # Blueprint §12: Strictly check permission in code
    try:
        verify_clip_posting_permission(clip_id)
    except PermissionBlockedError as e:
        raise HTTPException(status_code=HTTP_403_FORBIDDEN, detail=str(e))

    account_ids = list(dict.fromkeys(account_ids))
    if any(not get_account(a, decrypt=False) for a in account_ids):
        raise HTTPException(status_code=HTTP_404_NOT_FOUND, detail="Platform account not found.")

    clean_caption = caption.strip()
    tag_list = [t.strip().lstrip("#") for t in (hashtags or "").split() if t.strip()]
    hashtags_json = json.dumps(tag_list)

    slot_iso = now_utc_iso() if timing == "now" else _slot_iso(scheduled_for)

    post_ids = [
        create_post(
            clip_id=clip_id,
            account_id=account_id,
            status="uploading" if timing == "now" else "scheduled",
            scheduled_for=slot_iso,
            caption=clean_caption,
            hashtags=hashtags_json,
            posted_by=user.get("id"),
        )
        for account_id in account_ids
    ]
    if approve:
        update_clip_status(clip_id, "approved", user_id=user.get("id"))
        log_event("info", f"Clip #{clip_id} approved by {user['login']}")
    if timing == "now":
        return _start_uploads(post_ids, background_tasks)
    log_event("info", f"Clip #{clip_id} scheduled to {len(post_ids)} account(s) at {slot_iso} by {user['login']}")
    return RedirectResponse(url="/posts?tab=scheduled", status_code=HTTP_303_SEE_OTHER)


def _slot_iso(scheduled_for: Optional[str]) -> str:
    """UTC ISO time from the datetime-local picker (the machine's local time); the next default slot when empty or bad."""
    try:
        return datetime.fromisoformat((scheduled_for or "").strip()).astimezone(timezone.utc).isoformat()
    except ValueError:
        return get_next_schedule_slot().astimezone(timezone.utc).isoformat()


def _start_uploads(post_ids: List[int], background_tasks: BackgroundTasks) -> RedirectResponse:
    """Mark posts 'uploading' and upload them after the response. The Posts page shows them as Posting
    and moves on to Posted or Failed once every watched upload has finished."""
    for post_id in post_ids:
        update_post_status(post_id, "uploading")
    # Uploads run after the response, so several accounts (and Instagram's processing wait) never hold the page
    background_tasks.add_task(_dispatch_all, post_ids)
    return RedirectResponse(url="/posts?tab=scheduled&watch=" + ",".join(map(str, post_ids)), status_code=HTTP_303_SEE_OTHER)


@router.get("/api/posts/status")
async def posts_status(ids: str = "", user: Dict[str, Any] = Depends(get_current_user)):
    """Status of each watched post, for the Posts page's Posting poll."""
    out = {}
    for i in ids.split(",")[:200]:
        post = get_post(int(i)) if i.strip().isdigit() else None
        if post:
            out[i.strip()] = post["status"]
    return JSONResponse(out)


@router.post("/posts/bulk")
async def bulk_posts_action(
    background_tasks: BackgroundTasks,
    action: str = Form(...),
    post_ids: List[int] = Form([]),
    scheduled_for: Optional[str] = Form(None),
    user: Dict[str, Any] = Depends(get_current_user),
):
    """Post now / retry, change schedule, or cancel the ticked posts. Only scheduled and failed posts change."""
    posts = [dict(p) for p in (get_post(i) for i in dict.fromkeys(post_ids)) if p and p["status"] in ("scheduled", "failed")]
    back = "/posts?tab=" + ("failed" if posts and all(p["status"] == "failed" for p in posts) else "scheduled")
    if not posts:
        return RedirectResponse(url=back, status_code=HTTP_303_SEE_OTHER)

    if action in ("post_now", "retry"):
        ids = []
        for p in posts:
            try:
                verify_clip_posting_permission(p["clip_id"])
                ids.append(p["id"])
            except PermissionBlockedError as e:
                update_post_status(p["id"], "failed", error=str(e))
        log_event("info", f"{len(ids)} post(s) sent to upload by {user['login']}")
        if not ids:
            return RedirectResponse(url="/posts?tab=failed", status_code=HTTP_303_SEE_OTHER)
        return _start_uploads(ids, background_tasks)

    if action == "reschedule":
        slot_iso = _slot_iso(scheduled_for)
        for p in posts:  # create_post upserts on (clip, account): new time, status scheduled, error cleared
            create_post(clip_id=p["clip_id"], account_id=p["account_id"], status="scheduled", scheduled_for=slot_iso,
                        caption=p["caption"], hashtags=p["hashtags"], posted_by=user.get("id"))
        log_event("info", f"{len(posts)} post(s) rescheduled to {slot_iso} by {user['login']}")
        return RedirectResponse(url="/posts?tab=scheduled", status_code=HTTP_303_SEE_OTHER)

    if action == "cancel":
        for p in posts:
            update_post_status(p["id"], "cancelled", error="Cancelled by user")
        log_event("info", f"{len(posts)} post(s) cancelled by {user['login']}")
        return RedirectResponse(url=back, status_code=HTTP_303_SEE_OTHER)

    raise HTTPException(status_code=400, detail="Unknown action.")


@router.post("/posts/{post_id}/retry")
async def retry_post_action(
    post_id: int,
    background_tasks: BackgroundTasks,
    user: Dict[str, Any] = Depends(get_current_user),
):
    if not get_post(post_id):
        raise HTTPException(status_code=HTTP_404_NOT_FOUND, detail="Post not found.")
    return await bulk_posts_action(background_tasks, action="retry", post_ids=[post_id], scheduled_for=None, user=user)


@router.post("/posts/{post_id}/cancel")
async def cancel_post_action(
    post_id: int,
    background_tasks: BackgroundTasks,
    user: Dict[str, Any] = Depends(get_current_user),
):
    if not get_post(post_id):
        raise HTTPException(status_code=HTTP_404_NOT_FOUND, detail="Post not found.")
    return await bulk_posts_action(background_tasks, action="cancel", post_ids=[post_id], scheduled_for=None, user=user)
