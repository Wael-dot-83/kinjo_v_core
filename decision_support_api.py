"""
Decision-support analytics for the dashboard.

The frontend renders this block only for admins and managers. Admins see the
whole network; managers are scoped to their assigned kindergarten.
"""

from __future__ import annotations

from collections import defaultdict
from datetime import date, timedelta
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import func
from sqlalchemy.orm import Session

import models
from database import get_db
from dependencies import get_current_user


router = APIRouter(tags=["Decision Support"])


def _pct(numerator: int | float, denominator: int | float) -> float:
    if not denominator:
        return 0.0
    return round((float(numerator) / float(denominator)) * 100.0, 1)


def _enum_value(value: Any) -> str:
    return value.value if hasattr(value, "value") else str(value)


def _age_group_label(value: Any) -> str:
    labels = {
        "AGE_0_1": "٠-١ سنة",
        "AGE_1_2": "١-٢ سنة",
        "AGE_2_4": "٢-٤ سنوات",
    }
    return labels.get(_enum_value(value), _enum_value(value))


def _scoped_kindergarten_ids(db: Session, current_user: models.User) -> list[int]:
    if current_user.role == models.UserRole.ADMIN:
        rows = db.query(models.Kindergarten.id).order_by(models.Kindergarten.id).all()
        return [row[0] for row in rows]

    if current_user.role == models.UserRole.MANAGER:
        if not current_user.kindergarten_id:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Manager must be assigned to a kindergarten",
            )
        return [current_user.kindergarten_id]

    raise HTTPException(
        status_code=status.HTTP_403_FORBIDDEN,
        detail="Decision support is available to admins and managers only",
    )


def _empty_payload() -> dict[str, Any]:
    return {
        "total_kindergartens": 0,
        "total_children": 0,
        "total_capacity": 0,
        "network_utilization_pct": 0.0,
        "network_attendance_pct": 0.0,
        "geo_distribution": [],
        "classification_bands": [],
        "capacity_tiers": [],
        "predictions": [],
        "risk_items": [],
        "enrollment_funnel": {
            "submitted": 0,
            "pending_review": 0,
            "accepted": 0,
            "active": 0,
            "waitlisted": 0,
            "rejected": 0,
            "withdrawn": 0,
        },
        "age_group_distribution": [],
    }


