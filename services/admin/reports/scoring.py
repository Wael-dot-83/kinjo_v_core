"""Authoritative scoring formulas for admin reports.

Single source of truth for the three numbers the admin module publishes:

* :func:`calculate_compliance_score`   -- ADMIN-SCORING-001
* :func:`calculate_data_quality_score` -- ADMIN-SCORING-002
* :func:`calculate_risk_score` / :func:`rank_kindergartens_by_risk` -- ADMIN-SCORING-003

Every formula carries a comment citing the business rule it implements, per
mandate 3 ("no gut-feel thresholds"). All user-facing text is returned in both
Arabic and English, per mandate 1.

These functions are deliberately pure: they take counts and return numbers. No
database session, no request context, no clock. That is what makes the bands
testable against a fixed population.
"""

from __future__ import annotations

from enum import Enum
from typing import Any, Iterable


# ---------------------------------------------------------------------------
# Shared status bands
# ---------------------------------------------------------------------------

# Business rule: a score is a percentage of an ideal, so the bands are fixed
# absolute cut-offs rather than relative ones. 95 is "clean", 85 is "minor
# findings", 70 is "material findings", below that is "failing".
_STATUS_BANDS: tuple[tuple[float, str], ...] = (
    (95.0, "green"),
    (85.0, "yellow"),
    (70.0, "orange"),
)

_STATUS_LABELS: dict[str, tuple[str, str]] = {
    "green": ("ممتاز", "Excellent"),
    "yellow": ("مقبول", "Acceptable"),
    "orange": ("يحتاج معالجة", "Needs attention"),
    "red": ("حرج", "Critical"),
}


def _score_to_status(score: float) -> str:
    """Map a 0-100 score onto the shared green/yellow/orange/red band."""
    for threshold, status in _STATUS_BANDS:
        if score >= threshold:
            return status
    return "red"


def status_labels(status: str) -> dict[str, str]:
    """Bilingual labels for a band name."""
    label_ar, label_en = _STATUS_LABELS.get(status, _STATUS_LABELS["red"])
    return {"label_ar": label_ar, "label_en": label_en}


# ---------------------------------------------------------------------------
# ADMIN-SCORING-001 — Compliance score
# ---------------------------------------------------------------------------


class ViolationSeverity(Enum):
    """Point deduction applied per occurrence of a violation.

    Business rule: violations are not interchangeable. A class of children left
    without a supervisor is a child-safety failure and is weighted five times a
    missing date of birth. The previous formula divided a raw violation count by
    ``children + kindergartens + classes``, which let a large network dilute a
    critical safety breach to near zero.
    """

    CRITICAL = 25  # Child safety risk
    HIGH = 15      # Regulatory breach
    MEDIUM = 10    # Policy violation
    LOW = 5        # Data quality issue


# violation key -> (severity, Arabic description, English description)
VIOLATION_RULES: dict[str, tuple[ViolationSeverity, str, str]] = {
    "class_with_children_no_supervisor": (
        ViolationSeverity.CRITICAL,
        "صف يضم أطفالاً بدون مشرف",
        "Class with children has no supervisor",
    ),
    "kindergarten_no_supervisor_with_children": (
        ViolationSeverity.CRITICAL,
        "حضانة تضم أطفالاً بدون أي مشرف",
        "Kindergarten with children has no supervisor",
    ),
    "kindergarten_over_capacity": (
        ViolationSeverity.HIGH,
        "حضانة تتجاوز السعة الاستيعابية",
        "Kindergarten exceeds capacity",
    ),
    "child_in_multiple_classes": (
        ViolationSeverity.HIGH,
        "طفل مسجل في أكثر من صف",
        "Child enrolled in multiple classes",
    ),
    "invalid_age_too_young": (
        ViolationSeverity.MEDIUM,
        "عمر الطفل أقل من الحد الأدنى",
        "Child age below minimum",
    ),
    "invalid_age_too_old": (
        ViolationSeverity.MEDIUM,
        "عمر الطفل أعلى من الحد الأقصى",
        "Child age above maximum",
    ),
    "future_dob": (
        ViolationSeverity.LOW,
        "تاريخ ميلاد في المستقبل",
        "Future date of birth",
    ),
    "missing_dob": (
        ViolationSeverity.LOW,
        "تاريخ ميلاد مفقود",
        "Missing date of birth",
    ),
}


