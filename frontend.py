from fastapi import APIRouter, Request, Depends, status, HTTPException
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.templating import Jinja2Templates
from fastapi.staticfiles import StaticFiles
from sqlalchemy.orm import Session
from datetime import date
import typing

from database import get_db
from dependencies import get_current_user_optional, get_current_user, get_current_user_or_redirect
from models import User, UserRole, Kindergarten, EnrollmentApplication, AttendanceLog, DailyReport

# Setup templates with UTF-8 encoding
templates = Jinja2Templates(directory="templates")
templates.env.globals['encoding'] = 'utf-8'
# Ensure auto_reload for development
templates.env.auto_reload = True

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
async def login_page(request: Request):
    return templates.TemplateResponse(request=request, name="auth/login.html")

@router.get("/register", response_class=HTMLResponse)
async def register_page(request: Request):
    return templates.TemplateResponse(request=request, name="auth/register.html")

@router.get("/dashboard", response_class=HTMLResponse)
async def dashboard(request: Request, current_user: User = Depends(get_current_user_or_redirect)):
    user_role = current_user.role.value if hasattr(current_user.role, 'value') else current_user.role

    if user_role == "SUPERVISOR":
        return templates.TemplateResponse(request=request, name="dashboard/supervisor.html", context={"current_user": current_user, "today": date.today()})
    elif user_role == "PARENT":
        return templates.TemplateResponse(request=request, name="dashboard/parent.html", context={"current_user": current_user, "today": date.today()})
    else:
        # Admin or Manager
        return templates.TemplateResponse(request=request, name="dashboard/index.html", context={"current_user": current_user, "today": date.today()})


@router.get("/supervisor/dashboard", response_class=HTMLResponse)
async def supervisor_dashboard(request: Request, current_user: User = Depends(get_current_user_or_redirect)):
    """Dedicated supervisor dashboard route"""
    return templates.TemplateResponse(request=request, name="dashboard/supervisor.html", context={"current_user": current_user})


@router.get("/parent/dashboard", response_class=HTMLResponse)
async def parent_dashboard(request: Request, current_user: User = Depends(get_current_user_or_redirect)):
    """Dedicated parent dashboard route"""
    return templates.TemplateResponse(request=request, name="dashboard/parent.html", context={"current_user": current_user})

# -----------------------------------------------------------------------------
# Kindergartens
# -----------------------------------------------------------------------------

@router.get("/kindergartens", response_class=HTMLResponse)
async def list_kindergartens(request: Request, current_user: User = Depends(get_current_user_or_redirect)):
    return templates.TemplateResponse(request=request, name="kindergartens/list.html", context={"current_user": current_user})

@router.get("/kindergartens/create", response_class=HTMLResponse)
async def create_kindergarten_page(request: Request, current_user: User = Depends(get_current_user_or_redirect)):
    return templates.TemplateResponse(request=request, name="kindergartens/form.html", context={"current_user": current_user, "kindergarten": None})

@router.get("/kindergartens/{kg_id}", response_class=HTMLResponse)
async def view_kindergarten(request: Request, kg_id: int, db: Session = Depends(get_db), current_user: User = Depends(get_current_user_or_redirect)):
    kg = db.query(Kindergarten).filter(Kindergarten.id == kg_id).first()
    if not kg:
        return templates.TemplateResponse(request=request, name="404.html", status_code=404)
    return templates.TemplateResponse(request=request, name="kindergartens/view.html", context={"current_user": current_user, "kindergarten": kg})

@router.get("/kindergartens/{kg_id}/edit", response_class=HTMLResponse)
async def edit_kindergarten_page(request: Request, kg_id: int, db: Session = Depends(get_db), current_user: User = Depends(get_current_user_or_redirect)):
    kg = db.query(Kindergarten).filter(Kindergarten.id == kg_id).first()
    if not kg:
        return templates.TemplateResponse(request=request, name="404.html", status_code=404)
    return templates.TemplateResponse(request=request, name="kindergartens/form.html", context={"current_user": current_user, "kindergarten": kg})

# -----------------------------------------------------------------------------
# Enrollments
# -----------------------------------------------------------------------------

@router.get("/enrollments", response_class=HTMLResponse)
async def list_enrollments(request: Request, current_user: User = Depends(get_current_user_or_redirect)):
    return templates.TemplateResponse(request=request, name="enrollment/list.html", context={"current_user": current_user})

@router.get("/enrollments/create", response_class=HTMLResponse)
async def create_enrollment_page(request: Request, db: Session = Depends(get_db), current_user: User = Depends(get_current_user_or_redirect)):
    kgs = db.query(Kindergarten).filter(Kindergarten.status == 'active').all()
    return templates.TemplateResponse(request=request, name="enrollment/create.html", context={"current_user": current_user, "kindergartens": kgs})

@router.get("/enrollments/{app_id}", response_class=HTMLResponse)
async def view_enrollment(request: Request, app_id: int, db: Session = Depends(get_db), current_user: User = Depends(get_current_user_or_redirect)):
    enrollment = db.query(EnrollmentApplication).filter(EnrollmentApplication.id == app_id).first()
    if not enrollment:
         # For demo purposes if db empty, show mocked view if id=999 or something, but better to just 404
         return templates.TemplateResponse(request=request, name="404.html", status_code=404)
    
    # Enrich data for template - helper function would be better in real app
    # Simple mapping for now
    data = enrollment.__dict__
    
    return templates.TemplateResponse(request=request, name="enrollment/view.html", context={"current_user": current_user, "enrollment": data})

# -----------------------------------------------------------------------------
# Attendance
# -----------------------------------------------------------------------------

