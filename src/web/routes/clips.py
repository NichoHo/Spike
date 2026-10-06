"""
Spike: Clip media streaming, lifecycle, and interactive re-rendering routes.
Blueprint §7, §10.1, §10.2 & DESIGN.md §9.10, §9.11.
"""

import difflib
import json
import os
import re
import time
from collections import deque
from itertools import count
from pathlib import Path
from typing import Optional, Dict, Any

from fastapi import APIRouter, BackgroundTasks, Request, Depends, Form, HTTPException
from fastapi.responses import FileResponse, RedirectResponse
from starlette.status import HTTP_404_NOT_FOUND, HTTP_303_SEE_OTHER

from src.config import VIDEOS_DIR
from src.db import (
    get_clip_with_details,
    update_clip_status,
    update_clip_title,
    update_candidate_hook,
    create_or_update_clip,
    set_clip_render_state,
    list_review_clips,
    log_event,
)
from src.pipeline.stage9c_render import render_single_vertical_clip
from src.web.auth import get_current_user


router = APIRouter()

# In-memory rerender outcomes for toasts. Lost on restart, which is fine: they only drive a notification.
_render_events: deque = deque(maxlen=200)
_event_ids = count(1)
_EPOCH = int(time.time())  # changes on restart; event ids restart at 1 then


def _push_render_event(user_login: str, clip_id: int, title: str, ok: bool) -> None:
    _render_events.append({"id": next(_event_ids), "user": user_login, "clip_id": clip_id, "title": title, "ok": ok})


@router.get("/api/render-events")
async def render_events(after: Optional[int] = None, user: Dict[str, Any] = Depends(get_current_user)):
    """Rerender outcomes newer than `after`. Without `after`, only returns the baseline id."""
    last = _render_events[-1]["id"] if _render_events else 0
    if after is None:
        return {"epoch": _EPOCH, "last": last, "events": []}
    events = [e for e in list(_render_events) if e["id"] > after and e["user"] == user["login"]]
    return {"epoch": _EPOCH, "last": last, "events": events}


@router.get("/media/clip/{clip_id}/stream")
async def stream_clip_media(clip_id: int):
    """Serve vertical video file for playback in player or card preview."""
    clip_row = get_clip_with_details(clip_id)
    if not clip_row or not clip_row["file_path"]:
        raise HTTPException(status_code=HTTP_404_NOT_FOUND, detail="Clip media not found.")

    file_path = Path(clip_row["file_path"])
    if not file_path.exists():
        raise HTTPException(status_code=HTTP_404_NOT_FOUND, detail="Media file does not exist on disk.")

    # inline, not attachment: the player streams it with Range requests
    return FileResponse(path=file_path, media_type="video/mp4", content_disposition_type="inline")


@router.get("/media/clip/{clip_id}/thumb")
async def get_clip_thumbnail(clip_id: int):
    """Serve thumbnail image for clip card."""
    clip_row = get_clip_with_details(clip_id)
    if not clip_row or not clip_row["thumb_path"]:
        raise HTTPException(status_code=HTTP_404_NOT_FOUND, detail="Thumbnail not found.")

    thumb_path = Path(clip_row["thumb_path"])
    if not thumb_path.exists():
        raise HTTPException(status_code=HTTP_404_NOT_FOUND, detail="Thumbnail file does not exist.")

    return FileResponse(path=thumb_path, media_type="image/jpeg", filename=thumb_path.name)


@router.get("/clips/{clip_id}/download")
async def download_clip_file(
    clip_id: int,
    user: Dict[str, Any] = Depends(get_current_user),
):
    """Download vertical video file with safe filename attachment."""
    clip_row = get_clip_with_details(clip_id)
    if not clip_row or not clip_row["file_path"]:
        raise HTTPException(status_code=HTTP_404_NOT_FOUND, detail="Clip not found.")

    clip = dict(clip_row)
    file_path = Path(clip["file_path"])
    if not file_path.exists():
        raise HTTPException(status_code=HTTP_404_NOT_FOUND, detail="File not found on disk.")

    title = clip.get("cand_title") or f"clip_{clip_id}"
    safe_title = re.sub(r'[^a-zA-Z0-9_\- ]', '', title).strip().replace(' ', '_')[:60]
    filename = f"{safe_title}.mp4"

    return FileResponse(
        path=file_path,
        media_type="video/mp4",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )


@router.post("/clips/{clip_id}/approve")
async def approve_clip_action(
    clip_id: int,
    user: Dict[str, Any] = Depends(get_current_user),
):
    """Mark clip as approved."""
    update_clip_status(clip_id, "approved", user_id=user.get("id"))
    log_event("info", f"Clip #{clip_id} approved by {user['login']}")

    # If there's a next ready clip, navigate to it, else home
    ready_clips = list_review_clips(status="ready")
    if ready_clips:
        next_id = ready_clips[0]["id"]
        return RedirectResponse(url=f"/clips/{next_id}", status_code=HTTP_303_SEE_OTHER)
    return RedirectResponse(url="/", status_code=HTTP_303_SEE_OTHER)


