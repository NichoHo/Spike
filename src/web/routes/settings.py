"""
Spike: Settings & administration routes.
Blueprint §10.6, §10.10 & DESIGN.md §10.10.
"""

from typing import Dict, Any, Optional
from fastapi import APIRouter, Request, Depends, Form, HTTPException
from fastapi.responses import HTMLResponse, RedirectResponse, JSONResponse
from starlette.status import HTTP_303_SEE_OTHER

from src.config import (
    DEFAULT_WHISPER_MODEL,
    WHISPER_COMPUTE_TYPE,
    DEFAULT_GEMINI_MODEL,
    DATA_DIR,
    DB_PATH,
)
from src.db import (
    list_users,
    create_user,
    update_user_status,
    get_user_by_id,
    get_setting,
    set_setting,
    list_review_clips,
    list_accounts,
    create_account,
    delete_account,
)
from src.notify import get_active_webhook_url, verify_discord_webhook
from src.web.auth import get_current_user, require_admin


router = APIRouter()


@router.get("/settings", response_class=HTMLResponse)
async def settings_page(
    request: Request,
    user: Dict[str, Any] = Depends(require_admin),
):
    templates = request.app.state.templates
    users = [dict(u) for u in list_users()]
    review_count = len(list_review_clips(status="ready"))
    webhook_url = get_active_webhook_url()

    config_info = {
        "whisper_model": DEFAULT_WHISPER_MODEL,
        "whisper_compute": WHISPER_COMPUTE_TYPE,
        "gemini_model": DEFAULT_GEMINI_MODEL,
        "data_dir": str(DATA_DIR),
        "db_path": str(DB_PATH),
    }

    accounts = list_accounts(decrypt=False)

    return templates.TemplateResponse(
        request=request,
        name="pages/settings.html",
        context={
            "page_title": "Settings",
            "active_nav": "settings",
            "page_width": "narrow",
            "user": user,
            "users": users,
            "accounts": accounts,
            "discord_webhook_url": webhook_url,
            "config_info": config_info,
            "review_count": review_count,
        },
    )


@router.post("/settings/accounts/add")
async def add_account_action(
    platform: str = Form(...),
    display_name: str = Form(...),
    access_token: str = Form(...),
    refresh_token: Optional[str] = Form(None),
    user: Dict[str, Any] = Depends(require_admin),
):
    clean_platform = platform.strip().lower()
    clean_name = display_name.strip()
    clean_token = access_token.strip()
    clean_ref = refresh_token.strip() if refresh_token else None

    create_account(
        platform=clean_platform,
        display_name=clean_name,
        access_token=clean_token,
        refresh_token=clean_ref,
        connected_by=user.get("id"),
    )
    return RedirectResponse(url="/settings", status_code=HTTP_303_SEE_OTHER)


@router.post("/settings/accounts/{account_id}/delete")
async def delete_account_action(
    account_id: int,
    user: Dict[str, Any] = Depends(require_admin),
):
    delete_account(account_id)
    return RedirectResponse(url="/settings", status_code=HTTP_303_SEE_OTHER)


@router.post("/settings/discord")
async def save_discord_webhook(
    webhook_url: str = Form(""),
    user: Dict[str, Any] = Depends(require_admin),
):
    set_setting("discord_webhook_url", webhook_url.strip())
    return RedirectResponse(url="/settings", status_code=HTTP_303_SEE_OTHER)


@router.post("/settings/discord/test")
async def test_discord_action(
    webhook_url: str = Form(...),
    user: Dict[str, Any] = Depends(require_admin),
):
    ok, msg = verify_discord_webhook(webhook_url)
    return JSONResponse({"ok": ok, "error": "" if ok else msg})


@router.post("/settings/users/add")
async def add_user_action(
    login: str = Form(...),
    name: str = Form(""),
    role: str = Form("member"),
    user: Dict[str, Any] = Depends(require_admin),
):
    clean_login = login.strip().lower()
    create_user(clean_login, name.strip() or clean_login, role=role)
    return RedirectResponse(url="/settings", status_code=HTTP_303_SEE_OTHER)


@router.post("/settings/users/{user_id}/toggle")
async def toggle_user_action(
    user_id: int,
    user: Dict[str, Any] = Depends(require_admin),
):
    target = get_user_by_id(user_id)
    if target and target["login"] != user["login"]:
        new_active = 0 if target["active"] else 1
        update_user_status(user_id, new_active)
    return RedirectResponse(url="/settings", status_code=HTTP_303_SEE_OTHER)
