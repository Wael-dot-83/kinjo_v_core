"""ai/insights.py — Phase 2 Rule-Based AI Insights Engine

Implements all Phase 2 AI capabilities from the KinJo Platform AI roadmap:
  2.5  Consecutive absence detection (window function — 3 consecutive open days)
  2.6  Allergy precaution alert at check-in (menu keyword match)
  2.7  Waitlist next-candidate recommendation (top candidate per class with open seats)
  2.8  Incident hotspot detection (Z-score > 2.0 over last 30 days)
  2.9  Ratio compliance day-of-week forecast (8-week moving average < 80%)
  2.11 Governance score drop alert (2 consecutive periods below 60)
  2.12 SLA breach detector for safeguarding cases

All results are written to ai_manager_alerts. Each sub-job is logged in ai_job_logs.

Configuration — add to APScheduler in main.py lifespan:
    from ai.insights import generate_daily_insights
    scheduler.add_job(generate_daily_insights, "cron", hour=2, minute=0,
                      id="ai_daily_insights")
    # Runs at 02:00 UTC daily.

Configuration — pg_cron alternative (run from psql as superuser):
    SELECT cron.schedule(
        'ai-daily-insights',
        '0 2 * * *',
        $$ SELECT http_post('http://localhost:8000/internal/ai/run-insights', '', 'text/plain') $$
    );
    -- Requires pg_cron and pgsql-http extensions. In practice, trigger via an
    -- internal FastAPI endpoint or a cron-driven Celery task.
"""
import logging
from datetime import date, datetime, timedelta, timezone
from typing import Optional

from sqlalchemy import text
from sqlalchemy.orm import Session

from database import SessionLocal, init_db
from models import AIManagerAlert, AIJobLog

logger = logging.getLogger(__name__)

RULE_VERSION = "rules-v1.0"

_JORDAN_TZ = timezone(timedelta(hours=3))


def _now_utc() -> datetime:
    return datetime.now(_JORDAN_TZ)


def _today_amman() -> date:
    return datetime.now(_JORDAN_TZ).date()


def _start_job(db: Session, job_name: str, job_type: str) -> AIJobLog:
    """Record job start in ai_job_logs."""
    job = AIJobLog(
        job_name=job_name,
        job_type=job_type,
        started_at=_now_utc(),
        status="RUNNING",
        records_in=0,
        records_out=0,
        model_version=RULE_VERSION,
        prompt_version="n/a",
    )
    db.add(job)
    db.flush()
    return job


def _finish_job(
    db: Session, job: AIJobLog, records_out: int, error: Optional[str] = None
) -> None:
    """Mark job complete or failed in ai_job_logs."""
    job.finished_at = _now_utc()
    job.records_out = records_out
    job.status = "SUCCESS" if error is None else "FAILED"
    if error:
        job.error_message = error
    db.commit()


def _emit_alert(
    db: Session,
    kindergarten_id: int,
    alert_type: str,
    severity: str,
    target_entity_type: str,
    target_entity_id: int,
    details: dict,
) -> None:
    """Insert one AIManagerAlert row (no commit — caller commits in bulk)."""
    alert = AIManagerAlert(
        kindergarten_id=kindergarten_id,
        alert_type=alert_type,
        severity=severity,
        target_entity_type=target_entity_type,
        target_entity_id=target_entity_id,
        details=details,
        rule_version=RULE_VERSION,
    )
    db.add(alert)


