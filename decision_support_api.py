"""
Decision Support API — aggregated analytics for the enhanced dashboard.

Provides geographic distribution, predictions, classification breakdowns,
capacity planning data, and risk indicators to support decision-making.
"""
from datetime import date, datetime, timedelta, timezone
from typing import Dict, List, Optional

from fastapi import APIRouter, Depends, Query
from pydantic import BaseModel
from sqlalchemy import func, case, and_
from sqlalchemy.orm import Session

import models
from database import get_db
from dependencies import get_current_user

router = APIRouter(prefix="/api/dashboard", tags=["Decision Support"])


# ---------------------------------------------------------------------------
# Response models
# ---------------------------------------------------------------------------

class GeoDistributionItem(BaseModel):
    governorate: str
    city: str
    kindergarten_count: int
    total_capacity: int
    total_enrolled: int
    utilization_pct: float
    attendance_rate: float
    incident_count: int


class ClassificationBand(BaseModel):
    band: str  # green / amber / red
    count: int
    kindergarten_ids: List[int]
    avg_attendance: float
    avg_capacity_util: float


class CapacityTier(BaseModel):
    tier: str
    count: int
    avg_utilization: float


class PredictionSummary(BaseModel):
    metric: str
    current_value: float
    predicted_value: float
    direction: str  # up / down / stable
    confidence: float
    forecast_days: int


class RiskItem(BaseModel):
    kindergarten_id: int
    kindergarten_name: str
    risk_score: float
    risk_factors: List[str]
    city: str
    governorate: str


class EnrollmentFunnel(BaseModel):
    submitted: int
    pending_review: int
    accepted: int
    active: int
    rejected: int
    waitlisted: int
    withdrawn: int


class AgeGroupDistribution(BaseModel):
    age_group: str
    count: int
    pct: float


class DecisionSupportResponse(BaseModel):
    geo_distribution: List[GeoDistributionItem]
    classification_bands: List[ClassificationBand]
    capacity_tiers: List[CapacityTier]
    predictions: List[PredictionSummary]
    risk_items: List[RiskItem]
    enrollment_funnel: EnrollmentFunnel
    age_group_distribution: List[AgeGroupDistribution]
    total_kindergartens: int
    total_children: int
    total_capacity: int
    network_utilization_pct: float
    network_attendance_pct: float
    generated_at: str


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _safe_pct(numerator: int, denominator: int) -> float:
    if denominator <= 0:
        return 0.0
    return round(min(100.0, (numerator / denominator) * 100.0), 1)


def _classify_band(attendance_rate: float, capacity_util: float, incident_rate: float) -> str:
    """Simple composite classification into green/amber/red."""
    score = 0
    if attendance_rate >= 85:
        score += 2
    elif attendance_rate >= 70:
        score += 1
    if 50 <= capacity_util <= 95:
        score += 2
    elif 30 <= capacity_util <= 110:
        score += 1
    if incident_rate <= 2:
        score += 2
    elif incident_rate <= 5:
        score += 1
    if score >= 5:
        return "green"
    if score >= 3:
        return "amber"
    return "red"


def _capacity_tier_label(util_pct: float) -> str:
    if util_pct >= 95:
        return "over_capacity"
    if util_pct >= 75:
        return "high"
    if util_pct >= 50:
        return "moderate"
    return "low"


# ---------------------------------------------------------------------------
# Endpoint
# ---------------------------------------------------------------------------

