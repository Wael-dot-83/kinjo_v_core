"""
Jordan Heat Map — admin-facing FastAPI router.

Exposes the read-side endpoints that the Admin Heat Map UI needs:
- GET  /admin/heat-map/governorates          — canonical list of 12 governorates
- GET  /admin/heat-map/indicators            — 6 main indicators + sub-indicators
- GET  /admin/heat-map/data                  — full map payload (governorates + indicators)
- GET  /admin/heat-map/governorate/{slug}    — detailed payload for a single governorate
- GET  /admin/heat-map/geojson               — Jordan boundary GeoJSON
- GET  /admin/heat-map/correlations          — Pearson correlation matrix
- GET  /admin/heat-map/regression            — OLS regression weights (proxy)
- GET  /admin/heat-map/daily-update          — daily update metadata
- POST /admin/heat-map/refresh               — force recompute (admin only)
- GET  /admin/heat-map/runs                  — pipeline run history
- GET  /admin/heat-map/governorate/{slug}/history — risk trend data
- POST /admin/heat-map/alerts/{alert_id}/acknowledge — acknowledge alert
- GET  /admin/heat-map/alerts                — list alerts

All endpoints require admin role and are rate-limited via slowapi.
Naming follows the project convention ("Heat Map", not "GeoMap").
Uses standardized APIError responses from admin_security.
"""
from __future__ import annotations
import logging
import secrets
from datetime import date, datetime, timedelta
from utils.time_utils import now_amman, today_amman as _today, to_utc_iso
from typing import Any, Dict, Optional

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from sqlalchemy.orm import Session

from database import get_db
from admin_security import (
    APIError, ErrorCode, create_error_response, forbidden_error,
    not_found_error, validation_error
)
from admin_security import require_admin_role as _require_admin_role
from dependencies import get_current_user
from rate_limiter import limiter
from config import settings
import models

from . import service as heatmap_service
from . import cache as heatmap_cache
from .kpi_status import KPIStatus, normalize_kpi_status

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/admin/heat-map", tags=["admin-heat-map"])


def _require_admin(current_user: models.User = Depends(get_current_user)) -> models.User:
    """Validate admin role using standardized error handling."""
    if not current_user:
        raise forbidden_error("Authentication required")
    if getattr(current_user, "role", None) != models.UserRole.ADMIN:
        raise forbidden_error("Admin access required")
    return current_user


def _validate_csrf_token(request: Request) -> None:
    """Double-submit CSRF validation for state-changing requests."""
    header_token = request.headers.get("x-csrf-token")
    cookie_token = request.cookies.get(settings.CSRF_COOKIE_NAME)
    if not header_token or not cookie_token or not secrets.compare_digest(header_token, cookie_token):
        raise validation_error("Invalid CSRF token", fields={"csrf_token": "invalid"})


def _pagination_meta(page: int, page_size: int, total: int) -> Dict[str, Any]:
    total_pages = (total + page_size - 1) // page_size if total else 0
    return {
        "page": page,
        "page_size": page_size,
        "total": total,
        "total_pages": total_pages,
        "has_next": page < total_pages,
        "has_prev": page > 1,
    }


def _kindergarten_filters(
    governorate: Optional[str],
    city: Optional[str],
    status: Optional[str],
    from_date: Optional[date],
    to_date: Optional[date],
) -> Dict[str, Any]:
    return {
        "governorate": governorate,
        "city": city,
        "status": status,
        "from": from_date.isoformat() if from_date else None,
        "to": to_date.isoformat() if to_date else None,
    }


def _normalize_kindergarten_status(status: Optional[str]) -> Optional[str]:
    if status is None:
        return None
    normalized = normalize_kpi_status(status).value
    allowed = {s.value for s in KPIStatus}
    if normalized not in allowed:
        raise validation_error(f"Unknown kindergarten KPI status: {status!r}")
    return normalized


def _filter_kindergarten_rows_by_status(db: Session, rows, status: Optional[str]):
    normalized = _normalize_kindergarten_status(status)
    if normalized is None:
        return rows
    return [
        row for row in rows
        if heatmap_service.compute_kindergarten_kpi_scores(db, row)["kpi_status"]["status"] == normalized
    ]