# ---------------------------------------------------------------------------
# Task 2.5 — Consecutive absence detection
# Alert fires when a child has been absent on every open school day in the
# last 3 days (including today).
# ---------------------------------------------------------------------------
_ABSENCE_SQL = text("""
    WITH open_days AS (
        SELECT oc.kindergarten_id, oc.date
        FROM operating_calendar oc
        WHERE oc.is_open = TRUE
          AND oc.date BETWEEN CURRENT_DATE - 14 AND CURRENT_DATE
    ),
    active_enrollments AS (
        SELECT e.child_id, e.kindergarten_id
        FROM enrollment_applications e
        WHERE e.status = 'ACTIVE'
          AND e.deleted_at IS NULL
    ),
    attendance_grid AS (
        SELECT
            ae.child_id,
            ae.kindergarten_id,
            od.date,
            (al.id IS NOT NULL) AS present
        FROM active_enrollments ae
        JOIN open_days od ON od.kindergarten_id = ae.kindergarten_id
        LEFT JOIN attendance_logs al
               ON al.child_id = ae.child_id
              AND al.date = od.date
              AND al.deleted_at IS NULL
    ),
    streak_calc AS (
        SELECT
            child_id,
            kindergarten_id,
            date,
            present,
            SUM(CASE WHEN present THEN 1 ELSE 0 END)
                OVER (
                    PARTITION BY child_id
                    ORDER BY date
                    ROWS BETWEEN 2 PRECEDING AND CURRENT ROW
                ) AS present_in_last_3
        FROM attendance_grid
    )
    SELECT DISTINCT child_id, kindergarten_id
    FROM streak_calc
    WHERE date = CURRENT_DATE
      AND present_in_last_3 = 0
""")


def _run_absence_detection(db: Session) -> int:
    """Detect children absent for 3+ consecutive open school days ending today."""
    job = _start_job(db, "absence_detection", "RULE")
    try:
        rows = db.execute(_ABSENCE_SQL).fetchall()
        count = 0
        for row in rows:
            _emit_alert(
                db=db,
                kindergarten_id=row.kindergarten_id,
                alert_type="CONSECUTIVE_ABSENCE",
                severity="MEDIUM",
                target_entity_type="child",
                target_entity_id=row.child_id,
                details={"consecutive_absent_days": 3, "as_of": str(_today_amman())},
            )
            count += 1
        _finish_job(db, job, count)
        return count
    except Exception as exc:
        db.rollback()
        _finish_job(db, job, 0, str(exc))
        logger.warning("absence_detection failed: %s", exc)
        return 0


# ---------------------------------------------------------------------------
# Task 2.6 — Allergy precaution alert
# Alert fires when a child with allergy_notes checks in today and that day's
# daily_report activities field contains known allergen keywords.
# ---------------------------------------------------------------------------
_ALLERGY_SQL = text("""
    SELECT
        al.child_id,
        al.class_id,
        ea.kindergarten_id,
        ch.allergy_notes
    FROM attendance_logs al
    JOIN children ch ON ch.id = al.child_id
    JOIN enrollment_applications ea
           ON ea.child_id = al.child_id
          AND ea.class_id = al.class_id
          AND ea.status   = 'ACTIVE'
          AND ea.deleted_at IS NULL
    WHERE al.date = CURRENT_DATE
      AND al.deleted_at IS NULL
      AND ch.allergy_notes IS NOT NULL
      AND ch.allergy_notes <> ''
      AND EXISTS (
            SELECT 1 FROM daily_reports dr
            WHERE dr.child_id = al.child_id
              AND dr.date = CURRENT_DATE
              AND (
                    LOWER(dr.activities) LIKE '%nut%'
                 OR LOWER(dr.activities) LIKE '%peanut%'
                 OR LOWER(dr.activities) LIKE '%dairy%'
                 OR LOWER(dr.activities) LIKE '%egg%'
                 OR LOWER(dr.activities) LIKE '%wheat%'
                 OR LOWER(dr.activities) LIKE '%gluten%'
                 OR LOWER(dr.activities) LIKE '%sesame%'
              )
      )
""")


def _run_allergy_alerts(db: Session) -> int:
    """Alert when a child with allergy_notes checks in and today's menu has triggers."""
    job = _start_job(db, "allergy_alert", "RULE")
    try:
        rows = db.execute(_ALLERGY_SQL).fetchall()
        count = 0
        for row in rows:
            _emit_alert(
                db=db,
                kindergarten_id=row.kindergarten_id,
                alert_type="ALLERGY_PRECAUTION",
                severity="HIGH",
                target_entity_type="child",
                target_entity_id=row.child_id,
                details={
                    "class_id": row.class_id,
                    "allergen_detected_in_menu": True,
                    "date": str(_today_amman()),
                },
            )
            count += 1
        _finish_job(db, job, count)
        return count
    except Exception as exc:
        db.rollback()
        _finish_job(db, job, 0, str(exc))
        logger.warning("allergy_alert failed: %s", exc)
        return 0


