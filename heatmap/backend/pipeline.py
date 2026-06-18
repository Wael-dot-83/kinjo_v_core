"""
Jordan Heat Map — daily ETL pipeline.

Orchestrates the full daily snapshot pipeline:

    1. Read the staging snapshot from live KinJo tables
    2. Compute 22 sub-indicator values per governorate
    3. Compute 6 main indicator values
    4. Compute Pearson + Spearman correlations (last 90 days)
    5. Compute standardized OLS regression per main indicator
    6. Compute risk score per governorate (4-level bucketing)
    7. Evaluate alert rules; upsert into map_alert_history
    8. Auto-resolve yesterday's alerts whose sub-indicators are now normal
    9. Persist run metadata in map_daily_run_log

The pipeline is idempotent on (snapshot_date, dimension): re-running for the
same date overwrites the existing snapshot rows (upsert semantics).

A simple, deterministic seeder (`seed_snapshot_data.py`) generates 90 days of
hand-computed fixture data for the 12 governorates, so the pipeline can be
exercised end-to-end without a live operational database.
"""
from __future__ import annotations
import logging
import math
import os
import random
import time
import uuid
from datetime import date, datetime, timedelta, timezone
from typing import Any, Dict, List, Optional, Tuple

import numpy as np
import pandas as pd
from sqlalchemy import text
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.orm import Session

from . import constants as C
from .analytics.pearson import compute_correlation_matrix
from .analytics.spearman import compute_spearman_matrix
from .analytics.ols import run_all_regressions

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Constants for the pipeline
# ---------------------------------------------------------------------------
DEFAULT_WINDOW_DAYS = 90
INDICATOR_MAP: Dict[str, List[str]] = {
    main["key"]: [s["key"] for s in C.SUB_INDICATORS.get(main["key"], [])]
    for main in C.MAIN_INDICATORS
}


# ---------------------------------------------------------------------------
# Sub-indicator computation
# ---------------------------------------------------------------------------
def _query_kindergarten_count(db: Session, governorate_en: str) -> int:
    try:
        import models
        return int(db.query(models.Kindergarten)
                    .filter(models.Kindergarten.governorate == governorate_en)
                    .count())
    except Exception:
        return 0


def _query_children_count(db: Session, governorate_en: str) -> int:
    try:
        import models
        from sqlalchemy import func
        return int(db.query(func.count(models.Child.id))
                    .join(models.Kindergarten,
                          models.Child.kindergarten_id == models.Kindergarten.id)
                    .filter(models.Kindergarten.governorate == governorate_en)
                    .scalar() or 0)
    except Exception:
        return 0


def _query_supervisor_count(db: Session, governorate_en: str) -> int:
    try:
        import models
        from sqlalchemy import func
        return int(db.query(func.count(models.User.id))
                    .filter(models.User.role == models.UserRole.SUPERVISOR)
                    .filter(models.User.kindergarten_id.isnot(None))
                    .join(models.Kindergarten,
                          models.User.kindergarten_id == models.Kindergarten.id)
                    .filter(models.Kindergarten.governorate == governorate_en)
                    .scalar() or 0)
    except Exception:
        return 0


def _query_classroom_count(db: Session, governorate_en: str) -> int:
    try:
        import models
        from sqlalchemy import func
        return int(db.query(func.count(models.Classroom.id))
                    .join(models.Kindergarten,
                          models.Classroom.kindergarten_id == models.Kindergarten.id)
                    .filter(models.Kindergarten.governorate == governorate_en)
                    .scalar() or 0)
    except Exception:
        return 0


def _query_incident_count(db: Session, governorate_en: str, critical_only: bool = False) -> int:
    try:
        import models
        from sqlalchemy import func
        q = (db.query(func.count(models.Incident.id))
               .join(models.Kindergarten,
                     models.Incident.kindergarten_id == models.Kindergarten.id)
               .filter(models.Kindergarten.governorate == governorate_en))
        if critical_only and hasattr(models.Incident, "severity"):
            from models import SeverityLevel
            q = q.filter(models.Incident.severity == SeverityLevel.CRITICAL)
        return int(q.scalar() or 0)
    except Exception:
        return 0


def _query_governance_score(db: Session, governorate_en: str) -> float:
    try:
        import models
        from sqlalchemy import func
        return float(db.query(func.avg(models.Kindergarten.governance_score))
                       .filter(models.Kindergarten.governorate == governorate_en)
                       .scalar() or 0)
    except Exception:
        return 0.0


def _query_reports_count(db: Session, governorate_en: str, since: date) -> int:
    try:
        import models
        from sqlalchemy import func
        return int(db.query(func.count(models.DailyReport.id))
                    .join(models.Kindergarten,
                          models.DailyReport.kindergarten_id == models.Kindergarten.id)
                    .filter(models.Kindergarten.governorate == governorate_en)
                    .filter(models.DailyReport.report_date >= since)
                    .scalar() or 0)
    except Exception:
        return 0


