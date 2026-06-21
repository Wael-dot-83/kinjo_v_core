"""
Canonical KPI status enum and normalization utilities.

This module provides a single source of truth for KPI status values across
the backend, API, and frontend layers.

Status levels (in order of severity):
- unknown:   No data available or unable to determine status
- critical:  Critical risk - immediate action required
- risk:      Elevated risk - attention needed
- warning:   Warning level - monitoring recommended
- normal:    Normal/healthy status - operating within parameters
"""
from __future__ import annotations
from enum import Enum
from typing import Optional


class KPIStatus(str, Enum):
    """Canonical KPI status enumeration."""
    NORMAL = "normal"
    WARNING = "warning"
    RISK = "risk"
    CRITICAL = "critical"
    UNKNOWN = "unknown"


STATUS_THRESHOLDS = {
    "critical": (0, 25),
    "risk": (26, 50),
    "warning": (51, 75),
    "normal": (76, 100),
}


STATUS_COLORS = {
    KPIStatus.NORMAL: "#28A745",
    KPIStatus.WARNING: "#FFC107",
    KPIStatus.RISK: "#FD7E14",
    KPIStatus.CRITICAL: "#DC3545",
    KPIStatus.UNKNOWN: "#94A3B8",
}


STATUS_DISPLAY_NAMES = {
    KPIStatus.NORMAL: {"en": "Normal", "ar": "طبيعي"},
    KPIStatus.WARNING: {"en": "Warning", "ar": "تحذير"},
    KPIStatus.RISK: {"en": "At Risk", "ar": "خطر"},
    KPIStatus.CRITICAL: {"en": "Critical", "ar": "حرج"},
    KPIStatus.UNKNOWN: {"en": "Unknown", "ar": "غير معروف"},
}


def status_to_color(status: KPIStatus | str | None) -> str:
    """Return the color associated with a KPI status.

    Args:
        status: KPIStatus enum, string name, or None.

    Returns:
        Hex color string. Returns gray (#94A3B8) for unknown/invalid inputs.
    """
    if status is None:
        return STATUS_COLORS[KPIStatus.UNKNOWN]

    if isinstance(status, KPIStatus):
        return STATUS_COLORS.get(status, STATUS_COLORS[KPIStatus.UNKNOWN])

    if isinstance(status, str):
        try:
            enum_status = KPIStatus(status.lower())
            return STATUS_COLORS.get(enum_status, STATUS_COLORS[KPIStatus.UNKNOWN])
        except ValueError:
            normalized = normalize_kpi_status(status)
            return STATUS_COLORS.get(normalized, STATUS_COLORS[KPIStatus.UNKNOWN])

    return STATUS_COLORS[KPIStatus.UNKNOWN]


def normalize_kpi_status(value: Optional[str | KPIStatus | int | float]) -> KPIStatus:
    """Convert various input formats to canonical KPIStatus enum.

    Accepts:
    - KPIStatus enum (returned as-is)
    - String values: "normal", "warning", "risk", "critical", "unknown",
      or numeric strings like "0-25", "26-50", "51-75", "76-100"
    - Numeric values: maps to status based on thresholds

    Args:
        value: Input value to normalize.

    Returns:
        KPIStatus enum value. Returns UNKNOWN for invalid/unrecognized inputs.
    """
    if value is None:
        return KPIStatus.UNKNOWN

    if isinstance(value, KPIStatus):
        return value

    if isinstance(value, str):
        value_lower = value.strip().lower()

        if not value_lower:
            return KPIStatus.UNKNOWN

        if value_lower in {s.value for s in KPIStatus}:
            return KPIStatus(value_lower)

        alias_map = {
            "ok": KPIStatus.NORMAL,
            "healthy": KPIStatus.NORMAL,
            "good": KPIStatus.NORMAL,
            "alert": KPIStatus.WARNING,
            "danger": KPIStatus.CRITICAL,
            "emergency": KPIStatus.CRITICAL,
            "low": KPIStatus.CRITICAL,
            "medium": KPIStatus.RISK,
            "high": KPIStatus.CRITICAL,
        }
        if value_lower in alias_map:
            return alias_map[value_lower]

    if isinstance(value, (int, float)):
        return status_from_numeric(float(value))

    return KPIStatus.UNKNOWN


def status_from_numeric(score: float) -> KPIStatus:
    """Map a numeric score (0-100) to KPIStatus based on thresholds.

    Higher scores map to better status (normal), lower scores to worse status (critical).

    Args:
        score: Numeric score in range 0-100.

    Returns:
        Corresponding KPIStatus enum value.
    """
    try:
        score_f = float(score)
    except (TypeError, ValueError):
        return KPIStatus.UNKNOWN

    score_f = max(0.0, min(100.0, score_f))

    if 76 <= score_f <= 100:
        return KPIStatus.NORMAL
    elif 51 <= score_f <= 75:
        return KPIStatus.WARNING
    elif 26 <= score_f <= 50:
        return KPIStatus.RISK
    elif 0 <= score_f <= 25:
        return KPIStatus.CRITICAL

    return KPIStatus.UNKNOWN


def get_status_display(status: KPIStatus | str, locale: str = "en") -> str:
    """Return localized display name for a KPI status.

    Args:
        status: KPIStatus enum or string name.
        locale: "en" for English, "ar" for Arabic.

    Returns:
        Localized display name string. Returns "Unknown" for invalid inputs.
    """
    normalized = normalize_kpi_status(status)

    if normalized not in STATUS_DISPLAY_NAMES:
        return "Unknown" if locale == "en" else "غير معروف"

    display = STATUS_DISPLAY_NAMES[normalized]
    return display.get(locale, display.get("en", "Unknown"))


def get_status_threshold_range(status: KPIStatus) -> tuple[float, float] | None:
    """Return the numeric score range for a given status.

    Args:
        status: KPIStatus enum value.

    Returns:
        Tuple of (min, max) scores, or None if status is UNKNOWN.
    """
    if status == KPIStatus.UNKNOWN:
        return None
    return STATUS_THRESHOLDS.get(status.value)


__all__ = [
    "KPIStatus",
    "STATUS_THRESHOLDS",
    "STATUS_COLORS",
    "STATUS_DISPLAY_NAMES",
    "status_to_color",
    "normalize_kpi_status",
    "status_from_numeric",
    "get_status_display",
    "get_status_threshold_range",
]