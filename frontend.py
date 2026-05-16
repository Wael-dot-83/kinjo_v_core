from fastapi import APIRouter, Request, Depends, status, HTTPException, Response, Form, Query
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.templating import Jinja2Templates
from fastapi.staticfiles import StaticFiles
from jinja2 import pass_context
from sqlalchemy.orm import Session
from sqlalchemy import or_
from datetime import date
import typing
import re

from database import get_db
from dependencies import get_current_user_optional, get_current_user, get_current_user_or_redirect
from models import User, UserRole, Kindergarten, KindergartenStatus, EnrollmentApplication, AttendanceLog, DailyReport, ContactMessage
from i18n import normalize_language, make_gettext

# Setup templates with UTF-8 encoding
templates = Jinja2Templates(directory="templates")
templates.env.globals['encoding'] = 'utf-8'
# Ensure auto_reload for development
templates.env.auto_reload = True


def _resolve_lang(request: Request) -> str:
    """Resolve UI language: ui_lang cookie > default (ar).
    Accept-Language is intentionally ignored — the platform defaults to Arabic."""
    lang = request.cookies.get("ui_lang", "")
    return normalize_language(lang, default="ar")


@pass_context
def _jinja_gettext(ctx: dict, message: str, **kwargs) -> str:
    req = ctx.get("request")
    lang = _resolve_lang(req) if req else "ar"
    return make_gettext(lang)(message, **kwargs)


@pass_context
def _jinja_ui_lang(ctx: dict) -> str:
    req = ctx.get("request")
    return _resolve_lang(req) if req else "ar"


@pass_context
def _jinja_ui_dir(ctx: dict) -> str:
    req = ctx.get("request")
    lang = _resolve_lang(req) if req else "ar"
    return "rtl" if lang == "ar" else "ltr"


@pass_context
def _jinja_impersonation(ctx: dict) -> typing.Optional[dict]:
    """Returns impersonation session data or None, available as impersonation() in templates."""
    req = ctx.get("request")
    if not req:
        return None
    from rbac import get_impersonation_context
    return get_impersonation_context(req)


templates.env.globals["_"] = _jinja_gettext
templates.env.globals["ui_lang"] = _jinja_ui_lang
templates.env.globals["ui_dir"] = _jinja_ui_dir
templates.env.globals["get_impersonation"] = _jinja_impersonation

router = APIRouter(include_in_schema=False)


# -----------------------------------------------------------------------------
# Home & Auth
# -----------------------------------------------------------------------------

@router.get("/", response_class=HTMLResponse)
async def index(request: Request, current_user: typing.Optional[User] = Depends(get_current_user_optional)):
    if current_user:
        return RedirectResponse(url="/dashboard")
    return RedirectResponse(url="/login")

@router.get("/login", response_class=HTMLResponse)
async def login_page(request: Request, current_user: typing.Optional[User] = Depends(get_current_user_optional)):
    if current_user:
        return RedirectResponse(url="/dashboard")
    return templates.TemplateResponse(request=request, name="auth/login.html")

@router.get("/register", response_class=HTMLResponse)
async def register_page(request: Request, current_user: typing.Optional[User] = Depends(get_current_user_optional)):
    if current_user:
        return RedirectResponse(url="/dashboard")
    return templates.TemplateResponse(request=request, name="auth/register.html")

@router.get("/forgot-password", response_class=HTMLResponse)
async def forgot_password_page(request: Request, current_user: typing.Optional[User] = Depends(get_current_user_optional)):
    if current_user:
        return RedirectResponse(url="/dashboard")
    return templates.TemplateResponse(request=request, name="auth/forgot_password.html")

@router.get("/reset-password", response_class=HTMLResponse)
async def reset_password_page(request: Request, current_user: typing.Optional[User] = Depends(get_current_user_optional)):
    if current_user:
        return RedirectResponse(url="/dashboard")
    return templates.TemplateResponse(request=request, name="auth/reset_password.html")

@router.get("/dashboard", response_class=HTMLResponse)
async def dashboard(request: Request, current_user: User = Depends(get_current_user_or_redirect)):
    if current_user.role == UserRole.SUPERVISOR:
        return templates.TemplateResponse(request=request, name="dashboard/supervisor.html", context={"current_user": current_user, "today": date.today()})
    elif current_user.role == UserRole.PARENT:
        return templates.TemplateResponse(request=request, name="dashboard/parent.html", context={"current_user": current_user, "today": date.today()})
    else:
        # Admin or Manager
        return templates.TemplateResponse(request=request, name="dashboard/index.html", context={"current_user": current_user, "today": date.today()})


@router.get("/supervisor/dashboard", response_class=HTMLResponse)
async def supervisor_dashboard(request: Request, current_user: User = Depends(get_current_user_or_redirect)):
    """Dedicated supervisor dashboard route"""
    if current_user.role != UserRole.SUPERVISOR:
        return RedirectResponse(url="/dashboard")
    return templates.TemplateResponse(request=request, name="dashboard/supervisor.html", context={"current_user": current_user, "today": date.today()})


@router.get("/parent/dashboard", response_class=HTMLResponse)
async def parent_dashboard(request: Request, current_user: User = Depends(get_current_user_or_redirect)):
    """Dedicated parent dashboard route"""
    if current_user.role != UserRole.PARENT:
        return RedirectResponse(url="/dashboard")
    return templates.TemplateResponse(request=request, name="dashboard/parent.html", context={"current_user": current_user})

@router.get("/parent/children", response_class=HTMLResponse)
async def parent_children_page(request: Request, current_user: User = Depends(get_current_user_or_redirect)):
    """Parent: view all registered children"""
    if current_user.role != UserRole.PARENT:
        return RedirectResponse(url="/dashboard")
    return templates.TemplateResponse(request=request, name="parent/children.html", context={"current_user": current_user})

