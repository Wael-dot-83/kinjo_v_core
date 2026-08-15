"""Double-submit CSRF protection — the single enforcement point.

Policy for state-changing requests (safe methods always pass):

1. **Pre-auth entry points are exempt** (`CSRF_EXEMPT_PATHS`): login, register,
   token issue, MFA setup/verify, and browser telemetry. No session exists to
   forge against yet, and API clients must be able to authenticate without a
   cookie dance.
2. **Bearer-authenticated requests are exempt**: a browser cannot attach an
   `Authorization` header to a forged cross-origin request, so bearer tokens
   are inherently CSRF-safe.
3. **Requests carrying no cookies at all pass through**: with no ambient
   authority there is nothing to forge, and authentication downstream answers
   401. This is what keeps curl-style API clients and anonymous 401 semantics
   intact.
4. **Requests carrying cookies** (browser sessions — the real CSRF surface)
   must present the double-submit pair: a `kinjo_csrf_token` cookie matched by
   an `X-CSRF-Token` header, compared in constant time, from an allowed
   Origin/Referer. Failures return **400**.

There is deliberately **no TESTING conditional**: the suite authenticates with
bearer tokens (rule 2) or dependency overrides (rule 3), so production
semantics run unchanged under test and there is no test-only seam to drift.
"""

from __future__ import annotations

import secrets
from typing import Callable
from urllib.parse import urlparse

from fastapi import Request
from fastapi.responses import JSONResponse

from config import settings

CSRF_SAFE_METHODS = {"GET", "HEAD", "OPTIONS"}

# Pre-auth entry points: no session exists when these are called, so there is
# no ambient authority to forge against. Telemetry collectors are fire-and-
# forget reporters with no user-controlled state changes.
#
# /api/ui-language is the same shape as login: it is how an anonymous visitor
# switches the rendering language before authentication exists, it writes
# nothing but the kinjo_lang cookie, and it touches no database row. The worst
# a forged request can do is flip the victim's rendering language. Requiring
# the double-submit pair here would break the anonymous switcher, whose very
# purpose is to run before any session (and therefore before the browser has
# been taught to echo a CSRF header) exists.
CSRF_EXEMPT_PATHS = {
    "/token",
    "/api/auth/login",
    "/api/auth/register",
    "/api/auth/mfa/setup",
    "/api/auth/mfa/verify",
    "/api/contact",
    "/api/users/request-password-reset",
    "/api/users/reset-password",
    "/api/telemetry/vitals",
    "/api/telemetry/errors",
    "/api/telemetry/api",
    "/api/ui-language",
}

# Back-compat aliases for importers that want the named subsets.
CSRF_MFA_EXEMPT_PATHS = {"/api/auth/mfa/setup", "/api/auth/mfa/verify"}
CSRF_TELEMETRY_EXEMPT_PATHS = {
    "/api/telemetry/vitals",
    "/api/telemetry/errors",
    "/api/telemetry/api",
}


def _loopback_netloc_aliases(netloc: str) -> set[str]:
    """Return localhost/loopback aliases for the same port."""
    parsed = urlparse(f"http://{netloc}")
    host = (parsed.hostname or "").lower()
    port = parsed.port
    if host not in {"localhost", "127.0.0.1", "::1"}:
        return set()
    if port is None:
        return {"localhost", "127.0.0.1", "[::1]"}
    return {f"localhost:{port}", f"127.0.0.1:{port}", f"[::1]:{port}"}


def _allowed_hosts(request: Request) -> set[str]:
    hosts = {host.lower() for host in settings.TRUSTED_HOSTS}
    netloc = (request.url.netloc or "").lower()
    if netloc:
        hosts.add(netloc)
        hosts.update(_loopback_netloc_aliases(netloc))
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


def _reject() -> JSONResponse:
    return JSONResponse(status_code=400, content={"detail": "CSRF validation failed."})


async def csrf_protection_middleware(request: Request, call_next: Callable):
    """Single CSRF enforcement point for state-changing requests."""
    csrf_token = ensure_request_csrf_token(request)

    async def _pass() -> JSONResponse:
        response = await call_next(request)
        # Provision the CSRF cookie whenever the client does not already hold
        # the current token, so browsers always have the pair available.
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

    # Safe methods never mutate state.
    if request.method in CSRF_SAFE_METHODS:
        return await _pass()

    # Pre-auth entry points (login/register/token/MFA/telemetry).
    if request.url.path in CSRF_EXEMPT_PATHS:
        return await _pass()

    # Bearer tokens are inherently CSRF-safe: browsers cannot attach an
    # Authorization header to a forged cross-origin request.
    auth_header = request.headers.get("authorization", "")
    if auth_header.lower().startswith("bearer "):
        return await _pass()

    # No cookies means no ambient authority, so there is nothing to forge.
    # Authentication downstream answers 401 for protected endpoints.
    # A presented header without its cookie is half a pair — never valid.
    if not request.cookies:
        if request.headers.get("x-csrf-token"):
            return _reject()
        return await _pass()

    # Cookie-carrying requests (browser sessions): full double-submit contract.
    if not _same_origin_allowed(request):
        return _reject()

    csrf_cookie = request.cookies.get(settings.CSRF_COOKIE_NAME, "")
    csrf_header = request.headers.get("x-csrf-token", "")
    if not csrf_cookie or not csrf_header:
        return _reject()
    if not secrets.compare_digest(csrf_cookie, csrf_header):
        return _reject()

    return await _pass()
