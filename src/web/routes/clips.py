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
from fastapi.responses import FileResponse, HTMLResponse, RedirectResponse
from starlette.status import HTTP_404_NOT_FOUND, HTTP_303_SEE_OTHER

from src.concepts import CONCEPTS
from src.config import SILENCE_TRIM_S, VIDEOS_DIR
from src.cleanup import delete_rejected_clip_files
from src.db import (
    get_clip_with_details,
    update_clip_status,
    update_clip_title,
    update_candidate_hook,
    create_or_update_clip,
    set_clip_render_state,
    set_clip_layout_changes,
    list_review_clips,
    log_event,
)
from src.pipeline.stage9c_render import SWITCH_LAYOUTS, render_single_vertical_clip
from src import claude_fallback, gemini_budget
from src.web.auth import get_current_user, require_admin


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


@router.get("/api/claude-approval")
async def claude_approval_pending(user: Dict[str, Any] = Depends(require_admin)):
    """The Claude fallback call waiting for the user's OK, polled by every page."""
    return {"request": claude_fallback.pending(), "resets_at": gemini_budget.reset_at()}


def ai_status() -> Dict[str, Any]:
    """Sidebar panel: which AI is working right now, today's successful Gemini calls per model across all keys
    against the learned limit (Gemini does not report remaining quota), and whether Claude is paused."""
    from src import config
    models = dict.fromkeys([config.DEFAULT_GEMINI_MODEL, config.JUDGE_GEMINI_MODEL])  # same model twice: one row
    keys = config.gemini_keys()
    return {
        "claude_call": claude_fallback.running(),
        "claude_waiting": bool(claude_fallback.pending()),
        "paused": claude_fallback.paused(),
        # A key Google cut off counts as full, so the bar shows what is really left.
        "gemini": [{
            "model": m,
            "used": sum(gemini_budget.per_key_limit(m) if gemini_budget.key_capped(m, k) else gemini_budget.key_used(m, k)
                        for k in keys),
            "limit": gemini_budget.limit(m),
        } for m in models],
    }


@router.get("/ai-usage", response_class=HTMLResponse)
async def ai_usage_page(request: Request, user: Dict[str, Any] = Depends(get_current_user)):
    """Gemini calls today for each key in GEMINI_API_KEY, per model. Keys are shown by position and last 4 characters only."""
    from datetime import datetime
    from src import config
    keys = config.gemini_keys()
    models = list(dict.fromkeys([config.DEFAULT_GEMINI_MODEL, config.JUDGE_GEMINI_MODEL]))
    rows = []
    for i, k in enumerate(keys, 1):
        per_model = []
        for m in models:
            capped = gemini_budget.key_capped(m, k)
            limit = gemini_budget.per_key_limit(m)
            per_model.append({"model": m, "used": limit if capped else gemini_budget.key_used(m, k), "limit": limit, "capped": capped})
        rows.append({"n": i, "tail": k[-4:], "models": per_model})
    return request.app.state.templates.TemplateResponse(
        request=request,
        name="pages/ai_usage.html",
        context={
            "page_title": "Gemini key usage",
            "active_nav": "settings",
            "user": user,
            "rows": rows,
            "models": models,
            "duplicates": len(keys) - len(set(keys)),
            "resets_at": datetime.fromtimestamp(gemini_budget.reset_at()).strftime("%a %H:%M"),
        },
    )


@router.get("/partials/ai-status", response_class=HTMLResponse)
async def ai_status_partial(request: Request, user: Dict[str, Any] = Depends(get_current_user)):
    """The sidebar panel, re-rendered for app.js to swap in."""
    return request.app.state.templates.TemplateResponse(request=request, name="partials/ai_status.html", context={"user": user})


@router.post("/api/claude-pause")
async def claude_pause(request: Request, user: Dict[str, Any] = Depends(require_admin)):
    """Body: {"paused": bool}. JSON only, like /api/claude-approval."""
    if not request.headers.get("content-type", "").startswith("application/json"):
        raise HTTPException(status_code=415, detail="JSON body required")
    on = bool((await request.json()).get("paused"))
    claude_fallback.set_paused(on)
    log_event("info", f"Claude {'paused' if on else 'resumed'} by {user.get('login')}")
    return {"paused": on}


