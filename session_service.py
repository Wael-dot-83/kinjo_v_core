"""Server-side lifecycle for signed access-token sessions.

JWT signatures protect token integrity, but they cannot make a token disappear after
logout or a password change.  This module binds every access-token ``jti`` to a
short-lived server-side record.  Redis is mandatory in production; tests and local
development use a process-local, lock-protected store.
"""

from __future__ import annotations

import hashlib
import json
import logging
import threading
import time
from datetime import datetime, timezone
from typing import Any, Optional

from redis.exceptions import RedisError

from config import settings

logger = logging.getLogger(__name__)

_KEY_PREFIX = "kinjo:auth-session:"
_memory_sessions: dict[str, dict[str, float]] = {}
_memory_lock = threading.RLock()


class SessionStoreUnavailable(RuntimeError):
    """The shared production session store cannot enforce revocation."""


class SessionInvalid(RuntimeError):
    """An access token has no live server-side session binding."""


def _production_store_required() -> bool:
    # TESTING is deliberately allowed to exercise production branches with the
    # deterministic local store.  Application startup separately forbids the
    # unsafe TESTING+production combination outside the test process.
    return settings.ENVIRONMENT.lower() == "production" and not settings.TESTING


def _digest(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def _user_prefix(username: str) -> str:
    return f"{_KEY_PREFIX}{_digest(username)}:"


def _session_key(username: str, jti: str) -> str:
    return f"{_user_prefix(username)}{_digest(jti)}"


def _redis_client():
    # Imported lazily to keep auth module imports free of cache initialization
    # cycles.  CacheService owns the application's shared Redis connection.
    from cache_service import dashboard_cache

    return dashboard_cache.redis_client


def _ttl_seconds(expires_at: float, now: Optional[float] = None) -> int:
    now = time.time() if now is None else now
    remaining = max(0, int(expires_at - now))
    return min(settings.SESSION_TIMEOUT_MINUTES * 60, remaining)


def register_access_session(
    username: str,
    jti: str,
    *,
    issued_at: float,
    expires_at: float,
) -> None:
    """Register a newly issued token before it is returned to a client."""
    if not username or not jti:
        raise SessionInvalid("Access token session identity is incomplete")

    now = time.time()
    ttl = _ttl_seconds(expires_at, now)
    if ttl <= 0:
        # An already-expired JWT is allowed to be encoded for negative tests,
        # but it must never acquire a live server-side session.
        return

    key = _session_key(username, jti)
    record = {
        "issued_at": float(issued_at),
        "absolute_expires_at": float(expires_at),
        "jwt_iat": int(issued_at),
    }
    rc = _redis_client()
    if rc is not None:
        try:
            stored = rc.setex(
                key, ttl, json.dumps(record, separators=(",", ":"))
            )
            if not stored:
                raise SessionStoreUnavailable(
                    "Authentication security store rejected session registration"
                )
            return
        except (RedisError, OSError, TypeError, ValueError) as exc:
            logger.error("Session registration failed in Redis: %s", exc)
            if _production_store_required():
                raise SessionStoreUnavailable(
                    "Authentication security store is unavailable"
                ) from exc

    if _production_store_required():
        raise SessionStoreUnavailable("Authentication security store is unavailable")

    with _memory_lock:
        _memory_sessions[key] = {
            **record,
            "idle_expires_at": now + ttl,
        }


def _decode_record(raw: Any) -> dict[str, float]:
    if isinstance(raw, bytes):
        raw = raw.decode("utf-8")
    record = json.loads(raw) if isinstance(raw, str) else raw
    if not isinstance(record, dict):
        raise ValueError("invalid session record")
    return {
        "issued_at": float(record["issued_at"]),
        "absolute_expires_at": float(record["absolute_expires_at"]),
        "jwt_iat": int(record["jwt_iat"]),
    }


def validate_and_refresh_access_session(
    username: str,
    jti: str,
    *,
    jwt_iat: int,
    jwt_expires_at: float,
    password_changed_at: Optional[datetime],
) -> None:
    """Require an existing binding and slide its inactivity timeout.

    Missing records are always rejected.  They represent an expired, revoked,
    or never-issued token and are never recreated by an authenticated request.
    """
    if not username or not jti:
        raise SessionInvalid("Access token is missing its session identity")

    now = time.time()
    ttl = _ttl_seconds(jwt_expires_at, now)
    if ttl <= 0:
        raise SessionInvalid("Access token session has expired")

    key = _session_key(username, jti)
    record: Optional[dict[str, float]] = None
    rc = _redis_client()
    if rc is not None:
        try:
            # Read-and-touch is one Redis operation, so concurrent requests do
            # not manufacture a fresh session after logout removed the key.
            raw = rc.eval(
                "local value = redis.call('GET', KEYS[1]); "
                "if value then redis.call('EXPIRE', KEYS[1], ARGV[1]); end; "
                "return value",
                1,
                key,
                ttl,
            )
            if raw is not None:
                record = _decode_record(raw)
        except (RedisError, OSError, json.JSONDecodeError, KeyError, TypeError, ValueError) as exc:
            logger.error("Session validation failed in Redis: %s", exc)
            if _production_store_required():
                raise SessionStoreUnavailable(
                    "Authentication security store is unavailable"
                ) from exc

    if record is None and not _production_store_required():
        with _memory_lock:
            candidate = _memory_sessions.get(key)
            if candidate:
                if (
                    candidate["idle_expires_at"] <= now
                    or candidate["absolute_expires_at"] <= now
                ):
                    _memory_sessions.pop(key, None)
                else:
                    candidate["idle_expires_at"] = now + ttl
                    record = dict(candidate)

    if record is None:
        if _production_store_required() and rc is None:
            raise SessionStoreUnavailable("Authentication security store is unavailable")
        raise SessionInvalid("Access token session is expired or revoked")

    if record["jwt_iat"] != int(jwt_iat):
        revoke_access_session(username, jti)
        raise SessionInvalid("Access token session binding does not match")

    # The high-resolution issuance timestamp lives in the trusted server-side
    # record, avoiding JWT iat's one-second precision race at password reset.
    if password_changed_at is not None:
        changed_at = password_changed_at
        if changed_at.tzinfo is None:
            changed_at = changed_at.replace(tzinfo=timezone.utc)
        if record["issued_at"] <= changed_at.timestamp():
            revoke_access_session(username, jti)
            raise SessionInvalid("Access token predates the current password")


def revoke_access_session(username: str, jti: str) -> None:
    """Revoke exactly one independently issued access token."""
    if not username or not jti:
        return
    key = _session_key(username, jti)
    rc = _redis_client()
    if rc is not None:
        try:
            rc.delete(key)
        except (RedisError, OSError, TypeError, ValueError) as exc:
            logger.error("Session revocation failed in Redis: %s", exc)
            if _production_store_required():
                raise SessionStoreUnavailable(
                    "Authentication security store is unavailable"
                ) from exc
    elif _production_store_required():
        raise SessionStoreUnavailable("Authentication security store is unavailable")

    with _memory_lock:
        _memory_sessions.pop(key, None)


def revoke_all_user_sessions(username: str) -> None:
    """Revoke every issued access token for an account after credential change."""
    prefix = _user_prefix(username)
    rc = _redis_client()
    if rc is not None:
        try:
            keys = list(rc.scan_iter(match=f"{prefix}*", count=100))
            if keys:
                rc.delete(*keys)
        except (RedisError, OSError, TypeError, ValueError) as exc:
            logger.error("Account session revocation failed in Redis: %s", exc)
            if _production_store_required():
                raise SessionStoreUnavailable(
                    "Authentication security store is unavailable"
                ) from exc
    elif _production_store_required():
        raise SessionStoreUnavailable("Authentication security store is unavailable")

    with _memory_lock:
        for key in [candidate for candidate in _memory_sessions if candidate.startswith(prefix)]:
            _memory_sessions.pop(key, None)


def clear_local_sessions() -> None:
    """Clear only the non-production store (test isolation helper)."""
    with _memory_lock:
        _memory_sessions.clear()
