"""
Analytics observability API endpoints.
Provides alert quality, data quality, and system observability metrics.
"""
from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.orm import Session
from typing import Any, Dict, Optional

from database import get_db
from dependencies import get_current_user, require_admin
from models import User, UserRole
from alert_quality_service import alert_quality_service
from data_quality_enhanced import enhanced_data_quality_service
from staff_equity_service import staff_equity_service
from governance_quality_service import governance_quality_service
from enrollment_analytics_service import enrollment_analytics_service
from correlation_engine import correlation_engine
from performance_monitor import performance_monitor
from cache_service import dashboard_cache

router = APIRouter(prefix="/api/observability", tags=["Observability"])


@router.get("/alert-quality")
async def get_alert_quality(
    days: int = 30,
    kindergarten_id: Optional[int] = None,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    if current_user.role not in (UserRole.ADMIN, UserRole.MANAGER):
        raise HTTPException(status_code=403, detail="Admin or Manager role required")
    return alert_quality_service.overall_alert_quality(db, kindergarten_id=kindergarten_id)


@router.get("/data-quality")
async def get_data_quality(
    kindergarten_id: Optional[int] = None,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    if current_user.role not in (UserRole.ADMIN, UserRole.MANAGER):
        raise HTTPException(status_code=403, detail="Admin or Manager role required")
    return enhanced_data_quality_service.compute_overall_quality(db, kindergarten_id=kindergarten_id)


@router.get("/data-quality/freshness")
async def get_data_freshness(
    kindergarten_id: Optional[int] = None,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    if current_user.role not in (UserRole.ADMIN, UserRole.MANAGER):
        raise HTTPException(status_code=403, detail="Admin or Manager role required")
    return enhanced_data_quality_service.freshness_latency(db, kindergarten_id=kindergarten_id)


@router.get("/data-quality/completeness")
async def get_data_completeness(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    if current_user.role != UserRole.ADMIN:
        raise HTTPException(status_code=403, detail="Admin role required")
    return enhanced_data_quality_service.completeness_per_kg(db)


@router.get("/data-quality/consistency")
async def get_data_consistency(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    if current_user.role != UserRole.ADMIN:
        raise HTTPException(status_code=403, detail="Admin role required")
    return enhanced_data_quality_service.cross_entity_consistency(db)


@router.get("/data-quality/uniqueness")
async def get_data_uniqueness(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    if current_user.role != UserRole.ADMIN:
        raise HTTPException(status_code=403, detail="Admin role required")
    return enhanced_data_quality_service.uniqueness_check(db)


@router.get("/data-quality/validity")
async def get_data_validity(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    if current_user.role != UserRole.ADMIN:
        raise HTTPException(status_code=403, detail="Admin role required")
    return enhanced_data_quality_service.validity_check(db)


@router.get("/latency")
async def get_latency_metrics(
    current_user: User = Depends(get_current_user),
):
    if current_user.role not in (UserRole.ADMIN, UserRole.MANAGER):
        raise HTTPException(status_code=403, detail="Admin or Manager role required")
    collector = performance_monitor.collector
    return {
        "overall": {
            "p50_ms": collector.get_percentile(50),
            "p95_ms": collector.get_percentile(95),
            "p99_ms": collector.get_percentile(99),
            "total_requests": collector.request_count,
            "error_count": collector.error_count,
            "error_rate": round((collector.error_count / max(collector.request_count, 1)) * 100, 2),
        },
        "per_endpoint_p95": collector.get_endpoint_p95(),
    }


@router.get("/cache")
async def get_cache_metrics(
    current_user: User = Depends(get_current_user),
):
    if current_user.role not in (UserRole.ADMIN, UserRole.MANAGER):
        raise HTTPException(status_code=403, detail="Admin or Manager role required")
    stats = dashboard_cache.get_stats()
    return {
        "hit_rate": round(stats.get("hit_rate", 0), 1),
        "hits": stats.get("cache_hits", 0),
        "misses": stats.get("cache_misses", 0),
        "sets": stats.get("cache_sets", 0),
        "memory_entries": stats.get("memory_entries", 0),
        "redis_available": stats.get("redis_available", False),
        "redis_entries": stats.get("redis_entries", 0),
    }


@router.get("/summary")
async def get_observability_summary(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    if current_user.role not in (UserRole.ADMIN, UserRole.MANAGER):
        raise HTTPException(status_code=403, detail="Admin or Manager role required")

    collector = performance_monitor.collector
    alert_quality = alert_quality_service.overall_alert_quality(db)
    data_quality = enhanced_data_quality_service.compute_overall_quality(db)
    cache_stats = dashboard_cache.get_stats()

    return {
        "backend": {
            "p95_ms": collector.get_percentile(95),
            "error_rate": round((collector.error_count / max(collector.request_count, 1)) * 100, 2),
            "total_requests": collector.request_count,
        },
        "cache": {
            "hit_rate": round(cache_stats.get("hit_rate", 0), 1),
            "redis_available": cache_stats.get("redis_available", False),
        },
        "alerts": {
            "health": alert_quality.get("health", "unknown"),
            "signal_to_noise": alert_quality.get("signal_to_noise", {}).get("snr"),
        },
        "data_quality": {
            "overall_score": data_quality.get("overall_score"),
            "status": data_quality.get("status"),
        },
    }


# =============================================================================
# Wave 2: Staff Equity Metrics
# =============================================================================

@router.get("/staff-equity")
async def get_staff_equity(
    kindergarten_id: Optional[int] = None,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Overall staff equity metrics including Gini coefficient, workload balance, overtime."""
    if current_user.role not in (UserRole.ADMIN, UserRole.MANAGER):
        raise HTTPException(status_code=403, detail="Admin or Manager role required")
    return staff_equity_service.overall_staff_equity(db, kindergarten_id=kindergarten_id)


@router.get("/staff-equity/gini")
async def get_staff_gini(
    kindergarten_id: Optional[int] = None,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Teacher workload Gini coefficient — workload equity across classes."""
    if current_user.role not in (UserRole.ADMIN, UserRole.MANAGER):
        raise HTTPException(status_code=403, detail="Admin or Manager role required")
    return staff_equity_service.teacher_workload_gini(db, kindergarten_id=kindergarten_id)


@router.get("/staff-equity/overtime")
async def get_staff_overtime(
    kindergarten_id: Optional[int] = None,
    days: int = 30,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Staff overtime tracking — welfare and compliance monitoring."""
    if current_user.role not in (UserRole.ADMIN, UserRole.MANAGER):
        raise HTTPException(status_code=403, detail="Admin or Manager role required")
    return staff_equity_service.overtime_tracking(db, kindergarten_id=kindergarten_id, days=days)


# =============================================================================
# Wave 2: Governance Quality Metrics
# =============================================================================

@router.get("/governance-quality")
async def get_governance_quality(
    kindergarten_id: Optional[int] = None,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Overall governance quality — report rejection, first-pass approval, timing, morning routine."""
    if current_user.role not in (UserRole.ADMIN, UserRole.MANAGER):
        raise HTTPException(status_code=403, detail="Admin or Manager role required")
    return governance_quality_service.overall_governance_quality(db, kindergarten_id=kindergarten_id)


@router.get("/governance-quality/rejection-rate")
async def get_rejection_rate(
    kindergarten_id: Optional[int] = None,
    days: int = 30,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Daily report rejection rate — supervision quality signal."""
    if current_user.role not in (UserRole.ADMIN, UserRole.MANAGER):
        raise HTTPException(status_code=403, detail="Admin or Manager role required")
    return governance_quality_service.report_rejection_rate(db, kindergarten_id=kindergarten_id, days=days)


@router.get("/governance-quality/first-pass")
async def get_first_pass_approval(
    kindergarten_id: Optional[int] = None,
    days: int = 30,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """First-pass approval rate — report quality signal."""
    if current_user.role not in (UserRole.ADMIN, UserRole.MANAGER):
        raise HTTPException(status_code=403, detail="Admin or Manager role required")
    return governance_quality_service.first_pass_approval_rate(db, kindergarten_id=kindergarten_id, days=days)


@router.get("/governance-quality/submission-timing")
async def get_submission_timing(
    kindergarten_id: Optional[int] = None,
    days: int = 7,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Report submission time distribution — workflow pattern analysis."""
    if current_user.role not in (UserRole.ADMIN, UserRole.MANAGER):
        raise HTTPException(status_code=403, detail="Admin or Manager role required")
    return governance_quality_service.submission_timing_distribution(db, kindergarten_id=kindergarten_id, days=days)


@router.get("/governance-quality/morning-routine")
async def get_morning_routine(
    kindergarten_id: Optional[int] = None,
    days: int = 7,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Morning routine completion rate — operational readiness before 10 AM."""
    if current_user.role not in (UserRole.ADMIN, UserRole.MANAGER):
        raise HTTPException(status_code=403, detail="Admin or Manager role required")
    return governance_quality_service.morning_routine_completion(db, kindergarten_id=kindergarten_id, days=days)


# =============================================================================
# Wave 2: Enrollment Analytics
# =============================================================================

@router.get("/enrollment")
async def get_enrollment_analytics(
    kindergarten_id: Optional[int] = None,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Overall enrollment analytics — funnel, turnaround, waitlist conversion."""
    if current_user.role not in (UserRole.ADMIN, UserRole.MANAGER):
        raise HTTPException(status_code=403, detail="Admin or Manager role required")
    return enrollment_analytics_service.overall_enrollment_analytics(db, kindergarten_id=kindergarten_id)


@router.get("/enrollment/funnel")
async def get_enrollment_funnel(
    kindergarten_id: Optional[int] = None,
    days: int = 30,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Enrollment funnel — stage-by-stage drop-off rates."""
    if current_user.role not in (UserRole.ADMIN, UserRole.MANAGER):
        raise HTTPException(status_code=403, detail="Admin or Manager role required")
    return enrollment_analytics_service.enrollment_funnel(db, kindergarten_id=kindergarten_id, days=days)


@router.get("/enrollment/turnaround")
async def get_enrollment_turnaround(
    kindergarten_id: Optional[int] = None,
    days: int = 30,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Enrollment turnaround — time from application to acceptance/rejection."""
    if current_user.role not in (UserRole.ADMIN, UserRole.MANAGER):
        raise HTTPException(status_code=403, detail="Admin or Manager role required")
    return enrollment_analytics_service.enrollment_turnaround(db, kindergarten_id=kindergarten_id, days=days)


@router.get("/enrollment/waitlist")
async def get_enrollment_waitlist(
    kindergarten_id: Optional[int] = None,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Waitlist conversion rate — how many offered waitlist entries are accepted."""
    if current_user.role not in (UserRole.ADMIN, UserRole.MANAGER):
        raise HTTPException(status_code=403, detail="Admin or Manager role required")
    return enrollment_analytics_service.waitlist_conversion_rate(db, kindergarten_id=kindergarten_id)


# =============================================================================
# Wave 2: Correlation Discovery Engine
# =============================================================================

@router.get("/correlations")
async def get_correlations(
    days: int = 90,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Automated pairwise correlation scan across all key metrics."""
    if current_user.role != UserRole.ADMIN:
        raise HTTPException(status_code=403, detail="Admin role required")
    return correlation_engine.discover_correlations(db, days=days)


# =============================================================================
# Wave 3: Parent Engagement
# =============================================================================

@router.get("/parent-engagement")
async def get_parent_engagement(
    kindergarten_id: Optional[int] = None,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Overall parent engagement — report view rate, login frequency, NPS."""
    if current_user.role not in (UserRole.ADMIN, UserRole.MANAGER):
        raise HTTPException(status_code=403, detail="Admin or Manager role required")
    from parent_engagement_service import parent_engagement_service
    return parent_engagement_service.overall_parent_engagement(db, kindergarten_id=kindergarten_id)


@router.get("/parent-engagement/report-views")
async def get_report_view_rate(
    kindergarten_id: Optional[int] = None,
    days: int = 30,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Daily report view rate — notification-to-action conversion."""
    if current_user.role not in (UserRole.ADMIN, UserRole.MANAGER):
        raise HTTPException(status_code=403, detail="Admin or Manager role required")
    from parent_engagement_service import parent_engagement_service
    return parent_engagement_service.report_view_rate(db, kindergarten_id=kindergarten_id, days=days)


@router.get("/parent-engagement/nps")
async def get_parent_nps(
    kindergarten_id: Optional[int] = None,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Parent NPS score — satisfaction trajectory."""
    if current_user.role not in (UserRole.ADMIN, UserRole.MANAGER):
        raise HTTPException(status_code=403, detail="Admin or Manager role required")
    from parent_engagement_service import parent_engagement_service
    return parent_engagement_service.nps_score(db, kindergarten_id=kindergarten_id)


# =============================================================================
# Wave 3: Predictive Analytics
# =============================================================================

@router.get("/predictive/attendance-volatility")
async def get_attendance_volatility(
    kindergarten_id: Optional[int] = None,
    window_days: int = 7,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Attendance volatility index per KG — early warning for declining KGs."""
    if current_user.role not in (UserRole.ADMIN, UserRole.MANAGER):
        raise HTTPException(status_code=403, detail="Admin or Manager role required")
    from predictive_service import predictive_analytics_service
    return predictive_analytics_service.attendance_volatility_index(
        db, kindergarten_id=kindergarten_id, window_days=window_days,
    )


@router.get("/predictive/capacity-runway")
async def get_capacity_runway(
    kindergarten_id: Optional[int] = None,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Capacity runway — months until 100% occupancy at current enrollment rate."""
    if current_user.role not in (UserRole.ADMIN, UserRole.MANAGER):
        raise HTTPException(status_code=403, detail="Admin or Manager role required")
    from predictive_service import predictive_analytics_service
    return predictive_analytics_service.capacity_runway(db, kindergarten_id=kindergarten_id)


@router.get("/predictive/enrollment-projection")
async def get_enrollment_projection(
    kindergarten_id: int,
    months: int = 6,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Enrollment projection — forecast enrollment for next N months."""
    if current_user.role not in (UserRole.ADMIN, UserRole.MANAGER):
        raise HTTPException(status_code=403, detail="Admin or Manager role required")
    from predictive_service import predictive_analytics_service
    return predictive_analytics_service.enrollment_projection(
        db, kindergarten_id=kindergarten_id, months_ahead=months,
    )
