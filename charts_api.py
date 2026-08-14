"""
FastAPI router for the KinJo charting subsystem.

Endpoints:
  GET  /admin/charts/data         — raw JSON data for a chart source
  GET  /admin/charts/render       — rendered Plotly HTML
  POST /admin/charts/suggest      — chart-type suggestions
  GET  /admin/charts/task/{task_id} — Celery task status
  GET  /admin/charts/dashboard    — HTML page
"""

from __future__ import annotations

import logging
from typing import Any, Dict, Optional

from fastapi import APIRouter, Depends, HTTPException, Query, Request, status
from fastapi.responses import RedirectResponse
from sqlalchemy.orm import Session

from database import get_db
from dependencies import require_admin, require_admin_or_manager
from rate_limiter import limiter
from config import settings
from charts.schemas import (
    ChartRequest,
    ChartResponse,
    ChartSource,
    ChartType,
    Granularity,
    SuggestRequest,
    SuggestResponse,
    TaskStatus,
)
from charts.service import ChartService
from pydantic import BaseModel, EmailStr, Field, field_validator
import models
from admin_security import log_audit_event
from audit_actions import AuditAction

logger = logging.getLogger(__name__)
# ---------------------------------------------------------------------------
# Compatibility Alias Note:
# Chart sources can aggregate network-wide operational data. The routes below
# mounted directly at `/admin/charts/...` are intentional legacy compatibility 
# aliases retained to support existing front-end dashboards without breaking 
# them during the transition. The canonical API namespace is protected at 
# `/api/admin/charts/...` at the bottom of this file.
# Both aliases are fully protected by `require_admin` at the router boundary.
# ---------------------------------------------------------------------------
router = APIRouter(tags=["Charts"], dependencies=[Depends(require_admin)])
_svc = ChartService()

# ---------------------------------------------------------------------------
# Helper: resolve optional chart_type override from query param
# ---------------------------------------------------------------------------

def _parse_source(source: str) -> ChartSource:
    try:
        return ChartSource(source)
    except ValueError:
        raise HTTPException(
            status_code=422,  # 422 literal: Starlette deprecated the ENTITY constant name
            detail=f"Invalid source '{source}'. Valid: {[s.value for s in ChartSource]}",
        )

def _parse_chart_type(ct: Optional[str]) -> Optional[ChartType]:
    if ct is None:
        return None
    try:
        return ChartType(ct)
    except ValueError:
        raise HTTPException(
            status_code=422,  # 422 literal: Starlette deprecated the ENTITY constant name
            detail=f"Invalid chart_type '{ct}'. Valid: {[t.value for t in ChartType]}",
        )

# ---------------------------------------------------------------------------
# GET /admin/charts/data
# ---------------------------------------------------------------------------

@router.get(
    "/admin/charts/data",
    summary="Raw chart data as JSON",
    dependencies=[Depends(require_admin_or_manager)],
)
def get_chart_data(
    source: str = Query(..., description="One of: incidents, attendance, daily_reports, enrollments, kindergartens"),
    date_from: Optional[str] = Query(None),
    date_to: Optional[str] = Query(None),
    kindergarten_id: Optional[int] = Query(None),
    governorate: Optional[str] = Query(None),
    city: Optional[str] = Query(None),
    granularity: str = Query("month"),
    group_by: Optional[str] = Query(None),
    top_n: Optional[int] = Query(None),
    lang: str = Query("ar", pattern="^(ar|en)$"),
    db: Session = Depends(get_db),
) -> Dict[str, Any]:
    req = ChartRequest(
        source=_parse_source(source),
        date_from=date_from,
        date_to=date_to,
        kindergarten_id=kindergarten_id,
        governorate=governorate,
        city=city,
        granularity=Granularity(granularity) if granularity else Granularity.MONTH,
        group_by=group_by,
        top_n=top_n,
        lang=lang,
    )
    df = _svc.get_data(db, req)
    return {
        "source": source,
        "row_count": len(df),
        "columns": list(df.columns),
        "data": df.to_dict(orient="records"),
    }

# ---------------------------------------------------------------------------
# GET /admin/charts/render
# ---------------------------------------------------------------------------