# ---------------------------------------------------------------------------
# Task 2.7 — Waitlist next-candidate recommendation
# Surfaces the top-priority waitlisted candidate per class that has open seats.
# ---------------------------------------------------------------------------
_WAITLIST_SQL = text("""
    WITH class_capacity AS (
        SELECT
            cl.id              AS class_id,
            cl.kindergarten_id,
            cl.capacity_total,
            COUNT(ea.id)       AS active_count
        FROM classes cl
        LEFT JOIN enrollment_applications ea
               ON ea.class_id  = cl.id
              AND ea.status IN ('ACTIVE', 'ACCEPTED')
              AND ea.deleted_at IS NULL
        WHERE cl.is_active = TRUE
          AND cl.deleted_at IS NULL
        GROUP BY cl.id, cl.kindergarten_id, cl.capacity_total
        HAVING COUNT(ea.id) < cl.capacity_total
    ),
    ranked_candidates AS (
        SELECT
            ea.class_id,
            ea.child_id,
            wl.id           AS waitlist_entry_id,
            wl.priority_score,
            cc.kindergarten_id,
            ROW_NUMBER() OVER (
                PARTITION BY ea.class_id
                ORDER BY wl.priority_score DESC, wl.created_at ASC
            ) AS rn
        FROM waitlist_entries wl
        JOIN enrollment_applications ea ON ea.id = wl.enrollment_id
        JOIN class_capacity cc ON cc.class_id = ea.class_id
        WHERE wl.status = 'WAITLISTED'
          AND ea.deleted_at IS NULL
    )
    SELECT class_id, child_id, waitlist_entry_id, priority_score, kindergarten_id
    FROM ranked_candidates
    WHERE rn = 1
""")


def _run_waitlist_recommendations(db: Session) -> int:
    """Recommend top waitlist candidate per class that has an open seat."""
    job = _start_job(db, "waitlist_recommendation", "RULE")
    try:
        rows = db.execute(_WAITLIST_SQL).fetchall()
        count = 0
        for row in rows:
            _emit_alert(
                db=db,
                kindergarten_id=row.kindergarten_id,
                alert_type="WAITLIST_SEAT_AVAILABLE",
                severity="LOW",
                target_entity_type="waitlist_entry",
                target_entity_id=row.waitlist_entry_id,
                details={
                    "class_id": row.class_id,
                    "child_id": row.child_id,
                    "priority_score": float(row.priority_score),
                },
            )
            count += 1
        _finish_job(db, job, count)
        return count
    except Exception as exc:
        db.rollback()
        _finish_job(db, job, 0, str(exc))
        logger.warning("waitlist_recommendation failed: %s", exc)
        return 0


# ---------------------------------------------------------------------------
# Task 2.8 — Incident hotspot detection (Z-score)
# Alert fires for any class whose incident count in the last 30 days has a
# Z-score > 2.0 relative to all classes in the same period.
# ---------------------------------------------------------------------------
_HOTSPOT_SQL = text("""
    WITH class_counts AS (
        SELECT
            class_id,
            kindergarten_id,
            COUNT(*) AS incident_count
        FROM incidents
        WHERE occurred_at >= CURRENT_DATE - 30
          AND deleted_at IS NULL
          AND class_id IS NOT NULL
        GROUP BY class_id, kindergarten_id
    ),
    stats AS (
        SELECT
            AVG(incident_count)    AS mean,
            STDDEV(incident_count) AS stddev
        FROM class_counts
    )
    SELECT
        cc.class_id,
        cc.kindergarten_id,
        cc.incident_count,
        s.mean,
        s.stddev,
        (cc.incident_count - s.mean) / NULLIF(s.stddev, 0) AS z_score
    FROM class_counts cc
    CROSS JOIN stats s
    WHERE s.stddev > 0
      AND (cc.incident_count - s.mean) / s.stddev > 2.0
""")


