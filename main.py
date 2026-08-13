"""
KinJo - Kindergarten Management Platform
Main FastAPI Application
"""
import asyncio
import gzip
import os
import secrets
from datetime import datetime, timedelta, timezone
from typing import Optional
from fastapi import FastAPI, Depends, HTTPException, status, Request, Form, WebSocket
from fastapi.security import OAuth2PasswordRequestForm
from fastapi.staticfiles import StaticFiles
from fastapi.responses import HTMLResponse, RedirectResponse, JSONResponse, FileResponse, Response
from fastapi.templating import Jinja2Templates
from fastapi.middleware.cors import CORSMiddleware
from fastapi.middleware.gzip import GZipMiddleware
from pydantic import BaseModel
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.concurrency import iterate_in_threadpool
from starlette.middleware.trustedhost import TrustedHostMiddleware
from contextlib import asynccontextmanager
from sqlalchemy.orm import Session
from sqlalchemy.exc import SQLAlchemyError
from slowapi.errors import RateLimitExceeded


class UTF8ContentTypeMiddleware(BaseHTTPMiddleware):
    """Middleware to ensure UTF-8 Content-Type for HTML responses"""
    async def dispatch(self, request: Request, call_next):
        response = await call_next(request)
        content_type = response.headers.get("content-type", "")
        if "text/html" in content_type and "charset" not in content_type:
            response.headers["content-type"] = "text/html; charset=utf-8"
        return response


class UTF8StaticFiles(StaticFiles):
    async def get_response(self, path: str, scope):
        response = await super().get_response(path, scope)
        if isinstance(response, FileResponse):
            normalized_path = path.lower()
            if normalized_path.endswith(".js"):
                response.headers["Content-Type"] = "application/javascript; charset=utf-8"

            if "cache-control" not in response.headers:
                static_asset_suffixes = (
                    ".js", ".css", ".json", ".svg", ".png", ".jpg", ".jpeg",
                    ".webp", ".ico", ".woff", ".woff2", ".ttf", ".eot", ".map"
                )
                if normalized_path.endswith(static_asset_suffixes):
                    if settings.ENVIRONMENT.lower() == "production":
                        response.headers["Cache-Control"] = "public, max-age=31536000, immutable"
                    else:
                        response.headers["Cache-Control"] = "no-cache, no-store, must-revalidate"
                elif normalized_path.endswith(".html"):
                    response.headers["Cache-Control"] = "no-cache"
        return response


import logging
logger = logging.getLogger(__name__)

import models
from database import get_db, init_db
from auth import authenticate_user, create_access_token, get_password_hash, requires_password_change
from cache_service import cache_service
from config import settings
from ui_language import set_ui_language_cookie
from ui_language import normalize_ui_language
from dependencies import get_current_user, get_current_user_optional, ManagerScope, RedirectToLogin
from middleware.auth import (
    build_generic_auth_exception,
    classify_login_identifier,
    is_privileged_role,
    sanitize_response_payload,
)
from middleware.csrf import csrf_protection_middleware
from utils.time_utils import now_amman
from middleware.security import (
    audit_state_changes_middleware,
    request_timeout_middleware,
    sanitize_json_response_middleware,
    security_headers_middleware,
)
from mfa_service import (
    decrypt_secret,
    encrypt_secret,
    generate_totp_secret,
    provisioning_uri,
    qr_code_data_url,
    verify_code,
)
import validators
from captcha_service import captcha_error_message, captcha_required, verify_captcha
from admin_security import CorrelationIdMiddleware, APIError, api_error_handler
from audit_actions import AuditAction
from rate_limiter import limiter, rate_limit_exceeded_handler, check_admin_surface_limit
from performance_monitor import PerformanceMiddleware, setup_database_monitoring, start_system_monitoring
from backup_manager import backup_scheduler
from daily_report_scheduler import daily_report_scheduler, waitlist_expiry_scheduler
from monitoring_service import performance_monitor, health_checker, auto_scaler
from predictive_analytics import predictive_analytics
from language_integrity import enforce_english_html_integrity


# Safety guard: never allow TESTING bypass in production
def ensure_not_testing_in_production() -> None:
    if settings.ENVIRONMENT.lower() == "production" and settings.TESTING:
        raise RuntimeError("Refusing to start with TESTING=true in production environment.")


def warn_if_testing_disables_security() -> None:
    """Say out loud when TESTING=true has relaxed security subsystems.

    CSRF is NOT one of them: middleware/csrf.py runs identical semantics under
    TESTING (bearer and cookie-less requests pass; cookie-carrying requests
    need the double-submit pair), so a CSRF regression is always reproducible
    locally. What TESTING still relaxes is the rate limiter
    (rate_limiter.py disables itself and uses in-memory storage), so a dev
    server started with TESTING=true in .env accepts request rates production
    never would.

    The pytest suite sets TESTING itself (conftest.py sets os.environ["TESTING"]
    before importing the app), so .env does NOT need it — leaving it out of .env
    costs nothing and makes the dev server behave like production.

    Production can't reach this: ensure_not_testing_in_production() raises first.
    """
    if not settings.TESTING:
        return
    logging.getLogger("main").warning(
        "TESTING=true — rate limiting is DISABLED for this process "
        "(rate_limiter.py). CSRF is unaffected: middleware/csrf.py enforces "
        "the same double-submit policy under TESTING as in production. "
        "TESTING is for the pytest suite, which sets the flag itself; a dev "
        "or staging server does not need it in .env. Unset TESTING to "
        "exercise full production behaviour."
    )


def ensure_secure_production_config() -> None:
    """Fail fast on obviously unsafe production configuration."""
    if settings.ENVIRONMENT.lower() != "production":
        return

    secret_key = (settings.SECRET_KEY or "").strip().lower()
    weak_markers = {"changeme", "change-me", "development-only", "test-secret-key", "your-secret-key"}
    if len(settings.SECRET_KEY or "") < 32 or any(marker in secret_key for marker in weak_markers):
        raise RuntimeError("Refusing to start with an insecure SECRET_KEY in production.")

    if not settings.CORS_ALLOWED_ORIGINS:
        raise RuntimeError("Refusing to start without explicit CORS_ALLOWED_ORIGINS in production.")


ensure_not_testing_in_production()
ensure_secure_production_config()

# Logging configuration — JSON-structured in production, human-readable otherwise
def configure_logging():
    log_level = getattr(logging, settings.LOG_LEVEL.upper(), logging.INFO)
    use_json = settings.LOG_FORMAT.lower() == "json" and settings.ENVIRONMENT.lower() == "production"
    handlers: list = []
    if use_json:
        try:
            from pythonjsonlogger.json import JsonFormatter

            stream_handler = logging.StreamHandler()
            fmt = JsonFormatter(
                "%(asctime)s %(levelname)s %(name)s %(message)s",
                rename_fields={"asctime": "ts", "levelname": "level"},
            )
            stream_handler.setFormatter(fmt)
            handlers.append(stream_handler)
            if settings.LOG_FILE:
                file_handler = logging.FileHandler(settings.LOG_FILE)
                file_handler.setFormatter(fmt)
                handlers.append(file_handler)
        except ImportError:
            logging.warning("python-json-logger not installed; falling back to text logging")
            use_json = False

    if not use_json:
        stream_handler = logging.StreamHandler()
        stream_handler.setFormatter(
            logging.Formatter("%(asctime)s %(levelname)s %(name)s %(message)s")
        )
        handlers.append(stream_handler)
        if settings.ENVIRONMENT.lower() == "production" and settings.LOG_FILE:
            file_handler = logging.FileHandler(settings.LOG_FILE)
            file_handler.setFormatter(
                logging.Formatter("%(asctime)s %(levelname)s %(name)s %(message)s")
            )
            handlers.append(file_handler)

    root = logging.getLogger()
    root.setLevel(log_level)
    for h in handlers:
        h.setLevel(log_level)
        root.addHandler(h)

configure_logging()
# Must run after configure_logging() so the warning actually reaches a handler.
warn_if_testing_disables_security()

# Suppress noisy WinError 10054 connection reset errors on Windows asyncio
def _ignore_connection_reset(loop, context):
    exc = context.get("exception")
    if isinstance(exc, ConnectionResetError):
        logging.getLogger("uvicorn.error").debug("Client disconnected")
        return
    loop.default_exception_handler(context)

# Import routers
from frontend import router as frontend_router
from communication_service import router as communication_router
from safety_service import router as safety_router
from kpi_service import router as kpi_router
from analytics_service import router as analytics_router
from analytics_ws import router as analytics_ws_router
from dashboard_api import router as dashboard_router
from decision_support_api import router as decision_support_router
from admin_reports_api import router as admin_reports_router
from filter_api import router as filter_router
from export_api import router as export_router
# from realtime_service import websocket_endpoint
import audit_service
from admin_endpoints import router as admin_router
from admin_advanced_analytics_endpoints import router as admin_advanced_analytics_router

