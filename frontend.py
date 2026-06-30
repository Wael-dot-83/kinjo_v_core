from fastapi import APIRouter, Request, Depends
from fastapi.responses import HTMLResponse, RedirectResponse, Response
from fastapi.templating import Jinja2Templates
from jinja2 import pass_context
import models
from i18n import gettext as _i18n_gettext
from sqlalchemy.orm import Session
from sqlalchemy import or_
from datetime import date, timedelta, datetime, timezone
from utils.time_utils import today_amman as _today
import typing
from typing import Optional

from database import get_db
from dependencies import get_current_user_optional, get_current_user_or_redirect, require_admin
from models import User, UserRole, Kindergarten, EnrollmentApplication
from config import settings
from validators import validate_jordan_governorate

SUPPORTED_UI_LANGUAGES = {"ar", "en"}


def normalize_ui_language(value: Optional[str]) -> str:
    if not value:
        return "ar"
    normalized = str(value).strip().lower()
    return normalized if normalized in SUPPORTED_UI_LANGUAGES else "ar"


def language_context_processor(request: Request) -> dict:
    # Resolve UI language from the persisted cookie first; allow request.state/query override.
    lang = normalize_ui_language(
        request.cookies.get("kinjo_lang")
        or getattr(request.state, "ui_lang", None)
        or request.query_params.get("lang")
    )
    # Pass impersonation state so the banner template can render it
    from rbac import IMPERSONATION_SESSION_KEY
    session = getattr(request.state, "session", None) or {}
    impersonation = session.get(IMPERSONATION_SESSION_KEY)
    return {
        "ui_lang": lang,
        "ui_dir": "rtl" if lang == "ar" else "ltr",
        "public_registration_enabled": settings.PUBLIC_REGISTRATION_ENABLED or settings.TESTING,
        "csrf_token": getattr(
            request.state,
            "csrf_token",
            request.cookies.get(settings.CSRF_COOKIE_NAME, ""),
        ),
        "impersonation": impersonation,
        "current_year": _today().year,
        "support_contact_email": settings.SUPPORT_CONTACT_EMAIL,
        "support_contact_phone": settings.SUPPORT_CONTACT_PHONE,
        # CAPTCHA_SITE_KEY is the public key â€” safe to expose to templates/JS.
        # CAPTCHA_SECRET_KEY never leaves the server.
        "captcha_enabled": settings.CAPTCHA_ENABLED,
        "captcha_provider": settings.CAPTCHA_PROVIDER,
        "captcha_site_key": settings.CAPTCHA_SITE_KEY,
    }


# Setup templates with UTF-8 encoding
templates = Jinja2Templates(
    directory="templates",
    context_processors=[language_context_processor],
)
templates.env.globals['encoding'] = 'utf-8'
# Expose only the single non-sensitive value templates need (never the full settings object).
templates.env.globals['session_timeout_minutes'] = settings.SESSION_TIMEOUT_MINUTES
templates.env.globals['_t'] = lambda k, default=None, **kw: _i18n_gettext(k, **kw)
templates.env.globals['max_attachment_size_mb'] = settings.MAX_ATTACHMENT_SIZE_MB


@pass_context
def _jinja_gettext(ctx, message, **kwargs):
    lang = ctx.get('ui_lang', 'ar')
    return _i18n_gettext(message, lang=lang, **kwargs)


templates.env.globals['_'] = _jinja_gettext
# Ensure auto_reload for development
templates.env.auto_reload = True

# Custom Jinja2 filters
def status_color(status: str) -> str:
    """Map enrollment/application status to Bootstrap color class"""
    color_map = {
        'PENDING': 'warning',
        'SUBMITTED': 'info',
        'UNDER_REVIEW': 'primary',
        'APPROVED': 'success',
        'REJECTED': 'danger',
        'WAITLISTED': 'secondary',
        'ENROLLED': 'success',
        'ACTIVE': 'success',
        'WITHDRAWN': 'dark',
        'GRADUATED': 'info',
        'CANCELLED': 'danger',
        'DRAFT': 'secondary',
        'SENT': 'success',
        'VIEWED': 'info',
    }
    return color_map.get(status, 'secondary')

templates.env.filters['status_color'] = status_color

router = APIRouter(include_in_schema=False)

# -----------------------------------------------------------------------------
# Home & Auth
# -----------------------------------------------------------------------------

@router.get("/", response_class=HTMLResponse)
async def index(request: Request, current_user: typing.Optional[User] = Depends(get_current_user_optional)):
    if current_user:
        return RedirectResponse(url="/dashboard")
    return templates.TemplateResponse(request=request, name="public/home.html", context={"current_user": None})

@router.get("/login", response_class=HTMLResponse)
async def login_page(request: Request):
    return templates.TemplateResponse(
        request=request,
        name="auth/login.html",
        context={"current_user": None, "messages": []},
    )

@router.get("/register", response_class=HTMLResponse)
async def register_page(request: Request):
    if not (settings.PUBLIC_REGISTRATION_ENABLED or settings.TESTING):
        return RedirectResponse(url="/login?registration=disabled", status_code=302)
    return templates.TemplateResponse(
        request=request,
        name="auth/register.html",
        context={
            "current_user": None,
            "messages": [],
            "registration_open": settings.PUBLIC_REGISTRATION_ENABLED or settings.TESTING,
        },
    )


# -----------------------------------------------------------------------------
# Public pages (no authentication required)
# -----------------------------------------------------------------------------

@router.get("/about", response_class=HTMLResponse)
async def about_page(request: Request):
    return templates.TemplateResponse(request=request, name="public/about.html", context={"current_user": None})


@router.get("/services", response_class=HTMLResponse)
async def service_guide_page(request: Request):
    """Public Service Guide / Service Card for the kindergarten enrollment service."""
    return templates.TemplateResponse(
        request=request,
        name="public/service_guide.html",
        context={
            "current_user": None,
            "required_documents": settings.REQUIRED_ENROLLMENT_DOCUMENTS,
            "min_child_age_days": settings.MIN_CHILD_AGE_DAYS,
            "max_child_age_months": settings.MAX_CHILD_AGE_MONTHS,
        },
    )


@router.get("/faq", response_class=HTMLResponse)
async def faq_page(request: Request):
    return templates.TemplateResponse(request=request, name="public/faq.html", context={"current_user": None})


@router.get("/contact", response_class=HTMLResponse)
async def contact_page(request: Request):
    return templates.TemplateResponse(request=request, name="public/contact.html", context={"current_user": None})


@router.get("/sitemap", response_class=HTMLResponse)
async def sitemap_page(request: Request):
    return templates.TemplateResponse(request=request, name="public/sitemap.html", context={"current_user": None})


@router.get("/privacy", response_class=HTMLResponse)
async def privacy_page(request: Request):
    return templates.TemplateResponse(
        request=request, name="public/legal.html", context={"current_user": None, "doc_type": "privacy"}
    )


@router.get("/terms", response_class=HTMLResponse)
async def terms_page(request: Request):
    return templates.TemplateResponse(
        request=request, name="public/legal.html", context={"current_user": None, "doc_type": "terms"}
    )


@router.get("/disclaimer", response_class=HTMLResponse)
async def disclaimer_page(request: Request):
    return templates.TemplateResponse(
        request=request, name="public/legal.html", context={"current_user": None, "doc_type": "disclaimer"}
    )


@router.get("/copyright", response_class=HTMLResponse)
async def copyright_page(request: Request):
    return templates.TemplateResponse(
        request=request, name="public/legal.html", context={"current_user": None, "doc_type": "copyright"}
    )


@router.get("/robots.txt", include_in_schema=False)
async def robots_txt():
    lines = [
        "User-agent: *",
        "Allow: /$",
        "Allow: /about",
        "Allow: /services",
        "Allow: /faq",
        "Allow: /contact",
        "Allow: /sitemap",
        "Allow: /privacy",
        "Allow: /terms",
        "Allow: /disclaimer",
        "Allow: /copyright",
        "Allow: /login",
        "Allow: /register",
        "Disallow: /api/",
        "Disallow: /admin",
        "Disallow: /dashboard",
        "Disallow: /parent/",
        "Disallow: /supervisor/",
        "Disallow: /manager/",
        "Sitemap: /sitemap.xml",
        "",
    ]
    return Response(content="\n".join(lines), media_type="text/plain")


@router.get("/sitemap.xml", include_in_schema=False)
async def sitemap_xml(request: Request):
    public_paths = [
        "/", "/about", "/services", "/faq", "/contact", "/sitemap",
        "/privacy", "/terms", "/disclaimer", "/copyright",
        "/login", "/register",
    ]
    base = str(request.base_url).rstrip("/")
    entries = "".join(
        f"<url><loc>{base}{path}</loc></url>" for path in public_paths
    )
    xml = (
        '<?xml version="1.0" encoding="UTF-8"?>'
        '<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">'
        f"{entries}"
        "</urlset>"
    )
    return Response(content=xml, media_type="application/xml")


@router.get("/mfa/setup", response_class=HTMLResponse)
async def mfa_setup_page(request: Request):
    return templates.TemplateResponse(
        request=request,
        name="auth/mfa_setup.html",
        context={"current_user": None, "messages": []},
    )

@router.get("/favicon.ico", include_in_schema=False)
async def favicon():
    return Response(content=b"", media_type="image/x-icon", status_code=204)