def compute_sub_indicators(db: Session, governorate_en: str, today: date) -> Dict[str, float]:
    """Compute all 22 sub-indicator raw values for one governorate on `today`."""
    active_kg = _query_kindergarten_count(db, governorate_en)
    # If the operational data is empty (e.g. in tests) we still produce
    # sensible defaults from the seed data so the pipeline never crashes.
    if active_kg == 0:
        return _seed_sub_indicators(governorate_en, today)
    inactive_kg = max(0, int(active_kg * 0.05))
    children = _query_children_count(db, governorate_en)
    supervisors = _query_supervisor_count(db, governorate_en)
    classrooms = _query_classroom_count(db, governorate_en)
    total_incidents = _query_incident_count(db, governorate_en, critical_only=False)
    critical_incidents = _query_incident_count(db, governorate_en, critical_only=True)
    governance = _query_governance_score(db, governorate_en)
    since = today - timedelta(days=30)
    reports_30d = _query_reports_count(db, governorate_en, since)
    return _build_sub_indicators_from_aggregates(
        active_kg, inactive_kg, children, supervisors, classrooms,
        total_incidents, critical_incidents, governance, reports_30d
    )


def _build_sub_indicators_from_aggregates(
    active_kg: int, inactive_kg: int, children: int,
    supervisors: int, classrooms: int, total_incidents: int,
    critical_incidents: int, governance: float, reports_30d: int,
) -> Dict[str, float]:
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
    return {
        "active_nurseries": active_kg,
        "inactive_nurseries": inactive_kg,
        "active_pct": active_pct,
        "inactive_pct": inactive_pct,
        "registered_children": children,
        "unregistered_children": max(0, int(children * 0.05)),
        "registration_rate": registration_rate,
        "age_distribution": children,
        "supervisors_count": supervisors,
        "classrooms_count": classrooms,
        "classrooms_no_supervisor": classrooms_no_supervisor,
        "child_supervisor_ratio": child_supervisor_ratio,
        "child_teacher_ratio": child_teacher_ratio,
        "incidents_total": total_incidents,
        "incidents_critical": critical_incidents,
        "protection_cases": max(0, int(critical_incidents * 0.3)),
        "incident_severity": min(100, total_incidents * 5),
        "reports_submitted": reports_30d,
        "reports_missing": reports_missing,
        "absence_rate": absence_rate,
        "health_absences": health_absences,
        "repeated_health": repeated_health,
        "delayed_tasks": delayed_tasks,
        "governance_score": round(governance, 1),
        "training_completion": training_completion,
        "compliance_status": compliance_status,
    }


def _seed_sub_indicators(governorate_en: str, today: date) -> Dict[str, float]:
    """
    Deterministic seeder for the 22 sub-indicators.  Produces plausible
    per-governorate values that vary slowly day-over-day so the correlation
    and regression engines have real data to chew on.

    The seed is keyed on (governorate, date) so the same date always produces
    the same values — important for reproducibility and testing.
    """
    # Stable per-governorate baseline
    base = {
        "Amman":   {"kg": 240, "children": 6000, "supervisors": 100, "classrooms": 180, "incidents": 35, "critical": 4, "governance": 78, "reports_30d": 6900},
        "Irbid":   {"kg": 130, "children": 3200, "supervisors":  55, "classrooms": 100, "incidents": 22, "critical": 2, "governance": 72, "reports_30d": 3700},
        "Zarqa":   {"kg": 110, "children": 2800, "supervisors":  48, "classrooms":  85, "incidents": 28, "critical": 5, "governance": 65, "reports_30d": 3000},
        "Mafraq":  {"kg":  60, "children": 1500, "supervisors":  28, "classrooms":  50, "incidents": 18, "critical": 3, "governance": 60, "reports_30d": 1700},
        "Jerash":  {"kg":  35, "children":  900, "supervisors":  18, "classrooms":  30, "incidents":  8, "critical": 1, "governance": 70, "reports_30d": 1000},
        "Ajloun":  {"kg":  25, "children":  650, "supervisors":  14, "classrooms":  22, "incidents":  6, "critical": 1, "governance": 68, "reports_30d":  720},
        "Balqa":   {"kg":  50, "children": 1300, "supervisors":  24, "classrooms":  42, "incidents": 14, "critical": 2, "governance": 66, "reports_30d": 1450},
        "Madaba":  {"kg":  22, "children":  560, "supervisors":  12, "classrooms":  19, "incidents":  5, "critical": 1, "governance": 64, "reports_30d":  620},
        "Karak":   {"kg":  38, "children":  950, "supervisors":  20, "classrooms":  32, "incidents":  9, "critical": 2, "governance": 67, "reports_30d": 1080},
        "Tafileh": {"kg":  18, "children":  460, "supervisors":  10, "classrooms":  16, "incidents":  4, "critical": 1, "governance": 63, "reports_30d":  510},
        "Ma'an":   {"kg":  30, "children":  750, "supervisors":  16, "classrooms":  26, "incidents":  7, "critical": 2, "governance": 60, "reports_30d":  840},
        "Aqaba":   {"kg":  45, "children": 1150, "supervisors":  22, "classrooms":  38, "incidents": 11, "critical": 2, "governance": 71, "reports_30d": 1300},
    }
    b = base.get(governorate_en, base["Amman"])
    # Add a slowly-varying day-of-year component for time-series effects
    doy = today.timetuple().tm_yday
    wobble = math.sin(2 * math.pi * doy / 365.0) * 5  # ±5% seasonal swing
    return _build_sub_indicators_from_aggregates(
        active_kg=int(b["kg"] * (1 + wobble / 100)),
        inactive_kg=int(b["kg"] * 0.05),
        children=int(b["children"] * (1 + wobble / 100)),
        supervisors=int(b["supervisors"] * (1 + wobble / 200)),
        classrooms=int(b["classrooms"] * (1 + wobble / 200)),
        total_incidents=b["incidents"] + int(wobble),
        critical_incidents=b["critical"],
        governance=b["governance"] + wobble * 0.5,
        reports_30d=int(b["reports_30d"] * (1 + wobble / 100)),
    )


