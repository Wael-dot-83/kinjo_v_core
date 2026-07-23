"""
Dashboard customization API endpoints + unified summary endpoint.
"""
import json
import logging
from datetime import date, datetime, timedelta, timezone
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import func
from sqlalchemy.orm import Session
from sqlalchemy.exc import SQLAlchemyError
from typing import List, Dict, Optional
from pydantic import BaseModel
from dependencies import get_current_user
from kpi_service import KPIService
from database import get_db
from dashboard_customization import dashboard_customization
from audit_actions import AuditAction
from admin_security import log_audit_event
import models

router = APIRouter(prefix="/api/dashboard", tags=["Dashboard Customization"])
logger = logging.getLogger(__name__)

_JORDAN_TZ = timezone(timedelta(hours=3))


@router.get("/widgets")
async def get_user_widgets(
    current_user: models.User = Depends(get_current_user),
):
    try:
        widgets = dashboard_customization.get_user_widgets(current_user.id, current_user.role.value.lower())
        return {"widgets": widgets}
    except SQLAlchemyError as e:
        logger.error("Database error fetching dashboard widgets for user_id=%s: %s", current_user.id, str(e), exc_info=True)
        raise HTTPException(status_code=500, detail="Failed to fetch dashboard widget configuration")
    except (json.JSONDecodeError, TypeError, ValueError) as e:
        logger.warning("Invalid dashboard widget configuration for user_id=%s: %s", current_user.id, str(e))
        raise HTTPException(status_code=500, detail="Failed to fetch dashboard widget configuration")