@router.get("/change-password", response_class=HTMLResponse)
async def change_password_page(request: Request, current_user: User = Depends(get_current_user_or_redirect)):
    """Change password page for users who must change their password"""
    return templates.TemplateResponse(request=request, name="auth/change-password.html", context={"current_user": current_user, "messages": []})

@router.get("/forgot-password", response_class=HTMLResponse)
async def forgot_password_page(request: Request):
    """Forgot password page â€” allows users to request a password reset email"""
    return templates.TemplateResponse(request=request, name="auth/forgot-password.html", context={})

@router.get("/reset-password", response_class=HTMLResponse)
async def reset_password_page(request: Request, token: str = ""):
    """Reset password page â€” consumes the token from the email link"""
    return templates.TemplateResponse(request=request, name="auth/reset-password.html", context={"token": token})

@router.get("/dashboard", response_class=HTMLResponse)
async def dashboard(request: Request, current_user: User = Depends(get_current_user_or_redirect)):
    user_role = current_user.role.value if hasattr(current_user.role, 'value') else current_user.role

    if user_role == "SUPERVISOR":
        return templates.TemplateResponse(request=request, name="dashboard/supervisor.html", context={"current_user": current_user, "today": _today()})
    elif user_role == "PARENT":
        return templates.TemplateResponse(request=request, name="dashboard/parent.html", context={"current_user": current_user, "today": _today()})
    elif user_role == "ADMIN":
        return templates.TemplateResponse(request=request, name="admin_dashboard.html", context={"current_user": current_user, "today": _today()})
    else:
        # Manager
        return templates.TemplateResponse(request=request, name="dashboard/index.html", context={"current_user": current_user, "today": _today()})


@router.get("/supervisor/dashboard", response_class=HTMLResponse)
async def supervisor_dashboard(request: Request, current_user: User = Depends(get_current_user_or_redirect)):
    """Dedicated supervisor dashboard route"""
    user_role = current_user.role.value if hasattr(current_user.role, 'value') else current_user.role
    if user_role != 'SUPERVISOR':
        return RedirectResponse(url="/dashboard")
    return templates.TemplateResponse(
        request=request,
        name="dashboard/supervisor.html",
        context={"current_user": current_user, "today": _today()}
    )


@router.get("/parent/dashboard", response_class=HTMLResponse)
async def parent_dashboard(request: Request, current_user: User = Depends(get_current_user_or_redirect)):
    """Dedicated parent dashboard route"""
    user_role = current_user.role.value if hasattr(current_user.role, 'value') else current_user.role
    if user_role != 'PARENT':
        return RedirectResponse(url="/dashboard")
    return templates.TemplateResponse(
        request=request,
        name="dashboard/parent.html",
        context={"current_user": current_user, "today": _today()},
    )


@router.get("/parent/profile", response_class=HTMLResponse)
async def parent_profile_page(request: Request, current_user: User = Depends(get_current_user_or_redirect)):
    """Parent profile view/edit page"""
    user_role = current_user.role.value if hasattr(current_user.role, 'value') else current_user.role
    if user_role != 'PARENT':
        return RedirectResponse(url="/profile")
    return templates.TemplateResponse(request=request, name="parent/profile.html", context={"current_user": current_user})


@router.get("/parent/children", response_class=HTMLResponse)
async def parent_children_list(request: Request, current_user: User = Depends(get_current_user_or_redirect)):
    """Parent children list page"""
    user_role = current_user.role.value if hasattr(current_user.role, 'value') else current_user.role
    if user_role != 'PARENT':
        return RedirectResponse(url="/dashboard")
    return templates.TemplateResponse(request=request, name="parent/children.html", context={"current_user": current_user})


@router.get("/parent/enrollments", response_class=HTMLResponse)
async def parent_enrollments_page(request: Request, current_user: User = Depends(get_current_user_or_redirect)):
    """Parent enrollment history page"""
    user_role = current_user.role.value if hasattr(current_user.role, 'value') else current_user.role
    if user_role != 'PARENT':
        return RedirectResponse(url="/enrollments")
    return templates.TemplateResponse(request=request, name="parent/enrollments.html", context={"current_user": current_user})

@router.get("/parent/attendance", response_class=HTMLResponse)
async def parent_attendance_page(request: Request, current_user: User = Depends(get_current_user_or_redirect)):
    """Parent attendance view page"""
    user_role = current_user.role.value if hasattr(current_user.role, 'value') else current_user.role
    if user_role != 'PARENT':
        return RedirectResponse(url="/attendance")
    return templates.TemplateResponse(request=request, name="parent/attendance.html", context={"current_user": current_user})

# -----------------------------------------------------------------------------
# Kindergartens
# -----------------------------------------------------------------------------

@router.get("/kindergartens", response_class=HTMLResponse)
async def list_kindergartens(
    request: Request,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user_or_redirect),
    status: Optional[str] = None,
    governorate: Optional[str] = None,
    city: Optional[str] = None,
    name: Optional[str] = None,
    skip: int = 0,
    limit: int = 50
):
    # For managers, show only their kindergarten
    if current_user.role == models.UserRole.MANAGER:
        if current_user.kindergarten_id:
            kindergarten = db.query(Kindergarten).filter(
                Kindergarten.id == current_user.kindergarten_id
            ).first()
            kindergartens = [kindergarten] if kindergarten else []
            total = len(kindergartens)
        else:
            kindergartens = []
            total = 0
    elif current_user.role == models.UserRole.ADMIN:
        # Admins can see all kindergartens with filtering
        query = db.query(Kindergarten)

        # Apply filters
        if status:
            try:
                status_enum = models.KindergartenStatus(status.upper())
                query = query.filter(Kindergarten.status == status_enum)
            except (ValueError, AttributeError):
                pass  # Invalid status, ignore filter

        if governorate:
            normalized_governorate = governorate
            try:
                normalized_governorate = validate_jordan_governorate(governorate)
            except (TypeError, ValueError):
                normalized_governorate = governorate
            query = query.filter(Kindergarten.governorate.ilike(f"%{normalized_governorate}%"))

        if city:
            query = query.filter(Kindergarten.district.ilike(f"%{city}%"))

        if name:
            query = query.filter(
                or_(
                    Kindergarten.name_ar.ilike(f"%{name}%"),
                    Kindergarten.name_en.ilike(f"%{name}%")
                )
            )

        # Get total count before pagination
        total = query.count()

        # Apply pagination
        kindergartens = query.offset(skip).limit(limit).all()
    else:
        # Other roles cannot access this page
        kindergartens = []
        total = 0

    # Get filter options for the UI
    governorates = settings.JORDAN_GOVERNORATES

    return templates.TemplateResponse(
        request=request,
        name="kindergartens/list.html",
        context={
            "current_user": current_user,
            "kindergartens": kindergartens,
            "total": total,
            "skip": skip,
            "limit": limit,
            "filters": {
                "status": status,
                "governorate": governorate,
                "city": city,
                "name": name
            },
            "governorates": governorates
        }
    )

@router.get("/kindergartens/create", response_class=HTMLResponse)
async def create_kindergarten_page(request: Request, current_user: User = Depends(get_current_user_or_redirect)):
    if current_user.role != models.UserRole.ADMIN:
        return templates.TemplateResponse(request=request, name="403.html", status_code=403)
    return templates.TemplateResponse(request=request, name="kindergartens/form.html", context={"current_user": current_user, "kindergarten": None})

@router.get("/kindergartens/{kg_id}", response_class=HTMLResponse)
async def view_kindergarten(request: Request, kg_id: int, db: Session = Depends(get_db), current_user: User = Depends(get_current_user_or_redirect)):
    kg = db.query(Kindergarten).filter(Kindergarten.id == kg_id).first()
    if not kg:
        return templates.TemplateResponse(request=request, name="404.html", status_code=404)
    
    # Check access permissions
    if current_user.role == models.UserRole.MANAGER:
        if current_user.kindergarten_id != kg_id:
            return templates.TemplateResponse(request=request, name="403.html", status_code=403)
    elif current_user.role != models.UserRole.ADMIN:
        return templates.TemplateResponse(request=request, name="403.html", status_code=403)
    
    return templates.TemplateResponse(request=request, name="kindergartens/view.html", context={"current_user": current_user, "kindergarten": kg})

@router.get("/kindergartens/{kg_id}/edit", response_class=HTMLResponse)
async def edit_kindergarten_page(request: Request, kg_id: int, db: Session = Depends(get_db), current_user: User = Depends(get_current_user_or_redirect)):
    kg = db.query(Kindergarten).filter(Kindergarten.id == kg_id).first()
    if not kg:
        return templates.TemplateResponse(request=request, name="404.html", status_code=404)
    
    # Check access permissions
    if current_user.role == models.UserRole.MANAGER:
        if current_user.kindergarten_id != kg_id:
            return templates.TemplateResponse(request=request, name="403.html", status_code=403)
    elif current_user.role != models.UserRole.ADMIN:
        return templates.TemplateResponse(request=request, name="403.html", status_code=403)
    
    return templates.TemplateResponse(request=request, name="kindergartens/form.html", context={"current_user": current_user, "kindergarten": kg})

# -----------------------------------------------------------------------------
# Classes (Sections)
# -----------------------------------------------------------------------------

@router.get("/classes", response_class=HTMLResponse)
async def list_classes_page(request: Request, current_user: User = Depends(get_current_user_or_redirect)):
    """Class list page â€” Manager and Admin."""
    if current_user.role not in (UserRole.MANAGER, UserRole.ADMIN):
        return templates.TemplateResponse(request=request, name="403.html", status_code=403, context={"current_user": current_user})
    return templates.TemplateResponse(request=request, name="classes/list.html", context={"current_user": current_user})