@router.get(
    "/admin/charts/render",
    response_model=ChartResponse,
    summary="Render a Plotly chart as HTML",
    dependencies=[Depends(require_admin_or_manager)],
)
def render_chart(
    source: str = Query(...),
    chart_type: Optional[str] = Query(None, description="Override auto-selection"),
    date_from: Optional[str] = Query(None),
    date_to: Optional[str] = Query(None),
    kindergarten_id: Optional[int] = Query(None),
    governorate: Optional[str] = Query(None),
    city: Optional[str] = Query(None),
    granularity: str = Query("month"),
    group_by: Optional[str] = Query(None),
    top_n: Optional[int] = Query(None),
    title: Optional[str] = Query(None),
    lang: str = Query("ar", pattern="^(ar|en)$"),
    db: Session = Depends(get_db),
) -> ChartResponse:
    req = ChartRequest(
        source=_parse_source(source),
        chart_type=_parse_chart_type(chart_type),
        date_from=date_from,
        date_to=date_to,
        kindergarten_id=kindergarten_id,
        governorate=governorate,
        city=city,
        granularity=Granularity(granularity) if granularity else Granularity.MONTH,
        group_by=group_by,
        top_n=top_n,
        title=title,
        lang=lang,
    )
    try:
        return _svc.render(db, req)
    except Exception as exc:
        logger.exception("render_chart failed source=%s", source)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Chart rendering failed. Use the correlation ID to investigate.",
        )

# ---------------------------------------------------------------------------
# POST /admin/charts/suggest

def _suggest(db: Session, req: SuggestRequest) -> SuggestResponse:
    """Shared suggestion logic.

    Kept as a plain function so the two routes below can each apply their own rate
    limit without one endpoint calling the other — chaining them would charge a
    single client request against the limiter twice.
    """
    try:
        return _svc.suggest(db, req)
    except Exception:
        logger.exception("suggest failed source=%s", req.source)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Chart suggestion failed. Use the correlation ID to investigate.",
        )


# Decorator order matters: @router.post must sit ABOVE @limiter.limit so the router
# registers the rate-limited wrapper. With the two swapped, the router captured the
# bare function and the limit was never enforced on this path.
@router.post(
    "/admin/charts/suggest",
    response_model=SuggestResponse,
    summary="Auto-suggest chart types for a data source",
    dependencies=[Depends(require_admin_or_manager)],
)
@limiter.limit(settings.RATE_LIMIT_ADMIN_WRITE)
def suggest_charts(request: Request, req: SuggestRequest, db: Session = Depends(get_db)) -> SuggestResponse:
    return _suggest(db, req)

# ---------------------------------------------------------------------------
# GET /admin/charts/task/{task_id}
# ---------------------------------------------------------------------------

@router.get(
    "/admin/charts/task/{task_id}",
    response_model=TaskStatus,
    summary="Poll Celery task status for a heavy chart render",
    dependencies=[Depends(require_admin_or_manager)],
)
def get_task_status(task_id: str) -> TaskStatus:
    from celery_app import celery_app

    result = celery_app.AsyncResult(task_id)
    try:
        state = result.state  # PENDING / STARTED / SUCCESS / FAILURE
    except Exception:
        return TaskStatus(task_id=task_id, status="PENDING", progress=0)

    if state == "SUCCESS":
        data = result.result or {}
        return TaskStatus(
            task_id=task_id,
            status="SUCCESS",
            result=ChartResponse(**data),
            progress=100,
        )
    elif state == "FAILURE":
        return TaskStatus(task_id=task_id, status="FAILURE", error=str(result.result), progress=0)
    else:
        progress = result.info.get("progress", 10) if isinstance(result.info, dict) else 10
        return TaskStatus(task_id=task_id, status=state, progress=progress)

# ---------------------------------------------------------------------------
# GET /admin/charts/dashboard (HTML page)
# ---------------------------------------------------------------------------

# NOTE: GET /admin/analytics/charts (the explorer PAGE) is served by
# frontend_orig.admin_charts_explorer, which the admin sidebar contract expects to own it.
# charts_api owns only the data / render / redirect endpoints below — declaring the page
# route here as well produced a duplicate registration for the same method+path.

@router.get(
    "/admin/charts/dashboard",
    summary="Legacy charts explorer dashboard",
    dependencies=[Depends(require_admin_or_manager)],
)
def legacy_charts_dashboard(request: Request) -> RedirectResponse:
    query_string = request.url.query
    dest = "/admin/analytics/charts"
    if query_string:
        dest += f"?{query_string}"
    return RedirectResponse(url=dest, status_code=status.HTTP_301_MOVED_PERMANENTLY)