@router.post("/api/claude-approval")
async def claude_approval_answer(request: Request, user: Dict[str, Any] = Depends(require_admin)):
    # JSON only: another site can POST text/plain without a CORS preflight, but not application/json
    if not request.headers.get("content-type", "").startswith("application/json"):
        raise HTTPException(status_code=415, detail="JSON body required")
    body = await request.json()
    ok = claude_fallback.answer(str(body.get("id", "")), bool(body.get("approve")), bool(body.get("skip_today")))
    return {"ok": ok}


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


@router.get("/media/music/{rel_path:path}")
async def music_preview(rel_path: str, user: Dict[str, Any] = Depends(get_current_user)):
    """A library track for the clip page's preview button. Only paths in the music library are served."""
    from src.music import list_all_tracks
    track = next((t for t in list_all_tracks() if t["rel_path"] == rel_path), None)
    if not track:
        raise HTTPException(status_code=HTTP_404_NOT_FOUND, detail="Track not found.")
    return FileResponse(path=track["path"], content_disposition_type="inline")


@router.get("/media/sfx/{sound_id}")
def sfx_preview(sound_id: str, user: Dict[str, Any] = Depends(get_current_user)):
    """A sound effect for the clip page's preview and live playback. Sync: the first request may fetch the file."""
    from src.sfx import sound_path
    path = sound_path(sound_id)
    if not path:
        raise HTTPException(status_code=HTTP_404_NOT_FOUND, detail="Sound not found.")
    return FileResponse(path=path, media_type="audio/mpeg", content_disposition_type="inline")


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
    background_tasks: BackgroundTasks,
    reason: Optional[str] = Form(""),
    user: Dict[str, Any] = Depends(get_current_user),
):
    """Mark clip as rejected with optional feedback reason."""
    clean_reason = (reason or "").strip()
    clip_row = get_clip_with_details(clip_id)
    update_clip_status(clip_id, "rejected", user_id=user.get("id"), reject_reason=clean_reason)
    if clip_row and clip_row["status"] != "rendering":  # a running re-render would recreate files
        delete_rejected_clip_files(dict(clip_row))
    log_event("info", f"Clip #{clip_id} rejected by {user['login']} (Reason: '{clean_reason}')")
    if clip_row and clean_reason:
        from src.profile import record_feedback  # every 5th item makes one summary call, so run it after the response
        background_tasks.add_task(record_feedback, clip_row["source_id"], f"Rejected: {clean_reason}")
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


