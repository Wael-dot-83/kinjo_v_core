from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session
from sqlalchemy import func
from typing import List, Dict, Any, Optional
from database import get_db
import models
import math
from admin_security import require_admin
import json
from data_science.report_generator import generate_government_report
from utils.time_utils import today_amman as _today

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
    """Compare two levels. Returns radar chart data."""
    def get_latest_cache(dtype, did):
        return db.query(models.AnalyticsDimensionCache).filter(
            models.AnalyticsDimensionCache.dimension_type == models.AnalyticsDimensionType(dtype),
            models.AnalyticsDimensionCache.dimension_id == did
        ).order_by(models.AnalyticsDimensionCache.period_date.desc()).first()

    d1 = get_latest_cache(dim1_type, dim1_id)
    d2 = get_latest_cache(dim2_type, dim2_id)

    if not d1 or not d2:
        raise HTTPException(status_code=404, detail="Missing data for one or both dimensions.")
        
    # Calculate Network-wide Mean and Standard Deviation for Z-Score Standardization
    # This enables true statistical comparison "standardized for all aspects"
    network_stats = db.query(
        func.avg(models.AnalyticsDimensionCache.final_governance_score).label("gov_mean"),
        func.stddev(models.AnalyticsDimensionCache.final_governance_score).label("gov_std"),
        func.avg(models.AnalyticsDimensionCache.attendance_rate).label("att_mean"),
        func.stddev(models.AnalyticsDimensionCache.attendance_rate).label("att_std")
    ).filter(
        models.AnalyticsDimensionCache.dimension_type == models.AnalyticsDimensionType.KINDERGARTEN
    ).first()
    
    # Fallback to math if SQLite doesn't support stddev
    if network_stats.gov_std is None:
        all_kgs = db.query(models.AnalyticsDimensionCache).filter(models.AnalyticsDimensionCache.dimension_type == models.AnalyticsDimensionType.KINDERGARTEN).all()
        n = len(all_kgs)
        if n > 1:
            gov_mean = sum((k.final_governance_score or 0) for k in all_kgs) / n
            gov_std = math.sqrt(sum(((k.final_governance_score or 0) - gov_mean)**2 for k in all_kgs) / (n - 1))
            att_mean = sum((k.attendance_rate or 0) for k in all_kgs) / n
            att_std = math.sqrt(sum(((k.attendance_rate or 0) - att_mean)**2 for k in all_kgs) / (n - 1))
        else:
            gov_mean, gov_std, att_mean, att_std = 0, 1, 0, 1
    else:
        gov_mean = network_stats.gov_mean or 0
        gov_std = network_stats.gov_std or 1
        att_mean = network_stats.att_mean or 0
        att_std = network_stats.att_std or 1
        
    def z_score(val, mean, std):
        if not std or std == 0: return 0.0
        return round((val - mean) / std, 2)

    return {
        "dim1": {
            "name": dim1_id,
            "attendance": d1.attendance_rate or 0,
            "governance": d1.final_governance_score or 0,
            "enrollment": d1.enrollment_rate or 0,
            "safety": 100 - (d1.incident_rate_per_100 or 0)*5, 
            "capacity": min(100, (d1.total_capacity or 100)),
            "z_scores": {
                "governance": z_score((d1.final_governance_score or 0), gov_mean, gov_std),
                "attendance": z_score((d1.attendance_rate or 0), att_mean, att_std)
            }
        },
        "dim2": {
            "name": dim2_id,
            "attendance": d2.attendance_rate or 0,
            "governance": d2.final_governance_score or 0,
            "enrollment": d2.enrollment_rate or 0,
            "safety": 100 - (d2.incident_rate_per_100 or 0)*5,
            "capacity": min(100, (d2.total_capacity or 100)),
            "z_scores": {
                "governance": z_score((d2.final_governance_score or 0), gov_mean, gov_std),
                "attendance": z_score((d2.attendance_rate or 0), att_mean, att_std)
            }
        }
    }

@router.get("/list-dimensions")
def list_dimensions(
    dimension_type: str = Query(...),
    db: Session = Depends(get_db),
    current_user: models.User = Depends(require_admin)
):
    """List available IDs for a specific dimension type."""
    results = db.query(models.AnalyticsDimensionCache.dimension_id).filter(
        models.AnalyticsDimensionCache.dimension_type == models.AnalyticsDimensionType(dimension_type)
    ).distinct().all()
    
    return [r[0] for r in results]

