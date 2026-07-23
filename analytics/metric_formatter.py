"""Metric formatting & explicit data-state handling.

The historical anti-pattern (baseline audit D3) coalesces missing data to ``0``,
so a genuine 0% is indistinguishable from "no records" or "sample too small".
This module gives every consumer a single, honest vocabulary for that distinction
and localized rendering for each state.

States
------
valid              : real, reportable value.
missing            : no underlying records at all (denominator == 0 / None).
insufficient_data  : some records, but below the metric's ``minimum_denominator``.
suppressed         : withheld for privacy (small cell / restricted metric without perm).
not_applicable     : metric does not apply to this entity/period.

Nothing here computes a metric — values come from analytics_gap_service. This module
only *classifies* and *renders*.
"""
from __future__ import annotations

from typing import Any, Dict, Optional

try:  # registry is optional at import time (keeps unit tests isolated)
    from . import metric_registry
except Exception:  # pragma: no cover
    metric_registry = None  # type: ignore


# Canonical states
VALID = "valid"
MISSING = "missing"
INSUFFICIENT = "insufficient_data"
SUPPRESSED = "suppressed"
NOT_APPLICABLE = "not_applicable"

ALL_STATES = (VALID, MISSING, INSUFFICIENT, SUPPRESSED, NOT_APPLICABLE)

# Bilingual labels + the placeholder shown instead of a fabricated number.
_STATE_TEXT: Dict[str, Dict[str, str]] = {
    MISSING: {
        "en": "No data",
        "ar": "لا تتوفر بيانات",
        "placeholder": "—",
    },
    INSUFFICIENT: {
        "en": "Insufficient data",
        "ar": "بيانات غير كافية",
        "placeholder": "—",
    },
    SUPPRESSED: {
        "en": "Withheld for privacy",
        "ar": "محجوب لحماية الخصوصية",
        "placeholder": "•••",
    },
    NOT_APPLICABLE: {
        "en": "Not applicable",
        "ar": "لا ينطبق",
        "placeholder": "—",
    },
}

# Longer helper message for empty layers (replaces the old "no_data" sentinel metric).
_NO_DATA_MESSAGE = {
    "en": "No data available for the selected period or filters. "
          "Adjust the filters or choose a different date range.",
    "ar": "لا تتوفر بيانات للفترة أو المعايير المحددة. "
          "يرجى تعديل عوامل التصفية أو اختيار نطاق زمني مختلف.",
}


def _minimum_denominator(metric_key: Optional[str]) -> Optional[int]:
    if not metric_key or metric_registry is None:
        return None
    try:
        return metric_registry.get_metric(metric_key).get("minimum_denominator")
    except KeyError:
        return None


def classify_data_state(
    value: Any,
    *,
    metric_key: Optional[str] = None,
    denominator: Optional[int] = None,
    minimum_denominator: Optional[int] = None,
    suppressed: bool = False,
) -> str:
    """Classify a metric result into one of ALL_STATES.

    ``denominator`` is the sample size behind the value (e.g. expected attendance
    records). When it is known, this reliably separates missing / insufficient /
    valid; when it is unknown (None), we only fall back to ``value is None`` -> missing.
    """
    if suppressed:
        return SUPPRESSED
    if minimum_denominator is None:
        minimum_denominator = _minimum_denominator(metric_key)
    if denominator is not None:
        if denominator <= 0:
            return MISSING
        if minimum_denominator is not None and denominator < minimum_denominator:
            return INSUFFICIENT
        return VALID
    # No denominator available: only an explicit None value signals absence.
    if value is None:
        return MISSING
    return VALID


def state_label(state: str, lang: str = "en") -> str:
    if state == VALID:
        return ""  # valid has no badge text
    return _STATE_TEXT.get(state, {}).get(lang, state)


def placeholder(state: str) -> str:
    return _STATE_TEXT.get(state, {}).get("placeholder", "—")


def _format_number(value: Any, value_type: str) -> str:
    try:
        num = float(value)
    except (TypeError, ValueError):
        return str(value)
    if value_type == "percent":
        return f"{num:.1f}%"
    if value_type in ("count",):
        return f"{int(round(num))}"
    if value_type in ("index", "score", "rate", "velocity"):
        return f"{num:.1f}"
    return f"{num:g}"


def format_metric_value(
    value: Any,
    *,
    state: str = VALID,
    value_type: str = "number",
    lang: str = "en",
) -> str:
    """Return the string to display for a metric.

    For any non-valid state the placeholder is returned instead of the raw number,
    so callers can never accidentally render a fabricated ``0``.
    """
    if state != VALID:
        return placeholder(state)
    return _format_number(value, value_type)


def render_no_data_state(lang: str = "en", state: str = MISSING) -> Dict[str, Any]:
    """Structured payload a UI can render for an empty layer / cell."""
    return {
        "data_state": state,
        "label": state_label(state, lang),
        "message": _NO_DATA_MESSAGE["ar"] if lang == "ar" else _NO_DATA_MESSAGE["en"],
        "placeholder": placeholder(state),
    }


def annotate_metric(
    metric: "Any",
    *,
    denominator: Optional[int] = None,
    suppressed: bool = False,
    lang: Optional[str] = None,
) -> "Any":
    """Set ``data_state`` / ``coverage`` / ``display`` on a MetricResponse in place.

    Accepts the pydantic MetricResponse from schemas.chart_dto. Uses the registry to
    resolve value_type + minimum_denominator by ``metric.metric``. Returns the metric
    for chaining.
    """
    metric_key = getattr(metric, "metric", None)
    value = getattr(metric, "value", None)
    lang = lang or getattr(metric, "locale", "en")

    definition = {}
    if metric_registry is not None and metric_key:
        try:
            definition = metric_registry.get_metric(metric_key)
        except KeyError:
            definition = {}

    min_denom = definition.get("minimum_denominator")
    value_type = definition.get("value_type", "number")

    state = classify_data_state(
        value,
        metric_key=metric_key,
        denominator=denominator,
        minimum_denominator=min_denom,
        suppressed=suppressed,
    )
    metric.data_state = state
    if denominator is not None or min_denom is not None:
        metric.coverage = {
            "denominator": denominator,
            "minimum": min_denom,
        }
    metric.display = {
        "en": format_metric_value(value, state=state, value_type=value_type, lang="en"),
        "ar": format_metric_value(value, state=state, value_type=value_type, lang="ar"),
    }
    return metric
