"""ADMIN-SCORING-001 — weighted-severity compliance score.

Covers the validation cases named in specification section 3.1 plus the edge
cases the old formula got wrong.
"""

import pytest

from services.admin.reports.scoring import (
    VIOLATION_RULES,
    ViolationSeverity,
    calculate_compliance_score,
)


class TestComplianceScoring:
    def test_single_critical_violation(self):
        """One class of children with no supervisor costs 25 points."""
        result = calculate_compliance_score({"class_with_children_no_supervisor": 1})

        assert result["score"] == 75.0  # 100 - 25
        # Specification section 3.1 defines the bands as >=95 green, >=85
        # yellow, >=70 orange, else red, which puts 75 in "orange". The sample
        # assertion in section 7.3 says "yellow"; it contradicts the band table
        # in the same document, and the band table is the normative one.
        assert result["status"] == "orange"
        assert result["breakdown"]["class_with_children_no_supervisor"]["deduction"] == 25

    def test_multiple_violations(self):
        """Deductions accumulate across violation types."""
        result = calculate_compliance_score({
            "class_with_children_no_supervisor": 2,   # 2 * 25 = 50
            "kindergarten_over_capacity": 1,          # 1 * 15 = 15
        })

        assert result["score"] == 35.0  # 100 - 65
        assert result["status"] == "red"
        assert result["total_deduction"] == 65.0

    def test_score_never_negative(self):
        """The score floors at zero rather than going negative."""
        result = calculate_compliance_score({
            "class_with_children_no_supervisor": 10,  # would be 100 - 250
        })

        assert result["score"] == 0.0
        assert result["status"] == "red"

    def test_no_violations_perfect_score(self):
        result = calculate_compliance_score({})

        assert result["score"] == 100.0
        assert result["status"] == "green"
        assert result["violations"] == []

    def test_arabic_descriptions_present(self):
        """Mandate 1: every violation carries Arabic and English text."""
        result = calculate_compliance_score({"class_with_children_no_supervisor": 1})
        violation = result["violations"][0]

        assert "بدون مشرف" in violation["description_ar"]
        assert "Class with children" in violation["description_en"]

    def test_every_rule_is_bilingual(self):
        """No violation type may ship with an Arabic-only or English-only label."""
        counts = dict.fromkeys(VIOLATION_RULES, 1)
        result = calculate_compliance_score(counts)

        assert len(result["violations"]) == len(VIOLATION_RULES)
        for violation in result["violations"]:
            assert violation["description_ar"].strip()
            assert violation["description_en"].strip()
            assert violation["description_ar"] != violation["description_en"]

    def test_zero_and_negative_counts_ignored(self):
        """A counter at zero is not a violation and must not appear."""
        result = calculate_compliance_score({
            "class_with_children_no_supervisor": 0,
            "kindergarten_over_capacity": -3,
        })

        assert result["score"] == 100.0
        assert result["breakdown"] == {}

    def test_unknown_violation_type_scored_as_low(self):
        """A counter added upstream degrades the score instead of vanishing."""
        result = calculate_compliance_score({"some_new_violation": 2})

        assert result["score"] == 90.0  # 2 * LOW(5)
        assert result["breakdown"]["some_new_violation"]["severity"] == "LOW"

    def test_violations_sorted_worst_first(self):
        result = calculate_compliance_score({
            "missing_dob": 1,                          # LOW
            "class_with_children_no_supervisor": 1,    # CRITICAL
            "kindergarten_over_capacity": 1,           # HIGH
        })

        severities = [v["severity"] for v in result["violations"]]
        assert severities == ["CRITICAL", "HIGH", "LOW"]

    @pytest.mark.parametrize(
        "score_input, expected_status",
        [
            ({}, "green"),                                    # 100
            ({"missing_dob": 1}, "green"),                    # 95
            ({"missing_dob": 2}, "yellow"),                   # 90
            ({"missing_dob": 3}, "yellow"),                   # 85
            ({"missing_dob": 4}, "orange"),                   # 80
            ({"missing_dob": 6}, "orange"),                   # 70
            ({"missing_dob": 7}, "red"),                      # 65
        ],
    )
    def test_status_band_boundaries(self, score_input, expected_status):
        """The band edges are inclusive on the lower bound (>= 95, >= 85, >= 70)."""
        assert calculate_compliance_score(score_input)["status"] == expected_status

    def test_severity_weights_match_business_rule(self):
        """A critical violation is worth five data-quality ones."""
        assert ViolationSeverity.CRITICAL.value == 25
        assert ViolationSeverity.HIGH.value == 15
        assert ViolationSeverity.MEDIUM.value == 10
        assert ViolationSeverity.LOW.value == 5
        assert ViolationSeverity.CRITICAL.value == 5 * ViolationSeverity.LOW.value

    def test_large_network_does_not_dilute_a_critical_violation(self):
        """The defect that motivated ADMIN-SCORING-001.

        Under the old formula the deduction was divided by
        (children + kindergartens + classes), so one unsupervised class in a
        20,000-child network scored ~99.99 -- indistinguishable from clean.
        Severity weighting is independent of network size.
        """
        result = calculate_compliance_score({"class_with_children_no_supervisor": 1})

        old_formula_score = round(100.0 - ((1 / (20000 + 1375 + 3000)) * 100.0), 2)
        assert old_formula_score > 99.9
        assert result["score"] == 75.0