# ---------------------------------------------------------------------------
# Reference endpoints
# ---------------------------------------------------------------------------
@router.get("/governorates")
@limiter.limit(settings.RATE_LIMIT_ADMIN_READ)
def list_governorates(
    request: Request,
    current_user: models.User = Depends(_require_admin),
) -> dict:
    """Return the 12 Jordan governorates with metadata."""
    cached = heatmap_cache.cached_get("governorates")
    if cached is not None:
        return cached
    data = {
        "count": len(heatmap_service.get_governorates()),
        "governorates": heatmap_service.get_governorates(),
    }
    heatmap_cache.cached_set("governorates", data, ttl=heatmap_cache.HEAT_MAP_GOVERNORATES_TTL)
    return data


@router.get("/indicators")
@limiter.limit(settings.RATE_LIMIT_ADMIN_READ)
def list_indicators(
    request: Request,
    current_user: models.User = Depends(_require_admin),
) -> dict:
    """Return the 6 main indicators and their sub-indicators."""
    cached = heatmap_cache.cached_get("indicators")
    if cached is not None:
        return cached
    data = {
        "count": len(heatmap_service.get_indicators()),
        "indicators": heatmap_service.get_indicators(),
    }
    heatmap_cache.cached_set("indicators", data, ttl=heatmap_cache.HEAT_MAP_GOVERNORATES_TTL)
    return data


# ---------------------------------------------------------------------------
# Kindergarten-level heat map endpoints
# ---------------------------------------------------------------------------
@router.get("/kindergartens")
@limiter.limit(settings.RATE_LIMIT_ADMIN_READ)
def list_kindergartens(
    request: Request,
    governorate: Optional[str] = Query(None, description="Governorate slug, e.g. amman"),
    city: Optional[str] = Query(None),
    status: Optional[str] = Query(None, pattern="^(normal|warning|risk|critical|unknown)$"),
    from_date: Optional[date] = Query(None, alias="from"),
    to_date: Optional[date] = Query(None, alias="to"),
    page: int = Query(1, ge=1, description="Page number (1-indexed)"),
    page_size: int = Query(50, ge=1, le=200, description="Rows per page"),
    current_user: models.User = Depends(_require_admin),
    db: Session = Depends(get_db),
) -> dict:
    """List kindergartens with normalized KPI status and pagination."""
    try:
        query = heatmap_service.build_kindergarten_query(
            db,
            governorate=governorate,
            district=city,
            status=status,
            from_date=from_date,
            to_date=to_date,
        )
        rows = query.order_by(models.Kindergarten.id.asc()).all()
        rows = _filter_kindergarten_rows_by_status(db, rows, status)
    except ValueError as exc:
        raise validation_error(str(exc))

    total = len(rows)
    offset = (page - 1) * page_size
    page_rows = rows[offset:offset + page_size]
    items = [
        heatmap_service.kindergarten_to_dict(db, row, include_details=True)
        for row in page_rows
    ]
    return {
        "items": items,
        "count": len(items),
        "total": total,
        "pagination": _pagination_meta(page, page_size, total),
        "filters": _kindergarten_filters(governorate, city, status, from_date, to_date),
        "last_update": now_amman().isoformat(),
    }


@router.get("/kindergartens/map-data")
@limiter.limit(settings.RATE_LIMIT_ADMIN_READ)
def get_kindergarten_map_data(
    request: Request,
    governorate: Optional[str] = Query(None, description="Governorate slug, e.g. amman"),
    city: Optional[str] = Query(None),
    status: Optional[str] = Query(None, pattern="^(normal|warning|risk|critical|unknown)$"),
    from_date: Optional[date] = Query(None, alias="from"),
    to_date: Optional[date] = Query(None, alias="to"),
    current_user: models.User = Depends(_require_admin),
    db: Session = Depends(get_db),
) -> dict:
    """Return GeoJSON point data for kindergarten map visualization."""
    try:
        return heatmap_service.get_kindergarten_map_data(
            db,
            governorate=governorate,
            district=city,
            status=status,
            from_date=from_date,
            to_date=to_date,
        )
    except ValueError as exc:
        raise validation_error(str(exc))


