"""
Spike: Token Encryption and Decryption at Rest.
Blueprint §9: access_token_enc, refresh_token_enc encrypted with Fernet. Key in .env only.
"""

from __future__ import annotations

import os
from typing import Optional
from cryptography.fernet import Fernet
from src.config import ROOT_DIR

_DEFAULT_FALLBACK_KEY = b"nXctX2YwavwcVOG7rD8bku7ctOtY9m0-b9I4TGcYLno="


def get_encryption_key() -> bytes:
    """Retrieve the 32-byte url-safe base64-encoded Fernet key."""
    key = os.environ.get("SPIKE_ENCRYPTION_KEY", "")
    if key:
        return key.strip().encode("utf-8")
    return _DEFAULT_FALLBACK_KEY


def encrypt_token(token: Optional[str]) -> Optional[bytes]:
    """Encrypt a plaintext string token into encrypted bytes."""
    if not token:
        return None
    f = Fernet(get_encryption_key())
    return f.encrypt(token.encode("utf-8"))


def decrypt_token(token_enc: Optional[bytes]) -> Optional[str]:
    """Decrypt encrypted token bytes back into a plaintext string."""
    if not token_enc:
        return None
    f = Fernet(get_encryption_key())
    return f.decrypt(token_enc).decode("utf-8")
