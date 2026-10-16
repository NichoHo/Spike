"""
Google OAuth, Gmail and Drive for Outreach (OUTREACH.md §6.3, §6.7).

Scopes are the smallest that do the job:
- gmail.send: send first emails and follow-ups.
- gmail.metadata: read headers of our own threads to detect replies, bounces and auto-replies (no bodies).
- drive.file: only files this app created (the trial clips it shares).
- openid email: learn which address we send from.
The refresh token is Fernet-encrypted in outreach.db. Only the web app's admin route can connect.
"""

import base64
import hashlib
import json
import secrets
import time
import urllib.error
import urllib.parse
import urllib.request
from email.message import EmailMessage
from email.utils import formataddr
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

from src import config
from src.outreach import db

SCOPES = (
    "openid",
    "email",
    "https://www.googleapis.com/auth/gmail.send",
    "https://www.googleapis.com/auth/gmail.metadata",
    "https://www.googleapis.com/auth/drive.file",
)
AUTH_URL = "https://accounts.google.com/o/oauth2/v2/auth"
TOKEN_URL = "https://oauth2.googleapis.com/token"
USERINFO_URL = "https://openidconnect.googleapis.com/v1/userinfo"
GMAIL = "https://gmail.googleapis.com/gmail/v1/users/me"
DRIVE = "https://www.googleapis.com/drive/v3"
DRIVE_UPLOAD = "https://www.googleapis.com/upload/drive/v3"


class GoogleError(RuntimeError):
    def __init__(self, message: str, status: int = 0):
        super().__init__(message)
        self.status = status


class GoogleAuthError(GoogleError):
    """No account connected, or the refresh token was revoked or expired. A person must reconnect."""


def redirect_uri() -> str:
    return f"{config.PUBLIC_URL}/outreach/google/callback"


def oauth_configured() -> bool:
    return bool(config.GOOGLE_OAUTH_CLIENT_ID and config.GOOGLE_OAUTH_CLIENT_SECRET)


def encryption_key_set() -> bool:
    """security.py falls back to a key that is in the repo; a Gmail token must never be stored under it."""
    import os
    return bool(os.environ.get("SPIKE_ENCRYPTION_KEY", "").strip())


# ── HTTP ──────────────────────────────────────────────────────────────────────

def _http(method: str, url: str, token: Optional[str] = None, json_body: Any = None, data: Any = None,
          headers: Optional[Dict[str, str]] = None, timeout: float = 30) -> Tuple[int, Dict[str, str], Any]:
    """One request. Returns (status, headers, parsed JSON or None). Raises GoogleError on 4xx/5xx."""
    hdrs = {"User-Agent": "Spike-Outreach/1.0", **(headers or {})}
    if token:
        hdrs["Authorization"] = f"Bearer {token}"
    if json_body is not None:
        data = json.dumps(json_body).encode("utf-8")
        hdrs["Content-Type"] = "application/json; charset=UTF-8"
    req = urllib.request.Request(url, data=data, headers=hdrs, method=method)
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            raw = resp.read()
            return resp.status, dict(resp.headers), (json.loads(raw) if raw else None)
    except urllib.error.HTTPError as e:
        body = e.read().decode("utf-8", errors="replace")
        try:
            err = json.loads(body)
        except ValueError:
            err = {}
        e_obj = err.get("error") if isinstance(err, dict) else None
        if isinstance(e_obj, dict):  # Google APIs: {"error": {"message": ...}}
            msg = e_obj.get("message", "")
        else:  # OAuth endpoints: {"error": "invalid_grant", "error_description": ...}
            msg = err.get("error_description") or e_obj or body[:200]
        raise GoogleError(f"HTTP {e.code} from {urllib.parse.urlsplit(url).netloc}: {msg}", e.code) from None


# ── OAuth (authorization code + PKCE) ─────────────────────────────────────────

# state -> (code_verifier, user_id, expires_at). In memory: the web app is one process and a login takes minutes.
_pending: Dict[str, Tuple[str, Optional[int], float]] = {}


