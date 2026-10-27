"""
Spike: Settings & administration routes.
Blueprint §10.6, §10.10 & DESIGN.md §10.10.
"""

import urllib.parse
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
    delete_account,
)
from src.concepts import EMOTIONS
from src.notify import get_active_webhook_url, verify_discord_webhook
from src.pov import add_to_bank, delete_from_bank, load_bank
from src import platform_auth
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
            "pov_bank": load_bank(),
            "emotions": EMOTIONS,
            "bank_status": request.query_params.get("bank", ""),
            "connect_options": platform_auth.connect_options(),
            "accounts_notice": request.query_params.get("notice", ""),
            "accounts_error": request.query_params.get("error", ""),
        },
    )


@router.post("/settings/pov-bank/add")
async def add_pov_caption_action(
    text: str = Form(...),
    emotion: str = Form(...),
    user: Dict[str, Any] = Depends(require_admin),
):
    """Add a caption you saw and liked. Captions are only ever added by hand; Spike never fetches them."""
    status = "added" if add_to_bank(text, emotion) else "rejected"
    return RedirectResponse(url=f"/settings?bank={status}#pov-captions", status_code=HTTP_303_SEE_OTHER)


@router.post("/settings/pov-bank/{index}/delete")
async def delete_pov_caption_action(
    index: int,
    user: Dict[str, Any] = Depends(require_admin),
):
    delete_from_bank(index)
    return RedirectResponse(url="/settings#pov-captions", status_code=HTTP_303_SEE_OTHER)


def _accounts_back(notice: str = "", error: str = "") -> RedirectResponse:
    q = urllib.parse.urlencode({k: v[:300] for k, v in (("notice", notice), ("error", error)) if v})
    return RedirectResponse(url=f"/settings?{q}#accounts", status_code=HTTP_303_SEE_OTHER)


@router.get("/accounts/{platform}/connect")
async def connect_account(platform: str, user: Dict[str, Any] = Depends(require_admin)):
    if platform not in platform_auth.PLATFORMS:
        raise HTTPException(status_code=404, detail="Unknown platform.")
    if not platform_auth.configured(platform):
        cid, secret = platform_auth.PLATFORMS[platform]["env"]
        return _accounts_back(error=f"Set {cid} and {secret} in .env first, then restart Spike.")
    return RedirectResponse(platform_auth.start_auth(platform, user.get("id")), status_code=HTTP_303_SEE_OTHER)


@router.get("/accounts/{platform}/callback")
async def connect_account_callback(platform: str, state: str = "", code: str = "", error: Optional[str] = None,
                                   error_description: Optional[str] = None,
                                   user: Dict[str, Any] = Depends(require_admin)):
    if platform not in platform_auth.PLATFORMS:
        raise HTTPException(status_code=404, detail="Unknown platform.")
    if error or not code:
        return _accounts_back(error=f"Sign-in was cancelled ({error_description or error or 'no code'}).")
    try:
        name = platform_auth.finish_auth(platform, state, code)
    except platform_auth.PlatformError as e:
        return _accounts_back(error=str(e))
    return _accounts_back(notice=f"Connected {platform_auth.PLATFORMS[platform]['label']}: {name}.")


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
