"""Generate the production heat map indicator dataset from KinJo database data.

`/api/heatmap/*` reads a flat CSV (`PIPELINE_SOURCES["daily"]`). Before this module
that file had no producer, so the only thing that could satisfy it was the bundled
`test_data.csv` fixture — which the security repair (3868f25) correctly refuses to
serve in production. This module supplies the file from authoritative tables instead.

Design constraints, each traced in
`.kilo/phase1_reports/34_HEATMAP_PRODUCTION_DATA_CONTRACT.md`:

* **Governorate granularity only.** The CSV vocabulary also contains 20 qaḍāʼ-level
  codes (`JO-AM-01`…), but nothing in KinJo maps a `Kindergarten.district` onto them,
  so producing them would require inventing the mapping. 12 rows per day.
* **Unavailable is never zero.** Three columns have no defensible source in the domain
  model and are emitted as empty cells, matching the convention pinned by
  `tests/test_heatmap_unavailable_data.py` ("unavailable != 0").
* **Jordan UTC+3** for the snapshot date and every day-based window.
* **Atomic replacement.** The dataset is validated in full before it replaces the live
  file; a failure leaves the previous good file exactly where it was.
* **No caller-supplied paths, ever.** The destination is derived server-side and any
  override is checked against the approved directory.
"""
from __future__ import annotations

import hashlib
import json
import logging
import os
import tempfile
import threading
from dataclasses import dataclass, field
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional

import pandas as pd
from sqlalchemy import func
from sqlalchemy.orm import Session

import models
from utils.time_utils import now_amman, today_amman

from .. import constants as C
from .validate import validate_dataframe

logger = logging.getLogger(__name__)

# The one directory this module may write to. Anything else is a bug or an attack.
DATA_DIR = Path(__file__).resolve().parent.parent.parent / "data"
DAILY_DATASET = DATA_DIR / "daily_indicators.csv"
DATASET_METADATA = DATA_DIR / "daily_indicators.meta.json"

# Bump when the manifest's shape changes in a way readers must notice.
MANIFEST_SCHEMA_VERSION = 1

# Redis key carrying the active dataset version. An accelerator only — see
# _publish_version() for why correctness must not depend on it.
DATASET_VERSION_CACHE_KEY = "heatmap:dataset:version"
VERSION_KEY_TTL_SECONDS = 24 * 60 * 60

# Column order is the file's public contract; keep it stable.
CSV_COLUMNS: List[str] = [
    "date",
    "admin_id",
    "kindergartens_active",
    "kindergartens_inactive",
    "enrolled_children",
    "unregistered_children",
    "supervisors_count",
    "classes_count",
    "classes_without_supervisor",
    "critical_incidents",
    "protection_issues",
    "daily_reports_count",
    "absences_total",
    "absences_health_alerts",
    "tasks_overdue",
    "governance_score",
    "training_completion_pct",
]

# Columns KinJo cannot measure. Each is a missing vocabulary in the domain model, not
# a shortcut here — see contract §9.2. They are written as empty cells.
UNAVAILABLE_COLUMNS: Dict[str, str] = {
    "unregistered_children": (
        "no population denominator: KinJo only knows children it holds records for"
    ),
    "absences_health_alerts": (
        "AttendanceStatus has no health/sickness value (PRESENT/ABSENT/LATE/EXCUSED)"
    ),
    "protection_issues": (
        "IncidentType has no child-protection category; mapping BEHAVIOR onto it "
        "would be a category error"
    ),
}

# Low-frequency events are counted over a trailing window rather than a single day,
# matching compute_row()'s 30-day denominator for report completeness.
WINDOW_DAYS = 30

# One generation at a time per process. The dataset is a single file with a single
# writer; concurrent runs would race on the temp-file swap and waste identical work.
_GENERATION_LOCK = threading.Lock()


@dataclass
class GenerationResult:
    """Outcome of one generation attempt."""

    status: str                       # "success" | "skipped_locked" | "failed" | "empty"
    snapshot_date: Optional[str] = None
    rows_written: int = 0
    rows_rejected: int = 0
    governorates_covered: int = 0
    unresolved_governorates: List[str] = field(default_factory=list)
    validation_errors: List[Dict[str, Any]] = field(default_factory=list)
    output_path: Optional[str] = None
    generated_at: Optional[str] = None
    error: Optional[str] = None

    def as_dict(self) -> Dict[str, Any]:
        return {
            "status": self.status,
            "snapshot_date": self.snapshot_date,
            "rows_written": self.rows_written,
            "rows_rejected": self.rows_rejected,
            "governorates_covered": self.governorates_covered,
            "unresolved_governorates": self.unresolved_governorates,
            "validation_errors": self.validation_errors,
            "output_path": self.output_path,
            "generated_at": self.generated_at,
            "error": self.error,
        }


