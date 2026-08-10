"""Request timeout, security headers, audit, and JSON sanitization middleware."""

from __future__ import annotations

import asyncio
import json
import logging
from typing import Callable, Optional

from fastapi import Request
from fastapi.responses import JSONResponse, Response
from jose import JWTError, jwt
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session
from starlette.concurrency import iterate_in_threadpool

import models
import validators
from config import settings
from database import SessionLocal
from middleware.auth import sanitize_response_payload

logger = logging.getLogger(__name__)

STATE_CHANGING_METHODS = {"POST", "PUT", "PATCH", "DELETE"}
AUDIT_EXCLUDED_PATHS = {
    "/api/auth/logout",
}


_GMAPS_CONNECT = [
    "'self'",
    "http://localhost:8000",
    "http://127.0.0.1:8000",
    "ws://localhost:8000",
    "ws://127.0.0.1:8000",
    "https://cdn.jsdelivr.net",
    "https://cdnjs.cloudflare.com",
    # Google Maps APIs — tile downloads, geocoding, and places calls
    "https://maps.googleapis.com",
    "https://*.googleapis.com",
    "https://*.gstatic.com",
    "https://cloudflareinsights.com",
]

_BASE_CONNECT = [
    "'self'",
    "http://localhost:8000",
    "http://127.0.0.1:8000",
    "ws://localhost:8000",
    "ws://127.0.0.1:8000",
    "https://cdn.jsdelivr.net",
    "https://cdnjs.cloudflare.com",
    # Cloudflare Web Analytics beacon posts its RUM payload here. Without it the
    # beacon is injected by the edge on every response and then blocked by CSP.
    "https://cloudflareinsights.com",
]

# Cloudflare injects this script into every response when Web Analytics is on.
# It is edge-injected, so the app cannot opt out per-page — it must be allowed
# or every single page load reports a CSP violation.
_CF_INSIGHTS_SCRIPT = "https://static.cloudflareinsights.com"


def _security_csp(heatmap: bool = False) -> str:
    script_src = (
        "script-src 'self' 'unsafe-inline' "
        "https://cdn.jsdelivr.net https://cdnjs.cloudflare.com https://unpkg.com "
        f"https://maps.googleapis.com {_CF_INSIGHTS_SCRIPT}"
        if heatmap
        else
        "script-src 'self' 'unsafe-inline' "
        f"https://cdn.jsdelivr.net https://cdnjs.cloudflare.com https://unpkg.com {_CF_INSIGHTS_SCRIPT}"
    )
    connect_sources = _GMAPS_CONNECT if heatmap else _BASE_CONNECT
    img_src = (
        "img-src 'self' data: blob: https://*.googleapis.com https://*.gstatic.com"
        if heatmap
        else "img-src 'self' data: blob:"
    )
    style_src = (
        "style-src 'self' 'unsafe-inline' https://cdn.jsdelivr.net https://cdnjs.cloudflare.com "
        "https://fonts.googleapis.com"
        if heatmap
        else
        "style-src 'self' 'unsafe-inline' https://cdn.jsdelivr.net https://cdnjs.cloudflare.com "
        "https://fonts.googleapis.com"
    )
    return "; ".join(
        [
            "default-src 'self'",
            "object-src 'none'",
            "frame-ancestors 'none'",
            "base-uri 'self'",
            "form-action 'self'",
            script_src,
            style_src,
            "font-src 'self' data: https://cdn.jsdelivr.net https://cdnjs.cloudflare.com https://fonts.gstatic.com",
            img_src,
            f"connect-src {' '.join(connect_sources)}",
            "worker-src 'self' blob:",
        ]
    )


async def request_timeout_middleware(request: Request, call_next: Callable):
    """Abort requests that exceed the configured timeout."""
    try:
        response = await asyncio.wait_for(
            call_next(request),
            timeout=max(settings.REQUEST_TIMEOUT_SECONDS, 1),
        )
    except TimeoutError:
        logger.error("Request timed out: %s %s", request.method, request.url.path)
        return JSONResponse(status_code=504, content={"detail": "Request timed out."})
    return response


_ADMIN_RATE_LIMIT_WINDOW = 60  # seconds (matches slowapi default window)


