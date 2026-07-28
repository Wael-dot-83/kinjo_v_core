"""
Manager Analytics Endpoints
Provides manager-scoped operational analytics and predictive indicators.

These routes return plain dicts and declare no ``response_model``. Nine Pydantic
classes used to sit here describing the shapes — none was ever wired to a route
and none was referenced anywhere else, so they enforced nothing and drifted
freely from the dicts actually returned. They were removed rather than wired up,
because attaching an unverified model to a live route silently drops any field it
omits. Publishing real schemas is worthwhile, but each must be checked against
its endpoint's actual output first.
"""

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session
from sqlalchemy import func
from datetime import date, timedelta
from utils.time_utils import now_amman as _now, today_amman as _today

import models
from database import get_db
# Same guard as every other route in the module. These endpoints previously took
# Depends(get_current_user) and then called ManagerScope.validate_manager() by
# hand, which answers 400 for a manager with no kindergarten while /api/manager/*
# answers 403 for that identical account state — one module, two HTTP contracts.
# ManagerScope.validate_manager keeps its 400 (tests/test_manager_scope.py pins
# it); it is simply no longer used as a route guard.
#
# This also drops the last import of manager_scope.py, a shim whose only remaining
# job — a `validate_kindergarten_access` alias — has no callers anywhere. The shim
# survives solely because tests/test_manager_scope.py still asserts on it; retiring
# the two together is a follow-up, not a drive-by.
from dependencies import require_manager
from manager_analytics import ManagerAnalyticsService

router = APIRouter(tags=["manager_analytics"])


# =============================================================================
# CSV export safety (S1 — formula injection)
# =============================================================================

# Characters that make a spreadsheet treat a *text* cell as a formula when it
# appears first. Neutralized by prefixing a single quote (Excel/LibreOffice
# convention). csv.writer already handles RFC 4180 quoting/escaping.
_CSV_FORMULA_PREFIXES = ("=", "+", "-", "@", "\t", "\r")


def _csv_safe(value):
    """Neutralize CSV/formula injection for text cells.

    Only strings can be interpreted as formulas; numeric cells are returned
    unchanged so real numbers are not mangled into text.
    """
    if not isinstance(value, str):
        return "" if value is None else value
    if value and value[0] in _CSV_FORMULA_PREFIXES:
        return "'" + value
    return value


class _SafeCsvWriter:
    """csv.writer wrapper that runs every cell through _csv_safe, so no export
    field can be forgotten."""

    def __init__(self, writer):
        self._writer = writer

    def writerow(self, row):
        self._writer.writerow([_csv_safe(c) for c in row])


# =============================================================================
# Request/Response Models
# =============================================================================

# =============================================================================
# Manager Analytics Endpoints
# =============================================================================

@router.get("/manager/analytics/kpis")
def get_manager_kpis(
    period_days: int = Query(30, ge=1, le=365, description="Number of days to look back"),
    current_user: models.User = Depends(require_manager),
    db: Session = Depends(get_db)
):
    """
    Get manager operational KPIs for their kindergarten.
    
    Metrics included:
    - Enrollment rate
    - Attendance rate
    - Absenteeism rate
    - Incident rate (per 1,000 attended child-days)
    - Class capacity utilization
    - Supervisor workload
    """
    kg_id = current_user.kindergarten_id

    today = _today()
    start_date = today - timedelta(days=period_days)

    # Enrollment rate = active enrollments / total class capacity, as a percentage
    # (consistent with the sibling rate metrics below). Computed directly — the
    # previous code called compute_enrollment_trend() twice and then used a raw
    # count as the "rate" (A3). Division by zero is guarded.
    active_enrollments = db.query(
        func.count(models.EnrollmentApplication.id)
    ).filter(
        models.EnrollmentApplication.kindergarten_id == kg_id,
        models.EnrollmentApplication.status == models.EnrollmentStatus.ACTIVE,
    ).scalar() or 0
    total_capacity = db.query(
        func.sum(models.Class.capacity_total)
    ).filter(
        models.Class.kindergarten_id == kg_id,
        models.Class.is_active == True,
    ).scalar() or 0
    enrollment_rate = round(active_enrollments / total_capacity * 100, 2) if total_capacity else 0.0

    kpis = {
        "kindergarten_id": kg_id,
        "period": {
            "start_date": start_date.isoformat(),
            "end_date": today.isoformat(),
            "days": period_days
        },
        "metrics": {
            "enrollment_rate": enrollment_rate,
            "active_enrollments": active_enrollments,
            "capacity": int(total_capacity),
            "attendance_rate": ManagerAnalyticsService.compute_attendance_rate(
                db, kg_id, start_date, today
            ),
            "absenteeism_rate": ManagerAnalyticsService.compute_absenteeism_rate(
                db, kg_id, start_date, today
            ),
            "incident_rate": ManagerAnalyticsService.compute_incident_rate(
                db, kg_id, start_date, today
            ),
            "capacity_utilization": ManagerAnalyticsService.compute_class_capacity_utilization(
                db, kg_id
            ),
            "supervisor_workload": ManagerAnalyticsService.compute_supervisor_workload(
                db, kg_id
            )
        },
        # A timestamp, not a date. This returned _today().isoformat(), so every
        # call within the same Jordan day reported an identical "generated_at"
        # and a client could not tell a fresh response from a stale one.
        "generated_at": _now().isoformat()
    }

    return kpis