def _parse_layout_changes(raw: str, start_s: float, end_s: float) -> list:
    """Form JSON [{t, layout}] (t in source seconds) -> cleaned, sorted list. Bad input is dropped."""
    try:
        items = json.loads(raw) if raw.strip() else []
    except ValueError:
        return []
    if not isinstance(items, list):
        return []
    out = []
    for it in items[:20]:
        try:
            t = round(float(it["t"]), 2)
        except (TypeError, KeyError, ValueError):
            continue
        if it.get("layout") in SWITCH_LAYOUTS and start_s < t < end_s:
            out.append({"t": t, "layout": it["layout"]})
    return sorted(out, key=lambda c: c["t"])


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
    silence_trim_s: float = Form(SILENCE_TRIM_S),  # cut pauses longer than this
    caption_text: Optional[str] = Form(None),
    layout_changes: str = Form(""),
    letterbox_style: str = Form("blur"),  # the toggle sends "title" when on
    zooms: Optional[str] = Form(None),    # JSON [{t, scale, hold_s}]; absent keeps the stored list
    cuts: Optional[str] = Form(None),     # JSON [[start_s, end_s]]; absent keeps the stored cuts
    sfx: Optional[str] = Form(None),      # JSON [{t, id}] meme sounds; absent keeps the stored ones
    concept: Optional[str] = Form(None),          # single, story, pov, top3, top5; absent keeps the clip's concept
    segments: Optional[str] = Form(None),         # JSON segments of a concept clip
    overlay: Optional[str] = Form(None),          # JSON {pov_text, skip_card, callback_quote, foreshadow, ...}
    theme: Optional[str] = Form(None),
    concept_source: Optional[str] = Form(None),   # the page sends "user" once anything about the concept was changed
    user: Dict[str, Any] = Depends(get_current_user),
):
    """Interactively re-render vertical clip with user trims and style options."""
    clip_row = get_clip_with_details(clip_id)
    if not clip_row:
        raise HTTPException(status_code=HTTP_404_NOT_FOUND, detail="Clip not found.")

    clip = dict(clip_row)
    if clip["status"] == "rendering":
        return RedirectResponse(url=f"/clips/{clip_id}", status_code=HTTP_303_SEE_OTHER)
    if concept is not None and concept not in CONCEPTS:
        raise HTTPException(status_code=400, detail="Unknown concept.")
    # A clip that is, or becomes, a concept clip is cut from per-segment sections made inside the job
    if (concept or clip.get("concept") or "single") == "single" and (clip.get("concept") or "single") == "single" and not _section_file(clip).exists():
        raise HTTPException(
            status_code=HTTP_404_NOT_FOUND,
            detail="Section source file for this clip is missing on disk."
        )

    params = dict(
        start_s=start_s, end_s=end_s, layout=layout, caption_style=caption_style, hook_text=hook_text or "",
        show_hook=show_hook, music_enabled=music_enabled, music_track=music_track, silence_trim=silence_trim,
        silence_trim_s=min(5.0, max(0.5, silence_trim_s)), caption_text=caption_text, layout_changes=layout_changes, letterbox_style=letterbox_style,
        zooms=_json_list(zooms), cuts=_json_list(cuts), sfx=_json_list(sfx),
        concept=concept, segments=_json_list(segments), overlay=_json_dict(overlay), theme=theme,
        concept_source=concept_source if concept_source in ("ai", "user") else None,
    )
    set_clip_render_state(clip_id, "rendering")
    background_tasks.add_task(_rerender_job, clip, params, user["login"])
    return RedirectResponse(url=f"/clips/{clip_id}", status_code=HTTP_303_SEE_OTHER)


@router.post("/clips/{clip_id}/ai-edit")
async def ai_edit_clip_action(
    background_tasks: BackgroundTasks,
    clip_id: int,
    comment: str = Form(...),
    user: Dict[str, Any] = Depends(get_current_user),
):
    """"Ask the editor": Claude proposes new edges, cuts, zooms and a title for a comment, then the clip
    is re-rendered through the same job as the Re-render button. Runs in the background (Claude takes a while)."""
    clip_row = get_clip_with_details(clip_id)
    if not clip_row:
        raise HTTPException(status_code=HTTP_404_NOT_FOUND, detail="Clip not found.")
    clip = dict(clip_row)
    clean = (comment or "").strip()[:1000]
    if not clean:
        raise HTTPException(status_code=400, detail="Write what you want changed.")
    if clip["status"] == "rendering":
        return RedirectResponse(url=f"/clips/{clip_id}", status_code=HTTP_303_SEE_OTHER)
    if not _section_file(clip).exists():
        raise HTTPException(status_code=HTTP_404_NOT_FOUND, detail="Section source file for this clip is missing on disk.")

    params = dict(
        start_s=clip.get("trim_start_s") or clip["orig_start_s"], end_s=clip.get("trim_end_s") or clip["orig_end_s"],
        layout=clip.get("layout") or "split", caption_style=clip.get("caption_style") or "bold_pop",
        hook_text=clip.get("cand_hook") or "", show_hook=clip.get("show_hook") == 1,
        music_enabled=bool(clip.get("music_track")), music_track=clip.get("music_track"),
        silence_trim=clip.get("silence_trim") == 1, silence_trim_s=clip.get("silence_trim_s"), caption_text=None, layout_changes=clip.get("layout_changes") or "",
        letterbox_style=clip.get("letterbox_style") or "blur", zooms=None, cuts=None, sfx=None,
    )
    set_clip_render_state(clip_id, "rendering")
    background_tasks.add_task(
        _rerender_job, clip, params, user["login"],
        lambda p: _ai_edit_prepare(clip, p, clean), lambda exc: _ai_edit_failed(clip, clean, exc),
    )
    return RedirectResponse(url=f"/clips/{clip_id}", status_code=HTTP_303_SEE_OTHER)