@router.get("/decision-support", response_model=DecisionSupportResponse)
async def get_decision_support_data(
    current_user: models.User = Depends(get_current_user),
    db: Session = Depends(get_db),
    period_days: int = Query(30, ge=7, le=365),
):
    """Aggregated decision-support data for the enhanced dashboard."""

    # Only ADMIN and MANAGER can view
    role = current_user.role.value if hasattr(current_user.role, "value") else str(current_user.role)
    if role not in ("ADMIN", "MANAGER"):
        from fastapi import HTTPException
        raise HTTPException(status_code=403, detail="Insufficient permissions")

    today = date.today()
    period_start = today - timedelta(days=period_days)

    # Scope for MANAGER: their kindergarten only
    kg_filter = []
    if role == "MANAGER" and current_user.kindergarten_id:
        kg_filter = [models.Kindergarten.id == current_user.kindergarten_id]

    # ---- 1. Active kindergartens list ----
    kg_query = db.query(models.Kindergarten).filter(
        models.Kindergarten.status == models.KindergartenStatus.ACTIVE,
        *kg_filter,
    )
    kindergartens = kg_query.all()
    kg_ids = [kg.id for kg in kindergartens]

    if not kg_ids:
        return DecisionSupportResponse(
            geo_distribution=[],
            classification_bands=[],
            capacity_tiers=[],
            predictions=[],
            risk_items=[],
            enrollment_funnel=EnrollmentFunnel(
                submitted=0, pending_review=0, accepted=0,
                active=0, rejected=0, waitlisted=0, withdrawn=0,
            ),
            age_group_distribution=[],
            total_kindergartens=0,
            total_children=0,
            total_capacity=0,
            network_utilization_pct=0,
            network_attendance_pct=0,
            generated_at=datetime.now(timezone.utc).isoformat(),
        )

    # ---- 2. Per-KG capacity ----
    cap_rows = (
        db.query(
            models.Class.kindergarten_id,
            func.sum(models.Class.capacity_total),
        )
        .filter(models.Class.kindergarten_id.in_(kg_ids), models.Class.is_active.is_(True))
        .group_by(models.Class.kindergarten_id)
        .all()
    )
    kg_capacity: Dict[int, int] = {row[0]: int(row[1] or 0) for row in cap_rows}

    # ---- 3. Per-KG active enrollment count ----
    enr_rows = (
        db.query(
            models.EnrollmentApplication.kindergarten_id,
            func.count(models.EnrollmentApplication.id),
        )
        .filter(
            models.EnrollmentApplication.kindergarten_id.in_(kg_ids),
            models.EnrollmentApplication.status == models.EnrollmentStatus.ACTIVE,
        )
        .group_by(models.EnrollmentApplication.kindergarten_id)
        .all()
    )
    kg_enrolled: Dict[int, int] = {row[0]: int(row[1]) for row in enr_rows}

    # ---- 4. Per-KG attendance rate (period) ----
    # Count present days per kindergarten over the period
    att_present = (
        db.query(
            models.Class.kindergarten_id,
            func.count(models.AttendanceLog.id),
        )
        .join(models.Class, models.Class.id == models.AttendanceLog.class_id)
        .filter(
            models.Class.kindergarten_id.in_(kg_ids),
            models.AttendanceLog.date >= period_start,
            models.AttendanceLog.date <= today,
            models.AttendanceLog.status == models.AttendanceStatus.PRESENT,
        )
        .group_by(models.Class.kindergarten_id)
        .all()
    )
    kg_present: Dict[int, int] = {row[0]: int(row[1]) for row in att_present}

    att_total = (
        db.query(
            models.Class.kindergarten_id,
            func.count(models.AttendanceLog.id),
        )
        .join(models.Class, models.Class.id == models.AttendanceLog.class_id)
        .filter(
            models.Class.kindergarten_id.in_(kg_ids),
            models.AttendanceLog.date >= period_start,
            models.AttendanceLog.date <= today,
        )
        .group_by(models.Class.kindergarten_id)
        .all()
    )
    kg_att_total: Dict[int, int] = {row[0]: int(row[1]) for row in att_total}

    # ---- 5. Per-KG incident count (period) ----
    inc_rows = (
        db.query(
            models.Incident.kindergarten_id,
            func.count(models.Incident.id),
        )
        .filter(
            models.Incident.kindergarten_id.in_(kg_ids),
            func.date(models.Incident.occurred_at) >= period_start,
        )
        .group_by(models.Incident.kindergarten_id)
        .all()
    )
    kg_incidents: Dict[int, int] = {row[0]: int(row[1]) for row in inc_rows}

    # ---- 6. Build geo distribution & classification ----
    geo_map: Dict[str, GeoDistributionItem] = {}
    band_map: Dict[str, ClassificationBand] = {"green": None, "amber": None, "red": None}
    tier_counts: Dict[str, list] = {}
    risk_items: List[RiskItem] = []

    total_capacity = 0
    total_enrolled = 0
    total_present = 0
    total_att_records = 0

    for kg in kindergartens:
        cap = kg_capacity.get(kg.id, 0)
        enrolled = kg_enrolled.get(kg.id, 0)
        present = kg_present.get(kg.id, 0)
        att_total_kg = kg_att_total.get(kg.id, 0)
        incidents = kg_incidents.get(kg.id, 0)

        util_pct = _safe_pct(enrolled, cap)
        att_rate = _safe_pct(present, att_total_kg)
        inc_rate = (incidents / max(1, enrolled)) * 100.0 if enrolled > 0 else 0.0

        total_capacity += cap
        total_enrolled += enrolled
        total_present += present
        total_att_records += att_total_kg

        # Geographic distribution
        geo_key = f"{kg.governorate}|{kg.city}"
        if geo_key not in geo_map:
            geo_map[geo_key] = GeoDistributionItem(
                governorate=kg.governorate or "",
                city=kg.city or "",
                kindergarten_count=0,
                total_capacity=0,
                total_enrolled=0,
                utilization_pct=0,
                attendance_rate=0,
                incident_count=0,
            )
        item = geo_map[geo_key]
        item.kindergarten_count += 1
        item.total_capacity += cap
        item.total_enrolled += enrolled
        item.incident_count += incidents

        # Classification
        band = _classify_band(att_rate, util_pct, inc_rate)
        if band_map[band] is None:
            band_map[band] = ClassificationBand(
                band=band, count=0, kindergarten_ids=[], avg_attendance=0, avg_capacity_util=0,
            )
        bm = band_map[band]
        bm.count += 1
        bm.kindergarten_ids.append(kg.id)
        bm.avg_attendance += att_rate
        bm.avg_capacity_util += util_pct

        # Capacity tier
        tier = _capacity_tier_label(util_pct)
        tier_counts.setdefault(tier, []).append(util_pct)

        # Risk assessment
        risk_factors: List[str] = []
        risk_score = 0.0
        if att_rate < 70:
            risk_factors.append("low_attendance")
            risk_score += 30
        elif att_rate < 85:
            risk_factors.append("below_avg_attendance")
            risk_score += 10
        if util_pct > 100:
            risk_factors.append("over_capacity")
            risk_score += 25
        elif util_pct < 30:
            risk_factors.append("under_utilized")
            risk_score += 15
        if inc_rate > 5:
            risk_factors.append("high_incident_rate")
            risk_score += 30
        elif inc_rate > 2:
            risk_factors.append("elevated_incident_rate")
            risk_score += 10
        if kg.license_valid_until and kg.license_valid_until < today + timedelta(days=90):
            risk_factors.append("license_expiring_soon")
            risk_score += 20
            if kg.license_valid_until < today:
                risk_factors.append("license_expired")
                risk_score += 30

        if risk_score > 0:
            risk_items.append(RiskItem(
                kindergarten_id=kg.id,
                kindergarten_name=kg.name_ar or kg.name_en or "",
                risk_score=min(100, risk_score),
                risk_factors=risk_factors,
                city=kg.city or "",
                governorate=kg.governorate or "",
            ))

    # Finalize geo utilization & attendance averages
    for item in geo_map.values():
        item.utilization_pct = _safe_pct(item.total_enrolled, item.total_capacity)
        # attendance_rate for the geo aggregation — recalculate from the sum approach
        # We'll compute it as a weighted average below; for now set from totals later

    # Finalize classification band averages
    classification_bands = []
    for band_key in ("green", "amber", "red"):
        bm = band_map.get(band_key)
        if bm and bm.count > 0:
            bm.avg_attendance = round(bm.avg_attendance / bm.count, 1)
            bm.avg_capacity_util = round(bm.avg_capacity_util / bm.count, 1)
            classification_bands.append(bm)

    # Capacity tiers
    capacity_tiers = []
    for tier_key in ("low", "moderate", "high", "over_capacity"):
        values = tier_counts.get(tier_key, [])
        if values:
            capacity_tiers.append(CapacityTier(
                tier=tier_key,
                count=len(values),
                avg_utilization=round(sum(values) / len(values), 1),
            ))

    # Sort risk items by score descending
    risk_items.sort(key=lambda r: r.risk_score, reverse=True)

    # ---- 7. Enrollment funnel ----
    funnel_query = (
        db.query(
            models.EnrollmentApplication.status,
            func.count(models.EnrollmentApplication.id),
        )
        .filter(models.EnrollmentApplication.kindergarten_id.in_(kg_ids))
        .group_by(models.EnrollmentApplication.status)
        .all()
    )
    funnel_map = {str(row[0].value if hasattr(row[0], "value") else row[0]): int(row[1]) for row in funnel_query}
    enrollment_funnel = EnrollmentFunnel(
        submitted=funnel_map.get("SUBMITTED", 0),
        pending_review=funnel_map.get("PENDING_REVIEW", 0),
        accepted=funnel_map.get("ACCEPTED", 0),
        active=funnel_map.get("ACTIVE", 0),
        rejected=funnel_map.get("REJECTED", 0),
        waitlisted=funnel_map.get("WAITLISTED", 0),
        withdrawn=funnel_map.get("WITHDRAWN", 0),
    )

    # ---- 8. Age group distribution ----
    age_group_rows = (
        db.query(models.Class.age_group, func.sum(models.Class.enrolled_children_count))
        .filter(models.Class.kindergarten_id.in_(kg_ids), models.Class.is_active.is_(True))
        .group_by(models.Class.age_group)
        .all()
    )
    total_by_age = sum(int(r[1] or 0) for r in age_group_rows)
    age_group_distribution = []
    for row in age_group_rows:
        ag = str(row[0].value if hasattr(row[0], "value") else row[0]) if row[0] else "UNKNOWN"
        count = int(row[1] or 0)
        age_group_distribution.append(AgeGroupDistribution(
            age_group=ag,
            count=count,
            pct=_safe_pct(count, total_by_age),
        ))

    # ---- 9. Predictions (network-level simple linear trend) ----
    predictions: List[PredictionSummary] = []
    try:
        # Attendance trend over last 30 days
        att_daily = (
            db.query(models.AttendanceLog.date, func.count(models.AttendanceLog.id))
            .join(models.Class, models.Class.id == models.AttendanceLog.class_id)
            .filter(
                models.Class.kindergarten_id.in_(kg_ids),
                models.AttendanceLog.date >= period_start,
                models.AttendanceLog.status == models.AttendanceStatus.PRESENT,
            )
            .group_by(models.AttendanceLog.date)
            .order_by(models.AttendanceLog.date.asc())
            .all()
        )
        if len(att_daily) >= 5:
            from predictive_analytics import PredictiveAnalytics
            pa = PredictiveAnalytics()
            values = [float(r[1]) for r in att_daily]
            slope, intercept, r2, _, _ = pa._linear_fit(values)
            future_idx = len(values) + 6
            predicted = max(0, slope * future_idx + intercept)
            current = values[-1] if values else 0
            direction = "up" if slope > 0.05 else ("down" if slope < -0.05 else "stable")
            predictions.append(PredictionSummary(
                metric="attendance",
                current_value=round(current, 1),
                predicted_value=round(predicted, 1),
                direction=direction,
                confidence=round(r2, 2),
                forecast_days=7,
            ))

        # Incident trend
        inc_daily = (
            db.query(func.date(models.Incident.occurred_at), func.count(models.Incident.id))
            .filter(
                models.Incident.kindergarten_id.in_(kg_ids),
                func.date(models.Incident.occurred_at) >= period_start,
            )
            .group_by(func.date(models.Incident.occurred_at))
            .order_by(func.date(models.Incident.occurred_at).asc())
            .all()
        )
        if len(inc_daily) >= 3:
            from predictive_analytics import PredictiveAnalytics
            pa = PredictiveAnalytics()
            values = [float(r[1]) for r in inc_daily]
            slope, intercept, r2, _, _ = pa._linear_fit(values)
            future_idx = len(values) + 6
            predicted = max(0, slope * future_idx + intercept)
            current = values[-1] if values else 0
            direction = "up" if slope > 0.02 else ("down" if slope < -0.02 else "stable")
            predictions.append(PredictionSummary(
                metric="incidents",
                current_value=round(current, 1),
                predicted_value=round(predicted, 1),
                direction=direction,
                confidence=round(r2, 2),
                forecast_days=7,
            ))

        # Enrollment trend
        enr_daily = (
            db.query(
                func.date(models.EnrollmentApplication.submitted_at),
                func.count(models.EnrollmentApplication.id),
            )
            .filter(
                models.EnrollmentApplication.kindergarten_id.in_(kg_ids),
                models.EnrollmentApplication.submitted_at.isnot(None),
                func.date(models.EnrollmentApplication.submitted_at) >= period_start,
            )
            .group_by(func.date(models.EnrollmentApplication.submitted_at))
            .order_by(func.date(models.EnrollmentApplication.submitted_at).asc())
            .all()
        )
        if len(enr_daily) >= 3:
            from predictive_analytics import PredictiveAnalytics
            pa = PredictiveAnalytics()
            values = [float(r[1]) for r in enr_daily]
            slope, intercept, r2, _, _ = pa._linear_fit(values)
            future_idx = len(values) + 6
            predicted = max(0, slope * future_idx + intercept)
            current = values[-1] if values else 0
            direction = "up" if slope > 0.02 else ("down" if slope < -0.02 else "stable")
            predictions.append(PredictionSummary(
                metric="enrollment",
                current_value=round(current, 1),
                predicted_value=round(predicted, 1),
                direction=direction,
                confidence=round(r2, 2),
                forecast_days=7,
            ))
    except Exception:
        pass  # Predictions are best-effort

    # Geo distribution — fix attendance rates
    # Recompute attendance per geo region from the KG data
    geo_att_lookup: Dict[str, tuple] = {}
    for kg in kindergartens:
        geo_key = f"{kg.governorate}|{kg.city}"
        p = kg_present.get(kg.id, 0)
        t = kg_att_total.get(kg.id, 0)
        prev_p, prev_t = geo_att_lookup.get(geo_key, (0, 0))
        geo_att_lookup[geo_key] = (prev_p + p, prev_t + t)
    for geo_key, item in geo_map.items():
        p, t = geo_att_lookup.get(geo_key, (0, 0))
        item.attendance_rate = _safe_pct(p, t)

    network_util = _safe_pct(total_enrolled, total_capacity)
    network_att = _safe_pct(total_present, total_att_records)

    return DecisionSupportResponse(
        geo_distribution=sorted(geo_map.values(), key=lambda g: g.kindergarten_count, reverse=True),
        classification_bands=classification_bands,
        capacity_tiers=capacity_tiers,
        predictions=predictions,
        risk_items=risk_items[:20],  # Top 20 risk items
        enrollment_funnel=enrollment_funnel,
        age_group_distribution=age_group_distribution,
        total_kindergartens=len(kindergartens),
        total_children=total_enrolled,
        total_capacity=total_capacity,
        network_utilization_pct=network_util,
        network_attendance_pct=network_att,
        generated_at=datetime.now(timezone.utc).isoformat(),
    )
