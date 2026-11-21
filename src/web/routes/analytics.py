"""Analytics tab: stats per Short, linked to the clip that made it (docs/superpowers/specs/2026-11-21-clip-analytics-design.md)."""

from typing import Any, Dict

from fastapi import APIRouter, BackgroundTasks, Depends, Form, Request
from fastapi.responses import HTMLResponse, RedirectResponse
from starlette.status import HTTP_303_SEE_OTHER

from src import analytics
from src.db import get_connection, get_setting, list_accounts
from src.web.auth import get_current_user, require_admin

router = APIRouter()

SORTS = {"title": "title", "published": "published_at", "age": "age", "voice": "voice", "frame": "frame", "views": "views_7d",
         "multiple": "multiple", "stayed": "stayed", "pct": "avg_view_pct", "drop": "drop", "link": "link_state"}
GROUPS = {"voice": "Hook voice", "frame": "Frame", "layout": "Layout", "band": "Score band", "first_word": "First word",
          "loops": "Loops", "hook_card": "Hook card"}


def _value(r: Dict[str, Any], col: str):
    v = r.get(col)
    v = v["at_s"] if isinstance(v, dict) else v
    return v if isinstance(v, (int, float)) else (str(v).lower() if v else None)


@router.get("/analytics", response_class=HTMLResponse)
async def analytics_page(request: Request, sort: str = "published", desc: int = 1, group: str = "",
                         user: Dict[str, Any] = Depends(get_current_user)):
    rows = analytics.shorts_table()
    col = SORTS.get(sort, "published_at")
    have = sorted((r for r in rows if _value(r, col) is not None), key=lambda r: _value(r, col), reverse=bool(desc))
    rows = have + [r for r in rows if _value(r, col) is None]  # blanks last either way
    with get_connection() as conn:
        clips = [dict(r) for r in conn.execute(
            "SELECT cand.id, cand.title FROM candidates cand JOIN clips c ON c.candidate_id = cand.id "
            "WHERE cand.title IS NOT NULL GROUP BY cand.id ORDER BY MAX(c.created_at) DESC LIMIT 300")]
    accounts = [a for a in list_accounts() if a["platform"] == "youtube"]
    notices = [(a["display_name"], m) for a in accounts if (m := get_setting(f"analytics_status:{a['id']}"))]
    return request.app.state.templates.TemplateResponse(request=request, name="pages/analytics.html", context={
        "page_title": "Analytics", "active_nav": "analytics", "user": user, "rows": rows, "clips": clips, "notices": notices,
        "sort": sort, "desc": desc, "group": group if group in GROUPS else "", "groups": GROUPS,
        "group_rows": analytics.group_table(rows, group) if group in GROUPS else [],
        "has_account": bool(accounts), "last_run": get_setting("analytics_last_run")})


@router.post("/analytics/{published_id}/link")
async def link_short(published_id: int, candidate_id: int = Form(...), user: Dict[str, Any] = Depends(get_current_user)):
    analytics.link(published_id, candidate_id)
    return RedirectResponse("/analytics", status_code=HTTP_303_SEE_OTHER)


@router.post("/analytics/pull")
async def pull_now(tasks: BackgroundTasks, user: Dict[str, Any] = Depends(require_admin)):
    tasks.add_task(analytics.run_daily, True)
    return RedirectResponse("/analytics", status_code=HTTP_303_SEE_OTHER)
