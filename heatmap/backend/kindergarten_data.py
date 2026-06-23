"""
Kindergarten data normalization with KPIStatus integration.

Provides normalized data access for kindergarten metrics, mapping raw values
to canonical KPIStatus values for consistent UI rendering.
"""
from __future__ import annotations
from typing import Any, Dict, Optional

from . import constants as C
from .kpi_status import KPIStatus, normalize_kpi_status, status_to_color, status_from_numeric


def normalize_sub_indicator_value(
    sub_key: str,
    value: Optional[float],
    higher_is_better: bool = True,
) -> Dict[str, Any]:
    """Normalize a sub-indicator value to KPIStatus with color and display info.

    Args:
        sub_key: Sub-indicator key (e.g., 'active_nurseries', 'incidents_total').
        value: Raw numeric value or None.
        higher_is_better: Whether higher values are healthier for this indicator.

    Returns:
        Dict with value, status, color, and threshold info.
    """
    for ind_key, subs in C.SUB_INDICATORS.items():
        sub = next((s for s in subs if s["key"] == sub_key), None)
        if sub:
            threshold_high = sub["threshold_high"]
            threshold_low = sub["threshold_low"]
            break
    else:
        threshold_high = 100.0
        threshold_low = 0.0

    if value is None:
        value = 0.0
        status = KPIStatus.UNKNOWN
    elif higher_is_better:
        score = max(0.0, min(100.0, (value / threshold_high) * 100.0))
        status = status_from_numeric(score)
    else:
        score = max(0.0, min(100.0, 100.0 - (value / threshold_high) * 100.0))
        status = status_from_numeric(score)

    return {
        "value": round(value, 2) if isinstance(value, float) else value,
        "status": status.value,
        "status_display_en": status.name.capitalize(),
        "status_display_ar": {
            "normal": "طبيعي",
            "warning": "تحذير",
            "risk": "خطر",
            "critical": "حرج",
            "unknown": "غير معروف",
        }.get(status.value, "غير معروف"),
        "color": status_to_color(status),
        "threshold_high": threshold_high,
        "threshold_low": threshold_low,
    }


def get_kindergarten_metrics(db, slug: str) -> Dict[str, Any]:
    """Return normalized kindergarten metrics for a governorate.

    Args:
        db: SQLAlchemy session.
        slug: Governorate slug.

    Returns:
        Dict with active/inactive counts, children, supervisors, classrooms,
        incidents, and their normalized status values.
    """
    from . import service as heatmap_service
    sub = heatmap_service._compute_sub_indicators(db, slug)

    return {
        "governorate": slug,
        "kindergartens": {
            "active": normalize_sub_indicator_value("active_nurseries", float(sub.get("active_nurseries", 0)), True),
            "inactive": normalize_sub_indicator_value("inactive_nurseries", float(sub.get("inactive_nurseries", 0)), False),
            "active_pct": normalize_sub_indicator_value("active_pct", float(sub.get("active_pct", 0)), True),
        },
        "children": {
            "registered": normalize_sub_indicator_value("registered_children", float(sub.get("registered_children", 0)), True),
            "unregistered": normalize_sub_indicator_value("unregistered_children", float(sub.get("unregistered_children", 0)), False),
            "registration_rate": normalize_sub_indicator_value("registration_rate", float(sub.get("registration_rate", 0)), True),
        },
        "staff": {
            "supervisors": normalize_sub_indicator_value("supervisors_count", float(sub.get("supervisors_count", 0)), True),
            "classrooms": normalize_sub_indicator_value("classrooms_count", float(sub.get("classrooms_count", 0)), True),
            "unsupervised_classrooms": normalize_sub_indicator_value("classrooms_no_supervisor", float(sub.get("classrooms_no_supervisor", 0)), False),
        },
        "incidents": {
            "total": normalize_sub_indicator_value("incidents_total", float(sub.get("incidents_total", 0)), False),
            "critical": normalize_sub_indicator_value("incidents_critical", float(sub.get("incidents_critical", 0)), False),
        },
    }


def normalize_governorate_data(data: Dict[str, Any]) -> Dict[str, Any]:
    """Ensure all status fields use canonical KPIStatus values.

    Args:
        data: Raw governorate data dict.

    Returns:
        Normalized data with string statuses converted to KPIStatus.value format.
    """
    normalized = dict(data)

    for ind_key in C.INDICATOR_KEYS:
        if ind_key in normalized.get("main_indicators", {}):
            raw_status = normalized["main_indicators"].get(f"{ind_key}_status")
            normalized_status = normalize_kpi_status(raw_status).value
            normalized["main_indicators"][f"{ind_key}_status"] = normalized_status

        if ind_key in normalized.get("risk_by_indicator", {}):
            raw = normalized["risk_by_indicator"][ind_key]
            if isinstance(raw, dict) and "key" in raw:
                normalized["risk_by_indicator"][ind_key] = dict(raw)
                normalized["risk_by_indicator"][ind_key]["key"] = normalize_kpi_status(raw["key"]).value

    if "risk_level" in normalized:
        raw = normalized["risk_level"]
        if isinstance(raw, dict) and "key" in raw:
            normalized["risk_level"] = dict(raw)
            normalized["risk_level"]["key"] = normalize_kpi_status(raw["key"]).value

    return normalized


__all__ = [
    "normalize_sub_indicator_value",
    "get_kindergarten_metrics",
    "normalize_governorate_data",
]