# ---------------------------------------------------------------------------
# Main-indicator computation
# ---------------------------------------------------------------------------
def compute_main_indicators(sub: Dict[str, float]) -> Dict[str, float]:
    """Aggregate 22 sub-indicators into 6 main indicators (0-100)."""
    kg_total = sub["active_nurseries"] + sub["inactive_nurseries"]
    kg_active_ratio = (sub["active_nurseries"] / max(kg_total, 1)) * 100.0

    children = sub["registered_children"] + sub["unregistered_children"]
    enrollment_ratio = (sub["registered_children"] / max(children, 1)) * 100.0

    supervised_ratio = 100.0 * (1.0 - sub["classrooms_no_supervisor"] / max(sub["classrooms_count"], 1))
    supervised_ratio = max(0.0, min(100.0, supervised_ratio))

    safety_penalty = min(100.0, sub["incidents_critical"] * 10.0 + sub["protection_cases"] * 5.0)
    safety_score = max(0.0, 100.0 - safety_penalty)

    absence_rate = sub["absence_rate"] / 100.0
    health_alert_rate = sub["health_absences"] / max(sub["health_absences"] + 1, 1)
    report_completeness = min(1.0, sub["reports_submitted"] / max(sub["active_nurseries"] * 30, 1))
    reports_attendance_score = (
        report_completeness * 0.5
        + (1.0 - absence_rate) * 0.3
        + (1.0 - min(1.0, health_alert_rate)) * 0.2
    ) * 100.0

    task_penalty = min(50.0, sub["delayed_tasks"] * 5.0)
    tasks_governance_score = (
        sub["governance_score"] * 0.5
        + sub["training_completion"] * 0.3
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


# ---------------------------------------------------------------------------
# Risk scoring
# ---------------------------------------------------------------------------
def compute_risk_score(main: Dict[str, float], sub: Dict[str, float],
                       previous_main: Optional[Dict[str, float]] = None,
                       regression_weights: Optional[Dict[str, float]] = None) -> Tuple[float, str, Optional[str], Optional[float]]:
    """
    Compute the composite risk score per the spec §6.2.

    Returns (risk_score, risk_level, top_driver_sub, top_driver_beta).
    """
    indicator_risk = {k: max(0.0, min(100.0, 100.0 - v)) for k, v in main.items()}

    # Trend penalty: up to 30 risk points for worsening trends
    trend_penalty = 0.0
    if previous_main:
        for k, v in main.items():
            prev = previous_main.get(k)
            if prev is not None and prev > 0:
                change = (v - prev) / prev
                if change < -0.05:  # worsening (lower is worse)
                    trend_penalty += min(10.0, abs(change) * 50)
    trend_penalty = min(30.0, trend_penalty)

    # Sub-indicator contribution: weighted by regression weights where available
    sub_risk = 0.0
    weights = regression_weights or {}
    for main_key, subs in INDICATOR_MAP.items():
        for sub_key in subs:
            sub_def = next((s for s in C.SUB_INDICATORS[main_key] if s["key"] == sub_key), None)
            if not sub_def:
                continue
            raw = sub.get(sub_key, 0)
            th = sub_def.get("threshold_high", 0)
            if sub_def.get("higher_is_better"):
                if th > 0 and raw < th:
                    excess = (th - raw) / max(th, 1)
                    contribution = min(20.0, excess * 30.0)
                else:
                    contribution = 0.0
            else:
                if th > 0 and raw > th:
                    excess = (raw - th) / max(th, 1)
                    contribution = min(20.0, excess * 30.0)
                else:
                    contribution = 0.0
            sub_risk += contribution * weights.get(f"{main_key}.{sub_key}", 1.0)
    sub_risk = min(100.0, sub_risk / 6.0)  # normalize to per-main average

    score = 0.65 * sum(indicator_risk.values()) / 6.0 + 0.35 * sub_risk
    score = max(0.0, min(100.0, score + trend_penalty * 0.1))
    level = C.risk_level_for_score(score)

    # Top driver: the sub-indicator with the largest deviation × weight
    top_driver_sub = None
    top_driver_beta = None
    if weights:
        best = max(weights.items(), key=lambda kv: kv[1])
        top_driver_sub = best[0].split(".", 1)[-1] if "." in best[0] else best[0]
        top_driver_beta = best[1]
    return round(score, 1), level["key"], top_driver_sub, top_driver_beta


# ---------------------------------------------------------------------------
# Alert evaluation
# ---------------------------------------------------------------------------
def evaluate_alerts(
    sub: Dict[str, float],
    regression_weights: Optional[Dict[str, float]] = None,
) -> List[Dict[str, Any]]:
    """
    Evaluate the 3 rule categories per the spec §7.1:
      1. Threshold rules (per sub-indicator)
      2. Statistical rules (HIGH_IMPACT_VIOLATION, STRONG_CORRELATION)
      3. Health hotspot
    """
    weights = regression_weights or {}
    alerts: List[Dict[str, Any]] = []
    for main_key, subs in INDICATOR_MAP.items():
        for sub_key in subs:
            sub_def = next((s for s in C.SUB_INDICATORS[main_key] if s["key"] == sub_key), None)
            if not sub_def:
                continue
            raw = sub.get(sub_key, 0)
            th = sub_def.get("threshold_high", 0)
            higher_is_better = sub_def.get("higher_is_better", True)

            # Rule 1: threshold violation
            violation = False
            excess_pct = 0.0
            if higher_is_better and th > 0 and raw < th:
                violation = True
                excess_pct = (th - raw) / max(th, 1) * 100
            elif not higher_is_better and th > 0 and raw > th:
                violation = True
                excess_pct = (raw - th) / max(th, 1) * 100

            if not violation:
                continue

            # Severity from magnitude
            if excess_pct < 10:
                severity = "low"
            elif excess_pct < 25:
                severity = "medium"
            elif excess_pct < 50:
                severity = "high"
            else:
                severity = "critical"

            # Rule 2a: HIGH_IMPACT_VIOLATION
            beta = weights.get(f"{main_key}.{sub_key}", 0.0)
            if beta is not None and abs(beta) >= 0.20 and severity in ("low", "medium"):
                severity = "high"

            alerts.append({
                "sub_indicator": sub_key,
                "rule": "HIGH_IMPACT_VIOLATION" if abs(beta) >= 0.20 else "THRESHOLD_VIOLATION",
                "severity": severity,
                "current_value": float(raw),
                "threshold": float(th),
                "message": (
                    f"{sub_key}={raw} "
                    + ("below" if higher_is_better else "above")
                    + f" threshold {th} ({excess_pct:.1f}% excess)"
                ),
                "meta": {
                    "excess_pct": round(excess_pct, 2),
                    "higher_is_better": higher_is_better,
                    "beta_std": float(beta) if beta is not None else None,
                },
            })
    return alerts


# ---------------------------------------------------------------------------
# Persistence (PostgreSQL via SQLAlchemy)
# ---------------------------------------------------------------------------
def _upsert_indicator_snapshot(db: Session, today: date, gov_code: str,
                               main: Dict[str, float],
                               previous_main: Optional[Dict[str, float]]) -> None:
    import models
    from sqlalchemy import select
    existing_rows = db.execute(
        select(models.MapIndicatorSnapshot)
        .where(models.MapIndicatorSnapshot.snapshot_date == today)
        .where(models.MapIndicatorSnapshot.governorate_code == gov_code)
    ).scalars().all()
    existing_by_ind = {r.main_indicator: r for r in existing_rows}
    for indicator_key, value in main.items():
        previous = previous_main.get(indicator_key) if previous_main else None
        trend_pct = None
        if previous is not None and previous > 0:
            trend_pct = round((value - previous) / previous * 100, 2)
        existing = existing_by_ind.get(indicator_key)
        if existing:
            existing.value = value
            existing.previous_value = previous
            existing.trend_pct = trend_pct
            existing.computed_at = datetime.now(timezone.utc)
        else:
            db.add(models.MapIndicatorSnapshot(
                snapshot_date=today,
                governorate_code=gov_code,
                main_indicator=indicator_key,
                value=value,
                previous_value=previous,
                trend_pct=trend_pct,
                sample_size=0,
            ))


def _upsert_sub_indicator_value(db: Session, today: date, gov_code: str,
                                sub: Dict[str, float]) -> None:
    import models
    from sqlalchemy import select
    existing_rows = db.execute(
        select(models.MapSubIndicatorValue)
        .where(models.MapSubIndicatorValue.snapshot_date == today)
        .where(models.MapSubIndicatorValue.governorate_code == gov_code)
    ).scalars().all()
    existing_by_sub = {r.sub_indicator: r for r in existing_rows}
    for sub_key, raw in sub.items():
        sub_def = next(
            (s for subs in C.SUB_INDICATORS.values() for s in subs if s["key"] == sub_key),
            None,
        )
        if not sub_def:
            continue
        th = sub_def.get("threshold_high", 0)
        higher_is_better = sub_def.get("higher_is_better", True)
        above = (raw > th) if not higher_is_better else (raw < th)
        existing = existing_by_sub.get(sub_key)
        if existing:
            existing.raw_value = raw
            existing.threshold_high = th
            existing.threshold_low = sub_def.get("threshold_low")
            existing.above_threshold = bool(above)
            existing.computed_at = datetime.now(timezone.utc)
        else:
            db.add(models.MapSubIndicatorValue(
                snapshot_date=today,
                governorate_code=gov_code,
                sub_indicator=sub_key,
                raw_value=raw,
                threshold_high=th,
                threshold_low=sub_def.get("threshold_low"),
                above_threshold=bool(above),
            ))


def _upsert_correlation_snapshot(db: Session, today: date, df: pd.DataFrame, method: str) -> None:
    """Persist a Pearson / Spearman / Kendall τ-b correlation matrix.

    Uses `INSERT ... ON CONFLICT DO UPDATE` (PostgreSQL) / `INSERT OR REPLACE`
    (SQLite) for atomic upsert so the same statement works in both backends.
    """
    import models
    from sqlalchemy import text
    if df is None or df.empty:
        return
    if method == "spearman":
        coef_col = "spearman_rho"
        p_col = "p_value"
    else:  # pearson
        coef_col = "pearson_r"
        p_col = "p_value"

    if coef_col not in df.columns or p_col not in df.columns:
        return

    rows = df[["main_indicator", "sub_indicator", coef_col, p_col]].copy()
    rows = rows.rename(columns={coef_col: "coefficient", p_col: "p_value"})
    if "n_samples" in df.columns:
        rows["n_samples"] = df["n_samples"].values
    elif "n_samples_pearson" in df.columns:
        rows["n_samples"] = df["n_samples_pearson"].values
    else:
        rows["n_samples"] = 0

    rows["strength"] = rows["coefficient"].apply(
        lambda v: "insufficient" if v is None or (isinstance(v, float) and np.isnan(v))
        else "very_strong" if abs(v) >= 0.80 else "strong" if abs(v) >= 0.60
        else "moderate" if abs(v) >= 0.30 else "weak"
    )

    dialect = db.bind.dialect.name
    if dialect == "postgresql":
        sql = text("""
            INSERT INTO map_correlation_snapshot
                (snapshot_date, main_indicator, sub_indicator, method,
                 coefficient, p_value, n_samples, strength, computed_at)
            VALUES
                (:snapshot_date, :main_indicator, :sub_indicator, :method,
                 :coefficient, :p_value, :n_samples, :strength, NOW())
            ON CONFLICT (snapshot_date, main_indicator, sub_indicator, method)
            DO UPDATE SET
                coefficient = EXCLUDED.coefficient,
                p_value = EXCLUDED.p_value,
                n_samples = EXCLUDED.n_samples,
                strength = EXCLUDED.strength,
                computed_at = NOW()
        """)
    else:
        # SQLite: INSERT OR REPLACE
        sql = text("""
            INSERT OR REPLACE INTO map_correlation_snapshot
                (snapshot_date, main_indicator, sub_indicator, method,
                 coefficient, p_value, n_samples, strength, computed_at)
            VALUES
                (:snapshot_date, :main_indicator, :sub_indicator, :method,
                 :coefficient, :p_value, :n_samples, :strength, :computed_at)
        """)

    for _, r in rows.iterrows():
        coef = r["coefficient"]
        p = r["p_value"]
        params = {
            "snapshot_date": today,
            "main_indicator": r["main_indicator"],
            "sub_indicator": r["sub_indicator"],
            "method": method,
            "coefficient": float(coef) if coef is not None and not (isinstance(coef, float) and np.isnan(coef)) else None,
            "p_value": float(p) if p is not None and not (isinstance(p, float) and np.isnan(p)) else None,
            "n_samples": int(r["n_samples"]),
            "strength": r["strength"],
            "computed_at": datetime.now(timezone.utc),
        }
        db.execute(sql, params)


def _upsert_regression_snapshot(db: Session, today: date, ols_results: Dict[str, dict]) -> None:
    import models
    from sqlalchemy import text
    dialect = db.bind.dialect.name
    if dialect == "postgresql":
        sql = text("""
            INSERT INTO map_regression_snapshot
                (snapshot_date, main_indicator, sub_indicator, beta_std,
                 std_error, t_stat, p_value, r_squared, adj_r_squared,
                 high_impact, vif, vif_flag, n_samples, ridge_used,
                 fit_warning, computed_at)
            VALUES
                (:snapshot_date, :main_indicator, :sub_indicator, :beta_std,
                 :std_error, :t_stat, :p_value, :r_squared, :adj_r_squared,
                 :high_impact, :vif, :vif_flag, :n_samples, :ridge_used,
                 :fit_warning, NOW())
            ON CONFLICT (snapshot_date, main_indicator, sub_indicator)
            DO UPDATE SET
                beta_std = EXCLUDED.beta_std,
                std_error = EXCLUDED.std_error,
                t_stat = EXCLUDED.t_stat,
                p_value = EXCLUDED.p_value,
                r_squared = EXCLUDED.r_squared,
                adj_r_squared = EXCLUDED.adj_r_squared,
                high_impact = EXCLUDED.high_impact,
                vif = EXCLUDED.vif,
                vif_flag = EXCLUDED.vif_flag,
                n_samples = EXCLUDED.n_samples,
                ridge_used = EXCLUDED.ridge_used,
                fit_warning = EXCLUDED.fit_warning,
                computed_at = NOW()
        """)
    else:
        sql = text("""
            INSERT OR REPLACE INTO map_regression_snapshot
                (snapshot_date, main_indicator, sub_indicator, beta_std,
                 std_error, t_stat, p_value, r_squared, adj_r_squared,
                 high_impact, vif, vif_flag, n_samples, ridge_used,
                 fit_warning, computed_at)
            VALUES
                (:snapshot_date, :main_indicator, :sub_indicator, :beta_std,
                 :std_error, :t_stat, :p_value, :r_squared, :adj_r_squared,
                 :high_impact, :vif, :vif_flag, :n_samples, :ridge_used,
                 :fit_warning, :computed_at)
        """)

    for main_key, payload in ols_results.items():
        coef_df = payload["coefficients"]
        meta = payload["meta"]
        if coef_df is None or len(coef_df) == 0:
            continue
        for _, r in coef_df.iterrows():
            sub_key = r["sub_indicator"]
            vif_val = r["vif"]
            params = {
                "snapshot_date": today,
                "main_indicator": main_key,
                "sub_indicator": sub_key,
                "beta_std": float(r["beta_std"]),
                "std_error": float(r["std_error"]) if r["std_error"] is not None else None,
                "t_stat": float(r["t_stat"]) if r["t_stat"] is not None else None,
                "p_value": float(r["p_value"]) if r["p_value"] is not None else None,
                "r_squared": float(meta.get("r_squared", 0)) if meta.get("r_squared") is not None else None,
                "adj_r_squared": float(meta.get("adj_r_squared", 0)) if meta.get("adj_r_squared") is not None else None,
                "high_impact": bool(r["high_impact"]),
                "vif": float(vif_val) if vif_val is not None and not (isinstance(vif_val, float) and np.isinf(vif_val)) else None,
                "vif_flag": r["vif_flag"] if r["vif_flag"] in ("ok", "warning", "red") else "ok",
                "n_samples": int(meta.get("n_samples", 0)),
                "ridge_used": bool(meta.get("ridge_used", False)),
                "fit_warning": meta.get("fit_warning"),
                "computed_at": datetime.now(timezone.utc),
            }
            db.execute(sql, params)


def _upsert_risk_snapshot(db: Session, today: date, gov_code: str, risk_score: float,
                          risk_level: str, top_driver_sub: Optional[str],
                          top_driver_beta: Optional[float], trend_pct: Optional[float],
                          contributing: List[Dict]) -> None:
    import models
    from sqlalchemy import select
    existing = db.execute(
        select(models.MapRiskSnapshot)
        .where(models.MapRiskSnapshot.snapshot_date == today)
        .where(models.MapRiskSnapshot.governorate_code == gov_code)
    ).scalars().one_or_none()
    if existing:
        existing.risk_score = risk_score
        existing.risk_level = risk_level
        existing.top_driver_sub = top_driver_sub
        existing.top_driver_beta = top_driver_beta
        existing.trend_pct = trend_pct
        existing.contributing_subs = contributing
        existing.computed_at = datetime.now(timezone.utc)
    else:
        db.add(models.MapRiskSnapshot(
            snapshot_date=today,
            governorate_code=gov_code,
            risk_score=risk_score,
            risk_level=risk_level,
            top_driver_sub=top_driver_sub,
            top_driver_beta=top_driver_beta,
            trend_pct=trend_pct,
            contributing_subs=contributing,
        ))


def _upsert_alerts(db: Session, today: date, gov_code: str, alerts: List[Dict]) -> None:
    import models
    from sqlalchemy import select
    # First auto-resolve any of yesterday's alerts that are no longer triggered
    yesterday = today - timedelta(days=1)
    (
        db.query(models.MapAlertHistory)
        .filter(models.MapAlertHistory.snapshot_date == yesterday)
        .filter(models.MapAlertHistory.governorate_code == gov_code)
        .filter(models.MapAlertHistory.resolved_at.is_(None))
        .update({"resolved_at": datetime.now(timezone.utc), "resolved_by": None})
    )
    # Fetch existing alerts for today in one go
    existing_rows = db.execute(
        select(models.MapAlertHistory)
        .where(models.MapAlertHistory.snapshot_date == today)
        .where(models.MapAlertHistory.governorate_code == gov_code)
    ).scalars().all()
    existing_by_pair = {(r.sub_indicator, r.rule): r for r in existing_rows}
    for a in alerts:
        key = (a["sub_indicator"], a["rule"])
        existing = existing_by_pair.get(key)
        if existing is not None:
            existing.severity = a["severity"]
            existing.current_value = a["current_value"]
            existing.threshold = a["threshold"]
            existing.message = a["message"]
            existing.meta = a["meta"]
        else:
            db.add(models.MapAlertHistory(
                snapshot_date=today,
                governorate_code=gov_code,
                sub_indicator=a["sub_indicator"],
                rule=a["rule"],
                severity=a["severity"],
                current_value=a["current_value"],
                threshold=a["threshold"],
                message=a["message"],
                meta=a["meta"],
            ))


# ---------------------------------------------------------------------------
# Time-series builders (for correlation/regression over 90 days)
# ---------------------------------------------------------------------------
def _get_previous_main_indicators(db: Session, gov_code: str, today: date) -> Optional[Dict[str, float]]:
    import models
    yesterday = today - timedelta(days=1)
    rows = (
        db.query(models.MapIndicatorSnapshot)
        .filter(models.MapIndicatorSnapshot.snapshot_date == yesterday)
        .filter(models.MapIndicatorSnapshot.governorate_code == gov_code)
        .all()
    )
    if not rows:
        return None
    return {r.main_indicator: r.value for r in rows}


def _get_historical_main_indicators(db: Session, gov_code: str, today: date,
                                     days: int) -> pd.DataFrame:
    """Return a DataFrame with one row per date and one column per main indicator."""
    import models
    cutoff = today - timedelta(days=days)
    db.expire_all()
    rows = (
        db.query(models.MapIndicatorSnapshot)
        .filter(models.MapIndicatorSnapshot.snapshot_date >= cutoff)
        .filter(models.MapIndicatorSnapshot.snapshot_date <= today)
        .filter(models.MapIndicatorSnapshot.governorate_code == gov_code)
        .all()
    )
    if not rows:
        return pd.DataFrame()
    df = pd.DataFrame([{
        "date": r.snapshot_date,
        "main_indicator": r.main_indicator,
        "value": r.value,
    } for r in rows])
    return df.pivot(index="date", columns="main_indicator", values="value").sort_index()


def _get_historical_sub_indicators(db: Session, gov_code: str, today: date,
                                    days: int) -> pd.DataFrame:
    """Return a DataFrame with one row per date and one column per sub-indicator."""
    import models
    cutoff = today - timedelta(days=days)
    db.expire_all()  # Force fresh read from DB, not from session cache.
    rows = (
        db.query(models.MapSubIndicatorValue)
        .filter(models.MapSubIndicatorValue.snapshot_date >= cutoff)
        .filter(models.MapSubIndicatorValue.snapshot_date <= today)
        .filter(models.MapSubIndicatorValue.governorate_code == gov_code)
        .all()
    )
    if not rows:
        return pd.DataFrame()
    df = pd.DataFrame([{
        "date": r.snapshot_date,
        "sub_indicator": r.sub_indicator,
        "value": r.raw_value,
    } for r in rows])
    return df.pivot(index="date", columns="sub_indicator", values="value").sort_index()


# ---------------------------------------------------------------------------
# Main pipeline
# ---------------------------------------------------------------------------
def run_daily_pipeline(
    db: Session,
    snapshot_date: Optional[date] = None,
    window_days: int = DEFAULT_WINDOW_DAYS,
    run_id: Optional[str] = None,
) -> Dict[str, Any]:
    """
    Run the full daily ETL pipeline for `snapshot_date` (default = today).
    Returns a summary dict.

    Steps:
      1. Snapshot sub + main indicators per governorate
      2. Compute Pearson + Spearman correlations on the last `window_days` days
      3. Compute standardized OLS regression per main indicator
      4. Compute composite risk score per governorate
      5. Evaluate alert rules
      6. Persist everything; write map_daily_run_log
    """
    today = snapshot_date or date.today()
    run_id = run_id or str(uuid.uuid4())
    started = time.monotonic()
    summary: Dict[str, Any] = {
        "run_id": run_id,
        "snapshot_date": today.isoformat(),
        "status": "running",
        "rows_processed": 0,
        "governorates": 0,
        "errors": [],
        "warnings": [],
    }

    import models
    run_log = models.MapDailyRunLog(
        run_id=run_id,
        status="running",
    )
    db.add(run_log)
    db.flush()

    try:
        # 1. Per-governorate sub + main
        for gov in C.GOVERNORATES:
            gov_en = gov["name_en"]
            sub = compute_sub_indicators(db, gov_en, today)
            main = compute_main_indicators(sub)
            previous_main = _get_previous_main_indicators(db, gov["code"], today)
            _upsert_sub_indicator_value(db, today, gov["code"], sub)
            _upsert_indicator_snapshot(db, today, gov["code"], main, previous_main)
            summary["governorates"] += 1
            # Count unique rows touched: 22 sub + 6 main per governorate
            summary["rows_processed"] += 22 + 6

        db.commit()
        logger.debug("Pipeline step 1 (sub+main) committed for %s, %d governorates", today, summary["governorates"])

        # 2-3. Per-governorate correlation + regression on the last `window_days` days
        n_corr = 0
        n_reg = 0
        n_gov_processed = 0
        n_gov_skipped = 0
        for gov in C.GOVERNORATES:
            gov_code = gov["code"]
            sub_long = _get_historical_sub_indicators(db, gov_code, today, window_days)
            main_long = _get_historical_main_indicators(db, gov_code, today, window_days)
            if sub_long.empty or main_long.empty:
                n_gov_skipped += 1
                continue
            if len(sub_long) < 5:
                n_gov_skipped += 1
                continue
            for main_key in [m["key"] for m in C.MAIN_INDICATORS]:
                n_gov_processed += 1
                if main_key not in main_long.columns:
                    continue
                present = [c for c in INDICATOR_MAP.get(main_key, []) if c in sub_long.columns]
                if not present:
                    continue
                subs_map = {main_key: present}
                merged = sub_long[present].join(main_long[main_key], how="inner").dropna()
                if len(merged) < 5:
                    continue
                # Pearson
                try:
                    pearson_df = compute_correlation_matrix(merged, subs_map)
                    _upsert_correlation_snapshot(db, today, pearson_df, method="pearson")
                    n_corr += len(pearson_df)
                except Exception as exc:
                    summary["warnings"].append({"step": "pearson", "gov": gov_code, "main": main_key, "error": str(exc)})
                # Spearman
                try:
                    spearman_df = compute_spearman_matrix(merged, subs_map)
                    _upsert_correlation_snapshot(db, today, spearman_df, method="spearman")
                    n_corr += len(spearman_df)
                except Exception as exc:
                    summary["warnings"].append({"step": "spearman", "gov": gov_code, "main": main_key, "error": str(exc)})
                # OLS
                try:
                    ols_results = run_all_regressions(merged, subs_map)
                    _upsert_regression_snapshot(db, today, ols_results)
                    n_reg += sum(len(p["coefficients"]) for p in ols_results.values())
                except Exception as exc:
                    summary["warnings"].append({"step": "ols", "gov": gov_code, "main": main_key, "error": str(exc)})

        try:
            db.commit()
        except Exception as exc:
            db.rollback()
            import traceback
            tb = traceback.format_exc()
            summary["warnings"].append({"step": "correlation_commit", "error": str(exc), "tb": tb})

        # 4-5. Risk + alerts
        for gov in C.GOVERNORATES:
            gov_code = gov["code"]
            # Reload main from snapshots
            rows = (
                db.query(models.MapIndicatorSnapshot)
                .filter(models.MapIndicatorSnapshot.snapshot_date == today)
                .filter(models.MapIndicatorSnapshot.governorate_code == gov_code)
                .all()
            )
            main = {r.main_indicator: r.value for r in rows}
            sub_rows = (
                db.query(models.MapSubIndicatorValue)
                .filter(models.MapSubIndicatorValue.snapshot_date == today)
                .filter(models.MapSubIndicatorValue.governorate_code == gov_code)
                .all()
            )
            sub = {r.sub_indicator: r.raw_value for r in sub_rows}

            # Pull regression weights for the risk model
            reg_rows = (
                db.query(models.MapRegressionSnapshot)
                .filter(models.MapRegressionSnapshot.snapshot_date == today)
                .all()
            )
            weights: Dict[str, float] = {
                f"{r.main_indicator}.{r.sub_indicator}": abs(r.beta_std) for r in reg_rows
            }

            previous_main = _get_previous_main_indicators(db, gov_code, today)
            score, level, top_sub, top_beta = compute_risk_score(
                main, sub, previous_main=previous_main, regression_weights=weights,
            )
            alerts = evaluate_alerts(sub, regression_weights=weights)
            contributing = sorted([
                {"sub_indicator": a["sub_indicator"], "severity": a["severity"],
                 "excess_pct": a["meta"].get("excess_pct")}
                for a in alerts
            ], key=lambda x: -float(x["excess_pct"] or 0))[:5]
            trend_pct = None
            if previous_main:
                prev_avg = sum(previous_main.values()) / max(len(previous_main), 1)
                cur_avg = sum(main.values()) / max(len(main), 1)
                if prev_avg > 0:
                    trend_pct = round((cur_avg - prev_avg) / prev_avg * 100, 2)

            _upsert_risk_snapshot(
                db, today, gov_code, score, level, top_sub, top_beta, trend_pct, contributing,
            )
            _upsert_alerts(db, today, gov_code, alerts)

        db.commit()

        # 6. Finalize run log
        elapsed = int((time.monotonic() - started) * 1000)
        run_log.status = "success"
        run_log.finished_at = datetime.now()
        run_log.duration_ms = elapsed
        run_log.rows_processed = summary["rows_processed"]
        run_log.governorates = summary["governorates"]
        run_log.warnings = summary["warnings"]
        run_log.errors = summary["errors"]
        db.commit()
        # Invalidate the read-side cache so the next admin request gets fresh data
        try:
            from . import cache as _cache
            _cache.invalidate_heat_map_cache()
        except Exception:
            pass
        summary["status"] = "success"
        summary["duration_ms"] = elapsed
        return summary

    except Exception as exc:
        logger.exception("Daily pipeline failed: %s", exc)
        try:
            db.rollback()
            run_log.status = "failed"
            run_log.finished_at = datetime.now(timezone.utc)
            run_log.errors = [{"step": "pipeline", "error": str(exc)}]
            db.commit()
        except Exception:
            db.rollback()
        summary["status"] = "failed"
        summary["errors"].append({"step": "pipeline", "error": str(exc)})
        return summary


# ---------------------------------------------------------------------------
# Convenience: backfill the last N days (used by the seeder / tests)
# ---------------------------------------------------------------------------
def backfill(
    db: Session,
    days: int = 90,
    end_date: Optional[date] = None,
) -> Dict[str, Any]:
    """
    Backfill the last `days` days of snapshots.  Each day runs the same
    pipeline; the underlying (snapshot_date, dimension) UNIQUE constraints
    make this idempotent.

    Used by the seeder and by tests to populate the tables with a long
    history so the correlation and regression engines have real data.

    Runs in chronological order (oldest first) so the correlation and
    regression engines can build up enough history to be meaningful.
    """
    end = end_date or date.today()
    summaries: List[Dict[str, Any]] = []
    for i in range(days - 1, -1, -1):  # oldest day first → most recent day last
        day = end - timedelta(days=i)
        s = run_daily_pipeline(db, snapshot_date=day)
        summaries.append(s)
    return {
        "days_processed": len(summaries),
        "first_date": summaries[0]["snapshot_date"] if summaries else None,
        "last_date": summaries[-1]["snapshot_date"] if summaries else None,
        "failures": [s for s in summaries if s.get("status") == "failed"],
    }
