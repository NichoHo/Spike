"""
Spike: Web Application (FastAPI + Jinja2 + htmx).
Blueprint §3, §4, §8 (Security T2), §10, §13 (Phase 4).
"""

import uuid
import logging
from pathlib import Path

from fastapi import FastAPI, Request
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from fastapi.responses import HTMLResponse
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.status import HTTP_403_FORBIDDEN, HTTP_404_NOT_FOUND, HTTP_500_INTERNAL_SERVER_ERROR

from src.config import WEB_HOST, WEB_PORT, ROOT_DIR
from src.db import init_db, log_event, reset_stuck_renders
from src.web.filters import register_filters
from src.web.routes.review import router as review_router
from src.web.routes.new import router as new_router
from src.web.routes.sources import router as sources_router
from src.web.routes.jobs import router as jobs_router
from src.web.routes.settings import router as settings_router
from contextlib import asynccontextmanager
from src.web.routes.clips import router as clips_router
from src.web.routes.posts import router as posts_router

logger = logging.getLogger("spike.web")

# Paths
BASE_DIR = Path(__file__).resolve().parent
STATIC_DIR = BASE_DIR / "static"
TEMPLATES_DIR = BASE_DIR / "templates"


from src.music import validate_music_library


@asynccontextmanager
async def lifespan(app: FastAPI):
    init_db()
    if (n := reset_stuck_renders()):
        log_event("warning", f"Reset {n} clip(s) left in 'rendering' by a previous shutdown")
    validate_music_library(enforce=True)
    yield


# FastAPI app (debug=False per Blueprint §8)
app = FastAPI(title="Spike", debug=False, docs_url=None, redoc_url=None, lifespan=lifespan)

# Templates
templates = Jinja2Templates(directory=str(TEMPLATES_DIR))
register_filters(templates.env)
app.state.templates = templates

# Mount static files
app.mount("/static", StaticFiles(directory=str(STATIC_DIR)), name="static")


# ── Security Headers Middleware (Blueprint §8) ────────────────────────────────
class SecurityHeadersMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next):
        response = await call_next(request)
        response.headers["X-Content-Type-Options"] = "nosniff"
        response.headers["Referrer-Policy"] = "same-origin"
        return response


app.add_middleware(SecurityHeadersMiddleware)


# ── Custom Error Handlers (Blueprint §8, DESIGN.md §10.11) ────────────────────
@app.exception_handler(HTTP_403_FORBIDDEN)
async def forbidden_handler(request: Request, exc: Exception):
    detail = getattr(exc, "detail", "Access restricted.")
    return templates.TemplateResponse(
        request=request,
        name="pages/errors/403.html",
        context={"page_title": "Access restricted", "detail": detail},
        status_code=HTTP_403_FORBIDDEN,
    )


@app.exception_handler(HTTP_404_NOT_FOUND)
async def not_found_handler(request: Request, exc: Exception):
    return templates.TemplateResponse(
        request=request,
        name="pages/errors/404.html",
        context={"page_title": "Page not found"},
        status_code=HTTP_404_NOT_FOUND,
    )


@app.exception_handler(Exception)
async def internal_error_handler(request: Request, exc: Exception):
    error_id = str(uuid.uuid4())[:8]
    logger.error(f"[Error ID {error_id}] Unhandled error: {exc}", exc_info=True)
    return templates.TemplateResponse(
        request=request,
        name="pages/errors/500.html",
        context={"page_title": "Something went wrong", "error_id": error_id},
        status_code=HTTP_500_INTERNAL_SERVER_ERROR,
    )


# ── Include Routers ───────────────────────────────────────────────────────────
app.include_router(review_router)
app.include_router(new_router)
app.include_router(sources_router)
app.include_router(jobs_router)
app.include_router(settings_router)
app.include_router(clips_router)
app.include_router(posts_router)


if __name__ == "__main__":
    import uvicorn
    uvicorn.run("src.web.app:app", host=WEB_HOST, port=WEB_PORT, reload=False)
