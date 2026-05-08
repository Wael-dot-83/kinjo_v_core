"""government_api.py — Government Data Portal Endpoints

Implements:
  4.2  GET /ministry/enrollment-forecast?governorate=&year=
       GET /ministry/enrollment-forecast/export.csv
  4.3  GET /family/quality-certificates?nursery_id=
  4.4  GET /development/dashboard
  4.5  GET /census/child-density?governorate=&district=

Security:
  - JWT authentication required (ADMIN or MANAGER role).
  - All requests logged to audit_logs with entity_type='government_api'.
  - Rate limit: 100 requests / hour / IP (slowapi).

APScheduler — daily refresh of mv_development_dashboard (add to main.py lifespan):
    from government_api import refresh_development_dashboard
    scheduler.add_job(refresh_development_dashboard, "cron", hour=3, minute=0,
                      id="refresh_dev_dashboard")
    # Refreshes the materialized view each day at 03:00 UTC.

pg_cron alternative (run from psql as superuser):
    SELECT cron.schedule(
        'refresh-dev-dashboard',
        '0 3 * * *',
        $$ REFRESH MATERIALIZED VIEW CONCURRENTLY mv_development_dashboard $$
    );
"""
import csv
import io
import json
import math
from datetime import date, datetime, timedelta, timezone
from typing import List, Optional

import numpy as np
from fastapi import APIRouter, Depends, HTTPException, Query, Request
from fastapi.responses import StreamingResponse
from pydantic import BaseModel
from sklearn.linear_model import LinearRegression
from sqlalchemy import text
from sqlalchemy.orm import Session

import models
from config import settings
from database import get_db
from dependencies import get_current_user
from slowapi import Limiter
from slowapi.util import get_remote_address

router = APIRouter(tags=["government"])
limiter = Limiter(key_func=get_remote_address)
if settings.TESTING:
    limiter.enabled = False


# ---------------------------------------------------------------------------
# Jordan governorate geodata
# Centroid coordinates and official area in km² used for density calculations
# and as a fallback when address-level geocoding is unavailable.
# ---------------------------------------------------------------------------
_GOVERNORATE_CENTROIDS: dict = {
    "عمان":    (31.9454, 35.9284),
    "إربد":    (32.5556, 35.8500),
    "الزرقاء": (32.0728, 36.0878),
    "العقبة":  (29.5267, 35.0066),
    "المفرق":  (32.3429, 36.2047),
    "جرش":     (32.2795, 35.8987),
    "عجلون":   (32.3322, 35.7509),
    "الطفيلة": (30.8413, 35.6049),
    "الكرك":   (31.1817, 35.7037),
    "معان":    (30.1945, 35.7342),
    "السلط":   (32.0382, 35.7271),
    "مادبا":   (31.7168, 35.7942),
}

_GOVERNORATE_AREA_KM2: dict = {
    "عمان":    7579.0,
    "إربد":    1572.0,
    "الزرقاء": 4761.0,
    "العقبة":  6905.0,
    "المفرق":  26551.0,
    "جرش":     410.0,
    "عجلون":   420.0,
    "الطفيلة": 2209.0,
    "الكرك":   3217.0,
    "معان":    32832.0,
    "السلط":   1075.0,
    "مادبا":   2008.0,
}


def geocode_address(address_line: str, governorate: str) -> tuple:
    """Placeholder geocoder — returns the centroid of the named governorate.

    In production, replace this body with a call to a real geocoding service
    (e.g., Nominatim, Google Maps Geocoding API, or a local PostGIS lookup).

    Args:
        address_line: Full address string (unused in placeholder).
        governorate:  Arabic governorate name.

    Returns:
        (latitude, longitude) float tuple.
    """
    return _GOVERNORATE_CENTROIDS.get(governorate, (31.9454, 35.9284))


# ---------------------------------------------------------------------------
# Audit helper
# ---------------------------------------------------------------------------

def _log_government_request(
    db: Session,
    request: Request,
    endpoint: str,
    user: Optional[models.User] = None,
) -> None:
    """Log every government API request to audit_logs (non-fatal)."""
    ip = request.client.host if request.client else None
    try:
        log = models.AuditLog(
            user_id=user.id if user else None,
            action="GOVERNMENT_API_ACCESS",
            entity_type="government_api",
            entity_id=None,
            details={"endpoint": endpoint, "params": dict(request.query_params)},
            actor_role=user.role.value if user else None,
            ip_address=ip,
            sensitivity_level=3,
        )
        db.add(log)
        db.commit()
    except Exception:
        db.rollback()