@router.get("/classes/create", response_class=HTMLResponse)
async def create_class_page(request: Request, db: Session = Depends(get_db), current_user: User = Depends(get_current_user_or_redirect)):
    """Create class page â€” Manager only."""
    if current_user.role != UserRole.MANAGER:
        return templates.TemplateResponse(request=request, name="403.html", status_code=403, context={"current_user": current_user})
    kgs = db.query(Kindergarten).filter(Kindergarten.id == current_user.kindergarten_id).all()
    return templates.TemplateResponse(request=request, name="classes/form.html", context={
        "current_user": current_user,
        "kindergartens": kgs,
        "class_obj": None
    })

@router.get("/classes/{class_id}/edit", response_class=HTMLResponse)
async def edit_class_page(request: Request, class_id: int, db: Session = Depends(get_db), current_user: User = Depends(get_current_user_or_redirect)):
    """Edit class page â€” Manager only."""
    from models import Class
    if current_user.role != UserRole.MANAGER:
        return templates.TemplateResponse(request=request, name="403.html", status_code=403, context={"current_user": current_user})
    class_obj = db.query(Class).filter(Class.id == class_id).first()
    if not class_obj:
        return templates.TemplateResponse(request=request, name="404.html", status_code=404)
    if class_obj.kindergarten_id != current_user.kindergarten_id:
        return templates.TemplateResponse(request=request, name="403.html", status_code=403, context={"current_user": current_user})
    kgs = db.query(Kindergarten).filter(Kindergarten.id == current_user.kindergarten_id).all()
    return templates.TemplateResponse(request=request, name="classes/form.html", context={
        "current_user": current_user,
        "kindergartens": kgs,
        "class_obj": class_obj
    })

# -----------------------------------------------------------------------------
# Enrollments
# -----------------------------------------------------------------------------

@router.get("/enrollments", response_class=HTMLResponse)
async def list_enrollments(request: Request, current_user: User = Depends(get_current_user_or_redirect)):
    # Supervisors cannot access enrollments
    user_role = current_user.role.value if hasattr(current_user.role, 'value') else current_user.role
    if user_role == 'SUPERVISOR':
        return templates.TemplateResponse(request=request, name="403.html", status_code=403, context={"current_user": current_user})
    if user_role == 'PARENT':
        return RedirectResponse(url="/parent/enrollments")
    return templates.TemplateResponse(request=request, name="enrollment/list.html", context={"current_user": current_user})

@router.get("/enrollments/create", response_class=HTMLResponse)
async def create_enrollment_page(request: Request, db: Session = Depends(get_db), current_user: User = Depends(get_current_user_or_redirect)):
    # Filter kindergartens based on user role
    user_role = current_user.role.value if hasattr(current_user.role, 'value') else current_user.role

    # Supervisors cannot create enrollments - redirect to 403
    if user_role == 'SUPERVISOR':
        return templates.TemplateResponse(request=request, name="403.html", status_code=403, context={"current_user": current_user})

    if user_role == 'ADMIN':
        # Admins can see all active kindergartens
        kgs = db.query(Kindergarten).filter(Kindergarten.status == models.KindergartenStatus.ACTIVE).all()
        from config import settings as app_settings
        context = {
            "current_user": current_user,
            "kindergartens": kgs,
            "governorates": app_settings.JORDAN_GOVERNORATES,
            "is_manager_supervisor": False
        }
    elif user_role == 'MANAGER' and current_user.kindergarten_id:
        # Only Managers can create enrollments for their own kindergarten
        kgs = db.query(Kindergarten).filter(
            Kindergarten.status == models.KindergartenStatus.ACTIVE,
            Kindergarten.id == current_user.kindergarten_id
        ).all()
        user_kindergarten = kgs[0] if kgs else None
        from config import settings as app_settings
        context = {
            "current_user": current_user,
            "kindergartens": kgs,
            "governorates": app_settings.JORDAN_GOVERNORATES,
            "user_kindergarten": user_kindergarten,
            "is_manager_supervisor": True
        }
    elif user_role == 'PARENT':
        # Parents can see all active kindergartens to enroll their children
        kgs = db.query(Kindergarten).filter(Kindergarten.status == models.KindergartenStatus.ACTIVE).all()
        from config import settings as app_settings
        context = {
            "current_user": current_user,
            "kindergartens": kgs,
            "governorates": app_settings.JORDAN_GOVERNORATES,
            "is_manager_supervisor": False
        }
    else:
        # Other roles cannot create enrollments
        context = {
            "current_user": current_user,
            "kindergartens": [],
            "governorates": [],
            "is_manager_supervisor": False
        }

    return templates.TemplateResponse(request=request, name="enrollment/create.html", context=context)

@router.get("/enrollments/new", response_class=HTMLResponse)
async def new_enrollment(request: Request, db: Session = Depends(get_db), current_user: User = Depends(get_current_user_or_redirect)):
    """New enrollment - redirects to create page"""
    return RedirectResponse(url="/enrollments/create")

@router.get("/enrollments/{app_id}", response_class=HTMLResponse)
async def view_enrollment(request: Request, app_id: int, db: Session = Depends(get_db), current_user: User = Depends(get_current_user_or_redirect)):
    enrollment = db.query(EnrollmentApplication).filter(EnrollmentApplication.id == app_id).first()
    if not enrollment:
         return templates.TemplateResponse(request=request, name="404.html", status_code=404)

    # Access control for parent: only their own children's enrollments
    user_role = current_user.role.value if hasattr(current_user.role, 'value') else current_user.role
    if user_role == 'PARENT':
        parent_profile = db.query(models.ParentProfile).filter(
            models.ParentProfile.user_id == current_user.id
        ).first()
        child = db.query(models.Child).filter(models.Child.id == enrollment.child_id).first()
        if not parent_profile or not child or child.parent_id != parent_profile.id:
            return templates.TemplateResponse(request=request, name="403.html", status_code=403, context={"current_user": current_user})

    # Enrich data for template
    child = db.query(models.Child).filter(models.Child.id == enrollment.child_id).first()
    kg = db.query(models.Kindergarten).filter(models.Kindergarten.id == enrollment.kindergarten_id).first()

    STATUS_AR = {
        "DRAFT": "Ù…Ø³ÙˆØ¯Ø©", "SUBMITTED": "Ù…Ù‚Ø¯Ù‘Ù…", "PENDING_REVIEW": "Ù‚ÙŠØ¯ Ø§Ù„Ù…Ø±Ø§Ø¬Ø¹Ø©",
        "ACCEPTED": "Ù…Ù‚Ø¨ÙˆÙ„", "REJECTED": "Ù…Ø±ÙÙˆØ¶", "WITHDRAWN": "Ù…Ù†Ø³Ø­Ø¨",
        "WAITLISTED": "Ù‚Ø§Ø¦Ù…Ø© Ø§Ù„Ø§Ù†ØªØ¸Ø§Ø±", "ACTIVE": "Ù†Ø´Ø·"
    }
    STATUS_COLOR = {
        "DRAFT": "secondary", "SUBMITTED": "info", "PENDING_REVIEW": "warning",
        "ACCEPTED": "success", "REJECTED": "danger", "WITHDRAWN": "dark",
        "WAITLISTED": "info", "ACTIVE": "success"
    }

    status_val = enrollment.status.value if hasattr(enrollment.status, 'value') else str(enrollment.status)

    # Get parent profile for extra info
    parent_profile = None
    if child:
        parent_profile = db.query(models.ParentProfile).filter(
            models.ParentProfile.id == child.parent_id
        ).first()

    data = {
        "id": enrollment.id,
        "child_id": enrollment.child_id,
        "child_name": f"{child.first_name} {child.last_name}" if child else "ØºÙŠØ± Ù…Ø¹Ø±ÙˆÙ",
        "kindergarten_id": enrollment.kindergarten_id,
        "kindergarten_name": kg.name_ar if kg else "ØºÙŠØ± Ù…Ø¹Ø±ÙˆÙ",
        "status": status_val.lower(),
        "status_ar": STATUS_AR.get(status_val, status_val),
        "status_color": STATUS_COLOR.get(status_val, "secondary"),
        "created_at": enrollment.created_at.strftime("%Y-%m-%d") if enrollment.created_at else "â€”",
        "submitted_at": enrollment.submitted_at.strftime("%Y-%m-%d") if enrollment.submitted_at else None,
        "dob": child.date_of_birth.isoformat() if child and child.date_of_birth else "â€”",
        "gender_ar": ("Ø°ÙƒØ±" if child and child.gender and child.gender.value == "MALE" else "Ø£Ù†Ø«Ù‰") if child else "â€”",
        "national_id": child.mother_national_id if child else "â€”",
        "age": "",  # Will be computed by JS
        # Parent info
        "father_name": child.father_name if child else "â€”",
        "father_phone": parent_profile.phone_number if parent_profile else "â€”",
        "father_occupation": "â€”",  # Not in model yet
        # Mother info
        "mother_name": f"{child.mother_first_name} {child.mother_last_name}" if child else "â€”",
        "mother_phone": "â€”",  # Not in model yet
        "mother_nationality": child.mother_nationality if child else "â€”",
        # Health info
        "medical_conditions": None,  # Not in model yet
        "vaccinations_up_to_date": None,  # Not in model yet
        # Extra fields
        "source": enrollment.source or "WEB",
        "correspondence_flag": child.correspondence_flag if child else True,
        "media_consent": child.media_consent if child else False,
    }

    return templates.TemplateResponse(request=request, name="enrollment/view.html", context={"current_user": current_user, "enrollment": data})

