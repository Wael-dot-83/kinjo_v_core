"""
Data ingestion: reads CSV or JSON payload files, validates, and returns a clean DataFrame.
"""
from __future__ import annotations
import json
import logging
from pathlib import Path

import pandas as pd

from .validate import validate_dataframe, validate_records

logger = logging.getLogger(__name__)


def ingest_csv(path: str | Path) -> tuple[pd.DataFrame, list[dict]]:
    path = Path(path)
    logger.info("Ingesting CSV: %s", path)
    df_raw = pd.read_csv(path, dtype=str)
    # coerce numerics
    numeric_cols = [
        "kindergartens_active","kindergartens_inactive","enrolled_children","unregistered_children",
        "supervisors_count","classes_count","classes_without_supervisor","critical_incidents",
        "protection_issues","daily_reports_count","absences_total","absences_health_alerts",
        "tasks_overdue","governance_score","training_completion_pct",
    ]
    for col in numeric_cols:
        if col in df_raw.columns:
            df_raw[col] = pd.to_numeric(df_raw[col], errors="coerce")
    return validate_dataframe(df_raw)


def ingest_json(path: str | Path) -> tuple[list[dict], list[dict]]:
    path = Path(path)
    logger.info("Ingesting JSON: %s", path)
    with open(path, encoding="utf-8") as f:
        data = json.load(f)
    if isinstance(data, dict):
        data = [data]
    return validate_records(data)


def ingest_records(records: list[dict]) -> tuple[list[dict], list[dict]]:
    """Validate a list of dicts passed directly (e.g. from API endpoint)."""
    return validate_records(records)


def log_data_quality(errors: list[dict], source: str = "") -> None:
    if not errors:
        logger.info("Data quality OK for %s — no errors", source or "input")
        return
    logger.warning("Data quality issues in %s: %d row(s) rejected", source or "input", len(errors))
    for err in errors[:10]:
        logger.warning("  row %s admin=%s: %s", err.get("row_index", err.get("index")), err.get("admin_id"), err.get("error"))
    if len(errors) > 10:
        logger.warning("  ... and %d more errors", len(errors) - 10)