# ---------------------------------------------------------------------------
# Governorate resolution
# ---------------------------------------------------------------------------

def _governorate_code(raw: Optional[str]) -> Optional[str]:
    """Resolve a free-form Kindergarten.governorate onto a JO-XX code.

    Returns None when the value does not resolve. Callers must count those
    separately rather than bucketing them into a default governorate — silently
    attributing a kindergarten to the wrong governorate is worse than omitting it.
    """
    if not raw:
        return None
    # normalize_governorate() falls back to the lowercased input for anything it does
    # not recognise, so an unknown value simply misses GOVERNORATE_BY_SLUG below.
    slug = C.normalize_governorate(raw)
    if not slug:
        return None
    gov = C.GOVERNORATE_BY_SLUG.get(slug)
    return gov["code"] if gov else None


# ---------------------------------------------------------------------------
# Batched aggregation helpers
#
# Each returns {kindergarten_id: value}. One query per measure regardless of how
# many governorates exist — the per-governorate query style used elsewhere in this
# package would issue 12x this many round trips.
#
# NOTE ON SCOPE: database.py installs a `do_orm_execute` listener that constrains
# every ORM select on EnrollmentApplication, AttendanceLog, DailyReport and Incident
# to children satisfying KinJo's age policy. These counts therefore describe
# *age-eligible* children, consistently with the rest of the application — the heat
# map is not a back door around that policy. Bypassing it would need an explicit
# `include_out_of_range_children` execution option, which is deliberately not used.
# ---------------------------------------------------------------------------

def _counts_by_kg(rows: Iterable) -> Dict[int, int]:
    return {int(kg_id): int(count or 0) for kg_id, count in rows}


def _enrolled_children(db: Session, kg_ids: List[int]) -> Dict[int, int]:
    rows = (
        db.query(
            models.EnrollmentApplication.kindergarten_id,
            func.count(func.distinct(models.EnrollmentApplication.child_id)),
        )
        .filter(models.EnrollmentApplication.kindergarten_id.in_(kg_ids))
        .filter(models.EnrollmentApplication.status == models.EnrollmentStatus.ACTIVE)
        .filter(models.EnrollmentApplication.deleted_at.is_(None))
        .group_by(models.EnrollmentApplication.kindergarten_id)
        .all()
    )
    return _counts_by_kg(rows)


def _supervisors(db: Session, kg_ids: List[int]) -> Dict[int, int]:
    rows = (
        db.query(models.User.kindergarten_id, func.count(models.User.id))
        .filter(models.User.kindergarten_id.in_(kg_ids))
        .filter(models.User.role == models.UserRole.SUPERVISOR)
        .filter(models.User.deleted_at.is_(None))
        .group_by(models.User.kindergarten_id)
        .all()
    )
    return _counts_by_kg(rows)


def _classes(db: Session, kg_ids: List[int]) -> tuple[Dict[int, int], Dict[int, int]]:
    """Returns (total classes, classes with no supervisor assigned)."""
    total = _counts_by_kg(
        db.query(models.Class.kindergarten_id, func.count(models.Class.id))
        .filter(models.Class.kindergarten_id.in_(kg_ids))
        .filter(models.Class.deleted_at.is_(None))
        .group_by(models.Class.kindergarten_id)
        .all()
    )
    unsupervised = _counts_by_kg(
        db.query(models.Class.kindergarten_id, func.count(models.Class.id))
        .filter(models.Class.kindergarten_id.in_(kg_ids))
        .filter(models.Class.deleted_at.is_(None))
        .filter(models.Class.supervisor_id.is_(None))
        .group_by(models.Class.kindergarten_id)
        .all()
    )
    return total, unsupervised


def _critical_incidents(db: Session, kg_ids: List[int], since: date) -> Dict[int, int]:
    rows = (
        db.query(models.Incident.kindergarten_id, func.count(models.Incident.id))
        .filter(models.Incident.kindergarten_id.in_(kg_ids))
        .filter(models.Incident.deleted_at.is_(None))
        .filter(models.Incident.severity_level == models.SeverityLevel.CRITICAL)
        .filter(func.date(models.Incident.occurred_at) >= since)
        .group_by(models.Incident.kindergarten_id)
        .all()
    )
    return _counts_by_kg(rows)


