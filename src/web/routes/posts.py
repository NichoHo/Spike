"""
Spike: Platform Posting and Scheduling Routes.
Blueprint §8, §9, §10.8 & DESIGN.md §10.8 (Phase 6).
"""

import json
from datetime import datetime, timezone
from typing import Optional, Dict, Any, List

from fastapi import APIRouter, Request, Depends, Form, HTTPException
from fastapi.responses import HTMLResponse, RedirectResponse
from starlette.status import HTTP_404_NOT_FOUND, HTTP_403_FORBIDDEN, HTTP_303_SEE_OTHER

from src.db import (
    get_clip_with_details,
    list_posts,
    get_post,
    get_post_with_details,
    create_post,
    update_post_status,
    list_accounts,
    get_account,
    log_event,
    now_utc_iso,
)
from src.posting import (
    verify_clip_posting_permission,
    dispatch_post,
    get_next_schedule_slot,
    PermissionBlockedError,
)
from src.music import music_credit
from src.web.auth import get_current_user


router = APIRouter()


@router.get("/posts", response_class=HTMLResponse)
async def posts_page(
    request: Request,
    tab: str = "scheduled",
    user: Dict[str, Any] = Depends(get_current_user),
):
    templates = request.app.state.templates
    all_posts_raw = list_posts()
    all_posts = [dict(p) for p in all_posts_raw]

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
    features_json = clip.get("features") or "[]"
    tags = []
    if isinstance(features_json, str) and features_json.startswith("["):
        try:
            tags = json.loads(features_json)
        except Exception:
            tags = []

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
            "prefilled_tags": " ".join(f"#{t.lstrip('#')}" for t in tags) if tags else "#Shorts",
        },
    )


@router.post("/clips/{clip_id}/post")
async def post_clip_action(
    clip_id: int,
    account_id: int = Form(...),
    timing: str = Form("now"),
    scheduled_for: Optional[str] = Form(None),
    caption: str = Form(""),
    hashtags: Optional[str] = Form(""),
    user: Dict[str, Any] = Depends(get_current_user),
):
    # Blueprint §12: Strictly check permission in code
    try:
        verify_clip_posting_permission(clip_id)
    except PermissionBlockedError as e:
        raise HTTPException(status_code=HTTP_403_FORBIDDEN, detail=str(e))

    account = get_account(account_id, decrypt=False)
    if not account:
        raise HTTPException(status_code=HTTP_404_NOT_FOUND, detail="Platform account not found.")

    clean_caption = caption.strip()
    tag_list = [t.strip().lstrip("#") for t in (hashtags or "").split() if t.strip()]
    hashtags_json = json.dumps(tag_list)

    if timing == "now":
        slot_iso = now_utc_iso()
        post_id = create_post(
            clip_id=clip_id,
            account_id=account_id,
            status="uploading",
            scheduled_for=slot_iso,
            caption=clean_caption,
            hashtags=hashtags_json,
            posted_by=user.get("id"),
        )
        try:
            dispatch_post(post_id)
            return RedirectResponse(url="/posts?tab=posted", status_code=HTTP_303_SEE_OTHER)
        except Exception:
            # Error recorded in DB post record
            return RedirectResponse(url="/posts?tab=failed", status_code=HTTP_303_SEE_OTHER)
    else:
        # Scheduled post
        if scheduled_for and scheduled_for.strip():
            try:
                # Parse HTML datetime-local or ISO
                parsed_dt = datetime.fromisoformat(scheduled_for.strip())
                slot_iso = parsed_dt.astimezone(timezone.utc).isoformat()
            except Exception:
                next_slot = get_next_schedule_slot()
                slot_iso = next_slot.astimezone(timezone.utc).isoformat()
        else:
            next_slot = get_next_schedule_slot()
            slot_iso = next_slot.astimezone(timezone.utc).isoformat()

        post_id = create_post(
            clip_id=clip_id,
            account_id=account_id,
            status="scheduled",
            scheduled_for=slot_iso,
            caption=clean_caption,
            hashtags=hashtags_json,
            posted_by=user.get("id"),
        )
        log_event("info", f"Clip #{clip_id} scheduled for post #{post_id} at {slot_iso} by {user['login']}")
        return RedirectResponse(url="/posts?tab=scheduled", status_code=HTTP_303_SEE_OTHER)


@router.post("/posts/{post_id}/retry")
async def retry_post_action(
    post_id: int,
    user: Dict[str, Any] = Depends(get_current_user),
):
    post_row = get_post_with_details(post_id)
    if not post_row:
        raise HTTPException(status_code=HTTP_404_NOT_FOUND, detail="Post not found.")

    try:
        verify_clip_posting_permission(post_row["clip_id"])
    except PermissionBlockedError as e:
        raise HTTPException(status_code=HTTP_403_FORBIDDEN, detail=str(e))

    try:
        dispatch_post(post_id)
        return RedirectResponse(url="/posts?tab=posted", status_code=HTTP_303_SEE_OTHER)
    except Exception:
        return RedirectResponse(url="/posts?tab=failed", status_code=HTTP_303_SEE_OTHER)


@router.post("/posts/{post_id}/cancel")
async def cancel_post_action(
    post_id: int,
    user: Dict[str, Any] = Depends(get_current_user),
):
    post = get_post(post_id)
    if not post:
        raise HTTPException(status_code=HTTP_404_NOT_FOUND, detail="Post not found.")

    update_post_status(post_id, "cancelled", error="Cancelled by user")
    log_event("info", f"Post #{post_id} cancelled by {user['login']}")
    return RedirectResponse(url="/posts?tab=scheduled", status_code=HTTP_303_SEE_OTHER)
