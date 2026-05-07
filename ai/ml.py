"""ai/ml.py — Phase 4 Predictive ML

Implements:
  4.1  Attendance absence probability per child (next 5 school days)
  4.3  Incident risk score per child (logistic regression proxy)
  4.4  Staff burnout signal (k-means clustering)

All predictions are written to ai_features (4.1, 4.3) or ai_manager_alerts (4.4).
Each run is logged in ai_job_logs.

Dependency guard: Phase 1 data quality fixes must be active before training;
the code handles sparse / missing data gracefully via try/except guards.

APScheduler wiring (add to main.py lifespan):
    from ai.ml import run_ml_daily_jobs
    scheduler.add_job(run_ml_daily_jobs, "cron", hour=4, minute=0,
                      id="ml_daily_jobs")
"""
import logging
from datetime import date, datetime, timedelta, timezone
from typing import Optional

import numpy as np
from sklearn.cluster import KMeans
from sklearn.linear_model import LogisticRegression
from sklearn.preprocessing import StandardScaler
from sqlalchemy import text
from sqlalchemy.orm import Session

from database import SessionLocal, init_db
from models import AIFeature, AIJobLog, AIManagerAlert

logger = logging.getLogger(__name__)

_RULE_VER = "ml-v1.0"
_MIN_SAMPLES_LOGISTIC = 10   # minimum rows needed to fit logistic regression
_MIN_SAMPLES_KMEANS   = 4    # minimum staff needed for k-means


def _now_utc() -> datetime:
    return datetime.now(timezone.utc)


def _start_job(db: Session, job_name: str) -> AIJobLog:
    job = AIJobLog(
        job_name=job_name,
        job_type="ml",
        started_at=_now_utc(),
        status="RUNNING",
        records_in=0,
        records_out=0,
        model_version=_RULE_VER,
        prompt_version="n/a",
    )
    db.add(job)
    db.flush()
    return job


def _finish_job(db: Session, job: AIJobLog, out: int, error: Optional[str] = None) -> None:
    job.finished_at = _now_utc()
    job.records_out = out
    job.status = "SUCCESS" if error is None else "FAILED"
    if error:
        job.error_message = error[:500]
    db.commit()


def _upsert_feature(
    db: Session,
    entity_type: str,
    entity_id: int,
    feature_name: str,
    feature_value: float,
    feature_json: Optional[dict] = None,
    valid_days: int = 7,
) -> None:
    """Insert or replace a single feature row (unique on entity_type+entity_id+feature_name)."""
    existing = (
        db.query(AIFeature)
        .filter(
            AIFeature.entity_type == entity_type,
            AIFeature.entity_id == entity_id,
            AIFeature.feature_name == feature_name,
        )
        .first()
    )
    expires = _now_utc() + timedelta(days=valid_days)
    if existing:
        existing.feature_value = feature_value
        existing.feature_json  = feature_json
        existing.computed_at   = _now_utc()
        existing.valid_until   = expires
        existing.model_version = _RULE_VER
    else:
        db.add(AIFeature(
            entity_type=entity_type,
            entity_id=entity_id,
            feature_name=feature_name,
            feature_value=feature_value,
            feature_json=feature_json,
            computed_at=_now_utc(),
            valid_until=expires,
            model_version=_RULE_VER,
        ))


# ---------------------------------------------------------------------------
# 4.1 — Attendance absence-probability forecast (next 5 school days)
# Strategy: per-child per-day-of-week historical absence rate over last 90 days
# is used as the predicted probability for each upcoming DOW.
# ---------------------------------------------------------------------------

_ATTENDANCE_HISTORY_SQL = text("""
    SELECT
        al.child_id,
        EXTRACT(DOW FROM al.date)::integer AS day_of_week,
        COUNT(*)                           AS present_count
    FROM attendance_logs al
    WHERE al.date BETWEEN CURRENT_DATE - 90 AND CURRENT_DATE - 1
      AND al.deleted_at IS NULL
    GROUP BY al.child_id, EXTRACT(DOW FROM al.date)::integer
""")

_SCHOOL_DAYS_SQL = text("""
    SELECT DISTINCT child_id
    FROM enrollment_applications
    WHERE status = 'ACTIVE'
      AND deleted_at IS NULL
""")

_OPERATING_DAYS_SQL = text("""
    SELECT date, EXTRACT(DOW FROM date)::integer AS day_of_week,
           kindergarten_id
    FROM operating_calendar
    WHERE is_open = TRUE
      AND date BETWEEN CURRENT_DATE AND CURRENT_DATE + 5
""")


