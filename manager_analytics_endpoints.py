"""
Manager Analytics Endpoints
Provides manager-scoped operational analytics and predictive indicators
"""

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.orm import Session
from datetime import date, timedelta
from utils.time_utils import today_amman as _today
from typing import Optional, List, Dict
from pydantic import BaseModel, ConfigDict

import models
from dependencies import get_current_user
from database import get_db
from manager_scope import ManagerScope
from manager_analytics import ManagerAnalyticsService

router = APIRouter(tags=["manager_analytics"])


# =============================================================================
# Request/Response Models
# =============================================================================

class KPIMetrics(BaseModel):
    """Manager operational KPI metrics"""
    enrollment_rate: float
    attendance_rate: float
    absenteeism_rate: float
    incident_rate: float  # Per 100 children
    capacity_utilization: float
    supervisor_workload_avg: float  # Children per supervisor

    model_config = ConfigDict(from_attributes=True)


class TrendPoint(BaseModel):
    """Single point in a trend chart"""
    date: str
    value: float
    cumulative: Optional[float] = None


class ForecastPoint(BaseModel):
    """Single point in a forecast"""
    date: str
    predicted_value: float
    lower_bound: float
    upper_bound: float


class AnomalyPoint(BaseModel):
    """Anomaly detection result"""
    date: str
    metric: str
    value: float
    z_score: float
    severity: str  # "critical" or "warning"


class AttendanceForecastResponse(BaseModel):
    """Attendance forecast with historical data and trend"""
    historical: List[Dict]
    forecast: List[Dict]
    trend: str  # "increasing", "decreasing", "stable"
    slope: float
    period_start: str
    period_end: str
    forecast_start: str
    forecast_days: int


class AnomalyDetectionResponse(BaseModel):
    """Anomaly detection results"""
    anomalies: List[Dict]
    baseline_mean: float
    baseline_std: float
    threshold: float
    status: str
    period_start: str
    period_end: str


class ClassDrilldown(BaseModel):
    """Class-level statistics for drill-down"""
    class_id: int
    class_name: str
    supervisor_name: str
    age_range: str
    capacity: int
    enrolled: int
    utilization_percent: float
    attendance_rate: float
    incidents: int
    period_start: str
    period_end: str


class SupervisorDrilldown(BaseModel):
    """Supervisor-level statistics for drill-down"""
    supervisor_id: int
    supervisor_name: str
    classes_managed: int
    children_supervised: int
    reports_submitted: int
    incidents_reported: int
    period_start: str
    period_end: str


class EnrollmentTrendResponse(BaseModel):
    """Enrollment trend over time"""
    trend: List[Dict]
    total_active: int
    new_this_period: int
    period_start: str
    period_end: str


# =============================================================================
# Manager Analytics Endpoints
# =============================================================================

@router.get("/manager/analytics/kpis")
def get_manager_kpis(
    period_days: int = Query(30, ge=1, le=365, description="Number of days to look back"),
    current_user: models.User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """
    Get manager operational KPIs for their kindergarten.
    
    Metrics included:
    - Enrollment rate
    - Attendance rate
    - Absenteeism rate
    - Incident rate (per 100 children)
    - Class capacity utilization
    - Supervisor workload
    """
    ManagerScope.validate_manager(current_user)
    kg_id = ManagerScope.get_manager_kindergarten_id(current_user)

    today = _today()
    start_date = today - timedelta(days=period_days)

    kpis = {
        "kindergarten_id": kg_id,
        "period": {
            "start_date": start_date.isoformat(),
            "end_date": today.isoformat(),
            "days": period_days
        },
        "metrics": {
            "enrollment_rate": ManagerAnalyticsService.compute_enrollment_trend(
                db, kg_id, start_date, today
            )[-1]["cumulative_active"] if ManagerAnalyticsService.compute_enrollment_trend(
                db, kg_id, start_date, today
            ) else 0,
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
        "generated_at": _today().isoformat()
    }

    return kpis


@router.get("/manager/analytics/enrollment-trend")
def get_enrollment_trend(
    period_days: int = Query(30, ge=1, le=365),
    grouping: str = Query("daily", pattern="^(daily|weekly|monthly)$"),
    current_user: models.User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """
    Get enrollment trend over time.
    Shows new enrollments and cumulative active enrollments per day/week/month.
    """
    ManagerScope.validate_manager(current_user)
    kg_id = ManagerScope.get_manager_kindergarten_id(current_user)

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
        "generated_at": _today().isoformat()
    }


@router.get("/manager/analytics/attendance-forecast")
def get_attendance_forecast(
    lookback_days: int = Query(30, ge=7, le=90),
    forecast_days: int = Query(7, ge=1, le=30),
    current_user: models.User = Depends(get_current_user),
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
    ManagerScope.validate_manager(current_user)
    kg_id = ManagerScope.get_manager_kindergarten_id(current_user)

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
        "generated_at": _today().isoformat()
    }


@router.get("/manager/analytics/anomalies")
def detect_attendance_anomalies(
    lookback_days: int = Query(30, ge=7, le=90),
    std_threshold: float = Query(2.0, ge=1.0, le=5.0),
    current_user: models.User = Depends(get_current_user),
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
    ManagerScope.validate_manager(current_user)
    kg_id = ManagerScope.get_manager_kindergarten_id(current_user)

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
        "generated_at": _today().isoformat()
    }


@router.get("/manager/analytics/drilldown/by-class")
def drilldown_by_class(
    period_days: int = Query(30, ge=1, le=365),
    current_user: models.User = Depends(get_current_user),
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
    ManagerScope.validate_manager(current_user)
    kg_id = ManagerScope.get_manager_kindergarten_id(current_user)

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
        "generated_at": _today().isoformat()
    }


@router.get("/manager/analytics/drilldown/by-supervisor")
def drilldown_by_supervisor(
    period_days: int = Query(30, ge=1, le=365),
    current_user: models.User = Depends(get_current_user),
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
    ManagerScope.validate_manager(current_user)
    kg_id = ManagerScope.get_manager_kindergarten_id(current_user)

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
        "generated_at": _today().isoformat()
    }


@router.get("/manager/analytics/export/csv")
def export_analytics_csv(
    report_type: str = Query("kpis", pattern="^(kpis|trends|drilldown)$"),
    period_days: int = Query(30, ge=1, le=365),
    current_user: models.User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """
    Export manager analytics as CSV.
    
    Scoped to manager's kindergarten only.
    Supports: KPIs, trends, drilldown reports.
    """
    ManagerScope.validate_manager(current_user)
    kg_id = ManagerScope.get_manager_kindergarten_id(current_user)

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

    # Create CSV content based on report type
    output = io.StringIO()
    writer = csv.writer(output)

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
        writer.writerow(["Incident Rate (per 100 children)", incident_rate])

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