def calculate_compliance_score(violations: dict[str, int]) -> dict[str, Any]:
    """Calculate the compliance score using weighted severity.

    Formula::

        score = max(0, 100 - sum(count * weight for each violation type))

    Business rule: each violation type carries a fixed severity weight
    (:class:`ViolationSeverity`). Critical violations -- children present with
    no supervisor -- deduct 25 points *each*, so four of them exhaust the
    score on their own. The score is a floor at 0; it never goes negative.

    Unknown violation keys are scored as LOW rather than dropped, so a new
    counter added upstream degrades the score instead of silently vanishing.

    Returns a dict with ``score``, ``status``, ``total_deduction``,
    ``violations`` (a list) and ``breakdown`` (keyed by violation type).
    """
    total_deduction = 0.0
    breakdown: dict[str, Any] = {}
    violation_list: list[dict[str, Any]] = []

    for vtype, count in violations.items():
        if not count or count <= 0:
            continue

        severity, ar_desc, en_desc = VIOLATION_RULES.get(
            vtype, (ViolationSeverity.LOW, vtype, vtype)
        )
        deduction = float(count * severity.value)
        total_deduction += deduction

        breakdown[vtype] = {
            "count": count,
            "severity": severity.name,
            "severity_weight": severity.value,
            "deduction": deduction,
            "description_ar": ar_desc,
            "description_en": en_desc,
        }
        violation_list.append({
            "type": vtype,
            "count": count,
            "severity": severity.name,
            "description_ar": ar_desc,
            "description_en": en_desc,
        })

    score = max(0.0, round(100.0 - total_deduction, 2))
    status = _score_to_status(score)

    # Worst first, so a caller that truncates the list keeps the critical rows.
    violation_list.sort(
        key=lambda v: (-VIOLATION_RULES.get(
            v["type"], (ViolationSeverity.LOW, "", "")
        )[0].value, v["type"])
    )

    return {
        "score": score,
        "status": status,
        **status_labels(status),
        "total_deduction": round(total_deduction, 2),
        "violations": violation_list,
        "breakdown": breakdown,
    }


# ---------------------------------------------------------------------------
# ADMIN-SCORING-002 — Data quality score
# ---------------------------------------------------------------------------

# Business rule: data quality is not report-filing rate. Filing on time is one
# of four dimensions and carries the smallest weight along with uniqueness,
# because a punctual report full of blank fields is not quality data.
DATA_QUALITY_WEIGHTS: dict[str, float] = {
    "completeness": 0.30,
    "timeliness": 0.20,
    "validity": 0.30,
    "uniqueness": 0.20,
}

_DIMENSION_LABELS: dict[str, tuple[str, str]] = {
    "completeness": ("الاكتمال", "Completeness"),
    "timeliness": ("التوقيت", "Timeliness"),
    "validity": ("الصحة", "Validity"),
    "uniqueness": ("عدم التكرار", "Uniqueness"),
}


def calculate_data_quality_score(
    total_children: int,
    missing_dob_count: int,
    missing_gender_count: int,
    invalid_age_count: int,
    duplicate_count: int,
    total_enrollments: int,
    active_kg_count: int,
    kg_with_recent_report: int,
    total_fields_required: int,
    total_fields_filled: int,
) -> dict[str, Any]:
    """Score data quality across four dimensions, each 0-100.

    Dimensions and weights:

    1. COMPLETENESS (30%) -- required fields that are actually filled
    2. TIMELINESS   (20%) -- kindergartens that filed a report recently
    3. VALIDITY     (30%) -- records passing business-rule validation
    4. UNIQUENESS   (20%) -- absence of duplicate children/enrollments

    Overall score is the weighted average. Each ratio is clamped to 0-100 so a
    denominator smaller than its numerator (possible when counts come from
    differently scoped queries) cannot push a dimension out of range.
    """
    completeness = _ratio_pct(total_fields_filled, total_fields_required)
    timeliness = _ratio_pct(kg_with_recent_report, active_kg_count)

    # Validity penalises records that fail a business rule: no usable date of
    # birth, or an age outside the licensed range for a nursery.
    invalid_records = missing_dob_count + invalid_age_count
    validity = _inverse_ratio_pct(invalid_records, total_children)

    # Uniqueness penalises duplicate child records against the enrollment base.
    uniqueness = _inverse_ratio_pct(duplicate_count, total_enrollments)

    scores = {
        "completeness": completeness,
        "timeliness": timeliness,
        "validity": validity,
        "uniqueness": uniqueness,
    }
    overall = round(
        sum(scores[dim] * weight for dim, weight in DATA_QUALITY_WEIGHTS.items()),
        2,
    )
    status = _score_to_status(overall)

    return {
        "overall_score": overall,
        "status": status,
        **status_labels(status),
        "dimensions": {
            dim: {
                "score": scores[dim],
                "weight": DATA_QUALITY_WEIGHTS[dim],
                "label_ar": _DIMENSION_LABELS[dim][0],
                "label_en": _DIMENSION_LABELS[dim][1],
            }
            for dim in DATA_QUALITY_WEIGHTS
        },
        "issues": {
            "missing_dob": missing_dob_count,
            "missing_gender": missing_gender_count,
            "invalid_age": invalid_age_count,
            "duplicate_children": duplicate_count,
            "kindergartens_without_recent_report": max(
                0, active_kg_count - kg_with_recent_report
            ),
        },
    }


def _ratio_pct(numerator: int, denominator: int) -> float:
    """``numerator / denominator`` as a percentage, clamped to 0-100."""
    pct = (numerator / max(1, denominator)) * 100.0
    return round(min(100.0, max(0.0, pct)), 2)