# ===========================================================================
# 4.2  Enrollment demand forecast — Ministry of Education
# ===========================================================================

class ForecastRow(BaseModel):
    governorate: str
    eligible_children: int
    predicted_count: int
    confidence_lower: int
    confidence_upper: int
    model_r2: float


class ForecastResponse(BaseModel):
    year: int
    generated_at: str
    forecasts: List[ForecastRow]


# Historical cohort: eligible children (aged 5-6 at Sep-1 of enroll_year) vs
# actual enrollments by governorate and year.
_HIST_SQL = text("""
    SELECT
        pp.home_governorate                                         AS governorate,
        EXTRACT(YEAR FROM ea.enrollment_start_date)::integer        AS enroll_year,
        COUNT(DISTINCT c.id)                                        AS eligible_count,
        COUNT(DISTINCT CASE WHEN ea.status IN ('ACTIVE','ACCEPTED')
                            THEN ea.id END)                         AS enrolled_count
    FROM children c
    JOIN parent_profiles pp ON pp.id = c.parent_id
    LEFT JOIN enrollment_applications ea
           ON ea.child_id = c.id
          AND ea.deleted_at IS NULL
          AND ea.enrollment_start_date IS NOT NULL
    WHERE c.deleted_at IS NULL
    GROUP BY pp.home_governorate,
             EXTRACT(YEAR FROM ea.enrollment_start_date)::integer
    HAVING COUNT(DISTINCT c.id) > 0
    ORDER BY pp.home_governorate, enroll_year
""")

# SQLite-compatible historical cohort
_HIST_SQLITE_SQL = text("""
    SELECT
        pp.home_governorate                                         AS governorate,
        CAST(strftime('%Y', ea.enrollment_start_date) AS INTEGER)   AS enroll_year,
        COUNT(DISTINCT c.id)                                        AS eligible_count,
        COUNT(DISTINCT CASE WHEN ea.status IN ('ACTIVE','ACCEPTED')
                            THEN ea.id END)                         AS enrolled_count
    FROM children c
    JOIN parent_profiles pp ON pp.id = c.parent_id
    LEFT JOIN enrollment_applications ea
           ON ea.child_id = c.id
          AND ea.deleted_at IS NULL
          AND ea.enrollment_start_date IS NOT NULL
    WHERE c.deleted_at IS NULL
    GROUP BY pp.home_governorate,
             CAST(strftime('%Y', ea.enrollment_start_date) AS INTEGER)
    HAVING COUNT(DISTINCT c.id) > 0
    ORDER BY pp.home_governorate, enroll_year
""")

# Children aged 5-6 at Sep-1 of target year, grouped by governorate.
_ELIGIBLE_SQL = text("""
    SELECT
        pp.home_governorate AS governorate,
        COUNT(c.id)         AS eligible_count
    FROM children c
    JOIN parent_profiles pp ON pp.id = c.parent_id
    WHERE c.deleted_at IS NULL
      AND DATE_PART('year', AGE(
              MAKE_DATE(CAST(:year AS INTEGER), 9, 1), c.date_of_birth
          )) BETWEEN 5 AND 6
    GROUP BY pp.home_governorate
""")

# SQLite-compatible fallback for tests (age approximation via date arithmetic)
_ELIGIBLE_SQLITE_SQL = text("""
    SELECT
        pp.home_governorate AS governorate,
        COUNT(c.id)         AS eligible_count
    FROM children c
    JOIN parent_profiles pp ON pp.id = c.parent_id
    WHERE c.deleted_at IS NULL
      AND c.date_of_birth <= date(:sep1, '-5 years')
      AND c.date_of_birth >= date(:sep1, '-7 years')
    GROUP BY pp.home_governorate
""")


