from fastapi import APIRouter, Depends, Query, HTTPException, status, BackgroundTasks
from pydantic import BaseModel, Field
from typing import List, Optional, Dict, Any
from datetime import date
import models
from database import get_db
from sqlalchemy.orm import Session
from dependencies import get_current_user

# ...existing code...

# =============================================================================
# Pydantic Schemas for API
# =============================================================================

class AdvancedAnalyticsCacheResponse(BaseModel):
    dimension_type: str
    dimension_id: str
    period_type: str
    period_start: date
    period_end: date
    attendance_rate: Optional[float] = None
    chronic_absence_rate: Optional[float] = None
    incident_rate_per_100: Optional[float] = None
    serious_incident_rate: Optional[float] = None
    ratio_compliance_rate: Optional[float] = None
    report_completion_rate: Optional[float] = None
    parent_satisfaction_nps: Optional[float] = None
    child_development_index: Optional[float] = None
    staff_turnover_rate: Optional[float] = None
    regulatory_compliance_score: Optional[float] = None
    attendance_trend_slope: Optional[float] = None
    risk_score: Optional[float] = None
    improvement_velocity: Optional[float] = None
    attendance_incident_correlation: Optional[float] = None
    staffing_quality_correlation: Optional[float] = None
    health_alerts_count: Optional[int] = None
    curriculum_progress: Optional[float] = None
    class Config:
        orm_mode = True

class InvalidateCacheRequest(BaseModel):
    dimension_type: Optional[str] = None
    dimension_id: Optional[str] = None
    period_type: Optional[str] = None
    period_start: Optional[date] = None
    period_end: Optional[date] = None

class WarmCacheRequest(BaseModel):
    dimension_type: str
    dimension_ids: List[str]
    period_type: str
    period_start: date
    period_end: date

# =============================================================================
# API Endpoints for Advanced Analytics Cache
# =============================================================================

router = APIRouter(tags=["Analytics"])