@router.get("/parent/attendance", response_class=HTMLResponse)
async def parent_attendance_page(request: Request, current_user: User = Depends(get_current_user_or_redirect)):
    """Parent: monthly attendance calendar for own children"""
    if current_user.role != UserRole.PARENT:
        return RedirectResponse(url="/dashboard")
    return templates.TemplateResponse(request=request, name="parent/attendance.html", context={"current_user": current_user})

@router.get("/parent/enrollments", response_class=HTMLResponse)
async def parent_enrollments_page(request: Request, current_user: User = Depends(get_current_user_or_redirect)):
    """Parent: list of all enrollment applications"""
    if current_user.role != UserRole.PARENT:
        return RedirectResponse(url="/dashboard")
    return templates.TemplateResponse(request=request, name="parent/enrollments.html", context={"current_user": current_user})

@router.get("/parent/reports", response_class=HTMLResponse)
async def parent_reports_page(request: Request, current_user: User = Depends(get_current_user_or_redirect)):
    """Parent: list of children's daily/progress reports"""
    if current_user.role != UserRole.PARENT:
        return RedirectResponse(url="/dashboard")
    return templates.TemplateResponse(request=request, name="reports/parent_list.html", context={"current_user": current_user})

# -----------------------------------------------------------------------------
# Kindergartens
# -----------------------------------------------------------------------------

@router.get("/kindergartens", response_class=HTMLResponse)
async def list_kindergartens(request: Request, current_user: User = Depends(get_current_user_or_redirect)):
    return templates.TemplateResponse(request=request, name="kindergartens/list.html", context={"current_user": current_user})

@router.get("/kindergartens/create", response_class=HTMLResponse)
async def create_kindergarten_page(request: Request, current_user: User = Depends(get_current_user_or_redirect)):
    if current_user.role not in [UserRole.ADMIN, UserRole.MANAGER]:
        return RedirectResponse(url="/dashboard")
    return templates.TemplateResponse(request=request, name="kindergartens/form.html", context={"current_user": current_user, "kindergarten": None})

@router.get("/kindergartens/{kg_id}", response_class=HTMLResponse)
async def view_kindergarten(request: Request, kg_id: int, db: Session = Depends(get_db), current_user: User = Depends(get_current_user_or_redirect)):
    kg = db.query(Kindergarten).filter(Kindergarten.id == kg_id).first()
    if not kg:
        return templates.TemplateResponse(request=request, name="404.html", status_code=404)
    return templates.TemplateResponse(request=request, name="kindergartens/view.html", context={"current_user": current_user, "kindergarten": kg})

@router.get("/kindergartens/{kg_id}/edit", response_class=HTMLResponse)
async def edit_kindergarten_page(request: Request, kg_id: int, db: Session = Depends(get_db), current_user: User = Depends(get_current_user_or_redirect)):
    if current_user.role not in [UserRole.ADMIN, UserRole.MANAGER]:
        return RedirectResponse(url="/dashboard")
    kg = db.query(Kindergarten).filter(Kindergarten.id == kg_id).first()
    if not kg:
        return templates.TemplateResponse(request=request, name="404.html", status_code=404)
    return templates.TemplateResponse(request=request, name="kindergartens/form.html", context={"current_user": current_user, "kindergarten": kg})

# -----------------------------------------------------------------------------
# Enrollments
# -----------------------------------------------------------------------------

@router.get("/enrollments", response_class=HTMLResponse)
async def list_enrollments(request: Request, current_user: User = Depends(get_current_user_or_redirect)):
    from fastapi.responses import RedirectResponse
    if current_user.role == UserRole.PARENT:
        return RedirectResponse(url="/parent/enrollments", status_code=302)
    if current_user.role == UserRole.SUPERVISOR:
        return RedirectResponse(url="/supervisor/dashboard", status_code=302)
    return templates.TemplateResponse(request=request, name="enrollment/list.html", context={"current_user": current_user})

@router.get("/enrollments/create", response_class=HTMLResponse)
async def create_enrollment_page(request: Request, db: Session = Depends(get_db), current_user: User = Depends(get_current_user_or_redirect)):
    from models import ParentProfile
    kgs = db.query(Kindergarten).filter(Kindergarten.status == KindergartenStatus.ACTIVE).all()
    parent_profile = db.query(ParentProfile).filter(ParentProfile.user_id == current_user.id).first()

    # Build display full name for pre-filling
    parent_full_name = ""
    parent_first_name = ""
    parent_last_name = ""
    parent_type = None
    profile_complete = False
    if parent_profile:
        parent_first_name = parent_profile.first_name or ""
        parent_last_name  = parent_profile.last_name  or ""
        parent_full_name = " ".join(
            p for p in [parent_profile.first_name, parent_profile.second_name, parent_profile.last_name] if p
        )
        parent_type = parent_profile.parent_type
        profile_complete = bool(parent_profile.parent_type and parent_profile.national_id)

    return templates.TemplateResponse(
        request=request,
        name="enrollment/create.html",
        context={
            "current_user":       current_user,
            "kindergartens":      kgs,
            "parent_type":        parent_type,
            "parent_full_name":   parent_full_name,
            "parent_first_name":  parent_first_name,
            "parent_last_name":   parent_last_name,
            "profile_complete":   profile_complete,
        },
    )