def _section_file(clip: Dict[str, Any]) -> Path:
    return VIDEOS_DIR / str(clip["video_id"]) / "sections" / f"section_{clip['candidate_id']}.mp4"


def _json_list(raw: Optional[str]) -> Optional[list]:
    """Form JSON -> list. None (keep the stored value) when the field is absent or not a list."""
    if raw is None or not raw.strip():
        return None
    try:
        value = json.loads(raw)
    except ValueError:
        return None
    return value if isinstance(value, list) else None


def _ai_edit_prepare(clip: Dict[str, Any], p: Dict[str, Any], comment: str) -> Dict[str, Any]:
    """Ask Claude, then turn the answer into render parameters: a single clip's new edges, cuts and zooms, or a concept
    clip's segments and overlay (including a switch of concept, a swapped entry, a new POV caption). Widens a single
    clip's section when the new edges need it. Raises when Claude, the checks or the download fail (the clip keeps its
    old render)."""
    from src.ai_edit import WINDOW_S, run_ai_edit
    from src.concept_build import pov_captions_for, pov_from_range
    from src.db import add_clip_ai_edit, get_connection, update_clip_title
    from src.pipeline.stage8_sections import refetch_section, section_bounds
    from src.pipeline.stage9c_render import default_zooms
    from src.profile import load_context, profile_block, record_feedback, streamer_name
    from src.sfx import clean_sfx

    video_dir = VIDEOS_DIR / str(clip["video_id"])
    sec_file = _section_file(clip)
    meta = json.loads((video_dir / "meta.json").read_text(encoding="utf-8"))
    cur = clip.get("concept") or "single"
    cur_segs = json.loads(clip.get("segments") or "[]") if cur != "single" else []
    cur_overlay = json.loads(clip.get("overlay") or "{}") if cur != "single" else {}
    if cur == "single":
        start, end = p["start_s"], p["end_s"]
        stored_zooms = json.loads(clip["zooms"]) if clip.get("zooms") is not None else default_zooms(sec_file, start, end, clip.get("payoff_t"))
        ranges = None
    else:  # the clip's own clock is the length of the finished video; the stream times are in the segments
        start, end = min(s["start_s"] for s in cur_segs), max(s["end_s"] for s in cur_segs)
        stored_zooms = []
        ranges = [(s["start_s"] - 5, s["end_s"] + 5) for s in cur_segs]
    state = {
        "concept": cur, "start_s": start, "end_s": end, "title": clip.get("cand_title") or "",
        "cuts": json.loads(clip.get("cuts") or "[]") if cur == "single" else [], "zooms": stored_zooms, "layout": p["layout"],
        "segments": cur_segs, "overlay": cur_overlay, "theme": clip.get("theme") or "", "word_ranges": ranges,
        "sfx": clean_sfx(clip.get("sfx"), start, end) if cur == "single" else [],
    }
    ctx = load_context(clip["video_id"], video_dir, meta)
    with get_connection() as conn:
        moments = [dict(id=r["id"], title=r["title"] or "", start_s=r["start_s"], end_s=r["end_s"], score=r["llm_score"], humor=r["humor_type"])
                   for r in conn.execute(
                       "SELECT id, title, start_s, end_s, llm_score, humor_type FROM candidates WHERE video_id = ? "
                       "AND COALESCE(concept, 'single') = 'single' ORDER BY llm_score DESC LIMIT 40", (clip["video_id"],)).fetchall()]
    result = run_ai_edit(
        state, _load_words(video_dir, clip["candidate_id"]), comment, profile_block(ctx), streamer_name(ctx, meta),
        clip["video_id"], None, moments,
    )
    new = result["concept"]
    hook = clip.get("cand_hook") or ""
    if new == "single":
        lo, hi = None, None
        if cur == "single":  # same concept: the section already covers the clip, widen it only if the edges moved out
            lo, hi = section_bounds(sec_file, clip["orig_start_s"], clip["orig_end_s"])
        if lo is None or result["start_s"] < lo or result["end_s"] > hi:
            refetch_section(video_dir, meta, clip["candidate_id"], result["start_s"], result["end_s"])
        overrides = {"start_s": result["start_s"], "end_s": result["end_s"], "cuts": result["remove"], "zooms": result["zooms"],
                     "sfx": result["sfx"], "concept": "single", "segments": [], "overlay": {}, "theme": ""}
    else:
        segs, overlay, theme = result["segments"], dict(result["overlay"]), result["theme"] or (clip.get("theme") or "")
        for k in ("pov_options", "emotion"):
            overlay[k] = cur_overlay.get(k, [] if k == "pov_options" else "")
        if new == "pov":
            first = segs[0]
            moved = cur != "pov" or abs(first["start_s"] - cur_segs[0]["start_s"]) > 1.0 or abs(first["end_s"] - cur_segs[0]["end_s"]) > 1.0
            if moved:  # a new reaction: find its peak, cut the window around it, caption it
                spec = pov_from_range(clip["video_id"], first.get("candidate_id") or clip["candidate_id"], first["start_s"], first["end_s"], result["title"], hook)
                segs, overlay = spec["segments"], spec["overlay"]
            elif result["new_caption"] or not cur_overlay.get("pov_text"):
                cap = pov_captions_for(clip["video_id"], first["start_s"], first["end_s"], result["title"], hook, result["caption_hint"])
                overlay.update(emotion=cap["emotion"], pov_options=cap["options"], pov_text=cap["text"])
            else:
                overlay["pov_text"] = overlay["pov_text"] or cur_overlay.get("pov_text", "")
        else:
            for k in ("skip_card", "callback_quote"):
                overlay[k] = overlay[k] or cur_overlay.get(k, "")
        overrides = {"concept": new, "segments": segs, "overlay": overlay, "theme": theme, "concept_source": "user"}
    add_clip_ai_edit(clip["id"], comment, result, True)
    if result["title"] and result["title"] != state["title"]:
        update_clip_title(clip["id"], result["title"])
    record_feedback(clip.get("source_id"), f"Edit request: {comment}")
    return overrides