def start_auth(user_id: Optional[int]) -> str:
    """URL that sends the admin to Google's consent screen."""
    now = time.time()
    for k in [k for k, v in _pending.items() if v[2] < now]:
        del _pending[k]
    state = secrets.token_urlsafe(24)
    verifier = secrets.token_urlsafe(64)
    _pending[state] = (verifier, user_id, now + 600)
    challenge = base64.urlsafe_b64encode(hashlib.sha256(verifier.encode()).digest()).rstrip(b"=").decode()
    params = {
        "client_id": config.GOOGLE_OAUTH_CLIENT_ID,
        "redirect_uri": redirect_uri(),
        "response_type": "code",
        "scope": " ".join(SCOPES),
        "access_type": "offline",
        "prompt": "consent",  # always return a refresh token, also on reconnect
        "state": state,
        "code_challenge": challenge,
        "code_challenge_method": "S256",
    }
    return f"{AUTH_URL}?{urllib.parse.urlencode(params)}"


def finish_auth(state: str, code: str) -> str:
    """Exchange the code, store the encrypted refresh token. Returns the connected address."""
    from src.security import encrypt_token
    entry = _pending.pop(state, None)
    if not entry or entry[2] < time.time():
        raise GoogleAuthError("The sign-in link expired or was already used. Start again.")
    verifier, user_id, _ = entry
    _, _, tok = _http("POST", TOKEN_URL, data=urllib.parse.urlencode({
        "code": code,
        "client_id": config.GOOGLE_OAUTH_CLIENT_ID,
        "client_secret": config.GOOGLE_OAUTH_CLIENT_SECRET,
        "redirect_uri": redirect_uri(),
        "grant_type": "authorization_code",
        "code_verifier": verifier,
    }).encode(), headers={"Content-Type": "application/x-www-form-urlencoded"})
    granted = set((tok.get("scope") or "").split())
    missing = [s for s in SCOPES[2:] if s not in granted]
    if missing:
        raise GoogleAuthError("Google did not grant: " + ", ".join(s.rsplit("/", 1)[-1] for s in missing)
                              + ". Tick every box on the consent screen.")
    if not tok.get("refresh_token"):
        raise GoogleAuthError("Google returned no refresh token. Remove Spike's access in your Google account and connect again.")
    _, _, info = _http("GET", USERINFO_URL, token=tok["access_token"])
    email = (info or {}).get("email", "")
    db.save_google_account(email, encrypt_token(tok["refresh_token"]), tok.get("scope", ""), user_id)
    _cache.update(token=tok["access_token"], expires=time.time() + int(tok.get("expires_in", 3600)) - 60)
    return email


_cache: Dict[str, Any] = {"token": "", "expires": 0.0}


def access_token() -> str:
    """A valid access token, refreshed when needed."""
    if _cache["token"] and _cache["expires"] > time.time():
        return _cache["token"]
    from src.security import decrypt_token
    acc = db.get_google_account()
    if not acc or not acc.get("refresh_token_enc"):
        raise GoogleAuthError("No Google account connected.")
    try:
        _, _, tok = _http("POST", TOKEN_URL, data=urllib.parse.urlencode({
            "client_id": config.GOOGLE_OAUTH_CLIENT_ID,
            "client_secret": config.GOOGLE_OAUTH_CLIENT_SECRET,
            "refresh_token": decrypt_token(acc["refresh_token_enc"]),
            "grant_type": "refresh_token",
        }).encode(), headers={"Content-Type": "application/x-www-form-urlencoded"})
    except GoogleError as e:
        if e.status in (400, 401):  # invalid_grant: revoked, or 7-day expiry while the OAuth app is in Testing
            db.set_google_error("Google access expired or was revoked. Reconnect the account.")
            raise GoogleAuthError(str(e), e.status) from None
        raise
    _cache.update(token=tok["access_token"], expires=time.time() + int(tok.get("expires_in", 3600)) - 60)
    return _cache["token"]


def revoke() -> None:
    from src.security import decrypt_token
    acc = db.get_google_account()
    if acc and acc.get("refresh_token_enc"):
        try:
            _http("POST", "https://oauth2.googleapis.com/revoke",
                  data=urllib.parse.urlencode({"token": decrypt_token(acc["refresh_token_enc"])}).encode(),
                  headers={"Content-Type": "application/x-www-form-urlencoded"})
        except GoogleError:
            pass  # already revoked; delete locally anyway
    db.delete_google_account()
    _cache.update(token="", expires=0.0)


# ── Gmail ─────────────────────────────────────────────────────────────────────