@router.get("/enrollments/{app_id}", response_class=HTMLResponse)
async def view_enrollment(request: Request, app_id: int, db: Session = Depends(get_db), current_user: User = Depends(get_current_user_or_redirect)):
    from models import Child, ParentProfile
    enrollment = db.query(EnrollmentApplication).filter(EnrollmentApplication.id == app_id).first()
    if not enrollment:
        return templates.TemplateResponse(request=request, name="404.html", status_code=404)

    # Access-control: parents can only view their own children's enrollments
    if current_user.role == UserRole.PARENT:
        parent_profile = db.query(ParentProfile).filter(ParentProfile.user_id == current_user.id).first()
        if not parent_profile or (enrollment.child and enrollment.child.parent_id != parent_profile.id):
            return templates.TemplateResponse(request=request, name="404.html", status_code=404)

    child = enrollment.child
    today = date.today()

    # Compute child age string
    age_str = "—"
    if child and child.date_of_birth:
        total_months = (today.year - child.date_of_birth.year) * 12 + (today.month - child.date_of_birth.month)
        years, months = divmod(total_months, 12)
        age_str = f"{years} سنة {months} شهر" if years else f"{months} شهر"

    gender_map = {"MALE": "ذكر", "FEMALE": "أنثى"}
    gender_val = ""
    if child and child.gender:
        gender_val = gender_map.get(child.gender.value if hasattr(child.gender, "value") else str(child.gender).upper(), "—")

    mother_name = "—"
    if child:
        parts = [p for p in [child.mother_first_name, child.mother_last_name] if p]
        mother_name = " ".join(parts) if parts else "—"

    status_val = enrollment.status.value if hasattr(enrollment.status, "value") else str(enrollment.status)

    data = {
        "id":                    enrollment.id,
        "status":                status_val.lower(),
        "created_at":            enrollment.created_at.strftime("%Y-%m-%d") if enrollment.created_at else "—",
        "submitted_at":          enrollment.submitted_at.strftime("%Y-%m-%d") if enrollment.submitted_at else None,
        "child_name":            f"{child.first_name} {child.last_name}" if child else "—",
        "dob":                   child.date_of_birth.strftime("%Y-%m-%d") if child and child.date_of_birth else "—",
        "age":                   age_str,
        "gender_ar":             gender_val,
        "national_id":           None,  # child has no national_id column; reserved for future
        "father_name":           (child.father_name or "—") if child else "—",
        "father_phone":          (child.father_phone or "—") if child else "—",
        "father_occupation":     None,
        "mother_name":           mother_name,
        "mother_phone":          (child.mother_phone or "—") if child else "—",
        "mother_nationality":    (child.mother_nationality or "—") if child else "—",
        "medical_conditions":    (child.medical_notes or "") if child else "",
        "vaccinations_up_to_date": child.vaccination_up_to_date if child else False,
        "kindergarten_id":       enrollment.kindergarten_id,
        "class_id":              enrollment.class_id,
    }

    return templates.TemplateResponse(request=request, name="enrollment/view.html", context={"current_user": current_user, "enrollment": data})

# -----------------------------------------------------------------------------
# Attendance
# -----------------------------------------------------------------------------

@router.get("/attendance/daily", response_class=HTMLResponse)
async def attendance_daily(request: Request, current_user: User = Depends(get_current_user_or_redirect)):
    if current_user.role in (UserRole.ADMIN, UserRole.SUPERVISOR):
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Access denied.")
    return templates.TemplateResponse(request=request, name="attendance/daily.html", context={"current_user": current_user, "today": date.today()})

@router.get("/attendance/history", response_class=HTMLResponse)
async def attendance_history(request: Request, current_user: User = Depends(get_current_user_or_redirect)):
    if current_user.role == UserRole.ADMIN:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Admins do not access classroom pages directly.")
    return templates.TemplateResponse(request=request, name="attendance/history.html", context={"current_user": current_user})

@router.get("/attendance/absence-requests", response_class=HTMLResponse)
async def attendance_absence_requests(request: Request, current_user: User = Depends(get_current_user_or_redirect)):
    if current_user.role == UserRole.ADMIN:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Admins do not access classroom pages directly.")
    return templates.TemplateResponse(request=request, name="attendance/absence_requests.html", context={"current_user": current_user})

# -----------------------------------------------------------------------------
# Reports
# -----------------------------------------------------------------------------

@router.get("/reports", response_class=HTMLResponse)
async def list_reports(request: Request, current_user: User = Depends(get_current_user_or_redirect)):
    return templates.TemplateResponse(request=request, name="reports/list.html", context={"current_user": current_user, "today": date.today()})

@router.get("/reports/create", response_class=HTMLResponse)
async def create_report_page(request: Request, current_user: User = Depends(get_current_user_or_redirect)):
    if current_user.role == UserRole.PARENT or current_user.role.value == "ADMIN":
        return RedirectResponse(url="/daily-reports")
    return templates.TemplateResponse(request=request, name="reports/form.html", context={"current_user": current_user, "today": date.today()})

@router.get("/reports/{report_id}", response_class=HTMLResponse)
async def view_report(request: Request, report_id: int, db: Session = Depends(get_db), current_user: User = Depends(get_current_user_or_redirect)):
    from models import DailyReport, Child, ParentProfile
    report = db.query(DailyReport).filter(DailyReport.id == report_id).first()
    if not report:
        return templates.TemplateResponse(request=request, name="404.html", status_code=404)

    # Access-control: parents can only view reports for their own children
    if current_user.role == UserRole.PARENT:
        parent_profile = db.query(ParentProfile).filter(ParentProfile.user_id == current_user.id).first()
        if not parent_profile or (report.child and report.child.parent_id != parent_profile.id):
            return templates.TemplateResponse(request=request, name="404.html", status_code=404)

    child = report.child
    child_name = f"{child.first_name} {child.last_name}" if child else "—"

    teacher_name = "—"
    if report.submitter:
        profile = db.query(ParentProfile).filter(ParentProfile.user_id == report.submitter.id).first()
        if profile:
            teacher_name = " ".join(p for p in [profile.first_name, profile.last_name] if p) or report.submitter.username
        else:
            teacher_name = report.submitter.username or "—"

    import json as _json
    activities = []
    if report.activities:
        try:
            activities = _json.loads(report.activities)
        except Exception:
            activities = [report.activities]

    nap_mins = report.nap_duration_minutes or 0

    report_data = {
        "id":           report.id,
        "child_name":   child_name,
        "date":         report.date.strftime("%Y-%m-%d") if report.date else "—",
        "teacher_name": teacher_name,
        "meals": {
            "breakfast": "✓" if report.breakfast else "—",
            "lunch":     "✓" if report.lunch else "—",
            "snack":     "✓" if report.snack else "—",
            "milk":      "✓" if report.milk else "—",
        },
        "sleep_minutes": nap_mins,
        "activities":    activities,
        "notes":         report.notes or "",
        "photos":        [],
        "status":        report.status.value if hasattr(report.status, "value") else str(report.status),
    }
    return templates.TemplateResponse(request=request, name="reports/view.html", context={"current_user": current_user, "report": report_data})