from daily_report_analytics import router as dr_analytics_router, frontend_router as dr_analytics_frontend
from monitoring_endpoints import router as monitoring_router
from manager_analytics_endpoints import router as manager_analytics_router
from classification_service import router as classification_router
from daily_reports_organization_api import router as daily_reports_organization_router
from api.parent import router as parent_router
from api.kindergartens import router as kindergartens_router
from api.locations import router as locations_router
from api.enrollment import router as enrollment_router
from api.daily_reports_routes import router as daily_reports_api_router
from api.children import router as children_router
from api.classes import router as classes_router
from api.attendance_routes import router as attendance_api_router
from api.registration import router as registration_router
from api.absence_requests import router as absence_requests_router
from api.users import router as users_router
from api.tasks import router as tasks_router
from api.manager import router as manager_router
from api.portfolio import router as portfolio_router
from routers.supervisor import router as supervisor_scoped_router
from routers.manager import router as manager_scoped_router
from routers.admin_impersonation import router as admin_impersonation_router
from routers.messaging import router as messaging_router
from me_endpoints import router as me_router
from government_api import router as government_api_router
from api.public import router as public_router
from api.missing_endpoints import router as missing_endpoints_router
from charts_api import router as charts_router
from analytics_explorer import router as analytics_explorer_router
from analytics_explorer import page_router as analytics_explorer_page_router
from telemetry_service import router as telemetry_router
from observability_endpoints import router as observability_router

# =============================================================================
# Lifespan Event Handler
# =============================================================================

@asynccontextmanager
async def lifespan(app: FastAPI):
    """Handle application startup and shutdown events"""
    # Startup
    init_db()
    if os.name == "nt":
        try:
            loop = asyncio.get_running_loop()
            loop.set_exception_handler(_ignore_connection_reset)
        except RuntimeError:
            pass

    # Setup performance monitoring (skip in test mode to avoid thread delays)
    if not settings.TESTING:
        from database import engine
        setup_database_monitoring(engine)
        start_system_monitoring()

        # Start daily report scheduler
        daily_report_scheduler.start_scheduler()

        # Start waitlist expiry scheduler (every 15 min)
        waitlist_expiry_scheduler.start_scheduler()

        # Start backup scheduler (automated daily backups)
        backup_scheduler.start_scheduler()

        # Start monitoring services
        performance_monitor.start_monitoring()
        auto_scaler.start_auto_scaling()

        # Start WebSocket periodic updates for real-time dashboards
        try:
            from realtime_service import periodic_kpi_updates
            asyncio.create_task(periodic_kpi_updates())
            logger.info("WebSocket real-time KPI updates enabled")
        except ImportError as e:
            logger.warning(f"Failed to enable WebSocket real-time updates: {e}")

    yield
    # Shutdown
    if not settings.TESTING:
        performance_monitor.stop_monitoring()

        # Stop schedulers
        backup_scheduler.stop_scheduler()
        daily_report_scheduler.stop_scheduler()
        waitlist_expiry_scheduler.stop_scheduler()

        auto_scaler.stop_auto_scaling()


# Create FastAPI application
api_docs_enabled = settings.API_DOCS_ENABLED and settings.ENVIRONMENT.lower() != "production"
app = FastAPI(
    title="KinJo - Kindergarten Management Platform",
    description="Enterprise-grade management system for kindergartens in Jordan",
    version="2.0.0",
    docs_url="/docs" if api_docs_enabled else None,
    redoc_url="/redoc" if api_docs_enabled else None,
    lifespan=lifespan
)

# Add rate limiter to app state
app.state.limiter = limiter
app.add_exception_handler(RateLimitExceeded, rate_limit_exceeded_handler)


# Handle redirect to login for unauthenticated frontend requests
@app.exception_handler(RedirectToLogin)
async def redirect_to_login_handler(request: Request, exc: RedirectToLogin):
    return RedirectResponse(url=exc.redirect_url, status_code=302)


@app.exception_handler(validators.ValidationError)
async def validation_error_handler(request: Request, exc: validators.ValidationError):
    return JSONResponse(status_code=400, content={"detail": exc.message})


# Catch-all: guarantee every uncaught exception is logged with a full traceback
# server-side (so it lands in the app's own structured log, not just uvicorn's
# console output) and that the client only ever sees a generic message —
# regardless of environment — never internal details or a stack trace.
@app.exception_handler(Exception)
async def unhandled_exception_handler(request: Request, exc: Exception):
    logger.exception(
        "UNHANDLED_EXCEPTION method=%s path=%s", request.method, request.url.path
    )
    
    # Check if the client is expecting an HTML response
    accept = request.headers.get("accept", "")
    if "text/html" in accept:
        from fastapi.templating import Jinja2Templates
        from fastapi.responses import HTMLResponse
        error_templates = Jinja2Templates(directory="templates")
        ui_lang = normalize_ui_language(request.cookies.get("kinjo_lang"))
        return error_templates.TemplateResponse(
            request=request, 
            name="500.html", 
            context={"ui_lang": ui_lang, "ui_dir": "rtl" if ui_lang == "ar" else "ltr"},
            status_code=500
        )
        
    return JSONResponse(status_code=500, content={"detail": "Internal server error."})

# Trusted host middleware
trusted_hosts = settings.TRUSTED_HOSTS or ["127.0.0.1", "localhost", "testserver"]
if settings.ENVIRONMENT.lower() != "production":
    trusted_hosts = list(dict.fromkeys([*trusted_hosts, "127.0.0.1", "localhost", "testserver"]))
app.add_middleware(TrustedHostMiddleware, allowed_hosts=trusted_hosts)

# CORS middleware
allowed_origins = settings.CORS_ALLOWED_ORIGINS or ["http://127.0.0.1:8000", "http://localhost:8000"]

app.add_middleware(
    CORSMiddleware,
    allow_origins=allowed_origins,
    allow_credentials=True,
    allow_methods=["GET", "POST", "PUT", "PATCH", "DELETE", "OPTIONS"],
    # X-UI-Language is read by i18n.request_language() as the explicit,
    # highest-priority language selector, but it was missing here — so no
    # browser-based client could ever send it. Starlette answers a preflight
    # that requests a disallowed header with 400 "Disallowed CORS headers",
    # which blocks the whole request, not just that header. The mobile web
    # build sends it on every call and was blocked at the preflight.
    allow_headers=[
        "Authorization",
        "Content-Type",
        "X-CSRF-Token",
        "X-UI-Language",
        "Accept",
        "Accept-Language",
    ],
)

# Compression middleware for faster API/template responses over network.
app.add_middleware(GZipMiddleware, minimum_size=1024, compresslevel=6)
from starlette.middleware.base import BaseHTTPMiddleware

class SecurityHeadersMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next):
        response = await call_next(request)
        response.headers["X-Content-Type-Options"] = "nosniff"
        response.headers["Content-Security-Policy"] = "frame-ancestors 'none';"
        response.headers["X-XSS-Protection"] = "0"
        if "Expires" in response.headers:
            del response.headers["Expires"]
        if "X-Frame-Options" in response.headers:
            del response.headers["X-Frame-Options"]
        return response

app.add_middleware(SecurityHeadersMiddleware)


# Canonical host redirect. Serving the same app on both the apex and www leaves
# two origins that each build their own history, caches and analytics. Sessions
# already survive the split because COOKIE_DOMAIN scopes the cookie to the
# registrable domain, so this is about having one address rather than about
# authentication. Disabled unless CANONICAL_HOST is set.
@app.middleware("http")
async def enforce_canonical_host(request: Request, call_next):
    canonical = settings.CANONICAL_HOST.strip().lower()
    if canonical and request.method in ("GET", "HEAD"):
        host = (request.headers.get("host") or "").split(":")[0].strip().lower()
        # Loopback is how the container health check and any on-box probe reach
        # the app; redirecting those to the public hostname would break them.
        if host and host not in {canonical, "localhost", "127.0.0.1", "::1"}:
            target = f"https://{canonical}{request.url.path}"
            if request.url.query:
                target = f"{target}?{request.url.query}"
            return RedirectResponse(target, status_code=301)
    return await call_next(request)


# Request timeout middleware
@app.middleware("http")
async def enforce_request_timeout(request: Request, call_next):
    return await request_timeout_middleware(request, call_next)

# Security headers middleware
@app.middleware("http")
async def add_security_headers(request: Request, call_next):
    return await security_headers_middleware(request, call_next)


@app.middleware("http")
async def enforce_admin_surface_rate_limit(request: Request, call_next):
    path = request.url.path
    # /api/telemetry is deliberately absent: its beacon endpoints (vitals/errors/
    # api) are public, high-frequency browser calls (CSRF-exempt below) that must
    # not be throttled by the admin-surface policy; its admin-only endpoints
    # (/stats, /cache) carry Depends(require_admin) individually, and /health is
    # an aggregate-only probe with no user data.
    protected_prefixes = ("/api/admin", "/api/observability", "/api/analytics", "/admin/charts")
    if path.startswith(protected_prefixes):
        allowed, limit_value = check_admin_surface_limit(request)
        if not allowed:
            return JSONResponse(
                status_code=429,
                content={"detail": "Rate limit exceeded"},
                headers={"Retry-After": "60", "X-RateLimit-Policy": limit_value},
            )
    return await call_next(request)


