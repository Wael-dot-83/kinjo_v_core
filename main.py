"""
KInJo - Kindergarten Management Platform
Main FastAPI Application
"""
from datetime import timedelta
from typing import Optional
from fastapi import FastAPI, Depends, HTTPException, status, Request, Response, Form
from fastapi.security import OAuth2PasswordRequestForm
from fastapi.staticfiles import StaticFiles
from fastapi.middleware.cors import CORSMiddleware
from starlette.middleware.base import BaseHTTPMiddleware
from contextlib import asynccontextmanager
from sqlalchemy.orm import Session
from sqlalchemy import text
from slowapi import Limiter, _rate_limit_exceeded_handler
from slowapi.util import get_remote_address
from slowapi.errors import RateLimitExceeded
from apscheduler.schedulers.asyncio import AsyncIOScheduler


class UTF8ContentTypeMiddleware(BaseHTTPMiddleware):
    """Middleware to ensure UTF-8 Content-Type for HTML responses"""
    async def dispatch(self, request: Request, call_next):
        response = await call_next(request)
        content_type = response.headers.get("content-type", "")
        if "text/html" in content_type and "charset" not in content_type:
            response.headers["content-type"] = "text/html; charset=utf-8"
        return response


class SecurityHeadersMiddleware(BaseHTTPMiddleware):
    """Add HTTP security headers to all responses"""
    async def dispatch(self, request: Request, call_next):
        response = await call_next(request)
        response.headers["X-Content-Type-Options"] = "nosniff"
        response.headers["X-Frame-Options"] = "DENY"
        response.headers["X-XSS-Protection"] = "1; mode=block"
        response.headers["Referrer-Policy"] = "strict-origin-when-cross-origin"
        if settings.ENVIRONMENT == "production":
            response.headers["Strict-Transport-Security"] = "max-age=31536000; includeSubDomains"
        return response

import models
from database import get_db, init_db
from auth import authenticate_user, create_access_token, get_password_hash
from config import settings, validate_production_settings
from dependencies import get_current_user, get_current_user_optional, RedirectToLogin
from fastapi.responses import RedirectResponse, JSONResponse
import validators

# Safety guard: never allow TESTING bypass in production
def ensure_not_testing_in_production() -> None:
    if settings.ENVIRONMENT.lower() == "production" and settings.TESTING:
        raise RuntimeError("Refusing to start with TESTING=true in production environment.")

ensure_not_testing_in_production()

# Rate limiter setup — use Redis backend when REDIS_URL is set and reachable;
# falls back to in-memory storage so the app starts cleanly without Redis.
def _build_limiter() -> Limiter:
    try:
        import redis as _redis
        _redis.from_url(settings.REDIS_URL).ping()
        lim = Limiter(key_func=get_remote_address, storage_uri=settings.REDIS_URL)
    except Exception:
        lim = Limiter(key_func=get_remote_address)
    return lim

limiter = _build_limiter()
# Disable rate limiting during automated tests to avoid flakiness
if settings.TESTING:
    limiter.enabled = False

# Import routers
from missing_endpoints import router as api_router
from frontend import router as frontend_router
from communication_service import router as communication_router
from safety_service import router as safety_router
from curriculum_service import router as curriculum_router
from kpi_service import router as kpi_router
from analytics_service import router as analytics_router
from analytics_ws import router as analytics_ws_router
from government_api import router as government_router
from routers.ai import router as ai_router
from routers.supervisor import router as supervisor_router
from routers.manager import router as manager_router
from routers.admin_impersonation import router as admin_impersonation_router
from routers.messaging import router as messaging_router

# =============================================================================
# Scheduled Jobs
# =============================================================================

async def expire_waitlist_entries() -> None:
    """Mark waitlist offers as EXPIRED when their offer_expiry_at has passed."""
    from database import SessionLocal
    db = SessionLocal()
    try:
        db.execute(
            text(
                "UPDATE waitlist_entries "
                "SET status = 'EXPIRED' "
                "WHERE status = 'OFFERED' "
                "  AND offer_expiry_at IS NOT NULL "
                "  AND offer_expiry_at < NOW()"
            )
        )
        db.commit()
    except Exception:
        db.rollback()
    finally:
        db.close()


# =============================================================================
# Lifespan Event Handler
# =============================================================================

