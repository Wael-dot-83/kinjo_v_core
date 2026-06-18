"""
Unit tests for KPI formula correctness in heatmap/backend/service.py.

Tests _compute_sub_indicators and _compute_main_indicators independently of
the database by injecting pre-built sub-indicator dicts. Each test names the
specific formula or invariant it is verifying so failures are self-explanatory.
"""
import os
import sys
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import math
import pytest

from heatmap.backend.service import _compute_main_indicators


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_sub(
    active_nurseries=100,
    inactive_nurseries=5,
    registered_children=500,
    unregistered_children=25,
    supervisors_count=50,
    classrooms_count=60,
    classrooms_no_supervisor=5,
    child_supervisor_ratio=10.0,
    child_teacher_ratio=8.0,
    incidents_total=2,
    incidents_critical=0,
    protection_cases=0,
    incident_severity=10,
    reports_submitted=2700,
    reports_missing=300,
    absence_rate=8.0,
    health_absences=40,
    repeated_health=12,
    delayed_tasks=10,
    governance_score=70.0,
    training_completion=75.0,
    compliance_status=65.0,
    active_pct=95.2,
    inactive_pct=4.8,
    registration_rate=84.0,
    age_distribution=500,
):
    return dict(
        active_nurseries=active_nurseries,
        inactive_nurseries=inactive_nurseries,
        registered_children=registered_children,
        unregistered_children=unregistered_children,
        supervisors_count=supervisors_count,
        classrooms_count=classrooms_count,
        classrooms_no_supervisor=classrooms_no_supervisor,
        child_supervisor_ratio=child_supervisor_ratio,
        child_teacher_ratio=child_teacher_ratio,
        incidents_total=incidents_total,
        incidents_critical=incidents_critical,
        protection_cases=protection_cases,
        incident_severity=incident_severity,
        reports_submitted=reports_submitted,
        reports_missing=reports_missing,
        absence_rate=absence_rate,
        health_absences=health_absences,
        repeated_health=repeated_health,
        delayed_tasks=delayed_tasks,
        governance_score=governance_score,
        training_completion=training_completion,
        compliance_status=compliance_status,
        active_pct=active_pct,
        inactive_pct=inactive_pct,
        registration_rate=registration_rate,
        age_distribution=age_distribution,
    )


# ---------------------------------------------------------------------------
# _compute_main_indicators — output shape
# ---------------------------------------------------------------------------

class TestComputeMainIndicatorsShape:

    def test_returns_six_keys(self):
        result = _compute_main_indicators(_make_sub())
        expected = {
            "nursery_status", "children_registration", "staff_classrooms",
            "safety_incidents", "reports_attendance", "tasks_governance",
        }
        assert set(result.keys()) == expected

    def test_all_values_are_floats(self):
        result = _compute_main_indicators(_make_sub())
        for k, v in result.items():
            assert isinstance(v, float), f"{k} should be float, got {type(v)}"

    def test_all_values_in_0_100_range(self):
        result = _compute_main_indicators(_make_sub())
        for k, v in result.items():
            assert 0.0 <= v <= 100.0, f"{k}={v} is out of [0, 100]"


# ---------------------------------------------------------------------------
# nursery_status — kg_active_ratio
# ---------------------------------------------------------------------------

class TestNurseryStatus:

    def test_all_active(self):
        sub = _make_sub(active_nurseries=100, inactive_nurseries=0)
        result = _compute_main_indicators(sub)
        assert result["nursery_status"] == 100.0

    def test_half_active(self):
        sub = _make_sub(active_nurseries=50, inactive_nurseries=50)
        result = _compute_main_indicators(sub)
        assert result["nursery_status"] == 50.0

    def test_zero_total_kg_no_crash(self):
        """Empty DB: no kindergartens. Should return 0 not ZeroDivisionError."""
        sub = _make_sub(active_nurseries=0, inactive_nurseries=0)
        result = _compute_main_indicators(sub)
        assert result["nursery_status"] == 0.0

    def test_typical_95_percent(self):
        sub = _make_sub(active_nurseries=95, inactive_nurseries=5)
        result = _compute_main_indicators(sub)
        assert abs(result["nursery_status"] - 95.0) < 0.1


# ---------------------------------------------------------------------------
# children_registration — enrollment_ratio
# ---------------------------------------------------------------------------

class TestChildrenRegistration:

    def test_fully_registered(self):
        sub = _make_sub(registered_children=500, unregistered_children=0)
        result = _compute_main_indicators(sub)
        assert result["children_registration"] == 100.0

    def test_zero_children_no_crash(self):
        sub = _make_sub(registered_children=0, unregistered_children=0)
        result = _compute_main_indicators(sub)
        assert result["children_registration"] == 0.0

    def test_half_registered(self):
        sub = _make_sub(registered_children=250, unregistered_children=250)
        result = _compute_main_indicators(sub)
        assert abs(result["children_registration"] - 50.0) < 0.1


# ---------------------------------------------------------------------------
# staff_classrooms — supervised_ratio
# ---------------------------------------------------------------------------