@app.middleware("http")
async def structured_access_log(request: Request, call_next):
    """Emit one structured log line per admin API request (user_id, method, path, status_code, duration_ms, request_id)."""
    import time
    from jose import jwt as _jwt, JWTError as _JWTError

    if not request.url.path.startswith("/api/admin"):
        return await call_next(request)

    start = time.monotonic()
    response = await call_next(request)
    duration_ms = int((time.monotonic() - start) * 1000)

    # Prefer the id resolved by the auth dependency (set on request.state) to avoid
    # re-decoding the JWT on every admin request. Fall back to a lightweight decode
    # only when the dependency did not run (e.g. unauthenticated/error responses).
    user_id: Optional[int] = getattr(request.state, "user_id", None)
    if user_id is None:
        try:
            auth_header = request.headers.get("Authorization", "")
            if auth_header.startswith("Bearer "):
                token = auth_header[7:]
                payload = _jwt.decode(token, settings.SECRET_KEY, algorithms=[settings.ALGORITHM])
                sub = payload.get("sub")
                if sub and str(sub).isdigit():
                    user_id = int(sub)
        except (_JWTError, Exception):
            pass

    correlation_id = request.headers.get("X-Correlation-ID") or response.headers.get("X-Correlation-ID", "")
    logger.info(
        "admin_api_access",
        extra={
            "user_id": user_id,
            "method": request.method,
            "path": request.url.path,
            "status_code": response.status_code,
            "duration_ms": duration_ms,
            "request_id": correlation_id,
        },
    )
    return response


def _likely_contains_arabic_utf8(payload: bytes) -> bool:
    """Fast heuristic to skip expensive HTML translation on ASCII-only pages."""
    if not payload:
        return False
    return b"\xd8" in payload or b"\xd9" in payload


def _restore_response_body(response: Response, body: bytes) -> None:
    if getattr(response, "body_iterator", None) is not None:
        response.body_iterator = iterate_in_threadpool([body])
    else:
        response.body = body
    response.headers["content-length"] = str(len(body))


@app.middleware("http")
async def enforce_english_language_integrity(request: Request, call_next):
    """
    Enforce single-language English output for HTML pages.
    This prevents mixed Arabic/English UI when the selected language is English.
    """
    response = await call_next(request)

    if request.method != "GET":
        return response
    if request.url.path.startswith("/api") or request.url.path.startswith("/static"):
        return response

    requested_lang = _normalize_ui_language(request.cookies.get("kinjo_lang"))
    if requested_lang != "en":
        return response

    content_type = response.headers.get("content-type", "").lower()
    if "text/html" not in content_type:
        return response

    body = b""
    try:
        if getattr(response, "body_iterator", None) is not None:
            body = b""
            async for chunk in response.body_iterator:
                body += chunk
        else:
            body = getattr(response, "body", b"") or b""

        if not body:
            return response

        content_encoding = response.headers.get("content-encoding", "").lower()
        is_gzip = "gzip" in content_encoding

        plain_body = body
        if is_gzip:
            try:
                plain_body = gzip.decompress(body)
            except OSError:
                _restore_response_body(response, body)
                return response

        if not _likely_contains_arabic_utf8(plain_body):
            _restore_response_body(response, body)
            return response

        html = plain_body.decode("utf-8", errors="ignore")
        translated_html = enforce_english_html_integrity(html)
        if translated_html == html:
            _restore_response_body(response, body)
            return response

        translated_plain = translated_html.encode("utf-8")
        translated_bytes = gzip.compress(translated_plain) if is_gzip else translated_plain

        _restore_response_body(response, translated_bytes)
        if is_gzip:
            response.headers["content-encoding"] = "gzip"
            response.headers["vary"] = "Accept-Encoding"
    except (RuntimeError, TypeError, UnicodeDecodeError, OSError):
        if body:
            _restore_response_body(response, body)
        # Do not block responses if translation enforcement fails.
        return response

    return response


# CSRF protection lives in middleware/csrf.py as the single enforcement
# point (double-submit pair, 400 on failure). Bearer-authenticated and
# cookie-less requests are inherently unforgeable and pass through; the
# full policy is documented in middleware/csrf.py's module docstring.


@app.middleware("http")
async def csrf_double_submit_protection(request: Request, call_next):
    return await csrf_protection_middleware(request, call_next)


@app.middleware("http")
async def audit_state_changes(request: Request, call_next):
    return await audit_state_changes_middleware(request, call_next)


@app.middleware("http")
async def sanitize_json_responses(request: Request, call_next):
    return await sanitize_json_response_middleware(request, call_next)

# Add UTF-8 Content-Type middleware for proper Arabic text encoding
app.add_middleware(UTF8ContentTypeMiddleware)

# Add Correlation ID middleware for request tracking
app.add_middleware(CorrelationIdMiddleware)

# Add Performance Monitoring middleware
app.add_middleware(PerformanceMiddleware)

# Register custom exception handler for APIError
app.add_exception_handler(APIError, api_error_handler)

# Mount static files
try:
    app.mount("/static", UTF8StaticFiles(directory="static"), name="static")
    logger.info("Static files mounted successfully from 'static' directory")
except FileNotFoundError as e:
    logger.warning("Static files directory not found: %s - serving without static files", str(e))
except (OSError, RuntimeError) as e:
    logger.error("Failed to mount static files: %s", str(e), exc_info=False)

# =============================================================================
# Authentication Endpoints (defined BEFORE routers to take precedence)
# =============================================================================

def _get_request_ip(request: Request) -> Optional[str]:
    forwarded_for = request.headers.get("X-Forwarded-For")
    if forwarded_for:
        return forwarded_for.split(",")[0].strip()
    client = request.client
    return client.host if client else None


def _log_auth_event(
    db: Session,
    user_id: Optional[int],
    action: str,
    details: Optional[str],
    ip_address: Optional[str],
    sensitivity_level: int = 2
) -> None:
    try:
        validators.log_audit_action(
            db=db,
            user_id=user_id,
            action=action,
            entity_type="Auth",
            entity_id=user_id,
            details=details,
            ip_address=ip_address,
            sensitivity_level=sensitivity_level
        )
    except SQLAlchemyError as e:
        logger.error("Failed to log audit action (database error): %s", str(e), exc_info=False)
        # Avoid blocking auth flows if audit logging fails
    except (RuntimeError, TypeError, ValueError, AttributeError) as e:
        logger.error("Unexpected error logging audit action: %s", str(e), exc_info=True)
        # Avoid blocking auth flows if audit logging fails


def _normalize_ui_language(value: Optional[str]) -> str:
    normalized = str(value or "ar").strip().lower()
    return normalized if normalized in {"ar", "en"} else "ar"


def _resolve_user_language(db: Session, user_id: int) -> str:
    try:
        pref = (
            db.query(models.UserFilterPreference)
            .filter(models.UserFilterPreference.user_id == user_id)
            .first()
        )
        if pref and isinstance(pref.filter_config, dict):
            return _normalize_ui_language(pref.filter_config.get("user_lang"))
    except (SQLAlchemyError, AttributeError, TypeError):
        pass
    return "ar"


def _set_ui_language_cookie(response: Response, language: str) -> None:
    # Delegates to ui_language so the login path and the language endpoint write
    # byte-identical cookie attributes; a domain mismatch between the two would
    # leave the browser holding two kinjo_lang cookies with different values.
    set_ui_language_cookie(response, language)


def _set_no_store_headers(response: Response) -> None:
    response.headers["Cache-Control"] = "no-store"
    response.headers["Pragma"] = "no-cache"


def _set_mfa_ticket_cookie(response: Response, ticket: str) -> None:
    response.set_cookie(
        key="kinjo_mfa_ticket",
        value=ticket,
        max_age=settings.MFA_TICKET_EXPIRE_MINUTES * 60,
        path="/",
        samesite="strict",
        secure=settings.secure_cookies,
        httponly=True,
        domain=settings.COOKIE_DOMAIN or None,
    )


def _clear_mfa_ticket_cookie(response: Response) -> None:
    response.delete_cookie(
        key="kinjo_mfa_ticket",
        path="/",
        domain=settings.COOKIE_DOMAIN or None,
    )


def _set_authenticated_session(
    response: Response,
    *,
    access_token: str,
    remember_me: bool,
) -> None:
    max_age = (
        settings.ACCESS_TOKEN_EXPIRE_MINUTES_REMEMBER
        if remember_me
        else settings.ACCESS_TOKEN_EXPIRE_MINUTES
    ) * 60
    csrf_token = secrets.token_hex(32)

    response.set_cookie(
        key=settings.SESSION_COOKIE_NAME,
        value=access_token,
        max_age=max_age,
        path="/",
        samesite="strict",
        secure=settings.secure_cookies,
        httponly=True,
        domain=settings.COOKIE_DOMAIN or None,
    )
    response.set_cookie(
        key=settings.CSRF_COOKIE_NAME,
        value=csrf_token,
        max_age=max_age,
        path="/",
        samesite="strict",
        secure=settings.secure_cookies,
        httponly=False,
        domain=settings.COOKIE_DOMAIN or None,
    )
    _set_no_store_headers(response)