# -----------------------------------------------------------------------------
# KPI
# -----------------------------------------------------------------------------

@router.get("/kpi/dashboard", response_class=HTMLResponse)
async def kpi_dashboard_page(request: Request, current_user: User = Depends(get_current_user_or_redirect)):
    if current_user.role not in [UserRole.ADMIN, UserRole.MANAGER]:
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
    return templates.TemplateResponse(request=request, name="tasks/list.html", context={"current_user": current_user})


# -----------------------------------------------------------------------------
# Safety & Health
# -----------------------------------------------------------------------------

@router.get("/safety", response_class=HTMLResponse)
async def safety_dashboard(request: Request, current_user: User = Depends(get_current_user_or_redirect)):
    return templates.TemplateResponse(request=request, name="safety/index.html", context={"current_user": current_user})


@router.get("/admin/safety-analytics", response_class=HTMLResponse)
async def admin_safety_analytics(request: Request, current_user: User = Depends(get_current_user_or_redirect)):
    """Admin-only safety incident analytics dashboard."""
    if current_user.role.value != "ADMIN":
        return RedirectResponse(url="/safety")
    return templates.TemplateResponse(request=request, name="admin/safety_analytics.html", context={"current_user": current_user})

@router.get("/safety/incidents/new", response_class=HTMLResponse)
async def create_incident_page(request: Request, db: Session = Depends(get_db), current_user: User = Depends(get_current_user_or_redirect)):
    if current_user.role == UserRole.PARENT:
        return RedirectResponse(url="/dashboard")
    if current_user.role.value == "ADMIN":
        return RedirectResponse(url="/safety?msg=admin_no_create")
    from models import Class as ClassModel
    kg_id = current_user.kindergarten_id
    classes = (
        db.query(ClassModel)
        .filter(ClassModel.kindergarten_id == kg_id, ClassModel.is_active == True)
        .order_by(ClassModel.name_ar)
        .all()
    )
    supervisors = (
        db.query(User)
        .filter(User.kindergarten_id == kg_id, User.role == UserRole.SUPERVISOR)
        .order_by(User.username)
        .all()
    )
    return templates.TemplateResponse(request=request, name="safety/incident_form.html", context={
        "current_user": current_user,
        "classes": classes,
        "supervisors": supervisors,
    })


@router.get("/safety/incidents/{incident_id}", response_class=HTMLResponse)
async def view_incident(
    request: Request,
    incident_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user_or_redirect),
):
    """View a single safety incident."""
    from models import Incident, Child, ParentProfile, User as UserModel
    incident = db.query(Incident).filter(Incident.id == incident_id, Incident.deleted_at.is_(None)).first()
    if not incident:
        return templates.TemplateResponse(request=request, name="404.html", status_code=404)
    # Parents may only view incidents for their own children
    if current_user.role == UserRole.PARENT:
        parent_profile = db.query(ParentProfile).filter(ParentProfile.user_id == current_user.id).first()
        if not parent_profile or incident.child.parent_id != parent_profile.id:
            return templates.TemplateResponse(request=request, name="404.html", status_code=404)
    reporter = db.query(UserModel).filter(UserModel.id == incident.reported_by).first() if incident.reported_by else None
    return templates.TemplateResponse(
        request=request,
        name="safety/incident_detail.html",
        context={"current_user": current_user, "incident": incident, "reporter": reporter},
    )


# -----------------------------------------------------------------------------
# Curriculum
# -----------------------------------------------------------------------------

@router.get("/curriculum", response_class=HTMLResponse)
async def curriculum_dashboard(request: Request, current_user: User = Depends(get_current_user_or_redirect)):
    # Supervisors use /supervisor/observations instead of the general curriculum page.
    # Admins and parents have no curriculum access at all.
    if current_user.role in (UserRole.ADMIN, UserRole.PARENT, UserRole.SUPERVISOR):
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Access denied.")
    return templates.TemplateResponse(request=request, name="curriculum/index.html", context={"current_user": current_user})

@router.get("/curriculum/observations/new", response_class=HTMLResponse)
async def create_observation_page(request: Request, current_user: User = Depends(get_current_user_or_redirect)):
    if current_user.role not in [UserRole.SUPERVISOR, UserRole.MANAGER, UserRole.ADMIN]:
        return RedirectResponse(url="/dashboard")
    return templates.TemplateResponse(request=request, name="curriculum/observation_form.html", context={"current_user": current_user})


# -----------------------------------------------------------------------------
# Additional Missing Routes
# -----------------------------------------------------------------------------

@router.get("/attendance", response_class=HTMLResponse)
async def attendance_main(request: Request, current_user: User = Depends(get_current_user_or_redirect)):
    """Main attendance page - redirects to daily attendance"""
    return RedirectResponse(url="/attendance/daily")


@router.get("/attendance/check-in", response_class=HTMLResponse)
async def attendance_check_in(request: Request, current_user: User = Depends(get_current_user_or_redirect)):
    """Attendance check-in page — Admin is blocked from operational data entry."""
    if current_user.role.value == "ADMIN":
        return RedirectResponse(url="/attendance/daily")
    return templates.TemplateResponse(request=request, name="attendance/daily.html", context={"current_user": current_user, "today": date.today(), "mode": "check-in"})


@router.get("/daily-reports", response_class=HTMLResponse)
async def daily_reports_list(request: Request, current_user: User = Depends(get_current_user_or_redirect)):
    """List all daily reports"""
    return templates.TemplateResponse(request=request, name="reports/list.html", context={"current_user": current_user, "today": date.today()})