def _run_incident_hotspots(db: Session) -> int:
    """Detect classes with abnormally high incident rates (Z-score > 2.0, last 30 days)."""
    job = _start_job(db, "incident_hotspot", "RULE")
    try:
        rows = db.execute(_HOTSPOT_SQL).fetchall()
        count = 0
        for row in rows:
            _emit_alert(
                db=db,
                kindergarten_id=row.kindergarten_id,
                alert_type="INCIDENT_HOTSPOT",
                severity="HIGH",
                target_entity_type="class",
                target_entity_id=row.class_id,
                details={
                    "incident_count_30d": int(row.incident_count),
                    "z_score": round(float(row.z_score), 2),
                    "mean": round(float(row.mean), 2),
                    "period_days": 30,
                },
            )
            count += 1
        _finish_job(db, job, count)
        return count
    except Exception as exc:
        db.rollback()
        _finish_job(db, job, 0, str(exc))
        logger.warning("incident_hotspot failed: %s", exc)
        return 0


# ---------------------------------------------------------------------------
# Task 2.9 — Ratio compliance day-of-week forecast
# Uses an 8-week moving average of ratio compliance per day-of-week.
# Alert fires if the projected compliance for a day of week in the next 3
# working days falls below 80 %.
# ---------------------------------------------------------------------------
_RATIO_SQL = text("""
    WITH weekly_dow AS (
        SELECT
            kindergarten_id,
            EXTRACT(DOW FROM date)::integer AS day_of_week,
            AVG(
                CASE WHEN operating_minutes > 0
                     THEN compliant_minutes::float / operating_minutes
                     ELSE NULL
                END
            ) AS avg_compliance_rate
        FROM ratio_compliance
        WHERE date >= CURRENT_DATE - 56
        GROUP BY kindergarten_id, EXTRACT(DOW FROM date)::integer
        HAVING COUNT(*) >= 3
    )
    SELECT kindergarten_id, day_of_week, avg_compliance_rate
    FROM weekly_dow
    WHERE avg_compliance_rate < 0.80
""")


def _run_ratio_compliance_forecast(db: Session) -> int:
    """Alert when projected day-of-week ratio compliance drops below 80%."""
    job = _start_job(db, "ratio_compliance_forecast", "RULE")
    try:
        rows = db.execute(_RATIO_SQL).fetchall()
        # Build set of upcoming 3 weekday DOW values (Postgres: 0=Sun,1=Mon..6=Sat)
        upcoming_dows: set[int] = set()
        for delta in range(1, 4):
            d = _today_amman() + timedelta(days=delta)
            upcoming_dows.add(d.weekday() + 1 if d.weekday() < 6 else 0)  # convert python DOW to pg DOW
        count = 0
        for row in rows:
            if int(row.day_of_week) in upcoming_dows:
                _emit_alert(
                    db=db,
                    kindergarten_id=row.kindergarten_id,
                    alert_type="RATIO_COMPLIANCE_RISK",
                    severity="MEDIUM",
                    target_entity_type="kindergarten",
                    target_entity_id=row.kindergarten_id,
                    details={
                        "projected_day_of_week": int(row.day_of_week),
                        "avg_compliance_rate": round(float(row.avg_compliance_rate), 3),
                        "threshold": 0.80,
                    },
                )
                count += 1
        _finish_job(db, job, count)
        return count
    except Exception as exc:
        db.rollback()
        _finish_job(db, job, 0, str(exc))
        logger.warning("ratio_compliance_forecast failed: %s", exc)
        return 0


# ---------------------------------------------------------------------------
# Task 2.11 — Governance score drop alert
# Alert fires when a kindergarten has had 2 consecutive governance scoring
# periods both below 60.
# ---------------------------------------------------------------------------
_GOVERNANCE_SQL = text("""
    WITH scored AS (
        SELECT
            kindergarten_id,
            period_start,
            final_governance_score,
            LAG(final_governance_score) OVER (
                PARTITION BY kindergarten_id ORDER BY period_start
            ) AS prev_score
        FROM governance_scores
    )
    SELECT kindergarten_id, period_start, final_governance_score, prev_score
    FROM scored
    WHERE final_governance_score < 60
      AND prev_score < 60
""")


