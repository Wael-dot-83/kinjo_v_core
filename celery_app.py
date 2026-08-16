"""
Celery application for KinJo background task processing.

Tasks run eagerly in-process when TESTING=True so no Redis is required in CI.
"""
import logging

from celery import Celery
from celery.schedules import crontab
from celery.signals import task_prerun, task_postrun, task_failure, task_revoked

from config import settings

logger = logging.getLogger(__name__)

celery_app = Celery(
    "kinjo",
    broker=settings.CELERY_BROKER_URL,
    backend=settings.CELERY_RESULT_BACKEND,
    include=[
        "messaging_tasks", "charts.tasks", "backup_tasks", "import_tasks", "export_tasks",
        "heatmap_tasks", "chart_export_tasks", "notification_tasks",
    ],
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
        "redispatch-stale-pending-notifications": {
            "task": "notification_tasks.redispatch_stale_pending_notifications",
            "schedule": 60.0,
        },
        # Heat map dataset rebuild. Beat runs on UTC (see timezone/enable_utc above),
        # so this is expressed in UTC: 17:00 UTC == 20:00 Jordan (UTC+3). That is
        # after the Jordan business day, so the day's attendance and reports are
        # already recorded when the snapshot is taken — running at Jordan midnight
        # would stamp a date whose activity had barely begun.
        "regenerate-heatmap-dataset": {
            "task": "heatmap_tasks.regenerate_daily_indicators",
            "schedule": crontab(hour=17, minute=0),
        },
        # Daily automated backup + retention cleanup. Beat runs on UTC (see
        # timezone/enable_utc above), so BACKUP_SCHEDULE_HOUR / BACKUP_CLEANUP_HOUR
        # are interpreted as UTC hours-of-day — matching BackupScheduler's own
        # "2:00 AM UTC" convention (backup_manager.py). Scheduled runs are tagged
        # "automated" so the retention sweep can prune them; manual backups are
        # never auto-deleted. Cleanup runs an hour after the backup so the day's
        # fresh snapshot already exists before old ones are pruned.
        "run-daily-backup": {
            "task": "backup_tasks.run_backup",
            "schedule": crontab(hour=settings.BACKUP_SCHEDULE_HOUR, minute=0),
            "kwargs": {"backup_type": "automated"},
        },
        "cleanup-old-backups": {
            "task": "backup_tasks.cleanup_old_backups",
            "schedule": crontab(hour=settings.BACKUP_CLEANUP_HOUR, minute=0),
        },
        # Scheduled chart exports. Swept hourly rather than at fixed times so a
        # schedule can pick any UTC hour without needing its own beat entry;
        # each row carries its own next_run_at and is skipped until due.
        "run-due-chart-exports": {
            "task": "chart_export_tasks.run_due_exports",
            "schedule": crontab(minute=5),
        },
        # Agency report nightly snapshots. Runs at 21:00 UTC == 00:00 Jordan
        # (UTC+3), so the previous day's data is complete. Pre-materializes
        # aggregated rows so report loads query snapshots, not raw joins.
        "run-agency-report-snapshots": {
            "task": "agency_report_snapshot_task.run_daily_snapshots",
            "schedule": crontab(hour=21, minute=0),
        },
    },
)

# Ensure the snapshot task module is imported so Celery discovers it.
celery_app.conf.include = list(celery_app.conf.get("include", [])) + [
    "services.agency_reports.snapshot_task",
]


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
