"""
Spike: Authentication middleware and dependency injection.
Blueprint §4 (Auth) & Blueprint §8 (Security T2).
Supports Tailscale Serve identity headers with local development fallback.
"""

from typing import Optional, Dict, Any
from fastapi import Request, HTTPException, Depends
from starlette.status import HTTP_403_FORBIDDEN

from src.db import get_user_by_login, get_user_by_id, list_users


def get_current_user(request: Request) -> Dict[str, Any]:
    """
    Authenticate user from Tailscale Serve headers or fallback to local admin.
    Returns user dict or raises HTTPException(403).
    """
    # 1. Check Tailscale Serve proxy headers
    ts_login = request.headers.get("Tailscale-User-Login")
    ts_name = request.headers.get("Tailscale-User-Name")

    if ts_login:
        login = ts_login.strip().lower()
        user_row = get_user_by_login(login)
        if not user_row:
            raise HTTPException(
                status_code=HTTP_403_FORBIDDEN,
                detail=f"Access denied. User '{login}' is on the tailnet but not authorized in Spike."
            )
        user = dict(user_row)
        if not user.get("active"):
            raise HTTPException(
                status_code=HTTP_403_FORBIDDEN,
                detail="Your account has been deactivated. Please contact an administrator."
            )
        return user

    # 2. Local development fallback (no Tailscale header present)
    # Allows local testing on 127.0.0.1
    admin_row = get_user_by_login("admin@local")
    if admin_row and admin_row["active"]:
        return dict(admin_row)

    # Fallback to first active user if admin@local was altered
    all_users = list_users()
    for u in all_users:
        if u["active"]:
            return dict(u)

    raise HTTPException(
        status_code=HTTP_403_FORBIDDEN,
        detail="No active user accounts found."
    )


def require_admin(user: Dict[str, Any] = Depends(get_current_user)) -> Dict[str, Any]:
    """Ensure current authenticated user has the 'admin' role."""
    if user.get("role") != "admin":
        raise HTTPException(
            status_code=HTTP_403_FORBIDDEN,
            detail="Admin permissions required to access this resource."
        )
    return user
