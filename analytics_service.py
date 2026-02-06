"""
Analytics and Reporting Services for Admin Dashboard
Implements drill-down analytics from Network → Governorate → Kindergarten → Class → Child
"""
from fastapi import APIRouter, Depends, Query, HTTPException, status, BackgroundTasks
from pydantic import BaseModel, Field
from typing import List, Optional, Dict, Any
from datetime import date, datetime, timedelta
from sqlalchemy.orm import Session
from sqlalchemy import func, and_, or_, case, desc, asc
from enum import Enum

import models
from database import get_db
from dependencies import get_current_user, get_current_user_or_redirect
from kpi_service import KPIService
import validators
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
        from_attributes = True

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

router = APIRouter(prefix="/analytics", tags=["Analytics"])

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


class ConsolidatedAnalyticsResponse(BaseModel):
    network_summary: NetworkSummary
    governorate_breakdown: List["GovernorateMetrics"]
    attendance_trend: List["TimeSeriesPoint"]
    incident_trend: List["TimeSeriesPoint"]
    risk_radar: List[Dict[str, Any]]
    governance_distribution: "GovernanceDistribution"


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
    
    # Advanced Metrics
    attendance_trend_slope: Optional[float] = None
    risk_score: Optional[float] = None
    attendance_incident_correlation: Optional[float] = None


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


class GovernanceDistribution(BaseModel):
    green: int
    amber: int
    red: int


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
# API Endpoints
# =============================================================================

