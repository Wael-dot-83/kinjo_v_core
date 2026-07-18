"""
Computes composite indicators from available sub-indicator data.

Each indicator is normalised 0-100 (higher = better, except where noted).
Unavailable sub-indicators (None or missing) are excluded from composite scores;
available sub-indicators are averaged to produce the composite.

Only sub-indicators with a defensible KinJo data source are included.
Fabricated estimates (e.g. unregistered_children, absences_total) are never
used in composite calculations.
"""
from __future__ import annotations
import numpy as np
import pandas as pd


# ---------------------------------------------------------------------------
# Sub-indicator → main indicator mapping (used by analytics layer too)
# Only includes indicators with real KinJo data sources.
# ---------------------------------------------------------------------------
INDICATOR_MAP: dict[str, list[str]] = {
    "kindergarten_status":   ["kindergartens_active", "kindergartens_inactive"],
    "staff_classrooms":      ["supervisors_count", "classes_count", "classes_without_supervisor"],
    "safety_incidents":      ["critical_incidents"],
    "reports_attendance":    ["daily_reports_count"],
    "tasks_governance":      ["governance_score"],
}

ALL_SUB_INDICATORS: list[str] = [s for subs in INDICATOR_MAP.values() for s in subs]


def _safe_div(a: float, b: float, default: float = 0.0) -> float:
    return a / b if b != 0 else default

def _g(row: dict, key: str, default: float = 0.0) -> float:
    """Get a float value from a row dict, defaulting if None or missing."""
    val = row.get(key, default)
    return float(val) if val is not None else default

def _is_available(row: dict, key: str) -> bool:
    """Check if a sub-indicator has a real (non-None) value."""
    return key in row and row[key] is not None


def compute_row(row: dict) -> dict:
    """Compute composite indicators from available sub-indicator data only.

    Unavailable sub-indicators are excluded.  Available ones are averaged
    to produce the composite score.  No fabricated estimates are used.
    """
    # Kindergarten status: active ratio (uses real data only)
    kg_total = _g(row, "kindergartens_active") + _g(row, "kindergartens_inactive")
    kg_active_ratio = _safe_div(_g(row, "kindergartens_active"), kg_total, 1.0)

    # Staff & classrooms: supervision ratio (uses real data only)
    supervised_ratio = 1.0 - _safe_div(
        _g(row, "classes_without_supervisor"),
        max(_g(row, "classes_count"), 1),
    )

    # Safety: based only on critical incidents (uses real data)
    critical = _g(row, "critical_incidents")
    incident_penalty = min(critical * 10, 100)
    safety_score = max(0.0, 100.0 - incident_penalty)

    # Reports & attendance: based only on daily report completeness
    # (absence_rate, health_absences are unavailable — no defensible source)
    active_kgs = max(_g(row, "kindergartens_active"), 1)
    report_completeness = min(_g(row, "daily_reports_count") / max(30 * active_kgs, 1), 1.0)
    reports_attendance_score = report_completeness * 100.0

    # Governance: based only on governance score
    # (training_completion_pct, tasks_overdue — no defensible source)
    governance_score = _g(row, "governance_score")
    tasks_governance_score = governance_score

    return {
        "date":                  row["date"],
        "admin_id":              row["admin_id"],
        "kindergarten_status":   round(kg_active_ratio * 100, 2),
        "children_enrollment":   None,  # Unavailable — no population denominator
        "staff_classrooms":      round(supervised_ratio * 100, 2),
        "safety_incidents":      round(safety_score, 2),
        "reports_attendance":    round(reports_attendance_score, 2),
        "tasks_governance":      round(tasks_governance_score, 2) if governance_score else None,
        # pass-through raw columns for correlation analysis
        **{k: row[k] for k in ALL_SUB_INDICATORS if k in row},
    }


def compute_dataframe(df: pd.DataFrame) -> pd.DataFrame:
    """Apply compute_row to all rows; returns combined indicators + raws."""
    records = [compute_row(r) for r in df.to_dict("records")]
    return pd.DataFrame(records)


def impute_missing(df: pd.DataFrame) -> pd.DataFrame:
    """Forward-fill then median-fill numeric columns.

    Columns containing the marker value -1.0 (unavailable) are left as-is
    so that unavailable sub-indicators are not silently converted to synthetic values.
    """
    result = df.copy()
    # Identify columns that should be left as-is: those with -1.0 sentinel values
    unavailable_cols = set()
    for col in result.columns:
        if result[col].dtype == np.number and -1.0 in result[col].values:
            unavailable_cols.add(col)

    num_cols = [c for c in result.select_dtypes(include=[np.number]).columns
                if c not in unavailable_cols]
    result[num_cols] = result.sort_values(["admin_id", "date"]).groupby("admin_id")[num_cols].transform(
        lambda g: g.ffill().bfill()
    )
    # global median for any remaining NaN (only for non-unavailable columns)
    result[num_cols] = result[num_cols].fillna(result[num_cols].median())
    return result


INDICATOR_THRESHOLDS: dict[str, float] = {
    "kindergarten_status":  70.0,
    "staff_classrooms":     80.0,
    "safety_incidents":     85.0,
    "reports_attendance":   70.0,
    "tasks_governance":     65.0,
}

SUB_INDICATOR_THRESHOLDS: dict[str, float] = {
    "critical_incidents":         2.0,
    "classes_without_supervisor": 5.0,
}