@router.get("/daily-reports/create", response_class=HTMLResponse)
async def create_daily_report(request: Request, current_user: User = Depends(get_current_user_or_redirect)):
    """Create a new daily report — Admin and Supervisor are blocked (supervisors use /supervisor/daily-reports/create)."""
    if current_user.role in (UserRole.ADMIN, UserRole.SUPERVISOR):
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Access denied.")
    return templates.TemplateResponse(request=request, name="reports/form.html", context={"current_user": current_user, "today": date.today()})


@router.get("/daily-reports/{report_id}", response_class=HTMLResponse)
async def view_daily_report(request: Request, report_id: int, current_user: User = Depends(get_current_user_or_redirect)):
    """View a daily report — alias route that canonically redirects to /reports/{id}."""
    return RedirectResponse(url=f"/reports/{report_id}", status_code=301)


@router.get("/enrollments/new", response_class=HTMLResponse)
async def new_enrollment(request: Request, db: Session = Depends(get_db), current_user: User = Depends(get_current_user_or_redirect)):
    """New enrollment - redirects to create page"""
    return RedirectResponse(url="/enrollments/create")


@router.get("/incidents/create", response_class=HTMLResponse)
async def create_incident(request: Request, db: Session = Depends(get_db), current_user: User = Depends(get_current_user_or_redirect)):
    """Create a new incident report — alias for /safety/incidents/new."""
    if current_user.role in (UserRole.PARENT, UserRole.ADMIN):
        return RedirectResponse(url="/safety")
    from models import Class as ClassModel
    kg_id = current_user.kindergarten_id
    classes = (
        db.query(ClassModel)
        .filter(ClassModel.kindergarten_id == kg_id, ClassModel.is_active == True)
        .order_by(ClassModel.name_ar)
        .all()
    )
    supervisors = (
        db.query(User)
        .filter(User.kindergarten_id == kg_id, User.role == UserRole.SUPERVISOR)
        .order_by(User.username)
        .all()
    )
    return templates.TemplateResponse(request=request, name="safety/incident_form.html", context={
        "current_user": current_user,
        "classes": classes,
        "supervisors": supervisors,
    })


@router.get("/messages", response_class=HTMLResponse)
async def messages_list(request: Request, current_user: User = Depends(get_current_user_or_redirect)):
    """List all messages"""
    return templates.TemplateResponse(request=request, name="communication/messages.html", context={"current_user": current_user})


@router.get("/messages/new", response_class=HTMLResponse)
async def new_message(request: Request, current_user: User = Depends(get_current_user_or_redirect)):
    """Compose new message"""
    return templates.TemplateResponse(request=request, name="communication/messages.html", context={"current_user": current_user, "compose": True})


@router.get("/profile", response_class=HTMLResponse)
async def user_profile(request: Request, current_user: User = Depends(get_current_user_or_redirect)):
    """User profile page"""
    if current_user.role == UserRole.PARENT:
        return templates.TemplateResponse(request=request, name="parent/profile.html", context={"current_user": current_user})
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
    """View class details"""
    from models import Class
    class_obj = db.query(Class).filter(Class.id == class_id).first()
    if not class_obj:
        return templates.TemplateResponse(request=request, name="404.html", status_code=404)
    return templates.TemplateResponse(request=request, name="classes/view.html", context={"current_user": current_user, "class": class_obj})


@router.get("/children/{child_id}", response_class=HTMLResponse)
async def view_child(request: Request, child_id: int, db: Session = Depends(get_db), current_user: User = Depends(get_current_user_or_redirect)):
    """View child details"""
    from models import Child, ParentProfile
    child = db.query(Child).filter(Child.id == child_id).first()
    if not child:
        return templates.TemplateResponse(request=request, name="404.html", status_code=404)
    # Parents may only view their own children
    if current_user.role == UserRole.PARENT:
        parent_profile = db.query(ParentProfile).filter(ParentProfile.user_id == current_user.id).first()
        if not parent_profile or child.parent_id != parent_profile.id:
            return templates.TemplateResponse(request=request, name="404.html", status_code=404)
    return templates.TemplateResponse(request=request, name="children/view.html", context={"current_user": current_user, "child": child})


@router.get("/enroll", response_class=HTMLResponse)
async def enroll_child(request: Request, current_user: User = Depends(get_current_user_or_redirect)):
    """Enroll a child - redirects to enrollment create"""
    return RedirectResponse(url="/enrollments/create")


@router.get("/my-reports", response_class=HTMLResponse)
async def parent_reports(request: Request, current_user: User = Depends(get_current_user_or_redirect)):
    """Parent view of their children's reports"""
    return templates.TemplateResponse(request=request, name="reports/parent_list.html", context={"current_user": current_user})


# -----------------------------------------------------------------------------
# Static / Public Info Pages
# -----------------------------------------------------------------------------

@router.get("/help", response_class=HTMLResponse)
async def help_page(
    request: Request,
    current_user: typing.Optional[User] = Depends(get_current_user_optional),
):
    """Help / FAQ page – accessible without authentication."""
    return templates.TemplateResponse(
        request=request,
        name="static/help.html",
        context={"current_user": current_user},
    )


@router.get("/privacy", response_class=HTMLResponse)
async def privacy_page(
    request: Request,
    current_user: typing.Optional[User] = Depends(get_current_user_optional),
):
    """Privacy policy page – accessible without authentication."""
    return templates.TemplateResponse(
        request=request,
        name="static/privacy.html",
        context={"current_user": current_user},
    )


@router.get("/terms", response_class=HTMLResponse)
async def terms_page(
    request: Request,
    current_user: typing.Optional[User] = Depends(get_current_user_optional),
):
    """Terms and conditions page – accessible without authentication."""
    return templates.TemplateResponse(
        request=request,
        name="static/terms.html",
        context={"current_user": current_user},
    )