def _run_governance_drop_alerts(db: Session) -> int:
    """Alert when a kindergarten has 2 consecutive governance periods below 60."""
    job = _start_job(db, "governance_drop_alert", "RULE")
    try:
        rows = db.execute(_GOVERNANCE_SQL).fetchall()
        count = 0
        for row in rows:
            _emit_alert(
                db=db,
                kindergarten_id=row.kindergarten_id,
                alert_type="GOVERNANCE_SCORE_DROP",
                severity="HIGH",
                target_entity_type="kindergarten",
                target_entity_id=row.kindergarten_id,
                details={
                    "current_score": round(float(row.final_governance_score), 2),
                    "previous_score": round(float(row.prev_score), 2),
                    "period_start": str(row.period_start),
                },
            )
            count += 1
        _finish_job(db, job, count)
        return count
    except Exception as exc:
        db.rollback()
        _finish_job(db, job, 0, str(exc))
        logger.warning("governance_drop_alert failed: %s", exc)
        return 0


# ---------------------------------------------------------------------------
# Task 2.12 — SLA breach detector for safeguarding
# Alert fires for every open safeguarding case whose escalation SLA deadline
# has passed.
# ---------------------------------------------------------------------------
_SLA_SQL = text("""
    SELECT id, kindergarten_id, sla_escalation_deadline, status
    FROM safeguarding_cases
    WHERE sla_escalation_deadline < NOW()
      AND status NOT IN ('ESCALATED', 'CLOSED', 'PENDING_CLOSURE')
""")


def _run_sla_breach_detection(db: Session) -> int:
    """Alert for safeguarding cases that have breached their escalation SLA."""
    job = _start_job(db, "sla_breach_detection", "RULE")
    try:
        rows = db.execute(_SLA_SQL).fetchall()
        count = 0
        for row in rows:
            _emit_alert(
                db=db,
                kindergarten_id=row.kindergarten_id,
                alert_type="SAFEGUARDING_SLA_BREACH",
                severity="CRITICAL",
                target_entity_type="safeguarding_case",
                target_entity_id=row.id,
                details={
                    "sla_deadline": str(row.sla_escalation_deadline),
                    "current_status": str(row.status),
                },
            )
            count += 1
        _finish_job(db, job, count)
        return count
    except Exception as exc:
        db.rollback()
        _finish_job(db, job, 0, str(exc))
        logger.warning("sla_breach_detection failed: %s", exc)
        return 0


# ---------------------------------------------------------------------------
# Public orchestrator
# ---------------------------------------------------------------------------

_JOBS = [
    ("absence_detection",        _run_absence_detection),
    ("allergy_alerts",           _run_allergy_alerts),
    ("waitlist_recommendations", _run_waitlist_recommendations),
    ("incident_hotspots",        _run_incident_hotspots),
    ("ratio_compliance_forecast", _run_ratio_compliance_forecast),
    ("governance_drop_alerts",   _run_governance_drop_alerts),
    ("sla_breach_detection",     _run_sla_breach_detection),
]


async def generate_daily_insights() -> None:
    """Run all Phase-2 rule-based AI insight jobs against the production database.

    Each job runs in isolation: a failure in one job is logged and skipped without
    aborting the remaining jobs.

    APScheduler configuration (add to main.py lifespan):
        from ai.insights import generate_daily_insights
        scheduler.add_job(generate_daily_insights, "cron", hour=2, minute=0,
                          id="ai_daily_insights")

    pg_cron alternative (run as DB superuser):
        SELECT cron.schedule(
            'ai-daily-insights', '0 2 * * *',
            $$ NOTIFY ai_worker, 'run_daily_insights' $$
        );
        -- Then listen in a Python worker:  asyncpg LISTEN 'ai_worker', call generate_daily_insights()
    """
    # Ensure all tables exist (important in SQLite test/dev environments)
    try:
        init_db()
    except Exception as exc:
        logger.warning("generate_daily_insights: init_db failed: %s", exc)

    db: Session = SessionLocal()
    totals: dict = {}
    try:
        for name, fn in _JOBS:
            try:
                count = fn(db)
                totals[name] = count
                logger.info("ai_insights: %s produced %d alerts", name, count)
            except Exception as job_exc:
                db.rollback()
                totals[name] = 0
                logger.warning("ai_insights: %s skipped due to error: %s", name, job_exc)
        db.commit()
        logger.info("generate_daily_insights complete: %s", totals)
    except Exception as exc:
        db.rollback()
        logger.error("generate_daily_insights fatal error: %s", exc)
        raise
    finally:
        db.close()