@router.get("/kindergartens/stats")
@limiter.limit(settings.RATE_LIMIT_ADMIN_READ)
def get_kindergarten_stats(
    request: Request,
    governorate: Optional[str] = Query(None, description="Governorate slug, e.g. amman"),
    city: Optional[str] = Query(None),
    status: Optional[str] = Query(None, pattern="^(normal|warning|risk|critical|unknown)$"),
    from_date: Optional[date] = Query(None, alias="from"),
    to_date: Optional[date] = Query(None, alias="to"),
    current_user: models.User = Depends(_require_admin),
    db: Session = Depends(get_db),
) -> dict:
    """Return aggregated kindergarten KPI statistics for the data table."""
    try:
        return heatmap_service.get_kindergarten_stats(
            db,
            governorate=governorate,
            district=city,
            status=status,
            from_date=from_date,
            to_date=to_date,
        )
    except ValueError as exc:
        raise validation_error(str(exc))


@router.get("/kindergartens/{id}")
@limiter.limit(settings.RATE_LIMIT_ADMIN_READ)
def get_kindergarten_detail(
    request: Request,
    id: int,
    current_user: models.User = Depends(_require_admin),
    db: Session = Depends(get_db),
) -> dict:
    """Return one kindergarten with normalized KPI status and indicator details."""
    data = heatmap_service.get_kindergarten_detail(db, id)
    if data is None:
        raise not_found_error(f"Unknown kindergarten: {id}")
    return {
        "kindergarten": data,
        "last_update": now_amman().isoformat(),
    }


# ---------------------------------------------------------------------------
# Map data
# ---------------------------------------------------------------------------
@router.get("/data")
@limiter.limit(settings.RATE_LIMIT_ADMIN_READ)
def get_heat_map_data(
    request: Request,
    indicator: Optional[str] = Query(None, description="Main indicator to highlight", pattern=r"^[a-z_]+$"),
    current_user: models.User = Depends(_require_admin),
    db: Session = Depends(get_db),
) -> dict:
    """Return the full heat-map payload: all governorates with current values and risk scores."""
    cache_name = f"data:{indicator or 'default'}"
    cached = heatmap_cache.cached_get(cache_name)
    if cached is not None:
        return cached
    overview = heatmap_service.get_map_overview(db)
    if indicator and indicator in [i["key"] for i in overview["indicators"]]:
        overview["selected_indicator"] = indicator
    else:
        overview["selected_indicator"] = "overall_risk"
    heatmap_cache.cached_set(cache_name, overview, ttl=heatmap_cache.HEAT_MAP_TTL_SECONDS)
    return overview


@router.get("/governorate/{slug}")
@limiter.limit(settings.RATE_LIMIT_ADMIN_READ)
def get_governorate_detail(
    request: Request,
    slug: str,
    current_user: models.User = Depends(_require_admin),
    db: Session = Depends(get_db),
) -> dict:
    """Return detailed payload for a single governorate (sub-indicators, trends, alerts)."""
    if slug not in [g["slug"] for g in heatmap_service.get_governorates()]:
        raise not_found_error(f"Unknown governorate: {slug!r}")
    cache_name = f"governorate:{slug}"
    cached = heatmap_cache.cached_get(cache_name)
    if cached is not None:
        return cached
    try:
        data = heatmap_service.get_governorate_overview(db, slug)
    except ValueError as exc:
        raise validation_error(str(exc))
    heatmap_cache.cached_set(cache_name, data, ttl=heatmap_cache.HEAT_MAP_TTL_SECONDS)
    return data


@router.get("/geojson")
@limiter.limit(settings.RATE_LIMIT_ADMIN_READ)
def get_geojson(
    request: Request,
    current_user: models.User = Depends(_require_admin),
) -> dict:
    """Return the Jordan boundary GeoJSON."""
    cached = heatmap_cache.cached_get("geojson")
    if cached is not None:
        return cached
    data = heatmap_service.load_jordan_geojson()
    heatmap_cache.cached_set("geojson", data, ttl=heatmap_cache.HEAT_MAP_GOVERNORATES_TTL)
    return data