class TestStaffClassrooms:

    def test_fully_supervised(self):
        sub = _make_sub(classrooms_count=60, classrooms_no_supervisor=0)
        result = _compute_main_indicators(sub)
        assert result["staff_classrooms"] == 100.0

    def test_zero_classrooms_no_crash(self):
        sub = _make_sub(classrooms_count=0, classrooms_no_supervisor=0)
        result = _compute_main_indicators(sub)
        assert result["staff_classrooms"] == 100.0

    def test_half_unsupervised(self):
        sub = _make_sub(classrooms_count=60, classrooms_no_supervisor=30)
        result = _compute_main_indicators(sub)
        assert abs(result["staff_classrooms"] - 50.0) < 0.1

    def test_all_unsupervised_clamps_to_zero(self):
        sub = _make_sub(classrooms_count=60, classrooms_no_supervisor=60)
        result = _compute_main_indicators(sub)
        assert result["staff_classrooms"] == 0.0

    def test_over_unsupervised_clamps_to_zero(self):
        """Edge case: more unsupervised than total shouldn't go negative."""
        sub = _make_sub(classrooms_count=10, classrooms_no_supervisor=20)
        result = _compute_main_indicators(sub)
        assert result["staff_classrooms"] == 0.0


# ---------------------------------------------------------------------------
# safety_incidents — penalty-based score
# ---------------------------------------------------------------------------

class TestSafetyIncidents:

    def test_no_incidents_is_100(self):
        sub = _make_sub(incidents_critical=0, protection_cases=0)
        result = _compute_main_indicators(sub)
        assert result["safety_incidents"] == 100.0

    def test_ten_critical_incidents(self):
        """10 critical * 10 pts = 100 penalty → score = 0."""
        sub = _make_sub(incidents_critical=10, protection_cases=0)
        result = _compute_main_indicators(sub)
        assert result["safety_incidents"] == 0.0

    def test_penalty_clamps_at_100(self):
        """Excessive incidents should clamp at 0, not go negative."""
        sub = _make_sub(incidents_critical=50, protection_cases=100)
        result = _compute_main_indicators(sub)
        assert result["safety_incidents"] == 0.0

    def test_single_critical_incident(self):
        sub = _make_sub(incidents_critical=1, protection_cases=0)
        result = _compute_main_indicators(sub)
        assert abs(result["safety_incidents"] - 90.0) < 0.1


# ---------------------------------------------------------------------------
# reports_attendance — composite score + health_alert_rate fix
# ---------------------------------------------------------------------------

class TestReportsAttendance:

    def test_perfect_conditions(self):
        """All reports submitted, zero absences, zero health absences → ~100."""
        sub = _make_sub(
            active_nurseries=100,
            reports_submitted=3000,
            absence_rate=0.0,
            health_absences=0,
            registered_children=500,
        )
        result = _compute_main_indicators(sub)
        assert result["reports_attendance"] >= 99.0

    def test_zero_reports_zero_children_no_crash(self):
        sub = _make_sub(
            active_nurseries=0,
            reports_submitted=0,
            absence_rate=0.0,
            health_absences=0,
            registered_children=0,
        )
        result = _compute_main_indicators(sub)
        assert 0.0 <= result["reports_attendance"] <= 100.0

    def test_health_alert_rate_uses_registered_children(self):
        """
        The health_alert_rate denominator must be registered_children, not
        health_absences+1.  With 10 health absences and 1000 children:
          correct rate = 10/1000 = 1%
          old buggy rate = 10/11 = 91%

        With the bug, the health component would be ~0 regardless of child count.
        With the fix, high child count keeps the rate small and the component
        contributes meaningfully to the score.
        """
        sub_few_children = _make_sub(
            active_nurseries=10,
            reports_submitted=300,
            absence_rate=5.0,
            health_absences=10,
            registered_children=11,   # only 11 children → rate = 10/11 = 91%
        )
        sub_many_children = _make_sub(
            active_nurseries=10,
            reports_submitted=300,
            absence_rate=5.0,
            health_absences=10,
            registered_children=1000,  # 1000 children → rate = 10/1000 = 1%
        )
        score_few = _compute_main_indicators(sub_few_children)["reports_attendance"]
        score_many = _compute_main_indicators(sub_many_children)["reports_attendance"]
        # More children relative to health absences → lower rate → higher score
        assert score_many > score_few, (
            f"Expected score_many ({score_many:.2f}) > score_few ({score_few:.2f}). "
            "health_alert_rate denominator may be health_absences+1 instead of registered_children."
        )

    def test_high_absence_rate_reduces_score(self):
        sub_low = _make_sub(absence_rate=2.0, health_absences=10, registered_children=500)
        sub_high = _make_sub(absence_rate=40.0, health_absences=10, registered_children=500)
        score_low = _compute_main_indicators(sub_low)["reports_attendance"]
        score_high = _compute_main_indicators(sub_high)["reports_attendance"]
        assert score_low > score_high

    def test_missing_reports_reduces_score(self):
        sub_complete = _make_sub(active_nurseries=10, reports_submitted=300)
        sub_missing = _make_sub(active_nurseries=10, reports_submitted=0)
        score_complete = _compute_main_indicators(sub_complete)["reports_attendance"]
        score_missing = _compute_main_indicators(sub_missing)["reports_attendance"]
        assert score_complete > score_missing