def _run_attendance_forecast(db: Session) -> int:
    """Compute per-child absence probability for the next 5 school days."""
    job = _start_job(db, "attendance_forecast")
    try:
        # Build attendance frequency per child per DOW
        rows = db.execute(_ATTENDANCE_HISTORY_SQL).fetchall()
        child_dow: dict = {}
        for row in rows:
            cid = row.child_id
            dow = row.day_of_week
            if cid not in child_dow:
                child_dow[cid] = {}
            child_dow[cid][dow] = int(row.present_count)

        # Active children
        active_children = {r.child_id for r in db.execute(_SCHOOL_DAYS_SQL).fetchall()}

        # Upcoming open days
        upcoming = db.execute(_OPERATING_DAYS_SQL).fetchall()
        upcoming_dows = [(r.date, int(r.day_of_week)) for r in upcoming]

        if not upcoming_dows:
            _finish_job(db, job, 0)
            return 0

        count = 0
        for child_id in active_children:
            dow_map = child_dow.get(child_id, {})
            # Weeks in window: ~90 days / 7 ≈ 13 opportunities per DOW
            weeks = 90 / 7
            for upcoming_date, dow in upcoming_dows:
                present = dow_map.get(dow, 0)
                # Absence probability: (weeks - present) / weeks, min 0, max 1
                absence_prob = max(0.0, min(1.0, (weeks - present) / weeks))
                _upsert_feature(
                    db, "child", child_id,
                    f"absence_probability_{upcoming_date}",
                    round(absence_prob, 4),
                    {"date": str(upcoming_date), "day_of_week": dow, "present_in_90d": present},
                    valid_days=6,
                )
                count += 1

        _finish_job(db, job, count)
        return count
    except Exception as exc:
        db.rollback()
        _finish_job(db, job, 0, str(exc))
        logger.warning("attendance_forecast failed: %s", exc)
        return 0


# ---------------------------------------------------------------------------
# 4.3 — Incident risk score per child
# Features: age_months, attendance_rate_30d, incident_count_90d.
# A logistic regression is fitted when ≥ MIN_SAMPLES_LOGISTIC children exist
# with outcome labels (incident in last 30 days = 1, else 0).
# Falls back to a weighted heuristic score when data is insufficient.
# ---------------------------------------------------------------------------

_RISK_FEATURE_SQL = text("""
    SELECT
        c.id                                                       AS child_id,
        EXTRACT(MONTH FROM AGE(CURRENT_DATE, c.date_of_birth))::int AS age_months,
        COALESCE(
            (SELECT COUNT(*)::float / 30.0
               FROM attendance_logs al
              WHERE al.child_id = c.id
                AND al.date BETWEEN CURRENT_DATE - 30 AND CURRENT_DATE - 1
                AND al.deleted_at IS NULL), 0.0
        )                                                          AS attendance_rate_30d,
        COALESCE(
            (SELECT COUNT(*)
               FROM incidents i
              WHERE i.child_id = c.id
                AND i.occurred_at >= CURRENT_DATE - 90
                AND i.deleted_at IS NULL), 0
        )                                                          AS incident_count_90d,
        COALESCE(
            (SELECT COUNT(*) > 0
               FROM incidents i2
              WHERE i2.child_id = c.id
                AND i2.occurred_at >= CURRENT_DATE - 30
                AND i2.deleted_at IS NULL), FALSE
        )::int                                                     AS had_incident_30d
    FROM children c
    WHERE c.deleted_at IS NULL
""")


def _run_incident_risk_scores(db: Session) -> int:
    """Compute an incident risk score [0,1] per child; store in ai_features."""
    job = _start_job(db, "incident_risk_score")
    try:
        rows = db.execute(_RISK_FEATURE_SQL).fetchall()
        if not rows:
            _finish_job(db, job, 0)
            return 0

        child_ids  = [r.child_id        for r in rows]
        X_raw      = np.array([
            [r.age_months, float(r.attendance_rate_30d), int(r.incident_count_90d)]
            for r in rows
        ], dtype=float)
        y = np.array([int(r.had_incident_30d) for r in rows])

        scaler = StandardScaler()
        X = scaler.fit_transform(X_raw)

        if y.sum() >= 2 and (y == 0).sum() >= 2 and len(rows) >= _MIN_SAMPLES_LOGISTIC:
            # Enough labelled examples — fit logistic regression
            clf = LogisticRegression(max_iter=200, random_state=42)
            clf.fit(X, y)
            probs = clf.predict_proba(X)[:, 1]
        else:
            # Heuristic fallback: normalise incident_count_90d as proxy risk
            raw_risk = X_raw[:, 2] / max(X_raw[:, 2].max(), 1.0)
            # Penalise low attendance (absence correlates with risk)
            attendance_penalty = np.clip(1.0 - X_raw[:, 1], 0.0, 1.0) * 0.3
            probs = np.clip(raw_risk * 0.7 + attendance_penalty, 0.0, 1.0)

        count = 0
        for child_id, risk, row in zip(child_ids, probs, rows):
            _upsert_feature(
                db, "child", child_id,
                "incident_risk_score",
                round(float(risk), 4),
                {
                    "age_months": int(row.age_months),
                    "attendance_rate_30d": round(float(row.attendance_rate_30d), 4),
                    "incident_count_90d": int(row.incident_count_90d),
                },
                valid_days=7,
            )
            count += 1

        _finish_job(db, job, count)
        return count
    except Exception as exc:
        db.rollback()
        _finish_job(db, job, 0, str(exc))
        logger.warning("incident_risk_score failed: %s", exc)
        return 0


