"""
Celery application configuration.
"""
from celery import Celery

from config import settings


celery_app = Celery(
    "kinjo",
    broker=settings.CELERY_BROKER_URL,
    backend=settings.CELERY_RESULT_BACKEND
)

celery_app.conf.update(
    task_serializer="json",
    accept_content=["json"],
    result_serializer="json",
    timezone="UTC",
    enable_utc=True,
    task_always_eager=settings.TESTING,
    task_eager_propagates=False,
)


__all__ = ["celery_app"]
