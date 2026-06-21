"""Celery tasks for heavy chart processing (>10k row datasets)."""

from __future__ import annotations

import logging
from typing import Any, Dict

from celery import shared_task

logger = logging.getLogger(__name__)


@shared_task(bind=True, name="charts.render_chart", max_retries=2, default_retry_delay=5)
def render_chart_task(self, req_dict: Dict[str, Any]) -> Dict[str, Any]:
    """
    Background chart render for large datasets.
    Returns a serialised ChartResponse dict on success.
    """
    from database import SessionLocal
    from charts.schemas import ChartRequest, ChartSource, ChartType
    from charts.service import ChartService

    try:
        req = ChartRequest(**req_dict)
        db = SessionLocal()
        try:
            svc = ChartService()
            df = svc.get_data(db, req)
            chart_type = req.chart_type or svc._auto_type(df, req.source)
            html = svc._build_html(df, req, chart_type)

            from charts import cache as chart_cache
            cache_params = {**req_dict, "chart_type": chart_type}
            chart_cache.set_render(cache_params, html)

            return {
                "chart_type": chart_type,
                "source": req.source,
                "html": html,
                "title": req.title or "",
                "row_count": len(df),
                "cached": False,
            }
        finally:
            db.close()
    except Exception as exc:
        logger.exception("render_chart_task failed for req=%s", req_dict)
        raise self.retry(exc=exc)