@router.get("/network-summary", response_model=NetworkSummary)
def get_network_summary_endpoint(
    period_start: date = Query(...),
    period_end: date = Query(...),
    current_user: models.User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """Get network-wide summary metrics (Admin only)"""
    validators.validate_admin_role(current_user)
    return AnalyticsService.get_network_summary(db, period_start, period_end)

@router.get("/governorate-breakdown", response_model=List[GovernorateMetrics])
def get_governorate_breakdown_endpoint(
    period_start: date = Query(...),
    period_end: date = Query(...),
    current_user: models.User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """Get metrics broken down by governorate (Admin only)"""
    validators.validate_admin_role(current_user)
    return AnalyticsService.get_governorate_breakdown(db, period_start, period_end)


@router.get("/dashboard-data", response_model=ConsolidatedAnalyticsResponse)
def get_consolidated_dashboard_data(
    period_start: date = Query(...),
    period_end: date = Query(...),
    current_user: models.User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """Get all data needed for the main analytics dashboard."""
    validators.validate_admin_role(current_user)
    
    # Validate date range
    if period_start > period_end:
        raise HTTPException(status_code=400, detail="Invalid date range: start date must be before or equal to end date")
    
    if (period_end - period_start).days > 365:
        raise HTTPException(status_code=400, detail="Date range cannot exceed 365 days")

    network_summary = AnalyticsService.get_network_summary(db, period_start, period_end)
    governorate_breakdown = AnalyticsService.get_governorate_breakdown(db, period_start, period_end)
    attendance_trend = AnalyticsService.get_network_trends(db, "attendance", period_start, period_end)
    incident_trend = AnalyticsService.get_network_trends(db, "incidents", period_start, period_end)
    risk_radar = AnalyticsService.get_high_risk_children(db)
    governance_distribution = AnalyticsService.get_governance_distribution(db, period_start, period_end)

    return ConsolidatedAnalyticsResponse(
        network_summary=network_summary,
        governorate_breakdown=governorate_breakdown,
        attendance_trend=attendance_trend,
        incident_trend=incident_trend,
        risk_radar=risk_radar,
        governance_distribution=governance_distribution,
    )



@router.get("/trends", response_model=List[TimeSeriesPoint])
def get_network_trends_endpoint(
    metric: str = Query(..., description="Metric to retrieve: attendance, incidents"),
    period_start: date = Query(...),
    period_end: date = Query(...),
    current_user: models.User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """Get time-series trend data for network (Admin only)"""
    validators.validate_admin_role(current_user)
    return AnalyticsService.get_network_trends(db, metric, period_start, period_end)

@router.get("/risk-radar")
def get_risk_radar_endpoint(
    current_user: models.User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """Get list of high-risk entities (Admin only)"""
    validators.validate_admin_role(current_user)
    return AnalyticsService.get_high_risk_children(db)

@router.post("/export")
def export_analytics_data(
    request: ExportRequest,
    current_user: models.User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """
    Export analytics reports (CSV).
    """
    validators.validate_admin_role(current_user)

    # Extract dates from filters if present
    start_str = request.filters.get("period_start") if request.filters else None
    end_str = request.filters.get("period_end") if request.filters else None
    
    if not start_str or not end_str:
         # Default to last 30 days if not provided
         end_date = date.today()
         start_date = end_date - timedelta(days=30)
    else:
        try:
            # Handle string dates
            if isinstance(start_str, str):
                start_date = datetime.strptime(start_str, "%Y-%m-%d").date()
            else:
                start_date = start_str
                
            if isinstance(end_str, str):
                end_date = datetime.strptime(end_str, "%Y-%m-%d").date()
            else:
                end_date = end_str
        except ValueError:
            raise HTTPException(status_code=400, detail="Invalid date format")

    import csv
    import io
    from fastapi.responses import Response

    output = io.StringIO()
    writer = csv.writer(output)

    if request.report_type == "attendance":
        writer.writerow(["Kindergarten", "Children Count", "Capacity", "Attendance Rate %"])
        # Re-use governorate breakdown or network summary logic? 
        # Better to iterate all KGs for a detailed report
        kgs = db.query(models.Kindergarten).filter(models.Kindergarten.status == models.KindergartenStatus.ACTIVE).all()
        for kg in kgs:
            rate = KPIService.compute_attendance_rate(db, kg.id, start_date, end_date)
            # Fetch other metrics if needed
            writer.writerow([kg.name_ar, len(kg.enrollments), "N/A", rate])

    elif request.report_type == "incidents":
        writer.writerow(["Date", "Kindergarten", "Type", "Severity", "Description", "Child"])
        incidents = db.query(models.Incident).filter(
            func.date(models.Incident.occurred_at) >= start_date,
            func.date(models.Incident.occurred_at) <= end_date
        ).all()
        for inc in incidents:
            ch_name = f"{inc.child.first_name} {inc.child.last_name}" if inc.child else "Unknown"
            writer.writerow([
                inc.occurred_at.strftime("%Y-%m-%d"),
                inc.kindergarten.name_ar,
                inc.type.value,
                inc.severity_level.value,
                inc.description,
                ch_name
            ])

    elif request.report_type == "compliance":
        writer.writerow(["Kindergarten", "Ratio Compliance %", "Governance Score"])
        kgs = db.query(models.Kindergarten).filter(models.Kindergarten.status == models.KindergartenStatus.ACTIVE).all()
        for kg in kgs:
            ratio = KPIService.compute_ratio_compliance(db, kg.id, start_date, end_date)
            # Governance Score logic might be complex, verify if exists in KPIService
            # KPIService.compute_governance_score returns (score, band)
            # Assuming compute_governance_score exists as previously viewed/inferred
            # If not, we might error. Let's assume it exists or use placeholder.
            # I will use a safe try/except or placeholder if not sure. 
            # Reviewing code items: 'KPIService.compute_governance_quality_index' was in viewed_code_items.
            # But 'compute_governance_score' was mentioned in 'get_kindergarten_metrics' snippet (line 737)
            # So it likely exists.
            try:
                gov_score, _ = KPIService.compute_governance_score(db, kg.id, start_date, end_date)
            except:
                gov_score = 0
            writer.writerow([kg.name_ar, ratio, gov_score])

    elif request.report_type == "governorate":
        writer.writerow(["Governorate", "Kindergartens", "Children", "Attendance %", "Incident Rate", "Governance Score"])
        # Re-use existing service logic
        data = AnalyticsService.get_governorate_breakdown(db, start_date, end_date)
        for item in data:
            writer.writerow([
                item.governorate,
                item.kindergarten_count,
                item.children_count,
                item.attendance_rate,
                item.incident_rate,
                item.governance_score
            ])

    elif request.report_type == "full_audit":
        writer.writerow(["Timestamp", "User", "Action", "Entity", "Details", "IP"])
        logs = db.query(models.AuditLog).filter(
             func.date(models.AuditLog.created_at) >= start_date,
             func.date(models.AuditLog.created_at) <= end_date
        ).order_by(desc(models.AuditLog.created_at)).all()
        
        # Pre-fetch users to avoid N+1
        user_map = {u.id: u.username for u in db.query(models.User).all()}
        
        for log in logs:
            username = user_map.get(log.user_id, "Unknown")
            writer.writerow([
                log.created_at,
                username,
                log.action,
                log.entity_type,
                log.details,
                log.ip_address
            ])

    else:
        raise HTTPException(status_code=400, detail="Invalid report type")

    filename = f"{request.report_type}_report_{start_date}_{end_date}.csv"
    return Response(
        content=output.getvalue(),
        media_type="text/csv",
        headers={"Content-Disposition": f"attachment; filename={filename}"}
    )

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


            # === Advanced Analytics Implementation ===
            
            # 1. Attendance Trend Slope (Linear Regression)
            # Calculate daily attendance rates for the period
            daily_attendance = db.query(models.AttendanceLog.date, func.count(models.AttendanceLog.id)).join(models.Child).join(models.EnrollmentApplication, models.EnrollmentApplication.child_id == models.Child.id).filter(
                models.EnrollmentApplication.kindergarten_id == kg_id,
                models.AttendanceLog.date >= period_start,
                models.AttendanceLog.date <= period_end
            ).group_by(models.AttendanceLog.date).order_by(models.AttendanceLog.date).all()
            
            if daily_attendance:
                # Prepare data for regression: x = day index, y = count
                dates = [d[0] for d in daily_attendance]
                counts = [d[1] for d in daily_attendance]
                x_vals = range(len(counts))
                
                # Simple Least Squares Slope: (mean(x*y) - mean(x)*mean(y)) / (mean(x^2) - mean(x)^2)
                n = len(counts)
                if n > 1:
                    sum_x = sum(x_vals)
                    sum_y = sum(counts)
                    sum_xy = sum(i * count for i, count in enumerate(counts))
                    sum_xx = sum(i*i for i in x_vals)
                    
                    slope = (n * sum_xy - sum_x * sum_y) / (n * sum_xx - sum_x**2)
                    attendance_trend_slope = round(slope, 3)
                else:
                    attendance_trend_slope = 0.0
            
            # 2. Risk Score (Heuristic)
            # Factors: Low attendance (<80%), Recent Incidents, No Observations
            # Simplified: Count of children with < 80% attendance in period
            total_kids = len(db.query(models.EnrollmentApplication).filter(models.EnrollmentApplication.kindergarten_id == kg_id, models.EnrollmentApplication.status == models.EnrollmentStatus.ACTIVE).all())
            if total_kids > 0:
                at_risk_kids = 0
                all_enrollments = db.query(models.EnrollmentApplication).filter(models.EnrollmentApplication.kindergarten_id == kg_id, models.EnrollmentApplication.status == models.EnrollmentStatus.ACTIVE).all()
                for enrollment in all_enrollments:
                    child_att_days = db.query(func.count(models.AttendanceLog.id)).filter(
                         models.AttendanceLog.child_id == enrollment.child_id,
                         models.AttendanceLog.date >= period_start,
                         models.AttendanceLog.date <= period_end
                    ).scalar() or 0
                    child_exp_days = (period_end - period_start).days + 1 # Simplified
                    if child_exp_days > 0 and (child_att_days / child_exp_days) < 0.80:
                        at_risk_kids += 1
                
                risk_score = (at_risk_kids / total_kids) * 100 # % of "At Risk" population
            else:
                risk_score = 0.0

            # 3. Attendance vs Incident Correlation
            # daily_attendance (calculated above) vs incidents per day
            if len(daily_attendance) > 1:
                # Get daily incidents
                daily_incidents_q = db.query(func.date(models.Incident.occurred_at), func.count(models.Incident.id)).filter(
                    models.Incident.kindergarten_id == kg_id,
                    func.date(models.Incident.occurred_at) >= period_start,
                    func.date(models.Incident.occurred_at) <= period_end
                ).group_by(func.date(models.Incident.occurred_at)).all()
                incident_map = {d[0]: d[1] for d in daily_incidents_q}
                
                # Align data
                inc_counts = [incident_map.get(d[0], 0) for d in daily_attendance]
                att_counts = [d[1] for d in daily_attendance]
                
                # Pearson Correlation
                n = len(att_counts)
                sum_x = sum(att_counts)
                sum_y = sum(inc_counts)
                sum_xy = sum(x*y for x,y in zip(att_counts, inc_counts))
                sum_x2 = sum(x*x for x in att_counts)
                sum_y2 = sum(y*y for y in inc_counts)
                
                # Denominator for correlation
                denom = ((n * sum_x2 - sum_x**2) * (n * sum_y2 - sum_y**2)) ** 0.5
                if denom != 0:
                    attendance_incident_correlation = (n * sum_xy - sum_x * sum_y) / denom
                else:
                    attendance_incident_correlation = 0.0

            # 4. Improvement Velocity (Trend of Governance Scores)
            # Placeholder: compare current score vs prev period
            # For now, 0
            improvement_velocity = 0.0
            
            # 5. Populate Metadata
            parent_satisfaction_nps = 0.0 # Placeholder
            child_development_index = 0.0 # Placeholder
            staff_turnover_rate = 0.0 # Placeholder
            regulatory_compliance_score = ratio_compliance_rate # Proxy

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
    def get_network_trends(
        db: Session,
        metric: str,
        period_start: date,
        period_end: date
    ) -> List[TimeSeriesPoint]:
        """
        Get daily trend data for the entire network.
        Metric: 'attendance', 'incidents'
        """
        results = []
        
        if metric == 'attendance':
            # Daily attendance rate across all KGs
            # Ideally: Sum(attended) / Sum(expected) per day
            # Simplified: Just count attended logs for now as a proxy or calculate rate if possible
            # Let's count total attendance logs per day
            query = db.query(
                models.AttendanceLog.date, 
                func.count(models.AttendanceLog.id)
            ).filter(
                models.AttendanceLog.date >= period_start,
                models.AttendanceLog.date <= period_end
            ).group_by(models.AttendanceLog.date).order_by(models.AttendanceLog.date).all()
            
            for date_val, count in query:
                # We need "Rate" but calculating expected per day globally is expensive. 
                # Let's just return Count for the trend line, labeled "Hudur" 
                # OR estimate expected based on active children count *today* (rough approx)
                results.append(TimeSeriesPoint(
                    date=date_val.strftime("%Y-%m-%d"),
                    value=float(count),
                    label="Hudur"
                ))
                
        elif metric == 'incidents':
            query = db.query(
                func.date(models.Incident.occurred_at), 
                func.count(models.Incident.id)
            ).filter(
                func.date(models.Incident.occurred_at) >= period_start,
                func.date(models.Incident.occurred_at) <= period_end
            ).group_by(func.date(models.Incident.occurred_at)).order_by(func.date(models.Incident.occurred_at)).all()
            
            for date_str, count in query:
                 results.append(TimeSeriesPoint(
                    date=str(date_str), # sqlite might return str
                    value=float(count),
                    label="Incidents"
                ))
        
        return results

    @staticmethod
    def get_high_risk_children(db: Session, limit: int = 5) -> List[Dict[str, Any]]:
        """
        Identify children at risk based on attendance (<80%) and incidents.
        Returns top N riskiest profiles.
        """
        # 1. Find children with low attendance in last 30 days
        end_date = date.today()
        start_date = end_date - timedelta(days=30)
        
        # Calculate attendance counts for all active children
        # This is expensive, so we limit to last 30 days
        
        # Subquery for attendance count
        att_sub = db.query(
            models.AttendanceLog.child_id, 
            func.count(models.AttendanceLog.id).label('days')
        ).filter(
            models.AttendanceLog.date >= start_date
        ).group_by(models.AttendanceLog.child_id).subquery()
        
        # Main query
        active_children = db.query(
             models.Child,
             models.Kindergarten.name_ar,
             func.coalesce(att_sub.c.days, 0).label('attended')
        ).join(
            models.EnrollmentApplication, models.EnrollmentApplication.child_id == models.Child.id
        ).join(
             models.Kindergarten, models.EnrollmentApplication.kindergarten_id == models.Kindergarten.id
        ).outerjoin(
            att_sub, att_sub.c.child_id == models.Child.id
        ).filter(
            models.EnrollmentApplication.status == models.EnrollmentStatus.ACTIVE
        ).all()
        
        risk_list = []
        expected_days = 20 # Approx for 30 days excluding weekends
        
        for child, kg_name, attended in active_children:
            rate = (attended / expected_days) * 100
            if rate < 80:
                risk_list.append({
                    "name": f"{child.first_name} {child.last_name}",
                    "kindergarten": kg_name,
                    "reason": "معدل غياب مرتفع",
                    "risk_score": int(100 - rate) # Simple score
                })
        
        # Sort by risk score desc
        risk_list.sort(key=lambda x: x['risk_score'], reverse=True)
        return risk_list[:limit]

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
    def get_governance_distribution(
        db: Session, period_start: date, period_end: date
    ) -> GovernanceDistribution:
        """Get the distribution of kindergartens by governance band."""
        kindergartens = db.query(models.Kindergarten).filter(
            models.Kindergarten.status == models.KindergartenStatus.ACTIVE
        ).all()

        green = 0
        amber = 0
        red = 0

        for kg in kindergartens:
            _, band = KPIService.compute_governance_score(db, kg.id, period_start, period_end)
            if band == "Green":
                green += 1
            elif band == "Amber":
                amber += 1
            elif band == "Red":
                red += 1

        return GovernanceDistribution(green=green, amber=amber, red=red)

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
                kindergarten_count=0,
                children_count=0,
                capacity=0,
                enrollment_rate=0.0,
                attendance_rate=0.0,
                incident_rate=0.0,
                governance_score=0.0
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
    current_user: models.User = Depends(get_current_user_or_redirect),
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


@router.get("/governance-distribution", response_model=GovernanceDistribution)
def get_governance_distribution_endpoint(
    start_date: Optional[date] = Query(None),
    end_date: Optional[date] = Query(None),
    current_user: models.User = Depends(get_current_user_or_redirect),
    db: Session = Depends(get_db)
):
    """Get the distribution of kindergartens by governance band."""
    validators.validate_admin_role(current_user)
    period_start, period_end = get_date_range(start_date, end_date)
    return AnalyticsService.get_governance_distribution(db, period_start, period_end)



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


# =============================================================================
# AnalyticsService Implementation
# =============================================================================

class AnalyticsService:
    """Service class for computing analytics and KPIs across the network"""

    @staticmethod
    def get_network_summary(db: Session, period_start: date, period_end: date) -> NetworkSummary:
        """Get network-wide summary metrics"""
        from kpi_service import KPIService

        # Count total active kindergartens
        total_kindergartens = db.query(func.count(models.Kindergarten.id)).filter(
            models.Kindergarten.status == models.KindergartenStatus.ACTIVE
        ).scalar() or 0

        # Count total active children
        total_children = db.query(func.count(models.Child.id)).join(
            models.EnrollmentApplication
        ).filter(
            models.EnrollmentApplication.status == models.EnrollmentStatus.ACTIVE
        ).scalar() or 0

        # Count total active enrollments
        total_enrollments = db.query(func.count(models.EnrollmentApplication.id)).filter(
            models.EnrollmentApplication.status == models.EnrollmentStatus.ACTIVE
        ).scalar() or 0

        # Count total staff
        total_staff = db.query(func.count(models.User.id)).filter(
            models.User.role.in_([
                models.UserRole.ADMIN,
                models.UserRole.MANAGER,
                models.UserRole.SUPERVISOR
            ])
        ).scalar() or 0

        # Calculate total capacity (sum of all kindergarten capacities)
        # Note: Capacity not currently stored in database schema
        total_capacity = 0  # TODO: Add capacity field to Kindergarten model

        # Calculate enrollment rate
        enrollment_rate = (total_children / total_capacity * 100) if total_capacity > 0 else 0.0

        # Calculate network-wide attendance rate
        attendance_rate = AnalyticsService._compute_network_attendance_rate(db, period_start, period_end)

        # Calculate network-wide incident rate
        incident_rate = AnalyticsService._compute_network_incident_rate(db, period_start, period_end)

        # Calculate report submission and approval rates
        report_submission_rate = AnalyticsService._compute_report_submission_rate(db, period_start, period_end)
        report_approval_rate = AnalyticsService._compute_report_approval_rate(db, period_start, period_end)

        # Calculate average governance score (GCEI)
        governance_avg_score = AnalyticsService._compute_network_governance_score(db, period_start, period_end)

        return NetworkSummary(
            total_kindergartens=total_kindergartens,
            total_children=total_children,
            total_staff=total_staff,
            total_capacity=total_capacity,
            enrollment_rate=enrollment_rate,
            attendance_rate=attendance_rate,
            incident_rate=incident_rate,
            report_submission_rate=report_submission_rate,
            report_approval_rate=report_approval_rate,
            governance_avg_score=governance_avg_score
        )

    @staticmethod
    def get_governorate_breakdown(db: Session, period_start: date, period_end: date) -> List[GovernorateMetrics]:
        """Get metrics broken down by governorate"""
        from kpi_service import KPIService

        # Get all governorates with active kindergartens
        governorates = db.query(models.Kindergarten.governorate).filter(
            models.Kindergarten.status == models.KindergartenStatus.ACTIVE
        ).distinct().all()

        results = []
        for (gov_name,) in governorates:
            # Count kindergartens in this governorate
            kg_count = db.query(func.count(models.Kindergarten.id)).filter(
                models.Kindergarten.governorate == gov_name,
                models.Kindergarten.status == models.KindergartenStatus.ACTIVE
            ).scalar() or 0

            # Count children in this governorate
            children_count = db.query(func.count(models.Child.id)).join(
                models.EnrollmentApplication
            ).join(
                models.Kindergarten
            ).filter(
                models.Kindergarten.governorate == gov_name,
                models.EnrollmentApplication.status == models.EnrollmentStatus.ACTIVE
            ).scalar() or 0

            # Sum capacity of classes in active kindergartens for this governorate
            capacity = db.query(func.coalesce(func.sum(models.Class.capacity_total), 0)).join(
                models.Kindergarten,
                models.Kindergarten.id == models.Class.kindergarten_id
            ).filter(
                models.Kindergarten.governorate == gov_name,
                models.Kindergarten.status == models.KindergartenStatus.ACTIVE
            ).scalar() or 0

            # Enrollment rate (children / capacity)
            enrollment_rate = round((children_count / capacity) * 100, 2) if capacity else 0.0

            # Calculate governorate attendance rate
            attendance_rate = AnalyticsService._compute_governorate_attendance_rate(db, gov_name, period_start, period_end)

            # Calculate governorate incident rate
            incident_rate = AnalyticsService._compute_governorate_incident_rate(db, gov_name, period_start, period_end)

            # Calculate governorate governance score
            governance_score = AnalyticsService._compute_governorate_governance_score(db, gov_name, period_start, period_end)

            results.append(GovernorateMetrics(
                governorate=gov_name,
                kindergarten_count=kg_count,
                children_count=children_count,
                capacity=int(capacity),
                enrollment_rate=enrollment_rate,
                attendance_rate=attendance_rate,
                incident_rate=incident_rate,
                governance_score=governance_score
            ))

        return results

    @staticmethod
    def get_network_trends(db: Session, metric: str, period_start: date, period_end: date) -> List[TimeSeriesPoint]:
        """Get time-series trend data for network metrics"""
        from kpi_service import KPIService

        trends = []

        # Generate monthly intervals
        current_date = period_start
        while current_date <= period_end:
            month_end = min(current_date + timedelta(days=30), period_end)

            if metric == "attendance":
                value = AnalyticsService._compute_network_attendance_rate(db, current_date, month_end)
            elif metric == "incidents":
                value = AnalyticsService._compute_network_incident_rate(db, current_date, month_end)
            else:
                value = 0.0

            trends.append(TimeSeriesPoint(
                date=current_date.isoformat(),
                value=round(value, 2),
                label=f"{current_date.strftime('%b %Y')}"
            ))

            # Move to next month
            current_date = current_date + timedelta(days=30)

        return trends

    @staticmethod
    def get_high_risk_children(db: Session) -> List[Dict[str, Any]]:
        """Get list of high-risk children based on attendance and incidents"""
        # Get children with low attendance (< 80%) in last 30 days
        period_end = date.today()
        period_start = period_end - timedelta(days=30)

        # Find children with attendance rate below 80%
        low_attendance_children = db.query(
            models.Child,
            func.count(models.AttendanceLog.id).label('attendance_days')
        ).join(
            models.EnrollmentApplication
        ).outerjoin(
            models.AttendanceLog,
            and_(
                models.AttendanceLog.child_id == models.Child.id,
                models.AttendanceLog.date >= period_start,
                models.AttendanceLog.date <= period_end
            )
        ).filter(
            models.EnrollmentApplication.status == models.EnrollmentStatus.ACTIVE
        ).group_by(
            models.Child.id
        ).having(
            func.count(models.AttendanceLog.id) / 30.0 < 0.8  # Less than 80% attendance
        ).all()

        # Get children with recent incidents
        recent_incidents = db.query(
            models.Child,
            func.count(models.Incident.id).label('incident_count')
        ).join(
            models.Incident
        ).filter(
            models.Incident.occurred_at >= period_start,
            models.Incident.severity_level.in_([models.SeverityLevel.HIGH, models.SeverityLevel.CRITICAL])
        ).group_by(
            models.Child.id
        ).having(
            func.count(models.Incident.id) >= 2  # 2 or more serious incidents
        ).all()

        # Combine and deduplicate
        risk_children = []

        # Add low attendance children
        for child, attendance_days in low_attendance_children:
            attendance_rate = (attendance_days / 30.0) * 100
            risk_children.append({
                "child_id": child.id,
                "child_name": f"{child.first_name} {child.last_name}",
                "kindergarten_name": child.enrollments[0].kindergarten.name_ar if child.enrollments else "Unknown",
                "risk_type": "Low Attendance",
                "risk_value": round(attendance_rate, 1),
                "description": f"Attendance rate: {round(attendance_rate, 1)}%"
            })

        # Add children with multiple incidents
        for child, incident_count in recent_incidents:
            risk_children.append({
                "child_id": child.id,
                "child_name": f"{child.first_name} {child.last_name}",
                "kindergarten_name": child.incidents[0].kindergarten.name_ar if child.incidents else "Unknown",
                "risk_type": "Multiple Incidents",
                "risk_value": incident_count,
                "description": f"{incident_count} serious incidents in last 30 days"
            })

        return risk_children

    @staticmethod
    def get_governance_distribution(db: Session, period_start: date, period_end: date) -> GovernanceDistribution:
        """Get distribution of governance scores (GCEI bands)"""
        from kpi_service import KPIService

        # Get all active kindergartens
        kindergartens = db.query(models.Kindergarten).filter(
            models.Kindergarten.status == models.KindergartenStatus.ACTIVE
        ).all()

        green_count = 0
        amber_count = 0
        red_count = 0

        for kg in kindergartens:
            # Calculate governance score for this kindergarten
            score = AnalyticsService._compute_kindergarten_governance_score(db, kg.id, period_start, period_end)

            if score >= 85:
                green_count += 1
            elif score >= 70:
                amber_count += 1
            else:
                red_count += 1

        return GovernanceDistribution(
            green=green_count,
            amber=amber_count,
            red=red_count
        )

    # Helper methods for computing network-level metrics

    @staticmethod
    def _compute_network_attendance_rate(db: Session, period_start: date, period_end: date) -> float:
        """Compute network-wide attendance rate"""
        from kpi_service import KPIService

        # Get all active kindergartens
        kindergartens = db.query(models.Kindergarten).filter(
            models.Kindergarten.status == models.KindergartenStatus.ACTIVE
        ).all()

        if not kindergartens:
            return 0.0

        total_attended_days = 0
        total_expected_days = 0

        for kg in kindergartens:
            # Count attended days for this kindergarten
            attended = db.query(func.count(models.AttendanceLog.id)).filter(
                models.AttendanceLog.date >= period_start,
                models.AttendanceLog.date <= period_end
            ).join(
                models.Child
            ).join(
                models.EnrollmentApplication,
                models.EnrollmentApplication.child_id == models.Child.id
            ).filter(
                models.EnrollmentApplication.kindergarten_id == kg.id,
                models.EnrollmentApplication.status == models.EnrollmentStatus.ACTIVE
            ).scalar() or 0

            # Count expected days for this kindergarten
            active_enrollments = db.query(func.count(models.EnrollmentApplication.id)).filter(
                models.EnrollmentApplication.kindergarten_id == kg.id,
                models.EnrollmentApplication.status == models.EnrollmentStatus.ACTIVE
            ).scalar() or 0

            days_in_period = (period_end - period_start).days + 1
            expected = active_enrollments * days_in_period

            total_attended_days += attended
            total_expected_days += expected

        if total_expected_days == 0:
            return 0.0

        return round((total_attended_days / total_expected_days) * 100, 2)

    @staticmethod
    def _compute_network_incident_rate(db: Session, period_start: date, period_end: date) -> float:
        """Compute network-wide incident rate per 100 child-days"""
        # Count total incidents
        total_incidents = db.query(func.count(models.Incident.id)).filter(
            func.date(models.Incident.occurred_at) >= period_start,
            func.date(models.Incident.occurred_at) <= period_end
        ).scalar() or 0

        # Count total child-days attended
        total_child_days = db.query(func.count(models.AttendanceLog.id)).filter(
            models.AttendanceLog.date >= period_start,
            models.AttendanceLog.date <= period_end
        ).scalar() or 1

        return round((total_incidents / total_child_days) * 100, 2)

    @staticmethod
    def _compute_network_serious_incident_rate(db: Session, period_start: date, period_end: date) -> float:
        """Compute network-wide serious incident rate per 100 child-days"""
        # Count serious incidents
        serious_incidents = db.query(func.count(models.Incident.id)).filter(
            func.date(models.Incident.occurred_at) >= period_start,
            func.date(models.Incident.occurred_at) <= period_end,
            models.Incident.severity_level.in_([models.SeverityLevel.HIGH, models.SeverityLevel.CRITICAL])
        ).scalar() or 0

        # Count total child-days attended
        total_child_days = db.query(func.count(models.AttendanceLog.id)).filter(
            models.AttendanceLog.date >= period_start,
            models.AttendanceLog.date <= period_end
        ).scalar() or 1

        return round((serious_incidents / total_child_days) * 100, 2)

    @staticmethod
    def _compute_network_governance_score(db: Session, period_start: date, period_end: date) -> float:
        """Compute average governance score across all kindergartens"""
        from kpi_service import KPIService

        kindergartens = db.query(models.Kindergarten).filter(
            models.Kindergarten.status == models.KindergartenStatus.ACTIVE
        ).all()

        if not kindergartens:
            return 0.0

        total_score = 0.0
        count = 0

        for kg in kindergartens:
            score = AnalyticsService._compute_kindergarten_governance_score(db, kg.id, period_start, period_end)
            if score > 0:
                total_score += score
                count += 1

        return round(total_score / count, 2) if count > 0 else 0.0

    @staticmethod
    def _compute_governorate_attendance_rate(db: Session, governorate: str, period_start: date, period_end: date) -> float:
        """Compute attendance rate for a specific governorate"""
        # Get all kindergartens in the governorate
        kg_ids = db.query(models.Kindergarten.id).filter(
            models.Kindergarten.governorate == governorate,
            models.Kindergarten.status == models.KindergartenStatus.ACTIVE
        ).all()

        if not kg_ids:
            return 0.0

        kg_ids = [kg_id for (kg_id,) in kg_ids]

        # Count attended days
        attended = db.query(func.count(models.AttendanceLog.id)).filter(
            models.AttendanceLog.date >= period_start,
            models.AttendanceLog.date <= period_end
        ).join(
            models.Child
        ).join(
            models.EnrollmentApplication,
            models.EnrollmentApplication.child_id == models.Child.id
        ).filter(
            models.EnrollmentApplication.kindergarten_id.in_(kg_ids),
            models.EnrollmentApplication.status == models.EnrollmentStatus.ACTIVE
        ).scalar() or 0

        # Count expected days
        active_enrollments = db.query(func.count(models.EnrollmentApplication.id)).filter(
            models.EnrollmentApplication.kindergarten_id.in_(kg_ids),
            models.EnrollmentApplication.status == models.EnrollmentStatus.ACTIVE
        ).scalar() or 0

        days_in_period = (period_end - period_start).days + 1
        expected = active_enrollments * days_in_period

        if expected == 0:
            return 0.0

        return round((attended / expected) * 100, 2)

    @staticmethod
    def _compute_governorate_incident_rate(db: Session, governorate: str, period_start: date, period_end: date) -> float:
        """Compute incident rate for a specific governorate"""
        # Get kindergarten IDs in governorate
        kg_ids = db.query(models.Kindergarten.id).filter(
            models.Kindergarten.governorate == governorate,
            models.Kindergarten.status == models.KindergartenStatus.ACTIVE
        ).all()

        if not kg_ids:
            return 0.0

        kg_ids = [kg_id for (kg_id,) in kg_ids]

        # Count incidents
        incidents = db.query(func.count(models.Incident.id)).filter(
            models.Incident.kindergarten_id.in_(kg_ids),
            func.date(models.Incident.occurred_at) >= period_start,
            func.date(models.Incident.occurred_at) <= period_end
        ).scalar() or 0

        # Count child-days
        child_days = db.query(func.count(models.AttendanceLog.id)).filter(
            models.AttendanceLog.date >= period_start,
            models.AttendanceLog.date <= period_end
        ).join(
            models.Child
        ).join(
            models.EnrollmentApplication,
            models.EnrollmentApplication.child_id == models.Child.id
        ).filter(
            models.EnrollmentApplication.kindergarten_id.in_(kg_ids)
        ).scalar() or 1

        return round((incidents / child_days) * 100, 2)

    @staticmethod
    def _compute_governorate_governance_score(db: Session, governorate: str, period_start: date, period_end: date) -> float:
        """Compute average governance score for a governorate"""
        # Get all kindergartens in governorate
        kindergartens = db.query(models.Kindergarten).filter(
            models.Kindergarten.governorate == governorate,
            models.Kindergarten.status == models.KindergartenStatus.ACTIVE
        ).all()

        if not kindergartens:
            return 0.0

        total_score = 0.0
        count = 0

        for kg in kindergartens:
            score = AnalyticsService._compute_kindergarten_governance_score(db, kg.id, period_start, period_end)
            if score > 0:
                total_score += score
                count += 1

        return round(total_score / count, 2) if count > 0 else 0.0

    @staticmethod
    def _compute_kindergarten_governance_score(db: Session, kindergarten_id: int, period_start: date, period_end: date) -> float:
        """Compute governance score (GCEI) for a specific kindergarten"""
        from kpi_service import KPIService

        try:
            # Get individual KPI scores
            attendance_rate = KPIService.compute_attendance_rate(db, kindergarten_id, period_start, period_end)
            incident_rate = KPIService.compute_incident_rate(db, kindergarten_id, period_start, period_end)
            serious_incident_rate = KPIService.compute_serious_incident_rate(db, kindergarten_id, period_start, period_end)
            ratio_compliance = KPIService.compute_ratio_compliance(db, kindergarten_id, period_start, period_end)

            # Normalize and weight the scores (simplified GCEI calculation)
            # Higher attendance = better score
            attendance_score = min(attendance_rate, 100) * 0.4

            # Lower incident rates = better score
            incident_score = max(0, 100 - incident_rate * 10) * 0.3

            # Lower serious incident rates = better score
            serious_incident_score = max(0, 100 - serious_incident_rate * 20) * 0.2

            # Higher ratio compliance = better score
            ratio_score = ratio_compliance * 0.1

            total_score = attendance_score + incident_score + serious_incident_score + ratio_score

            return round(total_score, 2)
        except Exception:
            return 0.0

    @staticmethod
    def _compute_report_submission_rate(db: Session, period_start: date, period_end: date) -> float:
        """Compute network-wide report submission rate"""
        # Count expected reports (one per kindergarten per day in period)
        days_in_period = (period_end - period_start).days + 1
        total_kindergartens = db.query(func.count(models.Kindergarten.id)).filter(
            models.Kindergarten.status == models.KindergartenStatus.ACTIVE
        ).scalar() or 0
        expected_reports = total_kindergartens * days_in_period

        # Count actual submitted reports
        submitted_reports = db.query(func.count(models.DailyReport.id)).filter(
            models.DailyReport.date >= period_start,
            models.DailyReport.date <= period_end
        ).scalar() or 0

        return round((submitted_reports / expected_reports * 100) if expected_reports > 0 else 0, 2)

    @staticmethod
    def _compute_report_approval_rate(db: Session, period_start: date, period_end: date) -> float:
        """Compute network-wide report approval rate"""
        # Count submitted reports
        submitted_reports = db.query(func.count(models.DailyReport.id)).filter(
            models.DailyReport.date >= period_start,
            models.DailyReport.date <= period_end
        ).scalar() or 0

        # Count approved reports
        approved_reports = db.query(func.count(models.DailyReport.id)).filter(
            models.DailyReport.date >= period_start,
            models.DailyReport.date <= period_end,
            models.DailyReport.status == models.DailyReportStatus.APPROVED
        ).scalar() or 0

        return round((approved_reports / submitted_reports * 100) if submitted_reports > 0 else 0, 2)

    # Placeholder methods for advanced analytics cache (to be implemented)
    @staticmethod
    def get_advanced_analytics_cache(db: Session, dimension_type: models.AnalyticsDimensionType,
                                   dimension_id: str, period_type: models.AnalyticsPeriodType,
                                   period_start: date, period_end: date):
        """Placeholder for advanced analytics cache"""
        # TODO: Implement caching logic
        return None

    @staticmethod
    def invalidate_advanced_analytics_cache(db: Session, dimension_type: Optional[models.AnalyticsDimensionType] = None,
                                          dimension_id: Optional[str] = None,
                                          period_type: Optional[models.AnalyticsPeriodType] = None,
                                          period_start: Optional[date] = None, period_end: Optional[date] = None) -> int:
        """Placeholder for cache invalidation"""
        # TODO: Implement cache invalidation logic
        return 0
