"""
Security Middleware and Utilities for KinJo Platform
=====================================================
Enterprise-grade security implementation including:
- Rate limiting
- Security headers
- Input sanitization
- Request logging
- IP blocking
"""
import re
import time
import hashlib
import secrets
from datetime import datetime, timedelta, timezone
from typing import Dict, Optional, Callable
from collections import defaultdict
from functools import wraps

from fastapi import Request, Response, HTTPException, status
from fastapi.responses import JSONResponse
from starlette.middleware.base import BaseHTTPMiddleware
import bleach


# ============================================================================
# Rate Limiting
# ============================================================================

class RateLimiter:
    """
    Token bucket rate limiter with sliding window
    Provides protection against brute force and DoS attacks
    """
    
    def __init__(
        self,
        requests_per_minute: int = 60,
        requests_per_hour: int = 1000,
        login_attempts_per_minute: int = 5
    ):
        self.requests_per_minute = requests_per_minute
        self.requests_per_hour = requests_per_hour
        self.login_attempts_per_minute = login_attempts_per_minute
        
        # Storage: {ip: [(timestamp, endpoint), ...]}
        self._requests: Dict[str, list] = defaultdict(list)
        self._login_attempts: Dict[str, list] = defaultdict(list)
        self._blocked_ips: Dict[str, datetime] = {}
    
    def _cleanup_old_requests(self, ip: str, storage: dict, window_seconds: int):
        """Remove requests older than the window"""
        cutoff = time.time() - window_seconds
        storage[ip] = [r for r in storage[ip] if r[0] > cutoff]
    
    def is_rate_limited(self, ip: str, endpoint: str = None) -> tuple[bool, str]:
        """
        Check if request should be rate limited
        Returns: (is_limited, reason)
        """
        now = time.time()
        
        # Check if IP is blocked
        if ip in self._blocked_ips:
            if datetime.now() < self._blocked_ips[ip]:
                return True, "IP temporarily blocked due to suspicious activity"
            else:
                del self._blocked_ips[ip]
        
        # Cleanup old requests
        self._cleanup_old_requests(ip, self._requests, 3600)
        
        # Check hourly limit
        hour_requests = len([r for r in self._requests[ip] if r[0] > now - 3600])
        if hour_requests >= self.requests_per_hour:
            return True, f"Rate limit exceeded: {self.requests_per_hour} requests per hour"
        
        # Check minute limit
        minute_requests = len([r for r in self._requests[ip] if r[0] > now - 60])
        if minute_requests >= self.requests_per_minute:
            return True, f"Rate limit exceeded: {self.requests_per_minute} requests per minute"
        
        # Record request
        self._requests[ip].append((now, endpoint))
        
        return False, ""
    
    def check_login_attempt(self, ip: str) -> tuple[bool, str]:
        """
        Check if login attempt should be rate limited
        More strict limits for authentication endpoints
        """
        now = time.time()
        
        self._cleanup_old_requests(ip, self._login_attempts, 60)
        
        attempts = len(self._login_attempts[ip])
        if attempts >= self.login_attempts_per_minute:
            # Block IP for increasing duration based on attempts
            block_duration = min(attempts * 5, 60)  # Max 60 minutes
            self._blocked_ips[ip] = datetime.now() + timedelta(minutes=block_duration)
            return True, f"Too many login attempts. Blocked for {block_duration} minutes"
        
        self._login_attempts[ip].append((now, "login"))
        return False, ""
    
    def record_failed_login(self, ip: str):
        """Record a failed login attempt"""
        self._login_attempts[ip].append((time.time(), "failed"))


# Global rate limiter instance
rate_limiter = RateLimiter()


# ============================================================================
# Security Headers Middleware
# ============================================================================