def _daily_reports(db: Session, kg_ids: List[int], since: date, until: date) -> Dict[int, int]:
    rows = (
        db.query(models.DailyReport.kindergarten_id, func.count(models.DailyReport.id))
        .filter(models.DailyReport.kindergarten_id.in_(kg_ids))
        .filter(models.DailyReport.date >= since)
        .filter(models.DailyReport.date <= until)
        .group_by(models.DailyReport.kindergarten_id)
        .all()
    )
    return _counts_by_kg(rows)


def _absences(db: Session, kg_ids: List[int], on_day: date) -> Dict[int, int]:
    """Absences recorded for the snapshot day, joined through Class to its kindergarten."""
    rows = (
        db.query(models.Class.kindergarten_id, func.count(models.AttendanceLog.id))
        .join(models.Class, models.AttendanceLog.class_id == models.Class.id)
        .filter(models.Class.kindergarten_id.in_(kg_ids))
        .filter(models.AttendanceLog.date == on_day)
        .filter(models.AttendanceLog.status == models.AttendanceStatus.ABSENT)
        .group_by(models.Class.kindergarten_id)
        .all()
    )
    return _counts_by_kg(rows)


def _tasks_overdue(db: Session, kg_ids: List[int], as_of: date) -> Dict[int, int]:
    rows = (
        db.query(models.Task.kindergarten_id, func.count(models.Task.id))
        .filter(models.Task.kindergarten_id.in_(kg_ids))
        .filter(models.Task.deleted_at.is_(None))
        .filter(models.Task.due_date.isnot(None))
        .filter(models.Task.due_date < as_of)
        .filter(
            models.Task.status.notin_([models.TaskStatus.COMPLETED, models.TaskStatus.CANCELLED])
        )
        .group_by(models.Task.kindergarten_id)
        .all()
    )
    return _counts_by_kg(rows)


def _governance_scores(db: Session, kg_ids: List[int]) -> Dict[int, float]:
    rows = (
        db.query(
            models.GovernanceScore.kindergarten_id,
            func.avg(models.GovernanceScore.final_governance_score),
        )
        .filter(models.GovernanceScore.kindergarten_id.in_(kg_ids))
        .group_by(models.GovernanceScore.kindergarten_id)
        .all()
    )
    return {int(kg): float(v) for kg, v in rows if v is not None}


def _training_completion(db: Session, kg_ids: List[int]) -> Dict[int, tuple[int, int]]:
    """Returns {kindergarten_id: (completed, total)} over mandatory modules only."""
    rows = (
        db.query(
            models.StaffTrainingCompletion.kindergarten_id,
            models.StaffTrainingCompletion.status,
            func.count(models.StaffTrainingCompletion.id),
        )
        .join(
            models.TrainingModule,
            models.StaffTrainingCompletion.training_module_id == models.TrainingModule.id,
        )
        .filter(models.StaffTrainingCompletion.kindergarten_id.in_(kg_ids))
        .filter(models.TrainingModule.is_mandatory.is_(True))
        .group_by(
            models.StaffTrainingCompletion.kindergarten_id,
            models.StaffTrainingCompletion.status,
        )
        .all()
    )
    out: Dict[int, tuple[int, int]] = {}
    for kg_id, status, count in rows:
        if kg_id is None:
            continue  # network-level training has no kindergarten to attribute it to
        completed, total = out.get(int(kg_id), (0, 0))
        count = int(count or 0)
        if status == models.TrainingStatus.COMPLETED:
            completed += count
        out[int(kg_id)] = (completed, total + count)
    return out


# ---------------------------------------------------------------------------
# Row building
# ---------------------------------------------------------------------------