@router.post("/clips/{clip_id}/reject")
async def reject_clip_action(
    clip_id: int,
    reason: Optional[str] = Form(""),
    user: Dict[str, Any] = Depends(get_current_user),
):
    """Mark clip as rejected with optional feedback reason."""
    clean_reason = (reason or "").strip()
    update_clip_status(clip_id, "rejected", user_id=user.get("id"), reject_reason=clean_reason)
    log_event("info", f"Clip #{clip_id} rejected by {user['login']} (Reason: '{clean_reason}')")
    return RedirectResponse(url="/", status_code=HTTP_303_SEE_OTHER)


@router.post("/clips/{clip_id}/title")
async def rename_clip_action(
    clip_id: int,
    title: str = Form(...),
    user: Dict[str, Any] = Depends(get_current_user),
):
    clean = title.strip()[:200]
    if not clean or not update_clip_title(clip_id, clean):
        raise HTTPException(status_code=HTTP_404_NOT_FOUND, detail="Clip not found or empty title.")
    return RedirectResponse(url=f"/clips/{clip_id}", status_code=HTTP_303_SEE_OTHER)


def _load_words(video_dir: Path, cand_id: int) -> list:
    """Word list for captions: the user's saved edit if any, else the Whisper transcript."""
    override = video_dir / "renders" / f"captions_{cand_id}.json"
    if override.exists():
        try:
            return json.loads(override.read_text(encoding="utf-8"))
        except Exception:
            pass
    words = []
    transcript_file = video_dir / "transcript.json"
    if transcript_file.exists():
        try:
            for seg in json.loads(transcript_file.read_text(encoding="utf-8")).get("segments", []):
                words.extend(seg.get("words", []))
        except Exception:
            pass
    return words


def _retime_edit(old: list, new_words: list) -> list:
    """Give edited words timings. Words that survive the edit keep their spoken timing
    (so captions stay on the audio); only changed spots are spread across the time of the
    words they replace. Spreading the whole clip evenly made captions drift off the speech."""
    norm = lambda s: re.sub(r"[^\w']", "", s.lower())
    ops = difflib.SequenceMatcher(
        a=[norm(w["word"]) for w in old], b=[norm(w) for w in new_words], autojunk=False
    ).get_opcodes()
    out = []
    for tag, i1, i2, j1, j2 in ops:
        if tag == "equal":
            out += [dict(old[i1 + k], word=new_words[j1 + k]) for k in range(i2 - i1)]
        elif j2 > j1:  # replace or insert: spread over the replaced words' time, or the gap for an insert
            if i2 > i1:
                t0, t1 = old[i1]["start"], old[i2 - 1].get("end", old[i2 - 1]["start"])
            else:
                t0 = old[i1 - 1].get("end", old[i1 - 1]["start"]) if i1 else old[0]["start"]
                t1 = old[i1]["start"] if i1 < len(old) else t0
            n = j2 - j1
            if t1 - t0 < 0.1 * n:
                t1 = t0 + 0.25 * n  # a tight gap would flash the words; let them overlap the next one a little
            step = (t1 - t0) / n
            out += [{"word": new_words[j1 + k], "start": round(t0 + k * step, 3), "end": round(t0 + (k + 1) * step, 3)}
                    for k in range(n)]
    return out


def _in_window(w: Dict[str, Any], start_s: float, end_s: float) -> bool:
    # Same window stage9b_captions._group_words uses
    return start_s <= w.get("start", 0) < end_s and bool(w.get("word", "").strip())


@router.get("/clips/{clip_id}/captions")
async def get_clip_captions(
    clip_id: int,
    start_s: float,
    end_s: float,
    user: Dict[str, Any] = Depends(get_current_user),
):
    """Current caption text for the clip window, for the edit-captions dialog."""
    clip_row = get_clip_with_details(clip_id)
    if not clip_row:
        raise HTTPException(status_code=HTTP_404_NOT_FOUND, detail="Clip not found.")
    clip = dict(clip_row)
    words = _load_words(VIDEOS_DIR / str(clip["video_id"]), clip["candidate_id"])
    return {"text": " ".join(w["word"].strip() for w in words if _in_window(w, start_s, end_s))}


