from __future__ import annotations

import base64
from hashlib import sha256
from typing import Any

from cryptography.fernet import Fernet, InvalidToken
from fastapi import Request
from itsdangerous import BadSignature
from itsdangerous import URLSafeSerializer

from reviewpilot.config import get_settings


SESSION_COOKIE_NAME = "reviewpilot_session"
OAUTH_STATE_COOKIE_NAME = "reviewpilot_oauth_state"
GITHUB_TOKEN_FIELD = "github_access_token"


def get_session_serializer() -> URLSafeSerializer:
    settings = get_settings()
    return URLSafeSerializer(settings.app_secret_key, salt="reviewpilot-session")


def dump_session(data: dict[str, Any]) -> str:
    return get_session_serializer().dumps(data)


def load_session(value: str | None) -> dict[str, Any]:
    if not value:
        return {}
    try:
        data = get_session_serializer().loads(value)
    except BadSignature:
        return {}
    return data if isinstance(data, dict) else {}


def encrypt_session_value(value: str) -> str:
    return _fernet().encrypt(value.encode("utf-8")).decode("ascii")


def decrypt_session_value(value: str | None) -> str | None:
    if not value:
        return None
    try:
        return _fernet().decrypt(value.encode("ascii")).decode("utf-8")
    except (InvalidToken, UnicodeDecodeError):
        return None


def build_github_session(
    access_token: str,
    *,
    scope: str = "",
    token_type: str = "bearer",
) -> str:
    return dump_session(
        {
            GITHUB_TOKEN_FIELD: encrypt_session_value(access_token),
            "github_scope": scope,
            "github_token_type": token_type,
        }
    )


def get_github_token_from_request(request: Request) -> str | None:
    session = load_session(request.cookies.get(SESSION_COOKIE_NAME))
    return decrypt_session_value(session.get(GITHUB_TOKEN_FIELD))


def _fernet() -> Fernet:
    settings = get_settings()
    key = base64.urlsafe_b64encode(sha256(settings.app_secret_key.encode("utf-8")).digest())
    return Fernet(key)
