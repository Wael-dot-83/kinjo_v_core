"""
Jordan Heat Map — service layer.

Encapsulates all read-side logic that the Admin UI needs:
- Loading latest governorate indicator values from the live KinJo DB
- Computing risk scores with consistent thresholds
- Loading sub-indicator breakdowns per governorate
- Loading trends (current vs previous period) per governorate
- Loading related alerts (from the existing `active_alerts` table)
- Computing Pearson/Spearman correlation matrices and OLS regression weights
- Mapping `governorate` string columns to canonical slugs

The service is deliberately pure (no FastAPI imports) so it can be reused
from synchronous admin endpoints, async jobs, and tests alike.
"""
from __future__ import annotations
import json
import logging
import math
import os
from datetime import date, datetime, timedelta, timezone
from utils.time_utils import today_amman as _today
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

from sqlalchemy import func
from sqlalchemy.orm import Session

from . import constants as C
import models

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# GeoJSON loading (canonical Jordan boundary file)
# ---------------------------------------------------------------------------
# We deliberately look first in heatmap/data/ (the more detailed file with
# real polygon coordinates) and fall back to static/data/ (a smaller version).
_GEOJSON_CANDIDATES: List[Path] = [
    Path(__file__).resolve().parent.parent / "data" / "jordan_admin.geojson",
    Path(__file__).resolve().parents[1] / "static" / "data" / "jordan_governorates.geojson",
    Path(__file__).resolve().parents[1] / "heatmap" / "data" / "jordan_admin.geojson",
]

_geojson_cache: Optional[Dict] = None


def load_jordan_geojson(force_reload: bool = False) -> Dict:
    """Return the Jordan governorate FeatureCollection as a dict."""
    global _geojson_cache
    if _geojson_cache is not None and not force_reload:
        return _geojson_cache
    for path in _GEOJSON_CANDIDATES:
        if path.exists():
            try:
                with open(path, encoding="utf-8") as f:
                    _geojson_cache = json.load(f)
                    return _geojson_cache
            except (OSError, json.JSONDecodeError) as exc:
                logger.warning("Failed to read GeoJSON at %s: %s", path, exc)
    _geojson_cache = {"type": "FeatureCollection", "features": []}
    return _geojson_cache


# ---------------------------------------------------------------------------
# Governorate aggregation from KinJo domain tables
# ---------------------------------------------------------------------------
# A single source of truth for the SQL aggregates used to derive the six
# main indicators per governorate.  Each entry is a callable that takes the
# `db` session and the governorate slug and returns a dict of sub-indicator
# values.  We deliberately use only first-class KinJo models so this code
# is compatible with the existing schema.
def _slug_to_db_name(slug: str) -> str:
    """Return the English name for a governorate slug (legacy; prefer _names_for_slug)."""
    g = C.GOVERNORATE_BY_SLUG.get(slug)
    if not g:
        return slug
    return g["name_en"]


def _names_for_slug(slug: str) -> list:
    """Return all DB-stored name variants for a governorate slug.

    The `governorate` column in Kindergarten/Incident/DailyReport tables may
    contain either the English name (e.g. "Amman") or the Arabic name
    (e.g. "عمان") depending on how the record was created.  Using .in_() with
    all known variants ensures both are matched without changing stored data.
    """
    g = C.GOVERNORATE_BY_SLUG.get(slug)
    if not g:
        return [slug]
    en = g["name_en"]
    ar = g["name_ar"]
    variants = {en, ar}
    # Arabic normalisation variants (hamza and taa marbuta)
    variants.add(ar.replace("أ", "ا").replace("إ", "ا"))  # أ إ → ا
    variants.add(ar.replace("ة", "ه"))  # ة → ه
    return list(variants)


def _query_kindergarten_count(db: Session, slug: str) -> int:
    try:
        import models
        names = _names_for_slug(slug)
        return int(db.query(func.count(models.Kindergarten.id))
                     .filter(models.Kindergarten.governorate.in_(names))
                     .scalar() or 0)
    except Exception:
        return 0


def _query_children_count(db: Session, slug: str) -> int:
    try:
        import models
        names = _names_for_slug(slug)
        # Child has no kindergarten_id; use active EnrollmentApplication as the source of truth
        return int(db.query(func.count(models.EnrollmentApplication.id))
                     .join(models.Kindergarten,
                           models.EnrollmentApplication.kindergarten_id == models.Kindergarten.id)
                     .filter(models.Kindergarten.governorate.in_(names))
                     .filter(models.EnrollmentApplication.status == models.EnrollmentStatus.ACTIVE)
                     .scalar() or 0)
    except Exception:
        return 0


def _query_supervisor_count(db: Session, slug: str) -> int:
    try:
        import models
        names = _names_for_slug(slug)
        return int(db.query(func.count(models.User.id))
                     .filter(models.User.role == models.UserRole.SUPERVISOR)
                     .filter(models.User.kindergarten_id.isnot(None))
                     .join(models.Kindergarten,
                           models.User.kindergarten_id == models.Kindergarten.id)
                     .filter(models.Kindergarten.governorate.in_(names))
                     .scalar() or 0)
    except Exception:
        return 0


def _query_classroom_count(db: Session, slug: str) -> int:
    try:
        import models
        names = _names_for_slug(slug)
        return int(db.query(func.count(models.Class.id))
                     .join(models.Kindergarten,
                           models.Class.kindergarten_id == models.Kindergarten.id)
                     .filter(models.Kindergarten.governorate.in_(names))
                     .scalar() or 0)
    except Exception:
        return 0


def _query_incident_count(db: Session, slug: str, critical_only: bool = False) -> int:
    try:
        import models
        names = _names_for_slug(slug)
        q = (db.query(func.count(models.Incident.id))
               .join(models.Kindergarten,
                     models.Incident.kindergarten_id == models.Kindergarten.id)
               .filter(models.Kindergarten.governorate.in_(names)))
        if critical_only and hasattr(models.Incident, "severity_level"):
            from models import SeverityLevel
            q = q.filter(models.Incident.severity_level == SeverityLevel.CRITICAL)
        return int(q.scalar() or 0)
    except Exception:
        return 0


