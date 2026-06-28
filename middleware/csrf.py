"""Double-submit CSRF protection helpers."""

from __future__ import annotations

import secrets
from typing import Callable
from urllib.parse import urlparse

from fastapi import Request
from fastapi.responses import JSONResponse

from config import settings

CSRF_SAFE_METHODS = {"GET", "HEAD", "OPTIONS"}
CSRF_MFA_EXEMPT_PATHS = {"/api/auth/mfa/setup", "/api/auth/mfa/verify"}

# Browser telemetry collectors are fire-and-forget reporters with no user-controlled
# state changes, so forging a POST against them has negligible security impact.
CSRF_TELEMETRY_EXEMPT_PATHS = {
    "/api/telemetry/vitals",
    "/api/telemetry/errors",
    "/api/telemetry/api",
}


def _allowed_hosts(request: Request) -> set[str]:
    hosts = {host.lower() for host in settings.TRUSTED_HOSTS}
    hosts.add((request.url.netloc or "").lower())
    for origin in settings.CORS_ALLOWED_ORIGINS or []:
        parsed = urlparse(origin)
        if parsed.netloc:
            hosts.add(parsed.netloc.lower())
    return {host for host in hosts if host}


def ensure_request_csrf_token(request: Request) -> str:
    """Resolve the request CSRF token and cache it on request.state."""
    token = request.cookies.get(settings.CSRF_COOKIE_NAME)
    if not token:
        token = secrets.token_hex(32)
    request.state.csrf_token = token
    return token


def _same_origin_allowed(request: Request) -> bool:
    allowed = _allowed_hosts(request)
    origin = request.headers.get("origin", "")
    referer = request.headers.get("referer", "")
    if origin:
        origin_host = (urlparse(origin).netloc or "").lower()
        return origin_host in allowed
    if referer:
        referer_host = (urlparse(referer).netloc or "").lower()
        return referer_host in allowed
    return True


async def csrf_protection_middleware(request: Request, call_next: Callable):
    """Strict CSRF enforcement for state-changing requests."""
    csrf_token = ensure_request_csrf_token(request)

    if (settings.TESTING and not settings.is_production) or request.method in CSRF_SAFE_METHODS:
        response = await call_next(request)
        if request.cookies.get(settings.CSRF_COOKIE_NAME) != csrf_token:
            response.set_cookie(
                key=settings.CSRF_COOKIE_NAME,
                value=csrf_token,
                path="/",
                samesite="strict",
                secure=settings.secure_cookies,
                httponly=False,
                domain=settings.COOKIE_DOMAIN or None,
            )
        return response

    # Skip CSRF for MFA setup/verify endpoints (user has kinjo_mfa_ticket but no session)
    if request.url.path in CSRF_MFA_EXEMPT_PATHS:
        return await call_next(request)

    # Skip CSRF for browser telemetry collectors (no state changes, negligible forgery risk)
    if request.url.path in CSRF_TELEMETRY_EXEMPT_PATHS:
        return await call_next(request)

    if not _same_origin_allowed(request):
        return JSONResponse(status_code=403, content={"detail": "CSRF validation failed."})

    csrf_cookie = request.cookies.get(settings.CSRF_COOKIE_NAME, "")
    csrf_header = request.headers.get("x-csrf-token", "")
    if not csrf_cookie or not csrf_header:
        return JSONResponse(status_code=403, content={"detail": "CSRF validation failed."})
    if not secrets.compare_digest(csrf_cookie, csrf_header):
        return JSONResponse(status_code=403, content={"detail": "CSRF validation failed."})

    response = await call_next(request)
    if request.cookies.get(settings.CSRF_COOKIE_NAME) != csrf_token:
        response.set_cookie(
            key=settings.CSRF_COOKIE_NAME,
            value=csrf_token,
            path="/",
            samesite="strict",
            secure=settings.secure_cookies,
            httponly=False,
            domain=settings.COOKIE_DOMAIN or None,
        )
    return response