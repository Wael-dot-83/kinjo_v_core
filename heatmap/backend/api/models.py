"""Pydantic models for the heatmap API."""
from __future__ import annotations
from typing import Any, Optional
from pydantic import BaseModel, Field


class DailyPayloadIn(BaseModel):
    date: str
    admin_id: str
    kindergartens_active: int = Field(ge=0)
    kindergartens_inactive: int = Field(ge=0)
    enrolled_children: int = Field(ge=0)
    unregistered_children: int = Field(ge=0)
    supervisors_count: int = Field(ge=0)
    classes_count: int = Field(ge=0)
    classes_without_supervisor: int = Field(ge=0)
    critical_incidents: int = Field(ge=0)
    protection_issues: int = Field(ge=0)
    daily_reports_count: int = Field(ge=0)
    absences_total: int = Field(ge=0)
    absences_health_alerts: int = Field(ge=0)
    tasks_overdue: int = Field(ge=0)
    governance_score: float = Field(ge=0.0, le=100.0)
    training_completion_pct: float = Field(ge=0.0, le=100.0)


class IndicatorResponse(BaseModel):
    date: str
    admin_id: str
    kindergarten_status: float
    children_enrollment: Optional[float]
    staff_classrooms: float
    safety_incidents: float
    reports_attendance: float
    tasks_governance: Optional[float]


class CorrelationRow(BaseModel):
    main_indicator: str
    sub_indicator: str
    pearson_r: Optional[float] = None
    p_value: Optional[float] = None
    strong_correlation: bool = False
    beta_std: Optional[float] = None
    se: Optional[float] = None
    t_stat: Optional[float] = None
    ols_p_value: Optional[float] = None
    high_impact: bool = False


class AlertOut(BaseModel):
    id: str
    severity: str
    admin_id: str
    rule: str
    message: str
    meta: dict[str, Any] = {}
    created_at: str
    acknowledged: bool = False


class PipelineResult(BaseModel):
    date: str
    rows_processed: int
    errors: list[dict[str, Any]] = []
    alerts: list[dict[str, Any]] = []
    hotspots: list[dict[str, Any]] = []


class GovernorateProperties(BaseModel):
    """Properties attached to each governorate boundary in the boundary GeoJSON."""
    id: str
    name: str
    name_ar: str
    level: str
    admin_code: str
    kindergarten_status: Optional[float] = None
    children_enrollment: Optional[float] = None
    staff_classrooms: Optional[float] = None
    safety_incidents: Optional[float] = None
    reports_attendance: Optional[float] = None
    tasks_governance: Optional[float] = None
