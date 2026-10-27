"""
Sign-in (OAuth) for the accounts Spike posts clips to: YouTube Shorts, TikTok, Instagram Reels.

Each sign-in stores a refresh token (Instagram: a 60-day token that is itself refreshed), so posting keeps
working after the first short-lived access token expires. One platform can have many accounts: signing in
again as an account that is already connected only refreshes its tokens.
Redirect URI to register in each developer app: <SPIKE_PUBLIC_URL>/accounts/<platform>/callback
"""

import base64
import hashlib
import secrets
import time
import urllib.parse
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, List, Optional, Tuple

from src import config
from src.db import save_connected_account, update_account_tokens
from src.outreach.google import GoogleError as PlatformError, _http  # one urllib wrapper for every OAuth API

PLATFORMS: Dict[str, Dict[str, Any]] = {
    "youtube": {
        "label": "YouTube Shorts",
        "env": ("YOUTUBE_UPLOAD_CLIENT_ID", "YOUTUBE_UPLOAD_CLIENT_SECRET"),
        "auth_url": "https://accounts.google.com/o/oauth2/v2/auth",
        "token_url": "https://oauth2.googleapis.com/token",
        # readonly only to read the channel name after sign-in
        "scope": "https://www.googleapis.com/auth/youtube.upload https://www.googleapis.com/auth/youtube.readonly",
    },
    "tiktok": {
        "label": "TikTok",
        "env": ("TIKTOK_CLIENT_KEY", "TIKTOK_CLIENT_SECRET"),
        "auth_url": "https://www.tiktok.com/v2/auth/authorize/",
        "token_url": "https://open.tiktokapis.com/v2/oauth/token/",
        "scope": "user.info.basic,video.upload",
    },
    "instagram": {
        "label": "Instagram Reels",
        "env": ("INSTAGRAM_APP_ID", "INSTAGRAM_APP_SECRET"),
        "auth_url": "https://www.instagram.com/oauth/authorize",
        "token_url": "https://api.instagram.com/oauth/access_token",
        "scope": "instagram_business_basic,instagram_business_content_publish",
    },
}
IG_API = "https://graph.instagram.com/v21.0"
FORM = {"Content-Type": "application/x-www-form-urlencoded"}


def _client(platform: str) -> Tuple[str, str]:
    cid, secret = PLATFORMS[platform]["env"]
    return getattr(config, cid), getattr(config, secret)


def configured(platform: str) -> bool:
    return all(_client(platform))


def redirect_uri(platform: str) -> str:
    return f"{config.PUBLIC_URL}/accounts/{platform}/callback"


def connect_options() -> List[Dict[str, Any]]:
    """What the Settings connect dialog shows for each platform."""
    return [{"key": p, "label": v["label"], "configured": configured(p), "env": v["env"], "redirect_uri": redirect_uri(p)}
            for p, v in PLATFORMS.items()]


# ── Sign-in ───────────────────────────────────────────────────────────────────

# state -> (platform, code_verifier, user_id, expires_at). In memory: the web app is one process and a sign-in takes minutes.
_pending: Dict[str, Tuple[str, str, Optional[int], float]] = {}


def start_auth(platform: str, user_id: Optional[int]) -> str:
    """URL that sends the admin to the platform's consent screen."""
    now = time.time()
    for k in [k for k, v in _pending.items() if v[3] < now]:
        del _pending[k]
    state = secrets.token_urlsafe(24)
    verifier = secrets.token_urlsafe(64)
    _pending[state] = (platform, verifier, user_id, now + 600)
    cid, _ = _client(platform)
    p = PLATFORMS[platform]
    params = {"redirect_uri": redirect_uri(platform), "response_type": "code", "scope": p["scope"], "state": state}
    params["client_key" if platform == "tiktok" else "client_id"] = cid
    if platform == "youtube":
        challenge = base64.urlsafe_b64encode(hashlib.sha256(verifier.encode()).digest()).rstrip(b"=").decode()
        params.update(access_type="offline", prompt="consent", code_challenge=challenge, code_challenge_method="S256")
    return f"{p['auth_url']}?{urllib.parse.urlencode(params)}"


