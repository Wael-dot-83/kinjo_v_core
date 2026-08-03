"""
Validation layer for daily kindergarten payload.
Enforces schema, ranges, and date format per spec.
"""
from __future__ import annotations
import re
from datetime import datetime
from typing import Any, Optional

import pandas as pd
from pydantic import BaseModel, Field, ValidationError, field_validator, model_validator

DATE_RE = re.compile(r"^\d{4}-\d{2}-\d{2}$")


def summarize_validation_error(exc: Exception) -> str:
    """Describe why a row failed without quoting any of its content.

    `str(exc)` on a pydantic ValidationError embeds `input_value=...`, i.e. the
    submitted row verbatim. When the source is a file the server read on the
    caller's behalf, echoing that back turns validation output into a file-read
    primitive, so only the field location and error type ever leave this module.
    """
    if isinstance(exc, ValidationError):
        parts = []
        for err in exc.errors():
            loc = ".".join(str(p) for p in err.get("loc", ())) or "<row>"
            parts.append(f"{loc}: {err.get('type', 'invalid')}")
        return "; ".join(parts) if parts else "validation failed"
    # Non-pydantic failures (e.g. a malformed row shape) may also carry data in
    # their message, so report the exception class alone.
    return type(exc).__name__


def _safe_admin_id(value: Any) -> str | None:
    """Echo the row's admin_id only when it is one of the known Jordan codes.

    Identifying which row failed is useful, but the field is only safe to reflect
    when its value came from the fixed vocabulary rather than from arbitrary
    file content.
    """
    return value if value in VALID_ADMIN_IDS else None

VALID_ADMIN_IDS = {
    "JO-AM", "JO-IR", "JO-ZA", "JO-BA", "JO-MD",
    "JO-JA", "JO-AJ", "JO-MA", "JO-KA", "JO-TA",
    "JO-MN", "JO-AQ",
    # qaḍāʼ level
    "JO-AM-01","JO-AM-02","JO-AM-03","JO-AM-04","JO-AM-05",
    "JO-IR-01","JO-IR-02","JO-IR-03",
    "JO-ZA-01","JO-ZA-02",
    "JO-KA-01","JO-KA-02",
    "JO-MA-01","JO-MA-02",
    "JO-MN-01","JO-AQ-01",
    "JO-BA-01","JO-MD-01","JO-TA-01","JO-AJ-01","JO-JA-01",
}


class DailyPayload(BaseModel):
    """One (date, admin_id) observation.

    Five measures are nullable, and the distinction matters: `None` means "not
    measurable", which this codebase deliberately never renders as `0` (see
    tests/test_heatmap_unavailable_data.py — "unavailable != 0 — no fabricated
    measurement is written"). Requiring them made an honest dataset impossible to
    express: a producer with no defensible source had to invent a zero or have the
    row rejected outright.

    Three have no source anywhere in the KinJo domain model:
      * unregistered_children  — no population denominator exists
      * absences_health_alerts — AttendanceStatus has no health/sickness value
      * protection_issues      — IncidentType has no child-protection category
    Two are derivable but genuinely undefined when nothing has been recorded:
      * governance_score       — no score filed for the period
      * training_completion_pct— no mandatory module assigned
    """

    date: str
    admin_id: str
    kindergartens_active: int = Field(ge=0)
    kindergartens_inactive: int = Field(ge=0)
    enrolled_children: int = Field(ge=0)
    unregistered_children: Optional[int] = Field(default=None, ge=0)
    supervisors_count: int = Field(ge=0)
    classes_count: int = Field(ge=0)
    classes_without_supervisor: int = Field(ge=0)
    critical_incidents: int = Field(ge=0)
    protection_issues: Optional[int] = Field(default=None, ge=0)
    daily_reports_count: int = Field(ge=0)
    absences_total: int = Field(ge=0)
    absences_health_alerts: Optional[int] = Field(default=None, ge=0)
    tasks_overdue: int = Field(ge=0)
    governance_score: Optional[float] = Field(default=None, ge=0.0, le=100.0)
    training_completion_pct: Optional[float] = Field(default=None, ge=0.0, le=100.0)

    @field_validator("date")
    @classmethod
    def validate_date(cls, v: str) -> str:
        if not DATE_RE.match(v):
            raise ValueError(f"date must be YYYY-MM-DD, got: {v!r}")
        try:
            datetime.strptime(v, "%Y-%m-%d")
        except ValueError as exc:
            raise ValueError(str(exc)) from exc
        return v

    @field_validator("admin_id")
    @classmethod
    def validate_admin_id(cls, v: str) -> str:
        if v not in VALID_ADMIN_IDS:
            raise ValueError(f"Unknown admin_id: {v!r}")
        return v

    @model_validator(mode="after")
    def cross_field_checks(self) -> "DailyPayload":
        if self.classes_without_supervisor > self.classes_count:
            raise ValueError("classes_without_supervisor cannot exceed classes_count")
        # Only comparable when the health-alert figure was actually measured; an
        # unavailable value has no ordering relationship with the total.
        if (
            self.absences_health_alerts is not None
            and self.absences_health_alerts > self.absences_total
        ):
            raise ValueError("absences_health_alerts cannot exceed absences_total")
        total_kg = self.kindergartens_active + self.kindergartens_inactive
        if total_kg > 0 and self.supervisors_count > total_kg * 10:
            raise ValueError("supervisors_count looks implausibly high relative to kindergartens")
        return self


def validate_dataframe(df: pd.DataFrame) -> tuple[pd.DataFrame, list[dict[str, Any]]]:
    """
    Validates every row; returns (clean_df, error_log).
    Rows that fail validation are excluded from clean_df.
    """
    errors: list[dict] = []
    valid_rows: list[dict] = []

    for idx, row in df.iterrows():
        data = row.to_dict()

        # An empty CSV cell arrives as NaN. NaN is pandas' "missing"; None is this
        # schema's "not measurable". Translating here is what lets a producer leave a
        # genuinely unmeasurable column blank instead of inventing a zero for it.
        for col, value in list(data.items()):
            if value is not None and not isinstance(value, str) and pd.isna(value):
                data[col] = None

        # cast integer-like floats that pandas may infer
        int_cols = [
            "kindergartens_active","kindergartens_inactive","enrolled_children",
            "unregistered_children","supervisors_count","classes_count",
            "classes_without_supervisor","critical_incidents","protection_issues",
            "daily_reports_count","absences_total","absences_health_alerts","tasks_overdue",
        ]
        for col in int_cols:
            if col in data and data[col] is not None:
                try:
                    data[col] = int(data[col])
                except (ValueError, TypeError):
                    pass

        try:
            payload = DailyPayload(**data)
            valid_rows.append(payload.model_dump())
        except Exception as exc:
            errors.append({
                "row_index": idx,
                "admin_id": _safe_admin_id(data.get("admin_id")),
                "error": summarize_validation_error(exc),
            })

    clean_df = pd.DataFrame(valid_rows) if valid_rows else pd.DataFrame()
    return clean_df, errors


def validate_records(records: list[dict]) -> tuple[list[dict], list[dict]]:
    """Validates a list of dicts; returns (valid_records, errors)."""
    valid, errors = [], []
    for i, rec in enumerate(records):
        try:
            payload = DailyPayload(**rec)
            valid.append(payload.model_dump())
        except Exception as exc:
            errors.append({
                "index": i,
                "admin_id": _safe_admin_id(rec.get("admin_id")),
                "error": summarize_validation_error(exc),
            })
    return valid, errors
