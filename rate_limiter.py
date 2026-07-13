"""
Shared rate limiter configuration for the API.
"""
from fastapi.responses import JSONResponse
from slowapi import Limiter
from slowapi.util import get_remote_address
from slowapi.errors import RateLimitExceeded
from limits import parse

from config import settings
from admin_security import create_error_response, ErrorCode, get_correlation_id


def _resolve_storage_uri() -> str:
    if settings.TESTING:
        return "memory://"
    storage_uri = getattr(settings, "RATE_LIMIT_STORAGE_URI", "").strip()
    return storage_uri or "memory://"


limiter = Limiter(key_func=get_remote_address, storage_uri=_resolve_storage_uri())

if settings.TESTING:
    limiter.enabled = False


def check_admin_surface_limit(request) -> tuple[bool, str]:
    """Apply a default per-IP/per-route limit to every Admin-consumed surface."""
    if settings.TESTING or not limiter.enabled:
        return True, ""
    method = request.method.upper()
    path = request.url.path
    if method in {"GET", "HEAD", "OPTIONS"}:
        limit_value = "20/minute" if any(token in path for token in ("/export", "/render")) else settings.RATE_LIMIT_ADMIN_READ
    else:
        limit_value = settings.RATE_LIMIT_ADMIN_WRITE
    item = parse(limit_value)
    client_key = get_remote_address(request)
    allowed = limiter._limiter.hit(item, "admin-surface", method, path, client_key)
    return allowed, limit_value


def rate_limit_exceeded_handler(request, exc: RateLimitExceeded) -> JSONResponse:
    retry_after = int(getattr(exc, "retry_after", 60) or 60)
    return JSONResponse(
        status_code=429,
        content=create_error_response(
            code=ErrorCode.RATE_LIMITED,
            message=f"Rate limit exceeded. Retry after {retry_after} seconds.",
            details={"retry_after": retry_after},
        ),
        headers={
            "Retry-After": str(retry_after),
            "X-Correlation-ID": get_correlation_id(),
        },
    )


__all__ = ["limiter", "rate_limit_exceeded_handler", "check_admin_surface_limit"]
