"""Celery tasks for heavy chart processing (>10k row datasets)."""

from __future__ import annotations

import logging
from typing import Any, Dict

from celery import shared_task

logger = logging.getLogger(__name__)


@shared_task(bind=True, name="charts.render_chart", max_retries=2, default_retry_delay=5)
def render_chart_task(self, req_dict: Dict[str, Any]) -> Dict[str, Any]:
    """
    Background chart build for large datasets.

    Returns a JSON-serialisable ``ChartResponse`` dict, which is exactly what
    ``charts_api.get_task_status`` feeds back into ``ChartResponse(**data)``.
    """
    from database import SessionLocal
    from charts.schemas import ChartRequest
    from charts.service import ChartService

    try:
        req = ChartRequest(**req_dict)
        db = SessionLocal()
        try:
            # allow_offload=False — this *is* the offloaded run. Letting it offload
            # again would submit a fresh task for the same data on every attempt.
            response = ChartService().render(db, req, allow_offload=False)
            return response.model_dump(mode="json")
        finally:
            db.close()
    except Exception as exc:
        logger.exception("render_chart_task failed for req=%s", req_dict)
        raise self.retry(exc=exc)