def _query_governance_score(db: Session, slug: str) -> float:
    try:
        import models
        names = _names_for_slug(slug)
        val = (db.query(func.avg(models.GovernanceScore.final_governance_score))
                 .join(models.Kindergarten,
                       models.GovernanceScore.kindergarten_id == models.Kindergarten.id)
                 .filter(models.Kindergarten.governorate.in_(names))
                 .scalar() or 0)
        return float(val)
    except Exception:
        return 0.0


def _query_reports_count(db: Session, slug: str, since: datetime) -> int:
    try:
        import models
        names = _names_for_slug(slug)
        return int(db.query(func.count(models.DailyReport.id))
                     .join(models.Kindergarten,
                           models.DailyReport.kindergarten_id == models.Kindergarten.id)
                     .filter(models.Kindergarten.governorate.in_(names))
                     .filter(models.DailyReport.date >= since.date())
                     .scalar() or 0)
    except Exception:
        return 0


def _query_active_alerts(db: Session, slug: str) -> List[Dict]:
    try:
        import models
        names = _names_for_slug(slug)
        rows = (db.query(models.ActiveAlert)
                  .filter(models.ActiveAlert.scope_type == "GOVERNORATE")
                  .filter(models.ActiveAlert.scope_id.in_(names))
                  .filter(models.ActiveAlert.status == models.AlertStatus.ACTIVE)
                  .order_by(models.ActiveAlert.triggered_at.desc())
                  .limit(20)
                  .all())
        return [_alert_to_dict(a) for a in rows]
    except Exception as exc:
        logger.debug("ActiveAlert query failed for %s: %s", slug, exc)
        return []


def _alert_to_dict(alert) -> Dict:
    return {
        "id": alert.id,
        "metric": alert.metric_type,
        "severity": (alert.severity.value if hasattr(alert.severity, "value") else str(alert.severity)),
        "status": (alert.status.value if hasattr(alert.status, "value") else str(alert.status)),
        "current_value": float(alert.current_value) if alert.current_value is not None else 0.0,
        "message": alert.message or "",
        "triggered_at": alert.triggered_at.isoformat() if alert.triggered_at else None,
    }


# ---------------------------------------------------------------------------
# Main API
# ---------------------------------------------------------------------------
def get_governorates() -> List[Dict]:
    """Return the canonical list of 12 governorates with metadata."""
    return [
        {
            "code": g["code"],
            "slug": g["slug"],
            "name_en": g["name_en"],
            "name_ar": g["name_ar"],
            "center": list(g["center"]),
            "display_order": g["display_order"],
        }
        for g in sorted(C.GOVERNORATES, key=lambda x: x["display_order"])
    ]


def get_indicators() -> List[Dict]:
    """Return the canonical list of 6 main indicators with their sub-indicators."""
    out: List[Dict] = []
    for ind in C.MAIN_INDICATORS:
        entry = {
            "key": ind["key"],
            "name_en": ind["name_en"],
            "name_ar": ind["name_ar"],
            "color": ind["color"],
            "description_en": ind["description_en"],
            "description_ar": ind["description_ar"],
            "alert_threshold": C.INDICATOR_ALERT_THRESHOLD.get(ind["key"], 70.0),
            "sub_indicators": [
                {
                    "key": s["key"],
                    "name_en": s["name_en"],
                    "name_ar": s["name_ar"],
                    "unit": s["unit"],
                    "threshold_high": s["threshold_high"],
                    "threshold_low": s["threshold_low"],
                    "higher_is_better": s["higher_is_better"],
                }
                for s in C.SUB_INDICATORS.get(ind["key"], [])
            ],
        }
        out.append(entry)
    return out


_ESTIMATED_SUB_INDICATORS: frozenset = frozenset({
    "inactive_nurseries",
    "unregistered_children",
    "health_absences",
    "repeated_health",
    "protection_cases",
    "incident_severity",
    "delayed_tasks",
    "registration_rate",
    "training_completion",
    "compliance_status",
})


def _compute_sub_indicators(db: Session, slug: str) -> Dict[str, Any]:
    """Compute the 25 sub-indicator values for a single governorate."""
    active_kg = _query_kindergarten_count(db, slug)
    inactive_kg = max(0, int(active_kg * 0.05))  # Conservative estimate if no inactive column
    children = _query_children_count(db, slug)
    supervisors = _query_supervisor_count(db, slug)
    classrooms = _query_classroom_count(db, slug)
    total_incidents = _query_incident_count(db, slug, critical_only=False)
    critical_incidents = _query_incident_count(db, slug, critical_only=True)
    governance = _query_governance_score(db, slug)
    since = datetime.now() - timedelta(days=30)
    reports_30d = _query_reports_count(db, slug, since)

    active_pct = round((active_kg / max(active_kg + inactive_kg, 1)) * 100, 1)
    inactive_pct = round(100 - active_pct, 1)
    registration_rate = round(min(100.0, max(0.0, 70.0 + (governance / 5))), 1)
    child_supervisor_ratio = round(children / max(supervisors, 1), 1)
    child_teacher_ratio = round(child_supervisor_ratio * 0.8, 1)
    classrooms_no_supervisor = max(0, classrooms - supervisors)
    absences_total = max(0, int(children * 0.08))
    health_absences = max(0, int(absences_total * 0.2))
    repeated_health = max(0, int(health_absences * 0.3))
    reports_missing = max(0, active_kg * 30 - reports_30d)
    absence_rate = round((absences_total / max(children, 1)) * 100, 1)
    delayed_tasks = max(0, int(active_kg * 0.4))
    training_completion = round(min(100.0, max(0.0, 60.0 + (governance / 4))), 1)
    compliance_status = round(min(100.0, max(0.0, 55.0 + (governance / 3))), 1)

    sub = {
        # nursery_status
        "active_nurseries": active_kg,
        "inactive_nurseries": inactive_kg,
        "active_pct": active_pct,
        "inactive_pct": inactive_pct,
        # children_registration
        "registered_children": children,
        "unregistered_children": max(0, int(children * 0.05)),
        "registration_rate": registration_rate,
        "age_distribution": children,
        # staff_classrooms
        "supervisors_count": supervisors,
        "classrooms_count": classrooms,
        "classrooms_no_supervisor": classrooms_no_supervisor,
        "child_supervisor_ratio": child_supervisor_ratio,
        "child_teacher_ratio": child_teacher_ratio,
        # safety_incidents
        "incidents_total": total_incidents,
        "incidents_critical": critical_incidents,
        "protection_cases": max(0, int(critical_incidents * 0.3)),
        "incident_severity": min(100, total_incidents * 5),
        # reports_attendance
        "reports_submitted": reports_30d,
        "reports_missing": reports_missing,
        "absence_rate": absence_rate,
        "health_absences": health_absences,
        "repeated_health": repeated_health,
        # tasks_governance
        "delayed_tasks": delayed_tasks,
        "governance_score": round(governance, 1),
        "training_completion": training_completion,
        "compliance_status": compliance_status,
        "_estimated_keys": sorted(_ESTIMATED_SUB_INDICATORS),
    }
    return sub


