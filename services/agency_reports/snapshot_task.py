"""Celery task for nightly agency report snapshot computation.

Runs nightly, computing each agency's reports for the previous day and
upserting into the ``agency_report_snapshots`` table.  This pre-materializes
aggregated data so report loads query pre-computed rows instead of re-joining
raw tables on every request.
"""
from __future__ import annotations

import logging
from datetime import date, timedelta, timezone

from celery_app import celery_app
from database import SessionLocal

import models

logger = logging.getLogger(__name__)

_JORDAN_TZ = timezone(timedelta(hours=3))

# Agencies and report codes to snapshot nightly.
_SNAPSHOT_TARGETS: list[tuple[str, str]] = [
    ("ncfa", "child_family_profile"),
    ("ncfa", "family_communication_counts"),
]


@celery_app.task(name="agency_report_snapshot_task.run_daily_snapshots", bind=True, max_retries=1, default_retry_delay=120)
def run_daily_snapshots(self) -> dict:
    """Compute and upsert agency report snapshots for yesterday's date.

    Returns a summary dict with per-agency row counts.
    """
    from services.agency_reports.registry import get_agency_service

    today = date.today()
    snapshot_date = today - timedelta(days=1)
    results: dict[str, int] = {}

    db = SessionLocal()
    try:
        for agency_code, report_code in _SNAPSHOT_TARGETS:
            try:
                service = get_agency_service(agency_code, db)
                payload = service.compute_report(report_code, {})
                rows_written = _upsert_snapshot(db, agency_code, report_code, snapshot_date, payload)
                results[f"{agency_code}/{report_code}"] = rows_written
                _update_snapshot_metadata(db, agency_code, report_code, snapshot_date, rows_written)
            except Exception:
                logger.exception("Snapshot failed for %s/%s", agency_code, report_code)
                results[f"{agency_code}/{report_code}"] = -1
        db.commit()
    except Exception:
        db.rollback()
        logger.exception("Daily snapshot run failed")
        raise
    finally:
        db.close()

    return {"snapshot_date": snapshot_date.isoformat(), "results": results}


def _upsert_snapshot(
    db, agency_code: str, report_code: str, snapshot_date: date, payload: dict
) -> int:
    """Upsert breakdown rows from a report payload into agency_report_snapshots."""
    breakdowns = payload.get("breakdowns", [])
    if not breakdowns:
        return 0

    written = 0
    for row in breakdowns:
        governorate = row.get("governorate")
        district = row.get("city") or row.get("district")
        gender = row.get("gender")
        age_group = row.get("age_group")
        count = row.get("count", 0)

        if count is None:
            continue

        existing = (
            db.query(models.AgencyReportSnapshot)
            .filter(
                models.AgencyReportSnapshot.agency_code == agency_code,
                models.AgencyReportSnapshot.report_code == report_code,
                models.AgencyReportSnapshot.snapshot_date == snapshot_date,
                models.AgencyReportSnapshot.governorate == governorate if governorate else models.AgencyReportSnapshot.governorate.is_(None),
                models.AgencyReportSnapshot.district == district if district else models.AgencyReportSnapshot.district.is_(None),
                models.AgencyReportSnapshot.gender == gender if gender else models.AgencyReportSnapshot.gender.is_(None),
                models.AgencyReportSnapshot.age_group == age_group if age_group else models.AgencyReportSnapshot.age_group.is_(None),
                models.AgencyReportSnapshot.metric_key == "count",
            )
            .first()
        )

        if existing:
            existing.metric_value = count
        else:
            db.add(models.AgencyReportSnapshot(
                agency_code=agency_code,
                report_code=report_code,
                snapshot_date=snapshot_date,
                governorate=governorate,
                district=district,
                gender=gender,
                age_group=age_group,
                metric_key="count",
                metric_value=count,
                dimension=row,
            ))
        written += 1

    return written


def _update_snapshot_metadata(
    db, agency_code: str, report_code: str, snapshot_date: date, row_count: int
) -> None:
    """Update or create the snapshot_metadata row for this agency/report."""
    from datetime import datetime
    meta = (
        db.query(models.SnapshotMetadata)
        .filter(
            models.SnapshotMetadata.agency_code == agency_code,
            models.SnapshotMetadata.report_code == report_code,
        )
        .first()
    )
    now = datetime.now(_JORDAN_TZ)
    if meta:
        meta.last_computed_at = now
        meta.row_count = row_count
        meta.snapshot_date = snapshot_date
    else:
        db.add(models.SnapshotMetadata(
            agency_code=agency_code,
            report_code=report_code,
            last_computed_at=now,
            row_count=row_count,
            snapshot_date=snapshot_date,
        ))


@celery_app.task(name="agency_report_snapshot_task.invalidate_cache")
def invalidate_cache(metric_namespace: str = None, agency_code: str = None, report_code: str = None) -> int:
    """Invalidate entries in the unified_metric_cache.

    Called when underlying data changes (e.g., after a child enrollment update)
    to ensure stale cached metrics are not served.
    """
    db = SessionLocal()
    try:
        q = db.query(models.UnifiedMetricCache)
        if metric_namespace:
            q = q.filter(models.UnifiedMetricCache.metric_namespace == metric_namespace)
        if agency_code:
            q = q.filter(models.UnifiedMetricCache.agency_code == agency_code)
        if report_code:
            q = q.filter(models.UnifiedMetricCache.report_code == report_code)
        count = q.delete()
        db.commit()
        return count
    except Exception:
        db.rollback()
        raise
    finally:
        db.close()