def _ai_edit_failed(clip: Dict[str, Any], comment: str, exc: Exception) -> None:
    from src.db import add_clip_ai_edit
    add_clip_ai_edit(clip["id"], comment, {"error": str(exc)[:300]}, False)


def _json_dict(raw: Optional[str]) -> Optional[dict]:
    """Form JSON -> dict. None (keep the stored value) when the field is absent or not an object."""
    if raw is None or not raw.strip():
        return None
    try:
        value = json.loads(raw)
    except ValueError:
        return None
    return value if isinstance(value, dict) else None


def _render_concept_version(clip: Dict[str, Any], p: Dict[str, Any], concept: str, out_file: Path, thumb_file: Path) -> Dict[str, Any]:
    """Render the clip as a story, POV or countdown from its segments (the posted ones, else the stored ones).
    Returns what to save: duration, segments, overlay, theme. Raises ValueError for a bad segment list."""
    from src.concepts import clean_segments, count_problem
    from src.pipeline.concept_render import render_concept_clip

    video_dir = VIDEOS_DIR / str(clip["video_id"])
    segs = clean_segments(p["segments"] if p.get("segments") is not None else json.loads(clip.get("segments") or "[]"))
    problem = count_problem(concept, len(segs))
    if problem:
        raise ValueError(problem)
    overlay = p["overlay"] if p.get("overlay") is not None else json.loads(clip.get("overlay") or "{}")
    theme = p["theme"] if p.get("theme") is not None else (clip.get("theme") or "")
    meta = json.loads((video_dir / "meta.json").read_text(encoding="utf-8"))
    duration = render_concept_clip(
        concept=concept, segs=segs, overlay=overlay, title=clip.get("cand_title") or "",
        hook_text=(p["hook_text"] or clip.get("cand_hook") or "").strip(), video_dir=video_dir, meta=meta,
        cand_id=clip["candidate_id"], all_words=_load_words(video_dir, clip["candidate_id"]), layout=p["layout"],
        caption_style=p["caption_style"], facecam_box=None, profanity_mask=True,
        letterbox_style=p["letterbox_style"] if p["letterbox_style"] in ("title", "blur") else "blur",
        out_file=out_file, thumb_file=thumb_file,
    )
    return {"duration": duration, "segments": segs, "overlay": overlay, "theme": theme}


