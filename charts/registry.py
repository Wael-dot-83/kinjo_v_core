"""Canonical Analytics Contract for KinJo Charts."""

from typing import Dict, List, Optional
from pydantic import BaseModel


class MetricDefinition(BaseModel):
    key: str
    label_ar: str
    label_en: str
    business_meaning: str
    unit: str
    higher_is_better: bool
    expected_range: Optional[tuple[float, float]] = None
    supported_levels: List[str] = ["national", "governorate", "city", "kindergarten"]
    supported_chart_types: List[str]


METRIC_REGISTRY: Dict[str, MetricDefinition] = {
    "incidents": MetricDefinition(
        key="incidents",
        label_ar="الحوادث",
        label_en="Incidents",
        business_meaning="Total number of incidents reported.",
        unit="count",
        higher_is_better=False,
        supported_chart_types=["bar", "line", "pie", "heatmap"],
    ),
    "attendance": MetricDefinition(
        key="attendance",
        label_ar="نسبة الحضور",
        label_en="Attendance Rate",
        business_meaning="Percentage of expected attendance logs marked as attended.",
        unit="percent",
        higher_is_better=True,
        expected_range=(0.0, 100.0),
        supported_chart_types=["line", "bar", "heatmap"],
    ),
    "daily_reports": MetricDefinition(
        key="daily_reports",
        label_ar="التقارير اليومية",
        label_en="Daily Reports",
        business_meaning="Daily reports recorded.",
        unit="count",
        higher_is_better=True,
        supported_chart_types=["bar", "pie", "line"],
    ),
    "enrollments": MetricDefinition(
        key="enrollments",
        label_ar="التسجيلات",
        label_en="Enrollments",
        business_meaning="Counts of enrollments by status.",
        unit="count",
        higher_is_better=True,
        supported_chart_types=["bar", "pie", "line"],
    ),
    "kindergartens": MetricDefinition(
        key="kindergartens",
        label_ar="الحضانات",
        label_en="Kindergartens",
        business_meaning="Total kindergartens, their capacity and enrollments.",
        unit="count",
        higher_is_better=True,
        # No "city" rung: for this source the drill path is
        # national -> governorate -> kindergarten, and city is a filter rather than
        # a level. Commit 2fc57c6 ("Correct kindergartens drill levels and
        # next-level hints") removed it deliberately and added kindergarten_id to
        # the scoped datasets so the next hop is deterministic; cfe0965 reintroduced
        # it two days later and silently broke
        # test_render_kindergartens_governorate_scope_includes_kindergarten_id.
        # Restored — do not add "city" back without updating that test.
        supported_levels=["national", "governorate", "kindergarten"],
        supported_chart_types=["bar", "scatter"],
    ),
}
