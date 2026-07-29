"""
Shared rate limiter configuration for the API.
"""
import logging

from fastapi.responses import JSONResponse
from slowapi import Limiter
from slowapi.util import get_remote_address
from slowapi.errors import RateLimitExceeded
from limits import parse

from config import settings
from admin_security import create_error_response, ErrorCode, get_correlation_id

logger = logging.getLogger(__name__)


def _storage_is_reachable(storage_uri: str) -> bool:
    """Can the configured limiter backend actually be reached right now?"""
    try:
        from limits.storage import storage_from_string

        return bool(storage_from_string(storage_uri).check())
    except Exception:  # noqa: BLE001 - any backend failure means "not usable"
        return False


def _resolve_storage_uri() -> str:
    if settings.TESTING:
        return "memory://"
    storage_uri = getattr(settings, "RATE_LIMIT_STORAGE_URI", "").strip()
    if not storage_uri or storage_uri.startswith("memory:"):
        return storage_uri or "memory://"

    # Fall back to in-process counters when the backend is down, instead of
    # letting every rate-limited endpoint raise.
    #
    # slowapi calls storage.incr() inside the request path, so an unreachable
    # Redis turned into an unhandled redis.exceptions.ConnectionError and a 500
    # on every decorated route — including POST /token, i.e. nobody could log in
    # at all. cache_service already degrades this way ("falling back to
    # in-memory cache"); the limiter was the one component that did not.
    if not _storage_is_reachable(storage_uri):
        logger.warning(
            "Rate limit storage %s is unreachable — falling back to in-memory "
            "counters for this process. Limits are then per-worker rather than "
            "shared, so restore the backend for accurate global limits.",
            storage_uri,
        )
        return "memory://"
    return storage_uri


# swallow_errors: if the backend dies *after* startup, slowapi logs and allows
# the request rather than raising. Availability wins over strict enforcement
# here: the alternative is a storage blip 500-ing sign-in for everyone.
limiter = Limiter(
    key_func=get_remote_address,
    storage_uri=_resolve_storage_uri(),
    swallow_errors=True,
)

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
    try:
        allowed = limiter._limiter.hit(item, "admin-surface", method, path, client_key)
    except Exception:  # noqa: BLE001 - storage outage must not block admin traffic
        # Mirrors the limiter's swallow_errors stance: a backend failure here
        # used to propagate out of the request and 500 the page.
        logger.warning("Rate limit check failed for %s %s; allowing request", method, path)
        return True, limit_value
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
