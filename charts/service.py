"""ChartService — orchestrates data loading, advisor, caching, and rendering.

Data source registry:
  Each loader accepts (db, req) and returns a pandas DataFrame.
  Column names are chosen to be chart-builder-friendly (short, lowercase).

Model column facts:
  Incident.type          (enum, NOT incident_type)
  Incident.occurred_at   (DateTime — the event timestamp)
  Incident.deleted_at    (soft-delete, must filter IS NULL)
  AttendanceLog.class_id → Class.kindergarten_id (no direct kg FK)
  DailyReport.kindergarten_id, DailyReport.mood, DailyReport.date
"""

from __future__ import annotations

import json
import logging
from datetime import date, timedelta
from utils.time_utils import today_amman as _today
from typing import Callable, Dict, Optional, Tuple

import pandas as pd
from sqlalchemy.orm import Session

from charts import cache as chart_cache
from charts.advisor import ChartAdvisor
from charts.builders import get_builder
from charts.schemas import (
    ChartRequest,
    ChartResponse,
    ChartSource,
    ChartType,
    DataProfile,
    SuggestRequest,
    SuggestResponse,
)

logger = logging.getLogger(__name__)

_advisor = ChartAdvisor()

# ---------------------------------------------------------------------------
# Data loaders
# ---------------------------------------------------------------------------

def _date_bounds(req: ChartRequest) -> Tuple[date, date]:
    today = _today()
    d_from = date.fromisoformat(req.date_from) if req.date_from else today - timedelta(days=365)
    d_to = date.fromisoformat(req.date_to) if req.date_to else today
    return d_from, d_to


def _load_incidents(db: Session, req: ChartRequest) -> pd.DataFrame:
    from sqlalchemy import func, extract
    import models

    d_from, d_to = _date_bounds(req)
    base_filter = [
        models.Incident.deleted_at.is_(None),
        models.Incident.occurred_at >= d_from,
        models.Incident.occurred_at <= d_to,
    ]
    if req.kindergarten_id:
        base_filter.append(models.Incident.kindergarten_id == req.kindergarten_id)

    group_by_col = req.group_by or "type"
    if group_by_col == "type":
        q = (
            db.query(
                models.Incident.type.label("incident_type"),
                extract("year", models.Incident.occurred_at).label("yr"),
                extract("month", models.Incident.occurred_at).label("mo"),
                func.count().label("count"),
            )
            .filter(*base_filter)
            .group_by(models.Incident.type, "yr", "mo")
            .order_by("yr", "mo")
        )
        rows = q.all()
        df = pd.DataFrame(rows, columns=["incident_type", "yr", "mo", "count"])
        df["incident_type"] = df["incident_type"].astype(str).str.replace("IncidentType.", "", regex=False)
        if not df.empty:
            df["month"] = pd.to_datetime(
                df["yr"].astype(int).astype(str) + "-" + df["mo"].astype(int).astype(str).str.zfill(2) + "-01"
            )
            df = df.drop(columns=["yr", "mo"])
    else:
        q = (
            db.query(
                models.Incident.severity_level.label("severity"),
                func.count().label("count"),
            )
            .filter(*base_filter)
            .group_by(models.Incident.severity_level)
        )
        rows = q.all()
        df = pd.DataFrame(rows, columns=["severity", "count"])
        df["severity"] = df["severity"].astype(str).str.replace("SeverityLevel.", "", regex=False)
    return df


def _load_attendance(db: Session, req: ChartRequest) -> pd.DataFrame:
    from sqlalchemy import func
    import models

    d_from, d_to = _date_bounds(req)
    q = (
        db.query(
            models.AttendanceLog.date.label("date"),
            models.AttendanceLog.status.label("status"),
            func.count().label("count"),
        )
        .filter(
            models.AttendanceLog.date >= d_from,
            models.AttendanceLog.date <= d_to,
        )
    )
    if req.kindergarten_id:
        q = q.join(models.Class, models.AttendanceLog.class_id == models.Class.id).filter(
            models.Class.kindergarten_id == req.kindergarten_id
        )
    q = q.group_by(models.AttendanceLog.date, models.AttendanceLog.status).order_by(
        models.AttendanceLog.date
    )
    rows = q.all()
    df = pd.DataFrame(rows, columns=["date", "status", "count"])
    df["status"] = df["status"].astype(str).str.replace("AttendanceStatus.", "")
    df["date"] = pd.to_datetime(df["date"])
    return df


def _load_daily_reports(db: Session, req: ChartRequest) -> pd.DataFrame:
    from sqlalchemy import func
    import models

    d_from, d_to = _date_bounds(req)
    q = (
        db.query(
            models.DailyReport.mood.label("mood"),
            func.count().label("count"),
        )
        .filter(
            models.DailyReport.date >= d_from,
            models.DailyReport.date <= d_to,
        )
    )
    if req.kindergarten_id:
        q = q.filter(models.DailyReport.kindergarten_id == req.kindergarten_id)
    q = q.group_by(models.DailyReport.mood).order_by(func.count().desc())
    rows = q.all()
    df = pd.DataFrame(rows, columns=["mood", "count"])
    return df