@router.get("/contact", response_class=HTMLResponse)
async def contact_page(
    request: Request,
    db: Session = Depends(get_db),
    current_user: typing.Optional[User] = Depends(get_current_user_optional),
):
    """Contact page – pre-fill fields for authenticated users."""
    prefill = {"name": "", "email": "", "phone": ""}
    if current_user:
        from models import ParentProfile
        profile = db.query(ParentProfile).filter(ParentProfile.user_id == current_user.id).first()
        parts = []
        if profile:
            for p in [profile.first_name, getattr(profile, "second_name", None), profile.last_name]:
                if p:
                    parts.append(p)
        prefill["name"] = " ".join(parts) if parts else (current_user.username or "")
        prefill["email"] = current_user.email or ""
        prefill["phone"] = (profile.phone_number if profile else "") or ""
    return templates.TemplateResponse(
        request=request,
        name="static/contact.html",
        context={"current_user": current_user, "prefill": prefill},
    )


@router.post("/contact", response_class=HTMLResponse)
async def contact_submit(
    request: Request,
    db: Session = Depends(get_db),
    current_user: typing.Optional[User] = Depends(get_current_user_optional),
    name: str = Form(...),
    email: str = Form(...),
    phone: str = Form(...),
    subject: str = Form(...),
    message: str = Form(...),
):
    """Handle contact form submission."""
    errors: list[str] = []
    # Minimal validation
    if not name.strip():
        errors.append("الاسم مطلوب")
    if not re.match(r"[^@\s]+@[^@\s]+\.[^@\s]+", email.strip()):
        errors.append("البريد الإلكتروني غير صحيح")
    if not phone.strip():
        errors.append("رقم الهاتف مطلوب")
    elif not re.fullmatch(r"[0-9+ \-]+", phone.strip()):
        errors.append("رقم الهاتف يجب أن يحتوي على أرقام فقط مع إمكانية استخدام + أو - أو مسافة")
    if len(subject.strip()) < 3:
        errors.append("الموضوع قصير جداً")
    if len(message.strip()) < 10:
        errors.append("الرسالة قصيرة جداً")

    if errors:
        prefill = {"name": name, "email": email, "phone": phone}
        return templates.TemplateResponse(
            request=request,
            name="static/contact.html",
            context={
                "current_user": current_user,
                "prefill": prefill,
                "form_subject": subject,
                "form_message": message,
                "form_errors": errors,
            },
            status_code=422,
        )

    contact = ContactMessage(
        name=name.strip(),
        email=email.strip().lower(),
        phone=phone.strip(),
        subject=subject.strip(),
        message=message.strip(),
    )
    db.add(contact)
    db.commit()

    prefill = {"name": name, "email": email, "phone": phone}
    return templates.TemplateResponse(
        request=request,
        name="static/contact.html",
        context={
            "current_user": current_user,
            "prefill": prefill,
            "messages": [("success", "تم إرسال رسالتك بنجاح. سنرد عليك في أقرب وقت.")],
        },
    )


@router.get("/supervisor/observations", response_class=HTMLResponse)
async def supervisor_observations(request: Request, current_user: User = Depends(get_current_user_or_redirect)):
    """Supervisor observations list"""
    if current_user.role != UserRole.SUPERVISOR:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN)
    return templates.TemplateResponse(request=request, name="curriculum/index.html", context={"current_user": current_user})


# ---------------------------------------------------------------------------
# Supervisor — scoped pages (SUPERVISOR only)
# ---------------------------------------------------------------------------

@router.get("/supervisor/attendance", response_class=HTMLResponse)
async def supervisor_attendance_page(request: Request, current_user: User = Depends(get_current_user_or_redirect)):
    if current_user.role != UserRole.SUPERVISOR:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN)
    return templates.TemplateResponse(
        request=request, name="supervisor/attendance.html",
        context={"current_user": current_user, "today": date.today()}
    )


@router.get("/supervisor/daily-reports", response_class=HTMLResponse)
async def supervisor_daily_reports_page(request: Request, current_user: User = Depends(get_current_user_or_redirect)):
    if current_user.role != UserRole.SUPERVISOR:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN)
    return templates.TemplateResponse(
        request=request, name="supervisor/daily_reports.html",
        context={"current_user": current_user, "today": date.today()}
    )


@router.get("/supervisor/daily-reports/create", response_class=HTMLResponse)
async def supervisor_daily_report_create_page(request: Request, current_user: User = Depends(get_current_user_or_redirect)):
    if current_user.role != UserRole.SUPERVISOR:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN)
    return templates.TemplateResponse(
        request=request, name="supervisor/daily_report_create.html",
        context={"current_user": current_user, "today": date.today()}
    )


@router.get("/supervisor/safety", response_class=HTMLResponse)
async def supervisor_safety_page(request: Request, current_user: User = Depends(get_current_user_or_redirect)):
    if current_user.role != UserRole.SUPERVISOR:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN)
    return templates.TemplateResponse(
        request=request, name="supervisor/safety.html",
        context={"current_user": current_user}
    )


@router.get("/supervisor/messages", response_class=HTMLResponse)
async def supervisor_messages_page(request: Request, current_user: User = Depends(get_current_user_or_redirect)):
    if current_user.role != UserRole.SUPERVISOR:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN)
    return templates.TemplateResponse(
        request=request, name="supervisor/messages.html",
        context={"current_user": current_user}
    )


@router.get("/supervisor/kpi", response_class=HTMLResponse)
async def supervisor_kpi_page(request: Request, current_user: User = Depends(get_current_user_or_redirect)):
    if current_user.role != UserRole.SUPERVISOR:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN)
    return templates.TemplateResponse(
        request=request, name="supervisor/kpi.html",
        context={"current_user": current_user, "today": date.today()}
    )


@router.get("/supervisor/profile", response_class=HTMLResponse)
async def supervisor_profile_page(request: Request, current_user: User = Depends(get_current_user_or_redirect)):
    if current_user.role != UserRole.SUPERVISOR:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN)
    return templates.TemplateResponse(
        request=request, name="supervisor/profile.html",
        context={"current_user": current_user}
    )


@router.get("/supervisor/settings", response_class=HTMLResponse)
async def supervisor_settings_page(request: Request, current_user: User = Depends(get_current_user_or_redirect)):
    if current_user.role != UserRole.SUPERVISOR:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN)
    return templates.TemplateResponse(
        request=request, name="supervisor/settings.html",
        context={"current_user": current_user}
    )