def build_rows(db: Session, snapshot_date: date) -> tuple[List[Dict[str, Any]], List[str]]:
    """Aggregate one row per governorate for `snapshot_date`.

    Returns (rows, unresolved_governorate_names).
    """
    window_start = snapshot_date - timedelta(days=WINDOW_DAYS)

    kindergartens = (
        db.query(
            models.Kindergarten.id,
            models.Kindergarten.governorate,
            models.Kindergarten.status,
        )
        .filter(models.Kindergarten.deleted_at.is_(None))
        .all()
    )

    kg_to_code: Dict[int, str] = {}
    unresolved: set[str] = set()
    for kg_id, governorate, _status in kindergartens:
        code = _governorate_code(governorate)
        if code is None:
            unresolved.add(str(governorate))
            continue
        kg_to_code[int(kg_id)] = code

    kg_ids = list(kg_to_code)

    # Per-governorate kindergarten status counts.
    active: Dict[str, int] = {}
    inactive: Dict[str, int] = {}
    for kg_id, governorate, status in kindergartens:
        code = kg_to_code.get(int(kg_id))
        if code is None:
            continue
        if status == models.KindergartenStatus.ACTIVE:
            active[code] = active.get(code, 0) + 1
        elif status == models.KindergartenStatus.INACTIVE:
            inactive[code] = inactive.get(code, 0) + 1

    if kg_ids:
        enrolled = _enrolled_children(db, kg_ids)
        supervisors = _supervisors(db, kg_ids)
        classes_total, classes_unsupervised = _classes(db, kg_ids)
        incidents = _critical_incidents(db, kg_ids, window_start)
        reports = _daily_reports(db, kg_ids, window_start, snapshot_date)
        absences = _absences(db, kg_ids, snapshot_date)
        overdue = _tasks_overdue(db, kg_ids, snapshot_date)
        governance = _governance_scores(db, kg_ids)
        training = _training_completion(db, kg_ids)
    else:
        enrolled = supervisors = classes_total = classes_unsupervised = {}
        incidents = reports = absences = overdue = governance = {}
        training = {}

    def _sum_by_code(per_kg: Dict[int, int]) -> Dict[str, int]:
        out: Dict[str, int] = {}
        for kg_id, value in per_kg.items():
            code = kg_to_code.get(kg_id)
            if code is not None:
                out[code] = out.get(code, 0) + int(value)
        return out

    enrolled_c = _sum_by_code(enrolled)
    supervisors_c = _sum_by_code(supervisors)
    classes_c = _sum_by_code(classes_total)
    unsupervised_c = _sum_by_code(classes_unsupervised)
    incidents_c = _sum_by_code(incidents)
    reports_c = _sum_by_code(reports)
    absences_c = _sum_by_code(absences)
    overdue_c = _sum_by_code(overdue)

    # Governance: mean of per-kindergarten means, only over kindergartens that have one.
    governance_c: Dict[str, List[float]] = {}
    for kg_id, value in governance.items():
        code = kg_to_code.get(kg_id)
        if code is not None:
            governance_c.setdefault(code, []).append(value)

    training_c: Dict[str, tuple[int, int]] = {}
    for kg_id, (done, total) in training.items():
        code = kg_to_code.get(kg_id)
        if code is None:
            continue
        acc_done, acc_total = training_c.get(code, (0, 0))
        training_c[code] = (acc_done + done, acc_total + total)

    date_str = snapshot_date.isoformat()
    rows: List[Dict[str, Any]] = []
    for gov in C.GOVERNORATES:
        code = gov["code"]

        scores = governance_c.get(code) or []
        # No governance score filed anywhere in the governorate is *unknown*, not 0.
        governance_score = round(sum(scores) / len(scores), 2) if scores else None

        done, total = training_c.get(code, (0, 0))
        # Likewise: no mandatory training assigned leaves completion undefined.
        training_pct = round(done * 100.0 / total, 2) if total else None

        row: Dict[str, Any] = {
            "date": date_str,
            "admin_id": code,
            "kindergartens_active": active.get(code, 0),
            "kindergartens_inactive": inactive.get(code, 0),
            "enrolled_children": enrolled_c.get(code, 0),
            "supervisors_count": supervisors_c.get(code, 0),
            "classes_count": classes_c.get(code, 0),
            "classes_without_supervisor": unsupervised_c.get(code, 0),
            "critical_incidents": incidents_c.get(code, 0),
            "daily_reports_count": reports_c.get(code, 0),
            "absences_total": absences_c.get(code, 0),
            "tasks_overdue": overdue_c.get(code, 0),
            "governance_score": governance_score,
            "training_completion_pct": training_pct,
        }
        # Explicitly unmeasurable -> empty cell, never 0.
        for column in UNAVAILABLE_COLUMNS:
            row[column] = None
        rows.append(row)

    return rows, sorted(unresolved)


# ---------------------------------------------------------------------------
# Atomic write
# ---------------------------------------------------------------------------