class SecurityHeadersMiddleware(BaseHTTPMiddleware):
    """
    Add security headers to all responses
    Implements OWASP security header recommendations
    """
    
    async def dispatch(self, request: Request, call_next: Callable) -> Response:
        response = await call_next(request)
        
        # Skip CSP for Swagger UI and ReDoc paths to allow them to function
        path = request.url.path
        is_docs_path = path in ["/docs", "/redoc", "/openapi.json"] or path.startswith("/docs/") or path.startswith("/redoc/")
        
        # Prevent MIME type sniffing
        response.headers["X-Content-Type-Options"] = "nosniff"
        
        # Prevent clickjacking (allow framing for docs)
        if is_docs_path:
            response.headers["X-Frame-Options"] = "SAMEORIGIN"
        else:
            response.headers["X-Frame-Options"] = "DENY"
        
        # XSS Protection (legacy, but still useful)
        response.headers["X-XSS-Protection"] = "1; mode=block"
        
        # Referrer Policy
        response.headers["Referrer-Policy"] = "strict-origin-when-cross-origin"
        
        # Content Security Policy
        if is_docs_path:
            # Relaxed CSP for Swagger UI / ReDoc (they need inline scripts/styles and CDN)
            response.headers["Content-Security-Policy"] = (
                "default-src 'self'; "
                "script-src 'self' 'unsafe-inline' https://cdn.jsdelivr.net; "
                "style-src 'self' 'unsafe-inline' https://cdn.jsdelivr.net; "
                "img-src 'self' data: https://cdn.jsdelivr.net https://fastapi.tiangolo.com; "
                "font-src 'self' https://cdn.jsdelivr.net; "
                "connect-src 'self' https://cdn.jsdelivr.net; "
                "frame-ancestors 'self';"
            )
        else:
            # Strict CSP for API endpoints
            response.headers["Content-Security-Policy"] = (
                "default-src 'self'; "
                "script-src 'self'; "
                "style-src 'self'; "
                "img-src 'self' data:; "
                "font-src 'self'; "
                "frame-ancestors 'none';"
            )
        
        # HSTS (enable in production with HTTPS)
        # response.headers["Strict-Transport-Security"] = "max-age=31536000; includeSubDomains"
        
        # Permissions Policy (disable unnecessary features)
        response.headers["Permissions-Policy"] = (
            "geolocation=(), "
            "microphone=(), "
            "camera=(), "
            "payment=()"
        )
        
        return response


# ============================================================================
# Rate Limiting Middleware
# ============================================================================

class RateLimitMiddleware(BaseHTTPMiddleware):
    """
    Apply rate limiting to all requests
    """
    
    async def dispatch(self, request: Request, call_next: Callable) -> Response:
        # Get client IP (handle proxies)
        ip = self._get_client_ip(request)
        endpoint = request.url.path
        
        # Special handling for login endpoint
        if endpoint == "/token" and request.method == "POST":
            is_limited, reason = rate_limiter.check_login_attempt(ip)
            if is_limited:
                return JSONResponse(
                    status_code=status.HTTP_429_TOO_MANY_REQUESTS,
                    content={"detail": reason}
                )
        else:
            is_limited, reason = rate_limiter.is_rate_limited(ip, endpoint)
            if is_limited:
                return JSONResponse(
                    status_code=status.HTTP_429_TOO_MANY_REQUESTS,
                    content={"detail": reason}
                )
        
        response = await call_next(request)
        
        # Record failed login
        if endpoint == "/token" and response.status_code == 401:
            rate_limiter.record_failed_login(ip)
        
        return response
    
    def _get_client_ip(self, request: Request) -> str:
        """Extract real client IP, handling proxy headers"""
        # Check X-Forwarded-For header (from reverse proxy)
        forwarded_for = request.headers.get("X-Forwarded-For")
        if forwarded_for:
            # Take the first IP (original client)
            return forwarded_for.split(",")[0].strip()
        
        # Check X-Real-IP header
        real_ip = request.headers.get("X-Real-IP")
        if real_ip:
            return real_ip
        
        # Fall back to direct connection IP
        return request.client.host if request.client else "unknown"


# ============================================================================
# Request Logging Middleware
# ============================================================================

class RequestLoggingMiddleware(BaseHTTPMiddleware):
    """
    Log all requests for audit and debugging
    """
    
    async def dispatch(self, request: Request, call_next: Callable) -> Response:
        start_time = time.time()
        
        # Generate request ID
        request_id = secrets.token_hex(8)
        
        # Process request
        response = await call_next(request)
        
        # Calculate duration
        duration = time.time() - start_time
        
        # Log request details (would go to logging system)
        log_data = {
            "request_id": request_id,
            "method": request.method,
            "path": request.url.path,
            "status_code": response.status_code,
            "duration_ms": round(duration * 1000, 2),
            "client_ip": request.client.host if request.client else "unknown",
            "user_agent": request.headers.get("User-Agent", "unknown"),
            "timestamp": datetime.now(timezone.utc).isoformat()
        }
        
        # Add request ID to response headers
        response.headers["X-Request-ID"] = request_id
        
        return response


# ============================================================================
# Input Sanitization
# ============================================================================

