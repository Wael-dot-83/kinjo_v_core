"""
KInJo - Kindergarten Management Platform
Main FastAPI Application
"""
from datetime import timedelta
from fastapi import FastAPI, Depends, HTTPException, status, Request, Response
from fastapi.security import OAuth2PasswordRequestForm
from fastapi.staticfiles import StaticFiles
from fastapi.middleware.cors import CORSMiddleware
from starlette.middleware.base import BaseHTTPMiddleware
from contextlib import asynccontextmanager
from sqlalchemy.orm import Session
from slowapi import Limiter, _rate_limit_exceeded_handler
from slowapi.util import get_remote_address
from slowapi.errors import RateLimitExceeded


class UTF8ContentTypeMiddleware(BaseHTTPMiddleware):
    """Middleware to ensure UTF-8 Content-Type for HTML responses"""
    async def dispatch(self, request: Request, call_next):
        response = await call_next(request)
        content_type = response.headers.get("content-type", "")
        if "text/html" in content_type and "charset" not in content_type:
            response.headers["content-type"] = "text/html; charset=utf-8"
        return response

import models
from database import get_db, init_db
from auth import authenticate_user, create_access_token, get_password_hash
from config import settings
from dependencies import get_current_user, RedirectToLogin
from fastapi.responses import RedirectResponse

# Rate limiter setup
limiter = Limiter(key_func=get_remote_address)

# Import routers
from missing_endpoints import router as api_router
from frontend import router as frontend_router
from communication_service import router as communication_router
from safety_service import router as safety_router
from curriculum_service import router as curriculum_router
from kpi_service import router as kpi_router
from analytics_service import router as analytics_router

# =============================================================================
# Lifespan Event Handler
# =============================================================================

@asynccontextmanager
async def lifespan(app: FastAPI):
    """Handle application startup and shutdown events"""
    # Startup
    init_db()
    yield
    # Shutdown (if needed)


# Create FastAPI application
app = FastAPI(
    title="KInJo - Kindergarten Management Platform",
    description="Enterprise-grade management system for kindergartens in Jordan",
    version="1.0.0",
    docs_url="/docs",
    redoc_url="/redoc",
    lifespan=lifespan
)

# Add rate limiter to app state
app.state.limiter = limiter
app.add_exception_handler(RateLimitExceeded, _rate_limit_exceeded_handler)


# Handle redirect to login for unauthenticated frontend requests
@app.exception_handler(RedirectToLogin)
async def redirect_to_login_handler(request: Request, exc: RedirectToLogin):
    return RedirectResponse(url=exc.redirect_url, status_code=302)

# CORS middleware - restrict origins in production
ALLOWED_ORIGINS = [
    "http://127.0.0.1:8000",
    "http://localhost:8000",
]
# Add production domain when deployed
if settings.ENVIRONMENT == "production":
    ALLOWED_ORIGINS = [
        "https://kinjo.jo",  # Replace with actual production domain
        "https://www.kinjo.jo",
    ]

app.add_middleware(
    CORSMiddleware,
    allow_origins=ALLOWED_ORIGINS if settings.ENVIRONMENT == "production" else ["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Add UTF-8 Content-Type middleware for proper Arabic text encoding
app.add_middleware(UTF8ContentTypeMiddleware)

# Mount static files
try:
    app.mount("/static", StaticFiles(directory="static"), name="static")
except:
    pass  # Static folder might not exist


# =============================================================================
# Authentication Endpoints (defined BEFORE routers to take precedence)
# =============================================================================

async def _do_login(form_data: OAuth2PasswordRequestForm, db: Session):
    """Internal login logic"""
    user = authenticate_user(db, form_data.username, form_data.password)
    if not user:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Incorrect username or password",
            headers={"WWW-Authenticate": "Bearer"},
        )

    access_token_expires = timedelta(minutes=settings.ACCESS_TOKEN_EXPIRE_MINUTES)
    access_token = create_access_token(
        data={"sub": user.username, "role": user.role.value},
        expires_delta=access_token_expires
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
    return await _do_login(form_data, db)


@app.post("/api/auth/login")
@limiter.limit("5/minute")  # Rate limit: 5 login attempts per minute per IP
async def api_login(
    request: Request,
    form_data: OAuth2PasswordRequestForm = Depends(),
    db: Session = Depends(get_db)
):
    """API login endpoint"""
    return await _do_login(form_data, db)


@app.post("/api/auth/logout")
async def logout():
    """Logout endpoint - client should clear tokens"""
    return {"message": "Logged out successfully"}


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
app.include_router(frontend_router)


@app.post("/api/auth/register", status_code=status.HTTP_201_CREATED)
async def register(
    username: str,
    email: str,
    password: str,
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