@router.get("/manager/analytics/enrollment-trend")
def get_enrollment_trend(
    period_days: int = Query(30, ge=1, le=365),
    grouping: str = Query("daily", pattern="^(daily|weekly|monthly)$"),
    current_user: models.User = Depends(require_manager),
    db: Session = Depends(get_db)
):
    """
    Get enrollment trend over time.
    Shows new enrollments and cumulative active enrollments per day/week/month.
    """
    kg_id = current_user.kindergarten_id

    today = _today()
    start_date = today - timedelta(days=period_days)

    trend = ManagerAnalyticsService.compute_enrollment_trend(
        db, kg_id, start_date, today, grouping
    )

    return {
        "kindergarten_id": kg_id,
        "period": {
            "start_date": start_date.isoformat(),
            "end_date": today.isoformat(),
            "grouping": grouping
        },
        "trend": trend,
        "generated_at": _now().isoformat()
    }


@router.get("/manager/analytics/attendance-forecast")
def get_attendance_forecast(
    lookback_days: int = Query(30, ge=7, le=90),
    forecast_days: int = Query(7, ge=1, le=30),
    current_user: models.User = Depends(require_manager),
    db: Session = Depends(get_db)
):
    """
    Get attendance forecast using linear regression.
    
    Returns:
    - Historical attendance rates
    - Forecast for next N days
    - Trend direction (increasing/decreasing/stable)
    - Confidence intervals for forecasted values
    """
    kg_id = current_user.kindergarten_id

    today = _today()
    start_date = today - timedelta(days=lookback_days)
    forecast_end = today + timedelta(days=forecast_days)

    result = ManagerAnalyticsService.compute_attendance_forecast(
        db, kg_id, lookback_days, forecast_days
    )

    return {
        "kindergarten_id": kg_id,
        "period": {
            "historical_start": start_date.isoformat(),
            "historical_end": today.isoformat(),
            "forecast_start": (today + timedelta(days=1)).isoformat(),
            "forecast_end": forecast_end.isoformat()
        },
        **result,
        "generated_at": _now().isoformat()
    }


@router.get("/manager/analytics/anomalies")
def detect_attendance_anomalies(
    lookback_days: int = Query(30, ge=7, le=90),
    std_threshold: float = Query(2.0, ge=1.0, le=5.0),
    current_user: models.User = Depends(require_manager),
    db: Session = Depends(get_db)
):
    """
    Detect anomalies in attendance using z-score method.
    
    Days with attendance significantly different from baseline (mean ± std*threshold)
    are flagged as anomalies.
    
    Severity levels:
    - warning: z-score between 2.0 and 3.0 (relative to threshold)
    - critical: z-score > 3.0
    """
    kg_id = current_user.kindergarten_id

    today = _today()
    start_date = today - timedelta(days=lookback_days)

    result = ManagerAnalyticsService.detect_anomalies(
        db, kg_id, lookback_days, std_threshold
    )

    return {
        "kindergarten_id": kg_id,
        "period": {
            "start_date": start_date.isoformat(),
            "end_date": today.isoformat(),
            "lookback_days": lookback_days
        },
        **result,
        "generated_at": _now().isoformat()
    }


@router.get("/manager/analytics/drilldown/by-class")
def drilldown_by_class(
    period_days: int = Query(30, ge=1, le=365),
    current_user: models.User = Depends(require_manager),
    db: Session = Depends(get_db)
):
    """
    Drill-down view: Kindergarten -> Classes -> Statistics
    
    Shows each class with:
    - Supervisor assignment
    - Enrollment count and capacity utilization
    - Class-specific attendance rate
    - Incident count for the period
    """
    kg_id = current_user.kindergarten_id

    today = _today()
    start_date = today - timedelta(days=period_days)

    classes = ManagerAnalyticsService.get_drilldown_by_class(
        db, kg_id, start_date, today
    )

    return {
        "kindergarten_id": kg_id,
        "period": {
            "start_date": start_date.isoformat(),
            "end_date": today.isoformat(),
            "days": period_days
        },
        "classes": classes,
        "total_classes": len(classes),
        "generated_at": _now().isoformat()
    }