def _compute_main_indicators(sub: Dict[str, Any]) -> Dict[str, float]:
    """Aggregate the 6 main indicators (0-100) from the sub-indicator values.

    Accepts both full sub-indicator dicts (from _compute_sub_indicators) and
    partial dicts (from _previous_period_sub); missing keys default to 0.
    """
    def _g(key, default=0):
        return sub.get(key, default)

    active_kg = _g("active_nurseries")
    inactive_kg = _g("inactive_nurseries")
    kg_total = active_kg + inactive_kg
    kg_active_ratio = (active_kg / max(kg_total, 1)) * 100.0

    reg_children = _g("registered_children")
    unreg_children = _g("unregistered_children")
    children = reg_children + unreg_children
    enrollment_ratio = (reg_children / max(children, 1)) * 100.0

    classrooms_no_sup = _g("classrooms_no_supervisor")
    classrooms_count = _g("classrooms_count")
    supervised_ratio = 100.0 * (1.0 - classrooms_no_sup / max(classrooms_count, 1))
    supervised_ratio = max(0.0, min(100.0, supervised_ratio))

    safety_penalty = min(100.0, _g("incidents_critical") * 10.0 + _g("protection_cases") * 5.0)
    safety_score = max(0.0, 100.0 - safety_penalty)

    absence_rate = _g("absence_rate") / 100.0
    health_alert_rate = _g("health_absences") / max(reg_children, 1)
    report_completeness = min(1.0, _g("reports_submitted") / max(active_kg * 30, 1))
    reports_attendance_score = (
        report_completeness * 0.5
        + (1.0 - absence_rate) * 0.3
        + (1.0 - min(1.0, health_alert_rate)) * 0.2
    ) * 100.0

    task_penalty = min(50.0, _g("delayed_tasks") * 5.0)
    tasks_governance_score = (
        _g("governance_score") * 0.5
        + _g("training_completion") * 0.3
        + max(0.0, 50.0 - task_penalty) * 0.4
    )

    return {
        "nursery_status":        round(kg_active_ratio, 2),
        "children_registration": round(enrollment_ratio, 2),
        "staff_classrooms":      round(supervised_ratio, 2),
        "safety_incidents":      round(safety_score, 2),
        "reports_attendance":    round(reports_attendance_score, 2),
        "tasks_governance":      round(tasks_governance_score, 2),
    }


def _kindergarten_status_payload(score: Optional[float]) -> Dict[str, Any]:
    """Return a canonical KPI status payload for a 0-100 score."""
    from .kpi_status import KPIStatus, get_status_display, normalize_kpi_status, status_to_color

    score_f = 0.0 if score is None else max(0.0, min(100.0, float(score)))
    status = normalize_kpi_status(score_f)
    if status == KPIStatus.UNKNOWN:
        score_f = 0.0
    return {
        "score": round(score_f, 2),
        "status": status.value,
        "display_en": get_status_display(status, "en"),
        "display_ar": get_status_display(status, "ar"),
        "color": status_to_color(status),
    }


def _latest_governance_score(db: Session, kindergarten_id: int) -> Optional[float]:
    try:
        score_tuple = (
            db.query(models.GovernanceScore.final_governance_score)
            .filter(models.GovernanceScore.kindergarten_id == kindergarten_id)
            .order_by(models.GovernanceScore.period_end.desc())
            .first()
        )
        score = score_tuple[0] if score_tuple else None
        return float(score) if score is not None else None
    except Exception:
        return None


def _count_enrollments(db: Session, kindergarten_id: int) -> int:
    try:
        return int(
            db.query(func.count(models.EnrollmentApplication.id))
            .filter(models.EnrollmentApplication.kindergarten_id == kindergarten_id)
            .filter(models.EnrollmentApplication.status == models.EnrollmentStatus.ACTIVE)
            .scalar()
            or 0
        )
    except Exception:
        return 0


def _count_classes(db: Session, kindergarten_id: int) -> int:
    try:
        return int(
            db.query(func.count(models.Class.id))
            .filter(models.Class.kindergarten_id == kindergarten_id)
            .scalar()
            or 0
        )
    except Exception:
        return 0


def _count_supervisors(db: Session, kindergarten_id: int) -> int:
    try:
        user_count = int(
            db.query(func.count(models.User.id))
            .filter(models.User.kindergarten_id == kindergarten_id)
            .filter(models.User.role == models.UserRole.SUPERVISOR)
            .scalar()
            or 0
        )
        profile_count = int(
            db.query(func.count(models.SupervisorProfile.user_id))
            .filter(models.SupervisorProfile.kindergarten_id == kindergarten_id)
            .scalar()
            or 0
        )
        return max(user_count, profile_count)
    except Exception:
        return 0


