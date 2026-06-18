"""
Computes the six main composite indicators from raw sub-indicators.
Each indicator is normalised 0-100 (higher = better, except where noted).
"""
from __future__ import annotations
import numpy as np
import pandas as pd


# ---------------------------------------------------------------------------
# Sub-indicator → main indicator mapping (used by analytics layer too)
# ---------------------------------------------------------------------------
INDICATOR_MAP: dict[str, list[str]] = {
    "kindergarten_status":   ["kindergartens_active", "kindergartens_inactive"],
    "children_enrollment":   ["enrolled_children", "unregistered_children"],
    "staff_classrooms":      ["supervisors_count", "classes_count", "classes_without_supervisor"],
    "safety_incidents":      ["critical_incidents", "protection_issues"],
    "reports_attendance":    ["daily_reports_count", "absences_total", "absences_health_alerts"],
    "tasks_governance":      ["tasks_overdue", "governance_score", "training_completion_pct"],
}

ALL_SUB_INDICATORS: list[str] = [s for subs in INDICATOR_MAP.values() for s in subs]


def _safe_div(a: float, b: float, default: float = 0.0) -> float:
    return a / b if b != 0 else default


def compute_row(row: dict) -> dict:
    """Compute six composite indicators for a single data row."""
    kg_total = row["kindergartens_active"] + row["kindergartens_inactive"]
    kg_active_ratio = _safe_div(row["kindergartens_active"], kg_total, 1.0)

    total_children = row["enrolled_children"] + row["unregistered_children"]
    enrollment_ratio = _safe_div(row["enrolled_children"], total_children, 1.0)

    supervised_ratio = 1.0 - _safe_div(row["classes_without_supervisor"], max(row["classes_count"], 1))

    incident_penalty = min((row["critical_incidents"] * 10 + row["protection_issues"] * 5), 100)
    safety_score = max(0.0, 100.0 - incident_penalty)

    absence_rate = _safe_div(row["absences_total"], max(row["enrolled_children"], 1))
    health_alert_rate = _safe_div(row["absences_health_alerts"], max(row["absences_total"], 1))
    report_completeness = min(row["daily_reports_count"] / max(row["kindergartens_active"], 1), 1.0)
    reports_attendance_score = (
        report_completeness * 0.5
        + (1.0 - absence_rate) * 0.3
        + (1.0 - health_alert_rate) * 0.2
    ) * 100.0

    task_penalty = min(row["tasks_overdue"] * 5, 50)
    tasks_governance_score = (
        (row["governance_score"] * 0.5)
        + (row["training_completion_pct"] * 0.3)
        + max(0.0, 50.0 - task_penalty) * 0.4
    )

    return {
        "date":                  row["date"],
        "admin_id":              row["admin_id"],
        "kindergarten_status":   round(kg_active_ratio * 100, 2),
        "children_enrollment":   round(enrollment_ratio * 100, 2),
        "staff_classrooms":      round(supervised_ratio * 100, 2),
        "safety_incidents":      round(safety_score, 2),
        "reports_attendance":    round(reports_attendance_score, 2),
        "tasks_governance":      round(tasks_governance_score, 2),
        # pass-through raw columns for correlation analysis
        **{k: row[k] for k in ALL_SUB_INDICATORS},
    }


def compute_dataframe(df: pd.DataFrame) -> pd.DataFrame:
    """Apply compute_row to all rows; returns combined indicators + raws."""
    records = [compute_row(r) for r in df.to_dict("records")]
    return pd.DataFrame(records)


def impute_missing(df: pd.DataFrame) -> pd.DataFrame:
    """Forward-fill then median-fill numeric columns."""
    num_cols = df.select_dtypes(include=[np.number]).columns
    df[num_cols] = df.sort_values(["admin_id", "date"]).groupby("admin_id")[num_cols].transform(
        lambda g: g.ffill().bfill()
    )
    # global median for any remaining NaN
    df[num_cols] = df[num_cols].fillna(df[num_cols].median())
    return df


INDICATOR_THRESHOLDS: dict[str, float] = {
    "kindergarten_status":  70.0,
    "children_enrollment":  75.0,
    "staff_classrooms":     80.0,
    "safety_incidents":     85.0,
    "reports_attendance":   70.0,
    "tasks_governance":     65.0,
}

SUB_INDICATOR_THRESHOLDS: dict[str, float] = {
    "critical_incidents":         2.0,
    "protection_issues":          1.0,
    "classes_without_supervisor": 5.0,
    "absences_health_alerts":     10.0,
    "tasks_overdue":              5.0,
    "unregistered_children":      50.0,
}