@router.post("/clips/{clip_id}/rerender")
async def rerender_clip_action(
    background_tasks: BackgroundTasks,
    clip_id: int,
    start_s: float = Form(...),
    end_s: float = Form(...),
    layout: str = Form("split"),
    caption_style: str = Form("bold_pop"),
    hook_text: Optional[str] = Form(""),
    show_hook: bool = Form(False),
    music_enabled: bool = Form(False),
    music_track: Optional[str] = Form(None),
    silence_trim: bool = Form(False),
    punch_in_zoom: bool = Form(True),
    caption_text: Optional[str] = Form(None),
    user: Dict[str, Any] = Depends(get_current_user),
):
    """Interactively re-render vertical clip with user trims and style options."""
    clip_row = get_clip_with_details(clip_id)
    if not clip_row:
        raise HTTPException(status_code=HTTP_404_NOT_FOUND, detail="Clip not found.")

    clip = dict(clip_row)
    if clip["status"] == "rendering":
        return RedirectResponse(url=f"/clips/{clip_id}", status_code=HTTP_303_SEE_OTHER)
    video_id = clip["video_id"]
    cand_id = clip["candidate_id"]
    video_dir = VIDEOS_DIR / str(video_id)
    renders_dir = video_dir / "renders"
    sections_dir = video_dir / "sections"
    renders_dir.mkdir(parents=True, exist_ok=True)

    # Locate section file (stage 8 names it section_<candidate id>.mp4)
    sec_file = sections_dir / f"section_{cand_id}.mp4"
    if not sec_file.exists():
        raise HTTPException(
            status_code=HTTP_404_NOT_FOUND,
            detail="Section source file for this clip is missing on disk."
        )

    all_words = _load_words(video_dir, cand_id)

    # Edited caption text: unchanged words keep their timing, changed spots are re-spread
    # (see _retime_edit). Saved so later re-renders keep the edit.
    if caption_text is not None:
        new_words = caption_text.split()
        old = [w for w in all_words if _in_window(w, start_s, end_s)]
        if new_words and old and new_words != [w["word"].strip() for w in old]:
            edited = _retime_edit(old, new_words)
            all_words = [w for w in all_words if not _in_window(w, start_s, end_s)] + edited
            all_words.sort(key=lambda w: w.get("start", 0))
            (renders_dir / f"captions_{cand_id}.json").write_text(json.dumps(all_words), encoding="utf-8")

    # Resolve music track
    chosen_music_str: Optional[str] = None
    if music_enabled:
        from src.music import get_random_track_for_mood
        if music_track and music_track.strip() not in ("", "auto"):
            chosen_music_str = music_track.strip()
        else:
            cand_mood = clip.get("mood") or "chill"
            track_p = get_random_track_for_mood(cand_mood)
            chosen_music_str = str(track_p) if track_p else None

    # Version increment
    new_version = (clip.get("version") or 1) + 1
    new_out_file = renders_dir / f"clip_{cand_id}_v{new_version}.mp4"
    new_thumb_file = renders_dir / f"clip_{cand_id}_v{new_version}_thumb.jpg"

    clean_hook = (hook_text or "").strip()

    prev_status = clip["status"]
    user_login = user["login"]
    clip_title = clip.get("cand_title") or f"Clip #{clip_id}"

    # Runs in a worker thread after the response is sent, so the user can leave the
    # page and the event loop stays free for other requests and other rerenders.
    def _job():
        try:
            ok = render_single_vertical_clip(
                sec_file=sec_file,
                out_file=new_out_file,
                thumb_file=new_thumb_file,
                clip_start=start_s,
                clip_end=end_s,
                layout=layout,
                caption_style=caption_style,
                hook_text=clean_hook if show_hook else "",
                all_words=all_words,
                music_track=chosen_music_str,
                silence_trim=silence_trim,
                punch_in_zoom=punch_in_zoom,
            )
        except Exception as exc:
            ok = False
            log_event("error", f"Clip #{clip_id} re-render crashed: {exc}")

        if not ok:
            set_clip_render_state(clip_id, prev_status)
            log_event("error", f"Clip #{clip_id} re-render failed in ffmpeg (requested by {user_login})")
            _push_render_event(user_login, clip_id, clip_title, False)
            return

        create_or_update_clip(
            candidate_id=cand_id,
            file_path=str(new_out_file),
            thumb_path=str(new_thumb_file),
            layout=layout,
            caption_style=caption_style,
            trim_start_s=start_s,
            trim_end_s=end_s,
            music_track=chosen_music_str,
            silence_trim=1 if silence_trim else 0,
            punch_in_zoom=1 if punch_in_zoom else 0,
            status="ready",
            show_hook=1 if show_hook and clean_hook else 0,
        )
        if clean_hook and clean_hook != (clip.get("cand_hook") or ""):
            update_candidate_hook(cand_id, clean_hook)
        log_event("info", f"Clip #{clip_id} re-rendered (v{new_version}, {layout}, {caption_style}, music={bool(chosen_music_str)}, silence_trim={silence_trim}) by {user_login}")
        _push_render_event(user_login, clip_id, clip_title, True)

    set_clip_render_state(clip_id, "rendering")
    background_tasks.add_task(_job)

    return RedirectResponse(url=f"/clips/{clip_id}", status_code=HTTP_303_SEE_OTHER)