def _clear_authenticated_session(response: Response, request: Request) -> None:
    restore_token = request.cookies.get("kinjo_impersonation")
    if restore_token:
        try:
            from jose import JWTError, jwt as _jwt

            restore_payload = _jwt.decode(
                restore_token, settings.SECRET_KEY, algorithms=[settings.ALGORITHM]
            )
            if restore_payload.get("purpose") == "impersonation_restore" and restore_payload.get("jti"):
                now = int(datetime.now(timezone.utc).timestamp())
                ttl = max(1, int(restore_payload.get("exp", now + 1)) - now)
                revoked = cache_service.add_if_absent(
                    f"impersonation_restore_revoked:{restore_payload['jti']}",
                    True,
                    ttl_seconds=ttl,
                )
                if revoked is None:
                    raise HTTPException(
                        status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                        detail="Authentication security store is unavailable.",
                    )
        except (JWTError, TypeError, ValueError):
            pass

    for cookie_name in (
        settings.SESSION_COOKIE_NAME,
        settings.CSRF_COOKIE_NAME,
        "kinjo_token",
        "kinjo_mfa_ticket",
        "kinjo_impersonation",
    ):
        response.delete_cookie(
            key=cookie_name,
            path="/",
            domain=settings.COOKIE_DOMAIN or None,
        )
    _set_no_store_headers(response)


async def _do_login(request: Request, form_data: OAuth2PasswordRequestForm, db: Session):
    """Internal login logic with server-side identifier validation and MFA."""
    from sqlalchemy import or_

    ip_address = _get_request_ip(request)
    form = await request.form()
    remember_raw = form.get("remember_me")
    remember_me = str(remember_raw).lower() in {"1", "true", "on", "yes"}
    raw_username = form_data.username.strip()

    if captcha_required():
        captcha_token = str(form.get("captcha_token") or "")
        if not verify_captcha(captcha_token):
            lang = "en" if request.headers.get("Accept-Language", "ar").startswith("en") else "ar"
            raise HTTPException(status_code=400, detail=captcha_error_message(lang))

    try:
        identifier_type, normalized_identifier = classify_login_identifier(raw_username)
    except ValueError:
        raise build_generic_auth_exception()

    filters = []
    if identifier_type == "phone":
        filters.append(models.User.phone_number == normalized_identifier)
    elif identifier_type == "email":
        filters.append(models.User.email == normalized_identifier)
    else:
        filters.extend(
            [
                models.User.username == normalized_identifier,
                models.User.email == normalized_identifier.lower(),
            ]
        )

    target_user = db.query(models.User).filter(or_(*filters)).first()
    now_utc = datetime.now(timezone.utc)
    if target_user and target_user.locked_until:
        locked_until = target_user.locked_until
        if locked_until.tzinfo is None:
            locked_until = locked_until.replace(tzinfo=timezone.utc)
        if locked_until > now_utc:
            _log_auth_event(
                db=db,
                user_id=target_user.id,
                action=AuditAction.LOGIN_LOCKED,
                details="Account lockout enforced",
                ip_address=ip_address,
                sensitivity_level=3,
            )
            raise build_generic_auth_exception(status_code=status.HTTP_423_LOCKED)

    user = authenticate_user(db, normalized_identifier, form_data.password)
    if not user:
        _log_auth_event(
            db=db,
            user_id=target_user.id if target_user else None,
            action=AuditAction.LOGIN_FAILED,
            details="Credential validation failed",
            ip_address=ip_address,
            sensitivity_level=3,
        )
        raise build_generic_auth_exception()

    _stored_lang = getattr(user, "preferred_language", None)
    user_lang = _stored_lang if _stored_lang in ("ar", "en") else _resolve_user_language(db, user.id)
    base_payload = {
        "user_lang": user_lang,
        "remember_me": remember_me,
        "user": {
            "id": user.id,
            "username": user.username,
            "email": user.email,
            "role": user.role.value,
            "must_change_password": requires_password_change(user),
            "mfa_enabled": bool(getattr(user, "mfa_enabled", False)),
        },
    }

    if not settings.TESTING and settings.REQUIRE_MFA and is_privileged_role(user.role):
        purpose = "mfa_challenge" if user.mfa_enabled else "mfa_setup"
        mfa_ticket = create_access_token(
            data={
                "sub": user.username,
                "role": user.role.value,
                "purpose": purpose,
                "remember_me": remember_me,
            },
            expires_delta=timedelta(minutes=settings.MFA_TICKET_EXPIRE_MINUTES),
        )
        _log_auth_event(
            db=db,
            user_id=user.id,
            action=AuditAction.MFA_REQUIRED,
            details=f"purpose={purpose}",
            ip_address=ip_address,
            sensitivity_level=2,
        )
        return {
            **base_payload,
            "mfa_required": True,
            "mfa_setup_required": purpose == "mfa_setup",
            "mfa_ticket": mfa_ticket,
            "mfa_redirect": "/mfa/setup?mode=setup" if purpose == "mfa_setup" else "/mfa/setup?mode=challenge",
        }

    access_token_expires = timedelta(
        minutes=(
            settings.ACCESS_TOKEN_EXPIRE_MINUTES_REMEMBER
            if remember_me
            else settings.ACCESS_TOKEN_EXPIRE_MINUTES
        )
    )
    access_token = create_access_token(
        data={"sub": user.username, "role": user.role.value},
        expires_delta=access_token_expires,
    )

    _log_auth_event(
        db=db,
        user_id=user.id,
        action=AuditAction.LOGIN_SUCCESS,
        details=f"Login successful (remember_me={remember_me})",
        ip_address=ip_address,
        sensitivity_level=2,
    )

    return {
        **base_payload,
        "access_token": access_token,
        "token_type": "bearer",
        "mfa_required": False,
    }


def _issue_auth_response(payload: dict, *, status_code: int = 200) -> JSONResponse:
    response_payload = sanitize_response_payload(dict(payload))
    mfa_ticket = response_payload.pop("mfa_ticket", None)
    response = JSONResponse(content=response_payload, status_code=status_code)
    if payload.get("access_token"):
        _clear_mfa_ticket_cookie(response)
        _set_authenticated_session(
            response,
            access_token=payload["access_token"],
            remember_me=bool(payload.get("remember_me")),
        )
    elif payload.get("mfa_required") and mfa_ticket:
        _set_mfa_ticket_cookie(response, mfa_ticket)
    else:
        _set_no_store_headers(response)
    _set_ui_language_cookie(response, payload.get("user_lang", "ar"))
    return response


def _resolve_mfa_ticket_from_request(request: Request) -> str:
    auth_header = request.headers.get("authorization", "")
    if auth_header.lower().startswith("bearer "):
        return auth_header[7:].strip()
    cookie_ticket = request.cookies.get("kinjo_mfa_ticket", "")
    if cookie_ticket:
        return cookie_ticket
    raise HTTPException(status_code=401, detail="MFA session expired.")


def _decode_mfa_ticket(token: str, db: Session, *, expected_purposes: set[str]) -> tuple[models.User, str, bool]:
    from jose import JWTError, jwt as _jwt

    try:
        payload = _jwt.decode(token, settings.SECRET_KEY, algorithms=[settings.ALGORITHM])
    except JWTError as exc:
        raise HTTPException(status_code=401, detail="MFA session expired.") from exc

    username = payload.get("sub")
    purpose = payload.get("purpose")
    if not username or purpose not in expected_purposes:
        raise HTTPException(status_code=401, detail="MFA session expired.")

    user = db.query(models.User).filter(
        models.User.username == username, models.User.deleted_at.is_(None)
    ).first()
    if not user or user.status != models.UserStatus.ACTIVE:
        raise HTTPException(status_code=401, detail="MFA session expired.")

    return user, purpose, bool(payload.get("remember_me"))


class MFACodeRequest(BaseModel):
    code: str


@app.post("/token")
@limiter.limit("5/minute")  # Rate limit: 5 login attempts per minute per IP
async def token_login(
    request: Request,
    form_data: OAuth2PasswordRequestForm = Depends(),
    db: Session = Depends(get_db)
):
    """OAuth2 token endpoint (for frontend)"""
    payload = await _do_login(request, form_data, db)
    return _issue_auth_response(payload, status_code=202 if payload.get("mfa_required") else 200)


@app.post("/api/auth/login")
@limiter.limit("5/minute")  # Rate limit: 5 login attempts per minute per IP
async def api_login(
    request: Request,
    form_data: OAuth2PasswordRequestForm = Depends(),
    db: Session = Depends(get_db)
):
    """API login endpoint"""
    payload = await _do_login(request, form_data, db)
    return _issue_auth_response(payload, status_code=202 if payload.get("mfa_required") else 200)


@app.post("/api/auth/logout")
async def logout(
    request: Request,
    current_user: Optional[models.User] = Depends(get_current_user_optional),
    db: Session = Depends(get_db)
):
    """Logout endpoint - client should clear tokens"""
    if current_user:
        _log_auth_event(
            db=db,
            user_id=current_user.id,
            action=AuditAction.LOGOUT,
            details="Logout",
            ip_address=_get_request_ip(request),
            sensitivity_level=1
        )
    response = JSONResponse(content={"message": "Logged out successfully"})
    _clear_authenticated_session(response, request)
    return response


