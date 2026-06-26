from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session
from typing import List, Dict, Any, Optional
from database import get_db
import models
from admin_security import require_admin
import json

router = APIRouter(prefix="/api/analytics", tags=["Advanced Analytics"])

@router.get("/predictive")
def get_predictive_insights(
    dimension_type: str = Query("NETWORK"),
    dimension_id: str = Query("JORDAN"),
    db: Session = Depends(get_db),
    current_user: models.User = Depends(require_admin)
):
    """Fetch advanced predictive indicators & correlations for a given dimension."""
    adv = db.query(models.AdvancedAnalyticsCache).filter(
        models.AdvancedAnalyticsCache.dimension_type == models.AnalyticsDimensionType(dimension_type),
        models.AdvancedAnalyticsCache.dimension_id == dimension_id
    ).order_by(models.AdvancedAnalyticsCache.period_start.desc()).first()

    if not adv:
        raise HTTPException(status_code=404, detail="No advanced analytics found for this dimension.")

    # Convert to standard dictionary
    return {
        "attendance_trend_slope": adv.attendance_trend_slope,
        "staffing_quality_correlation": adv.staffing_quality_correlation,
        "risk_score": adv.risk_score,
        "incident_rate_per_100": adv.incident_rate_per_100,
        "attendance_rate": adv.attendance_rate
    }

@router.get("/compare")
def compare_dimensions(
    dim1_type: str = Query(...),
    dim1_id: str = Query(...),
    dim2_type: str = Query(...),
    dim2_id: str = Query(...),
    db: Session = Depends(get_db),
    current_user: models.User = Depends(require_admin)
):
    """Compare two levels (e.g., Amman vs Jordan Overall). Returns radar chart data."""
    def get_latest_cache(dtype, did):
        return db.query(models.AnalyticsDimensionCache).filter(
            models.AnalyticsDimensionCache.dimension_type == models.AnalyticsDimensionType(dtype),
            models.AnalyticsDimensionCache.dimension_id == did
        ).order_by(models.AnalyticsDimensionCache.period_date.desc()).first()

    d1 = get_latest_cache(dim1_type, dim1_id)
    d2 = get_latest_cache(dim2_type, dim2_id)

    if not d1 or not d2:
        raise HTTPException(status_code=404, detail="Missing data for one or both dimensions.")

    return {
        "dim1": {
            "name": dim1_id,
            "attendance": d1.attendance_rate or 0,
            "governance": d1.final_governance_score or 0,
            "enrollment": d1.enrollment_rate or 0,
            "safety": 100 - (d1.incident_rate_per_100 or 0)*5, # Normalized safety score
            "capacity": min(100, (d1.total_capacity or 100)) # Placeholder
        },
        "dim2": {
            "name": dim2_id,
            "attendance": d2.attendance_rate or 0,
            "governance": d2.final_governance_score or 0,
            "enrollment": d2.enrollment_rate or 0,
            "safety": 100 - (d2.incident_rate_per_100 or 0)*5,
            "capacity": min(100, (d2.total_capacity or 100))
        }
    }

@router.get("/list-dimensions")
def list_dimensions(
    dimension_type: str = Query(...),
    db: Session = Depends(get_db),
    current_user: models.User = Depends(require_admin)
):
    """List available IDs for a specific dimension type (e.g. all Governorates)."""
    results = db.query(models.AnalyticsDimensionCache.dimension_id).filter(
        models.AnalyticsDimensionCache.dimension_type == models.AnalyticsDimensionType(dimension_type)
    ).distinct().all()
    
    return [r[0] for r in results]
