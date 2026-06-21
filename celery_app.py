"""
Celery application for KinJo background task processing.

Tasks run eagerly in-process when TESTING=True so no Redis is required in CI.
"""
import logging

from celery import Celery

from config import settings

logger = logging.getLogger(__name__)

celery_app = Celery(
    "kinjo",
    broker=settings.CELERY_BROKER_URL,
    backend=settings.CELERY_RESULT_BACKEND,
    include=["messaging_tasks", "charts.tasks"],
)

celery_app.conf.update(
    task_serializer="json",
    accept_content=["json"],
    result_serializer="json",
    timezone="UTC",
    enable_utc=True,
    task_always_eager=settings.TESTING,
    task_eager_propagates=settings.TESTING,
    beat_schedule={
        # Production requirement: run exactly one Celery Beat scheduler instance
        # per environment for this schedule to avoid duplicate dispatch triggers.
        "dispatch-scheduled-messages": {
            "task": "messaging_tasks.dispatch_scheduled_messages",
            "schedule": 60.0,
        },
    },
)

__all__ = ["celery_app"]
