"""Encrypt/decrypt sensitive integration tokens at rest."""

from __future__ import annotations

import base64
import hashlib

from cryptography.fernet import Fernet, InvalidToken
from flask import current_app


def _fernet() -> Fernet:
    # Derive a stable Fernet key from SECRET_KEY so tokens survive restarts (same SECRET_KEY).
    secret = (current_app.config.get("SECRET_KEY") or "dev-secret").encode("utf-8")
    digest = hashlib.sha256(secret).digest()
    key = base64.urlsafe_b64encode(digest)
    return Fernet(key)


def encrypt_secret(value: str | None) -> str | None:
    if not value or not str(value).strip():
        return None
    return _fernet().encrypt(str(value).strip().encode("utf-8")).decode("ascii")


def decrypt_secret(value: str | None) -> str | None:
    if not value:
        return None
    try:
        return _fernet().decrypt(value.encode("ascii")).decode("utf-8")
    except (InvalidToken, ValueError, TypeError):
        return None