def _fit_forecast(
    eligible_counts: list,
    enrolled_counts: list,
    target_eligible: float,
) -> tuple:
    """Fit LinearRegression(enrolled ~ eligible) and return (pred, lower, upper, r2).

    Falls back to a mean-ratio estimate when fewer than 2 training samples exist.
    Confidence interval width is derived from the residual standard deviation.
    """
    n = len(eligible_counts)
    if n < 2:
        if sum(eligible_counts) == 0:
            pred = target_eligible * 0.60
        else:
            rate = sum(enrolled_counts) / sum(eligible_counts)
            pred = target_eligible * rate
        margin = pred * 0.20
        return pred, max(0.0, pred - margin), pred + margin, 0.0

    X = np.array(eligible_counts, dtype=float).reshape(-1, 1)
    y = np.array(enrolled_counts, dtype=float)
    model = LinearRegression()
    model.fit(X, y)
    pred = float(model.predict([[target_eligible]])[0])
    r2 = float(model.score(X, y))

    residuals = y - model.predict(X).ravel()
    s = float(np.std(residuals, ddof=min(2, n - 1)))
    # Conservative t-multiplier: 1.65 (large n) + correction for small samples
    t = 1.65 + (2.0 / max(n - 2, 1))
    margin = t * s * math.sqrt(1.0 + 1.0 / n)
    return pred, max(0.0, pred - margin), pred + margin, max(0.0, r2)


def _build_forecasts(db: Session, target_year: int, governorate: Optional[str]) -> List[ForecastRow]:
    """Shared computation used by both JSON and CSV endpoints."""
    # Historical cohort data (dialect-aware)
    dialect = db.bind.dialect.name if db.bind else "postgresql"
    hist_sql = _HIST_SQLITE_SQL if dialect == "sqlite" else _HIST_SQL
    hist_rows = db.execute(hist_sql).fetchall()
    hist: dict = {}
    for row in hist_rows:
        gov = row.governorate
        if gov not in hist:
            hist[gov] = {"eligible": [], "enrolled": []}
        hist[gov]["eligible"].append(float(row.eligible_count))
        hist[gov]["enrolled"].append(float(row.enrolled_count))

    # Eligible children for target year (reuse already-determined dialect)
    if dialect == "sqlite":
        sep1 = f"{target_year}-09-01"
        eligible_rows = db.execute(_ELIGIBLE_SQLITE_SQL, {"sep1": sep1}).fetchall()
    else:
        eligible_rows = db.execute(_ELIGIBLE_SQL, {"year": target_year}).fetchall()

    if governorate:
        eligible_rows = [r for r in eligible_rows if r.governorate == governorate]
        if not eligible_rows:
            raise HTTPException(
                status_code=404,
                detail=f"No eligible children found for governorate: {governorate}",
            )

    forecasts: List[ForecastRow] = []
    for row in eligible_rows:
        gov = row.governorate
        gov_hist = hist.get(gov, {"eligible": [], "enrolled": []})
        pred, lower, upper, r2 = _fit_forecast(
            gov_hist["eligible"], gov_hist["enrolled"], float(row.eligible_count)
        )
        forecasts.append(ForecastRow(
            governorate=gov,
            eligible_children=int(row.eligible_count),
            predicted_count=max(0, round(pred)),
            confidence_lower=max(0, round(lower)),
            confidence_upper=max(0, round(upper)),
            model_r2=round(r2, 3),
        ))

    forecasts.sort(key=lambda r: r.predicted_count, reverse=True)
    return forecasts


@router.get("/ministry/enrollment-forecast", response_model=ForecastResponse)
@limiter.limit("100/hour")
async def get_enrollment_forecast(
    request: Request,
    year: Optional[int] = Query(default=None, ge=2020, le=2040),
    governorate: Optional[str] = Query(default=None),
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_user),
) -> ForecastResponse:
    """Predict kindergarten enrollment demand per governorate for `year`.

    Uses children aged 5–6 at September 1st of the target year (the standard
    Jordanian school-year entry age).  A LinearRegression model is fitted on all
    available historical cohort data (eligible children vs. actual enrollments).
    The 90 % prediction interval is derived from residual standard deviation.

    Rate limited: 100 requests / hour / IP.
    """
    if current_user.role not in (models.UserRole.ADMIN, models.UserRole.MANAGER):
        raise HTTPException(status_code=403, detail="Admin or Manager role required")

    target_year = year if year else (date.today().year + 1)
    _log_government_request(db, request, "enrollment-forecast", current_user)
    forecasts = _build_forecasts(db, target_year, governorate)

    return ForecastResponse(
        year=target_year,
        generated_at=datetime.now(timezone.utc).isoformat(),
        forecasts=forecasts,
    )