@router.put("/widgets")
async def update_user_widgets(
    widgets: List[Dict],
    current_user: models.User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    try:
        success = dashboard_customization.update_user_widgets(current_user.id, widgets)
        if not success:
            raise HTTPException(status_code=400, detail="Invalid widget configuration")

        log_audit_event(
            db,
            AuditAction.SETTINGS_UPDATED,
            current_user,
            target_type="DashboardWidgets",
            target_ids=current_user.id,
            after_state={"widget_count": len(widgets)},
            sensitivity_level=1,
        )
        db.commit()
        return {"message": "Dashboard widget configuration updated"}
    except HTTPException:
        db.rollback()
        raise
    except (TypeError, ValueError) as e:
        db.rollback()
        logger.warning("Invalid dashboard widget update request for user_id=%s: %s", current_user.id, str(e))
        raise HTTPException(status_code=500, detail="Failed to update dashboard widget configuration")


@router.post("/widgets/reset")
async def reset_user_widgets(
    current_user: models.User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    try:
        success = dashboard_customization.reset_user_widgets(current_user.id, current_user.role.value.lower())
        if not success:
            raise HTTPException(status_code=500, detail="Failed to reset dashboard widget configuration")

        log_audit_event(
            db,
            AuditAction.SETTINGS_UPDATED,
            current_user,
            target_type="DashboardWidgets",
            target_ids=current_user.id,
            after_state={"reset": True},
            sensitivity_level=1,
        )
        db.commit()
        return {"message": "Dashboard widgets reset to role defaults"}
    except (TypeError, ValueError) as e:
        db.rollback()
        logger.warning("Invalid dashboard reset request for user_id=%s: %s", current_user.id, str(e))
        raise HTTPException(status_code=500, detail="Failed to reset dashboard widget configuration")


@router.patch("/widgets/{widget_id}/toggle")
async def toggle_widget(
    widget_id: str,
    enabled: bool,
    current_user: models.User = Depends(get_current_user),
):
    try:
        success = dashboard_customization.toggle_widget(current_user.id, widget_id, enabled)
        if not success:
            raise HTTPException(status_code=404, detail="Widget not found or operation invalid")

        return {"message": f"Widget {'enabled' if enabled else 'disabled'}"}
    except HTTPException:
        raise
    except (TypeError, ValueError) as e:
        logger.warning("Invalid dashboard toggle request for user_id=%s widget_id=%s: %s", current_user.id, widget_id, str(e))
        raise HTTPException(status_code=500, detail="Failed to update widget state")


@router.put("/widgets/reorder")
async def reorder_widgets(
    widget_order: List[str],
    current_user: models.User = Depends(get_current_user),
):
    try:
        success = dashboard_customization.reorder_widgets(current_user.id, widget_order)
        if not success:
            raise HTTPException(status_code=400, detail="Invalid widget order")

        return {"message": "Widget order updated"}
    except HTTPException:
        raise
    except (TypeError, ValueError) as e:
        logger.warning("Invalid dashboard reorder request for user_id=%s: %s", current_user.id, str(e))
        raise HTTPException(status_code=500, detail="Failed to update widget order")


# ── Unified summary endpoint consumed by dashboard_filters.js ─────────────────

class DashboardSummaryRequest(BaseModel):
    range: Optional[str] = "month"
    period_start: Optional[str] = None
    period_end: Optional[str] = None
    kindergarten_id: Optional[int] = None


def _dashboard_kindergarten_scope(
    current_user: models.User,
    requested_kindergarten_id: Optional[int] = None,
) -> Optional[int]:
    """Resolve the only kindergarten a non-admin may use for aggregate data."""
    if current_user.role == models.UserRole.ADMIN:
        return requested_kindergarten_id

    if current_user.role in (models.UserRole.MANAGER, models.UserRole.SUPERVISOR):
        assigned_id = current_user.kindergarten_id
        if not assigned_id:
            raise HTTPException(status_code=403, detail="No kindergarten is assigned to this account")
        if requested_kindergarten_id is not None and requested_kindergarten_id != assigned_id:
            # Do not reveal whether a kindergarten outside the caller's scope exists.
            raise HTTPException(status_code=404, detail="Kindergarten not found")
        return assigned_id

    raise HTTPException(status_code=403, detail="Not authorized")


@router.post("/summary")
def get_dashboard_summary(
    body: DashboardSummaryRequest,
    current_user: models.User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Compact aggregate summary for the inline filter bar + chart panel.
    Returns children count, attendance rate, alert count, and 7-day trend."""
    today = datetime.now(_JORDAN_TZ).date()

    # resolve date window
    if body.period_start and body.period_end:
        try:
            start = date.fromisoformat(body.period_start)
            end = date.fromisoformat(body.period_end)
        except ValueError:
            start = date(today.year, today.month, 1)
            end = today
    elif body.range == "today":
        start = end = today
    elif body.range == "week":
        start = today - timedelta(days=6)
        end = today
    elif body.range == "quarter":
        start = today - timedelta(days=89)
        end = today
    else:  # month (default)
        start = date(today.year, today.month, 1)
        end = today

    scoped_kindergarten_id = _dashboard_kindergarten_scope(
        current_user, body.kindergarten_id
    )
    kg_filter_ids = [scoped_kindergarten_id] if scoped_kindergarten_id else None

    try:
        # active enrolled children
        ch_q = db.query(func.count(models.EnrollmentApplication.id)).filter(
            models.EnrollmentApplication.status == models.EnrollmentStatus.ACTIVE,
            models.EnrollmentApplication.deleted_at.is_(None),
        )
        if kg_filter_ids:
            ch_q = ch_q.filter(models.EnrollmentApplication.kindergarten_id.in_(kg_filter_ids))
        children = ch_q.scalar() or 0

        # Attendance rate over the period, via the canonical definition (attended-among-
        # expected child-days / expected child-days). This used to be
        # `present_rows_in_window / active_children`, which divides a multi-day count by
        # a single-day headcount and so grew with the window — a month view could report
        # an "attendance" far above 100%. compute_attendance_components_bulk is a fixed
        # 3 queries regardless of kindergarten count.
        if kg_filter_ids:
            summary_kg_ids = list(kg_filter_ids)
        else:
            summary_kg_ids = [
                kid
                for (kid,) in db.query(models.Kindergarten.id).filter(
                    models.Kindergarten.status == models.KindergartenStatus.ACTIVE,
                    models.Kindergarten.deleted_at.is_(None),
                ).all()
            ]
        components = KPIService.compute_attendance_components_bulk(
            db, summary_kg_ids, start, end
        )
        att_num = sum(a for a, _ in components.values())
        att_den = sum(e for _, e in components.values())
        attendance = round(att_num / att_den * 100, 1) if att_den > 0 else 0.0

        # open alerts: pending enrollments + today's incidents
        pending_q = db.query(func.count(models.EnrollmentApplication.id)).filter(
            models.EnrollmentApplication.status == models.EnrollmentStatus.PENDING_REVIEW,
            models.EnrollmentApplication.deleted_at.is_(None),
        )
        incident_q = db.query(func.count(models.Incident.id)).filter(
            func.date(models.Incident.occurred_at) == today,
            models.Incident.deleted_at.is_(None),
        )
        if kg_filter_ids:
            pending_q = pending_q.filter(
                models.EnrollmentApplication.kindergarten_id.in_(kg_filter_ids)
            )
            incident_q = incident_q.filter(models.Incident.kindergarten_id.in_(kg_filter_ids))
        pending_enr = pending_q.scalar() or 0
        today_incidents = incident_q.scalar() or 0
        alerts = pending_enr + today_incidents

        # 7-day attendance trend, one canonical single-day rate per point (attended /
        # expected for that day). Each day is a 1-day window, so the same definition as
        # the headline number above — a point can only be 0/50/100 style values bounded
        # by that day's expected child-days, never the headcount-scaled figure.
        trend = []
        for i in range(6, -1, -1):
            d = today - timedelta(days=i)
            day_components = KPIService.compute_attendance_components_bulk(
                db, summary_kg_ids, d, d
            )
            day_num = sum(a for a, _ in day_components.values())
            day_den = sum(e for _, e in day_components.values())
            trend.append(round(day_num / day_den * 100, 1) if day_den > 0 else 0.0)

        return {
            "children": children,
            "attendance": attendance,
            "alerts": alerts,
            "chart": trend,
            "period": {"start": start.isoformat(), "end": end.isoformat()},
            "generated_at": datetime.now(_JORDAN_TZ).isoformat(),
        }
    except Exception as e:
        logger.error("Dashboard summary error: %s", str(e), exc_info=True)
        raise HTTPException(status_code=500, detail="Failed to fetch dashboard summary")


@router.get("/suggested-actions")
def get_suggested_actions(
    current_user: models.User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Returns live-computed action-card data for the dashboard (week-over-week attendance change, pending enrollments)."""
    scoped_kindergarten_id = _dashboard_kindergarten_scope(current_user)

    today = datetime.now(_JORDAN_TZ).date()
    week_start = today - timedelta(days=6)
    prev_week_end = today - timedelta(days=7)
    prev_week_start = today - timedelta(days=13)

    try:
        # Pending enrollment count
        pending_q = db.query(func.count(models.EnrollmentApplication.id)).filter(
            models.EnrollmentApplication.status == models.EnrollmentStatus.PENDING_REVIEW,
            models.EnrollmentApplication.deleted_at.is_(None),
        )
        if scoped_kindergarten_id:
            pending_q = pending_q.filter(
                models.EnrollmentApplication.kindergarten_id == scoped_kindergarten_id
            )
        pending_count: int = pending_q.scalar() or 0

        # Week-over-week attendance rate
        def _att_rate(start: date, end: date) -> Optional[float]:
            total_q = db.query(func.count(models.AttendanceLog.id)).filter(
                models.AttendanceLog.date >= start,
                models.AttendanceLog.date <= end,
            )
            if scoped_kindergarten_id:
                total_q = total_q.join(
                    models.Class, models.Class.id == models.AttendanceLog.class_id
                ).filter(models.Class.kindergarten_id == scoped_kindergarten_id)
            total = total_q.scalar() or 0
            if not total:
                return None
            present_q = db.query(func.count(models.AttendanceLog.id)).filter(
                models.AttendanceLog.date >= start,
                models.AttendanceLog.date <= end,
                models.AttendanceLog.status == models.AttendanceStatus.PRESENT,
            )
            if scoped_kindergarten_id:
                present_q = present_q.join(
                    models.Class, models.Class.id == models.AttendanceLog.class_id
                ).filter(models.Class.kindergarten_id == scoped_kindergarten_id)
            present = present_q.scalar() or 0
            return round(present / total * 100, 1)

        curr_rate = _att_rate(week_start, today)
        prev_rate = _att_rate(prev_week_start, prev_week_end)
        change: Optional[float] = (
            round(curr_rate - prev_rate, 1)
            if curr_rate is not None and prev_rate is not None
            else None
        )

        att_route = (
            f"/attendance/history?period=week&reason=attendance_decline&change={change}"
            if change is not None
            else "/attendance/history?period=week"
        )

        actions = [
            {
                "id": "pending_enrollments",
                "pending_count": pending_count,
            },
            {
                "id": "attendance_trend",
                "current_rate": curr_rate,
                "prev_rate": prev_rate,
                "change": change,
                "route": att_route,
            },
        ]

        logger.info(
            "suggested-actions: user_id=%s pending=%d curr_rate=%s change=%s",
            current_user.id, pending_count, curr_rate, change,
        )

        return {
            "success": True,
            "data": actions,
            "generated_at": datetime.now(_JORDAN_TZ).isoformat(),
        }
    except Exception as e:
        logger.error("Suggested actions error: %s", str(e), exc_info=True)
        raise HTTPException(status_code=500, detail="Failed to compute suggested actions")


@router.get("/widgets/available")
async def get_available_widgets(
    current_user: models.User = Depends(get_current_user),
):
    try:
        widgets = dashboard_customization.get_available_widgets(current_user.role.value.lower())
        return {"widgets": widgets}
    except (TypeError, ValueError) as e:
        logger.warning("Invalid role while fetching available dashboard widgets for user_id=%s: %s", current_user.id, str(e))
        raise HTTPException(status_code=500, detail="Failed to fetch available widgets")