# ---------------------------------------------------------------------------
# Analytics
# ---------------------------------------------------------------------------
@router.get("/correlations")
@limiter.limit(settings.RATE_LIMIT_ADMIN_READ)
def get_correlations(
    request: Request,
    main_indicator: Optional[str] = Query(None, pattern=r"^[a-z_]+$"),
    current_user: models.User = Depends(_require_admin),
    db: Session = Depends(get_db),
) -> dict:
    """Return the Pearson correlation matrix for the 6 main indicators."""
    cache_name = f"correlations:{main_indicator or 'all'}"
    cached = heatmap_cache.cached_get(cache_name)
    if cached is not None:
        return cached
    data = heatmap_service.get_correlations(db)
    if main_indicator:
        data["matrix"] = [row for row in data["matrix"] if row["row"] == main_indicator or row["column"] == main_indicator]
    heatmap_cache.cached_set(cache_name, data, ttl=heatmap_cache.HEAT_MAP_CORRELATION_TTL)
    return data


@router.get("/regression")
@limiter.limit(settings.RATE_LIMIT_ADMIN_READ)
def get_regression(
    request: Request,
    main_indicator: Optional[str] = Query(None, pattern=r"^[a-z_]+$"),
    current_user: models.User = Depends(_require_admin),
    db: Session = Depends(get_db),
) -> dict:
    """Return the OLS regression weights for sub-indicators against main indicators."""
    cache_name = f"regression:{main_indicator or 'all'}"
    cached = heatmap_cache.cached_get(cache_name)
    if cached is not None:
        return cached
    data = heatmap_service.get_regression_weights(db)
    if main_indicator:
        data["weights"] = [w for w in data["weights"] if w["main_indicator"] == main_indicator]
    heatmap_cache.cached_set(cache_name, data, ttl=heatmap_cache.HEAT_MAP_CORRELATION_TTL)
    return data


@router.get("/daily-update")
@limiter.limit(settings.RATE_LIMIT_ADMIN_READ)
def get_daily_update(
    request: Request,
    current_user: models.User = Depends(_require_admin),
    db: Session = Depends(get_db),
) -> dict:
    """Return the daily-update metadata (last update, schedule, sources).

    Reads from `map_daily_run_log` when available; falls back to
    `daily_update_summary()` if the table is empty (fresh deployment).
    """
    try:
        latest = (
            db.query(models.MapDailyRunLog)
            .order_by(models.MapDailyRunLog.started_at.desc())
            .first()
        )
        if latest is not None:
            next_run = None
            if latest.started_at is not None:
                next_run = (latest.started_at + timedelta(days=1)).isoformat()
            return {
                # No manual "Z" suffix: stored values are aware UTC since D-11, so
                # .isoformat() already ends in "+00:00" and appending "Z" produced the
                # malformed "…+00:00Z". Correct while values were naive; wrong now.
                "last_update": to_utc_iso(latest.started_at),
                "last_run_status": latest.status,
                "rows_processed": latest.rows_processed,
                "governorates": latest.governorates,
                "duration_ms": latest.duration_ms,
                "schedule": "Daily at 02:00 local time (Asia/Amman)",
                "data_sources": ["daily_reports", "incidents", "kindergartens", "users", "tasks"],
                "next_run_at": next_run,
            }
    except Exception as exc:
        logger.warning("Could not read map_daily_run_log: %s", exc)
    return heatmap_service.daily_update_summary(db)


# ---------------------------------------------------------------------------
# Pipeline control
# ---------------------------------------------------------------------------
@router.post("/refresh")
@limiter.limit(settings.RATE_LIMIT_ADMIN_WRITE)
def refresh_heat_map(
    request: Request,
    snapshot_date: Optional[str] = None,
    current_user: models.User = Depends(_require_admin),
    db: Session = Depends(get_db),
) -> dict:
    _validate_csrf_token(request)
    """Force recompute the Heat Map by running the daily ETL pipeline.

    Optional `snapshot_date` query param (YYYY-MM-DD) reruns the pipeline for
    that date; default = today.

    Returns a summary with rows processed, governorates covered, warnings
    and the run_id.
    """
    from . import pipeline as heatmap_pipeline
    target_date = None
    if snapshot_date:
        try:
            target_date = date.fromisoformat(snapshot_date)
        except ValueError:
            raise validation_error(f"Invalid snapshot_date: {snapshot_date!r}; expected YYYY-MM-DD")

    try:
        heatmap_service.load_jordan_geojson(force_reload=True)
        summary = heatmap_pipeline.run_daily_pipeline(db, snapshot_date=target_date)
    except Exception as exc:
        db.rollback()
        logger.error("Pipeline failed: %s", exc, exc_info=True)
        raise APIError(
            status_code=500,
            code=ErrorCode.INTERNAL_ERROR,
            message="Pipeline execution failed",
            details={"error": str(exc)}
        )
    # Explicitly invalidate cache on success
    try:
        heatmap_cache.invalidate_heat_map_cache()
    except Exception:
        pass
    return {
        "status": summary.get("status", "ok"),
        "run_id": summary.get("run_id"),
        "snapshot_date": summary.get("snapshot_date"),
        "governorates": summary.get("governorates", 0),
        "rows_processed": summary.get("rows_processed", 0),
        "duration_ms": summary.get("duration_ms"),
        "errors": summary.get("errors", []),
        "warnings": summary.get("warnings", []),
    }


