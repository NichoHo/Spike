"""
Spike: Sources management routes.
Blueprint §10.3, §10.5, §10.6 & DESIGN.md §10.5, §10.6.
"""

from typing import Dict, Any
from fastapi import APIRouter, Request, Depends, Form, HTTPException
from fastapi.responses import HTMLResponse, RedirectResponse
from starlette.status import HTTP_404_NOT_FOUND, HTTP_303_SEE_OTHER

from src.db import (
    list_sources,
    get_source,
    create_source,
    update_source,
    delete_source,
    list_review_clips,
)
from src.web.auth import get_current_user


router = APIRouter()


@router.get("/sources", response_class=HTMLResponse)
async def sources_list(
    request: Request,
    user: Dict[str, Any] = Depends(get_current_user),
):
    templates = request.app.state.templates
    sources = [dict(s) for s in list_sources()]
    review_count = len(list_review_clips(status="ready"))

    return templates.TemplateResponse(
        request=request,
        name="pages/sources.html",
        context={
            "page_title": "Sources",
            "active_nav": "sources",
            "page_width": "wide",
            "user": user,
            "sources": sources,
            "review_count": review_count,
        },
    )


@router.get("/sources/new", response_class=HTMLResponse)
async def new_source_form(
    request: Request,
    user: Dict[str, Any] = Depends(get_current_user),
):
    templates = request.app.state.templates
    review_count = len(list_review_clips(status="ready"))

    return templates.TemplateResponse(
        request=request,
        name="pages/source_edit.html",
        context={
            "page_title": "Add Source",
            "active_nav": "sources",
            "page_width": "narrow",
            "user": user,
            "source": None,
            "review_count": review_count,
        },
    )


@router.post("/sources/new")
async def create_source_action(
    kind: str = Form("twitch"),
    external_id: str = Form(...),
    display_name: str = Form(...),
    permission: str = Form("none"),
    permission_note: str = Form(""),
    auto_process: bool = Form(False),
    layout: str = Form("split"),
    caption_style: str = Form("bold_pop"),
    music: bool = Form(False),
    default_music_mood: str = Form("chill"),
    silence_trim: bool = Form(False),
    punch_in_zoom: bool = Form(True),
    style_notes: str = Form(""),
    user: Dict[str, Any] = Depends(get_current_user),
):
    data = {
        "kind": kind,
        "external_id": external_id.strip(),
        "display_name": display_name.strip(),
        "permission": permission,
        "permission_note": permission_note.strip(),
        "auto_process": auto_process,
        "layout": layout,
        "caption_style": caption_style,
        "music": 1 if music else 0,
        "default_music_mood": default_music_mood,
        "silence_trim": 1 if silence_trim else 0,
        "punch_in_zoom": 1 if punch_in_zoom else 0,
        "style_notes": style_notes.strip(),
    }
    create_source(data)
    return RedirectResponse(url="/sources", status_code=HTTP_303_SEE_OTHER)


@router.get("/sources/{source_id}", response_class=HTMLResponse)
async def edit_source_form(
    request: Request,
    source_id: int,
    user: Dict[str, Any] = Depends(get_current_user),
):
    templates = request.app.state.templates
    src_row = get_source(source_id)
    if not src_row:
        raise HTTPException(status_code=HTTP_404_NOT_FOUND, detail="Source not found.")

    review_count = len(list_review_clips(status="ready"))

    return templates.TemplateResponse(
        request=request,
        name="pages/source_edit.html",
        context={
            "page_title": f"Edit {src_row['display_name']}",
            "active_nav": "sources",
            "page_width": "narrow",
            "user": user,
            "source": dict(src_row),
            "review_count": review_count,
        },
    )


@router.post("/sources/{source_id}/edit")
async def update_source_action(
    source_id: int,
    display_name: str = Form(...),
    permission: str = Form("none"),
    permission_note: str = Form(""),
    auto_process: bool = Form(False),
    layout: str = Form("split"),
    caption_style: str = Form("bold_pop"),
    music: bool = Form(False),
    default_music_mood: str = Form("chill"),
    silence_trim: bool = Form(False),
    punch_in_zoom: bool = Form(True),
    style_notes: str = Form(""),
    user: Dict[str, Any] = Depends(get_current_user),
):
    src_row = get_source(source_id)
    if not src_row:
        raise HTTPException(status_code=HTTP_404_NOT_FOUND, detail="Source not found.")

    data = {
        "display_name": display_name.strip(),
        "permission": permission,
        "permission_note": permission_note.strip(),
        "auto_process": auto_process,
        "layout": layout,
        "caption_style": caption_style,
        "music": 1 if music else 0,
        "default_music_mood": default_music_mood,
        "silence_trim": 1 if silence_trim else 0,
        "punch_in_zoom": 1 if punch_in_zoom else 0,
        "style_notes": style_notes.strip(),
    }
    update_source(source_id, data)
    return RedirectResponse(url="/sources", status_code=HTTP_303_SEE_OTHER)


@router.post("/sources/{source_id}/delete")
async def delete_source_action(
    source_id: int,
    user: Dict[str, Any] = Depends(get_current_user),
):
    delete_source(source_id)
    return RedirectResponse(url="/sources", status_code=HTTP_303_SEE_OTHER)