def _inverse_ratio_pct(bad: int, total: int) -> float:
    """``100 - bad/total`` as a percentage, clamped to 0-100."""
    pct = 100.0 - ((bad / max(1, total)) * 100.0)
    return round(min(100.0, max(0.0, pct)), 2)


# ---------------------------------------------------------------------------
# ADMIN-SCORING-003 — Risk ranking
# ---------------------------------------------------------------------------

_RISK_LABELS: dict[str, tuple[str, str]] = {
    "critical": ("حرج", "Critical"),
    "warning": ("تحذير", "Warning"),
    "elevated": ("مرتفع", "Elevated"),
    "normal": ("طبيعي", "Normal"),
}


def calculate_risk_score(
    capacity_utilization_pct: float,
    supervisor_gap: int,
    children_count: int,
    has_missing_capacity: bool,
    has_missing_coordinates: bool,
    classes_without_supervisor: int,
) -> float:
    """Composite pressure score for one kindergarten, 0-100.

    Formula::

        capacity_pressure = min(capacity_utilization_pct, 150)
        staffing_pressure = min(supervisor_gap * 20, 50)
        class_pressure    = min(classes_without_supervisor * 10, 30)

        pressure = capacity_pressure * 0.4
                 + staffing_pressure * 0.4
                 + class_pressure    * 0.2

        bonus = 10 if capacity is unknown, + 5 if coordinates are unknown
        raw   = min(100, pressure + bonus)

    Business rule: capacity and staffing pressure weigh equally (0.4 each)
    because an over-full nursery and an under-staffed one carry comparable
    child-safety exposure; unsupervised classes are already counted inside the
    staffing gap, so they contribute the residual 0.2. The "bonus" terms are
    not risk in themselves -- they mark a facility whose risk cannot be
    measured, which is itself a reason to inspect it.

    The raw score is only meaningful once :func:`rank_kindergartens_by_risk`
    converts it to a percentile against the whole population.
    """
    capacity_pressure = min(max(0.0, float(capacity_utilization_pct)), 150.0)
    staffing_pressure = min(max(0, supervisor_gap) * 20.0, 50.0)
    class_pressure = min(max(0, classes_without_supervisor) * 10.0, 30.0)

    pressure = (
        (capacity_pressure * 0.4)
        + (staffing_pressure * 0.4)
        + (class_pressure * 0.2)
    )

    bonus = 0.0
    if has_missing_capacity:
        bonus += 10.0
    if has_missing_coordinates:
        bonus += 5.0

    return round(min(100.0, pressure + bonus), 2)


def rank_kindergartens_by_risk(
    kindergarten_scores: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    """Assign risk bands by percentile rank within the population.

    Bands (business rule: risk is triaged by inspection capacity, so the bands
    are shares of the population rather than absolute score cut-offs -- the
    worst 10% are always the ones to visit first, whatever their raw score)::

        critical: > 90th percentile   (worst 10%)
        warning : > 75th percentile   (next 15%)
        elevated: > 50th percentile   (next 25%)
        normal  : <= 50th percentile  (bottom half)

    Each row must carry a ``raw_score``. Rows are returned sorted worst-first
    and mutated in place with ``percentile_rank``, ``population_size``,
    ``risk_status`` and bilingual labels.

    Note on ties: the shares above hold exactly when raw scores are distinct.
    Tied scores share a percentile, so a population with heavy ties can put
    more or fewer than 10% in ``critical``. That is intended -- splitting tied
    facilities arbitrarily would make the ranking unreproducible between runs.
    """
    if not kindergarten_scores:
        return []

    from scipy import stats

    scores = [kg["raw_score"] for kg in kindergarten_scores]
    population = len(scores)

    for kg in kindergarten_scores:
        percentile = stats.percentileofscore(scores, kg["raw_score"], kind="rank")
        kg["percentile_rank"] = round(float(percentile), 1)
        kg["population_size"] = population

        if percentile > 90:
            status = "critical"
        elif percentile > 75:
            status = "warning"
        elif percentile > 50:
            status = "elevated"
        else:
            status = "normal"

        kg["risk_status"] = status
        kg["risk_label_ar"] = _RISK_LABELS[status][0]
        kg["risk_label_en"] = _RISK_LABELS[status][1]

    # Highest risk first; ties broken by raw score then by a stable identity key
    # so repeated calls on the same data produce the same order.
    kindergarten_scores.sort(
        key=lambda x: (
            -x["percentile_rank"],
            -x["raw_score"],
            str(x.get("id", "")),
        )
    )
    return kindergarten_scores


def summarize_risk_bands(ranked: Iterable[dict[str, Any]]) -> dict[str, int]:
    """Count how many rows landed in each band. Used by dashboards and tests."""
    counts = {"critical": 0, "warning": 0, "elevated": 0, "normal": 0}
    for row in ranked:
        status = row.get("risk_status")
        if status in counts:
            counts[status] += 1
    return counts