# ---------------------------------------------------------------------------
# Classroom-only pages — block ADMIN (403)
# ---------------------------------------------------------------------------

_CLASSROOM_ROLES = {UserRole.MANAGER, UserRole.SUPERVISOR, UserRole.PARENT}


def _require_not_admin(current_user: User = Depends(get_current_user_or_redirect)):
    if current_user.role == UserRole.ADMIN:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Admins do not access classroom pages directly.",
        )
    return current_user


@router.get("/audit-logs", response_class=HTMLResponse)
async def audit_logs_page(request: Request, current_user: User = Depends(get_current_user_or_redirect)):
    """Audit logs page (admin only)"""
    if current_user.role != UserRole.ADMIN:
        from fastapi.responses import RedirectResponse
        return RedirectResponse(url="/dashboard")
    return templates.TemplateResponse(request=request, name="admin/audit_logs.html", context={"current_user": current_user})


@router.get("/admin/contact-messages", response_class=HTMLResponse)
async def admin_contact_messages(
    request: Request,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user_or_redirect),
    q: str = Query(""),
    status_filter: str = Query(""),
    page: int = Query(1, ge=1),
):
    """Admin contact-message list with search and status filters."""
    if current_user.role != UserRole.ADMIN:
        return RedirectResponse(url="/dashboard")

    query = db.query(ContactMessage)
    term = q.strip()
    if term:
        like = f"%{term}%"
        query = query.filter(
            or_(
                ContactMessage.name.ilike(like),
                ContactMessage.email.ilike(like),
                ContactMessage.phone.ilike(like),
                ContactMessage.subject.ilike(like),
                ContactMessage.message.ilike(like),
            )
        )
    if status_filter == "resolved":
        query = query.filter(ContactMessage.is_resolved.is_(True))
    elif status_filter == "open":
        query = query.filter(ContactMessage.is_resolved.is_(False))

    per_page = 20
    total = query.count()
    total_pages = max(1, (total + per_page - 1) // per_page)
    page = min(page, total_pages)
    contact_messages = (
        query.order_by(ContactMessage.submitted_at.desc(), ContactMessage.id.desc())
        .offset((page - 1) * per_page)
        .limit(per_page)
        .all()
    )
    return templates.TemplateResponse(
        request=request,
        name="admin/contact_messages.html",
        context={
            "current_user": current_user,
            "contact_messages": contact_messages,
            "filters": {"q": q, "status_filter": status_filter},
            "pagination": {"page": page, "total_pages": total_pages, "total": total},
        },
    )


@router.post("/admin/contact-messages/{message_id}/resolve", response_class=HTMLResponse)
async def admin_contact_message_resolve(
    message_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user_or_redirect),
):
    if current_user.role != UserRole.ADMIN:
        return RedirectResponse(url="/dashboard", status_code=303)
    item = db.query(ContactMessage).filter(ContactMessage.id == message_id).first()
    if not item:
        return RedirectResponse(url="/admin/contact-messages", status_code=303)
    item.is_resolved = True
    db.commit()
    return RedirectResponse(url="/admin/contact-messages?status_filter=open", status_code=303)

# -----------------------------------------------------------------------------
# -----------------------------------------------------------------------------
# Manager — Pending Corresponding Assignments
# -----------------------------------------------------------------------------

@router.get("/manager/pending-corresponding", response_class=HTMLResponse)
async def manager_pending_corresponding_page(
    request: Request,
    current_user: User = Depends(get_current_user_or_redirect)
):
    """Manager page — children awaiting a primary guardian assignment."""
    if current_user.role not in [UserRole.ADMIN, UserRole.MANAGER]:
        return RedirectResponse("/dashboard")
    return templates.TemplateResponse(
        request=request,
        name="manager/pending_corresponding.html",
        context={"current_user": current_user}
    )


@router.get("/manager/supervisors", response_class=HTMLResponse)
async def manager_supervisors_page(
    request: Request,
    current_user: User = Depends(get_current_user_or_redirect),
):
    if current_user.role != UserRole.MANAGER:
        return RedirectResponse(url="/dashboard")
    return templates.TemplateResponse(
        request=request,
        name="manager/supervisors.html",
        context={"current_user": current_user},
    )


@router.get("/manager/children", response_class=HTMLResponse)
async def manager_children_page(
    request: Request,
    current_user: User = Depends(get_current_user_or_redirect),
):
    if current_user.role != UserRole.MANAGER:
        return RedirectResponse(url="/dashboard")
    return templates.TemplateResponse(
        request=request,
        name="manager/children.html",
        context={"current_user": current_user},
    )


@router.get("/manager/messages", response_class=HTMLResponse)
async def manager_messages_page(
    request: Request,
    current_user: User = Depends(get_current_user_or_redirect),
):
    if current_user.role not in (UserRole.MANAGER, UserRole.ADMIN):
        return RedirectResponse(url="/dashboard")
    return templates.TemplateResponse(
        request=request,
        name="manager/messages.html",
        context={"current_user": current_user},
    )


@router.get("/manager/new-message", response_class=HTMLResponse)
async def manager_new_message_page(
    request: Request,
    current_user: User = Depends(get_current_user_or_redirect),
):
    if current_user.role != UserRole.MANAGER:
        return RedirectResponse(url="/dashboard")
    return templates.TemplateResponse(
        request=request,
        name="manager/new_message.html",
        context={"current_user": current_user},
    )


# ---------------------------------------------------------------------------
# Manager — Classes management
# ---------------------------------------------------------------------------

@router.get("/manager/classes", response_class=HTMLResponse)
async def manager_classes_page(
    request: Request,
    current_user: User = Depends(get_current_user_or_redirect),
    db: Session = Depends(get_db),
):
    if current_user.role != UserRole.MANAGER:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN)
    from models import Class
    classes = (
        db.query(Class)
        .filter(Class.kindergarten_id == current_user.kindergarten_id, Class.deleted_at.is_(None))
        .order_by(Class.name_ar)
        .all()
    )
    return templates.TemplateResponse(
        request=request,
        name="manager/classes.html",
        context={"current_user": current_user, "classes": classes},
    )


