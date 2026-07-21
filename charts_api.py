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
from fastapi.responses import HTMLResponse
from sqlalchemy.orm import Session

from database import get_db
from dependencies import require_admin, require_admin_or_manager
from rate_limiter import limiter
from config import settings
from frontend import templates  # use the singleton with globals/filters pre-configured
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

logger = logging.getLogger(__name__)
# Chart sources can aggregate network-wide operational data. Protect both the
# canonical API and its compatibility aliases at the router boundary.
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

@limiter.limit(settings.RATE_LIMIT_ADMIN_WRITE)

@router.post(
    "/admin/charts/suggest",
    response_model=SuggestResponse,
    summary="Auto-suggest chart types for a data source",
    dependencies=[Depends(require_admin_or_manager)],
)
def suggest_charts(request: Request, req: SuggestRequest, db: Session = Depends(get_db),) -> SuggestResponse:
    try:
        return _svc.suggest(db, req)
    except Exception as exc:
        logger.exception("suggest_charts failed source=%s", req.source)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Chart suggestion failed. Use the correlation ID to investigate.",
        )

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

# Bilingual display labels for the source and chart-type pickers. Kept beside the
# route that renders them so the template's context stays complete.
_SOURCE_LABELS_AR = {
    "incidents": "الحوادث", "attendance": "الحضور",
    "daily_reports": "التقارير اليومية", "enrollments": "التسجيلات",
    "kindergartens": "الحضانات",
}
_SOURCE_LABELS_EN = {
    "incidents": "Incidents", "attendance": "Attendance",
    "daily_reports": "Daily Reports", "enrollments": "Enrollments",
    "kindergartens": "Kindergartens",
}
_CHART_LABELS_AR = {
    "line": "خطي", "bar": "أعمدة", "scatter": "مبعثر", "pie": "دائري",
    "histogram": "مدرج تكراري", "box": "مربع", "heatmap": "خريطة حرارية",
    "funnel": "قمعي", "treemap": "شجري",
}
_CHART_LABELS_EN = {
    "line": "Line", "bar": "Bar", "scatter": "Scatter", "pie": "Pie",
    "histogram": "Histogram", "box": "Box", "heatmap": "Heatmap",
    "funnel": "Funnel", "treemap": "Treemap",
}

@router.get(
    "/admin/charts/dashboard",
    response_class=HTMLResponse,
    summary="Charts explorer dashboard",
    dependencies=[Depends(require_admin_or_manager)],
)
def charts_dashboard(
    request: Request,
    _: Any = Depends(require_admin_or_manager),
) -> HTMLResponse:
    return templates.TemplateResponse(
        request=request,
        name="admin/analytics/charts_dashboard.html",
        context={
            "sources": [s.value for s in ChartSource],
            "chart_types": [t.value for t in ChartType],
            "ui_lang": request.cookies.get("ui_lang", "ar"),
            "ui_dir": request.cookies.get("ui_dir", "rtl"),
            # The template renders both label sets behind a ui_lang guard, so all
            # four must be supplied or the page raises UndefinedError and 500s.
            "SOURCE_LABELS_AR": _SOURCE_LABELS_AR,
            "SOURCE_LABELS_EN": _SOURCE_LABELS_EN,
            "CHART_LABELS_AR": _CHART_LABELS_AR,
            "CHART_LABELS_EN": _CHART_LABELS_EN,
        },
    )


# Canonical admin API namespace. The legacy `/admin/charts/*` paths above are
# retained for compatibility with existing pages.
@router.get(
    "/api/admin/charts/data",
    summary="Raw chart data as JSON",
    dependencies=[Depends(require_admin_or_manager)],
)
def get_admin_chart_data(
    source: str = Query(..., description="One of: incidents, attendance, daily_reports, enrollments, kindergartens"),
    date_from: Optional[str] = Query(None),
    date_to: Optional[str] = Query(None),
    kindergarten_id: Optional[int] = Query(None),
    governorate: Optional[str] = Query(None),
    granularity: str = Query("month"),
    group_by: Optional[str] = Query(None),
    top_n: Optional[int] = Query(None),
    lang: str = Query("ar", pattern="^(ar|en)$"),
    db: Session = Depends(get_db),
) -> Dict[str, Any]:
    return get_chart_data(
        source=source,
        date_from=date_from,
        date_to=date_to,
        kindergarten_id=kindergarten_id,
        governorate=governorate,
        granularity=granularity,
        group_by=group_by,
        top_n=top_n,
        lang=lang,
        db=db,
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
    return suggest_charts(request=request, req=req, db=db)


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
    response_class=HTMLResponse,
    summary="Charts explorer dashboard",
    dependencies=[Depends(require_admin_or_manager)],
)
def admin_charts_dashboard(
    request: Request,
    _: Any = Depends(require_admin_or_manager),
) -> HTMLResponse:
    return charts_dashboard(request=request, _=_)