@router.get("/ministry/enrollment-forecast/export.csv")
@limiter.limit("100/hour")
async def export_enrollment_forecast_csv(
    request: Request,
    year: Optional[int] = Query(default=None, ge=2020, le=2040),
    governorate: Optional[str] = Query(default=None),
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_user),
) -> StreamingResponse:
    """CSV export of the enrollment forecast.  Same computation as the JSON endpoint.

    Returns a downloadable CSV file with one row per governorate.
    Rate limited: 100 requests / hour / IP.
    """
    if current_user.role not in (models.UserRole.ADMIN, models.UserRole.MANAGER):
        raise HTTPException(status_code=403, detail="Admin or Manager role required")

    target_year = year if year else (date.today().year + 1)
    _log_government_request(db, request, "enrollment-forecast-csv", current_user)
    forecasts = _build_forecasts(db, target_year, governorate)

    output = io.StringIO()
    writer = csv.writer(output)
    writer.writerow([
        "governorate", "eligible_children", "predicted_count",
        "confidence_lower", "confidence_upper", "model_r2",
    ])
    for f in forecasts:
        writer.writerow([
            f.governorate, f.eligible_children, f.predicted_count,
            f.confidence_lower, f.confidence_upper, f.model_r2,
        ])

    output.seek(0)
    filename = f"enrollment_forecast_{target_year}.csv"
    return StreamingResponse(
        iter([output.getvalue()]),
        media_type="text/csv",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )


# ===========================================================================
# 4.3  Quality certificate — National Council for Family Affairs (Jordan)
# ===========================================================================

class QualityCertificate(BaseModel):
    nursery_id: int
    nursery_name: str
    score: float
    rating: str
    valid_until: str
    breakdown: dict


