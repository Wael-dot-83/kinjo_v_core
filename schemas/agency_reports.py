"""Pydantic schemas for the unified agency-report contract.

A single ``ReportResult`` model is the contract between the API layer and the
frontend.  Both sides validate against it so there is no drift between what the
backend returns and what the template/JS consumes.
"""
from __future__ import annotations

from datetime import datetime
from typing import Any, Literal, Optional

from pydantic import BaseModel, Field


class KPI(BaseModel):
    key: str
    label_ar: str
    label_en: str
    value: Optional[Any] = None
    format: Literal["number", "percent", "currency", "text"] = "number"
    unit_ar: str = ""
    unit_en: str = ""
    trend: Optional[Literal["up", "down", "flat"]] = None


class ChartSpec(BaseModel):
    chart_type: Literal["bar", "line", "donut", "stacked_bar", "pie"] = "bar"
    title_ar: str = ""
    title_en: str = ""
    x_axis: str = ""
    y_axis: str = ""
    segment_by: Optional[str] = None
    series: list[dict[str, Any]] = Field(default_factory=list)
    group_by: Optional[str] = None
    orientation: Optional[str] = None


class Dimension(BaseModel):
    key: str
    label_ar: str
    label_en: str
    data_type: Literal["string", "number", "percent", "date"] = "string"


class ReportResult(BaseModel):
    """Unified response contract for all agency reports."""

    agency_code: str
    report_code: str
    report_title_ar: str
    report_title_en: str
    generated_at: datetime
    filters_applied: dict[str, Any] = Field(default_factory=dict)
    summary_kpis: list[KPI] = Field(default_factory=list)
    dimensions: list[Dimension] = Field(default_factory=list)
    rows: list[dict[str, Any]] = Field(default_factory=list)
    chart_spec: Optional[ChartSpec] = None
    data_source: Literal["snapshot", "live"] = "live"
    total_row_count: int = 0
    privacy_notice_ar: str = ""
    privacy_notice_en: str = ""


class ReportFilters(BaseModel):
    """Validated filter set accepted by every report endpoint."""

    admission_year: Optional[int] = None
    period: Optional[str] = None
    year: Optional[str] = None
    quarter: Optional[str] = None
    date_from: Optional[str] = None
    date_to: Optional[str] = None
    governorate: Optional[str] = None
    city: Optional[str] = None
    district: Optional[str] = None
    area: Optional[str] = None
    kindergarten_id: Optional[int] = None
    gender: Optional[str] = None
    age_group: Optional[str] = None
    enrollment_status: Optional[str] = None
    aggregation_level: str = "governorate"
    geography_basis: Optional[str] = None
    status: Optional[str] = None
    severity: Optional[str] = None

    def to_dict(self) -> dict[str, Any]:
        """Return a clean dict with ``None``/empty values removed."""
        return {k: v for k, v in self.model_dump().items() if v not in (None, "", "null", "undefined")}


class ExportFormat(BaseModel):
    format: Literal["csv", "json", "xlsx"] = "csv"
