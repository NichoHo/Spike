"""
Spike: Settings & administration routes.
Blueprint §10.6, §10.10 & DESIGN.md §10.10.
"""

import json
import urllib.parse
import uuid
from pathlib import Path
from typing import Dict, Any, List, Optional
from fastapi import APIRouter, BackgroundTasks, Request, Depends, File, Form, HTTPException, UploadFile
from fastapi.responses import HTMLResponse, PlainTextResponse, RedirectResponse, JSONResponse
from pydantic import BaseModel, Field
from starlette.status import HTTP_303_SEE_OTHER

from src.config import (
    CLAUDE_LANE_DAILY_CAP,
    DEFAULT_WHISPER_MODEL,
    WHISPER_COMPUTE_TYPE,
    DEFAULT_GEMINI_MODEL,
    DATA_DIR,
    DB_PATH,
    PUBLIC_URL,
    UPLOADS_DIR,
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
    delete_label,
    get_label,
    list_labels,
    save_label,
    update_label,
)
from src.labels import (GOLD_CATEGORIES, GOLD_EXTS, GOLD_MAX_BYTES, LIKE_TAGS, OTHER_CHARS, OTHER_MAX, analyze_gold,
                        gold_url_ok, reason_texts, shared_link)
from src.concepts import EMOTIONS
from src.notify import get_active_webhook_url, verify_discord_webhook
from src.pov import add_to_bank, delete_from_bank, load_bank
from src import platform_auth
from src.judge_pool import HELP_KEY, HELP_MODES, help_mode
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
            "claude_help": help_mode(),
            "claude_lane_cap": CLAUDE_LANE_DAILY_CAP,
            "gold_labels": [{**dict(r), "likes": reason_texts(r["reasons"], LIKE_TAGS)} for r in list_labels("gold")],
            "gold_categories": GOLD_CATEGORIES,
            "like_tags": LIKE_TAGS,
            "standards_error": request.query_params.get("standards_error", ""),
            "share_url": f"{PUBLIC_URL}/settings/standards/share",
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


@router.post("/settings/claude-help")
async def save_claude_help(
    mode: str = Form("down"),
    user: Dict[str, Any] = Depends(require_admin),
):
    if mode in HELP_MODES:  # form values are untrusted: only the three known modes are stored
        set_setting(HELP_KEY, mode)
    return RedirectResponse(url="/settings", status_code=HTTP_303_SEE_OTHER)


def _standards_back(error: str = "") -> RedirectResponse:
    query = f"?standards_error={urllib.parse.quote(error)}" if error else ""
    return RedirectResponse(url=f"/settings{query}#standards", status_code=HTTP_303_SEE_OTHER)


@router.post("/settings/standards")
async def add_standard(
    background_tasks: BackgroundTasks,
    url: str = Form(""),
    category: str = Form("any"),
    likes: List[str] = Form([]),
    other: List[str] = Form([]),
    file: Optional[UploadFile] = File(None),
    user: Dict[str, Any] = Depends(require_admin),
):
    """Add a short the team holds up as the standard: a link from an allowed host, or an uploaded video file, with the
    optional reasons the team likes it. Gemini reads it in the background (src/labels.analyze_gold); until then the
    card shows it as reading."""
    category = category if category in GOLD_CATEGORIES else "any"
    url = url.strip()
    likes = [t for t in dict.fromkeys(likes) if t in LIKE_TAGS]  # form input is untrusted: known tags only, once each
    others = [o for o in dict.fromkeys(" ".join(o.split())[:OTHER_CHARS].strip() for o in other) if o][:OTHER_MAX]
    fields = {"kind": "gold", "category": category, "status": "processing", "reasons": json.dumps(likes + others)}
    if file and file.filename:
        ext = Path(file.filename).suffix.lower()
        if ext not in GOLD_EXTS:
            return _standards_back(f"Upload a video file ({', '.join(sorted(GOLD_EXTS))}).")
        dest = UPLOADS_DIR / f"gold_{uuid.uuid4().hex}{ext}"  # never the user's file name in the path
        size = 0
        with open(dest, "wb") as out:
            while chunk := await file.read(1024 * 1024):
                size += len(chunk)
                if size > GOLD_MAX_BYTES:
                    break
                out.write(chunk)
        if size > GOLD_MAX_BYTES:
            dest.unlink(missing_ok=True)
            return _standards_back("That file is over 200 MB.")
        label_id = save_label({**fields, "source_url": file.filename[:200]})
        background_tasks.add_task(analyze_gold, label_id, str(dest))
    elif url:
        if not gold_url_ok(url):
            return _standards_back("Paste a TikTok, YouTube or Instagram link.")
        label_id = save_label({**fields, "source_url": url})
        background_tasks.add_task(analyze_gold, label_id)
    else:
        return _standards_back("Paste a link or pick a video file.")
    return _standards_back()


class SharedText(BaseModel):
    text: str = Field("", max_length=4000)


@router.post("/settings/standards/share", response_class=PlainTextResponse)
async def share_standard(body: SharedText, background_tasks: BackgroundTasks,
                         user: Dict[str, Any] = Depends(require_admin)) -> str:
    """The iPhone Shortcut's way in (docs/superpowers/specs/2026-11-10-share-standard-design.md): whatever the share
    sheet sent, as JSON. JSON only, so a form on another site cannot post here: FastAPI refuses other content types.
    Replies with one line for the Shortcut's notification."""
    link = shared_link(body.text)
    if not link:
        return "No TikTok, YouTube or Instagram link in that."
    same = [g for g in list_labels("gold") if g["source_url"] == link]
    if any(g["status"] != "failed" for g in same):
        return "Already a standard."
    if same:  # shared again after a failed read: read it again
        label_id = same[0]["id"]
        update_label(label_id, status="processing", error=None)
    else:
        label_id = save_label({"kind": "gold", "category": "any", "status": "processing", "reasons": "[]",
                               "source_url": link})
    background_tasks.add_task(analyze_gold, label_id)
    return "Saved. Gemini is reading it."


@router.post("/settings/standards/{label_id}/delete")
async def delete_standard(label_id: int, user: Dict[str, Any] = Depends(require_admin)):
    label = get_label(label_id)
    if label and label["kind"] == "gold":  # this route never deletes a review verdict
        delete_label(label_id)
    return _standards_back()


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