# Canonical admin API namespace. The legacy `/admin/charts/*` paths above are
# retained for compatibility with existing pages.
@router.get(
    "/api/admin/charts/data",
    response_model=ChartResponse,
    summary="Render a Plotly chart as JSON data",
    dependencies=[Depends(require_admin_or_manager)],
)
def get_admin_chart_data(
    source: str = Query(..., description="One of: incidents, attendance, daily_reports, enrollments, kindergartens"),
    chart_type: Optional[str] = Query(None, description="Override auto-selection"),
    date_from: Optional[str] = Query(None),
    date_to: Optional[str] = Query(None),
    kindergarten_id: Optional[int] = Query(None),
    governorate: Optional[str] = Query(None),
    city: Optional[str] = Query(None),
    granularity: str = Query("month"),
    group_by: Optional[str] = Query(None),
    top_n: Optional[int] = Query(None),
    title: Optional[str] = Query(None),
    lang: str = Query("ar", pattern="^(ar|en)$"),
    db: Session = Depends(get_db),
) -> ChartResponse:
    return _svc.render(
        db,
        ChartRequest(
            source=_parse_source(source),
            chart_type=_parse_chart_type(chart_type),
            date_from=date_from,
            date_to=date_to,
            kindergarten_id=kindergarten_id,
            governorate=governorate,
            city=city,
            granularity=Granularity(granularity) if granularity else Granularity.MONTH,
            group_by=group_by,
            top_n=top_n,
            title=title,
            lang=lang,
        ),
    )


@router.get(
    "/api/admin/charts/render",
    response_model=ChartResponse,
    summary="Render a Plotly chart as HTML",
    dependencies=[Depends(require_admin_or_manager)],
)
def render_admin_chart(
    source: str = Query(...),
    chart_type: Optional[str] = Query(None, description="Override auto-selection"),
    date_from: Optional[str] = Query(None),
    date_to: Optional[str] = Query(None),
    kindergarten_id: Optional[int] = Query(None),
    governorate: Optional[str] = Query(None),
    city: Optional[str] = Query(None),
    granularity: str = Query("month"),
    group_by: Optional[str] = Query(None),
    top_n: Optional[int] = Query(None),
    title: Optional[str] = Query(None),
    lang: str = Query("ar", pattern="^(ar|en)$"),
    db: Session = Depends(get_db),
) -> ChartResponse:
    return render_chart(
        source=source,
        chart_type=chart_type,
        date_from=date_from,
        date_to=date_to,
        kindergarten_id=kindergarten_id,
        governorate=governorate,
        city=city,
        granularity=granularity,
        group_by=group_by,
        top_n=top_n,
        title=title,
        lang=lang,
        db=db,
    )


@router.post(
    "/api/admin/charts/suggest",
    response_model=SuggestResponse,
    summary="Auto-suggest chart types for a data source",
    dependencies=[Depends(require_admin_or_manager)],
)
@limiter.limit(settings.RATE_LIMIT_ADMIN_WRITE)
def suggest_admin_charts(request: Request, req: SuggestRequest, db: Session = Depends(get_db)) -> SuggestResponse:
    return _suggest(db, req)


@router.get(
    "/api/admin/charts/task/{task_id}",
    response_model=TaskStatus,
    summary="Poll Celery task status for a heavy chart render",
    dependencies=[Depends(require_admin_or_manager)],
)
def get_admin_chart_task_status(task_id: str) -> TaskStatus:
    return get_task_status(task_id)


@router.get(
    "/api/admin/charts/dashboard",
    summary="Legacy charts explorer dashboard",
    dependencies=[Depends(require_admin_or_manager)],
)
def api_admin_charts_dashboard(request: Request) -> RedirectResponse:
    query_string = request.url.query
    dest = "/admin/analytics/charts"
    if query_string:
        dest += f"?{query_string}"
    return RedirectResponse(url=dest, status_code=status.HTTP_301_MOVED_PERMANENTLY)


# =============================================================================
# Scheduled exports
# =============================================================================
# The router already requires admin, so these inherit that. Schedules are
# per-user: an admin only ever sees and deletes their own.

