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
from database import get_db
from dashboard_customization import dashboard_customization
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
):
    try:
        success = dashboard_customization.update_user_widgets(current_user.id, widgets)
        if not success:
            raise HTTPException(status_code=400, detail="Invalid widget configuration")

        return {"message": "Dashboard widget configuration updated"}
    except HTTPException:
        raise
    except (TypeError, ValueError) as e:
        logger.warning("Invalid dashboard widget update request for user_id=%s: %s", current_user.id, str(e))
        raise HTTPException(status_code=500, detail="Failed to update dashboard widget configuration")


@router.post("/widgets/reset")
async def reset_user_widgets(
    current_user: models.User = Depends(get_current_user),
):
    try:
        success = dashboard_customization.reset_user_widgets(current_user.id, current_user.role.value.lower())
        if not success:
            raise HTTPException(status_code=500, detail="Failed to reset dashboard widget configuration")

        return {"message": "Dashboard widgets reset to role defaults"}
    except (TypeError, ValueError) as e:
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

    # kindergarten filter (ADMIN/MANAGER can filter; others see their own scope)
    kg_filter_ids: Optional[list] = None
    if body.kindergarten_id:
        kg_filter_ids = [body.kindergarten_id]
    elif current_user.role == models.UserRole.MANAGER and current_user.kindergarten_id:
        kg_filter_ids = [current_user.kindergarten_id]

    try:
        # active enrolled children
        ch_q = db.query(func.count(models.EnrollmentApplication.id)).filter(
            models.EnrollmentApplication.status == models.EnrollmentStatus.ACTIVE
        )
        if kg_filter_ids:
            ch_q = ch_q.filter(models.EnrollmentApplication.kindergarten_id.in_(kg_filter_ids))
        children = ch_q.scalar() or 0

        # attendance rate over period
        att_q = db.query(func.count(models.AttendanceLog.id)).filter(
            models.AttendanceLog.date >= start,
            models.AttendanceLog.date <= end,
            models.AttendanceLog.status == models.AttendanceStatus.PRESENT,
        )
        if kg_filter_ids:
            att_q = att_q.join(
                models.EnrollmentApplication,
                models.EnrollmentApplication.child_id == models.AttendanceLog.child_id,
            ).filter(models.EnrollmentApplication.kindergarten_id.in_(kg_filter_ids))
        present = att_q.scalar() or 0
        attendance = round(present / children * 100, 1) if children > 0 else 0.0

        # open alerts: pending enrollments + today's incidents
        pending_enr = db.query(func.count(models.EnrollmentApplication.id)).filter(
            models.EnrollmentApplication.status == models.EnrollmentStatus.PENDING_REVIEW
        ).scalar() or 0
        today_incidents = db.query(func.count(models.Incident.id)).filter(
            func.date(models.Incident.occurred_at) == today,
            models.Incident.deleted_at.is_(None),
        ).scalar() or 0
        alerts = pending_enr + today_incidents

        # 7-day attendance trend (percent each day)
        trend = []
        for i in range(6, -1, -1):
            d = today - timedelta(days=i)
            day_present = db.query(func.count(models.AttendanceLog.id)).filter(
                models.AttendanceLog.date == d,
                models.AttendanceLog.status == models.AttendanceStatus.PRESENT,
            ).scalar() or 0
            trend.append(round(day_present / children * 100, 1) if children > 0 else 0.0)

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
    if current_user.role == models.UserRole.PARENT:
        raise HTTPException(status_code=403, detail="Not authorized")

    today = datetime.now(_JORDAN_TZ).date()
    week_start = today - timedelta(days=6)
    prev_week_end = today - timedelta(days=7)
    prev_week_start = today - timedelta(days=13)

    try:
        # Pending enrollment count
        pending_count: int = db.query(func.count(models.EnrollmentApplication.id)).filter(
            models.EnrollmentApplication.status == models.EnrollmentStatus.PENDING_REVIEW,
        ).scalar() or 0

        # Week-over-week attendance rate
        def _att_rate(start: date, end: date) -> Optional[float]:
            total = db.query(func.count(models.AttendanceLog.id)).filter(
                models.AttendanceLog.date >= start,
                models.AttendanceLog.date <= end,
            ).scalar() or 0
            if not total:
                return None
            present = db.query(func.count(models.AttendanceLog.id)).filter(
                models.AttendanceLog.date >= start,
                models.AttendanceLog.date <= end,
                models.AttendanceLog.status == models.AttendanceStatus.PRESENT,
            ).scalar() or 0
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