@app.post("/api/auth/mfa/setup")
@limiter.limit("5/minute")
async def mfa_setup(
    request: Request,
    db: Session = Depends(get_db),
):
    """Generate or return the TOTP setup payload for a privileged user."""
    user, purpose, _remember_me = _decode_mfa_ticket(
        _resolve_mfa_ticket_from_request(request),
        db,
        expected_purposes={"mfa_setup"},
    )
    if settings.TESTING or not is_privileged_role(user.role):
        raise HTTPException(status_code=400, detail="MFA setup is not required.")

    if user.mfa_enabled:
        raise HTTPException(status_code=409, detail="MFA is already configured.")

    secret = decrypt_secret(user.mfa_secret)
    if not secret:
        secret = generate_totp_secret()
        user.mfa_secret = encrypt_secret(secret)
        db.commit()
        db.refresh(user)

    otpauth_uri = provisioning_uri(secret, user.email or user.username)
    return {
        "mode": purpose,
        "username": user.username,
        "issuer": settings.MFA_TOTP_ISSUER,
        "manual_key": secret,
        "otpauth_uri": otpauth_uri,
        "qr_code_data_url": qr_code_data_url(otpauth_uri),
    }


@app.post("/api/auth/mfa/verify")
@limiter.limit("5/minute")
async def mfa_verify(
    request: Request,
    payload: MFACodeRequest,
    db: Session = Depends(get_db),
):
    """Complete privileged MFA setup or challenge and issue the real session."""
    user, purpose, remember_me = _decode_mfa_ticket(
        _resolve_mfa_ticket_from_request(request),
        db,
        expected_purposes={"mfa_setup", "mfa_challenge"},
    )

    secret = decrypt_secret(user.mfa_secret)
    if not secret:
        raise HTTPException(status_code=400, detail="MFA setup has not started.")
    if not verify_code(secret, payload.code):
        _log_auth_event(
            db=db,
            user_id=user.id,
            action=AuditAction.MFA_FAILED,
            details=f"purpose={purpose}",
            ip_address=_get_request_ip(request),
            sensitivity_level=3,
        )
        raise HTTPException(status_code=401, detail="Invalid verification code.")

    now_utc = datetime.now(timezone.utc)
    if purpose == "mfa_setup":
        # Validate MFA secret is properly set before enabling MFA
        if not user.mfa_secret:
            raise HTTPException(
                status_code=500,
                detail="MFA secret not properly initialized. Please contact support."
            )
        user.mfa_enabled = True
        user.mfa_enrolled_at = now_utc
    user.mfa_last_verified_at = now_utc
    db.commit()
    db.refresh(user)

    access_token_expires = timedelta(
        minutes=(
            settings.ACCESS_TOKEN_EXPIRE_MINUTES_REMEMBER
            if remember_me
            else settings.ACCESS_TOKEN_EXPIRE_MINUTES
        )
    )
    access_token = create_access_token(
        data={"sub": user.username, "role": user.role.value},
        expires_delta=access_token_expires,
    )
    _log_auth_event(
        db=db,
        user_id=user.id,
        action=AuditAction.MFA_VERIFIED,
        details=f"purpose={purpose}",
        ip_address=_get_request_ip(request),
        sensitivity_level=2,
    )

    _mfa_stored_lang = getattr(user, "preferred_language", None)
    _mfa_user_lang = _mfa_stored_lang if _mfa_stored_lang in ("ar", "en") else _resolve_user_language(db, user.id)
    auth_payload = {
        "access_token": access_token,
        "token_type": "bearer",
        "user_lang": _mfa_user_lang,
        "remember_me": remember_me,
        "mfa_required": False,
        "user": {
            "id": user.id,
            "username": user.username,
            "email": user.email,
            "role": user.role.value,
            "must_change_password": requires_password_change(user),
            "mfa_enabled": bool(user.mfa_enabled),
        },
    }
    return _issue_auth_response(auth_payload)