def _token(platform: str, fields: Dict[str, str]) -> Dict[str, Any]:
    cid, secret = _client(platform)
    body = {"client_key" if platform == "tiktok" else "client_id": cid, "client_secret": secret, **fields}
    _, _, tok = _http("POST", PLATFORMS[platform]["token_url"], data=urllib.parse.urlencode(body).encode(), headers=FORM)
    if not (tok or {}).get("access_token"):  # TikTok reports some errors with HTTP 200
        raise PlatformError(f"{PLATFORMS[platform]['label']} sign-in failed: "
                            f"{(tok or {}).get('error_description') or (tok or {}).get('error') or 'no access token'}", 400)
    return tok


def _expires(seconds: Any) -> str:
    return (datetime.now(timezone.utc) + timedelta(seconds=int(seconds or 3600))).isoformat()


def finish_auth(platform: str, state: str, code: str) -> str:
    """Exchange the code, save the account (tokens encrypted). Returns the account's display name."""
    entry = _pending.pop(state, None)
    if not entry or entry[0] != platform or entry[3] < time.time():
        raise PlatformError("The sign-in link expired or was already used. Start again.")
    _, verifier, user_id, _ = entry
    fields = {"grant_type": "authorization_code", "code": code.removesuffix("#_"), "redirect_uri": redirect_uri(platform)}
    if platform == "youtube":
        fields["code_verifier"] = verifier
    tok = _token(platform, fields)
    access, refresh, expires = tok["access_token"], tok.get("refresh_token"), _expires(tok.get("expires_in"))

    if platform == "youtube":
        if not refresh:
            raise PlatformError("Google returned no refresh token. Remove Spike's access in your Google account and connect again.")
        _, _, res = _http("GET", "https://www.googleapis.com/youtube/v3/channels?part=snippet&mine=true", token=access)
        items = (res or {}).get("items") or []
        if not items:
            raise PlatformError("This Google account has no YouTube channel. Pick the channel's account on the consent screen.")
        uid, name = items[0]["id"], items[0]["snippet"]["title"]
    elif platform == "tiktok":
        _, _, res = _http("GET", "https://open.tiktokapis.com/v2/user/info/?fields=open_id,display_name", token=access)
        user = (res or {}).get("data", {}).get("user", {})
        uid, name = tok.get("open_id") or user.get("open_id", ""), user.get("display_name") or "TikTok account"
    else:
        # The code gives a 1-hour token; swap it for the 60-day one
        _, secret = _client(platform)
        _, _, long = _http("GET", "https://graph.instagram.com/access_token?" + urllib.parse.urlencode(
            {"grant_type": "ig_exchange_token", "client_secret": secret, "access_token": access}))
        access, expires = long["access_token"], _expires(long.get("expires_in"))
        _, _, me = _http("GET", f"{IG_API}/me?fields=user_id,username", token=access)
        uid, name = str(me.get("user_id") or me.get("id") or tok.get("user_id")), "@" + me.get("username", "instagram")

    save_connected_account(platform, uid, name, access, refresh, expires, user_id)
    return name


# ── Tokens at post time ───────────────────────────────────────────────────────

# Refresh this long before expiry. Instagram's token can only be refreshed while still valid, so it renews a month early.
_MARGIN = {"instagram": timedelta(days=30)}


def fresh_token(account: Dict[str, Any]) -> str:
    """A valid access token for a decrypted account row, refreshed and saved when close to expiry."""
    platform, access = account["platform"], account.get("access_token")
    if not access:
        raise PlatformError("Account is not authenticated. Reconnect it in Settings.")
    if not account.get("expires_at"):  # added without sign-in (tests, mock tokens)
        return access
    left = datetime.fromisoformat(account["expires_at"]) - datetime.now(timezone.utc)
    if left > _MARGIN.get(platform, timedelta(minutes=5)):
        return access
    try:
        if platform == "instagram":
            _, _, tok = _http("GET", "https://graph.instagram.com/refresh_access_token?" + urllib.parse.urlencode(
                {"grant_type": "ig_refresh_token", "access_token": access}))
        else:
            if not account.get("refresh_token"):
                raise PlatformError("No refresh token saved.", 400)
            tok = _token(platform, {"grant_type": "refresh_token", "refresh_token": account["refresh_token"]})
    except PlatformError as e:
        if e.status in (400, 401):  # revoked, expired, or Google's 7-day limit while the OAuth app is in Testing
            raise PlatformError(f"{PLATFORMS[platform]['label']} sign-in for {account.get('display_name')} expired "
                                f"or was revoked. Reconnect it in Settings. ({e})", e.status) from None
        raise
    update_account_tokens(account["id"], tok["access_token"], tok.get("refresh_token"), _expires(tok.get("expires_in")))
    return tok["access_token"]