# ---------------------------------------------------------------------------
# 4.4 — Staff burnout signal (k-means clustering)
# Features: weekly hours logged, incident reports filed (last 30d),
#           daily reports submitted (last 30d).
# Cluster 0 = lower workload, Cluster 1 = higher workload (potential burnout).
# Emits HIGH-severity alert for each staff member in the high-load cluster.
# ---------------------------------------------------------------------------

_STAFF_WORKLOAD_SQL = text("""
    SELECT
        u.id AS user_id,
        u.kindergarten_id,
        COALESCE(
            (SELECT SUM(
                EXTRACT(EPOCH FROM (spl.end_at - spl.start_at)) / 3600.0
             )
               FROM staff_presence_logs spl
              WHERE spl.user_id = u.id
                AND spl.date >= CURRENT_DATE - 30), 0.0
        ) AS hours_30d,
        COALESCE(
            (SELECT COUNT(*)
               FROM incidents i
              WHERE i.reported_by = u.id
                AND i.occurred_at >= CURRENT_DATE - 30
                AND i.deleted_at IS NULL), 0
        ) AS incidents_filed_30d,
        COALESCE(
            (SELECT COUNT(*)
               FROM daily_reports dr
              WHERE dr.submitted_by = u.id
                AND dr.date >= CURRENT_DATE - 30), 0
        ) AS reports_submitted_30d
    FROM users u
    WHERE u.role IN ('SUPERVISOR', 'TEACHER')
      AND u.status = 'ACTIVE'
      AND u.kindergarten_id IS NOT NULL
""")


def _run_staff_burnout_detection(db: Session) -> int:
    """Cluster staff by workload; emit alert for high-load cluster members."""
    job = _start_job(db, "staff_burnout_detection")
    try:
        rows = db.execute(_STAFF_WORKLOAD_SQL).fetchall()
        if len(rows) < _MIN_SAMPLES_KMEANS:
            _finish_job(db, job, 0)
            return 0

        X_raw = np.array([
            [float(r.hours_30d), int(r.incidents_filed_30d), int(r.reports_submitted_30d)]
            for r in rows
        ], dtype=float)

        scaler = StandardScaler()
        X = scaler.fit_transform(X_raw)

        kmeans = KMeans(n_clusters=2, random_state=42, n_init=10)
        labels = kmeans.fit_predict(X)

        # High-load cluster = the one with higher mean total_hours
        cluster_means = [X_raw[labels == k, 0].mean() for k in range(2)]
        burnout_cluster = int(np.argmax(cluster_means))

        count = 0
        for i, row in enumerate(rows):
            if labels[i] != burnout_cluster:
                continue
            alert = AIManagerAlert(
                kindergarten_id=row.kindergarten_id,
                alert_type="STAFF_BURNOUT_SIGNAL",
                severity="HIGH",
                target_entity_type="user",
                target_entity_id=row.user_id,
                details={
                    "hours_30d": round(float(row.hours_30d), 1),
                    "incidents_filed_30d": int(row.incidents_filed_30d),
                    "reports_submitted_30d": int(row.reports_submitted_30d),
                    "cluster": burnout_cluster,
                },
                rule_version=_RULE_VER,
            )
            db.add(alert)
            count += 1

        _finish_job(db, job, count)
        return count
    except Exception as exc:
        db.rollback()
        _finish_job(db, job, 0, str(exc))
        logger.warning("staff_burnout_detection failed: %s", exc)
        return 0


# ---------------------------------------------------------------------------
# Public orchestrator
# ---------------------------------------------------------------------------

# ---------------------------------------------------------------------------
# 4.2 — Ministry seat demand forecast by governorate
# Linear regression on monthly enrollment counts per governorate over 6 months.
# Results are stored in ai_features as "seat_demand_forecast_{governorate}".
# ---------------------------------------------------------------------------