# -----------------------------------------------------------------------------
# Attendance
# -----------------------------------------------------------------------------

@router.get("/attendance/history", response_class=HTMLResponse)
async def attendance_history(
    request: Request,
    period: Optional[str] = None,
    reason: Optional[str] = None,
    change: Optional[str] = None,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user_or_redirect)
):
    user_role = current_user.role.value if hasattr(current_user.role, "value") else current_user.role
    if user_role == "PARENT":
        return RedirectResponse(url="/parent/dashboard")

    today = _today()
    # Pre-set the week range when coming from the dashboard action card
    if period == "week":
        default_start = (today - timedelta(days=6)).isoformat()
        default_end = today.isoformat()
    else:
        default_start = (today - timedelta(days=29)).isoformat()
        default_end = today.isoformat()

    context = {
        "current_user": current_user,
        "is_admin": user_role == "ADMIN",
        "today": today,
        "default_start_date": default_start,
        "default_end_date": default_end,
        "kindergartens": [],
        "governorates": [],
        "user_kindergarten": None,
        # Passed to template for the contextual banner
        "filter_period": period,
        "filter_reason": reason,
        "filter_change": change,
    }

    if user_role == "ADMIN":
        kindergartens = db.query(Kindergarten).order_by(Kindergarten.name_ar).all()
        context["kindergartens"] = kindergartens
        context["governorates"] = sorted(
            {kg.governorate for kg in kindergartens if kg.governorate}
        )
    else:
        if not current_user.kindergarten_id:
            return templates.TemplateResponse(
                request=request,
                name="403.html",
                status_code=403,
                context={"current_user": current_user}
            )

        user_kindergarten = db.query(Kindergarten).filter(
            Kindergarten.id == current_user.kindergarten_id
        ).first()
        if not user_kindergarten:
            return templates.TemplateResponse(
                request=request,
                name="403.html",
                status_code=403,
                context={"current_user": current_user}
            )
        context["user_kindergarten"] = user_kindergarten

    return templates.TemplateResponse(request=request, name="attendance/history.html", context=context)

# -----------------------------------------------------------------------------
# Reports
# -----------------------------------------------------------------------------

@router.get("/reports", response_class=HTMLResponse)
async def list_reports(request: Request, current_user: User = Depends(get_current_user_or_redirect)):
    user_role = current_user.role.value if hasattr(current_user.role, 'value') else current_user.role
    if user_role == 'PARENT':
        return RedirectResponse(url="/parent/dashboard")
    return templates.TemplateResponse(request=request, name="reports/list.html", context={"current_user": current_user, "today": _today()})

@router.get("/reports/create", response_class=HTMLResponse)
async def create_report_page(request: Request, current_user: User = Depends(get_current_user_or_redirect)):
    user_role = current_user.role.value if hasattr(current_user.role, 'value') else current_user.role
    if user_role not in ('SUPERVISOR', 'ADMIN', 'MANAGER'):
        return RedirectResponse(url="/dashboard")
    return templates.TemplateResponse(request=request, name="reports/form.html", context={"current_user": current_user, "today": _today()})

@router.get("/reports/{report_id}", response_class=HTMLResponse)
async def view_report(request: Request, report_id: int, current_user: User = Depends(get_current_user_or_redirect)):
    """
    Daily report detail page with full approval workflow support.
    The actual report data is fetched via API call from the frontend JS.
    """
    # Provide default report object for template rendering - actual data loaded via JS
    default_report = {
        "id": report_id,
        "child_name": "...",
        "date": "",
        "teacher_name": "...",
        "mood_emoji": "ðŸ˜Š",
        "mood_text": ""
    }
    return templates.TemplateResponse(
        request=request,
        name="reports/view.html",
        context={"current_user": current_user, "report_id": report_id, "report": default_report}
    )

# -----------------------------------------------------------------------------
# KPI
# -----------------------------------------------------------------------------

@router.get("/kpi/dashboard", response_class=HTMLResponse)
async def kpi_dashboard_page(request: Request, current_user: User = Depends(get_current_user_or_redirect)):
    user_role = current_user.role.value if hasattr(current_user.role, 'value') else current_user.role
    if user_role not in ('ADMIN', 'MANAGER'):
        return RedirectResponse(url="/dashboard")
    return templates.TemplateResponse(request=request, name="kpi/dashboard.html", context={"current_user": current_user})

# -----------------------------------------------------------------------------
# Communication
# -----------------------------------------------------------------------------

@router.get("/communication", response_class=HTMLResponse)
async def communication_dashboard(request: Request, current_user: User = Depends(get_current_user_or_redirect)):
    return templates.TemplateResponse(request=request, name="communication/index.html", context={"current_user": current_user})

@router.get("/communication/messages", response_class=HTMLResponse)
async def list_messages(request: Request, current_user: User = Depends(get_current_user_or_redirect)):
    return templates.TemplateResponse(request=request, name="communication/messages.html", context={"current_user": current_user})

@router.get("/communication/events", response_class=HTMLResponse)
async def list_events(request: Request, current_user: User = Depends(get_current_user_or_redirect)):
    return templates.TemplateResponse(request=request, name="communication/events.html", context={"current_user": current_user})

@router.get("/communication/surveys", response_class=HTMLResponse)
async def list_surveys(request: Request, current_user: User = Depends(get_current_user_or_redirect)):
    return templates.TemplateResponse(request=request, name="communication/surveys.html", context={"current_user": current_user})

# -----------------------------------------------------------------------------
# Tasks
# -----------------------------------------------------------------------------

@router.get("/tasks", response_class=HTMLResponse)
async def list_tasks(request: Request, current_user: User = Depends(get_current_user_or_redirect)):
    user_role = current_user.role.value if hasattr(current_user.role, 'value') else current_user.role
    if user_role == 'PARENT':
        return RedirectResponse(url="/parent/dashboard")
    return templates.TemplateResponse(request=request, name="tasks/list.html", context={"current_user": current_user})


# -----------------------------------------------------------------------------
# Safety & Health
# -----------------------------------------------------------------------------

@router.get("/safety", response_class=HTMLResponse)
async def safety_dashboard(request: Request, current_user: User = Depends(get_current_user_or_redirect)):
    user_role = current_user.role.value if hasattr(current_user.role, 'value') else current_user.role
    if user_role == 'PARENT':
        return RedirectResponse(url="/parent/dashboard")
    return templates.TemplateResponse(request=request, name="safety/index.html", context={"current_user": current_user})

@router.get("/safety/incidents/new", response_class=HTMLResponse)
async def create_incident_page(request: Request, current_user: User = Depends(get_current_user_or_redirect)):
    user_role = current_user.role.value if hasattr(current_user.role, 'value') else current_user.role
    if user_role == 'ADMIN':
        # Admin should not create incidents directly - redirect to reporting
        return RedirectResponse(url="/daily-reports")
    if user_role not in ('SUPERVISOR', 'ADMIN', 'MANAGER'):
        return RedirectResponse(url="/dashboard")
    return templates.TemplateResponse(request=request, name="safety/incident_form.html", context={"current_user": current_user})


# -----------------------------------------------------------------------------
# Additional Missing Routes
# -----------------------------------------------------------------------------

@router.get("/attendance", response_class=HTMLResponse)
async def attendance_main(request: Request, current_user: User = Depends(get_current_user_or_redirect)):
    """Main attendance page - redirects to daily attendance"""
    user_role = current_user.role.value if hasattr(current_user.role, 'value') else current_user.role
    if user_role == 'ADMIN':
        return RedirectResponse(url="/dashboard")
    if user_role == 'PARENT':
        return RedirectResponse(url="/absence-requests")
    return RedirectResponse(url="/attendance/daily")


@router.get("/attendance/daily", response_class=HTMLResponse)
async def attendance_daily(request: Request, db: Session = Depends(get_db), current_user: User = Depends(get_current_user_or_redirect)):
    """Daily attendance page with role-based kindergarten filtering"""
    user_role = current_user.role.value if hasattr(current_user.role, 'value') else current_user.role

    # Admin and Supervisor are blocked from daily attendance (operational Manager page)
    if user_role in ('ADMIN', 'SUPERVISOR'):
        return templates.TemplateResponse(request=request, name="403.html", status_code=403, context={"current_user": current_user})

    # Parents see the absence-request page instead of staff attendance
    if user_role == 'PARENT':
        return RedirectResponse(url="/absence-requests")

    # For managers, automatically set their kindergarten
    if user_role == 'MANAGER':
        kindergarten = db.query(Kindergarten).filter(Kindergarten.id == current_user.kindergarten_id).first()
        if not kindergarten:
            # This should not happen due to database constraints, but handle gracefully
            return templates.TemplateResponse(request=request, name="403.html", status_code=403, context={"current_user": current_user})

        context = {
            "current_user": current_user,
            "today": _today(),
            "user_kindergarten": kindergarten,
            "is_manager_supervisor": True,
            "is_supervisor": False,
            "supervisor_class_ids": [],
        }
    else:
        # Admin can see all kindergartens
        context = {
            "current_user": current_user,
            "today": _today(),
            "is_manager_supervisor": False,
            "is_supervisor": False,
            "supervisor_class_ids": []
        }

    return templates.TemplateResponse(request=request, name="attendance/daily.html", context=context)