@asynccontextmanager
async def lifespan(app: FastAPI):
    """Handle application startup and shutdown events"""
    # Startup
    validate_production_settings()
    init_db()
    from ai.insights import generate_daily_insights
    from ai.llm import run_llm_daily_jobs
    from ai.ml import run_ml_daily_jobs
    from ai.embeddings import run_embedding_daily_jobs
    from government_api import refresh_development_dashboard
    scheduler = AsyncIOScheduler()
    scheduler.add_job(expire_waitlist_entries,    "interval", minutes=15, id="expire_waitlist")
    scheduler.add_job(generate_daily_insights,    "cron", hour=2, minute=0,  id="ai_daily_insights")
    scheduler.add_job(refresh_development_dashboard, "cron", hour=3, minute=0, id="refresh_dev_dashboard")
    scheduler.add_job(run_llm_daily_jobs,         "cron", hour=3, minute=30, id="llm_daily_jobs")
    scheduler.add_job(run_ml_daily_jobs,          "cron", hour=4, minute=0,  id="ml_daily_jobs")
    scheduler.add_job(run_embedding_daily_jobs,   "cron", hour=5, minute=0,  id="embedding_daily_jobs")
    scheduler.start()
    yield
    # Shutdown
    scheduler.shutdown(wait=False)


# Create FastAPI application
app = FastAPI(
    title="KInJo - Kindergarten Management Platform",
    description="Enterprise-grade management system for kindergartens in Jordan",
    version="1.0.0",
    docs_url="/docs" if settings.API_DOCS_ENABLED else None,
    redoc_url="/redoc" if settings.API_DOCS_ENABLED else None,
    lifespan=lifespan
)

# Add rate limiter to app state
app.state.limiter = limiter
app.add_exception_handler(RateLimitExceeded, _rate_limit_exceeded_handler)


# Handle redirect to login for unauthenticated frontend requests
@app.exception_handler(RedirectToLogin)
async def redirect_to_login_handler(request: Request, exc: RedirectToLogin):
    return RedirectResponse(url=exc.redirect_url, status_code=302)

# CORS middleware - origins controlled via CORS_ALLOWED_ORIGINS in .env
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.CORS_ALLOWED_ORIGINS,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Add security headers to all responses
app.add_middleware(SecurityHeadersMiddleware)
# Add UTF-8 Content-Type middleware for proper Arabic text encoding
app.add_middleware(UTF8ContentTypeMiddleware)

# Mount static files
try:
    app.mount("/static", StaticFiles(directory="static"), name="static")
except:
    pass  # Static folder might not exist


@app.get("/favicon.ico", include_in_schema=False)
async def favicon():
    return Response(status_code=204)


# =============================================================================
# Authentication Endpoints (defined BEFORE routers to take precedence)
# =============================================================================

def _get_request_ip(request: Request) -> Optional[str]:
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
    except Exception:
        # Avoid blocking auth flows if audit logging fails.
        pass


async def _do_login(request: Request, form_data: OAuth2PasswordRequestForm, db: Session):
    """Internal login logic"""
    ip_address = _get_request_ip(request)
    form = await request.form()
    remember_raw = form.get("remember_me")
    remember_me = str(remember_raw).lower() in {"1", "true", "on", "yes"}
    user = authenticate_user(db, form_data.username, form_data.password)
    if not user:
        _log_auth_event(
            db=db,
            user_id=None,
            action="LOGIN_FAILED",
            details=f"username={form_data.username}",
            ip_address=ip_address,
            sensitivity_level=3
        )
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Incorrect username or password",
            headers={"WWW-Authenticate": "Bearer"},
        )

    access_token_expires = timedelta(
        minutes=(
            settings.ACCESS_TOKEN_EXPIRE_MINUTES_REMEMBER
            if remember_me
            else settings.ACCESS_TOKEN_EXPIRE_MINUTES
        )
    )
    access_token = create_access_token(
        data={"sub": user.username, "role": user.role.value},
        expires_delta=access_token_expires
    )

    _log_auth_event(
        db=db,
        user_id=user.id,
        action="LOGIN_SUCCESS",
        details=f"Login successful (remember_me={remember_me})",
        ip_address=ip_address,
        sensitivity_level=2
    )

    return {
        "access_token": access_token,
        "token_type": "bearer",
        "user": {
            "id": user.id,
            "username": user.username,
            "email": user.email,
            "role": user.role.value
        }
    }


