"""Tests for explicit data-state handling (analytics/metric_formatter.py).

Guards the baseline-audit D3 fix: missing / insufficient / suppressed data must be
distinguishable from a genuine 0 and never rendered as a fabricated number.
"""
import pytest

from analytics import metric_formatter as fmt
from schemas.chart_dto import MetricResponse, ChartConfig, ChartDataset


def _metric(key, value):
    return MetricResponse(
        metric=key,
        value=value,
        chart=ChartConfig(type="gauge", labels=["x"],
                          datasets=[ChartDataset(label={"en": "x", "ar": "x"}, data=[value])]),
        locale="en",
    )


def test_missing_when_denominator_zero():
    assert fmt.classify_data_state(0.0, denominator=0) == fmt.MISSING


def test_insufficient_below_minimum_denominator():
    # network_attendance_rate has minimum_denominator=30 in the registry
    assert fmt.classify_data_state(
        90.0, metric_key="network_attendance_rate", denominator=10
    ) == fmt.INSUFFICIENT


def test_valid_when_denominator_meets_minimum():
    assert fmt.classify_data_state(
        90.0, metric_key="network_attendance_rate", denominator=100
    ) == fmt.VALID


def test_genuine_zero_is_valid_not_missing():
    # A real 0 with no denominator info must NOT be coerced to missing.
    assert fmt.classify_data_state(0.0) == fmt.VALID


def test_none_value_is_missing():
    assert fmt.classify_data_state(None) == fmt.MISSING


def test_suppressed_wins():
    assert fmt.classify_data_state(50.0, denominator=100, suppressed=True) == fmt.SUPPRESSED


def test_non_valid_states_render_placeholder_not_number():
    for state in (fmt.MISSING, fmt.INSUFFICIENT, fmt.SUPPRESSED, fmt.NOT_APPLICABLE):
        out = fmt.format_metric_value(0.0, state=state, value_type="percent")
        assert out == fmt.placeholder(state)
        assert "%" not in out  # never a fabricated 0%


def test_valid_percent_formatting():
    assert fmt.format_metric_value(95.0, state=fmt.VALID, value_type="percent") == "95.0%"


def test_state_labels_are_bilingual():
    assert fmt.state_label(fmt.INSUFFICIENT, "en") == "Insufficient data"
    assert fmt.state_label(fmt.INSUFFICIENT, "ar") == "بيانات غير كافية"
    assert fmt.state_label(fmt.VALID, "en") == ""  # valid has no badge


def test_annotate_metric_sets_state_coverage_and_display():
    m = _metric("network_attendance_rate", 88.0)
    fmt.annotate_metric(m, denominator=5)  # below minimum 30
    assert m.data_state == fmt.INSUFFICIENT
    assert m.coverage == {"denominator": 5, "minimum": 30}
    assert m.display["en"] == "—" and m.display["ar"] == "—"


def test_annotate_metric_suppressed():
    m = _metric("child_attendance_pattern", 100.0)
    fmt.annotate_metric(m, suppressed=True)
    assert m.data_state == fmt.SUPPRESSED
    assert m.display["en"] == fmt.placeholder(fmt.SUPPRESSED)


def test_render_no_data_state_payload():
    payload = fmt.render_no_data_state("ar")
    assert payload["data_state"] == fmt.MISSING
    assert payload["placeholder"] == "—"
    assert payload["message"]  # non-empty localized message