@router.get("/attendance/check-in", response_class=HTMLResponse)
async def attendance_check_in(request: Request, db: Session = Depends(get_db), current_user: User = Depends(get_current_user_or_redirect)):
    """Attendance check-in page"""
    from sqlalchemy import or_
    user_role = current_user.role.value if hasattr(current_user.role, 'value') else current_user.role

    # For managers and supervisors, automatically set their kindergarten
    if user_role in ['MANAGER', 'SUPERVISOR']:
        kindergarten = db.query(Kindergarten).filter(Kindergarten.id == current_user.kindergarten_id).first()
        if not kindergarten:
            # This should not happen due to database constraints, but handle gracefully
            return templates.TemplateResponse(request=request, name="403.html", status_code=403, context={"current_user": current_user})

        context = {
            "current_user": current_user,
            "today": _today(),
            "user_kindergarten": kindergarten,
            "is_manager_supervisor": True,
            "is_supervisor": user_role == 'SUPERVISOR',
            "supervisor_class_ids": [],
            "mode": "check-in"
        }

        # For supervisors, get their assigned class IDs
        if user_role == 'SUPERVISOR':
            today = _today()
            assignments = db.query(models.SupervisorAssignment).filter(
                models.SupervisorAssignment.supervisor_id == current_user.id,
                models.SupervisorAssignment.start_date <= today,
                or_(
                    models.SupervisorAssignment.end_date.is_(None),
                    models.SupervisorAssignment.end_date >= today
                )
            ).all()
            context["supervisor_class_ids"] = [a.class_id for a in assignments]
    else:
        # Admin can see all kindergartens
        context = {
            "current_user": current_user,
            "today": _today(),
            "is_manager_supervisor": False,
            "is_supervisor": False,
            "supervisor_class_ids": [],
            "mode": "check-in"
        }

    return templates.TemplateResponse(request=request, name="attendance/daily.html", context=context)


@router.get("/daily-reports", response_class=HTMLResponse)
async def daily_reports_list(request: Request, current_user: User = Depends(get_current_user_or_redirect)):
    """List all daily reports"""
    user_role = current_user.role.value if hasattr(current_user.role, 'value') else current_user.role
    if user_role == "ADMIN":
        return RedirectResponse(url="/admin/daily-reports-organization", status_code=302)
    return templates.TemplateResponse(
        request=request,
        name="reports/list.html",
        context={"current_user": current_user, "today": _today()},
    )


@router.get("/admin/daily-reports-organization", response_class=HTMLResponse)
async def admin_daily_reports_organization_page(
    request: Request,
    current_user: User = Depends(get_current_user_or_redirect),
):
    """Admin daily reports organization page."""
    user_role = current_user.role.value if hasattr(current_user.role, 'value') else current_user.role
    if user_role != "ADMIN":
        return RedirectResponse(url="/dashboard")
    return templates.TemplateResponse(
        request=request,
        name="admin/daily_reports_organization.html",
        context={
            "current_user": current_user,
            "today": _today(),
        },
    )


@router.get("/daily-reports/create", response_class=HTMLResponse)
async def create_daily_report(request: Request, current_user: User = Depends(get_current_user_or_redirect)):
    """Create a new daily report"""
    user_role = current_user.role.value if hasattr(current_user.role, 'value') else current_user.role
    if user_role != 'MANAGER':
        return templates.TemplateResponse(request=request, name="403.html", status_code=403, context={"current_user": current_user})
    return templates.TemplateResponse(request=request, name="reports/form.html", context={"current_user": current_user, "today": _today()})


@router.get("/curriculum", response_class=HTMLResponse)
async def curriculum_page(request: Request, current_user: User = Depends(get_current_user_or_redirect)):
    """Curriculum management placeholder - redirects to dashboard until module is built."""
    user_role = current_user.role.value if hasattr(current_user.role, 'value') else current_user.role
    if user_role in ('ADMIN', 'SUPERVISOR'):
        return templates.TemplateResponse(request=request, name="403.html", status_code=403, context={"current_user": current_user})
    return RedirectResponse(url="/dashboard")


@router.get("/incidents", response_class=HTMLResponse)
async def incidents_list(request: Request, current_user: User = Depends(get_current_user_or_redirect)):
    """Redirect to admin incidents page for admins."""
    user_role = current_user.role.value if hasattr(current_user.role, 'value') else current_user.role
    if user_role != 'ADMIN':
        return RedirectResponse(url="/dashboard")
    return RedirectResponse(url="/admin/reports/incidents")


@router.get("/incidents/create", response_class=HTMLResponse)
async def create_incident(request: Request, current_user: User = Depends(get_current_user_or_redirect)):
    """Create a new incident report"""
    user_role = current_user.role.value if hasattr(current_user.role, 'value') else current_user.role
    if user_role not in ('SUPERVISOR', 'ADMIN', 'MANAGER'):
        return RedirectResponse(url="/dashboard")
    return templates.TemplateResponse(request=request, name="safety/incident_form.html", context={"current_user": current_user})


@router.get("/messages", response_class=HTMLResponse)
async def messages_list(request: Request, current_user: User = Depends(get_current_user_or_redirect)):
    """List all messages"""
    return templates.TemplateResponse(
        request=request,
        name="communication/messages.html",
        context={
            "current_user": current_user,
            "governorates": settings.JORDAN_GOVERNORATES,
            "governorates_en": settings.JORDAN_GOVERNORATES_ENGLISH,
        },
    )


@router.get("/messages/new", response_class=HTMLResponse)
async def new_message(request: Request, current_user: User = Depends(get_current_user_or_redirect)):
    """Compose new message"""
    return templates.TemplateResponse(
        request=request,
        name="communication/messages.html",
        context={
            "current_user": current_user,
            "compose": True,
            "governorates": settings.JORDAN_GOVERNORATES,
            "governorates_en": settings.JORDAN_GOVERNORATES_ENGLISH,
        },
    )


@router.get("/profile", response_class=HTMLResponse)
async def user_profile(request: Request, current_user: User = Depends(get_current_user_or_redirect)):
    """Canonical profile redirect â€” sends each role to its dedicated profile page."""
    user_role = current_user.role.value if hasattr(current_user.role, 'value') else current_user.role
    if user_role == 'PARENT':
        return RedirectResponse(url="/parent/profile")
    if user_role == 'ADMIN':
        return RedirectResponse(url="/admin/profile")
    return templates.TemplateResponse(request=request, name="user/settings.html", context={"current_user": current_user})


@router.get("/settings", response_class=HTMLResponse)
async def user_settings(request: Request, current_user: User = Depends(get_current_user_or_redirect)):
    """User settings page"""
    return templates.TemplateResponse(request=request, name="user/settings.html", context={"current_user": current_user})


@router.get("/notifications", response_class=HTMLResponse)
async def notifications_list(request: Request, current_user: User = Depends(get_current_user_or_redirect)):
    """Notifications list page"""
    return templates.TemplateResponse(request=request, name="user/notifications.html", context={"current_user": current_user})


@router.get("/kpi", response_class=HTMLResponse)
async def kpi_main(request: Request, current_user: User = Depends(get_current_user_or_redirect)):
    """KPI main page - redirects to dashboard"""
    return RedirectResponse(url="/kpi/dashboard")


@router.get("/classes/{class_id}", response_class=HTMLResponse)
async def view_class(request: Request, class_id: int, db: Session = Depends(get_db), current_user: User = Depends(get_current_user_or_redirect)):
    """View class details â€” Admin and Manager can access; Manager scoped to own KG."""
    from models import Class
    class_obj = db.query(Class).filter(Class.id == class_id).first()
    if not class_obj:
        return templates.TemplateResponse(request=request, name="404.html", status_code=404)
    if current_user.role in (UserRole.MANAGER, UserRole.SUPERVISOR):
        if class_obj.kindergarten_id != current_user.kindergarten_id:
            return templates.TemplateResponse(request=request, name="403.html", status_code=403, context={"current_user": current_user})
    return templates.TemplateResponse(request=request, name="classes/view.html", context={"current_user": current_user, "class": class_obj})


@router.get("/children", response_class=HTMLResponse)
async def children_list_redirect(request: Request, current_user: User = Depends(get_current_user_or_redirect)):
    """Children list - redirect parents to parent children page"""
    user_role = current_user.role.value if hasattr(current_user.role, 'value') else current_user.role
    if user_role == 'PARENT':
        return RedirectResponse(url="/parent/children")
    # For manager/admin/supervisor, redirect to dashboard (no staff children list page exists)
    return RedirectResponse(url="/dashboard")