@router.get("/api/decision-support")
@router.get("/api/dashboard/decision-support")
def get_decision_support_dashboard(
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_user),
) -> dict[str, Any]:
    """Return scoped decision-support aggregates for the dashboard."""

    today = date.today()
    recent_since = today - timedelta(days=30)
    kg_ids = _scoped_kindergarten_ids(db, current_user)
    if not kg_ids:
        return _empty_payload()

    kindergartens = (
        db.query(models.Kindergarten)
        .filter(models.Kindergarten.id.in_(kg_ids))
        .order_by(models.Kindergarten.id)
        .all()
    )
    if not kindergartens:
        return _empty_payload()

    capacity_by_kg = dict(
        db.query(models.Class.kindergarten_id, func.sum(models.Class.capacity_total))
        .filter(models.Class.kindergarten_id.in_(kg_ids), models.Class.is_active.is_(True))
        .group_by(models.Class.kindergarten_id)
        .all()
    )

    enrolled_by_kg = dict(
        db.query(
            models.EnrollmentApplication.kindergarten_id,
            func.count(func.distinct(models.EnrollmentApplication.child_id)),
        )
        .filter(
            models.EnrollmentApplication.kindergarten_id.in_(kg_ids),
            models.EnrollmentApplication.status == models.EnrollmentStatus.ACTIVE,
        )
        .group_by(models.EnrollmentApplication.kindergarten_id)
        .all()
    )

    attendance_by_kg = dict(
        db.query(
            models.EnrollmentApplication.kindergarten_id,
            func.count(func.distinct(models.AttendanceLog.child_id)),
        )
        .join(
            models.EnrollmentApplication,
            models.EnrollmentApplication.child_id == models.AttendanceLog.child_id,
        )
        .filter(
            models.EnrollmentApplication.kindergarten_id.in_(kg_ids),
            models.EnrollmentApplication.status == models.EnrollmentStatus.ACTIVE,
            models.AttendanceLog.date == today,
            models.AttendanceLog.status == models.AttendanceStatus.PRESENT,
        )
        .group_by(models.EnrollmentApplication.kindergarten_id)
        .all()
    )

    incidents_by_kg = dict(
        db.query(models.Incident.kindergarten_id, func.count(models.Incident.id))
        .filter(
            models.Incident.kindergarten_id.in_(kg_ids),
            func.date(models.Incident.occurred_at) >= recent_since,
        )
        .group_by(models.Incident.kindergarten_id)
        .all()
    )

    funnel_counts = _empty_payload()["enrollment_funnel"]
    enrollment_rows = (
        db.query(models.EnrollmentApplication.status, func.count(models.EnrollmentApplication.id))
        .filter(models.EnrollmentApplication.kindergarten_id.in_(kg_ids))
        .group_by(models.EnrollmentApplication.status)
        .all()
    )
    for enrollment_status, count in enrollment_rows:
        key = _enum_value(enrollment_status).lower()
        if key in funnel_counts:
            funnel_counts[key] = count

    age_rows = (
        db.query(models.Class.age_group, func.count(models.EnrollmentApplication.id))
        .join(models.EnrollmentApplication, models.EnrollmentApplication.class_id == models.Class.id)
        .filter(
            models.Class.kindergarten_id.in_(kg_ids),
            models.EnrollmentApplication.status == models.EnrollmentStatus.ACTIVE,
        )
        .group_by(models.Class.age_group)
        .all()
    )
    age_group_distribution = [
        {"age_group": _age_group_label(age_group), "count": count}
        for age_group, count in age_rows
    ]

    total_capacity = int(sum((capacity_by_kg.get(kg.id) or 0) for kg in kindergartens))
    total_children = int(sum((enrolled_by_kg.get(kg.id) or 0) for kg in kindergartens))
    total_attendance = int(sum((attendance_by_kg.get(kg.id) or 0) for kg in kindergartens))

    geo_groups: dict[tuple[str, str], dict[str, Any]] = {}
    classification_accumulator: dict[str, dict[str, float]] = defaultdict(
        lambda: {"count": 0, "attendance_total": 0.0, "utilization_total": 0.0}
    )
    tier_counts: dict[str, int] = defaultdict(int)
    risk_items: list[dict[str, Any]] = []

    for kg in kindergartens:
        capacity = int(capacity_by_kg.get(kg.id) or 0)
        enrolled = int(enrolled_by_kg.get(kg.id) or 0)
        present = int(attendance_by_kg.get(kg.id) or 0)
        incident_count = int(incidents_by_kg.get(kg.id) or 0)
        utilization_pct = _pct(enrolled, capacity)
        attendance_rate = _pct(present, enrolled)

        group_key = (kg.governorate or "غير محدد", kg.district or "غير محدد")
        group = geo_groups.setdefault(
            group_key,
            {
                "governorate": group_key[0],
                "city": group_key[1],
                "kindergarten_count": 0,
                "total_capacity": 0,
                "total_enrolled": 0,
                "present_today": 0,
                "incident_count": 0,
            },
        )
        group["kindergarten_count"] += 1
        group["total_capacity"] += capacity
        group["total_enrolled"] += enrolled
        group["present_today"] += present
        group["incident_count"] += incident_count

        if utilization_pct > 100:
            tier_counts["over_capacity"] += 1
        elif utilization_pct >= 75:
            tier_counts["high"] += 1
        elif utilization_pct >= 50:
            tier_counts["moderate"] += 1
        else:
            tier_counts["low"] += 1

        if attendance_rate < 70 or utilization_pct > 100:
            band = "red"
        elif attendance_rate < 85 or utilization_pct < 50 or utilization_pct >= 95:
            band = "amber"
        else:
            band = "green"
        classification_accumulator[band]["count"] += 1
        classification_accumulator[band]["attendance_total"] += attendance_rate
        classification_accumulator[band]["utilization_total"] += utilization_pct

        risk_score = 0
        risk_factors: list[str] = []
        if attendance_rate and attendance_rate < 70:
            risk_score += 35
            risk_factors.append("low_attendance")
        elif attendance_rate and attendance_rate < 85:
            risk_score += 20
            risk_factors.append("below_avg_attendance")
        if utilization_pct > 100:
            risk_score += 35
            risk_factors.append("over_capacity")
        elif capacity and utilization_pct < 30:
            risk_score += 10
            risk_factors.append("under_utilized")
        if incident_count >= 5:
            risk_score += 30
            risk_factors.append("high_incident_rate")
        elif incident_count >= 3:
            risk_score += 15
            risk_factors.append("elevated_incident_rate")
        if kg.license_valid_until:
            days_to_expiry = (kg.license_valid_until - today).days
            if days_to_expiry < 0:
                risk_score += 30
                risk_factors.append("license_expired")
            elif days_to_expiry <= 30:
                risk_score += 15
                risk_factors.append("license_expiring_soon")

        if risk_factors:
            risk_items.append(
                {
                    "kindergarten_id": kg.id,
                    "kindergarten_name": kg.name_ar or kg.name_en or f"Kindergarten {kg.id}",
                    "city": kg.district or "غير محدد",
                    "risk_score": min(risk_score, 100),
                    "risk_factors": risk_factors,
                }
            )

    geo_distribution = []
    for group in geo_groups.values():
        geo_distribution.append(
            {
                "governorate": group["governorate"],
                "city": group["city"],
                "kindergarten_count": group["kindergarten_count"],
                "total_capacity": group["total_capacity"],
                "total_enrolled": group["total_enrolled"],
                "utilization_pct": _pct(group["total_enrolled"], group["total_capacity"]),
                "attendance_rate": _pct(group["present_today"], group["total_enrolled"]),
                "incident_count": group["incident_count"],
            }
        )

    classification_bands = []
    for band in ("green", "amber", "red"):
        item = classification_accumulator.get(band)
        if not item or not item["count"]:
            continue
        classification_bands.append(
            {
                "band": band,
                "count": int(item["count"]),
                "avg_attendance": round(item["attendance_total"] / item["count"], 1),
                "avg_capacity_util": round(item["utilization_total"] / item["count"], 1),
            }
        )

    capacity_tiers = [
        {"tier": tier, "count": tier_counts[tier]}
        for tier in ("low", "moderate", "high", "over_capacity")
        if tier_counts[tier]
    ]

    risk_items.sort(key=lambda item: item["risk_score"], reverse=True)

    return {
        "total_kindergartens": len(kindergartens),
        "total_children": total_children,
        "total_capacity": total_capacity,
        "network_utilization_pct": _pct(total_children, total_capacity),
        "network_attendance_pct": _pct(total_attendance, total_children),
        "geo_distribution": geo_distribution,
        "classification_bands": classification_bands,
        "capacity_tiers": capacity_tiers,
        "predictions": [],
        "risk_items": risk_items,
        "enrollment_funnel": funnel_counts,
        "age_group_distribution": age_group_distribution,
    }