@router.get("/manager/analytics/drilldown/by-supervisor")
def drilldown_by_supervisor(
    period_days: int = Query(30, ge=1, le=365),
    current_user: models.User = Depends(require_manager),
    db: Session = Depends(get_db)
):
    """
    Drill-down view: Kindergarten -> Supervisors -> Statistics
    
    Shows each supervisor with:
    - Classes managed
    - Total children supervised
    - Daily reports submitted in period
    - Incidents reported in period
    """
    kg_id = current_user.kindergarten_id

    today = _today()
    start_date = today - timedelta(days=period_days)

    supervisors = ManagerAnalyticsService.get_drilldown_by_supervisor(
        db, kg_id, start_date, today
    )

    return {
        "kindergarten_id": kg_id,
        "period": {
            "start_date": start_date.isoformat(),
            "end_date": today.isoformat(),
            "days": period_days
        },
        "supervisors": supervisors,
        "total_supervisors": len(supervisors),
        "generated_at": _now().isoformat()
    }


@router.get("/manager/analytics/export/csv")
def export_analytics_csv(
    report_type: str = Query("kpis", pattern="^(kpis|trends|drilldown)$"),
    period_days: int = Query(30, ge=1, le=365),
    current_user: models.User = Depends(require_manager),
    db: Session = Depends(get_db)
):
    """
    Export manager analytics as CSV.
    
    Scoped to manager's kindergarten only.
    Supports: KPIs, trends, drilldown reports.
    """
    kg_id = current_user.kindergarten_id

    # Get kindergarten name for filename
    kg = db.query(models.Kindergarten).filter(
        models.Kindergarten.id == kg_id
    ).first()

    if not kg:
        raise HTTPException(status_code=404, detail="Kindergarten not found")

    from fastapi.responses import StreamingResponse
    import io
    import csv

    today = _today()
    start_date = today - timedelta(days=period_days)

    # Create CSV content based on report type. Wrap the writer so every cell is
    # neutralized against formula injection (S1).
    output = io.StringIO()
    writer = _SafeCsvWriter(csv.writer(output))

    if report_type == "kpis":
        writer.writerow(["Manager Analytics - KPI Report"])
        writer.writerow(["Kindergarten:", kg.name_ar])
        writer.writerow(["Period:", f"{start_date} to {today}"])
        writer.writerow([])
        writer.writerow(["Metric", "Value"])

        attendance_rate = ManagerAnalyticsService.compute_attendance_rate(
            db, kg_id, start_date, today
        )
        writer.writerow(["Attendance Rate (%)", attendance_rate])

        absenteeism_rate = ManagerAnalyticsService.compute_absenteeism_rate(
            db, kg_id, start_date, today
        )
        writer.writerow(["Absenteeism Rate (%)", absenteeism_rate])

        incident_rate = ManagerAnalyticsService.compute_incident_rate(
            db, kg_id, start_date, today
        )
        writer.writerow(["Incident Rate (per 1,000 attended child-days)", incident_rate])

        capacity = ManagerAnalyticsService.compute_class_capacity_utilization(
            db, kg_id
        )
        writer.writerow(["Capacity Utilization (%)", capacity])

    elif report_type == "trends":
        writer.writerow(["Manager Analytics - Enrollment Trend Report"])
        writer.writerow(["Kindergarten:", kg.name_ar])
        writer.writerow(["Period:", f"{start_date} to {today}"])
        writer.writerow([])
        writer.writerow(["Date", "New Enrollments", "Active Enrollments", "Cumulative"])

        trend = ManagerAnalyticsService.compute_enrollment_trend(
            db, kg_id, start_date, today
        )
        for point in trend:
            writer.writerow([
                point["date"],
                point["new_enrollments"],
                point["active_enrollments"],
                point["cumulative_active"]
            ])

    elif report_type == "drilldown":
        writer.writerow(["Manager Analytics - Class Drill-down Report"])
        writer.writerow(["Kindergarten:", kg.name_ar])
        writer.writerow(["Period:", f"{start_date} to {today}"])
        writer.writerow([])
        writer.writerow([
            "Class Name", "Supervisor", "Age Range",
            "Capacity", "Enrolled", "Utilization %",
            "Attendance Rate %", "Incidents"
        ])

        classes = ManagerAnalyticsService.get_drilldown_by_class(
            db, kg_id, start_date, today
        )
        for cls in classes:
            writer.writerow([
                cls["class_name"],
                cls["supervisor_name"],
                cls["age_range"],
                cls["capacity"],
                cls["enrolled"],
                cls["utilization_percent"],
                cls["attendance_rate"],
                cls["incidents"]
            ])

    output.seek(0)
    filename = f"kindergarten_{kg_id}_{report_type}_{today}.csv"

    return StreamingResponse(
        iter([output.getvalue()]),
        media_type="text/csv",
        headers={"Content-Disposition": f"attachment; filename={filename}"}
    )


# Export router
__all__ = ["router"]
