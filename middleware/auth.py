"""Authentication and authorization helper utilities."""

from __future__ import annotations

import json
import re
from typing import Any, Optional

import models
from fastapi import HTTPException, status

GENERIC_AUTH_FAILURE_MESSAGE = "Unable to sign in with the provided credentials."
GENERIC_AUTH_FAILURE_MESSAGE_AR = "تعذر تسجيل الدخول بالبيانات المدخلة."

USERNAME_PATTERN = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_.-]{2,29}$")
EMAIL_PATTERN = re.compile(r"^[^\s@]+@[^\s@]+\.[^\s@]+$")

PRIVILEGED_ROLES = {models.UserRole.ADMIN, models.UserRole.MANAGER}
SENSITIVE_RESPONSE_KEYS = {
    "password",
    "current_password",
    "new_password",
    "confirm_password",
    "hashed_password",
    "hash",
    "mfa_secret",
    "password_reset_tokens",
    "reset_token",
}


def normalize_phone_number(raw: str) -> Optional[str]:
    """Normalize a Jordanian mobile number to 07XXXXXXXX."""
    if not raw:
        return None
    cleaned = re.sub(r"[\s\-\+]", "", raw)
    if cleaned.startswith("962") and len(cleaned) == 12:
        cleaned = "0" + cleaned[3:]
    elif cleaned.startswith("00962") and len(cleaned) == 14:
        cleaned = "0" + cleaned[5:]
    return cleaned if re.fullmatch(r"07\d{8}", cleaned) else None


def classify_login_identifier(raw: str) -> tuple[str, str]:
    """Return identifier type and normalized value, or raise ValueError."""
    value = str(raw or "").strip()
    if not value:
        raise ValueError("Login identifier is required.")

    normalized_phone = normalize_phone_number(value)
    if normalized_phone:
        return ("phone", normalized_phone)

    if EMAIL_PATTERN.fullmatch(value):
        return ("email", value.lower())

    if USERNAME_PATTERN.fullmatch(value):
        return ("username", value)

    raise ValueError("Login identifier must be a username, phone number, or email address.")


def is_privileged_role(role: Any) -> bool:
    """Return True for roles that must complete MFA."""
    try:
        normalized = role if isinstance(role, models.UserRole) else models.UserRole(str(role))
    except (TypeError, ValueError):
        return False
    return normalized in PRIVILEGED_ROLES


def build_generic_auth_exception(
    *,
    status_code: int = status.HTTP_401_UNAUTHORIZED,
    include_www_authenticate: bool = True,
) -> HTTPException:
    """Return a generic auth error that avoids account enumeration."""
    headers = {"WWW-Authenticate": "Bearer"} if include_www_authenticate else None
    return HTTPException(
        status_code=status_code,
        detail=GENERIC_AUTH_FAILURE_MESSAGE,
        headers=headers,
    )


def sanitize_response_payload(payload: Any) -> Any:
    """Recursively strip sensitive fields from JSON-compatible payloads."""
    if isinstance(payload, dict):
        sanitized: dict[str, Any] = {}
        for key, value in payload.items():
            if key.lower() in SENSITIVE_RESPONSE_KEYS:
                continue
            sanitized[key] = sanitize_response_payload(value)
        return sanitized
    if isinstance(payload, list):
        return [sanitize_response_payload(item) for item in payload]
    return payload


def serialize_safely(payload: Any) -> bytes:
    """Serialize JSON payloads with UTF-8 and without secret fields."""
    return json.dumps(
        sanitize_response_payload(payload),
        ensure_ascii=False,
        separators=(",", ":"),
        default=str,
    ).encode("utf-8")