_DEMAND_HISTORY_SQL = text("""
    SELECT
        pp.home_governorate                     AS governorate,
        DATE_TRUNC('month', ea.submitted_at)    AS month,
        COUNT(*)                                AS enrollment_count
    FROM enrollment_applications ea
    JOIN children c ON c.id = ea.child_id
    JOIN parent_profiles pp ON pp.user_id = c.parent_id
    WHERE ea.submitted_at >= CURRENT_DATE - INTERVAL '12 months'
      AND ea.deleted_at IS NULL
    GROUP BY pp.home_governorate, DATE_TRUNC('month', ea.submitted_at)
    ORDER BY pp.home_governorate, month
""")

_DEMAND_HISTORY_SQL_SQ = text("""
    SELECT
        pp.home_governorate                     AS governorate,
        strftime('%Y-%m-01', ea.submitted_at)   AS month,
        COUNT(*)                                AS enrollment_count
    FROM enrollment_applications ea
    JOIN children c ON c.id = ea.child_id
    JOIN parent_profiles pp ON pp.user_id = c.parent_id
    WHERE ea.submitted_at >= date('now', '-12 months')
      AND ea.deleted_at IS NULL
    GROUP BY pp.home_governorate, strftime('%Y-%m-01', ea.submitted_at)
    ORDER BY pp.home_governorate, month
""")


def _run_seat_demand_forecast(db: Session) -> int:
    """Linear regression forecast of enrollment demand by governorate.

    Stores one ai_features row per governorate:
      feature_name  = "seat_demand_forecast"
      feature_json  = {"governorate": ..., "trend_per_month": ..., "forecast_6m": [...]}
    """
    from sqlalchemy import text as _text
    from database import engine as _engine

    job = _start_job(db, "seat_demand_forecast")
    try:
        sql = _DEMAND_HISTORY_SQL if _engine.dialect.name == "postgresql" else _DEMAND_HISTORY_SQL_SQ
        rows = db.execute(sql).fetchall()
        if not rows:
            _finish_job(db, job, 0)
            return 0

        # Group by governorate
        gov_data: dict = {}
        for row in rows:
            gov = row.governorate or "unknown"
            if gov not in gov_data:
                gov_data[gov] = []
            gov_data[gov].append(int(row.enrollment_count))

        count = 0
        for gov, monthly_counts in gov_data.items():
            if len(monthly_counts) < 2:
                continue

            x = np.arange(len(monthly_counts), dtype=float)
            y = np.array(monthly_counts, dtype=float)
            # Simple least-squares linear fit
            x_mean, y_mean = x.mean(), y.mean()
            slope = np.dot(x - x_mean, y - y_mean) / max(np.dot(x - x_mean, x - x_mean), 1e-9)
            intercept = y_mean - slope * x_mean

            # Forecast next 6 months
            n = len(monthly_counts)
            forecast = [
                round(max(0.0, intercept + slope * (n + i)), 1)
                for i in range(6)
            ]

            _upsert_feature(
                db, "governorate", 0,
                f"seat_demand_forecast_{gov}",
                round(float(slope), 4),
                {
                    "governorate":     gov,
                    "trend_per_month": round(float(slope), 4),
                    "forecast_6m":     forecast,
                    "history_months":  len(monthly_counts),
                },
                valid_days=30,
            )
            count += 1

        _finish_job(db, job, count)
        return count
    except Exception as exc:
        db.rollback()
        _finish_job(db, job, 0, str(exc))
        logger.warning("seat_demand_forecast failed: %s", exc)
        return 0


_ML_JOBS = [
    ("attendance_forecast",      _run_attendance_forecast),
    ("incident_risk_scores",     _run_incident_risk_scores),
    ("staff_burnout_detection",  _run_staff_burnout_detection),
    ("seat_demand_forecast",     _run_seat_demand_forecast),
]


async def run_ml_daily_jobs() -> None:
    """Run all Phase-4 ML prediction jobs.

    Each job is isolated: a failure in one does not abort the others.

    APScheduler configuration (main.py lifespan):
        from ai.ml import run_ml_daily_jobs
        scheduler.add_job(run_ml_daily_jobs, "cron", hour=4, minute=0,
                          id="ml_daily_jobs")
    """
    try:
        init_db()
    except Exception as exc:
        logger.warning("run_ml_daily_jobs: init_db: %s", exc)

    db: Session = SessionLocal()
    try:
        for name, fn in _ML_JOBS:
            try:
                n = fn(db)
                logger.info("ml_jobs: %s → %d records", name, n)
            except Exception as exc:
                db.rollback()
                logger.warning("ml_jobs: %s failed: %s", name, exc)
        db.commit()
    except Exception as exc:
        db.rollback()
        logger.error("run_ml_daily_jobs fatal: %s", exc)
    finally:
        db.close()
