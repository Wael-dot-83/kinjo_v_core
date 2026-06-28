"""
Celery application for KinJo background task processing.

Tasks run eagerly in-process when TESTING=True so no Redis is required in CI.
"""
import logging

from celery import Celery
from celery.signals import task_prerun, task_postrun, task_failure, task_revoked

from config import settings

logger = logging.getLogger(__name__)

celery_app = Celery(
    "kinjo",
    broker=settings.CELERY_BROKER_URL,
    backend=settings.CELERY_RESULT_BACKEND,
    include=["messaging_tasks", "charts.tasks", "backup_tasks", "import_tasks", "export_tasks"],
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
        "dispatch-scheduled-messages": {
            "task": "messaging_tasks.dispatch_scheduled_messages",
            "schedule": 60.0,
        },
    },
)


_task_stats = {"completed": 0, "failed": 0, "durations": []}
_task_start_times = {}


@task_prerun.connect
def _on_task_prerun(task_id, task, **kwargs):
    import time
    _task_start_times[task_id] = time.monotonic()


@task_postrun.connect
def _on_task_postrun(task_id, task, retval=None, state=None, **kwargs):
    import time
    start = _task_start_times.pop(task_id, None)
    if start is not None:
        duration_ms = (time.monotonic() - start) * 1000
        _task_stats["durations"].append(duration_ms)
        if len(_task_stats["durations"]) > 5000:
            _task_stats["durations"] = _task_stats["durations"][-5000:]
    _task_stats["completed"] += 1


@task_failure.connect
def _on_task_failure(task_id, exception, traceback, sender, **kwargs):
    _task_stats["failed"] += 1
    _task_start_times.pop(task_id, None)


@task_revoked.connect
def _on_task_revoked(request, terminated, signum, **kwargs):
    _task_start_times.pop(getattr(request, "id", None), None)


def get_task_stats():
    durations = _task_stats["durations"]
    if not durations:
        return {
            "completed": _task_stats["completed"],
            "failed": _task_stats["failed"],
            "avg_duration_ms": 0,
            "p50_duration_ms": 0,
            "p95_duration_ms": 0,
        }
    n = len(durations)
    sorted_d = sorted(durations)
    return {
        "completed": _task_stats["completed"],
        "failed": _task_stats["failed"],
        "avg_duration_ms": round(sum(durations) / n, 1),
        "p50_duration_ms": round(sorted_d[n // 2], 1),
        "p95_duration_ms": round(sorted_d[min(int(n * 0.95), n - 1)], 1),
    }


__all__ = ["celery_app", "get_task_stats"]