# ---------------------------------------------------------------------------
# tasks_governance — composite score
# ---------------------------------------------------------------------------

class TestTasksGovernance:

    def test_max_governance_no_delay(self):
        """Perfect governance, all training done, no delayed tasks → should be near 100."""
        sub = _make_sub(
            governance_score=100.0,
            training_completion=100.0,
            delayed_tasks=0,
        )
        result = _compute_main_indicators(sub)
        assert result["tasks_governance"] >= 99.0

    def test_zero_governance_max_delay(self):
        """
        tasks_governance formula:
          governance * 0.5 + training * 0.3 + max(0, 50 - penalty) * 0.4
          penalty = min(50, delayed_tasks * 5)

        With governance=0, training=0, delayed_tasks=10:
          penalty = min(50, 50) = 50
          score = 0 + 0 + max(0, 50-50)*0.4 = 0
        """
        sub = _make_sub(
            governance_score=0.0,
            training_completion=0.0,
            delayed_tasks=10,
        )
        result = _compute_main_indicators(sub)
        assert result["tasks_governance"] == 0.0

    def test_score_in_valid_range(self):
        for g in [0, 50, 100]:
            for t in [0, 50, 100]:
                for d in [0, 5, 15]:
                    sub = _make_sub(governance_score=float(g),
                                    training_completion=float(t),
                                    delayed_tasks=d)
                    r = _compute_main_indicators(sub)
                    v = r["tasks_governance"]
                    assert 0.0 <= v <= 100.0, (
                        f"tasks_governance={v} out of range for "
                        f"governance={g}, training={t}, delayed={d}"
                    )


# ---------------------------------------------------------------------------
# Composite: all indicators simultaneously in empty-DB conditions
# ---------------------------------------------------------------------------

class TestEmptyDBEdgeCases:

    def test_zero_across_the_board(self):
        """
        All sub-indicators at zero. Should not crash and all values must be
        within [0, 100].
        """
        sub = _make_sub(
            active_nurseries=0, inactive_nurseries=0,
            registered_children=0, unregistered_children=0,
            supervisors_count=0, classrooms_count=0, classrooms_no_supervisor=0,
            child_supervisor_ratio=0.0, child_teacher_ratio=0.0,
            incidents_total=0, incidents_critical=0, protection_cases=0,
            incident_severity=0,
            reports_submitted=0, reports_missing=0,
            absence_rate=0.0, health_absences=0, repeated_health=0,
            delayed_tasks=0,
            governance_score=0.0, training_completion=0.0, compliance_status=0.0,
            active_pct=0.0, inactive_pct=0.0, registration_rate=0.0, age_distribution=0,
        )
        result = _compute_main_indicators(sub)
        for k, v in result.items():
            assert not math.isnan(v), f"{k} is NaN"
            assert not math.isinf(v), f"{k} is inf"
            assert 0.0 <= v <= 100.0, f"{k}={v} out of [0, 100]"

    def test_single_kindergarten_single_child(self):
        """Minimal real deployment: 1 KG, 1 child, no incidents."""
        sub = _make_sub(
            active_nurseries=1, inactive_nurseries=0,
            registered_children=1, unregistered_children=0,
            supervisors_count=1, classrooms_count=1, classrooms_no_supervisor=0,
            incidents_critical=0, protection_cases=0,
            reports_submitted=30, reports_missing=0,
            absence_rate=0.0, health_absences=0,
            governance_score=80.0, training_completion=80.0, delayed_tasks=0,
        )
        result = _compute_main_indicators(sub)
        for k, v in result.items():
            assert 0.0 <= v <= 100.0, f"{k}={v} out of range"
        assert result["nursery_status"] == 100.0
        assert result["children_registration"] == 100.0
        assert result["safety_incidents"] == 100.0

    def test_large_values_no_overflow(self):
        """Stress test: very large numbers should not overflow or crash."""
        sub = _make_sub(
            active_nurseries=10_000, inactive_nurseries=500,
            registered_children=500_000, unregistered_children=25_000,
            supervisors_count=5_000, classrooms_count=8_000, classrooms_no_supervisor=200,
            incidents_total=50, incidents_critical=2, protection_cases=0,
            reports_submitted=270_000, reports_missing=30_000,
            absence_rate=8.0, health_absences=4_000, repeated_health=1_200,
            delayed_tasks=400,
            governance_score=72.0, training_completion=68.0,
        )
        result = _compute_main_indicators(sub)
        for k, v in result.items():
            assert not math.isnan(v), f"{k} is NaN with large inputs"
            assert 0.0 <= v <= 100.0, f"{k}={v} out of [0, 100] with large inputs"