def _rerender_job(
    clip: Dict[str, Any],
    p: Dict[str, Any],
    user_login: str,
    prepare=None,
    on_error=None,
) -> None:
    """Renders a new version of the clip. Runs in a worker thread after the response is sent, so the user can
    leave the page and the event loop stays free. `prepare(p)` (Ask the editor) may return changed parameters,
    including a new concept with its segments and overlay."""
    from src.edges import clean_cuts, clean_zooms
    from src.pipeline.stage8_sections import refetch_section
    from src.sfx import clean_sfx
    from src.pipeline.stage9c_render import default_zooms, read_section_start

    clip_id, cand_id, video_id = clip["id"], clip["candidate_id"], clip["video_id"]
    video_dir = VIDEOS_DIR / str(video_id)
    renders_dir = video_dir / "renders"
    renders_dir.mkdir(parents=True, exist_ok=True)
    sec_file = _section_file(clip)
    prev_status = clip["status"]
    clip_title = clip.get("cand_title") or f"Clip #{clip_id}"
    new_version = (clip.get("version") or 1) + 1
    new_out_file = renders_dir / f"clip_{cand_id}_v{new_version}.mp4"
    new_thumb_file = renders_dir / f"clip_{cand_id}_v{new_version}_thumb.jpg"
    concept = "single"
    concept_saved: Dict[str, Any] = {}

    try:
        if prepare:
            p = {**p, **prepare(p)}
        concept = p.get("concept") or clip.get("concept") or "single"
        if concept != "single":
            concept_saved = _render_concept_version(clip, p, concept, new_out_file, new_thumb_file)
            ok = True
            start_s, end_s = 0.0, concept_saved["duration"]
            cuts, zooms, switches, chosen_music_str, clean_hook = [], [], [], None, (p["hook_text"] or "").strip()
            sfx = None  # concept clips have no sound effects yet; keep what is stored
            letterbox_style = p["letterbox_style"] if p["letterbox_style"] in ("title", "blur") else "blur"
        else:
            start_s, end_s = p["start_s"], p["end_s"]
            if not sec_file.exists():  # the clip was a concept clip: there is no single section yet, fetch one
                meta = json.loads((video_dir / "meta.json").read_text(encoding="utf-8"))
                refetch_section(video_dir, meta, cand_id, start_s, end_s)
            all_words = _load_words(video_dir, cand_id)
            switches = _parse_layout_changes(p["layout_changes"], start_s, end_s)
            if p["layout"] == "auto":  # the AI re-plans the opening layout and the switches
                from src.layout_ai import plan_layouts
                from src.pipeline.stage9c_render import resolve_layout
                plan = plan_layouts(sec_file, start_s, end_s, read_section_start(sec_file), all_words)
                if plan:
                    p = {**p, "layout": plan[0]["layout"]}
                    switches = plan[1:]
                else:  # no AI: keep the user's switches and use the face-size heuristic for the opening layout
                    p = {**p, "layout": resolve_layout("auto", sec_file, ai=False)[0]}

            # Edited caption text: unchanged words keep their timing, changed spots are re-spread
            # (see _retime_edit). Saved so later re-renders keep the edit.
            caption_text = p.get("caption_text")
            if caption_text is not None:
                new_words = caption_text.split()
                old = [w for w in all_words if _in_window(w, start_s, end_s)]
                if new_words and old and new_words != [w["word"].strip() for w in old]:
                    edited = _retime_edit(old, new_words)
                    all_words = [w for w in all_words if not _in_window(w, start_s, end_s)] + edited
                    all_words.sort(key=lambda w: w.get("start", 0))
                    (renders_dir / f"captions_{cand_id}.json").write_text(json.dumps(all_words), encoding="utf-8")

            chosen_music_str = None
            if p["music_enabled"]:
                from src.music import get_random_track_for_mood
                music_track = p.get("music_track")
                if music_track and music_track.strip() not in ("", "auto"):
                    chosen_music_str = music_track.strip()
                else:
                    track_p = get_random_track_for_mood(clip.get("mood") or "chill")
                    chosen_music_str = str(track_p) if track_p else None

            letterbox_style = p["letterbox_style"] if p["letterbox_style"] in ("title", "blur") else "blur"
            clean_hook = (p["hook_text"] or "").strip()

            # Cuts and zooms: what the page or the editor sent, else what is stored. Zooms are made explicit here
            # (a clip without a list gets the default one) so the page can show and edit them.
            cuts = clean_cuts(p["cuts"] if p.get("cuts") is not None else json.loads(clip.get("cuts") or "[]"), start_s, end_s)
            if p.get("zooms") is not None:
                zooms = clean_zooms(p["zooms"], start_s, end_s)
            elif clip.get("zooms") is not None:
                zooms = clean_zooms(json.loads(clip["zooms"]), start_s, end_s)
            else:
                zooms = default_zooms(sec_file, start_s, end_s, clip.get("payoff_t"))
            sfx = clean_sfx(p["sfx"] if p.get("sfx") is not None else clip.get("sfx"), start_s, end_s)

            ok = render_single_vertical_clip(
                sec_file=sec_file,
                out_file=new_out_file,
                thumb_file=new_thumb_file,
                clip_start=start_s,
                clip_end=end_s,
                layout=p["layout"],
                caption_style=p["caption_style"],
                hook_text=clean_hook if p["show_hook"] else "",
                all_words=all_words,
                music_track=chosen_music_str,
                silence_trim=p["silence_trim"],
                silence_trim_s=p.get("silence_trim_s"),
                layout_changes=switches,
                letterbox_style=letterbox_style,
                title_text=clean_hook or clip.get("cand_title") or "",
                extra_cuts=cuts,
                zooms=zooms,
                payoff_t=clip.get("payoff_t"),
                section_start_s=read_section_start(sec_file),
                sfx=sfx,
            )
    except Exception as exc:
        ok = False
        log_event("error", f"Clip #{clip_id} re-render crashed: {exc}")
        if on_error:
            on_error(exc)

    if not ok:
        set_clip_render_state(clip_id, prev_status)
        log_event("error", f"Clip #{clip_id} re-render failed (requested by {user_login})")
        _push_render_event(user_login, clip_id, clip_title, False)
        return

    from src.concepts import stored_segments
    is_concept = concept != "single"
    create_or_update_clip(
        candidate_id=cand_id,
        file_path=str(new_out_file),
        thumb_path=str(new_thumb_file),
        layout=p["layout"],
        caption_style=p["caption_style"],
        trim_start_s=start_s,
        trim_end_s=end_s,
        music_track=chosen_music_str,
        silence_trim=1 if p["silence_trim"] else 0,
        silence_trim_s=p.get("silence_trim_s"),
        status="ready",
        show_hook=1 if p["show_hook"] and clean_hook and not is_concept else 0,
        letterbox_style=letterbox_style,
        cuts=json.dumps(cuts),
        zooms=json.dumps(zooms),
        concept=concept,
        segments=json.dumps(stored_segments(concept_saved["segments"])) if is_concept else "[]",
        overlay=json.dumps(concept_saved["overlay"]) if is_concept else "{}",
        theme=concept_saved["theme"] if is_concept else "",
        concept_source=p.get("concept_source") or (clip.get("concept_source") or ("user" if p.get("concept") else None)),
        sfx=json.dumps(sfx) if sfx is not None else None,
    )
    set_clip_layout_changes(clip_id, json.dumps(switches) if switches else None)
    # Drop the superseded version so re-renders don't pile up on disk
    for old in (clip.get("file_path"), clip.get("thumb_path")):
        if old and Path(old) not in (new_out_file, new_thumb_file):
            Path(old).unlink(missing_ok=True)
    if clean_hook and clean_hook != (clip.get("cand_hook") or ""):
        update_candidate_hook(cand_id, clean_hook)
    log_event("info", f"Clip #{clip_id} re-rendered (v{new_version}, {concept}, {p['layout']}, {p['caption_style']}) by {user_login}")
    _push_render_event(user_login, clip_id, clip_title, True)