@router.get("/family/quality-certificates", response_model=QualityCertificate)
@limiter.limit("100/hour")
async def get_quality_certificate(
    request: Request,
    nursery_id: int = Query(..., ge=1),
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_user),
) -> QualityCertificate:
    """Calculate overall quality score (0–100) for a nursery.

    Scoring weights over the last 90 days:
      - Incident rate per enrolled child  (weight 30%) — lower is better
      - Attendance rate                   (weight 20%) — higher is better
      - Daily report completeness         (weight 20%) — higher is better
      - Parent satisfaction (NPS 0–10)    (weight 30%) — higher is better

    Ratings: Excellent (≥80), Good (60–79), Average (40–59), Poor (<40).
    Certificate valid_until = today + 365 days.
    Rate limited: 100 requests / hour / IP.
    """
    if current_user.role not in (models.UserRole.ADMIN, models.UserRole.MANAGER):
        raise HTTPException(status_code=403, detail="Admin or Manager role required")

    kg = db.query(models.Kindergarten).filter(
        models.Kindergarten.id == nursery_id
    ).first()
    if not kg:
        raise HTTPException(status_code=404, detail="Nursery not found")

    _log_government_request(db, request, "quality-certificates", current_user)

    period_start = date.today() - timedelta(days=90)

    # ---- Component 1: Incident rate per child (30%) ----
    active_children = db.execute(text("""
        SELECT COUNT(DISTINCT ea.child_id) AS cnt
        FROM enrollment_applications ea
        WHERE ea.kindergarten_id = :kg_id
          AND ea.status IN ('ACTIVE', 'ACCEPTED')
          AND ea.deleted_at IS NULL
    """), {"kg_id": nursery_id}).scalar() or 0

    incident_count = db.execute(text("""
        SELECT COUNT(*) AS cnt
        FROM incidents
        WHERE kindergarten_id = :kg_id
          AND occurred_at >= :since
          AND deleted_at IS NULL
    """), {"kg_id": nursery_id, "since": period_start}).scalar() or 0

    if active_children > 0:
        incident_rate = incident_count / active_children
        # 0 incidents = 100 pts; ≥1 incident per child = 0 pts
        incident_score = max(0.0, 100.0 * (1.0 - min(incident_rate, 1.0)))
    else:
        incident_score = 100.0  # no children enrolled; penalise or use neutral

    # ---- Component 2: Attendance rate (20%) ----
    # Expected = active_children × open_days_in_period
    open_days = db.execute(text("""
        SELECT COUNT(*) AS cnt
        FROM operating_calendar
        WHERE kindergarten_id = :kg_id
          AND is_open = TRUE
          AND date BETWEEN :since AND CURRENT_DATE
    """), {"kg_id": nursery_id, "since": period_start}).scalar() or 0

    present_logs = db.execute(text("""
        SELECT COUNT(*) AS cnt
        FROM attendance_logs al
        JOIN enrollment_applications ea ON ea.child_id = al.child_id
        WHERE ea.kindergarten_id = :kg_id
          AND ea.status IN ('ACTIVE', 'ACCEPTED')
          AND ea.deleted_at IS NULL
          AND al.date >= :since
          AND al.deleted_at IS NULL
    """), {"kg_id": nursery_id, "since": period_start}).scalar() or 0

    expected_logs = int(active_children) * int(open_days)
    if expected_logs > 0:
        attendance_score = min(100.0, present_logs / expected_logs * 100.0)
    else:
        attendance_score = 100.0

    # ---- Component 3: Daily report completeness (20%) ----
    report_data = db.execute(text("""
        SELECT
            COUNT(*)                                           AS total,
            COUNT(CASE WHEN dr.status IN ('SUBMITTED','APPROVED') THEN 1 END) AS completed,
            AVG(
                COALESCE(LENGTH(COALESCE(dr.activities, '')), 0)
              + COALESCE(LENGTH(COALESCE(dr.notes, '')), 0)
            )                                                  AS avg_text_len
        FROM daily_reports dr
        JOIN enrollment_applications ea ON ea.child_id = dr.child_id
        WHERE ea.kindergarten_id = :kg_id
          AND dr.date >= :since
    """), {"kg_id": nursery_id, "since": period_start}).first()

    if report_data and report_data.total and int(report_data.total) > 0:
        completion_ratio = (report_data.completed or 0) / int(report_data.total)
        avg_len = float(report_data.avg_text_len or 0)
        length_score = min(1.0, avg_len / 50.0)  # 50 chars = full marks
        report_score = (completion_ratio * 0.70 + length_score * 0.30) * 100.0
    else:
        report_score = 100.0

    # ---- Component 4: Parent satisfaction NPS → 0–100 (30%) ----
    avg_nps = db.execute(text("""
        SELECT AVG(sr.nps_score) AS avg_nps
        FROM survey_responses sr
        JOIN surveys s ON s.id = sr.survey_id
        WHERE s.kindergarten_id = :kg_id
          AND s.end_date >= :since
          AND sr.nps_score IS NOT NULL
    """), {"kg_id": nursery_id, "since": period_start}).scalar()

    if avg_nps is not None:
        satisfaction_score = float(avg_nps) / 10.0 * 100.0
    else:
        satisfaction_score = 50.0  # neutral default when no survey data

    # ---- Weighted total ----
    score = round(
        incident_score     * 0.30
        + attendance_score * 0.20
        + report_score     * 0.20
        + satisfaction_score * 0.30,
        1,
    )
    score = min(100.0, max(0.0, score))

    if score >= 80:
        rating = "Excellent"
    elif score >= 60:
        rating = "Good"
    elif score >= 40:
        rating = "Average"
    else:
        rating = "Poor"

    valid_until = (date.today() + timedelta(days=365)).isoformat()

    return QualityCertificate(
        nursery_id=nursery_id,
        nursery_name=kg.name_ar,
        score=score,
        rating=rating,
        valid_until=valid_until,
        breakdown={
            "incident_rate_score":       round(incident_score, 1),
            "attendance_score":          round(attendance_score, 1),
            "report_completeness_score": round(report_score, 1),
            "parent_satisfaction_score": round(satisfaction_score, 1),
            "active_children":           int(active_children),
            "incident_count_90d":        int(incident_count),
            "open_days_in_period":       int(open_days),
            "period_days":               90,
        },
    )


# ===========================================================================
# 4.4  Ministry of Development dashboard
# ===========================================================================

class DevelopmentDashboard(BaseModel):
    generated_at: str
    total_nurseries: int
    total_children: int
    avg_attendance_pct: float
    incident_trend: List[dict]
    top5_density_areas: List[dict]


async def refresh_development_dashboard() -> None:
    """Refresh mv_development_dashboard materialized view (PostgreSQL only).

    Called daily at 03:00 UTC from the APScheduler added in main.py.
    Silently skips on SQLite (test environments) and on any error.
    """
    from database import SessionLocal
    db = SessionLocal()
    try:
        dialect = db.bind.dialect.name if db.bind else "postgresql"
        if dialect == "postgresql":
            db.execute(
                text("REFRESH MATERIALIZED VIEW CONCURRENTLY mv_development_dashboard")
            )
            db.commit()
    except Exception:
        db.rollback()
    finally:
        db.close()