def _assert_approved_path(path: Path) -> Path:
    """Refuse to write anywhere except the heat map data directory.

    The generator is never handed a path from request input, but this keeps that
    guarantee locally checkable rather than relying on every future caller.
    """
    resolved = Path(path).resolve()
    approved = DATA_DIR.resolve()
    if resolved.parent != approved:
        raise ValueError(
            f"refusing to write heat map data to {resolved}: only {approved} is approved"
        )
    if resolved.suffix.lower() != ".csv":
        raise ValueError(f"refusing to write heat map data to a non-CSV path: {resolved}")
    return resolved


def _write_atomic(df: pd.DataFrame, destination: Path) -> None:
    """Write via a temp file in the same directory, then rename over the target.

    Same-directory keeps the rename on one filesystem, so `os.replace` is atomic:
    a reader either sees the whole previous file or the whole new one, never a
    half-written dataset.
    """
    destination.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp_name = tempfile.mkstemp(
        dir=str(destination.parent), prefix=".daily_indicators-", suffix=".csv.tmp"
    )
    tmp_path = Path(tmp_name)
    try:
        with os.fdopen(fd, "w", encoding="utf-8", newline="") as handle:
            df.to_csv(handle, index=False, columns=CSV_COLUMNS, lineterminator="\n")
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(tmp_path, destination)
    except Exception:
        tmp_path.unlink(missing_ok=True)
        raise


