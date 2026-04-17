"""
Missing Critical Endpoints - Aggregator
Routes are organized into domain modules under api/.
This file re-exports a unified router for backward compatibility.
"""
from fastapi import APIRouter

router = APIRouter()

# Import domain routers
from api.users import router as users_router
from api.kindergartens import router as kindergartens_router
from api.classes import router as classes_router
from api.enrollment import router as enrollment_router
from api.manager import router as manager_router
from api.parent import router as parent_router
from api.tasks import router as tasks_router
from api.registration import router as registration_router
from api.attendance_routes import router as attendance_router
from api.daily_reports_routes import router as daily_reports_router
from api.children import router as children_router
from api.kpi_routes import router as kpi_router
from api.supervisor import router as supervisor_router
from api.portfolio import router as portfolio_router
from api.audit_routes import router as audit_router

# Mount all domain routers
router.include_router(users_router)
router.include_router(kindergartens_router)
router.include_router(classes_router)
router.include_router(enrollment_router)
router.include_router(manager_router)
router.include_router(parent_router)
router.include_router(tasks_router)
router.include_router(registration_router)
router.include_router(attendance_router)
router.include_router(daily_reports_router)
router.include_router(children_router)
router.include_router(kpi_router)
router.include_router(supervisor_router)
router.include_router(portfolio_router)
router.include_router(audit_router)

# Re-export for backward compatibility
from api.supervisor import get_supervisor_classes  # noqa: F401  (notification_service.py)
from api.attendance_routes import check_in_child, check_out_child  # noqa: F401  (audit_attendance.py)
from api.children import create_incident_json, list_incidents  # noqa: F401  (audit_safety.py)
from api.portfolio import create_health_alert, get_child_health_alerts  # noqa: F401  (audit_safety.py)