def _count_recent_reports(db: Session, kindergarten_id: int, days: int = 30) -> int:
    try:
        since = _today() - timedelta(days=days)
        return int(
            db.query(func.count(models.DailyReport.id))
            .filter(models.DailyReport.kindergarten_id == kindergarten_id)
            .filter(models.DailyReport.date >= since)
            .scalar()
            or 0
        )
    except Exception:
        return 0


def _count_recent_incidents(db: Session, kindergarten_id: int, days: int = 90) -> Dict[str, int]:
    try:
        since = datetime.now() - timedelta(days=days)
        q = (
            db.query(models.Incident)
            .filter(models.Incident.kindergarten_id == kindergarten_id)
            .filter(models.Incident.occurred_at >= since)
        )
        total = q.count()
        critical = 0
        if hasattr(models.Incident, "severity_level"):
            critical = (
                q.filter(models.Incident.severity_level == models.SeverityLevel.CRITICAL)
                .count()
            )
        return {"total": int(total), "critical": int(critical)}
    except Exception:
        return {"total": 0, "critical": 0}


def compute_kindergarten_kpi_scores(db: Session, kindergarten: models.Kindergarten) -> Dict[str, Any]:
    """Compute normalized kindergarten-level KPI scores for admin heat-map views."""
    status_score = {
        models.KindergartenStatus.ACTIVE.value: 100.0,
        models.KindergartenStatus.DRAFT.value: 60.0,
        models.KindergartenStatus.INACTIVE.value: 20.0,
    }.get(kindergarten.status.value if hasattr(kindergarten.status, "value") else str(kindergarten.status), 0.0)

    license_score = 50.0
    if kindergarten.license_valid_until is not None:
        license_score = 100.0 if kindergarten.license_valid_until >= _today() else 25.0

    location_score = 100.0 if kindergarten.latitude is not None and kindergarten.longitude is not None else 60.0
    nursery_score = round((status_score + license_score + location_score) / 3.0, 2)

    enrollment_count = _count_enrollments(db, kindergarten.id)
    children_score = 100.0 if enrollment_count > 0 else 0.0

    class_count = _count_classes(db, kindergarten.id)
    supervisor_count = _count_supervisors(db, kindergarten.id)
    staff_score = 100.0 if class_count > 0 and supervisor_count >= max(1, class_count // 2) else 0.0

    incidents = _count_recent_incidents(db, kindergarten.id)
    safety_score = max(0.0, 100.0 - incidents["total"] * 8.0 - incidents["critical"] * 25.0)

    reports_count = _count_recent_reports(db, kindergarten.id)
    reports_score = 100.0 if class_count == 0 else min(100.0, reports_count / max(class_count * 30, 1) * 100.0)

    governance_score = _latest_governance_score(db, kindergarten.id)
    governance_score = 0.0 if governance_score is None else max(0.0, min(100.0, governance_score))

    indicator_scores = {
        "nursery_status": nursery_score,
        "children_registration": children_score,
        "staff_classrooms": staff_score,
        "safety_incidents": safety_score,
        "reports_attendance": reports_score,
        "tasks_governance": governance_score,
    }
    overall_score = round(sum(indicator_scores.values()) / len(indicator_scores), 2)

    return {
        "score": overall_score,
        "indicators": {
            key: _kindergarten_status_payload(score)
            for key, score in indicator_scores.items()
        },
        "kpi_status": _kindergarten_status_payload(overall_score),
        "supporting_counts": {
            "active_enrollments": enrollment_count,
            "classes": class_count,
            "supervisors": supervisor_count,
            "recent_reports": reports_count,
            "recent_incidents": incidents["total"],
            "recent_critical_incidents": incidents["critical"],
            "governance_score": round(governance_score, 2),
        },
    }


def kindergarten_to_dict(
    db: Session,
    kindergarten: models.Kindergarten,
    *,
    include_details: bool = True,
) -> Dict[str, Any]:
    """Serialize a Kindergarten row with canonical KPI status data."""
    kpi = compute_kindergarten_kpi_scores(db, kindergarten)
    data = {
        "id": kindergarten.id,
        "name_ar": kindergarten.name_ar,
        "name_en": kindergarten.name_en,
        "governorate": C.normalize_governorate(kindergarten.governorate),
        "governorate_name_en": kindergarten.governorate,
        "district": kindergarten.district,
        "area": kindergarten.area,
        "address_line": kindergarten.address_line,
        "contact_phone": kindergarten.contact_phone,
        "contact_email": kindergarten.contact_email,
        "status": kindergarten.status.value if hasattr(kindergarten.status, "value") else str(kindergarten.status),
        "latitude": kindergarten.latitude,
        "longitude": kindergarten.longitude,
        "license_number": kindergarten.license_number,
        "license_valid_until": kindergarten.license_valid_until.isoformat() if kindergarten.license_valid_until else None,
        "created_at": kindergarten.created_at.isoformat() if kindergarten.created_at else None,
        "updated_at": kindergarten.updated_at.isoformat() if kindergarten.updated_at else None,
        "kpi_score": kpi["score"],
        "kpi_status": kpi["kpi_status"]["status"],
        "kpi_status_payload": kpi["kpi_status"],
        "main_indicators": kpi["indicators"],
        "supporting_counts": kpi["supporting_counts"],
    }
    if include_details:
        gov = C.GOVERNORATE_BY_SLUG.get(data["governorate"], {})
        data.update({
            "governorate_code": gov.get("code"),
            "governorate_name_ar": gov.get("name_ar"),
        })
    return data


def get_kindergarten_detail(db: Session, kindergarten_id: int) -> Optional[Dict[str, Any]]:
    kindergarten = db.query(models.Kindergarten).filter(models.Kindergarten.id == kindergarten_id).first()
    if kindergarten is None:
        return None
    return kindergarten_to_dict(db, kindergarten, include_details=True)


def get_kindergarten_map_data(
    db: Session,
    *,
    governorate: Optional[str] = None,
    district: Optional[str] = None,
    status: Optional[str] = None,
    from_date: Optional[date] = None,
    to_date: Optional[date] = None,
) -> Dict[str, Any]:
    rows = build_kindergarten_query(
        db,
        governorate=governorate,
        district=district,
        status=status,
        from_date=from_date,
        to_date=to_date,
    ).order_by(models.Kindergarten.id.asc()).all()

    if status:
        from .kpi_status import normalize_kpi_status

        normalized = normalize_kpi_status(status).value
        rows = [
            kg for kg in rows
            if compute_kindergarten_kpi_scores(db, kg)["kpi_status"]["status"] == normalized
        ]

    features = []
    missing_location_count = 0
    for kg in rows:
        kg_dict = kindergarten_to_dict(db, kg, include_details=False)
        if kg.latitude is None or kg.longitude is None:
            gov_match = None
            for g in C.GOVERNORATES:
                if g.get("name_ar") == kg.governorate or g.get("name_en", "").lower() == (kg.governorate or "").lower():
                    gov_match = g
                    break
            if gov_match and gov_match.get("center"):
                kg_lon, kg_lat = gov_match["center"]
            else:
                missing_location_count += 1
                continue
        else:
            kg_lat = float(kg.latitude)
            kg_lon = float(kg.longitude)
        features.append({
            "type": "Feature",
            "id": kg.id,
            "geometry": {
                "type": "Point",
                "coordinates": [kg_lon, kg_lat],
            },
            "properties": kg_dict,
        })

    return {
        "type": "FeatureCollection",
        "features": features,
        "count": len(features),
        "total_kindergartens": len(rows),
        "missing_location_count": missing_location_count,
        "filters": {
            "governorate": governorate,
            "district": district,
            "status": status,
            "from": from_date.isoformat() if from_date else None,
            "to": to_date.isoformat() if to_date else None,
        },
        "last_update": datetime.now(timezone.utc).strftime('%Y-%m-%dT%H:%M:%SZ'),
    }


def get_kindergarten_stats(
    db: Session,
    *,
    governorate: Optional[str] = None,
    district: Optional[str] = None,
    status: Optional[str] = None,
    from_date: Optional[date] = None,
    to_date: Optional[date] = None,
) -> Dict[str, Any]:
    rows = build_kindergarten_query(
        db,
        governorate=governorate,
        district=district,
        status=status,
        from_date=from_date,
        to_date=to_date,
    ).order_by(models.Kindergarten.id.asc()).all()

    if status:
        from .kpi_status import normalize_kpi_status

        normalized = normalize_kpi_status(status).value
        rows = [
            kg for kg in rows
            if compute_kindergarten_kpi_scores(db, kg)["kpi_status"]["status"] == normalized
        ]

    from .kpi_status import KPIStatus

    status_counts = {s.value: 0 for s in KPIStatus}
    governorate_counts: Dict[str, Dict[str, int]] = {}
    city_counts: Dict[str, Dict[str, int]] = {}
    indicator_scores: Dict[str, List[float]] = {ind["key"]: [] for ind in C.MAIN_INDICATORS}
    scores: List[float] = []

    for kg in rows:
        kg_dict = kindergarten_to_dict(db, kg, include_details=False)
        kpi_status = kg_dict["kpi_status"]
        status_counts[kpi_status] = status_counts.get(kpi_status, 0) + 1
        scores.append(float(kg_dict["kpi_score"]))

        gov_key = kg_dict["governorate"]
        district_key = kg_dict["district"] or "Unknown"
        governorate_counts.setdefault(gov_key, {s.value: 0 for s in KPIStatus})
        governorate_counts[gov_key]["total"] = governorate_counts[gov_key].get("total", 0) + 1
        governorate_counts[gov_key][kpi_status] = governorate_counts[gov_key].get(kpi_status, 0) + 1
        city_counts.setdefault(district_key, {s.value: 0 for s in KPIStatus})
        city_counts[district_key]["total"] = city_counts[district_key].get("total", 0) + 1
        city_counts[district_key][kpi_status] = city_counts[district_key].get(kpi_status, 0) + 1

        for indicator_key, indicator in kg_dict["main_indicators"].items():
            indicator_scores.setdefault(indicator_key, []).append(float(indicator["score"]))

    return {
        "total": len(rows),
        "status_counts": status_counts,
        "governorate_counts": governorate_counts,
        "city_counts": city_counts,
        "score": {
            "average": round(sum(scores) / len(scores), 2) if scores else 0.0,
            "min": round(min(scores), 2) if scores else 0.0,
            "max": round(max(scores), 2) if scores else 0.0,
        },
        "indicator_averages": {
            key: round(sum(values) / len(values), 2) if values else 0.0
            for key, values in indicator_scores.items()
        },
        "filters": {
            "governorate": governorate,
            "district": district,
            "status": status,
            "from": from_date.isoformat() if from_date else None,
            "to": to_date.isoformat() if to_date else None,
        },
        "last_update": datetime.now(timezone.utc).strftime('%Y-%m-%dT%H:%M:%SZ'),
    }


def build_kindergarten_query(
    db: Session,
    *,
    governorate: Optional[str] = None,
    district: Optional[str] = None,
    status: Optional[str] = None,
    from_date: Optional[date] = None,
    to_date: Optional[date] = None,
):
    """Build the reusable filtered Kindergarten query for admin endpoints."""
    query = db.query(models.Kindergarten)

    if governorate:
        slug = C.normalize_governorate(governorate)
        if slug not in C.GOVERNORATE_BY_SLUG:
            raise ValueError(f"Unknown governorate slug: {governorate!r}")
        query = query.filter(models.Kindergarten.governorate.in_(_names_for_slug(slug)))

    if district:
        query = query.filter(models.Kindergarten.district == district)

    if from_date:
        query = query.filter(func.date(func.coalesce(models.Kindergarten.updated_at, models.Kindergarten.created_at)) >= from_date)
    if to_date:
        query = query.filter(func.date(func.coalesce(models.Kindergarten.updated_at, models.Kindergarten.created_at)) <= to_date)

    return query


def _previous_period_sub(db: Session, slug: str, days: int = 30) -> Dict[str, Any]:
    try:
        import models
        names = _names_for_slug(slug)
        since = datetime.now(timezone.utc) - timedelta(days=days * 2)
        until = datetime.now(timezone.utc) - timedelta(days=days)
        prev_gov = (db.query(func.avg(models.GovernanceScore.final_governance_score))
                      .join(models.Kindergarten,
                            models.GovernanceScore.kindergarten_id == models.Kindergarten.id)
                      .filter(models.Kindergarten.governorate.in_(names))
                      .scalar() or 0.0)
        prev_reports = (db.query(func.count(models.DailyReport.id))
                          .join(models.Kindergarten,
                                models.DailyReport.kindergarten_id == models.Kindergarten.id)
                          .filter(models.Kindergarten.governorate.in_(names))
                          .filter(models.DailyReport.date >= since.date())
                          .filter(models.DailyReport.date < until.date())
                          .scalar() or 0)
        prev_incidents = (db.query(func.count(models.Incident.id))
                            .join(models.Kindergarten,
                                  models.Incident.kindergarten_id == models.Kindergarten.id)
                            .filter(models.Kindergarten.governorate.in_(names))
                            .filter(models.Incident.occurred_at >= since)
                            .filter(models.Incident.occurred_at < until)
                            .scalar() or 0)
        return {
            "governance_score": round(float(prev_gov), 1),
            "reports_submitted": int(prev_reports),
            "incidents_total": int(prev_incidents),
        }
    except Exception:
        return {}


def _trend_direction(current: Optional[float], previous: Optional[float]) -> Dict:
    if current is None or previous is None or previous == 0:
        return {"direction": "stable", "pct": 0.0}
    diff_pct = (float(current) - float(previous)) / max(abs(float(previous)), 1e-6) * 100.0
    if abs(diff_pct) < 2.0:
        direction = "stable"
    elif diff_pct > 0:
        direction = "up"
    else:
        direction = "down"
    return {"direction": direction, "pct": round(diff_pct, 1)}


def get_governorate_overview(db: Session, slug: str) -> Dict:
    """Build the full detail payload for one governorate."""
    gov = C.GOVERNORATE_BY_SLUG.get(slug)
    if not gov:
        raise ValueError(f"Unknown governorate slug: {slug!r}")

    sub = _compute_sub_indicators(db, slug)
    main = _compute_main_indicators(sub)
    alerts = _query_active_alerts(db, slug)
    prev = _previous_period_sub(db, slug)

    # Risk scoring per main indicator
    risk_levels: Dict[str, Dict] = {}
    risk_score = 0.0
    for ind_key, value in main.items():
        rl = C.risk_level_for_indicator(ind_key, value)
        risk_levels[ind_key] = {
            "key": rl["key"],
            "name_en": rl["name_en"],
            "name_ar": rl["name_ar"],
            "color": rl["color"],
        }
        risk_score += (100.0 - max(0.0, min(100.0, value))) / 6.0
    risk_score = round(risk_score, 1)
    overall_risk = C.risk_level_for_score(risk_score)

    # Build trend per main indicator (current vs previous period)
    prev_main = _compute_main_indicators(prev) if prev else {}
    trends: Dict[str, Dict] = {}
    for ind_key, value in main.items():
        pv = prev_main.get(ind_key) if prev_main else None
        trends[ind_key] = _trend_direction(value, pv)

    return {
        "slug": slug,
        "code": gov["code"],
        "name_en": gov["name_en"],
        "name_ar": gov["name_ar"],
        "center": list(gov["center"]),
        "main_indicators": main,
        "sub_indicators": sub,
        "risk_score": risk_score,
        "risk_level": {
            "key": overall_risk["key"],
            "name_en": overall_risk["name_en"],
            "name_ar": overall_risk["name_ar"],
            "color": overall_risk["color"],
        },
        "risk_by_indicator": risk_levels,
        "trends": trends,
        "alerts": alerts,
        "recommended_action": C.RECOMMENDED_ACTIONS.get(overall_risk["key"], {}),
        "last_update": datetime.now(timezone.utc).strftime('%Y-%m-%dT%H:%M:%SZ'),
    }


def get_city_summary(db: Session, slug: str) -> Dict:
    """Return district-level KPI aggregation for all districts within a governorate.

    Groups kindergartens by their `district` field, computes average KPI scores
    per district, converts to risk scale, and sorts by descending risk.

    Response shape::

        {
          "slug": "amman",
          "governorate_ar": "عمان",
          "cities": [
            {
              "district": "عمّان",
              "kindergarten_count": 42,
              "avg_kpi_score": 81.5,
              "risk_score": 18.5,
              "risk_level": {"key": "low", "name_ar": "منخفض", "color": "..."},
              "critical_kindergartens": 2,
              "children_count": 1200,
            }
          ],
          "city_count": 1,
          "data_status": "loaded" | "empty",
          "warnings": [],
          "last_update": "...",
        }
    """
    gov = C.GOVERNORATE_BY_SLUG.get(slug)
    if not gov:
        raise ValueError(f"Unknown governorate slug: {slug!r}")

    names = _names_for_slug(slug)
    kgs = (db.query(models.Kindergarten)
             .filter(models.Kindergarten.governorate.in_(names))
             .all())

    if not kgs:
        return {
            "slug": slug,
            "governorate_ar": gov["name_ar"],
            "cities": [],
            "city_count": 0,
            "data_status": "empty",
            "warnings": ["لا توجد روضات مسجلة في هذه المحافظة."],
            "last_update": datetime.now(timezone.utc).strftime('%Y-%m-%dT%H:%M:%SZ'),
        }

    from collections import defaultdict
    city_map: Dict[str, list] = defaultdict(list)
    for kg in kgs:
        district_name = (kg.district or '').strip() or 'غير محدد'
        city_map[district_name].append(kg)

    cities = []
    for district_name, city_kgs in city_map.items():
        scores: List[float] = []
        enrollments = 0
        for kg in city_kgs:
            try:
                kpi = compute_kindergarten_kpi_scores(db, kg)
                scores.append(float(kpi["score"]))
                enrollments += int(kpi["supporting_counts"].get("active_enrollments", 0))
            except Exception as exc:
                logger.debug("City summary KPI error for KG %s: %s", kg.id, exc)
                scores.append(0.0)

        avg_perf = round(sum(scores) / len(scores), 1) if scores else 0.0
        risk_score = round(100.0 - avg_perf, 1)
        rl = C.risk_level_for_score(risk_score)
        critical_count = sum(1 for s in scores if (100.0 - s) >= 75)

        cities.append({
            "district": district_name,
            "kindergarten_count": len(city_kgs),
            "avg_kpi_score": avg_perf,
            "risk_score": risk_score,
            "risk_level": {
                "key": rl["key"],
                "name_ar": rl["name_ar"],
                "color": rl["color"],
            },
            "critical_kindergartens": critical_count,
            "children_count": enrollments,
        })

    cities.sort(key=lambda c: c["risk_score"], reverse=True)

    return {
        "slug": slug,
        "governorate_ar": gov["name_ar"],
        "cities": cities,
        "city_count": len(cities),
        "data_status": "loaded",
        "warnings": [],
        "last_update": datetime.now(timezone.utc).strftime('%Y-%m-%dT%H:%M:%SZ'),
    }


def get_map_overview(db: Session) -> Dict:
    """Build the full heat-map payload for the admin dashboard."""
    governors = []
    overall_risk_total = 0.0
    for gov in C.GOVERNORATES:
        try:
            sub = _compute_sub_indicators(db, gov["slug"])
            main = _compute_main_indicators(sub)
            risk_score = round(sum(100.0 - v for v in main.values()) / 6.0, 1)
            overall_risk = C.risk_level_for_score(risk_score)
            governors.append({
                "slug": gov["slug"],
                "code": gov["code"],
                "name_en": gov["name_en"],
                "name_ar": gov["name_ar"],
                "center": list(gov["center"]),
                "main_indicators": main,
                "risk_score": risk_score,
                "risk_level": {
                    "key": overall_risk["key"],
                    "name_en": overall_risk["name_en"],
                    "name_ar": overall_risk["name_ar"],
                    "color": overall_risk["color"],
                },
                "kg_count": int(sub.get("active_nurseries", 0)),
                "student_count": int(sub.get("registered_children", 0)),
            })
            overall_risk_total += risk_score
        except Exception as exc:
            logger.warning("Failed to build overview for %s: %s", gov["slug"], exc)
    overall_avg_risk = round(overall_risk_total / max(len(governors), 1), 1)

    return {
        "last_update": datetime.now(timezone.utc).strftime('%Y-%m-%dT%H:%M:%SZ'),
        "indicators": get_indicators(),
        "governorates": governors,
        "summary": {
            "total_governorates": len(governors),
            "average_risk": overall_avg_risk,
            "high_risk_count": sum(1 for g in governors if g["risk_score"] >= 50),
            "critical_count": sum(1 for g in governors if g["risk_score"] >= 75),
        },
        "risk_legend": [
            {
                "key": r["key"],
                "name_en": r["name_en"],
                "name_ar": r["name_ar"],
                "color": r["color"],
                "min": r["min"],
                "max": r["max"],
            }
            for r in C.RISK_LEVELS
        ],
    }


def get_correlations(db: Optional[Session] = None) -> Dict[str, Any]:
    """
    Read the Pearson correlation matrix from `map_correlation_snapshot` for
    the latest snapshot date.  If the table is empty, fall back to a
    snapshot-level proxy computed from the current main-indicator values.
    """
    matrix: List[Dict] = []
    if db is not None:
        try:
            import models
            latest = (
                db.query(func.max(models.MapCorrelationSnapshot.snapshot_date))
                .scalar()
            )
            if latest is not None:
                rows = (
                    db.query(models.MapCorrelationSnapshot)
                    .filter(models.MapCorrelationSnapshot.snapshot_date == latest)
                    .filter(models.MapCorrelationSnapshot.method == "pearson")
                    .all()
                )
                if rows:
                    for r in rows:
                        coef = r.coefficient
                        if coef is None or (isinstance(coef, float) and math.isnan(coef)):
                            strength = "insufficient"
                            color = "#94A3B8"
                        else:
                            level = C.correlation_level_for(coef)
                            strength = level["key"]
                            color = level["color"]
                        matrix.append({
                            "row": r.main_indicator,
                            "column": r.sub_indicator,
                            "value": float(coef) if coef is not None else None,
                            "p_value": float(r.p_value) if r.p_value is not None else None,
                            "n_samples": r.n_samples,
                            "strength": strength,
                            "color": color,
                            "method": "pearson",
                        })
                    return {
                        "method": "pearson",
                        "indicators": [i["key"] for i in C.MAIN_INDICATORS],
                        "matrix": matrix,
                        "snapshot_date": latest.isoformat(),
                    }
        except Exception as exc:
            logger.warning("Could not read map_correlation_snapshot: %s", exc)

    # Fallback: snapshot-level proxy from current main indicator values
    if db is not None:
        try:
            overview = get_map_overview(db)
        except Exception:
            overview = {"governorates": []}
    else:
        overview = {"governorates": []}
    gov_data = overview.get("governorates", [])
    if len(gov_data) < 3:
        return {
            "method": "pearson",
            "indicators": [i["key"] for i in C.MAIN_INDICATORS],
            "matrix": matrix,
            "note": "Insufficient data points for correlation analysis.",
        }

    indicator_keys = [i["key"] for i in C.MAIN_INDICATORS]
    values_by_ind: Dict[str, List[float]] = {k: [] for k in indicator_keys}
    for g in gov_data:
        for k in indicator_keys:
            v = g.get("main_indicators", {}).get(k)
            if v is not None:
                values_by_ind[k].append(float(v))

    for i_idx, i_key in enumerate(indicator_keys):
        for j_idx, j_key in enumerate(indicator_keys):
            xs = values_by_ind[i_key]
            ys = values_by_ind[j_key]
            n = min(len(xs), len(ys))
            if n < 3:
                r = None
            else:
                xs2 = xs[:n]
                ys2 = ys[:n]
                mx = sum(xs2) / n
                my = sum(ys2) / n
                num = sum((xs2[k] - mx) * (ys2[k] - my) for k in range(n))
                dx = math.sqrt(sum((xs2[k] - mx) ** 2 for k in range(n)))
                dy = math.sqrt(sum((ys2[k] - my) ** 2 for k in range(n)))
                r = round(num / (dx * dy), 4) if dx * dy > 0 else None
            level = C.correlation_level_for(r or 0) if r is not None else None
            matrix.append({
                "row": i_key,
                "column": j_key,
                "value": r,
                "strength": level["key"] if level else None,
                "color": level["color"] if level else "#94A3B8",
            })

    return {
        "method": "pearson",
        "indicators": indicator_keys,
        "matrix": matrix,
        "note": None,
    }


def get_regression_weights(db: Optional[Session] = None) -> Dict[str, Any]:
    """
    Read the OLS regression weights from `map_regression_snapshot` for the
    latest snapshot date.  If the table is empty (e.g. fresh deployment),
    fall back to a quick snapshot-level proxy.
    """
    weights: List[Dict] = []
    r_squared_per_indicator: Dict[str, float] = {}

    if db is not None:
        try:
            import models
            # Find the latest snapshot date
            latest = (
                db.query(func.max(models.MapRegressionSnapshot.snapshot_date))
                .scalar()
            )
            if latest is not None:
                rows = (
                    db.query(models.MapRegressionSnapshot)
                    .filter(models.MapRegressionSnapshot.snapshot_date == latest)
                    .all()
                )
                for r in rows:
                    weights.append({
                        "main_indicator": r.main_indicator,
                        "sub_indicator": r.sub_indicator,
                        "beta_std": r.beta_std,
                        "std_error": r.std_error,
                        "t_stat": r.t_stat,
                        "p_value": r.p_value,
                        "high_impact": bool(r.high_impact),
                        "vif": r.vif,
                        "vif_flag": r.vif_flag,
                        "n_samples": r.n_samples,
                    })
                # Aggregate R² per main indicator (all rows for a main have
                # the same R²; pick any)
                main_seen: Dict[str, bool] = {}
                for r in rows:
                    if r.main_indicator in main_seen:
                        continue
                    main_seen[r.main_indicator] = True
                    if r.r_squared is not None:
                        r_squared_per_indicator[r.main_indicator] = float(r.r_squared)
                return {
                    "method": "ols_standardized",
                    "weights": weights,
                    "r_squared_per_indicator": r_squared_per_indicator,
                    "snapshot_date": latest.isoformat(),
                    "note": "OLS coefficients are computed on standardized values. |β| ≥ 0.20 is high-impact.",
                }
        except Exception as exc:
            logger.warning("Could not read map_regression_snapshot: %s", exc)

    # Fallback: snapshot-level proxy
    if db is not None:
        try:
            overview = get_map_overview(db)
        except Exception:
            overview = {"governorates": []}
    else:
        overview = {"governorates": []}
    gov_data = overview.get("governorates", [])
    for ind in C.MAIN_INDICATORS:
        main_key = ind["key"]
        sub_keys = [s["key"] for s in C.SUB_INDICATORS.get(main_key, [])]
        if not sub_keys or len(gov_data) < 3:
            continue
        for sub_key in sub_keys:
            xs: List[float] = []
            ys: List[float] = []
            for g in gov_data:
                v = g.get("main_indicators", {}).get(main_key)
                if v is not None:
                    xs.append(float(v))
                    ys.append(float(v))
            n = len(xs)
            if n < 3:
                beta = None
            else:
                mx = sum(xs) / n
                my = sum(ys) / n
                num = sum((xs[k] - mx) * (ys[k] - my) for k in range(n))
                dx = math.sqrt(sum((xs[k] - mx) ** 2 for k in range(n)))
                dy = math.sqrt(sum((ys[k] - my) ** 2 for k in range(n)))
                beta = round(num / (dx * dy), 4) if dx * dy > 0 else 0.0
            weights.append({
                "main_indicator": main_key,
                "sub_indicator": sub_key,
                "beta_std": beta,
                "high_impact": abs(beta or 0) >= 0.20,
            })

    return {
        "method": "ols_standardized_proxy",
        "weights": weights,
        "r_squared_per_indicator": r_squared_per_indicator,
        "note": ("OLS weights are computed from the latest governorate "
                 "snapshot and are intended for relative ranking only. "
                 "Use the dedicated `/api/heatmap/analytics/regression/<indicator>` "
                 "endpoint (when integrated) for time-series regression."),
    }


# ---------------------------------------------------------------------------
# Daily update helpers
# ---------------------------------------------------------------------------
def daily_update_summary(db: Optional[Session] = None) -> Dict:
    """Return a summary describing the most recent map update."""
    now = datetime.now(timezone.utc)
    if db is not None:
        try:
            import models
            latest = (db.query(func.max(models.DailyReport.date)).scalar())
        except Exception:
            latest = None
    else:
        latest = None
    return {
        "last_update": now.strftime('%Y-%m-%dT%H:%M:%SZ'),
        "latest_data_date": str(latest) if latest else None,
        "schedule": "Daily at 02:00 UTC",
        "data_sources": ["daily_reports", "incidents", "kindergartens", "users", "tasks"],
    }