@router.get("/children/{child_id}", response_class=HTMLResponse)
async def view_child(request: Request, child_id: int, db: Session = Depends(get_db), current_user: User = Depends(get_current_user_or_redirect)):
    """View child details"""
    from models import Child, ParentProfile, EnrollmentApplication, EnrollmentStatus
    child = db.query(Child).filter(Child.id == child_id).first()
    if not child:
        return templates.TemplateResponse(request=request, name="404.html", status_code=404)
    # Access control
    if current_user.role == UserRole.PARENT:
        parent_profile = db.query(ParentProfile).filter(ParentProfile.user_id == current_user.id).first()
        if not parent_profile or child.parent_id != parent_profile.id:
            return templates.TemplateResponse(request=request, name="403.html", status_code=403, context={"current_user": current_user})
    elif current_user.role in [UserRole.MANAGER, UserRole.SUPERVISOR]:
        active_statuses = [EnrollmentStatus.ACTIVE, EnrollmentStatus.ACCEPTED]
        enrollment = db.query(EnrollmentApplication).filter(
            EnrollmentApplication.child_id == child_id,
            EnrollmentApplication.kindergarten_id == current_user.kindergarten_id,
            EnrollmentApplication.status.in_(active_statuses)
        ).first()
        if not enrollment:
            return templates.TemplateResponse(request=request, name="403.html", status_code=403, context={"current_user": current_user})
    return templates.TemplateResponse(request=request, name="children/view.html", context={"current_user": current_user, "child": child})


@router.get("/enroll", response_class=HTMLResponse)
async def enroll_child(request: Request, current_user: User = Depends(get_current_user_or_redirect)):
    """Enroll a child - redirects to enrollment create"""
    return RedirectResponse(url="/enrollments/create")


@router.get("/my-reports", response_class=HTMLResponse)
async def parent_reports(
    request: Request,
    current_user: User = Depends(get_current_user_or_redirect),
    db: Session = Depends(get_db),
):
    """Parent view of their children's reports."""
    user_role = current_user.role.value if hasattr(current_user.role, "value") else current_user.role
    if user_role != "PARENT":
        return RedirectResponse(url="/dashboard")

    selected_date = _today()
    raw_date = request.query_params.get("date")
    if raw_date:
        try:
            selected_date = date.fromisoformat(raw_date)
        except ValueError:
            selected_date = _today()

    parent_profile = db.query(models.ParentProfile).filter(
        models.ParentProfile.user_id == current_user.id
    ).first()

    if not parent_profile:
        return templates.TemplateResponse(
            request=request,
            name="reports/parent_list.html",
            context={"current_user": current_user, "today": selected_date.isoformat(), "reports": []},
        )

    child_ids = [
        child_id
        for (child_id,) in db.query(models.Child.id).filter(
            models.Child.parent_id == parent_profile.id
        ).all()
    ]

    child_id_filter = request.query_params.get("child_id")
    if child_id_filter:
        try:
            requested_child_id = int(child_id_filter)
        except ValueError:
            requested_child_id = -1
        if requested_child_id not in child_ids:
            return templates.TemplateResponse(
                request=request,
                name="403.html",
                status_code=403,
                context={"current_user": current_user},
            )
        child_ids = [requested_child_id]

    reports = []
    if child_ids:
        visible_statuses = [
            models.DailyReportStatus.APPROVED,
            models.DailyReportStatus.SENT_TO_PARENT,
        ]
        reports = db.query(models.DailyReport).filter(
            models.DailyReport.child_id.in_(child_ids),
            models.DailyReport.date == selected_date,
            models.DailyReport.status.in_(visible_statuses),
        ).order_by(
            models.DailyReport.created_at.desc(),
            models.DailyReport.id.desc(),
        ).all()

        child_name_by_id = {
            child.id: f"{child.first_name} {child.last_name}".strip()
            for child in db.query(models.Child).filter(models.Child.id.in_(child_ids)).all()
        }
        for report in reports:
            report.child_name = child_name_by_id.get(report.child_id, "طفل")

    return templates.TemplateResponse(
        request=request,
        name="reports/parent_list.html",
        context={
            "current_user": current_user,
            "today": selected_date.isoformat(),
            "reports": reports,
        },
    )




@router.get("/audit-logs", response_class=HTMLResponse)
async def audit_logs_page(request: Request, current_user: User = Depends(get_current_user_or_redirect)):
    """Audit logs page (admin only)"""
    if current_user.role != UserRole.ADMIN:
        from fastapi.responses import RedirectResponse
        return RedirectResponse(url="/dashboard")
    return templates.TemplateResponse(request=request, name="admin/audit_logs.html", context={"current_user": current_user})


@router.get("/admin/audit-logs", response_class=HTMLResponse, include_in_schema=False)
async def admin_audit_logs_page(request: Request, current_user: User = Depends(get_current_user_or_redirect)):
    """Admin-namespaced alias for the audit logs page."""
    return await audit_logs_page(request, current_user)

# -----------------------------------------------------------------------------
# Admin User Management
# -----------------------------------------------------------------------------

@router.get("/admin/users", response_class=HTMLResponse)
async def list_users_page(request: Request, current_user: User = Depends(get_current_user_or_redirect)):
    """Admin user list page"""
    if current_user.role not in [UserRole.ADMIN, UserRole.MANAGER]:
         return RedirectResponse("/")
    return templates.TemplateResponse(request=request, name="admin/users/list.html", context={"current_user": current_user})

@router.get("/admin/users/create", response_class=HTMLResponse)
async def create_user_page(request: Request, db: Session = Depends(get_db), current_user: User = Depends(get_current_user_or_redirect)):
    if current_user.role not in [UserRole.ADMIN, UserRole.MANAGER]:
         return RedirectResponse("/")
    
    if current_user.role == UserRole.MANAGER:
        kgs = db.query(Kindergarten).filter(Kindergarten.id == current_user.kindergarten_id).all()
        is_manager_user = True
    else:
        kgs = db.query(Kindergarten).all()
        is_manager_user = False

    return templates.TemplateResponse(request=request, name="admin/users/form.html", context={
        "current_user": current_user, 
        "kindergartens": kgs, 
        "user_obj": None,
        "is_manager_user": is_manager_user
    })

@router.get("/admin/users/{user_id}/edit", response_class=HTMLResponse)
async def edit_user_page(request: Request, user_id: int, db: Session = Depends(get_db), current_user: User = Depends(get_current_user_or_redirect)):
    if current_user.role not in [UserRole.ADMIN, UserRole.MANAGER]:
         return RedirectResponse("/")
    
    user_obj = db.query(User).filter(User.id == user_id).first()
    if not user_obj:
        return templates.TemplateResponse(request=request, name="404.html", status_code=404)
    
    # Check permission for Manager
    if current_user.role == UserRole.MANAGER:
        if user_obj.kindergarten_id != current_user.kindergarten_id:
             return RedirectResponse("/") 
        kgs = db.query(Kindergarten).filter(Kindergarten.id == current_user.kindergarten_id).all()
        is_manager_user = True
    else:
        kgs = db.query(Kindergarten).all()
        is_manager_user = False

    return templates.TemplateResponse(request=request, name="admin/users/form.html", context={
        "current_user": current_user, 
        "kindergartens": kgs, 
        "user_obj": user_obj,
        "is_manager_user": is_manager_user
    })


@router.get("/admin/messages/compose", response_class=HTMLResponse)
async def admin_message_compose(request: Request, current_user: User = Depends(get_current_user_or_redirect)):
    if current_user.role != UserRole.ADMIN:
        return RedirectResponse("/dashboard")
    return templates.TemplateResponse(
        request=request,
        name="admin/messages/compose.html",
        context={
            "current_user": current_user,
            "governorates": settings.JORDAN_GOVERNORATES,
            "governorates_en": settings.JORDAN_GOVERNORATES_ENGLISH
        }
    )


@router.get("/admin/import-kindergartens", response_class=HTMLResponse)
async def import_kindergartens_page(request: Request, current_user: User = Depends(get_current_user_or_redirect)):
    """Import kindergartens from Excel page"""
    if current_user.role != UserRole.ADMIN:
        return RedirectResponse("/dashboard")
    return templates.TemplateResponse(
        request=request,
        name="admin/import_kindergartens.html",
        context={"current_user": current_user}
    )


@router.get("/admin/imported-kindergartens", response_class=HTMLResponse)
async def list_imported_kindergartens_page(request: Request, current_user: User = Depends(get_current_user_or_redirect)):
    """List imported kindergartens page"""
    if current_user.role not in [UserRole.ADMIN, UserRole.MANAGER]:
        return RedirectResponse("/dashboard")
    return templates.TemplateResponse(
        request=request,
        name="admin/imported_kindergartens.html",
        context={"current_user": current_user}
    )


# -----------------------------------------------------------------------------
# Admin Analytics & Reporting
# -----------------------------------------------------------------------------

@router.get("/admin", response_class=HTMLResponse)
async def admin_root(request: Request):
    """Redirect /admin to /admin/dashboard"""
    return RedirectResponse(url="/admin/dashboard", status_code=302)


@router.get("/admin/dashboard", response_class=HTMLResponse)
async def admin_dashboard_page(request: Request, current_user: User = Depends(get_current_user_or_redirect)):
    """Admin dashboard page with system overview and KPIs"""
    if current_user.role != UserRole.ADMIN:
        return RedirectResponse("/dashboard")
    return templates.TemplateResponse(
        request=request,
        name="admin_dashboard.html",
        context={"current_user": current_user, "today": _today()}
    )


@router.get("/admin/kg-overview", response_class=HTMLResponse)
async def admin_kg_overview(request: Request, current_user: User = Depends(get_current_user_or_redirect)):
    """Kindergarten overview dashboard"""
    if current_user.role != UserRole.ADMIN:
        return RedirectResponse("/dashboard")
    return templates.TemplateResponse(
        request=request,
        name="admin/kg_overview.html",
        context={"current_user": current_user, "today": _today(), "now": datetime.now(timezone(timedelta(hours=3))).strftime("%d %B %Y, %I:%M %p")}
    )