def build_mime(sender_email: str, sender_name: str, to: str, subject: str, body: str,
               in_reply_to: Optional[str] = None) -> str:
    """RFC 2822 message as base64url, the shape users.messages.send wants."""
    msg = EmailMessage()
    msg["From"] = formataddr((sender_name, sender_email)) if sender_name else sender_email
    msg["To"] = to
    msg["Subject"] = subject
    if in_reply_to:  # keeps follow-ups in the same thread for the recipient
        msg["In-Reply-To"] = in_reply_to
        msg["References"] = in_reply_to
    msg["List-Unsubscribe"] = f"<mailto:{sender_email}?subject=unsubscribe>"
    msg.set_content(body)
    return base64.urlsafe_b64encode(msg.as_bytes()).decode("ascii")


def send_email(to: str, subject: str, body: str, sender_name: str,
               thread_id: Optional[str] = None, in_reply_to: Optional[str] = None) -> Dict[str, str]:
    """Send one plain-text email. Returns {id, thread_id, rfc_message_id}."""
    acc = db.get_google_account() or {}
    raw = build_mime(acc.get("email", ""), sender_name, to, subject, body, in_reply_to)
    payload: Dict[str, Any] = {"raw": raw}
    if thread_id:
        payload["threadId"] = thread_id
    token = access_token()
    _, _, sent = _http("POST", f"{GMAIL}/messages/send", token=token, json_body=payload)
    rfc_id = ""
    try:  # the Message-ID header is what follow-ups reply to
        _, _, meta = _http("GET", f"{GMAIL}/messages/{sent['id']}?format=metadata&metadataHeaders=Message-ID", token=token)
        rfc_id = next((h["value"] for h in meta.get("payload", {}).get("headers", []) if h["name"].lower() == "message-id"), "")
    except GoogleError:
        pass
    return {"id": sent["id"], "thread_id": sent.get("threadId", ""), "rfc_message_id": rfc_id}


def thread_inbound(thread_id: str) -> List[Dict[str, Any]]:
    """Messages in a thread that we did not send: [{at_ms, from, snippet, auto, bounce}]."""
    headers = ("From", "Auto-Submitted", "X-Autoreply", "X-Autorespond", "Precedence", "Subject")
    query = "format=metadata&" + "&".join(f"metadataHeaders={h}" for h in headers)
    _, _, th = _http("GET", f"{GMAIL}/threads/{thread_id}?{query}", token=access_token())
    out = []
    for m in (th or {}).get("messages", []):
        if "SENT" in m.get("labelIds", []):
            continue
        h = {x["name"].lower(): x["value"] for x in m.get("payload", {}).get("headers", [])}
        sender = h.get("from", "").lower()
        auto = (h.get("auto-submitted", "no").lower() != "no" or "x-autoreply" in h or "x-autorespond" in h
                or h.get("precedence", "").lower() in ("auto_reply", "bulk", "junk"))
        out.append({
            "at_ms": int(m.get("internalDate", 0)),
            "from": h.get("from", ""),
            "snippet": m.get("snippet", ""),
            "auto": auto,
            "bounce": "mailer-daemon" in sender or "postmaster" in sender,
        })
    return out


# ── Drive ─────────────────────────────────────────────────────────────────────

def upload_shared_file(path: Path, name: str) -> Dict[str, str]:
    """Upload a clip and share it as 'anyone with the link can view'. Returns {id, url}."""
    token = access_token()
    size = path.stat().st_size
    _, hdrs, _ = _http(
        "POST", f"{DRIVE_UPLOAD}/files?uploadType=resumable&fields=id,webViewLink", token=token,
        json_body={"name": name, "mimeType": "video/mp4"},
        headers={"X-Upload-Content-Type": "video/mp4", "X-Upload-Content-Length": str(size)},
    )
    location = next((v for k, v in hdrs.items() if k.lower() == "location"), None)
    if not location:
        raise GoogleError("Drive did not return an upload URL")
    with open(path, "rb") as f:  # http.client streams a file object in blocks when Content-Length is set
        _, _, file_meta = _http("PUT", location, data=f, headers={"Content-Type": "video/mp4", "Content-Length": str(size)},
                                timeout=600)
    file_id = file_meta["id"]
    try:
        _http("POST", f"{DRIVE}/files/{file_id}/permissions", token=token, json_body={"role": "reader", "type": "anyone"})
    except GoogleError:
        delete_file(file_id)  # never leave a private upload behind that the email cannot link to
        raise
    return {"id": file_id, "url": file_meta.get("webViewLink") or f"https://drive.google.com/file/d/{file_id}/view"}


def delete_file(file_id: str) -> None:
    try:
        _http("DELETE", f"{DRIVE}/files/{file_id}", token=access_token())
    except GoogleError as e:
        if e.status != 404:
            raise