def content_version(path: Path) -> str:
    """Short SHA-256 of the file's bytes — the dataset's identity.

    Deliberately *not* mtime. Filesystem timestamp resolution varies by platform and
    container, and a scheduled rebuild colliding with a manual refresh inside the same
    second is entirely realistic; either would make two different datasets look
    identical. Hashing the content cannot collide that way.
    """
    digest = hashlib.sha256()
    with open(path, "rb") as handle:
        for chunk in iter(lambda: handle.read(65536), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _write_metadata(result: GenerationResult, destination: Path) -> None:
    """Write the manifest atomically, *after* the dataset it describes is installed.

    Ordering matters: a manifest version must never name a dataset that failed
    validation, because workers treat the manifest as the authoritative statement of
    what they should be serving.
    """
    full_hash = content_version(destination)
    payload = {
        "schema_version": MANIFEST_SCHEMA_VERSION,
        "version": full_hash[:16],
        "content_sha256": full_hash,
        "status": result.status,
        # UTC for machine ordering; snapshot_date stays the Jordan business date.
        "generated_at_utc": (
            datetime.fromisoformat(result.generated_at).astimezone(timezone.utc).isoformat()
            if result.generated_at else None
        ),
        "generated_at": result.generated_at,
        "snapshot_date": result.snapshot_date,
        "rows": result.rows_written,
        "governorates_covered": result.governorates_covered,
        "unresolved_governorates": result.unresolved_governorates,
        "source": "kinjo-database",
        "generator": "heatmap.backend.etl.generate.generate_daily_indicators",
        "unavailable_columns": sorted(UNAVAILABLE_COLUMNS),
        "dataset": destination.name,
    }
    tmp = DATASET_METADATA.with_suffix(".json.tmp")
    tmp.write_text(json.dumps(payload, indent=2, ensure_ascii=False), encoding="utf-8")
    os.replace(tmp, DATASET_METADATA)
    _publish_version(payload["version"])


def _publish_version(version: str) -> None:
    """Best-effort announcement of the active version to Redis.

    Purely an accelerator: it lets a worker skip a stat() when nothing has changed.
    Correctness never depends on it, because cache_service degrades to a *per-process*
    in-memory dict when Redis is down — which would silently reintroduce the very
    staleness this work removes. So a failure here is logged and ignored.
    """
    try:
        from cache_service import cache_service

        cache_service.set(DATASET_VERSION_CACHE_KEY, version, ttl_seconds=VERSION_KEY_TTL_SECONDS)
    except Exception as exc:  # noqa: BLE001 - never let cache trouble fail a generation
        logger.warning("Could not publish heat map dataset version to cache: %s", exc)


# ---------------------------------------------------------------------------
# Public entry point
# ---------------------------------------------------------------------------

def generate_daily_indicators(
    db: Session,
    snapshot_date: Optional[date] = None,
    destination: Optional[Path] = None,
) -> GenerationResult:
    """Build, validate and atomically install the production indicator dataset.

    `destination` exists for tests, which must never touch the real data directory
    unguarded; it is still checked against the approved directory. Nothing in the
    request path may reach this argument.
    """
    if not _GENERATION_LOCK.acquire(blocking=False):
        logger.info("Heat map dataset generation already running; skipping this trigger")
        return GenerationResult(status="skipped_locked")

    try:
        target = _assert_approved_path(destination or DAILY_DATASET)
        snapshot = snapshot_date or today_amman()
        started = now_amman()

        rows, unresolved = build_rows(db, snapshot)
        if unresolved:
            logger.warning(
                "Heat map generation could not resolve %d governorate value(s): %s",
                len(unresolved), ", ".join(unresolved[:10]),
            )

        frame = pd.DataFrame(rows, columns=CSV_COLUMNS)

        # Validate the WHOLE dataset before anything touches the live file.
        clean, errors = validate_dataframe(frame)
        if errors:
            logger.error(
                "Heat map generation produced %d invalid row(s); keeping previous dataset",
                len(errors),
            )
            return GenerationResult(
                status="failed",
                snapshot_date=snapshot.isoformat(),
                rows_rejected=len(errors),
                validation_errors=errors[:20],
                error="generated dataset failed validation",
                generated_at=started.isoformat(),
            )

        if clean.empty:
            # An empty database is a real state, but replacing a good dataset with
            # zero rows would blank the map. Report it and leave the file alone.
            logger.warning("Heat map generation produced no rows; keeping previous dataset")
            return GenerationResult(
                status="empty",
                snapshot_date=snapshot.isoformat(),
                rows_written=0,
                unresolved_governorates=unresolved,
                generated_at=started.isoformat(),
                error="no rows produced",
            )

        result = GenerationResult(
            status="success",
            snapshot_date=snapshot.isoformat(),
            rows_written=int(len(frame)),
            rows_rejected=0,
            governorates_covered=int(frame["admin_id"].nunique()),
            unresolved_governorates=unresolved,
            output_path=str(target),
            generated_at=started.isoformat(),
        )

        _write_atomic(frame, target)
        if target == DAILY_DATASET.resolve():
            _write_metadata(result, target)

        logger.info(
            "Heat map dataset generated: %d rows for %s -> %s",
            result.rows_written, result.snapshot_date, target,
        )
        return result

    except Exception as exc:  # noqa: BLE001 - reported to the caller, previous file kept
        logger.exception("Heat map dataset generation failed")
        return GenerationResult(status="failed", error=str(exc))
    finally:
        _GENERATION_LOCK.release()


# ---------------------------------------------------------------------------
# Freshness
# ---------------------------------------------------------------------------

STALE_AFTER_DAYS = 2


def dataset_status(destination: Optional[Path] = None) -> Dict[str, Any]:
    """Describe the installed dataset: present, how old, and whether it is stale."""
    target = Path(destination) if destination else DAILY_DATASET
    if not target.exists():
        return {
            "available": False,
            "stale": False,
            "version": None,
            "schema_version": MANIFEST_SCHEMA_VERSION,
            "snapshot_date": None,
            "generated_at": None,
            "generated_at_utc": None,
            "rows": 0,
            "age_days": None,
            "message": "No generated dataset is installed.",
        }

    meta: Dict[str, Any] = {}
    if DATASET_METADATA.exists():
        try:
            meta = json.loads(DATASET_METADATA.read_text(encoding="utf-8"))
        except (ValueError, OSError):
            logger.warning("Heat map dataset metadata is unreadable; reporting file only")

    snapshot_raw = meta.get("snapshot_date")
    age_days: Optional[int] = None
    if snapshot_raw:
        try:
            age_days = (today_amman() - date.fromisoformat(snapshot_raw)).days
        except ValueError:
            age_days = None

    stale = age_days is not None and age_days > STALE_AFTER_DAYS
    return {
        "available": True,
        "stale": stale,
        # The active version every worker should converge on. Content-derived, so two
        # regenerations in the same second still produce distinct identities.
        "version": meta.get("version"),
        "schema_version": meta.get("schema_version", MANIFEST_SCHEMA_VERSION),
        "generation_status": meta.get("status"),
        "source": meta.get("source"),
        "snapshot_date": snapshot_raw,
        "generated_at": meta.get("generated_at"),
        "generated_at_utc": meta.get("generated_at_utc"),
        "rows": meta.get("rows", 0),
        "age_days": age_days,
        "unavailable_columns": meta.get("unavailable_columns", sorted(UNAVAILABLE_COLUMNS)),
        "unresolved_governorates": meta.get("unresolved_governorates", []),
        "message": (
            f"Dataset is {age_days} day(s) old and considered stale "
            f"(threshold {STALE_AFTER_DAYS} days)."
            if stale
            else "Dataset is current."
        ),
    }