@router.get("/admin/kpi", response_class=HTMLResponse)
async def admin_kpi_dashboard(request: Request, current_user: User = Depends(get_current_user_or_redirect)):
    """Admin network-level KPI dashboard"""
    if current_user.role != UserRole.ADMIN:
        return RedirectResponse("/dashboard")
    return templates.TemplateResponse(
        request=request,
        name="admin/kpi.html",
        context={
            "current_user": current_user,
            "today": _today(),
            "jordan_governorates": settings.JORDAN_GOVERNORATES,
        }
    )


@router.get("/admin/analytics", response_class=HTMLResponse, include_in_schema=False)
@router.get("/admin/analytics/dashboard", response_class=HTMLResponse)
async def admin_analytics(request: Request, current_user: User = Depends(get_current_user_or_redirect)):
    """Admin analytics and reporting dashboard"""
    if current_user.role != UserRole.ADMIN:
        return RedirectResponse("/dashboard")
    return templates.TemplateResponse(
        request=request,
        name="admin/analytics/dashboard.html",
        context={"current_user": current_user, "today": _today()}
    )

@router.get("/admin/analytics/reports", response_class=HTMLResponse)
async def admin_reports(request: Request, current_user: User = Depends(get_current_user_or_redirect)):
    """Admin centralized reports page"""
    if current_user.role != UserRole.ADMIN:
        return RedirectResponse("/dashboard")
    return templates.TemplateResponse(
        request=request,
        name="admin/analytics/reports.html",
        context={"current_user": current_user, "today": _today()}
    )


@router.get("/admin/governance-reports", response_class=HTMLResponse)
async def admin_governance_reports(request: Request, current_user: User = Depends(get_current_user_or_redirect)):
    """Admin governance reports dashboard for daily report compliance"""
    if current_user.role != UserRole.ADMIN:
        return RedirectResponse("/dashboard")
    return templates.TemplateResponse(
        request=request,
        name="admin/governance_reports.html",
        context={"current_user": current_user, "today": _today()}
    )


@router.get("/admin/classification", response_class=HTMLResponse)
async def admin_classification(request: Request, current_user: User = Depends(get_current_user_or_redirect)):
    """Admin classification and benchmarking page"""
    if current_user.role != UserRole.ADMIN:
        return RedirectResponse("/dashboard")
    return templates.TemplateResponse(
        request=request,
        name="admin/classification.html",
        context={"current_user": current_user, "today": _today()}
    )


@router.get("/manager/benchmarking", response_class=HTMLResponse)
async def manager_benchmarking(request: Request, current_user: User = Depends(get_current_user_or_redirect)):
    """Manager anonymized benchmarking page"""
    if current_user.role != UserRole.MANAGER:
        return RedirectResponse("/dashboard")
    return templates.TemplateResponse(
        request=request,
        name="manager/benchmarking.html",
        context={"current_user": current_user, "today": _today()}
    )


@router.get("/manager/kpi", response_class=HTMLResponse)
async def manager_kpi_page(request: Request, current_user: User = Depends(get_current_user_or_redirect)):
    """Manager KPI dashboard page"""
    if current_user.role != UserRole.MANAGER:
        return RedirectResponse("/dashboard")
    return templates.TemplateResponse(
        request=request,
        name="manager/kpi.html",
        context={"current_user": current_user, "today": _today()}
    )


@router.get("/supervisor/kpi", response_class=HTMLResponse)
async def supervisor_kpi_page(request: Request, current_user: User = Depends(get_current_user_or_redirect)):
    """Supervisor personal KPI dashboard"""
    if current_user.role != UserRole.SUPERVISOR:
        return RedirectResponse("/dashboard")
    return templates.TemplateResponse(
        request=request,
        name="supervisor/kpi.html",
        context={"current_user": current_user, "today": _today()}
    )


@router.get("/supervisor/performance", response_class=HTMLResponse)
async def supervisor_performance(request: Request, current_user: User = Depends(get_current_user_or_redirect)):
    """Supervisor self-performance page"""
    if current_user.role != UserRole.SUPERVISOR:
        return RedirectResponse("/dashboard")
    return templates.TemplateResponse(
        request=request,
        name="supervisor/performance.html",
        context={"current_user": current_user, "today": _today()}
    )


@router.get("/supervisor/observations", response_class=HTMLResponse)
async def supervisor_observations(request: Request, current_user: User = Depends(get_current_user_or_redirect)):
    """Supervisor observations recording page."""
    if current_user.role != UserRole.SUPERVISOR:
        return RedirectResponse("/dashboard")
    return templates.TemplateResponse(
        request=request,
        name="supervisor/observations.html",
        context={"current_user": current_user, "today": _today()}
    )


@router.get("/admin/messages", response_class=HTMLResponse)
async def admin_messages_list(
    request: Request,
    current_user: User = Depends(get_current_user_or_redirect),
    db: Session = Depends(get_db)
):
    if current_user.role != UserRole.ADMIN:
        return RedirectResponse("/dashboard")
    messages = (
        db.query(models.Message)
        .order_by(models.Message.created_at.desc())
        .limit(25)
        .all()
    )
    message_list = [
        {
            "id": msg.id,
            "subject": msg.subject or "Ø¨Ø¯ÙˆÙ† ÙˆØµÙˆÙ„",
            "created_at": msg.created_at,
            "recipient_count": msg.recipient_count or 0,
            "thread_type": msg.thread_type.value,
            "allow_replies": msg.allow_replies,
            "target_mode": msg.target_mode,
            "target_roles": msg.target_roles,
        }
        for msg in messages
    ]
    return templates.TemplateResponse(
        request=request,
        name="admin/messages/list.html",
        context={"current_user": current_user, "messages": message_list}
    )


@router.get("/admin/analytics/charts", response_class=HTMLResponse)
async def admin_charts_explorer(request: Request, current_user: User = Depends(get_current_user_or_redirect)):
    """Admin AI-assisted chart explorer page"""
    if current_user.role != UserRole.ADMIN:
        return RedirectResponse("/dashboard")
    return templates.TemplateResponse(
        request=request,
        name="admin/analytics/charts_dashboard.html",
        context={"current_user": current_user, "today": _today()}
    )


@router.get("/admin/analytics/drilldown/{dimension_type}/{dimension_id}", response_class=HTMLResponse)
async def admin_analytics_drilldown(
    request: Request,
    dimension_type: str,
    dimension_id: str,
    current_user: User = Depends(get_current_user_or_redirect)
):
    """Drilldown page for analytics."""
    if current_user.role != UserRole.ADMIN:
        return RedirectResponse("/dashboard")

    return templates.TemplateResponse(
        request=request,
        name="admin/analytics/drilldown.html",
        context={
            "current_user": current_user,
            "dimension_type": dimension_type,
            "dimension_id": dimension_id,
            "today": _today()
        }
    )


# ----------------------------------------------------------------------------- 
# Absence Requests
# -----------------------------------------------------------------------------

@router.get("/absence-requests", response_class=HTMLResponse)
async def parent_absence_requests(
    request: Request,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user_or_redirect),
):
    """Parent page: view & submit absence requests."""
    user_role = current_user.role.value if hasattr(current_user.role, 'value') else current_user.role
    if user_role != 'PARENT':
        return RedirectResponse(url="/dashboard")

    parent_profile = db.query(models.ParentProfile).filter(
        models.ParentProfile.user_id == current_user.id
    ).first()
    children = []
    if parent_profile:
        children = db.query(models.Child).filter(
            models.Child.parent_id == parent_profile.id
        ).all()

    return templates.TemplateResponse(
        request=request,
        name="attendance/absence_requests.html",
        context={
            "current_user": current_user,
            "children": children,
            "today": _today(),
        }
    )


@router.get("/manager/absence-requests", response_class=HTMLResponse)
async def manager_absence_requests(
    request: Request,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user_or_redirect),
):
    """Manager page: review absence requests."""
    user_role = current_user.role.value if hasattr(current_user.role, 'value') else current_user.role
    if user_role not in ('MANAGER', 'ADMIN'):
        return RedirectResponse(url="/dashboard")

    return templates.TemplateResponse(
        request=request,
        name="manager/absence_requests.html",
        context={
            "current_user": current_user,
            "today": _today(),
        }
    )


# =============================================================================
# Admin Incident Reporting Pages
# =============================================================================

@router.get("/admin/reports/incidents/generate", response_class=HTMLResponse)
async def generate_incident_report_page(request: Request, current_user: User = Depends(get_current_user_or_redirect)):
    """Page for admin to generate incident reports"""
    user_role = current_user.role.value if hasattr(current_user.role, 'value') else current_user.role
    if user_role != 'ADMIN':
        return RedirectResponse(url="/dashboard")
    return templates.TemplateResponse(request=request, name="admin/analytics/incident_reports_generate.html", context={"current_user": current_user})


@router.get("/admin/reports/incidents", response_class=HTMLResponse)
async def admin_incident_reports_page(request: Request, current_user: User = Depends(get_current_user_or_redirect)):
    """Admin incident report list page."""
    user_role = current_user.role.value if hasattr(current_user.role, 'value') else current_user.role
    if user_role != 'ADMIN':
        return RedirectResponse(url="/dashboard")
    return templates.TemplateResponse(request=request, name="admin/incident_reports_list.html", context={"current_user": current_user})