# ---------------------------------------------------------------------------
# Runs and history
# ---------------------------------------------------------------------------
@router.get("/runs")
@limiter.limit(settings.RATE_LIMIT_ADMIN_READ)
def list_runs(
    request: Request,
    limit: int = Query(20, ge=1, le=100),
    current_user: models.User = Depends(_require_admin),
    db: Session = Depends(get_db),
) -> dict:
    """List the most recent ETL pipeline runs."""
    runs = (
        db.query(models.MapDailyRunLog)
        .order_by(models.MapDailyRunLog.started_at.desc())
        .limit(limit)
        .all()
    )
    return {
        "runs": [
            {
                "id": r.id,
                "run_id": r.run_id,
                "started_at": r.started_at.isoformat() if r.started_at else None,
                "finished_at": r.finished_at.isoformat() if r.finished_at else None,
                "status": r.status,
                "rows_processed": r.rows_processed,
                "governorates": r.governorates,
                "duration_ms": r.duration_ms,
                "errors": r.errors or [],
                "warnings": r.warnings or [],
            }
            for r in runs
        ],
        "count": len(runs),
    }


# ---------------------------------------------------------------------------
# City-level aggregation
# ---------------------------------------------------------------------------
@router.get("/governorate/{slug}/cities")
@limiter.limit(settings.RATE_LIMIT_ADMIN_READ)
def get_governorate_cities(
    request: Request,
    slug: str,
    current_user: models.User = Depends(_require_admin),
    db: Session = Depends(get_db),
) -> dict:
    """Return city-level KPI summary for all cities within a governorate.

    Groups kindergartens by their `city` field and returns aggregated KPI
    scores, risk levels, and child/enrollment counts per city.
    """
    if slug not in [g["slug"] for g in heatmap_service.get_governorates()]:
        raise not_found_error(f"Unknown governorate: {slug!r}")
    cache_name = f"cities:{slug}"
    cached = heatmap_cache.cached_get(cache_name)
    if cached is not None:
        return cached
    try:
        data = heatmap_service.get_city_summary(db, slug)
    except ValueError as exc:
        raise validation_error(str(exc))
    heatmap_cache.cached_set(cache_name, data, ttl=heatmap_cache.HEAT_MAP_TTL_SECONDS)
    return data


# ---------------------------------------------------------------------------
# Historical data
# ---------------------------------------------------------------------------
@router.get("/governorate/{slug}/history")
@limiter.limit(settings.RATE_LIMIT_ADMIN_READ)
def get_governorate_history(
    request: Request,
    slug: str,
    days: int = Query(30, ge=1, le=365),
    current_user: models.User = Depends(_require_admin),
    db: Session = Depends(get_db),
) -> dict:
    """Return the historical risk score and main-indicator values for one
    governorate, suitable for sparkline / trend-chart rendering.

    The response is a list of (date, risk_score, main_indicators) tuples
    sorted oldest first.
    """
    gov = next((g for g in heatmap_service.get_governorates() if g["slug"] == slug), None)
    if gov is None:
        raise not_found_error(f"Unknown governorate: {slug!r}")

    cutoff = _today() - timedelta(days=days)
    risk_rows = (
        db.query(models.MapRiskSnapshot)
        .filter(models.MapRiskSnapshot.governorate_code == gov["code"])
        .filter(models.MapRiskSnapshot.snapshot_date >= cutoff)
        .order_by(models.MapRiskSnapshot.snapshot_date.asc())
        .all()
    )
    indicator_rows = (
        db.query(models.MapIndicatorSnapshot)
        .filter(models.MapIndicatorSnapshot.governorate_code == gov["code"])
        .filter(models.MapIndicatorSnapshot.snapshot_date >= cutoff)
        .order_by(models.MapIndicatorSnapshot.snapshot_date.asc())
        .all()
    )
    by_date_indicators: Dict[str, Dict[str, float]] = {}
    for r in indicator_rows:
        by_date_indicators.setdefault(r.snapshot_date.isoformat(), {})[r.main_indicator] = r.value

    history = []
    for r in risk_rows:
        history.append({
            "date": r.snapshot_date.isoformat(),
            "risk_score": float(r.risk_score),
            "risk_level": r.risk_level,
            "trend_pct": float(r.trend_pct) if r.trend_pct is not None else None,
            "main_indicators": by_date_indicators.get(r.snapshot_date.isoformat(), {}),
        })
    return {
        "slug": slug,
        "days": days,
        "history": history,
    }