@router.get("/development/dashboard", response_model=DevelopmentDashboard)
@limiter.limit("100/hour")
async def get_development_dashboard(
    request: Request,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_user),
) -> DevelopmentDashboard:
    """Aggregated national KPIs for the Ministry of Development.

    Attempts to read from the materialized view mv_development_dashboard
    (refreshed daily at 03:00 UTC).  Falls back to a live query when the view
    is empty or unavailable (e.g., on test databases).
    Rate limited: 100 requests / hour / IP.
    """
    if current_user.role not in (models.UserRole.ADMIN, models.UserRole.MANAGER):
        raise HTTPException(status_code=403, detail="Admin or Manager role required")

    _log_government_request(db, request, "development-dashboard", current_user)

    # Try materialized view first
    try:
        row = db.execute(text("SELECT * FROM mv_development_dashboard LIMIT 1")).first()
        if row:
            incident_trend = row.incident_trend
            if isinstance(incident_trend, str):
                incident_trend = json.loads(incident_trend)
            top5 = row.top5_density_areas
            if isinstance(top5, str):
                top5 = json.loads(top5)
            return DevelopmentDashboard(
                generated_at=(
                    row.refreshed_at.isoformat()
                    if row.refreshed_at
                    else datetime.now(timezone.utc).isoformat()
                ),
                total_nurseries=int(row.total_nurseries or 0),
                total_children=int(row.total_children or 0),
                avg_attendance_pct=round(float(row.avg_attendance_pct or 0), 1),
                incident_trend=incident_trend or [],
                top5_density_areas=top5 or [],
            )
    except Exception:
        pass  # view not yet populated or doesn't exist — use live fallback

    return await _development_dashboard_live(db)


async def _development_dashboard_live(db: Session) -> DevelopmentDashboard:
    """Live computation used when the materialized view is unavailable."""
    nursery_count = db.execute(text(
        "SELECT COUNT(*) FROM kindergartens WHERE status = 'ACTIVE'"
    )).scalar() or 0

    child_count = db.execute(text(
        "SELECT COUNT(*) FROM children WHERE deleted_at IS NULL"
    )).scalar() or 0

    # Average attendance % last 30 days
    # Dialect-aware: PostgreSQL supports CROSS JOIN + complex aggregation;
    # SQLite uses a simpler approach.
    dialect = db.bind.dialect.name if db.bind else "postgresql"
    if dialect == "sqlite":
        present = db.execute(text(
            "SELECT COUNT(*) FROM attendance_logs "
            "WHERE date >= date('now', '-30 days') AND deleted_at IS NULL"
        )).scalar() or 0
        avg_att = min(100.0, float(present) / max(1, int(child_count)) * 5)
    else:
        att_val = db.execute(text("""
            SELECT
                ROUND(
                    100.0 * COUNT(DISTINCT al.id)::numeric
                    / NULLIF(
                        (SELECT COUNT(DISTINCT ea2.child_id) *
                                COUNT(DISTINCT oc2.date)
                         FROM enrollment_applications ea2
                         JOIN operating_calendar oc2 ON oc2.kindergarten_id = ea2.kindergarten_id
                         WHERE ea2.status IN ('ACTIVE','ACCEPTED')
                           AND ea2.deleted_at IS NULL
                           AND oc2.is_open = TRUE
                           AND oc2.date BETWEEN CURRENT_DATE - 30 AND CURRENT_DATE
                        ), 0
                    ), 1
                ) AS att_pct
            FROM attendance_logs al
            WHERE al.date BETWEEN CURRENT_DATE - 30 AND CURRENT_DATE
              AND al.deleted_at IS NULL
        """)).scalar()
        avg_att = round(float(att_val or 0), 1)

    # Incident trend last 8 weeks
    if dialect == "sqlite":
        trend_rows = db.execute(text("""
            SELECT
                date(occurred_at, 'weekday 1', '-6 days') AS week_start,
                COUNT(*) AS incident_count
            FROM incidents
            WHERE occurred_at >= date('now', '-56 days')
              AND deleted_at IS NULL
            GROUP BY date(occurred_at, 'weekday 1', '-6 days')
            ORDER BY week_start
        """)).fetchall()
    else:
        trend_rows = db.execute(text("""
            SELECT
                DATE_TRUNC('week', occurred_at)::date AS week_start,
                COUNT(*) AS incident_count
            FROM incidents
            WHERE occurred_at >= CURRENT_DATE - 56
              AND deleted_at IS NULL
            GROUP BY DATE_TRUNC('week', occurred_at)
            ORDER BY week_start
        """)).fetchall()

    incident_trend = [
        {"week_start": str(r.week_start), "incident_count": int(r.incident_count)}
        for r in trend_rows
    ]

    # Top 5 areas by children-per-nursery density
    density_rows = db.execute(text("""
        SELECT
            k.area,
            k.governorate,
            COUNT(DISTINCT k.id)         AS nursery_count,
            COUNT(DISTINCT ea.child_id)  AS enrolled_children
        FROM kindergartens k
        LEFT JOIN enrollment_applications ea
               ON ea.kindergarten_id = k.id
              AND ea.status IN ('ACTIVE', 'ACCEPTED')
              AND ea.deleted_at IS NULL
        WHERE k.status = 'ACTIVE'
        GROUP BY k.area, k.governorate
        ORDER BY enrolled_children DESC, nursery_count ASC
        LIMIT 5
    """)).fetchall()

    top5 = [
        {
            "area":                  r.area,
            "governorate":           r.governorate,
            "nursery_count":         int(r.nursery_count),
            "enrolled_children":     int(r.enrolled_children),
            "children_per_nursery":  round(
                int(r.enrolled_children) / max(1, int(r.nursery_count)), 1
            ),
        }
        for r in density_rows
    ]

    return DevelopmentDashboard(
        generated_at=datetime.now(timezone.utc).isoformat(),
        total_nurseries=int(nursery_count),
        total_children=int(child_count),
        avg_attendance_pct=avg_att,
        incident_trend=incident_trend,
        top5_density_areas=top5,
    )