@router.get("/admin/analytics/daily-reports", response_class=HTMLResponse)
async def daily_reports_page(request: Request, current_user: User = Depends(get_current_user_or_redirect)):
    """Page to list generated reports"""
    user_role = current_user.role.value if hasattr(current_user.role, 'value') else current_user.role
    if user_role != 'ADMIN':
        return RedirectResponse(url="/dashboard")
    return templates.TemplateResponse(request=request, name="admin/analytics/daily_reports.html", context={"current_user": current_user})


@router.get("/admin/reports/incidents/{report_id}", response_class=HTMLResponse)
async def incident_report_detail_page(report_id: int, request: Request, current_user: User = Depends(get_current_user_or_redirect)):
    """Page to view incident report details"""
    user_role = current_user.role.value if hasattr(current_user.role, 'value') else current_user.role
    if user_role != 'ADMIN':
        return RedirectResponse(url="/dashboard")
    return templates.TemplateResponse(request=request, name="admin/analytics/incident_report_detail.html", context={"current_user": current_user, "report_id": report_id})


# =============================================================================
# Admin â€” Impersonation & Safety Analytics pages
# =============================================================================

@router.get("/admin/impersonate", response_class=HTMLResponse)
async def admin_impersonate_page(request: Request, current_user: User = Depends(get_current_user_or_redirect)):
    user_role = current_user.role.value if hasattr(current_user.role, 'value') else current_user.role
    if user_role != 'ADMIN':
        return RedirectResponse(url="/dashboard")
    return templates.TemplateResponse(request=request, name="admin/impersonate.html", context={"current_user": current_user})


@router.get("/admin/safety-analytics", response_class=HTMLResponse)
async def admin_safety_analytics_page(request: Request, current_user: User = Depends(get_current_user_or_redirect)):
    user_role = current_user.role.value if hasattr(current_user.role, 'value') else current_user.role
    if user_role != 'ADMIN':
        return RedirectResponse(url="/dashboard")
    return templates.TemplateResponse(request=request, name="admin/safety_analytics.html", context={"current_user": current_user})


# -----------------------------------------------------------------------------
# Admin Contact Messages  (P1-D: page route was missing)
# -----------------------------------------------------------------------------

@router.get("/admin/contact-messages", response_class=HTMLResponse)
async def admin_contact_messages_page(
    request: Request,
    q: Optional[str] = None,
    status_filter: Optional[str] = None,
    page: int = 1,
    current_user: User = Depends(get_current_user_or_redirect),
    db: Session = Depends(get_db),
):
    """
    Server-side rendered contact-messages list for admin.
    Queries the DB directly so the template has all data without a JS round-trip.
    """
    user_role = current_user.role.value if hasattr(current_user.role, 'value') else current_user.role
    if user_role != 'ADMIN':
        return RedirectResponse(url="/dashboard")

    page_size = 25
    query = db.query(models.ContactMessage)

    if q:
        q = q[:100]
        term = f"%{q}%"
        query = query.filter(
            or_(
                models.ContactMessage.name.ilike(term),
                models.ContactMessage.subject.ilike(term),
                models.ContactMessage.email.ilike(term),
            )
        )

    if status_filter == "open":
        query = query.filter(models.ContactMessage.is_resolved.is_(False))
    elif status_filter == "resolved":
        query = query.filter(models.ContactMessage.is_resolved.is_(True))

    total = query.count()
    page = max(1, page)
    total_pages = max(1, (total + page_size - 1) // page_size)
    offset = (page - 1) * page_size
    contact_messages = (
        query.order_by(models.ContactMessage.submitted_at.desc())
        .offset(offset)
        .limit(page_size)
        .all()
    )

    return templates.TemplateResponse(
        request=request,
        name="admin/contact_messages.html",
        context={
            "current_user": current_user,
            "contact_messages": contact_messages,
            "filters": {"q": q or "", "status_filter": status_filter or ""},
            "pagination": {"total": total, "page": page, "total_pages": total_pages},
        },
    )


# -----------------------------------------------------------------------------
# Admin Alerts
# -----------------------------------------------------------------------------

@router.get("/admin/alerts", response_class=HTMLResponse)
async def admin_alerts_page(request: Request, current_user: User = Depends(get_current_user_or_redirect)):
    user_role = current_user.role.value if hasattr(current_user.role, 'value') else current_user.role
    if user_role != 'ADMIN':
        return RedirectResponse(url="/dashboard")
    return templates.TemplateResponse(request=request, name="admin/alerts.html", context={"current_user": current_user, "today": _today()})


# -----------------------------------------------------------------------------
# Admin Heat Map
# -----------------------------------------------------------------------------

@router.get("/admin/heatmap", response_class=HTMLResponse)
async def admin_heatmap_page(request: Request, current_user: User = Depends(get_current_user_or_redirect)):
    user_role = current_user.role.value if hasattr(current_user.role, 'value') else current_user.role
    if user_role != 'ADMIN':
        return RedirectResponse(url="/dashboard")
    return templates.TemplateResponse(request=request, name="admin/heatmap.html", context={
        "current_user": current_user,
        "today": _today(),
        "google_maps_api_key": settings.GOOGLE_MAPS_API_KEY,
    })


# -----------------------------------------------------------------------------
# Admin Data Management â€” Import Logs
# -----------------------------------------------------------------------------

@router.get("/admin/import-logs", response_class=HTMLResponse)
async def admin_import_logs_page(request: Request, current_user: User = Depends(get_current_user_or_redirect)):
    """Admin import logs page â€” history of CSV/Excel import jobs"""
    user_role = current_user.role.value if hasattr(current_user.role, 'value') else current_user.role
    if user_role != 'ADMIN':
        return RedirectResponse(url="/dashboard")
    return templates.TemplateResponse(request=request, name="admin/import_logs.html", context={"current_user": current_user, "today": _today()})


# -----------------------------------------------------------------------------
# Admin User Management â€” Import Users
# -----------------------------------------------------------------------------

@router.get("/admin/users/import", response_class=HTMLResponse)
async def admin_import_users_page(request: Request, current_user: User = Depends(get_current_user_or_redirect)):
    """Admin import users page â€” bulk CSV import of user accounts"""
    user_role = current_user.role.value if hasattr(current_user.role, 'value') else current_user.role
    if user_role != 'ADMIN':
        return RedirectResponse(url="/dashboard")
    return templates.TemplateResponse(request=request, name="admin/import_users.html", context={"current_user": current_user, "today": _today()})


# -----------------------------------------------------------------------------
# Admin Governance â€” Reminders
# -----------------------------------------------------------------------------

@router.get("/admin/governance/reminders", response_class=HTMLResponse)
async def admin_governance_reminders_page(request: Request, current_user: User = Depends(get_current_user_or_redirect)):
    """Admin governance reminders page â€” manage compliance reminders sent to supervisors"""
    user_role = current_user.role.value if hasattr(current_user.role, 'value') else current_user.role
    if user_role != 'ADMIN':
        return RedirectResponse(url="/dashboard")
    return templates.TemplateResponse(request=request, name="admin/governance_reminders.html", context={"current_user": current_user, "today": _today()})


# -----------------------------------------------------------------------------
# Admin Profile & Settings
# -----------------------------------------------------------------------------

@router.get("/admin/profile", response_class=HTMLResponse)
async def admin_profile_page(
    request: Request,
    current_user: User = Depends(get_current_user_or_redirect),
    db: Session = Depends(get_db),
):
    """Admin profile page â€” view account details and change password"""
    user_role = current_user.role.value if hasattr(current_user.role, 'value') else current_user.role
    if user_role != 'ADMIN':
        return RedirectResponse(url="/dashboard")

    _JORDAN_TZ = timezone(timedelta(hours=3))
    now_jordan = datetime.now(_JORDAN_TZ)

    # Total audit events for stats widget
    from sqlalchemy import func as _func
    total_actions = db.query(_func.count(models.AuditLog.id)).filter(
        models.AuditLog.user_id == current_user.id
    ).scalar() or 0

    # Days active since account creation
    days_active = 0
    if current_user.created_at:
        created = current_user.created_at
        if created.tzinfo is None:
            created = created.replace(tzinfo=_JORDAN_TZ)
        days_active = max(0, (now_jordan - created).days)

    # Recent audit events (last 10) for the activity feed
    recent_events = (
        db.query(models.AuditLog)
        .filter(models.AuditLog.user_id == current_user.id)
        .order_by(models.AuditLog.created_at.desc())
        .limit(10)
        .all()
    )

    return templates.TemplateResponse(
        request=request,
        name="admin/profile.html",
        context={
            "current_user": current_user,
            "total_actions": total_actions,
            "days_active": days_active,
            "recent_events": recent_events,
            "now_jordan": now_jordan,
        },
    )


@router.get("/admin/settings", response_class=HTMLResponse)
async def admin_settings_page(request: Request, current_user: User = Depends(get_current_user_or_redirect)):
    """Admin settings page â€” view system configuration"""
    user_role = current_user.role.value if hasattr(current_user.role, 'value') else current_user.role
    if user_role != 'ADMIN':
        return RedirectResponse(url="/dashboard")
    return templates.TemplateResponse(request=request, name="admin/settings.html", context={"current_user": current_user})


@router.get("/admin/observability", response_class=HTMLResponse)
async def admin_observability_page(request: Request, current_user: User = Depends(require_admin)):
    """Admin observability dashboard â€” system health, latency, data quality, alert quality."""
    return templates.TemplateResponse(request=request, name="admin/observability_dashboard.html", context={"current_user": current_user})