# ---------------------------------------------------------------------------
# Alerts
# ---------------------------------------------------------------------------
@router.post("/alerts/{alert_id}/acknowledge")
@limiter.limit(settings.RATE_LIMIT_ADMIN_WRITE)
def acknowledge_alert(
    request: Request,
    alert_id: int,
    current_user: models.User = Depends(_require_admin),
    db: Session = Depends(get_db),
) -> dict:
    _validate_csrf_token(request)
    """Mark an open alert as acknowledged by the current admin."""
    alert = db.query(models.MapAlertHistory).filter(models.MapAlertHistory.id == alert_id).one_or_none()
    if alert is None:
        raise not_found_error(f"Unknown alert: {alert_id}")
    if alert.acknowledged_at is not None:
        return {"status": "already_acknowledged", "alert_id": alert_id}
    alert.acknowledged_at = now_amman()
    alert.acknowledged_by = current_user.id
    db.commit()
    try:
        heatmap_cache.invalidate_heat_map_cache()
    except Exception:
        pass
    return {"status": "acknowledged", "alert_id": alert_id}


@router.get("/alerts")
@limiter.limit(settings.RATE_LIMIT_ADMIN_READ)
def list_alerts(
    request: Request,
    severity: Optional[str] = Query(None, pattern="^(low|medium|high|critical)$"),
    governorate: Optional[str] = Query(None),
    open_only: bool = Query(True),
    limit: int = Query(50, ge=1, le=500),
    current_user: models.User = Depends(_require_admin),
    db: Session = Depends(get_db),
) -> dict:
    """List alerts with filters.

    - `severity`: filter by severity (low / medium / high / critical)
    - `governorate`: filter by governorate slug
    - `open_only`: if True, hide acknowledged+resolved alerts (default True)
    - `limit`: max rows returned (default 50)
    """
    q = db.query(models.MapAlertHistory).order_by(models.MapAlertHistory.created_at.desc())
    if open_only:
        q = q.filter(models.MapAlertHistory.acknowledged_at.is_(None))
    if severity:
        q = q.filter(models.MapAlertHistory.severity == severity)
    if governorate:
        gov = next((g for g in heatmap_service.get_governorates() if g["slug"] == governorate), None)
        if gov is None:
            raise not_found_error(f"Unknown governorate: {governorate!r}")
        q = q.filter(models.MapAlertHistory.governorate_code == gov["code"])
    alerts = q.limit(limit).all()
    return {
        "alerts": [
            {
                "id": a.id,
                "snapshot_date": a.snapshot_date.isoformat() if a.snapshot_date else None,
                "governorate_code": a.governorate_code,
                "sub_indicator": a.sub_indicator,
                "rule": a.rule,
                "severity": a.severity,
                "current_value": a.current_value,
                "threshold": a.threshold,
                "message": a.message,
                "meta": a.meta or {},
                "created_at": a.created_at.isoformat() if a.created_at else None,
                "acknowledged_at": a.acknowledged_at.isoformat() if a.acknowledged_at else None,
                "resolved_at": a.resolved_at.isoformat() if a.resolved_at else None,
            }
            for a in alerts
        ],
        "count": len(alerts),
    }