@app.post("/token")
@limiter.limit("5/minute")  # Rate limit: 5 login attempts per minute per IP
async def token_login(
    request: Request,
    form_data: OAuth2PasswordRequestForm = Depends(),
    db: Session = Depends(get_db)
):
    """OAuth2 token endpoint (for frontend)"""
    return await _do_login(request, form_data, db)


@app.post("/api/auth/login")
@limiter.limit("5/minute")  # Rate limit: 5 login attempts per minute per IP
async def api_login(
    request: Request,
    form_data: OAuth2PasswordRequestForm = Depends(),
    db: Session = Depends(get_db)
):
    """API login endpoint"""
    return await _do_login(request, form_data, db)


@app.post("/api/auth/logout")
async def logout(
    request: Request,
    current_user: Optional[models.User] = Depends(get_current_user_optional),
    db: Session = Depends(get_db)
):
    """Logout endpoint - clears the session cookie and invalidates the token"""
    if current_user:
        _log_auth_event(
            db=db,
            user_id=current_user.id,
            action="LOGOUT",
            details="Logout",
            ip_address=_get_request_ip(request),
            sensitivity_level=1
        )
    response = JSONResponse(content={"message": "Logged out successfully"})
    response.delete_cookie(
        key="kinjo_token",
        path="/",
        samesite="lax",
    )
    return response


@app.post("/api/auth/refresh")
async def refresh_token(
    current_user: models.User = Depends(get_current_user)
):
    """Refresh access token"""
    from auth import create_access_token
    
    access_token_expires = timedelta(minutes=settings.ACCESS_TOKEN_EXPIRE_MINUTES)
    access_token = create_access_token(
        data={"sub": current_user.username, "role": current_user.role.value},
        expires_delta=access_token_expires
    )
    
    return {
        "access_token": access_token,
        "token_type": "bearer"
    }


# Include routers AFTER auth endpoints
app.include_router(api_router, prefix="/api", tags=["API"])
app.include_router(communication_router, prefix="/comm", tags=["Communication"])
app.include_router(safety_router, prefix="/api", tags=["Safety"])
app.include_router(curriculum_router, prefix="/api", tags=["Curriculum"])
app.include_router(kpi_router, prefix="/api", tags=["KPI"])
app.include_router(analytics_router, prefix="/api", tags=["Analytics"])
app.include_router(analytics_ws_router)
app.include_router(government_router, prefix="/api", tags=["Government"])
app.include_router(ai_router, prefix="/api", tags=["AI"])
app.include_router(supervisor_router)   # prefix already contains /api/supervisor
app.include_router(manager_router)      # prefix already contains /api/manager
app.include_router(admin_impersonation_router, prefix="/api", tags=["Admin"])
app.include_router(messaging_router, prefix="/api", tags=["Messaging"])
app.include_router(frontend_router)


@app.post("/api/auth/register", status_code=status.HTTP_201_CREATED)
@limiter.limit("3/minute")
async def register(
    request: Request,
    username: str = Form(...),
    email: str = Form(...),
    password: str = Form(...),
    db: Session = Depends(get_db)
):
    """Register a new parent user"""
    # Check if user already exists
    existing = db.query(models.User).filter(
        (models.User.username == username) | (models.User.email == email)
    ).first()

    if existing:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Username or email already registered"
        )

    # Create user
    user = models.User(
        username=username,
        email=email,
        hashed_password=get_password_hash(password),
        role=models.UserRole.PARENT,
        status=models.UserStatus.ACTIVE
    )

    db.add(user)
    db.commit()
    db.refresh(user)

    return {"message": "User registered successfully", "user_id": user.id}


# =============================================================================
# Health Check
# =============================================================================

@app.get("/health")
async def health_check():
    """Health check endpoint"""
    return {"status": "healthy", "app": settings.APP_NAME, "version": "1.0.0"}


@app.get("/api/health")
async def api_health_check(db: Session = Depends(get_db)):
    """API health check with database connection test"""
    try:
        # Test database connection
        from sqlalchemy import text
        db.execute(text("SELECT 1"))
        db_status = "connected"
    except Exception as e:
        db_status = f"error: {str(e)}"

    return {
        "status": "healthy",
        "database": db_status,
        "app": settings.APP_NAME,
        "environment": settings.ENVIRONMENT
    }


# Note: When running with `python -m uvicorn main:app`, don't use the code below
# The if __name__ == "__main__" block is only for running with `python main.py`
if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="127.0.0.1", port=8000, reload=True)