@app.post("/api/auth/refresh")
@limiter.limit("30/minute")
async def refresh_token(
    request: Request,
    current_user: models.User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Refresh access token"""
    from auth import create_access_token
    
    access_token_expires = timedelta(minutes=settings.ACCESS_TOKEN_EXPIRE_MINUTES)
    access_token = create_access_token(
        data={"sub": current_user.username, "role": current_user.role.value},
        expires_delta=access_token_expires
    )

    response = JSONResponse(content={
        "access_token": access_token,
        "token_type": "bearer"
    })
    _set_authenticated_session(
        response,
        access_token=access_token,
        remember_me=False,
    )
    _log_auth_event(
        db=db,
        user_id=current_user.id,
        action=AuditAction.TOKEN_REFRESH,
        details="Access token refreshed",
        ip_address=_get_request_ip(request),
        sensitivity_level=1,
    )
    return response


# Include routers AFTER auth endpoints
app.include_router(admin_router, prefix="/api/admin", tags=["Admin"])
app.include_router(admin_advanced_analytics_router, prefix="/api/admin")


# Jordan Heat Map admin-facing endpoints (canonical route is /api/admin/heat-map/*)
try:
    from heatmap.backend.admin_router import router as admin_heat_map_router
    app.include_router(admin_heat_map_router, prefix="/api")
except Exception as _heat_map_import_exc:
    import logging as _logging
    _logging.getLogger(__name__).warning(
        "Heat map admin router not mounted: %s", _heat_map_import_exc
    )

app.include_router(communication_router, prefix="/comm", tags=["Communication"])
app.include_router(safety_router, prefix="/api", tags=["Safety"])
app.include_router(kpi_router, prefix="/api", tags=["KPI"])
app.include_router(monitoring_router, tags=["Monitoring"])
app.include_router(analytics_router, prefix="/api", tags=["Analytics"])
app.include_router(manager_analytics_router, prefix="/api", tags=["Manager Analytics"])
app.include_router(classification_router, prefix="/api", tags=["Classification"])
app.include_router(dashboard_router)
app.include_router(decision_support_router)
app.include_router(admin_reports_router, prefix="/api/admin")
app.include_router(filter_router)
app.include_router(export_router)
app.include_router(audit_service.router, prefix="/api", tags=["Audit"])
app.include_router(audit_service.admin_router, prefix="/api/admin", tags=["Admin"], include_in_schema=False)
app.include_router(analytics_ws_router)
app.include_router(dr_analytics_router, prefix="/api", tags=["Daily Report Analytics"])
app.include_router(dr_analytics_frontend)
app.include_router(daily_reports_organization_router, prefix="/api", tags=["Daily Reports Organization"])
app.include_router(frontend_router)
app.include_router(parent_router, prefix="/api", tags=["Parent"])
app.include_router(kindergartens_router, prefix="/api", tags=["Kindergartens"])
app.include_router(locations_router, prefix="/api/locations", tags=["Locations"])
app.include_router(enrollment_router, prefix="/api", tags=["Enrollment"])
app.include_router(daily_reports_api_router, prefix="/api", tags=["Daily Reports API"])
app.include_router(children_router, prefix="/api", tags=["Children"])
app.include_router(classes_router, prefix="/api", tags=["Classes"])
app.include_router(attendance_api_router, prefix="/api", tags=["Attendance API"])
app.include_router(registration_router, prefix="/api", tags=["Registration"])
app.include_router(absence_requests_router, prefix="/api", tags=["Absence Requests"])
app.include_router(users_router, prefix="/api", tags=["Users"])
app.include_router(tasks_router, prefix="/api", tags=["Tasks"])
app.include_router(manager_router, prefix="/api", tags=["Manager"])
app.include_router(supervisor_scoped_router)        # prefix /api/supervisor already in router
app.include_router(manager_scoped_router)           # prefix /api/manager already in router
app.include_router(admin_impersonation_router, prefix="/api/admin", tags=["Admin"])
app.include_router(messaging_router, prefix="/api", tags=["Messaging"])
app.include_router(portfolio_router, prefix="/api", tags=["Portfolio"])
app.include_router(government_api_router, prefix="/api", tags=["Government API"])
app.include_router(public_router, prefix="/api", tags=["Public"])
app.include_router(missing_endpoints_router, prefix="/api", tags=["Missing Endpoints"])
# Account self-service for any signed-in role. The /api/admin/profile pair is
# behind require_admin, so managers/supervisors/parents had no audited path to
# edit their own account — see me_endpoints.py.
app.include_router(me_router, prefix="/api/me", tags=["Account"])

app.include_router(charts_router, tags=["Charts"])
app.include_router(analytics_explorer_router, tags=["Analytics Explorer"])
app.include_router(analytics_explorer_page_router)
app.include_router(telemetry_router)
app.include_router(observability_router)

# Heat map ETL/analytics router (legacy /api/heatmap/* path used by the
# standalone React app).  Safe to fail if dependencies (pandas / scipy /
# apscheduler) are missing in the deployed environment.
try:
    from heatmap.backend.api.router import router as heat_map_router
    app.include_router(heat_map_router, prefix="/api/heatmap")
except Exception as _heat_map_router_exc:
    import logging as _logging
    _logging.getLogger(__name__).warning(
        "Heat map ETL router not mounted: %s", _heat_map_router_exc
    )

# WebSocket endpoint for real-time dashboard updates
from dependencies import get_current_user_optional
from realtime_service import websocket_endpoint as realtime_ws_endpoint

@app.websocket("/ws/dashboard")
async def dashboard_websocket(websocket: WebSocket):
    """Real-time dashboard WebSocket endpoint with JWT or session-cookie authentication"""
    from jose import JWTError, jwt as _jwt

    def decode_token(value: str):
        payload = _jwt.decode(value, settings.SECRET_KEY, algorithms=[settings.ALGORITHM])
        if payload.get("purpose"):
            raise JWTError("purpose-scoped token is not an access token")
        username = payload.get("sub")
        if not username:
            raise JWTError("missing subject")
        return username, payload

    token = websocket.query_params.get("token")
    session_token = websocket.cookies.get(settings.SESSION_COOKIE_NAME)
    try:
        username, payload = decode_token(token) if token else (None, None)
    except JWTError:
        if not session_token:
            await websocket.close(code=4001, reason="Invalid or expired token")
            return
        try:
            username, payload = decode_token(session_token)
        except JWTError:
            await websocket.close(code=4001, reason="Invalid or expired token")
            return

    if not username:
        await websocket.close(code=4001, reason="Missing authentication token")
        return

    # Verify user still exists and is active
    db = next(get_db())
    try:
        user = db.query(models.User).filter(
            models.User.username == username, models.User.deleted_at.is_(None)
        ).first()
        if not user or user.status != models.UserStatus.ACTIVE:
            await websocket.close(code=4003, reason="User not found or inactive")
            return
        user_id = str(user.id)
        role = user.role.value.lower()
    finally:
        db.close()

    await realtime_ws_endpoint(websocket, user_id, role)


@app.websocket("/ws/heatmap")
async def heatmap_websocket(websocket: WebSocket):
    """Real-time heatmap WebSocket — streams KPI updates to the Cesium globe every 30 s."""
    from jose import JWTError, jwt as _jwt

    def decode_token(value: str):
        payload = _jwt.decode(value, settings.SECRET_KEY, algorithms=[settings.ALGORITHM])
        if payload.get("purpose"):
            raise JWTError("purpose-scoped token is not an access token")
        username = payload.get("sub")
        if not username:
            raise JWTError("missing subject")
        return username

    token = websocket.query_params.get("token")
    session_token = websocket.cookies.get(settings.SESSION_COOKIE_NAME)
    username = None
    try:
        username = decode_token(token) if token else None
    except JWTError:
        pass
    if not username and session_token:
        try:
            username = decode_token(session_token)
        except JWTError:
            pass
    if not username:
        await websocket.close(code=4001, reason="Authentication required")
        return

    db = next(get_db())
    try:
        user = db.query(models.User).filter(
            models.User.username == username, models.User.deleted_at.is_(None)
        ).first()
        if not user or user.status != models.UserStatus.ACTIVE:
            await websocket.close(code=4003, reason="User not found or inactive")
            return
        if user.role != models.UserRole.ADMIN:
            await websocket.close(code=4003, reason="Admin role required")
            return
    finally:
        db.close()

    await websocket.accept()
    try:
        while True:
            db = next(get_db())
            try:
                from heatmap.backend.service import get_map_overview
                data = get_map_overview(db)
                await websocket.send_json({
                    "type": "kpi_update",
                    "governorates": data.get("governorates", []),
                    "timestamp": now_amman().isoformat(),
                })
            except Exception:
                # Previously `pass`, which hid a NameError here for the whole
                # life of the socket: the client stayed connected and simply
                # never received a frame, with nothing logged. Keep the loop
                # alive on transient errors, but never silently again.
                logger.exception("heatmap websocket kpi_update failed")
            finally:
                db.close()
            await asyncio.sleep(30)
    except Exception:
        pass


@app.websocket("/ws/notify")
async def notify_websocket(websocket: WebSocket):
    """
    Per-user notification WebSocket backed by Redis pub/sub.

    Clients connect with ?token=<jwt> or an active session cookie.
    Messages published via realtime_service.publish_notification(user_id, payload)
    are forwarded to the connected client in real time.
    """
    from jose import JWTError, jwt as _jwt

    def decode_token(value: str) -> str:
        payload = _jwt.decode(value, settings.SECRET_KEY, algorithms=[settings.ALGORITHM])
        if payload.get("purpose"):
            raise JWTError("purpose-scoped token is not an access token")
        sub = payload.get("sub")
        if not sub:
            raise JWTError("missing subject")
        return sub

    token = websocket.query_params.get("token")
    session_token = websocket.cookies.get(settings.SESSION_COOKIE_NAME)
    username = None
    for candidate in [token, session_token]:
        if not candidate:
            continue
        try:
            username = decode_token(candidate)
            break
        except JWTError:
            pass

    if not username:
        await websocket.close(code=4001, reason="Authentication required")
        return

    db = next(get_db())
    try:
        user = db.query(models.User).filter(
            models.User.username == username, models.User.deleted_at.is_(None)
        ).first()
        if not user or user.status != models.UserStatus.ACTIVE:
            await websocket.close(code=4003, reason="User not found or inactive")
            return
        user_id = user.id
    finally:
        db.close()

    await websocket.accept()

    from realtime_service import _NOTIFY_CHANNEL_PREFIX, _get_redis
    channel = f"{_NOTIFY_CHANNEL_PREFIX}{user_id}"

    loop = asyncio.get_event_loop()

    def _listen():
        rc = _get_redis()
        pubsub = rc.pubsub()
        pubsub.subscribe(channel)
        try:
            for message in pubsub.listen():
                if message["type"] == "message":
                    yield message["data"]
        finally:
            pubsub.unsubscribe(channel)
            pubsub.close()

    try:
        async def _stream():
            for raw in await loop.run_in_executor(None, lambda: list(_listen())):
                pass

        # Streaming via thread executor so the Redis blocking call doesn't stall the event loop
        import concurrent.futures
        executor = concurrent.futures.ThreadPoolExecutor(max_workers=1)
        rc = _get_redis()
        pubsub = rc.pubsub()
        pubsub.subscribe(channel)

        try:
            while True:
                message = await loop.run_in_executor(executor, pubsub.get_message, True, 1.0)
                if message and message["type"] == "message":
                    data = message["data"]
                    if isinstance(data, bytes):
                        data = data.decode("utf-8")
                    await websocket.send_text(data)
        finally:
            pubsub.unsubscribe(channel)
            pubsub.close()
            executor.shutdown(wait=False)

    except Exception:
        pass


@app.post("/api/auth/register", status_code=status.HTTP_201_CREATED)
@limiter.limit("10/hour")
async def register(
    request: Request,
    username: str = Form(...),
    email: str = Form(...),
    password: str = Form(...),
    db: Session = Depends(get_db)
):
    """Register a new parent user"""
    # The public page is not the security boundary.  Enforce the same policy
    # here so a caller cannot create accounts by posting to the API directly.
    if not (settings.PUBLIC_REGISTRATION_ENABLED or settings.TESTING):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Public registration is not available",
        )

    from email_validator import EmailNotValidError, validate_email as validate_email_address

    username = username.strip()
    email = email.strip().lower()
    if not username:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Username is required"
        )

    try:
        email = validate_email_address(email, check_deliverability=False).normalized
    except EmailNotValidError as exc:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Invalid email format: {exc}"
        )

    # Validate password complexity
    from auth import validate_password_complexity
    password_errors = validate_password_complexity(password)
    if password_errors:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="; ".join(password_errors)
        )

    # Check if user already exists
    existing = db.query(models.User).filter(
        (models.User.username == username) | (models.User.email == email)
    ).first()

    if existing:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Username or email already registered"
        )

    # This legacy form endpoint cannot collect the mandatory ParentProfile
    # fields. Keeping it live creates login-capable orphan parent accounts.
    raise HTTPException(
        status_code=status.HTTP_410_GONE,
        detail="Use POST /api/register/parent to create a complete parent account.",
    )


# =============================================================================
# Health Check
# =============================================================================

@app.get("/health")
async def health_check(db: Session = Depends(get_db)):
    """Basic health check endpoint with DB connectivity verification"""
    try:
        from importlib.metadata import version as _pkg_version
        _version = _pkg_version("kinjo")
    except Exception:
        _version = "unknown"
    try:
        from sqlalchemy import text
        db.execute(text("SELECT 1"))
        return {"status": "healthy", "app": settings.APP_NAME, "version": _version}
    except (SQLAlchemyError, RuntimeError):
        return JSONResponse(
            status_code=503,
            content={"status": "unhealthy", "app": settings.APP_NAME, "version": _version},
        )


@app.head("/api/health")
async def api_health_check_head(
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_user),
):
    """HEAD reachability probe used by the front-end connectivity heartbeat.

    Any authenticated user (admin, manager, supervisor, ...) may call this — it
    only confirms the backend is reachable and the session is still valid, and
    returns no body. The comprehensive GET /api/health below stays admin-only.
    """
    # HEAD request just checks reachability + valid session - return empty body
    return Response(status_code=200, headers={"X-Health": "OK"})


@app.get("/api/health")
async def api_health_check(
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_user),
):
    """Comprehensive health check with all system components (admin only)"""
    if current_user.role != models.UserRole.ADMIN:
        raise HTTPException(status_code=403, detail="Admin access required")
    health_results = {}
    system_health_score = performance_monitor.get_system_health_score()
    overall_status = "healthy"
    db_status = "unknown"
    try:
        # Run all health checks
        health_results = await health_checker.run_health_checks()

        # Get system health score
        system_health_score = performance_monitor.get_system_health_score()

        # Get overall status
        overall_status = health_checker.get_overall_health_status()

        # Test database connection
        from sqlalchemy import text
        db.execute(text("SELECT 1"))
        db_status = "connected"
    except (SQLAlchemyError, RuntimeError, AttributeError) as e:
        db_status = f"error: {str(e)}"
        overall_status = "unhealthy"

    # Prepare response
    response = {
        "status": overall_status,
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "system_health_score": system_health_score,
        "database": db_status,
        "app": settings.APP_NAME,
        "environment": settings.ENVIRONMENT,
        "services": {}
    }

    # Add service health details
    for service_name, health_check in health_results.items():
        response["services"][service_name] = {
            "status": health_check.status,
            "response_time": round(health_check.response_time, 3),
            "message": health_check.message,
            "timestamp": health_check.timestamp.isoformat(),
            "details": health_check.details
        }

    # Add SMTP health (non-blocking — failure degrades but doesn't mark service unhealthy)
    from email_service import check_smtp_health
    smtp_health = check_smtp_health()
    response["services"]["smtp"] = smtp_health
    if smtp_health.get("status") not in ("ok", "unconfigured"):
        overall_status = "degraded"

    # Set HTTP status code based on overall health
    status_code = 200
    if overall_status == "unhealthy":
        status_code = 503  # Service Unavailable
    elif overall_status == "degraded":
        status_code = 200  # Still OK but with warnings

    return response


@app.get("/api/metrics")
async def get_system_metrics(
    minutes: int = 60,
    current_user: models.User = Depends(get_current_user),
):
    """Get system performance metrics (admin only)"""
    if current_user.role != models.UserRole.ADMIN:
        raise HTTPException(status_code=403, detail="Admin access required")
    try:
        recent_metrics = performance_monitor.get_recent_metrics(minutes)

        if not recent_metrics:
            return {"error": "No metrics available", "minutes_requested": minutes}

        # Convert metrics to dict format
        metrics_data = []
        for metric in recent_metrics:
            metrics_data.append({
                "timestamp": metric.timestamp.isoformat(),
                "cpu_percent": metric.cpu_percent,
                "memory_percent": metric.memory_percent,
                "memory_used_mb": round(metric.memory_used_mb, 2),
                "memory_available_mb": round(metric.memory_available_mb, 2),
                "disk_usage_percent": metric.disk_usage_percent,
                "disk_free_gb": round(metric.disk_free_gb, 2),
                "network_connections": metric.network_connections,
                "active_threads": metric.active_threads,
                "active_coroutines": metric.active_coroutines,
                "db_connections": metric.db_connections,
                "cache_hit_rate": round(metric.cache_hit_rate, 3),
                "response_time_avg": round(metric.response_time_avg, 3),
                "error_rate": round(metric.error_rate, 4)
            })

        # Calculate averages
        if metrics_data:
            avg_metrics = {
                "cpu_percent": round(sum(m["cpu_percent"] for m in metrics_data) / len(metrics_data), 2),
                "memory_percent": round(sum(m["memory_percent"] for m in metrics_data) / len(metrics_data), 2),
                "response_time_avg": round(sum(m["response_time_avg"] for m in metrics_data) / len(metrics_data), 3),
                "error_rate": round(sum(m["error_rate"] for m in metrics_data) / len(metrics_data), 4),
                "cache_hit_rate": round(sum(m["cache_hit_rate"] for m in metrics_data) / len(metrics_data), 3)
            }
        else:
            avg_metrics = {}

        return {
            "metrics": metrics_data,
            "averages": avg_metrics,
            "count": len(metrics_data),
            "time_range_minutes": minutes,
            "system_health_score": performance_monitor.get_system_health_score()
        }

    except (RuntimeError, AttributeError, TypeError) as e:
        return {"error": str(e)}


@app.get("/api/scaling/history")
async def get_scaling_history(
    hours: int = 24,
    current_user: models.User = Depends(get_current_user),
):
    """Get auto-scaling history (admin only)"""
    if current_user.role != models.UserRole.ADMIN:
        raise HTTPException(status_code=403, detail="Admin access required")
    try:
        history = auto_scaler.get_scaling_history(hours)

        scaling_data = []
        for rec in history:
            scaling_data.append({
                "timestamp": rec.timestamp.isoformat(),
                "service": rec.service,
                "action": rec.action,
                "reason": rec.reason,
                "confidence": rec.confidence,
                "metrics": rec.metrics
            })

        return {
            "scaling_history": scaling_data,
            "count": len(scaling_data),
            "time_range_hours": hours
        }

    except (RuntimeError, AttributeError, TypeError) as e:
        return {"error": str(e)}


# Predictive Analytics Endpoints
# =============================================================================

@app.get("/api/analytics/predict/attendance")
async def predict_attendance_rate(
    kindergarten_id: int,
    days_ahead: int = 7,
    current_user: models.User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Predict attendance rate for the next N days"""
    try:
        # Role gate first, then the tenant gate.
        #
        # ManagerScope.assert_kindergarten_access is the canonical IDOR guard: it
        # answers a cross-tenant target with 404 rather than 403, so the response
        # cannot be used to tell an existing kindergarten from an absent one. The
        # inline check it replaces returned 403 (an enumeration oracle) and, worse,
        # exempted SUPERVISOR from the ownership test entirely -- a supervisor could
        # read any kindergarten's analytics.
        if current_user.role not in [models.UserRole.ADMIN, models.UserRole.SUPERVISOR, models.UserRole.MANAGER]:
            raise HTTPException(status_code=403, detail="Insufficient permissions")

        ManagerScope.assert_kindergarten_access(current_user, kindergarten_id)

        prediction = await predictive_analytics.predict_attendance_rate(db, kindergarten_id, days_ahead)

        return {
            "prediction": {
                "type": prediction.prediction_type.value,
                "predicted_value": round(prediction.predicted_value, 2),
                "confidence_interval": [round(prediction.confidence_interval[0], 2), round(prediction.confidence_interval[1], 2)],
                "confidence_level": round(prediction.confidence_level, 3),
                "model_used": prediction.model_used.value,
                "accuracy_score": round(prediction.accuracy_score, 3),
                "historical_data_points": prediction.historical_data_points,
                "prediction_date": prediction.prediction_date.isoformat(),
                "forecast_period_days": prediction.forecast_period_days
            },
            "kindergarten_id": kindergarten_id,
            "generated_at": datetime.now(timezone.utc).isoformat()
        }

    except HTTPException:
        raise
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    except (RuntimeError, AttributeError, TypeError):
        raise HTTPException(status_code=500, detail="Internal server error")


@app.get("/api/analytics/predict/incidents")
async def predict_incident_trend(
    kindergarten_id: int,
    days_ahead: int = 30,
    current_user: models.User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Predict incident trends for risk assessment"""
    try:
        # Role gate first, then the tenant gate.
        #
        # ManagerScope.assert_kindergarten_access is the canonical IDOR guard: it
        # answers a cross-tenant target with 404 rather than 403, so the response
        # cannot be used to tell an existing kindergarten from an absent one. The
        # inline check it replaces returned 403 (an enumeration oracle) and, worse,
        # exempted SUPERVISOR from the ownership test entirely -- a supervisor could
        # read any kindergarten's analytics.
        if current_user.role not in [models.UserRole.ADMIN, models.UserRole.SUPERVISOR, models.UserRole.MANAGER]:
            raise HTTPException(status_code=403, detail="Insufficient permissions")

        ManagerScope.assert_kindergarten_access(current_user, kindergarten_id)

        prediction = await predictive_analytics.predict_incident_trend(db, kindergarten_id, days_ahead)

        return {
            "prediction": {
                "type": prediction.prediction_type.value,
                "predicted_value": round(prediction.predicted_value, 2),
                "confidence_interval": [round(prediction.confidence_interval[0], 2), round(prediction.confidence_interval[1], 2)],
                "confidence_level": round(prediction.confidence_level, 3),
                "model_used": prediction.model_used.value,
                "accuracy_score": round(prediction.accuracy_score, 3),
                "historical_data_points": prediction.historical_data_points,
                "prediction_date": prediction.prediction_date.isoformat(),
                "forecast_period_days": prediction.forecast_period_days
            },
            "kindergarten_id": kindergarten_id,
            "generated_at": datetime.now(timezone.utc).isoformat()
        }

    except HTTPException:
        raise
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    except (RuntimeError, AttributeError, TypeError):
        raise HTTPException(status_code=500, detail="Internal server error")


@app.get("/api/analytics/predict/capacity")
async def predict_capacity_utilization(
    kindergarten_id: int,
    days_ahead: int = 90,
    current_user: models.User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Predict capacity utilization trends"""
    try:
        # Role gate first, then the tenant gate.
        #
        # ManagerScope.assert_kindergarten_access is the canonical IDOR guard: it
        # answers a cross-tenant target with 404 rather than 403, so the response
        # cannot be used to tell an existing kindergarten from an absent one. The
        # inline check it replaces returned 403 (an enumeration oracle) and, worse,
        # exempted SUPERVISOR from the ownership test entirely -- a supervisor could
        # read any kindergarten's analytics.
        if current_user.role not in [models.UserRole.ADMIN, models.UserRole.SUPERVISOR, models.UserRole.MANAGER]:
            raise HTTPException(status_code=403, detail="Insufficient permissions")

        ManagerScope.assert_kindergarten_access(current_user, kindergarten_id)

        prediction = await predictive_analytics.predict_capacity_utilization(db, kindergarten_id, days_ahead)

        return {
            "prediction": {
                "type": prediction.prediction_type.value,
                "predicted_value": round(prediction.predicted_value, 2),
                "confidence_interval": [round(prediction.confidence_interval[0], 2), round(prediction.confidence_interval[1], 2)],
                "confidence_level": round(prediction.confidence_level, 3),
                "model_used": prediction.model_used.value,
                "accuracy_score": round(prediction.accuracy_score, 3),
                "historical_data_points": prediction.historical_data_points,
                "prediction_date": prediction.prediction_date.isoformat(),
                "forecast_period_days": prediction.forecast_period_days
            },
            "kindergarten_id": kindergarten_id,
            "generated_at": datetime.now(timezone.utc).isoformat()
        }

    except HTTPException:
        raise
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    except (RuntimeError, AttributeError, TypeError):
        raise HTTPException(status_code=500, detail="Internal server error")


@app.get("/api/analytics/predict/enrollment")
async def predict_enrollment_trend(
    kindergarten_id: int,
    days_ahead: int = 30,
    current_user: models.User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Predict enrollment application trends for a kindergarten"""
    try:
        # Enrollment prediction is admin/manager only — supervisors are excluded by
        # the role gate rather than by the tenant gate, so the canonical scope check
        # below still applies to whoever gets past it. See the note on the other
        # predict endpoints: a cross-tenant target must answer 404, not 403.
        if current_user.role not in [models.UserRole.ADMIN, models.UserRole.MANAGER]:
            raise HTTPException(status_code=403, detail="Insufficient permissions")

        ManagerScope.assert_kindergarten_access(current_user, kindergarten_id)

        prediction = await predictive_analytics.predict_enrollment_trend(db, kindergarten_id, days_ahead)

        return {
            "prediction": {
                "type": prediction.prediction_type.value,
                "predicted_value": round(prediction.predicted_value, 2),
                "confidence_interval": [
                    round(prediction.confidence_interval[0], 2),
                    round(prediction.confidence_interval[1], 2),
                ],
                "confidence_level": round(prediction.confidence_level, 3),
                "model_used": prediction.model_used.value,
                "accuracy_score": round(prediction.accuracy_score, 3),
                "historical_data_points": prediction.historical_data_points,
                "prediction_date": prediction.prediction_date.isoformat(),
                "forecast_period_days": prediction.forecast_period_days,
            },
            "kindergarten_id": kindergarten_id,
            "generated_at": datetime.now(timezone.utc).isoformat(),
        }

    except HTTPException:
        raise
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    except (RuntimeError, AttributeError, TypeError):
        raise HTTPException(status_code=500, detail="Internal server error")


@app.get("/api/analytics/trends/{metric_type}")
async def analyze_trends(
    kindergarten_id: int,
    metric_type: str,
    days: int = 365,
    current_user: models.User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Perform comprehensive trend analysis"""
    try:
        # Role gate first, then the tenant gate.
        #
        # ManagerScope.assert_kindergarten_access is the canonical IDOR guard: it
        # answers a cross-tenant target with 404 rather than 403, so the response
        # cannot be used to tell an existing kindergarten from an absent one. The
        # inline check it replaces returned 403 (an enumeration oracle) and, worse,
        # exempted SUPERVISOR from the ownership test entirely -- a supervisor could
        # read any kindergarten's analytics.
        if current_user.role not in [models.UserRole.ADMIN, models.UserRole.SUPERVISOR, models.UserRole.MANAGER]:
            raise HTTPException(status_code=403, detail="Insufficient permissions")

        ManagerScope.assert_kindergarten_access(current_user, kindergarten_id)

        # Validate metric type
        valid_metrics = ["attendance", "incidents", "capacity"]
        if metric_type not in valid_metrics:
            raise HTTPException(status_code=400, detail=f"Invalid metric type. Must be one of: {', '.join(valid_metrics)}")

        trend_analysis = await predictive_analytics.analyze_trends(db, kindergarten_id, metric_type, days)

        return {
            "trend_analysis": {
                "trend_direction": trend_analysis.trend_direction,
                "trend_strength": round(trend_analysis.trend_strength, 3),
                "seasonality_detected": trend_analysis.seasonality_detected,
                "change_points": [cp.isoformat() for cp in trend_analysis.change_points],
                "forecast_values": [round(v, 2) for v in trend_analysis.forecast_values],
                "forecast_dates": [d.isoformat() for d in trend_analysis.forecast_dates],
                "r_squared": round(trend_analysis.r_squared, 3),
                "mean_absolute_error": round(trend_analysis.mean_absolute_error, 3)
            },
            "kindergarten_id": kindergarten_id,
            "metric_type": metric_type,
            "analysis_period_days": days,
            "generated_at": datetime.now(timezone.utc).isoformat()
        }

    except HTTPException:
        raise
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    except (RuntimeError, AttributeError, TypeError):
        raise HTTPException(status_code=500, detail="Internal server error")


@app.get("/api/analytics/predictive-insights")
async def get_predictive_insights(
    kindergarten_id: int,
    current_user: models.User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Generate comprehensive predictive insights"""
    try:
        # Role gate first, then the tenant gate.
        #
        # ManagerScope.assert_kindergarten_access is the canonical IDOR guard: it
        # answers a cross-tenant target with 404 rather than 403, so the response
        # cannot be used to tell an existing kindergarten from an absent one. The
        # inline check it replaces returned 403 (an enumeration oracle) and, worse,
        # exempted SUPERVISOR from the ownership test entirely -- a supervisor could
        # read any kindergarten's analytics.
        if current_user.role not in [models.UserRole.ADMIN, models.UserRole.SUPERVISOR, models.UserRole.MANAGER]:
            raise HTTPException(status_code=403, detail="Insufficient permissions")

        ManagerScope.assert_kindergarten_access(current_user, kindergarten_id)

        insights = await predictive_analytics.get_predictive_insights(db, kindergarten_id)

        return {
            "insights": insights,
            "kindergarten_id": kindergarten_id,
            "generated_at": datetime.now(timezone.utc).isoformat()
        }

    except HTTPException:
        raise
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    except (RuntimeError, AttributeError, TypeError):
        raise HTTPException(status_code=500, detail="Internal server error")


@app.get("/api/dev/auto-login")
async def dev_auto_login(
    request: Request,
    role: str = "admin",
    db: Session = Depends(get_db),
):
    """
    Development-only auto-login endpoint.
    Only available when TESTING=true and ENVIRONMENT=development.
    Returns a session cookie for immediate testing without manual auth.
    """
    if settings.ENVIRONMENT.lower() == "production":
        raise HTTPException(status_code=404, detail="Not found")
    if not settings.TESTING:
        raise HTTPException(status_code=404, detail="Not found")

    role = role.lower()
    username_map = {
        "admin": "admin",
        "manager": "manager1",
        "manager1": "manager1",
        "manager2": "manager2",
        "supervisor": "supervisor1",
        "supervisor1": "supervisor1",
        "supervisor2": "supervisor2",
        "parent": "parent1",
        "parent1": "parent1",
        "parent2": "parent2",
    }

    if role not in username_map:
        raise HTTPException(status_code=400, detail="Invalid role. Use: admin, manager, supervisor, parent")

    username = username_map[role]
    user = db.query(models.User).filter(models.User.username == username).first()
    if not user:
        raise HTTPException(status_code=404, detail=f"User '{username}' not found in database")

    access_token_expires = timedelta(minutes=settings.ACCESS_TOKEN_EXPIRE_MINUTES_REMEMBER)
    access_token = create_access_token(
        data={"sub": user.username, "role": user.role.value},
        expires_delta=access_token_expires,
    )

    response = JSONResponse(content={
        "access_token": access_token,
        "token_type": "bearer",
        "user": {
            "id": user.id,
            "username": user.username,
            "email": user.email,
            "role": user.role.value,
        }
    })
    _set_authenticated_session(response, access_token=access_token, remember_me=True)
    _set_ui_language_cookie(response, "ar")
    return response


# Note: When running with `python -m uvicorn main:app`, don't use the code below
# The if __name__ == "__main__" block is only for running with `python main.py`
if __name__ == "__main__":
    import uvicorn
    uvicorn.run("main:app", host="127.0.0.1", port=8000, reload=False)