class ScheduledExportIn(BaseModel):
    source: str
    chart_type: Optional[str] = None
    date_preset: str = "last_30"
    export_format: str = "CSV"
    frequency: str = "WEEKLY"
    hour_utc: int = Field(default=6, ge=0, le=23)
    recipient_email: EmailStr
    governorate: Optional[str] = None

    @field_validator("frequency")
    @classmethod
    def _freq(cls, v: str) -> str:
        if v not in {"DAILY", "WEEKLY", "MONTHLY"}:
            raise ValueError("frequency must be DAILY, WEEKLY or MONTHLY")
        return v

    @field_validator("export_format")
    @classmethod
    def _fmt(cls, v: str) -> str:
        if v not in {"CSV", "JSON"}:
            raise ValueError("export_format must be CSV or JSON")
        return v


def _serialize_schedule(row: "models.ScheduledChartExport") -> Dict[str, Any]:
    return {
        "id": row.id,
        "source": row.source,
        "chart_type": row.chart_type,
        "date_preset": row.date_preset,
        "export_format": row.export_format,
        "frequency": row.frequency,
        "hour_utc": row.hour_utc,
        "recipient_email": row.recipient_email,
        "governorate": row.governorate,
        "is_active": row.is_active,
        "last_run_at": row.last_run_at.isoformat() if row.last_run_at else None,
        "last_status": row.last_status,
        "next_run_at": row.next_run_at.isoformat() if row.next_run_at else None,
    }


@router.get("/api/admin/charts/scheduled-exports")
@limiter.limit(settings.RATE_LIMIT_ADMIN_READ)
def list_scheduled_exports(
    request: Request,
    db: Session = Depends(get_db),
    current_user=Depends(require_admin),
) -> Dict[str, Any]:
    rows = (
        db.query(models.ScheduledChartExport)
        .filter(models.ScheduledChartExport.user_id == current_user.id)
        .order_by(models.ScheduledChartExport.id.desc())
        .all()
    )
    return {"schedules": [_serialize_schedule(r) for r in rows]}


@router.post("/api/admin/charts/scheduled-exports", status_code=status.HTTP_201_CREATED)
@limiter.limit(settings.RATE_LIMIT_ADMIN_WRITE)
def create_scheduled_export(
    request: Request,
    payload: ScheduledExportIn,
    db: Session = Depends(get_db),
    current_user=Depends(require_admin),
) -> Dict[str, Any]:
    from chart_export_tasks import compute_next_run

    row = models.ScheduledChartExport(
        user_id=current_user.id,
        source=payload.source,
        chart_type=payload.chart_type,
        date_preset=payload.date_preset,
        export_format=payload.export_format,
        frequency=payload.frequency,
        hour_utc=payload.hour_utc,
        recipient_email=str(payload.recipient_email),
        governorate=payload.governorate,
        is_active=True,
        # Set at creation so the hourly sweep has something to compare against;
        # a NULL next_run_at is never picked up.
        next_run_at=compute_next_run(payload.frequency, payload.hour_utc),
    )
    db.add(row)
    db.commit()
    db.refresh(row)
    log_audit_event(
        db,
        action=AuditAction.SCHEDULED_EXPORT_CREATED,
        actor=current_user,
        target_type="scheduled_chart_export",
        target_ids=row.id,
        metadata={
            "source": row.source,
            "frequency": row.frequency,
            "recipient_email": row.recipient_email,
        },
    )
    return _serialize_schedule(row)


@router.delete("/api/admin/charts/scheduled-exports/{schedule_id}")
@limiter.limit(settings.RATE_LIMIT_ADMIN_WRITE)
def delete_scheduled_export(
    request: Request,
    schedule_id: int,
    db: Session = Depends(get_db),
    current_user=Depends(require_admin),
) -> Dict[str, Any]:
    row = (
        db.query(models.ScheduledChartExport)
        .filter(
            models.ScheduledChartExport.id == schedule_id,
            # Scoped to the owner so one admin cannot delete another's schedule.
            models.ScheduledChartExport.user_id == current_user.id,
        )
        .first()
    )
    if row is None:
        raise HTTPException(status_code=404, detail="Scheduled export not found")
    db.delete(row)
    db.commit()
    log_audit_event(
        db,
        action=AuditAction.SCHEDULED_EXPORT_DELETED,
        actor=current_user,
        target_type="scheduled_chart_export",
        target_ids=schedule_id,
    )
    return {"deleted": schedule_id}
