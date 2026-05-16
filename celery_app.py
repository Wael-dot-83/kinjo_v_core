"""
Celery application for KinJo background task processing.

The app is always created successfully at import time — Celery does not
connect to the broker until a task is dispatched or a worker starts.
In TESTING mode (TESTING=True), tasks run eagerly in-process so no
Redis instance is required.
"""
import logging

from celery import Celery

from config import settings

logger = logging.getLogger(__name__)

celery_app = Celery(
    "kinjo",
    broker=settings.REDIS_URL,
    backend=settings.REDIS_URL,
    include=["messaging_tasks"],
)

celery_app.conf.update(
    task_serializer="json",
    result_serializer="json",
    accept_content=["json"],
    timezone="UTC",
    enable_utc=True,
    # Run tasks synchronously in-process during tests (no broker needed)
    task_always_eager=settings.TESTING,
    task_eager_propagates=settings.TESTING,
    beat_schedule={
        "dispatch-scheduled-messages": {
            "task": "messaging_tasks.dispatch_scheduled_messages",
            "schedule": 60.0,  # every minute
        },
    },
)

logger.info(
    "Celery configured — broker=%s testing=%s",
    settings.REDIS_URL,
    settings.TESTING,
)