# ===========================================================================
# 4.5  Population density / child mapping — census endpoint
# ===========================================================================

@router.get("/census/child-density")
@limiter.limit("100/hour")
async def get_child_density(
    request: Request,
    governorate: Optional[str] = Query(default=None),
    district: Optional[str] = Query(default=None),
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_user),
) -> dict:
    """Return number of children under 6 per km² as a GeoJSON FeatureCollection.

    Aggregates by governorate (and district/area when `district` is supplied).
    Coordinates come from geocode_address() — currently a centroid placeholder.
    Replace geocode_address() with a live geocoding call for production use.

    Rate limited: 100 requests / hour / IP.
    """
    if current_user.role not in (models.UserRole.ADMIN, models.UserRole.MANAGER):
        raise HTTPException(status_code=403, detail="Admin or Manager role required")

    _log_government_request(db, request, "child-density", current_user)

    # Children born within the last 6 years
    cutoff_date = date.today() - timedelta(days=6 * 365)

    density_rows = db.execute(text("""
        SELECT
            pp.home_governorate AS governorate,
            pp.home_area        AS area,
            COUNT(c.id)         AS child_count
        FROM children c
        JOIN parent_profiles pp ON pp.id = c.parent_id
        WHERE c.deleted_at IS NULL
          AND c.date_of_birth >= :cutoff
          AND (:governorate IS NULL OR pp.home_governorate = :governorate)
          AND (:district IS NULL OR pp.home_area = :district)
        GROUP BY pp.home_governorate, pp.home_area
        ORDER BY child_count DESC
    """), {
        "cutoff":      cutoff_date,
        "governorate": governorate,
        "district":    district,
    }).fetchall()

    features = []
    for row in density_rows:
        lat, lon = geocode_address("", row.governorate)
        area_km2 = _GOVERNORATE_AREA_KM2.get(row.governorate, 1000.0)
        density_per_km2 = round(int(row.child_count) / area_km2, 4)
        features.append({
            "type": "Feature",
            "geometry": {
                "type": "Point",
                "coordinates": [lon, lat],
            },
            "properties": {
                "governorate":    row.governorate,
                "area":           row.area,
                "child_count":    int(row.child_count),
                "area_km2":       area_km2,
                "density_per_km2": density_per_km2,
            },
        })

    return {
        "type":         "FeatureCollection",
        "query":        {"governorate": governorate, "district": district},
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "features":     features,
    }