@router.get("/scatter")
def scatter_plot_data(
    dim_type: str = Query(...),
    dim_id: str = Query(...),
    db: Session = Depends(get_db),
    current_user: models.User = Depends(require_admin)
):
    """Fetches scatter plot data (Governance vs Attendance) for anomaly detection.
       If Network, plots all Govs. If Gov, plots all Cities. If City, plots all KGs."""
    
    target_type = models.AnalyticsDimensionType.KINDERGARTEN
    if dim_type == "NETWORK":
        target_type = models.AnalyticsDimensionType.GOVERNORATE
    elif dim_type == "GOVERNORATE":
        target_type = models.AnalyticsDimensionType.DISTRICT
    
    # Query the target dimensions. For simplicity, we just query recent caches
    # where the dimension ID starts with the dim_id (since we constructed City IDs as "Gov_City").
    query = db.query(models.AnalyticsDimensionCache).filter(
        models.AnalyticsDimensionCache.dimension_type == target_type
    )
    
    if dim_type == "GOVERNORATE":
        query = query.filter(models.AnalyticsDimensionCache.dimension_id.like(f"{dim_id}_%"))
    elif dim_type == "CITY":
        # For City -> KG, we need a join. But since we lack direct parent IDs in cache,
        # we just plot all KGs for now as a statistical sample.
        pass
    elif dim_type in ["JORDAN", "NETWORK"]:
        pass # No additional filter for national level

    results = query.order_by(models.AnalyticsDimensionCache.period_date.desc()).limit(100).all()

    points = []
    for r in results:
        points.append({
            "x": r.final_governance_score or 0,
            "y": r.attendance_rate or 0,
            "name": r.dimension_id
        })
    return points

@router.get("/demographics")
def get_demographics(
    dim_type: str = Query(...),
    dim_id: str = Query(...),
    db: Session = Depends(get_db),
    current_user: models.User = Depends(require_admin)
):
    """Fetches Demographic & Density Distributions (Age, Gender, KG Sizes)."""
    from datetime import date
    today = _today()

    # Join Child -> Enrollment -> Kindergarten
    query = db.query(
        models.Child.date_of_birth,
        models.Child.gender,
        models.Kindergarten.id.label("kg_id")
    ).join(
        models.EnrollmentApplication,
        models.Child.id == models.EnrollmentApplication.child_id
    ).join(
        models.Kindergarten,
        models.EnrollmentApplication.kindergarten_id == models.Kindergarten.id
    ).filter(
        models.EnrollmentApplication.status.in_([
            models.EnrollmentStatus.ACTIVE, 
            models.EnrollmentStatus.ACCEPTED
        ])
    )

    if dim_type == "GOVERNORATE":
        query = query.filter(models.Kindergarten.governorate == dim_id)
    elif dim_type == "CITY":
        # dim_id might be "Amman_Amman" or just "Amman". We'll use like or split.
        district_name = dim_id.split("_")[-1] if "_" in dim_id else dim_id
        query = query.filter(models.Kindergarten.district == district_name)
    elif dim_type == "KINDERGARTEN":
        query = query.filter(models.Kindergarten.id == dim_id)
    elif dim_type == "CLASS":
        # Need to join class but since we don't have it in the SELECT, just filter by it
        query = query.filter(models.EnrollmentApplication.class_id == dim_id)
    elif dim_type in ["JORDAN", "NETWORK"]:
        pass

    results = query.all()

    # Process distributions in memory (fast enough for 10-50k rows)
    gender_counts = {"MALE": 0, "FEMALE": 0}
    age_bands = {
        "1 day to 3 months": 0,
        "3 to 6 months": 0,
        "6 to 9 months": 0,
        "9 to 12 months": 0,
        "12 to 15 months": 0,
        "15 to 18 months": 0,
        "18 to 21 months": 0,
        "21 to 24 months": 0,
        "24 to 27 months": 0,
        "27 to 30 months": 0,
        "30 to 33 months": 0,
        "33 to 36 months": 0,
        "36 to 39 months": 0,
        "39 to 42 months": 0,
        "42 to 45 months": 0,
        "45 to 48 months": 0,
        "48 to 51 months": 0,
        "51 to 54 months": 0,
        "54 to 57 months": 0
    }
    data_quality = {
        "missing_dob": 0,
        "invalid_age": 0,
        "missing_gender": 0
    }
    kg_density = {}

    for dob, gender, kg_id in results:
        # Gender
        if not gender:
            data_quality["missing_gender"] += 1
        else:
            gender_counts[gender.value] += 1
        
        # Density
        kg_density[kg_id] = kg_density.get(kg_id, 0) + 1
        
        # Age
        if not dob:
            data_quality["missing_dob"] += 1
        else:
            age_days = (today - dob).days
            age_months = age_days / 30.4375  # approximate months
            
            if age_days < 1 or age_months > 57:
                data_quality["invalid_age"] += 1
            else:
                if age_months < 3: age_bands["1 day to 3 months"] += 1
                elif age_months < 6: age_bands["3 to 6 months"] += 1
                elif age_months < 9: age_bands["6 to 9 months"] += 1
                elif age_months < 12: age_bands["9 to 12 months"] += 1
                elif age_months < 15: age_bands["12 to 15 months"] += 1
                elif age_months < 18: age_bands["15 to 18 months"] += 1
                elif age_months < 21: age_bands["18 to 21 months"] += 1
                elif age_months < 24: age_bands["21 to 24 months"] += 1
                elif age_months < 27: age_bands["24 to 27 months"] += 1
                elif age_months < 30: age_bands["27 to 30 months"] += 1
                elif age_months < 33: age_bands["30 to 33 months"] += 1
                elif age_months < 36: age_bands["33 to 36 months"] += 1
                elif age_months < 39: age_bands["36 to 39 months"] += 1
                elif age_months < 42: age_bands["39 to 42 months"] += 1
                elif age_months < 45: age_bands["42 to 45 months"] += 1
                elif age_months < 48: age_bands["45 to 48 months"] += 1
                elif age_months < 51: age_bands["48 to 51 months"] += 1
                elif age_months < 54: age_bands["51 to 54 months"] += 1
                else: age_bands["54 to 57 months"] += 1

    # Bucket KG densities (Histogram)
    density_histogram = {"<20": 0, "20-50": 0, "50-100": 0, "100+": 0}
    for count in kg_density.values():
        if count < 20:
            density_histogram["<20"] += 1
        elif count < 50:
            density_histogram["20-50"] += 1
        elif count < 100:
            density_histogram["50-100"] += 1
        else:
            density_histogram["100+"] += 1

    return {
        "gender": gender_counts,
        "age_bands": age_bands,
        "density_histogram": density_histogram,
        "total_children": len(results),
        "total_kgs": len(kg_density),
        "data_quality": data_quality
    }

