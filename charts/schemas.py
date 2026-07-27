"""Pydantic schemas for the KinJo charting subsystem."""

from __future__ import annotations

from enum import Enum
from typing import Any, Dict, List, Optional

from pydantic import BaseModel, Field, field_validator


class ChartType(str, Enum):
    LINE = "line"
    BAR = "bar"
    SCATTER = "scatter"
    PIE = "pie"
    HISTOGRAM = "histogram"
    BOX = "box"
    HEATMAP = "heatmap"
    FUNNEL = "funnel"
    TREEMAP = "treemap"


class ChartSource(str, Enum):
    INCIDENTS = "incidents"
    ATTENDANCE = "attendance"
    DAILY_REPORTS = "daily_reports"
    ENROLLMENTS = "enrollments"
    KINDERGARTENS = "kindergartens"


class Granularity(str, Enum):
    DAY = "day"
    WEEK = "week"
    MONTH = "month"


class ChartRequest(BaseModel):
    source: ChartSource
    chart_type: Optional[ChartType] = None
    date_from: Optional[str] = Field(default=None, description="ISO date YYYY-MM-DD")
    date_to: Optional[str] = Field(default=None, description="ISO date YYYY-MM-DD")
    kindergarten_id: Optional[int] = None
    governorate: Optional[str] = None
    city: Optional[str] = None
    granularity: Granularity = Granularity.MONTH
    group_by: Optional[str] = Field(default=None, description="Column to group by")
    top_n: Optional[int] = Field(default=None, ge=1, le=50)
    title: Optional[str] = None
    lang: str = "ar"

    @field_validator("date_from", "date_to", mode="before")
    @classmethod
    def validate_date(cls, v: Any) -> Optional[str]:
        if v is None:
            return None
        import re
        if not re.match(r"^\d{4}-\d{2}-\d{2}$", str(v)):
            raise ValueError("Date must be in YYYY-MM-DD format")
        return str(v)


class MetricMeta(BaseModel):
    key: str
    label: str
    unit: str
    higher_is_better: bool

class ScopeMeta(BaseModel):
    level: str
    parent_key: Optional[str] = None

class PeriodMeta(BaseModel):
    start: Optional[str] = None
    end: Optional[str] = None
    comparison_start: Optional[str] = None
    comparison_end: Optional[str] = None

class DrilldownMeta(BaseModel):
    enabled: bool
    next_level: Optional[str] = None

class QualityMeta(BaseModel):
    status: str
    record_count: int
    missing_count: int
    freshness_at: str

class ChartResponse(BaseModel):
    metric: MetricMeta
    scope: ScopeMeta
    period: PeriodMeta
    summary: Dict[str, Any]
    series: List[Dict[str, Any]]
    table: List[Dict[str, Any]]
    drilldown: DrilldownMeta
    quality: QualityMeta

    chart_type: ChartType
    source: ChartSource
    title: str
    cached: bool = False
    task_id: Optional[str] = None


class ChartSuggestion(BaseModel):
    chart_type: ChartType
    title: str
    rationale: str
    confidence: float = Field(ge=0.0, le=1.0)


class SuggestRequest(BaseModel):
    source: ChartSource
    date_from: Optional[str] = None
    date_to: Optional[str] = None
    kindergarten_id: Optional[int] = None
    governorate: Optional[str] = None
    city: Optional[str] = None
    max_suggestions: int = Field(default=3, ge=1, le=5)


class SuggestResponse(BaseModel):
    source: ChartSource
    suggestions: List[ChartSuggestion]
    row_count: int
    profile: Dict[str, Any] = Field(default_factory=dict)


class TaskStatus(BaseModel):
    task_id: str
    status: str
    result: Optional[ChartResponse] = None
    error: Optional[str] = None
    progress: int = Field(default=0, ge=0, le=100)


class DataProfile(BaseModel):
    """Internal schema — statistical profile of a raw dataset."""
    row_count: int
    has_time_series: bool = False
    has_categories: bool = False
    has_numeric: bool = False
    n_categories: int = 0
    n_numeric_cols: int = 0
    cardinality: Dict[str, int] = Field(default_factory=dict)
    time_span_days: Optional[int] = None
    skewness: Optional[float] = None
    has_negative: bool = False