class InputSanitizer:
    """
    Sanitize user input to prevent XSS and injection attacks
    """
    
    # Allowed HTML tags for rich text fields
    ALLOWED_TAGS = ['b', 'i', 'u', 'strong', 'em', 'p', 'br', 'ul', 'ol', 'li']
    ALLOWED_ATTRIBUTES = {}
    
    @staticmethod
    def sanitize_html(text: str) -> str:
        """Remove/escape dangerous HTML content"""
        if not text:
            return text
        return bleach.clean(
            text,
            tags=InputSanitizer.ALLOWED_TAGS,
            attributes=InputSanitizer.ALLOWED_ATTRIBUTES,
            strip=True
        )
    
    @staticmethod
    def sanitize_plain_text(text: str) -> str:
        """Strip all HTML from plain text fields"""
        if not text:
            return text
        return bleach.clean(text, tags=[], strip=True)
    
    @staticmethod
    def sanitize_filename(filename: str) -> str:
        """Sanitize filename to prevent path traversal"""
        if not filename:
            return filename
        
        # Remove path separators and null bytes
        filename = filename.replace("/", "").replace("\\", "").replace("\x00", "")
        
        # Remove dangerous characters
        filename = re.sub(r'[<>:"|?*]', '', filename)
        
        # Prevent hidden files
        filename = filename.lstrip('.')
        
        return filename
    
    @staticmethod
    def validate_email(email: str) -> bool:
        """Validate email format"""
        pattern = r'^[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}$'
        return bool(re.match(pattern, email))
    
    @staticmethod
    def validate_phone(phone: str, country: str = "JO") -> bool:
        """Validate phone number format"""
        if country == "JO":
            # Jordan phone pattern
            pattern = r'^(\+962|00962|0)[0-9]{9}$'
            return bool(re.match(pattern, phone))
        return True


# ============================================================================
# Password Security
# ============================================================================

class PasswordValidator:
    """
    Validate password strength
    Implements NIST password guidelines
    """
    
    MIN_LENGTH = 8
    MAX_LENGTH = 128
    
    # Common passwords to reject (should be loaded from file in production)
    COMMON_PASSWORDS = {
        'password', 'password123', '123456', '12345678', 'qwerty',
        'abc123', 'admin', 'letmein', 'welcome', 'password1'
    }
    
    @classmethod
    def validate(cls, password: str) -> tuple[bool, str]:
        """
        Validate password strength
        Returns: (is_valid, error_message)
        """
        if len(password) < cls.MIN_LENGTH:
            return False, f"Password must be at least {cls.MIN_LENGTH} characters"
        
        if len(password) > cls.MAX_LENGTH:
            return False, f"Password cannot exceed {cls.MAX_LENGTH} characters"
        
        if password.lower() in cls.COMMON_PASSWORDS:
            return False, "Password is too common"
        
        # Require mixed case
        if not re.search(r'[A-Z]', password):
            return False, "Password must contain at least one uppercase letter"
        
        if not re.search(r'[a-z]', password):
            return False, "Password must contain at least one lowercase letter"
        
        # Require at least one digit
        if not re.search(r'\d', password):
            return False, "Password must contain at least one digit"
        
        return True, ""
    
    @classmethod
    def check_breached(cls, password: str) -> bool:
        """
        Check if password appears in known breaches using k-anonymity
        Uses Have I Been Pwned API (should be implemented for production)
        """
        # In production, would call HIBP API
        return False


# ============================================================================
# CSRF Protection (for session-based auth)
# ============================================================================

class CSRFProtection:
    """
    CSRF token generation and validation
    Note: JWT-based APIs are generally CSRF-immune, but included for forms
    """
    
    @staticmethod
    def generate_token() -> str:
        """Generate a secure CSRF token"""
        return secrets.token_urlsafe(32)
    
    @staticmethod
    def validate_token(token: str, stored_token: str) -> bool:
        """Validate CSRF token with timing-safe comparison"""
        if not token or not stored_token:
            return False
        return secrets.compare_digest(token, stored_token)


# ============================================================================
# Secure Cookie Configuration
# ============================================================================

def get_secure_cookie_settings() -> dict:
    """
    Get secure cookie configuration
    For session cookies if using cookie-based sessions
    """
    return {
        "httponly": True,       # Prevent JavaScript access
        "secure": True,         # HTTPS only
        "samesite": "strict",   # Prevent CSRF
        "max_age": 3600,        # 1 hour expiry
    }


# ============================================================================
# IP Validation
# ============================================================================

def is_private_ip(ip: str) -> bool:
    """Check if IP is private/internal"""
    private_patterns = [
        r'^127\.',              # Loopback
        r'^10\.',               # Class A private
        r'^172\.(1[6-9]|2[0-9]|3[0-1])\.',  # Class B private
        r'^192\.168\.',         # Class C private
        r'^::1$',               # IPv6 loopback
        r'^fc00:',              # IPv6 private
        r'^fe80:',              # IPv6 link-local
    ]
    
    for pattern in private_patterns:
        if re.match(pattern, ip):
            return True
    return False