def _load_enrollments(db: Session, req: ChartRequest) -> pd.DataFrame:
    from sqlalchemy import func, extract
    import models

    d_from, d_to = _date_bounds(req)
    base_filter = [
        models.EnrollmentApplication.created_at >= d_from,
        models.EnrollmentApplication.created_at <= d_to,
    ]
    if req.kindergarten_id:
        base_filter.append(models.EnrollmentApplication.kindergarten_id == req.kindergarten_id)
    q = (
        db.query(
            models.EnrollmentApplication.status.label("status"),
            extract("year", models.EnrollmentApplication.created_at).label("yr"),
            extract("month", models.EnrollmentApplication.created_at).label("mo"),
            func.count().label("count"),
        )
        .filter(*base_filter)
        .group_by(models.EnrollmentApplication.status, "yr", "mo")
        .order_by("yr", "mo")
    )
    rows = q.all()
    df = pd.DataFrame(rows, columns=["status", "yr", "mo", "count"])
    df["status"] = df["status"].astype(str).str.replace("EnrollmentStatus.", "", regex=False)
    if not df.empty:
        df["month"] = pd.to_datetime(
            df["yr"].astype(int).astype(str) + "-" + df["mo"].astype(int).astype(str).str.zfill(2) + "-01"
        )
        df = df.drop(columns=["yr", "mo"])
    return df


def _load_kindergartens(db: Session, req: ChartRequest) -> pd.DataFrame:
    from sqlalchemy import func, and_
    import models

    q = (
        db.query(
            models.Kindergarten.name_ar.label("kindergarten"),
            models.Kindergarten.governorate.label("governorate"),
            func.coalesce(func.sum(models.Class.capacity_total), 0).label("capacity"),
            func.coalesce(func.sum(models.Class.enrolled_children_count), 0).label("enrolled"),
        )
        .outerjoin(
            models.Class,
            and_(
                models.Class.kindergarten_id == models.Kindergarten.id,
                models.Class.deleted_at.is_(None),
            ),
        )
        .group_by(models.Kindergarten.id, models.Kindergarten.name_ar, models.Kindergarten.governorate)
    )
    if req.governorate:
        q = q.filter(models.Kindergarten.governorate == req.governorate)
    rows = q.all()
    df = pd.DataFrame(rows, columns=["kindergarten", "governorate", "capacity", "enrolled"])
    return df


_LOADERS: Dict[ChartSource, Callable[[Session, ChartRequest], pd.DataFrame]] = {
    ChartSource.INCIDENTS: _load_incidents,
    ChartSource.ATTENDANCE: _load_attendance,
    ChartSource.DAILY_REPORTS: _load_daily_reports,
    ChartSource.ENROLLMENTS: _load_enrollments,
    ChartSource.KINDERGARTENS: _load_kindergartens,
}


# ---------------------------------------------------------------------------
# ChartService
# ---------------------------------------------------------------------------

class ChartService:
    """Public API for the charting subsystem."""

    HEAVY_ROW_THRESHOLD = 10_000

    def get_data(self, db: Session, req: ChartRequest) -> pd.DataFrame:
        """Load raw data for the given source, with Redis caching."""
        import io as _io
        cache_params = req.model_dump()
        cached = chart_cache.get_raw(cache_params)
        if cached:
            return pd.read_json(_io.StringIO(cached), orient="split")

        loader = _LOADERS.get(req.source)
        if loader is None:
            raise ValueError(f"Unknown chart source: {req.source}")
        df = loader(db, req)

        chart_cache.set_raw(cache_params, df.to_json(orient="split", date_format="iso"))
        return df

    def render(self, db: Session, req: ChartRequest) -> ChartResponse:
        """
        Render a chart as HTML.  Returns immediately for small datasets.
        For large datasets (>10k rows) submit a Celery task and return task_id.
        """
        cache_params = {**req.model_dump(), "chart_type": req.chart_type}
        cached_html = chart_cache.get_render(cache_params)
        if cached_html:
            return ChartResponse(
                chart_type=req.chart_type or ChartType.BAR,
                source=req.source,
                html=cached_html,
                title=req.title or "",
                row_count=0,
                cached=True,
            )

        df = self.get_data(db, req)

        if len(df) >= self.HEAVY_ROW_THRESHOLD:
            task_id = self._submit_task(req)
            return ChartResponse(
                chart_type=req.chart_type or ChartType.BAR,
                source=req.source,
                html="",
                title=req.title or "",
                row_count=len(df),
                task_id=task_id,
            )

        chart_type = req.chart_type or self._auto_type(df, req.source)
        html = self._build_html(df, req, chart_type)

        chart_cache.set_render(cache_params, html)
        return ChartResponse(
            chart_type=chart_type,
            source=req.source,
            html=html,
            title=req.title or "",
            row_count=len(df),
        )

    def suggest(self, db: Session, req: SuggestRequest) -> SuggestResponse:
        """Return chart-type suggestions for the given source + filters."""
        chart_req = ChartRequest(
            source=req.source,
            date_from=req.date_from,
            date_to=req.date_to,
            kindergarten_id=req.kindergarten_id,
            governorate=req.governorate,
        )
        df = self.get_data(db, chart_req)
        suggestions, profile = _advisor.suggest(df, req.source, req.max_suggestions)
        return SuggestResponse(
            source=req.source,
            suggestions=suggestions,
            row_count=len(df),
            profile=profile.model_dump(),
        )

    # ── Internal helpers ───────────────────────────────────────────────

    def _auto_type(self, df: pd.DataFrame, source: ChartSource) -> ChartType:
        suggestions, _ = _advisor.suggest(df, source, max_suggestions=1)
        return suggestions[0].chart_type if suggestions else ChartType.BAR

    def _build_html(self, df: pd.DataFrame, req: ChartRequest, chart_type: ChartType) -> str:
        patched_req = req.model_copy(update={"chart_type": chart_type})
        builder = get_builder(chart_type)
        return builder.render(df, patched_req)

    def _submit_task(self, req: ChartRequest) -> str:
        from charts.tasks import render_chart_task
        result = render_chart_task.delay(req.model_dump())
        return result.id