@router.get("/manager/classes/create", response_class=HTMLResponse)
async def manager_class_create_page(
    request: Request,
    current_user: User = Depends(get_current_user_or_redirect),
):
    if current_user.role != UserRole.MANAGER:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN)
    return templates.TemplateResponse(
        request=request,
        name="manager/class_form.html",
        context={"current_user": current_user, "class_obj": None},
    )


@router.get("/manager/classes/{class_id}/edit", response_class=HTMLResponse)
async def manager_class_edit_page(
    request: Request,
    class_id: int,
    current_user: User = Depends(get_current_user_or_redirect),
    db: Session = Depends(get_db),
):
    if current_user.role != UserRole.MANAGER:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN)
    from models import Class
    class_obj = db.query(Class).filter(
        Class.id == class_id,
        Class.kindergarten_id == current_user.kindergarten_id,
        Class.deleted_at.is_(None),
    ).first()
    if not class_obj:
        return templates.TemplateResponse(request=request, name="404.html", status_code=404)
    return templates.TemplateResponse(
        request=request,
        name="manager/class_form.html",
        context={"current_user": current_user, "class_obj": class_obj},
    )


# ---------------------------------------------------------------------------
# Manager — Daily reports review
# ---------------------------------------------------------------------------

@router.get("/manager/daily-reports", response_class=HTMLResponse)
async def manager_daily_reports_review_page(
    request: Request,
    current_user: User = Depends(get_current_user_or_redirect),
):
    if current_user.role != UserRole.MANAGER:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN)
    return templates.TemplateResponse(
        request=request,
        name="manager/daily_reports_review.html",
        context={"current_user": current_user, "today": date.today()},
    )


# ---------------------------------------------------------------------------
# Manager — KPI dashboard
# ---------------------------------------------------------------------------

@router.get("/manager/kpi", response_class=HTMLResponse)
async def manager_kpi_page(
    request: Request,
    current_user: User = Depends(get_current_user_or_redirect),
):
    if current_user.role not in (UserRole.MANAGER, UserRole.ADMIN):
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN)
    return templates.TemplateResponse(
        request=request,
        name="manager/kpi.html",
        context={"current_user": current_user, "today": date.today()},
    )


# ---------------------------------------------------------------------------
# Admin — Impersonation
# ---------------------------------------------------------------------------

@router.get("/admin/impersonate", response_class=HTMLResponse)
async def admin_impersonate_page(
    request: Request,
    current_user: User = Depends(get_current_user_or_redirect),
    db: Session = Depends(get_db),
):
    if current_user.role != UserRole.ADMIN:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN)
    managers = (
        db.query(User)
        .filter(User.role == UserRole.MANAGER, User.deleted_at.is_(None))
        .order_by(User.full_name)
        .all()
    )
    return templates.TemplateResponse(
        request=request,
        name="admin/impersonate.html",
        context={"current_user": current_user, "managers": managers},
    )


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
    else:
        kgs = db.query(Kindergarten).all()

    return templates.TemplateResponse(request=request, name="admin/users/form.html", context={"current_user": current_user, "kindergartens": kgs, "user_obj": None})

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
    else:
        kgs = db.query(Kindergarten).all()

    return templates.TemplateResponse(request=request, name="admin/users/form.html", context={"current_user": current_user, "kindergartens": kgs, "user_obj": user_obj})


# -----------------------------------------------------------------------------
# Admin Analytics & Reporting
# -----------------------------------------------------------------------------

@router.get("/admin/analytics", response_class=HTMLResponse)
async def admin_analytics(request: Request, current_user: User = Depends(get_current_user_or_redirect)):
    """Admin analytics and reporting dashboard"""
    if current_user.role != UserRole.ADMIN:
        return RedirectResponse("/dashboard")
    return templates.TemplateResponse(
        request=request,
        name="admin/analytics/index.html",
        context={"current_user": current_user, "today": date.today()}
    )


# -----------------------------------------------------------------------------
# Parent Enrollment Wizard
# -----------------------------------------------------------------------------

@router.get("/parent/enroll", response_class=HTMLResponse)
async def parent_enroll_wizard_step2(request: Request, current_user: User = Depends(get_current_user_or_redirect)):
    """Parent enrollment wizard — Step 2: Kindergarten selection."""
    if current_user.role != UserRole.PARENT:
        return RedirectResponse(url="/dashboard")
    return templates.TemplateResponse(
        request=request,
        name="parent/wizard/kindergarten_select.html",
        context={"current_user": current_user},
    )


@router.get("/parent/enroll/step3", response_class=HTMLResponse)
async def parent_enroll_wizard_step3(request: Request, current_user: User = Depends(get_current_user_or_redirect)):
    """Parent enrollment wizard — Step 3: Parent/guardian information."""
    if current_user.role != UserRole.PARENT:
        return RedirectResponse(url="/dashboard")
    return templates.TemplateResponse(
        request=request,
        name="parent/wizard/step3_parent_info.html",
        context={"current_user": current_user},
    )


# -----------------------------------------------------------------------------
# Language Switch
# -----------------------------------------------------------------------------

@router.get("/set-language/{lang}")
async def set_language(lang: str, request: Request, next: str = "/dashboard"):
    """Switch UI language by setting a cookie, then redirect back."""
    safe_lang = normalize_language(lang, default="ar")
    # Validate next is a relative path to prevent open-redirect
    if not next.startswith("/"):
        next = "/dashboard"
    response = RedirectResponse(url=next, status_code=302)
    response.set_cookie(
        key="ui_lang",
        value=safe_lang,
        max_age=60 * 60 * 24 * 365,  # 1 year
        httponly=False,  # JS may read for dynamic UI
        samesite="lax",
    )
    return response