async def security_headers_middleware(request: Request, call_next: Callable):
    """Attach baseline browser security headers and rate-limit info to every response."""
    import time

    start = time.monotonic()
    response = await call_next(request)
    duration_ms = int((time.monotonic() - start) * 1000)

    response.headers["X-Frame-Options"] = "DENY"
    response.headers["X-Content-Type-Options"] = "nosniff"
    response.headers["X-XSS-Protection"] = "0"
    # The password-reset page carries a single-use token in its URL query string;
    # use the strictest Referrer-Policy there so the token can never leak to a
    # third-party resource via the Referer header.
    if request.url.path == "/reset-password":
        response.headers["Referrer-Policy"] = "no-referrer"
    else:
        response.headers["Referrer-Policy"] = "strict-origin-when-cross-origin"
    response.headers["Content-Security-Policy"] = _security_csp(
        heatmap=request.url.path == "/admin/heatmap"
    )
    response.headers.setdefault("Permissions-Policy", "camera=(), microphone=(), geolocation=()")
    if settings.ENVIRONMENT.lower() == "production":
        response.headers["Strict-Transport-Security"] = "max-age=31536000; includeSubDomains"

    # Expose rate-limit context on admin API responses so clients can back off proactively.
    # The actual counters live in slowapi; we surface the configured ceiling and window.
    # Write methods are governed by RATE_LIMIT_ADMIN_WRITE, reads by RATE_LIMIT_ADMIN_READ,
    # so the advertised ceiling must match the method to avoid misleading clients.
    path = request.url.path
    if path.startswith("/api/admin"):
        if request.method in ("POST", "PUT", "PATCH", "DELETE"):
            limit_str = getattr(settings, "RATE_LIMIT_ADMIN_WRITE", "30/minute")
            default_ceiling = 30
        else:
            limit_str = getattr(settings, "RATE_LIMIT_ADMIN_READ", "60/minute")
            default_ceiling = 60
        try:
            ceiling = int(limit_str.split("/")[0])
        except (ValueError, IndexError):
            ceiling = default_ceiling
        response.headers.setdefault("X-RateLimit-Limit", str(ceiling))
        response.headers.setdefault("X-RateLimit-Window", str(_ADMIN_RATE_LIMIT_WINDOW))

    response.headers["X-Response-Time-Ms"] = str(duration_ms)
    return response


def _restore_response_body(response: Response, body: bytes) -> None:
    response.body_iterator = iterate_in_threadpool([body])
    response.headers["content-length"] = str(len(body))


async def sanitize_json_response_middleware(request: Request, call_next: Callable):
    """Remove secret fields from JSON responses defensively."""
    response = await call_next(request)
    content_type = (response.headers.get("content-type") or "").lower()
    if "application/json" not in content_type:
        return response

    body = b""
    try:
        async for chunk in response.body_iterator:
            body += chunk
    except (RuntimeError, TypeError):
        return response

    _restore_response_body(response, body)
    if not body or len(body) > 1_000_000:
        return response

    try:
        payload = json.loads(body)
    except (json.JSONDecodeError, TypeError, ValueError):
        return response

    sanitized = sanitize_response_payload(payload)
    if sanitized == payload:
        return response

    new_body = json.dumps(
        sanitized,
        ensure_ascii=False,
        separators=(",", ":"),
        default=str,
    ).encode("utf-8")
    _restore_response_body(response, new_body)
    return response


def _resolve_actor_id(request: Request, db: Session) -> Optional[int]:
    token = request.headers.get("authorization", "")
    if token.lower().startswith("bearer "):
        token = token[7:].strip()
    else:
        token = request.cookies.get(settings.SESSION_COOKIE_NAME) or request.cookies.get("kinjo_token") or ""

    if not token:
        return None

    try:
        payload = jwt.decode(token, settings.SECRET_KEY, algorithms=[settings.ALGORITHM])
    except JWTError:
        return None

    username = payload.get("sub")
    if not username or payload.get("purpose"):
        return None

    user = db.query(models.User).filter(
        models.User.username == username, models.User.deleted_at.is_(None)
    ).first()
    return user.id if user else None


async def audit_state_changes_middleware(request: Request, call_next: Callable):
    """Create a generic audit trail for successful state-changing HTTP calls."""
    response = await call_next(request)
    path = request.url.path
    if (
        request.method not in STATE_CHANGING_METHODS
        or response.status_code >= 400
        or not path.startswith("/api")
        or path in AUDIT_EXCLUDED_PATHS
    ):
        return response

    try:
        db = SessionLocal()
        actor_id = _resolve_actor_id(request, db)
        validators.log_audit_action(
            db=db,
            user_id=actor_id,
            action=f"HTTP_{request.method}",
            entity_type="HTTP",
            entity_id=None,
            details=f"{path} -> {response.status_code}",
            ip_address=request.client.host if request.client else None,
            sensitivity_level=1,
        )
    except (RuntimeError, AttributeError, TypeError, ValueError, SQLAlchemyError) as exc:
        logger.warning("Failed to write generic audit log for %s: %s", path, exc)
    finally:
        try:
            db.close()
        except (RuntimeError, AttributeError):
            pass

    return response