@router.get("/advanced-cache", response_model=AdvancedAnalyticsCacheResponse)
def get_advanced_analytics_cache(
    dimension_type: str = Query(...),
    dimension_id: str = Query(...),
    period_type: str = Query(...),
    period_start: date = Query(...),
    period_end: date = Query(...),
    current_user: models.User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    # Enforce authentication (current_user will raise 401 if not authenticated)
    # RBAC: Only admin/supervisor/manager can access
    if current_user.role not in {models.UserRole.ADMIN, models.UserRole.SUPERVISOR, models.UserRole.MANAGER}:
        raise HTTPException(status_code=403, detail="Insufficient permissions")
    cache = AnalyticsService.get_advanced_analytics_cache(
        db,
        models.AnalyticsDimensionType(dimension_type),
        dimension_id,
        models.AnalyticsPeriodType(period_type),
        period_start,
        period_end
    )
    if not cache:
        raise HTTPException(status_code=404, detail="No cache found")
    return cache

@router.post("/advanced-cache/invalidate")
def invalidate_advanced_analytics_cache(
    req: InvalidateCacheRequest,
    current_user: models.User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    if current_user.role != models.UserRole.ADMIN:
        raise HTTPException(status_code=403, detail="Admin only")
    count = AnalyticsService.invalidate_advanced_analytics_cache(
        db,
        models.AnalyticsDimensionType(req.dimension_type) if req.dimension_type else None,
        req.dimension_id,
        models.AnalyticsPeriodType(req.period_type) if req.period_type else None,
        req.period_start,
        req.period_end
    )
    return {"deleted": count}

@router.post("/advanced-cache/warm")
def warm_advanced_analytics_cache(
    req: WarmCacheRequest,
    current_user: models.User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    if current_user.role != models.UserRole.ADMIN:
        raise HTTPException(status_code=403, detail="Admin only")
    count = AnalyticsService.warm_advanced_analytics_cache(
        db,
        models.AnalyticsDimensionType(req.dimension_type),
        req.dimension_ids,
        models.AnalyticsPeriodType(req.period_type),
        req.period_start,
        req.period_end
    )
    return {"created": count}
"""
Analytics and Reporting Services for Admin Dashboard
Implements drill-down analytics from Network → Governorate → Kindergarten → Class → Child
"""
from fastapi import APIRouter, Depends, Query, HTTPException, status, BackgroundTasks
from datetime import date, datetime, timedelta
from typing import List, Dict, Optional, Any
from sqlalchemy.orm import Session
from sqlalchemy import func, and_, or_, case, desc, asc
from pydantic import BaseModel, Field
from enum import Enum

import models
from database import get_db
from dependencies import get_current_user
from kpi_service import KPIService
import validators

router = APIRouter(prefix="/analytics", tags=["Analytics"])


# =============================================================================
# Response Models
# =============================================================================

class MetricValue(BaseModel):
    value: float
    change: Optional[float] = None  # Percentage change from previous period
    trend: Optional[str] = None  # "up", "down", "stable"


class NetworkSummary(BaseModel):
    total_kindergartens: int
    total_children: int
    total_staff: int
    total_capacity: int
    enrollment_rate: float
    attendance_rate: float
    incident_rate: float
    report_submission_rate: float
    report_approval_rate: float
    report_completion_rate: float = Field(alias="report_approval_rate")  # Backward compatibility
    governance_avg_score: float


class GovernorateMetrics(BaseModel):
    governorate: str
    kindergarten_count: int
    children_count: int
    capacity: int
    enrollment_rate: float
    attendance_rate: float
    incident_rate: float
    governance_score: float


class KindergartenMetrics(BaseModel):
    id: int
    name: str
    governorate: str
    children_count: int
    capacity: int
    enrollment_rate: float
    attendance_rate: float
    incident_rate: float
    report_submission_rate: float
    report_approval_rate: float
    report_completion_rate: float = Field(alias="report_approval_rate")  # Backward compatibility
    ratio_compliance: float
    governance_score: float
    governance_band: str


class ClassMetrics(BaseModel):
    id: int
    name: str
    children_count: int
    capacity: int
    age_group: str
    attendance_rate: float
    assigned_teachers: int


class TimeSeriesPoint(BaseModel):
    date: str
    value: float
    label: Optional[str] = None


class RankingEntry(BaseModel):
    rank: int
    kindergarten_id: int
    kindergarten_name: str
    governorate: str
    value: float
    band: Optional[str] = None


class DrilldownResponse(BaseModel):
    dimension_type: str
    dimension_id: str
    dimension_name: str
    period_start: date
    period_end: date
    metrics: Dict[str, Any]
    children: Optional[List[Any]] = None


class ExportJobResponse(BaseModel):
    job_id: int
    status: str
    report_type: str
    created_at: datetime
    file_path: Optional[str] = None


class ExportRequest(BaseModel):
    """Request body for export endpoint"""
    report_type: str = Field(..., description="Report type: overview, attendance, incidents, etc.")
    export_format: str = Field("CSV", description="CSV, PDF, EXCEL")
    filters: Optional[Dict[str, Any]] = None


# =============================================================================
# Analytics Service Class
# =============================================================================

class AnalyticsService:
    @staticmethod
    def invalidate_advanced_analytics_cache(
        db: Session,
        dimension_type: models.AnalyticsDimensionType = None,
        dimension_id: str = None,
        period_type: models.AnalyticsPeriodType = None,
        period_start: date = None,
        period_end: date = None
    ) -> int:
        """
        Invalidate (delete) advanced analytics cache entries matching the given filters.
        Returns number of rows deleted.
        """
        query = db.query(models.AdvancedAnalyticsCache)
        if dimension_type:
            query = query.filter(models.AdvancedAnalyticsCache.dimension_type == dimension_type)
        if dimension_id:
            query = query.filter(models.AdvancedAnalyticsCache.dimension_id == str(dimension_id))
        if period_type:
            query = query.filter(models.AdvancedAnalyticsCache.period_type == period_type)
        if period_start:
            query = query.filter(models.AdvancedAnalyticsCache.period_start == period_start)
        if period_end:
            query = query.filter(models.AdvancedAnalyticsCache.period_end == period_end)
        count = query.delete(synchronize_session=False)
        db.commit()
        return count

    @staticmethod
    def warm_advanced_analytics_cache(
        db: Session,
        dimension_type: models.AnalyticsDimensionType,
        dimension_ids: list,
        period_type: models.AnalyticsPeriodType,
        period_start: date,
        period_end: date
    ) -> int:
        """
        Precompute and store advanced analytics cache for a list of dimension_ids.
        Returns number of cache entries created.
        """
        created = 0
        for dim_id in dimension_ids:
            AnalyticsService.compute_advanced_analytics(
                db, dimension_type, dim_id, period_type, period_start, period_end
            )
            created += 1
        return created

    @staticmethod
    def compute_advanced_analytics(
        db: Session,
        dimension_type: models.AnalyticsDimensionType,
        dimension_id: str,
        period_type: models.AnalyticsPeriodType,
        period_start: date,
        period_end: date
    ) -> models.AdvancedAnalyticsCache:
        """
        Compute and store advanced analytics metrics for a given dimension and period.
        Overwrites existing cache entry for the same dimension/period.
        """
        # Remove any existing cache for this dimension/period
        existing = db.query(models.AdvancedAnalyticsCache).filter(
            models.AdvancedAnalyticsCache.dimension_type == dimension_type,
            models.AdvancedAnalyticsCache.dimension_id == str(dimension_id),
            models.AdvancedAnalyticsCache.period_type == period_type,
            models.AdvancedAnalyticsCache.period_start == period_start,
            models.AdvancedAnalyticsCache.period_end == period_end
        ).first()
        if existing:
            db.delete(existing)
            db.commit()

        # Compute core KPIs (example for KINDERGARTEN, extend for others as needed)
        attendance_rate = None
        chronic_absence_rate = None
        incident_rate_per_100 = None
        serious_incident_rate = None
        ratio_compliance_rate = None
        report_completion_rate = None

        parent_satisfaction_nps = None
        child_development_index = None
        staff_turnover_rate = None
        regulatory_compliance_score = None

        attendance_trend_slope = None
        risk_score = None
        improvement_velocity = None

        attendance_incident_correlation = None
        staffing_quality_correlation = None

        health_alerts_count = None
        curriculum_progress = None

        # Example: KINDERGARTEN-level metrics
        if dimension_type == models.AnalyticsDimensionType.KINDERGARTEN:
            kg_id = int(dimension_id)
            attendance_rate = KPIService.compute_attendance_rate(db, kg_id, period_start, period_end)
            chronic_absence_rate = KPIService.compute_chronic_absence_rate(db, kg_id, period_start, period_end)
            incident_rate_per_100 = KPIService.compute_incident_rate(db, kg_id, period_start, period_end)
            serious_incident_rate = KPIService.compute_serious_incident_rate(db, kg_id, period_start, period_end)
            ratio_compliance_rate = KPIService.compute_ratio_compliance(db, kg_id, period_start, period_end)
            # Report completion rate: use daily reports
            total_reports = db.query(models.DailyReport).join(models.Child).join(models.EnrollmentApplication, models.EnrollmentApplication.child_id == models.Child.id).filter(
                models.EnrollmentApplication.kindergarten_id == kg_id,
                models.DailyReport.date >= period_start,
                models.DailyReport.date <= period_end
            ).count()
            sent_reports = db.query(models.DailyReport).join(models.Child).join(models.EnrollmentApplication, models.EnrollmentApplication.child_id == models.Child.id).filter(
                models.EnrollmentApplication.kindergarten_id == kg_id,
                models.DailyReport.date >= period_start,
                models.DailyReport.date <= period_end,
                models.DailyReport.status == models.DailyReportStatus.SUBMITTED
            ).count()
            report_completion_rate = (sent_reports / total_reports * 100) if total_reports > 0 else 0

            # Health alerts
            health_alerts_count = db.query(models.HealthAlert).join(models.Child).join(models.EnrollmentApplication, models.EnrollmentApplication.child_id == models.Child.id).filter(
                models.EnrollmentApplication.kindergarten_id == kg_id,
                models.HealthAlert.created_at >= period_start,
                models.HealthAlert.created_at <= period_end
            ).count()

            # Curriculum progress (placeholder: set to None or compute if available)
            curriculum_progress = None

            # Advanced, predictive, and correlation metrics (placeholders)
            # TODO: Implement real calculations for these metrics
            parent_satisfaction_nps = None
            child_development_index = None
            staff_turnover_rate = None
            regulatory_compliance_score = None
            attendance_trend_slope = None
            risk_score = None
            improvement_velocity = None
            attendance_incident_correlation = None
            staffing_quality_correlation = None

        # TODO: Add logic for other dimension types (NETWORK, GOVERNORATE, etc.)

        cache = models.AdvancedAnalyticsCache(
            dimension_type=dimension_type,
            dimension_id=str(dimension_id),
            period_type=period_type,
            period_start=period_start,
            period_end=period_end,
            attendance_rate=attendance_rate,
            chronic_absence_rate=chronic_absence_rate,
            incident_rate_per_100=incident_rate_per_100,
            serious_incident_rate=serious_incident_rate,
            ratio_compliance_rate=ratio_compliance_rate,
            report_completion_rate=report_completion_rate,
            parent_satisfaction_nps=parent_satisfaction_nps,
            child_development_index=child_development_index,
            staff_turnover_rate=staff_turnover_rate,
            regulatory_compliance_score=regulatory_compliance_score,
            attendance_trend_slope=attendance_trend_slope,
            risk_score=risk_score,
            improvement_velocity=improvement_velocity,
            attendance_incident_correlation=attendance_incident_correlation,
            staffing_quality_correlation=staffing_quality_correlation,
            health_alerts_count=health_alerts_count,
            curriculum_progress=curriculum_progress
        )
        db.add(cache)
        db.commit()
        db.refresh(cache)
        return cache

    @staticmethod
    def get_advanced_analytics_cache(
        db: Session,
        dimension_type: models.AnalyticsDimensionType,
        dimension_id: str,
        period_type: models.AnalyticsPeriodType,
        period_start: date,
        period_end: date
    ) -> models.AdvancedAnalyticsCache:
        """
        Retrieve advanced analytics cache for a given dimension and period.
        """
        return db.query(models.AdvancedAnalyticsCache).filter(
            models.AdvancedAnalyticsCache.dimension_type == dimension_type,
            models.AdvancedAnalyticsCache.dimension_id == str(dimension_id),
            models.AdvancedAnalyticsCache.period_type == period_type,
            models.AdvancedAnalyticsCache.period_start == period_start,
            models.AdvancedAnalyticsCache.period_end == period_end
        ).first()

    @staticmethod
    def get_network_summary(
        db: Session,
        period_start: date,
        period_end: date
    ) -> NetworkSummary:
        """Get network-wide summary metrics"""
        # Total kindergartens (active only)
        total_kg = db.query(func.count(models.Kindergarten.id)).filter(
            models.Kindergarten.status == models.KindergartenStatus.ACTIVE
        ).scalar() or 0

        # Total capacity (from active classes in active kindergartens)
        total_capacity = db.query(func.sum(models.Class.capacity_total)).join(
            models.Kindergarten
        ).filter(
            models.Kindergarten.status == models.KindergartenStatus.ACTIVE,
            models.Class.is_active == True
        ).scalar() or 0

        # Total enrolled children
        total_children = db.query(func.count(models.EnrollmentApplication.id)).filter(
            models.EnrollmentApplication.status == models.EnrollmentStatus.ACTIVE
        ).scalar() or 0

        # Total staff
        total_staff = db.query(func.count(models.User.id)).filter(
            models.User.role.in_([
                models.UserRole.MANAGER,
                models.UserRole.SUPERVISOR
            ]),
            models.User.status == models.UserStatus.ACTIVE
        ).scalar() or 0

        # Enrollment rate
        enrollment_rate = (total_children / total_capacity * 100) if total_capacity > 0 else 0

        # Network-wide attendance rate
        days_in_period = (period_end - period_start).days + 1
        expected_attendance = total_children * days_in_period
        actual_attendance = db.query(func.count(models.AttendanceLog.id)).filter(
            models.AttendanceLog.date >= period_start,
            models.AttendanceLog.date <= period_end
        ).scalar() or 0
        attendance_rate = (actual_attendance / expected_attendance * 100) if expected_attendance > 0 else 0

        # Network-wide incident rate
        total_incidents = db.query(func.count(models.Incident.id)).filter(
            func.date(models.Incident.occurred_at) >= period_start,
            func.date(models.Incident.occurred_at) <= period_end
        ).scalar() or 0
        incident_rate = (total_incidents / actual_attendance * 100) if actual_attendance > 0 else 0

        # Report completion rate
        expected_reports = db.query(func.count(models.Child.id)).join(
            models.EnrollmentApplication
        ).filter(
            models.EnrollmentApplication.status == models.EnrollmentStatus.ACTIVE
        ).scalar() or 0
        expected_reports = expected_reports * days_in_period

        submitted_reports = db.query(func.count(models.DailyReport.id)).filter(
            models.DailyReport.date >= period_start,
            models.DailyReport.date <= period_end,
            models.DailyReport.status.in_([
                models.DailyReportStatus.SUBMITTED,
                models.DailyReportStatus.APPROVED
            ])
        ).scalar() or 0

        approved_reports = db.query(func.count(models.DailyReport.id)).filter(
            models.DailyReport.date >= period_start,
            models.DailyReport.date <= period_end,
            models.DailyReport.status == models.DailyReportStatus.APPROVED
        ).scalar() or 0

        report_submission_rate = (submitted_reports / expected_reports * 100) if expected_reports > 0 else 0
        report_approval_rate = (approved_reports / submitted_reports * 100) if submitted_reports > 0 else 0
        report_completion_rate = report_submission_rate  # Same as submission rate for backward compatibility

        # Average governance score
        avg_governance = db.query(func.avg(models.GovernanceScore.final_governance_score)).filter(
            models.GovernanceScore.period_start >= period_start,
            models.GovernanceScore.period_end <= period_end
        ).scalar() or 0

        return NetworkSummary(
            total_kindergartens=total_kg,
            total_children=total_children,
            total_staff=total_staff,
            total_capacity=total_capacity,
            enrollment_rate=round(enrollment_rate, 2),
            attendance_rate=round(attendance_rate, 2),
            incident_rate=round(incident_rate, 4),
            report_submission_rate=round(report_submission_rate, 2),
            report_approval_rate=round(report_approval_rate, 2),
            report_completion_rate=round(report_completion_rate, 2),
            governance_avg_score=round(avg_governance, 2)
        )

    @staticmethod
    def get_governorate_breakdown(
        db: Session,
        period_start: date,
        period_end: date
    ) -> List[GovernorateMetrics]:
        """Get metrics broken down by governorate"""
        # Get distinct governorates
        governorates = db.query(models.Kindergarten.governorate).filter(
            models.Kindergarten.status == models.KindergartenStatus.ACTIVE,
            models.Kindergarten.governorate.isnot(None)
        ).distinct().all()

        results = []
        for (gov,) in governorates:
            if not gov:
                continue

            # Get kindergartens in this governorate
            kg_ids = db.query(models.Kindergarten.id).filter(
                models.Kindergarten.governorate == gov,
                models.Kindergarten.status == models.KindergartenStatus.ACTIVE
            ).all()
            kg_ids = [k[0] for k in kg_ids]

            kg_count = len(kg_ids)

            # Capacity (from active classes)
            capacity = db.query(func.sum(models.Class.capacity_total)).filter(
                models.Class.kindergarten_id.in_(kg_ids),
                models.Class.is_active == True
            ).scalar() or 0

            # Children count
            children_count = db.query(func.count(models.EnrollmentApplication.id)).filter(
                models.EnrollmentApplication.kindergarten_id.in_(kg_ids),
                models.EnrollmentApplication.status == models.EnrollmentStatus.ACTIVE
            ).scalar() or 0

            # Enrollment rate
            enrollment_rate = (children_count / capacity * 100) if capacity > 0 else 0

            # Attendance rate (simplified)
            days_in_period = (period_end - period_start).days + 1
            expected = children_count * days_in_period
            actual = db.query(func.count(models.AttendanceLog.id)).join(
                models.Child
            ).join(
                models.EnrollmentApplication,
                models.EnrollmentApplication.child_id == models.Child.id
            ).filter(
                models.EnrollmentApplication.kindergarten_id.in_(kg_ids),
                models.AttendanceLog.date >= period_start,
                models.AttendanceLog.date <= period_end
            ).scalar() or 0
            attendance_rate = (actual / expected * 100) if expected > 0 else 0

            # Incident rate
            incidents = db.query(func.count(models.Incident.id)).filter(
                models.Incident.kindergarten_id.in_(kg_ids),
                func.date(models.Incident.occurred_at) >= period_start,
                func.date(models.Incident.occurred_at) <= period_end
            ).scalar() or 0
            incident_rate = (incidents / actual * 100) if actual > 0 else 0

            # Average governance score
            avg_gov_score = db.query(func.avg(models.GovernanceScore.final_governance_score)).filter(
                models.GovernanceScore.kindergarten_id.in_(kg_ids),
                models.GovernanceScore.period_start >= period_start,
                models.GovernanceScore.period_end <= period_end
            ).scalar() or 0

            results.append(GovernorateMetrics(
                governorate=gov,
                kindergarten_count=kg_count,
                children_count=children_count,
                capacity=capacity,
                enrollment_rate=round(enrollment_rate, 2),
                attendance_rate=round(attendance_rate, 2),
                incident_rate=round(incident_rate, 4),
                governance_score=round(avg_gov_score, 2)
            ))

        # Sort by governance score descending
        results.sort(key=lambda x: x.governance_score, reverse=True)
        return results

    @staticmethod
    def get_kindergarten_metrics(
        db: Session,
        kindergarten_id: int,
        period_start: date,
        period_end: date
    ) -> KindergartenMetrics:
        """Get detailed metrics for a specific kindergarten"""
        kg = db.query(models.Kindergarten).filter(
            models.Kindergarten.id == kindergarten_id
        ).first()

        if not kg:
            raise HTTPException(status_code=404, detail="Kindergarten not found")

        # Get capacity from classes
        kg_capacity = db.query(func.sum(models.Class.capacity_total)).filter(
            models.Class.kindergarten_id == kindergarten_id,
            models.Class.is_active == True
        ).scalar() or 0

        # Children count
        children_count = db.query(func.count(models.EnrollmentApplication.id)).filter(
            models.EnrollmentApplication.kindergarten_id == kindergarten_id,
            models.EnrollmentApplication.status == models.EnrollmentStatus.ACTIVE
        ).scalar() or 0

        # Enrollment rate
        enrollment_rate = (children_count / kg_capacity * 100) if kg_capacity > 0 else 0

        # Attendance rate
        attendance_rate = KPIService.compute_attendance_rate(
            db, kindergarten_id, period_start, period_end
        )

        # Incident rate
        incident_rate = KPIService.compute_incident_rate(
            db, kindergarten_id, period_start, period_end
        )

        # Report completion rate
        days_in_period = (period_end - period_start).days + 1
        expected_reports = children_count * days_in_period
        submitted_reports = db.query(func.count(models.DailyReport.id)).join(
            models.Child
        ).join(
            models.EnrollmentApplication,
            models.EnrollmentApplication.child_id == models.Child.id
        ).filter(
            models.EnrollmentApplication.kindergarten_id == kindergarten_id,
            models.DailyReport.date >= period_start,
            models.DailyReport.date <= period_end,
            models.DailyReport.status.in_([
                models.DailyReportStatus.SUBMITTED,
                models.DailyReportStatus.APPROVED
            ])
        ).scalar() or 0

        approved_reports = db.query(func.count(models.DailyReport.id)).join(
            models.Child
        ).join(
            models.EnrollmentApplication,
            models.EnrollmentApplication.child_id == models.Child.id
        ).filter(
            models.EnrollmentApplication.kindergarten_id == kindergarten_id,
            models.DailyReport.date >= period_start,
            models.DailyReport.date <= period_end,
            models.DailyReport.status == models.DailyReportStatus.APPROVED
        ).scalar() or 0

        report_submission_rate = (submitted_reports / expected_reports * 100) if expected_reports > 0 else 0
        report_approval_rate = (approved_reports / submitted_reports * 100) if submitted_reports > 0 else 0
        report_completion_rate = report_submission_rate

        # Ratio compliance
        ratio_compliance = KPIService.compute_ratio_compliance(
            db, kindergarten_id, period_start, period_end
        )

        # Governance score
        gov_score, gov_band = KPIService.compute_governance_score(
            db, kindergarten_id, period_start, period_end
        )

        return KindergartenMetrics(
            id=kg.id,
            name=kg.name_ar,
            governorate=kg.governorate or "",
            children_count=children_count,
            capacity=kg_capacity,
            enrollment_rate=round(enrollment_rate, 2),
            attendance_rate=attendance_rate,
            incident_rate=incident_rate,
            report_submission_rate=round(report_submission_rate, 2),
            report_approval_rate=round(report_approval_rate, 2),
            report_completion_rate=round(report_completion_rate, 2),
            ratio_compliance=ratio_compliance,
            governance_score=gov_score,
            governance_band=gov_band
        )

    @staticmethod
    def get_time_series(
        db: Session,
        metric: str,
        dimension_type: str,
        dimension_id: Optional[str],
        period_start: date,
        period_end: date,
        granularity: str = "daily"
    ) -> List[TimeSeriesPoint]:
        """Get time series data for charts"""
        points = []
        current = period_start

        while current <= period_end:
            if granularity == "daily":
                next_date = current + timedelta(days=1)
            elif granularity == "weekly":
                next_date = current + timedelta(weeks=1)
            elif granularity == "monthly":
                if current.month == 12:
                    next_date = date(current.year + 1, 1, 1)
                else:
                    next_date = date(current.year, current.month + 1, 1)
            else:
                next_date = current + timedelta(days=1)

            # Compute metric for this period
            value = 0.0

            if metric == "attendance_rate":
                if dimension_type == "NETWORK":
                    # Network-wide attendance
                    total_children = db.query(func.count(models.EnrollmentApplication.id)).filter(
                        models.EnrollmentApplication.status == models.EnrollmentStatus.ACTIVE
                    ).scalar() or 1
                    actual = db.query(func.count(models.AttendanceLog.id)).filter(
                        models.AttendanceLog.date >= current,
                        models.AttendanceLog.date < next_date
                    ).scalar() or 0
                    value = (actual / total_children * 100) if total_children > 0 else 0
                elif dimension_type == "KINDERGARTEN" and dimension_id:
                    value = KPIService.compute_attendance_rate(
                        db, int(dimension_id), current, next_date - timedelta(days=1)
                    )

            elif metric == "incident_count":
                query = db.query(func.count(models.Incident.id)).filter(
                    func.date(models.Incident.occurred_at) >= current,
                    func.date(models.Incident.occurred_at) < next_date
                )
                if dimension_type == "KINDERGARTEN" and dimension_id:
                    query = query.filter(models.Incident.kindergarten_id == int(dimension_id))
                value = query.scalar() or 0

            elif metric == "enrollment_count":
                query = db.query(func.count(models.EnrollmentApplication.id)).filter(
                    func.date(models.EnrollmentApplication.created_at) >= current,
                    func.date(models.EnrollmentApplication.created_at) < next_date
                )
                if dimension_type == "KINDERGARTEN" and dimension_id:
                    query = query.filter(models.EnrollmentApplication.kindergarten_id == int(dimension_id))
                value = query.scalar() or 0

            points.append(TimeSeriesPoint(
                date=current.isoformat(),
                value=round(value, 2)
            ))

            current = next_date

        return points

    @staticmethod
    def get_rankings(
        db: Session,
        metric: str,
        period_start: date,
        period_end: date,
        top_n: int = 10,
        bottom: bool = False
    ) -> List[RankingEntry]:
        """Get top/bottom kindergartens by a specific metric"""
        # Get all active kindergartens
        kindergartens = db.query(models.Kindergarten).filter(
            models.Kindergarten.status == models.KindergartenStatus.ACTIVE
        ).all()

        rankings = []
        for kg in kindergartens:
            if metric == "attendance_rate":
                value = KPIService.compute_attendance_rate(db, kg.id, period_start, period_end)
            elif metric == "incident_rate":
                value = KPIService.compute_incident_rate(db, kg.id, period_start, period_end)
            elif metric == "ratio_compliance":
                value = KPIService.compute_ratio_compliance(db, kg.id, period_start, period_end)
            elif metric == "governance_score":
                value, band = KPIService.compute_governance_score(db, kg.id, period_start, period_end)
            else:
                value = 0

            rankings.append({
                "kindergarten_id": kg.id,
                "kindergarten_name": kg.name_ar,
                "governorate": kg.governorate or "",
                "value": value,
                "band": band if metric == "governance_score" else None
            })

        # Sort
        reverse = not bottom  # For most metrics, higher is better
        if metric == "incident_rate":
            reverse = bottom  # For incidents, lower is better

        rankings.sort(key=lambda x: x["value"], reverse=reverse)

        # Return top N with ranks
        results = []
        for i, r in enumerate(rankings[:top_n]):
            results.append(RankingEntry(
                rank=i + 1,
                kindergarten_id=r["kindergarten_id"],
                kindergarten_name=r["kindergarten_name"],
                governorate=r["governorate"],
                value=r["value"],
                band=r["band"]
            ))

        return results

    @staticmethod
    def get_enrollment_analytics(
        db: Session,
        period_start: date,
        period_end: date,
        kindergarten_id: Optional[int] = None
    ) -> Dict[str, Any]:
        """Get enrollment-specific analytics"""
        query = db.query(models.EnrollmentApplication)

        if kindergarten_id:
            query = query.filter(models.EnrollmentApplication.kindergarten_id == kindergarten_id)

        # Applications by status
        status_counts = {}
        for status in models.EnrollmentStatus:
            count = query.filter(
                models.EnrollmentApplication.status == status
            ).count()
            status_counts[status.value] = count

        # New applications in period
        new_applications = query.filter(
            func.date(models.EnrollmentApplication.created_at) >= period_start,
            func.date(models.EnrollmentApplication.created_at) <= period_end
        ).count()

        # Conversion funnel
        total = query.count()
        active = status_counts.get("ACTIVE", 0)
        conversion_rate = (active / total * 100) if total > 0 else 0

        return {
            "status_breakdown": status_counts,
            "new_applications": new_applications,
            "total_applications": total,
            "active_enrollments": active,
            "conversion_rate": round(conversion_rate, 2)
        }

    @staticmethod
    def get_attendance_analytics(
        db: Session,
        period_start: date,
        period_end: date,
        kindergarten_id: Optional[int] = None
    ) -> Dict[str, Any]:
        """Get attendance-specific analytics"""
        query = db.query(models.AttendanceLog).filter(
            models.AttendanceLog.date >= period_start,
            models.AttendanceLog.date <= period_end
        )

        if kindergarten_id:
            query = query.join(models.Child).join(
                models.EnrollmentApplication,
                models.EnrollmentApplication.child_id == models.Child.id
            ).filter(models.EnrollmentApplication.kindergarten_id == kindergarten_id)

        total_logs = query.count()

        # Attendance by day of week
        day_distribution = {}
        for i in range(7):
            day_name = ["الأحد", "الإثنين", "الثلاثاء", "الأربعاء", "الخميس", "الجمعة", "السبت"][i]
            from sqlalchemy import extract
            count = query.filter(
                extract('dow', models.AttendanceLog.date) == i
            ).count()
            day_distribution[day_name] = count

        # Average daily attendance
        days_in_period = (period_end - period_start).days + 1
        avg_daily = total_logs / days_in_period if days_in_period > 0 else 0

        return {
            "total_attendance_logs": total_logs,
            "average_daily_attendance": round(avg_daily, 1),
            "day_of_week_distribution": day_distribution,
            "period_days": days_in_period
        }

    @staticmethod
    def get_safety_analytics(
        db: Session,
        period_start: date,
        period_end: date,
        kindergarten_id: Optional[int] = None
    ) -> Dict[str, Any]:
        """Get safety/incident analytics"""
        query = db.query(models.Incident).filter(
            func.date(models.Incident.occurred_at) >= period_start,
            func.date(models.Incident.occurred_at) <= period_end
        )

        if kindergarten_id:
            query = query.filter(models.Incident.kindergarten_id == kindergarten_id)

        total_incidents = query.count()

        # By severity
        severity_counts = {}
        for severity in models.SeverityLevel:
            count = query.filter(models.Incident.severity_level == severity).count()
            severity_counts[severity.value] = count

        # By type
        type_counts = {}
        for inc_type in models.IncidentType:
            count = query.filter(models.Incident.incident_type == inc_type).count()
            type_counts[inc_type.value] = count

        # Resolution rate
        resolved = query.filter(models.Incident.resolved_at.isnot(None)).count()
        resolution_rate = (resolved / total_incidents * 100) if total_incidents > 0 else 0

        return {
            "total_incidents": total_incidents,
            "severity_breakdown": severity_counts,
            "type_breakdown": type_counts,
            "resolved_count": resolved,
            "resolution_rate": round(resolution_rate, 2)
        }

    @staticmethod
    def get_staffing_analytics(
        db: Session,
        period_start: date,
        period_end: date,
        kindergarten_id: Optional[int] = None
    ) -> Dict[str, Any]:
        """Get staffing and ratio compliance analytics"""
        query = db.query(models.RatioCompliance).filter(
            models.RatioCompliance.date >= period_start,
            models.RatioCompliance.date <= period_end
        )

        if kindergarten_id:
            query = query.filter(models.RatioCompliance.kindergarten_id == kindergarten_id)

        # Sum up compliance data
        result = query.with_entities(
            func.sum(models.RatioCompliance.compliant_minutes),
            func.sum(models.RatioCompliance.operating_minutes),
            func.avg(models.RatioCompliance.staff_count_avg),
            func.avg(models.RatioCompliance.child_count_avg)
        ).first()

        compliant_min = result[0] or 0
        operating_min = result[1] or 1
        avg_staff = result[2] or 0
        avg_children = result[3] or 0

        compliance_rate = (compliant_min / operating_min * 100) if operating_min > 0 else 0
        avg_ratio = (avg_children / avg_staff) if avg_staff > 0 else 0

        # Staff count by role
        staff_query = db.query(models.User).filter(
            models.User.role.in_([models.UserRole.MANAGER, models.UserRole.SUPERVISOR]),
            models.User.status == models.UserStatus.ACTIVE
        )
        if kindergarten_id:
            staff_query = staff_query.filter(models.User.kindergarten_id == kindergarten_id)

        staff_by_role = {}
        for role in [models.UserRole.MANAGER, models.UserRole.SUPERVISOR]:
            count = staff_query.filter(models.User.role == role).count()
            staff_by_role[role.value] = count

        return {
            "compliance_rate": round(compliance_rate, 2),
            "average_staff_count": round(avg_staff, 1),
            "average_child_count": round(avg_children, 1),
            "average_ratio": round(avg_ratio, 1),
            "staff_by_role": staff_by_role,
            "compliant_minutes": compliant_min,
            "operating_minutes": operating_min
        }

    @staticmethod
    def get_daily_reports_analytics(
        db: Session,
        period_start: date,
        period_end: date,
        kindergarten_id: Optional[int] = None
    ) -> Dict[str, Any]:
        """Get daily reports analytics"""
        query = db.query(models.DailyReport).filter(
            models.DailyReport.date >= period_start,
            models.DailyReport.date <= period_end
        )

        if kindergarten_id:
            query = query.join(models.Child).join(
                models.EnrollmentApplication,
                models.EnrollmentApplication.child_id == models.Child.id
            ).filter(models.EnrollmentApplication.kindergarten_id == kindergarten_id)

        total_reports = query.count()

        # By status
        status_counts = {}
        for status in models.DailyReportStatus:
            count = query.filter(models.DailyReport.status == status).count()
            status_counts[status.value] = count

        # Completion rate
        sent_count = status_counts.get("SENT", 0)
        completion_rate = (sent_count / total_reports * 100) if total_reports > 0 else 0

        return {
            "total_reports": total_reports,
            "status_breakdown": status_counts,
            "sent_count": sent_count,
            "completion_rate": round(completion_rate, 2)
        }


# =============================================================================
# API Endpoints
# =============================================================================

def get_date_range(
    start_date: Optional[date] = Query(None),
    end_date: Optional[date] = Query(None)
) -> tuple:
    """Parse date range, default to last 30 days"""
    if not end_date:
        end_date = date.today()
    if not start_date:
        start_date = end_date - timedelta(days=30)
    return start_date, end_date


@router.get("/overview")
def get_analytics_overview(
    start_date: Optional[date] = Query(None),
    end_date: Optional[date] = Query(None),
    current_user: models.User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """
    Get network-wide analytics overview (Admin only)
    """
    validators.validate_admin_role(current_user)

    period_start, period_end = get_date_range(start_date, end_date)

    summary = AnalyticsService.get_network_summary(db, period_start, period_end)
    governorates = AnalyticsService.get_governorate_breakdown(db, period_start, period_end)

    # Include all Jordan governorates for filter dropdown, even if no data
    from config import settings
    all_governorates = []
    for gov_name in settings.JORDAN_GOVERNORATES:
        # Find if we have data for this governorate
        existing = next((g for g in governorates if g.governorate == gov_name), None)
        if existing:
            all_governorates.append(existing)
        else:
            # Add empty entry for governorates with no data
            all_governorates.append(GovernorateMetrics(
                governorate=gov_name,
                kindergartens_count=0,
                capacity_total=0,
                children_count=0,
                attendance_rate=0.0,
                incident_rate=0.0,
                ratio_compliance=0.0,
                governance_avg_score=0.0
            ))

    return {
        "period_start": period_start.isoformat(),
        "period_end": period_end.isoformat(),
        "summary": summary,
        "governorates": all_governorates
    }


@router.get("/drilldown/{dimension_type}/{dimension_id}")
def get_drilldown(
    dimension_type: str,
    dimension_id: str,
    start_date: Optional[date] = Query(None),
    end_date: Optional[date] = Query(None),
    current_user: models.User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """
    Drill down into a specific dimension (governorate, kindergarten, class, child)
    """
    validators.validate_admin_role(current_user)

    period_start, period_end = get_date_range(start_date, end_date)

    if dimension_type.upper() == "GOVERNORATE":
        # Get all kindergartens in this governorate
        kindergartens = db.query(models.Kindergarten).filter(
            models.Kindergarten.governorate == dimension_id,
            models.Kindergarten.status == models.KindergartenStatus.ACTIVE
        ).all()

        children_list = []
        for kg in kindergartens:
            metrics = AnalyticsService.get_kindergarten_metrics(
                db, kg.id, period_start, period_end
            )
            children_list.append(metrics.dict())

        return DrilldownResponse(
            dimension_type="GOVERNORATE",
            dimension_id=dimension_id,
            dimension_name=dimension_id,
            period_start=period_start,
            period_end=period_end,
            metrics={"kindergarten_count": len(kindergartens)},
            children=children_list
        )

    elif dimension_type.upper() == "KINDERGARTEN":
        kg_id = int(dimension_id)
        metrics = AnalyticsService.get_kindergarten_metrics(
            db, kg_id, period_start, period_end
        )

        # Get classes
        classes = db.query(models.Class).filter(
            models.Class.kindergarten_id == kg_id
        ).all()

        class_list = []
        for cls in classes:
            # Count children in class
            children_count = db.query(func.count(models.EnrollmentApplication.id)).filter(
                models.EnrollmentApplication.class_id == cls.id,
                models.EnrollmentApplication.status == models.EnrollmentStatus.ACTIVE
            ).scalar() or 0

            # Compute age group from min/max months
            age_group = f"{cls.min_age_months}-{cls.max_age_months} شهر"

            class_list.append({
                "id": cls.id,
                "name": cls.name_ar,
                "capacity": cls.capacity_total,
                "children_count": children_count,
                "age_group": age_group
            })

        return DrilldownResponse(
            dimension_type="KINDERGARTEN",
            dimension_id=dimension_id,
            dimension_name=metrics.name,
            period_start=period_start,
            period_end=period_end,
            metrics=metrics.dict(),
            children=class_list
        )

    elif dimension_type.upper() == "CLASS":
        cls_id = int(dimension_id)
        cls = db.query(models.Class).filter(models.Class.id == cls_id).first()

        if not cls:
            raise HTTPException(status_code=404, detail="Class not found")

        # Get children in class
        enrollments = db.query(models.EnrollmentApplication).filter(
            models.EnrollmentApplication.class_id == cls_id,
            models.EnrollmentApplication.status == models.EnrollmentStatus.ACTIVE
        ).all()

        children_list = []
        for enrollment in enrollments:
            child = enrollment.child
            if child:
                # Get attendance for this child
                attendance_count = db.query(func.count(models.AttendanceLog.id)).filter(
                    models.AttendanceLog.child_id == child.id,
                    models.AttendanceLog.date >= period_start,
                    models.AttendanceLog.date <= period_end
                ).scalar() or 0

                days_in_period = (period_end - period_start).days + 1
                attendance_rate = (attendance_count / days_in_period * 100) if days_in_period > 0 else 0

                children_list.append({
                    "id": child.id,
                    "name": f"{child.first_name} {child.last_name}",
                    "attendance_rate": round(attendance_rate, 2),
                    "attendance_days": attendance_count
                })

        # Compute age group from min/max months
        cls_age_group = f"{cls.min_age_months}-{cls.max_age_months} شهر"

        return DrilldownResponse(
            dimension_type="CLASS",
            dimension_id=dimension_id,
            dimension_name=cls.name_ar,
            period_start=period_start,
            period_end=period_end,
            metrics={
                "capacity": cls.capacity_total,
                "children_count": len(children_list),
                "age_group": cls_age_group
            },
            children=children_list
        )

    raise HTTPException(status_code=400, detail="Invalid dimension type")


@router.get("/time-series")
def get_time_series_data(
    metric: str = Query(..., description="Metric to chart: attendance_rate, incident_count, enrollment_count"),
    dimension_type: str = Query("NETWORK"),
    dimension_id: Optional[str] = Query(None),
    granularity: str = Query("daily", description="daily, weekly, monthly"),
    start_date: Optional[date] = Query(None),
    end_date: Optional[date] = Query(None),
    current_user: models.User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """Get time series data for charts"""
    validators.validate_admin_role(current_user)

    period_start, period_end = get_date_range(start_date, end_date)

    data = AnalyticsService.get_time_series(
        db, metric, dimension_type, dimension_id, period_start, period_end, granularity
    )

    return {
        "metric": metric,
        "dimension_type": dimension_type,
        "dimension_id": dimension_id,
        "granularity": granularity,
        "period_start": period_start.isoformat(),
        "period_end": period_end.isoformat(),
        "data": [p.dict() for p in data]
    }


@router.get("/compare")
def compare_kindergartens(
    kg_ids: str = Query(..., description="Comma-separated kindergarten IDs"),
    start_date: Optional[date] = Query(None),
    end_date: Optional[date] = Query(None),
    current_user: models.User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """Compare multiple kindergartens side by side"""
    validators.validate_admin_role(current_user)

    period_start, period_end = get_date_range(start_date, end_date)

    ids = [int(x.strip()) for x in kg_ids.split(",") if x.strip()]

    comparisons = []
    for kg_id in ids:
        try:
            metrics = AnalyticsService.get_kindergarten_metrics(
                db, kg_id, period_start, period_end
            )
            comparisons.append(metrics.dict())
        except HTTPException:
            continue

    return {
        "period_start": period_start.isoformat(),
        "period_end": period_end.isoformat(),
        "kindergartens": comparisons
    }


@router.get("/rankings/{metric}")
def get_metric_rankings(
    metric: str,
    top_n: int = Query(10, ge=1, le=50),
    bottom: bool = Query(False),
    start_date: Optional[date] = Query(None),
    end_date: Optional[date] = Query(None),
    current_user: models.User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """Get kindergarten rankings by a specific metric"""
    validators.validate_admin_role(current_user)

    period_start, period_end = get_date_range(start_date, end_date)

    rankings = AnalyticsService.get_rankings(
        db, metric, period_start, period_end, top_n, bottom
    )

    return {
        "metric": metric,
        "period_start": period_start.isoformat(),
        "period_end": period_end.isoformat(),
        "order": "bottom" if bottom else "top",
        "rankings": [r.dict() for r in rankings]
    }


@router.get("/enrollments/summary")
def get_enrollment_summary(
    kindergarten_id: Optional[int] = Query(None),
    start_date: Optional[date] = Query(None),
    end_date: Optional[date] = Query(None),
    current_user: models.User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """Get enrollment analytics"""
    validators.validate_admin_role(current_user)

    period_start, period_end = get_date_range(start_date, end_date)

    data = AnalyticsService.get_enrollment_analytics(
        db, period_start, period_end, kindergarten_id
    )

    return {
        "period_start": period_start.isoformat(),
        "period_end": period_end.isoformat(),
        "kindergarten_id": kindergarten_id,
        **data
    }


@router.get("/attendance/summary")
def get_attendance_summary(
    kindergarten_id: Optional[int] = Query(None),
    start_date: Optional[date] = Query(None),
    end_date: Optional[date] = Query(None),
    current_user: models.User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """Get attendance analytics"""
    validators.validate_admin_role(current_user)

    period_start, period_end = get_date_range(start_date, end_date)

    data = AnalyticsService.get_attendance_analytics(
        db, period_start, period_end, kindergarten_id
    )

    return {
        "period_start": period_start.isoformat(),
        "period_end": period_end.isoformat(),
        "kindergarten_id": kindergarten_id,
        **data
    }


@router.get("/daily-reports/summary")
def get_daily_reports_summary(
    kindergarten_id: Optional[int] = Query(None),
    start_date: Optional[date] = Query(None),
    end_date: Optional[date] = Query(None),
    current_user: models.User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """Get daily reports analytics"""
    validators.validate_admin_role(current_user)

    period_start, period_end = get_date_range(start_date, end_date)

    data = AnalyticsService.get_daily_reports_analytics(
        db, period_start, period_end, kindergarten_id
    )

    return {
        "period_start": period_start.isoformat(),
        "period_end": period_end.isoformat(),
        "kindergarten_id": kindergarten_id,
        **data
    }


@router.get("/safety/summary")
def get_safety_summary(
    kindergarten_id: Optional[int] = Query(None),
    start_date: Optional[date] = Query(None),
    end_date: Optional[date] = Query(None),
    current_user: models.User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """Get safety/incident analytics"""
    validators.validate_admin_role(current_user)

    period_start, period_end = get_date_range(start_date, end_date)

    data = AnalyticsService.get_safety_analytics(
        db, period_start, period_end, kindergarten_id
    )

    return {
        "period_start": period_start.isoformat(),
        "period_end": period_end.isoformat(),
        "kindergarten_id": kindergarten_id,
        **data
    }


@router.get("/staffing/summary")
def get_staffing_summary(
    kindergarten_id: Optional[int] = Query(None),
    start_date: Optional[date] = Query(None),
    end_date: Optional[date] = Query(None),
    current_user: models.User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """Get staffing analytics"""
    validators.validate_admin_role(current_user)

    period_start, period_end = get_date_range(start_date, end_date)

    data = AnalyticsService.get_staffing_analytics(
        db, period_start, period_end, kindergarten_id
    )

    return {
        "period_start": period_start.isoformat(),
        "period_end": period_end.isoformat(),
        "kindergarten_id": kindergarten_id,
        **data
    }


@router.post("/export")
def request_export(
    request_body: ExportRequest,
    background_tasks: BackgroundTasks = None,
    current_user: models.User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """Request an async export job"""
    validators.validate_admin_role(current_user)

    # Create export job
    job = models.ExportJob(
        user_id=current_user.id,
        export_format=models.ExportFormat(request_body.export_format.upper()),
        report_type=request_body.report_type,
        filters=request_body.filters,
        status=models.ExportStatus.PENDING
    )

    db.add(job)
    db.commit()
    db.refresh(job)

    # In production, this would trigger a background task
    # For now, we just create the job record

    return ExportJobResponse(
        job_id=job.id,
        status=job.status.value,
        report_type=job.report_type,
        created_at=job.created_at
    )


@router.get("/export/{job_id}")
def get_export_status(
    job_id: int,
    current_user: models.User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """Check export job status"""
    job = db.query(models.ExportJob).filter(
        models.ExportJob.id == job_id,
        models.ExportJob.user_id == current_user.id
    ).first()

    if not job:
        raise HTTPException(status_code=404, detail="Export job not found")

    return ExportJobResponse(
        job_id=job.id,
        status=job.status.value,
        report_type=job.report_type,
        created_at=job.created_at,
        file_path=job.file_path
    )