@router.get("/government-report")
def get_government_report(
    dim_type: str = Query(...),
    dim_id: str = Query(...),
    db: Session = Depends(get_db),
    current_user: models.User = Depends(require_admin)
):
    """Generates the official Government Decision Support Report."""
    
    # 1. Fetch Demographics
    demo_data = get_demographics(dim_type, dim_id, db, current_user)
    
    # 2. Fetch Z-Scores
    # To get Z-scores, we just use the existing logic (simplified)
    dim_enum = getattr(models.AnalyticsDimensionType, dim_type, models.AnalyticsDimensionType.NETWORK)
    target = db.query(models.AnalyticsDimensionCache).filter(
        models.AnalyticsDimensionCache.dimension_type == dim_enum,
        models.AnalyticsDimensionCache.dimension_id == dim_id
    ).order_by(models.AnalyticsDimensionCache.period_date.desc()).first()
    
    network_targets = db.query(models.AnalyticsDimensionCache).filter(
        models.AnalyticsDimensionCache.dimension_type == models.AnalyticsDimensionType.NETWORK,
        models.AnalyticsDimensionCache.dimension_id == "JORDAN"
    ).order_by(models.AnalyticsDimensionCache.period_date.desc()).all()
    
    gov_mean, att_mean, gov_std, att_std = 0.0, 0.0, 1.0, 1.0
    if network_targets:
        n_govs = [t.final_governance_score for t in network_targets if t.final_governance_score]
        n_atts = [t.attendance_rate for t in network_targets if t.attendance_rate]
        if n_govs: gov_mean = sum(n_govs) / len(n_govs)
        if n_atts: att_mean = sum(n_atts) / len(n_atts)
        
        gov_var = sum((x - gov_mean)**2 for x in n_govs) / len(n_govs) if n_govs else 1.0
        att_var = sum((x - att_mean)**2 for x in n_atts) / len(n_atts) if n_atts else 1.0
        gov_std = math.sqrt(gov_var) if gov_var > 0 else 1.0
        att_std = math.sqrt(att_var) if att_var > 0 else 1.0

    target_gov = target.final_governance_score if target and target.final_governance_score else gov_mean
    target_att = target.attendance_rate if target and target.attendance_rate else att_mean
    
    z_scores = {
        "governance": (target_gov - gov_mean) / gov_std,
        "attendance": (target_att - att_mean) / att_std
    }
    
    # 3. Fetch Predictive Insights
    adv = db.query(models.AdvancedAnalyticsCache).filter(
        models.AdvancedAnalyticsCache.dimension_type == dim_enum,
        models.AdvancedAnalyticsCache.dimension_id == dim_id
    ).order_by(models.AdvancedAnalyticsCache.period_date.desc()).first()
    
    adv_data = {
        "staffing_quality_correlation": adv.staffing_quality_correlation if adv else 0.0,
        "attendance_trend_slope": adv.attendance_trend_slope if adv else 0.0,
        "predictive_risk_index": adv.predictive_risk_index if adv else 50.0
    }
    
    # Generate human-readable report via Heuristics Engine
    dim_name_display = "الأردن (الشبكة الوطنية)" if dim_id == "JORDAN" else dim_id.replace("_", " ")
    
    report = generate_government_report(dim_name_display, z_scores, adv_data, demo_data)
    return report