@router.get("/attendance/daily", response_class=HTMLResponse)
async def attendance_daily(request: Request, current_user: User = Depends(get_current_user_or_redirect)):
    return templates.TemplateResponse(request=request, name="attendance/daily.html", context={"current_user": current_user, "today": date.today()})

@router.get("/attendance/history", response_class=HTMLResponse)
async def attendance_history(request: Request, current_user: User = Depends(get_current_user_or_redirect)):
    return templates.TemplateResponse(request=request, name="attendance/history.html", context={"current_user": current_user})

# -----------------------------------------------------------------------------
# Reports
# -----------------------------------------------------------------------------

@router.get("/reports", response_class=HTMLResponse)
async def list_reports(request: Request, current_user: User = Depends(get_current_user_or_redirect)):
    return templates.TemplateResponse(request=request, name="reports/list.html", context={"current_user": current_user, "today": date.today()})

@router.get("/reports/create", response_class=HTMLResponse)
async def create_report_page(request: Request, current_user: User = Depends(get_current_user_or_redirect)):
    return templates.TemplateResponse(request=request, name="reports/form.html", context={"current_user": current_user, "today": date.today()})

@router.get("/reports/{report_id}", response_class=HTMLResponse)
async def view_report(request: Request, report_id: int, current_user: User = Depends(get_current_user_or_redirect)):
    # Mock data for view - in real app fetch from DB
    mock_report = {
        "id": report_id,
        "child_name": "أحمد محمد",
        "date": "2023-10-25",
        "teacher_name": "المعلمة منى",
        "mood_emoji": "😊",
        "mood_text": "سعيد",
        "meals": {"breakfast": "أكل كل شيء", "lunch": "أكل المعظم", "snack": "أكل كل شيء"},
        "sleep_minutes": 45,
        "bathroom_count": 3,
        "diaper": {"wet": False, "soiled": False},
        "activities": ["رسم", "قصة", "لعب حر"],
        "notes": "كان أحمد متعاوناً جداً اليوم.",
        "photos": []
    }
    return templates.TemplateResponse(request=request, name="reports/view.html", context={"current_user": current_user, "report": mock_report})

# -----------------------------------------------------------------------------
# KPI
# -----------------------------------------------------------------------------

@router.get("/kpi/dashboard", response_class=HTMLResponse)
async def kpi_dashboard_page(request: Request, current_user: User = Depends(get_current_user_or_redirect)):
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

@router.get("/safety/incidents/new", response_class=HTMLResponse)
async def create_incident_page(request: Request, current_user: User = Depends(get_current_user_or_redirect)):
    return templates.TemplateResponse(request=request, name="safety/incident_form.html", context={"current_user": current_user})


# -----------------------------------------------------------------------------
# Curriculum
# -----------------------------------------------------------------------------

@router.get("/curriculum", response_class=HTMLResponse)
async def curriculum_dashboard(request: Request, current_user: User = Depends(get_current_user_or_redirect)):
    return templates.TemplateResponse(request=request, name="curriculum/index.html", context={"current_user": current_user})

@router.get("/curriculum/observations/new", response_class=HTMLResponse)
async def create_observation_page(request: Request, current_user: User = Depends(get_current_user_or_redirect)):
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
    """Attendance check-in page"""
    return templates.TemplateResponse(request=request, name="attendance/daily.html", context={"current_user": current_user, "today": date.today(), "mode": "check-in"})


@router.get("/daily-reports", response_class=HTMLResponse)
async def daily_reports_list(request: Request, current_user: User = Depends(get_current_user_or_redirect)):
    """List all daily reports"""
    return templates.TemplateResponse(request=request, name="reports/list.html", context={"current_user": current_user, "today": date.today()})


@router.get("/daily-reports/create", response_class=HTMLResponse)
async def create_daily_report(request: Request, current_user: User = Depends(get_current_user_or_redirect)):
    """Create a new daily report"""
    return templates.TemplateResponse(request=request, name="reports/form.html", context={"current_user": current_user, "today": date.today()})


@router.get("/enrollments/new", response_class=HTMLResponse)
async def new_enrollment(request: Request, db: Session = Depends(get_db), current_user: User = Depends(get_current_user_or_redirect)):
    """New enrollment - redirects to create page"""
    return RedirectResponse(url="/enrollments/create")


@router.get("/incidents/create", response_class=HTMLResponse)
async def create_incident(request: Request, current_user: User = Depends(get_current_user_or_redirect)):
    """Create a new incident report"""
    return templates.TemplateResponse(request=request, name="safety/incident_form.html", context={"current_user": current_user})


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
    return templates.TemplateResponse(request=request, name="user/profile.html", context={"current_user": current_user})


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
    from models import Child
    child = db.query(Child).filter(Child.id == child_id).first()
    if not child:
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


@router.get("/contact", response_class=HTMLResponse)
async def contact_page(request: Request, current_user: User = Depends(get_current_user_or_redirect)):
    """Contact page"""
    return templates.TemplateResponse(request=request, name="static/contact.html", context={"current_user": current_user})


@router.get("/supervisor/observations", response_class=HTMLResponse)
async def supervisor_observations(request: Request, current_user: User = Depends(get_current_user_or_redirect)):
    """Supervisor observations - redirects to curriculum observations"""
    return RedirectResponse(url="/curriculum/observations/new")


@router.get("/audit-logs", response_class=HTMLResponse)
async def audit_logs_page(request: Request, current_user: User = Depends(get_current_user_or_redirect)):
    """Audit logs page (admin only)"""
    if current_user.role != UserRole.ADMIN:
        from fastapi.responses import RedirectResponse
        return RedirectResponse(url="/dashboard")
    return templates.TemplateResponse(request=request, name="admin/audit_logs.html", context={"current_user": current_user})

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

