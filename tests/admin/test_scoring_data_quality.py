"""ADMIN-SCORING-002 — four-dimensional data quality score.

The old score was report-filing rate alone. These tests pin the four
dimensions, their weights, and the clamping that keeps a dimension in range
when counts arrive from differently scoped queries.
"""

import pytest

from services.admin.reports.scoring import (
    DATA_QUALITY_WEIGHTS,
    calculate_data_quality_score,
)


def _score(**overrides):
    """A perfect-quality baseline, with named fields overridden per test."""
    args = dict(
        total_children=100,
        missing_dob_count=0,
        missing_gender_count=0,
        invalid_age_count=0,
        duplicate_count=0,
        total_enrollments=100,
        active_kg_count=10,
        kg_with_recent_report=10,
        total_fields_required=1000,
        total_fields_filled=1000,
    )
    args.update(overrides)
    return calculate_data_quality_score(**args)


class TestDataQualityScoring:
    def test_weights_sum_to_one(self):
        assert pytest.approx(sum(DATA_QUALITY_WEIGHTS.values())) == 1.0

    def test_weights_match_business_rule(self):
        assert DATA_QUALITY_WEIGHTS == {
            "completeness": 0.30,
            "timeliness": 0.20,
            "validity": 0.30,
            "uniqueness": 0.20,
        }

    def test_perfect_data_scores_100(self):
        result = _score()

        assert result["overall_score"] == 100.0
        assert result["status"] == "green"
        for dimension in result["dimensions"].values():
            assert dimension["score"] == 100.0

    def test_all_four_dimensions_reported(self):
        result = _score()
        assert set(result["dimensions"]) == set(DATA_QUALITY_WEIGHTS)

    def test_completeness_dimension(self):
        result = _score(total_fields_required=1000, total_fields_filled=800)

        assert result["dimensions"]["completeness"]["score"] == 80.0
        # Only the 30% completeness slice moves: 100 - (20 * 0.30)
        assert result["overall_score"] == 94.0

    def test_timeliness_dimension(self):
        result = _score(active_kg_count=10, kg_with_recent_report=5)

        assert result["dimensions"]["timeliness"]["score"] == 50.0
        assert result["overall_score"] == 90.0  # 100 - (50 * 0.20)
        assert result["issues"]["kindergartens_without_recent_report"] == 5

    def test_validity_dimension_counts_dob_and_age(self):
        result = _score(total_children=100, missing_dob_count=10, invalid_age_count=10)

        assert result["dimensions"]["validity"]["score"] == 80.0
        assert result["overall_score"] == 94.0  # 100 - (20 * 0.30)

    def test_uniqueness_dimension(self):
        result = _score(total_enrollments=100, duplicate_count=25)

        assert result["dimensions"]["uniqueness"]["score"] == 75.0
        assert result["overall_score"] == 95.0  # 100 - (25 * 0.20)

    def test_timeliness_alone_no_longer_defines_the_score(self):
        """The defect that motivated ADMIN-SCORING-002.

        Every kindergarten filed on time, but a third of the children have no
        usable date of birth. The old score reported 100.
        """
        result = _score(
            active_kg_count=10,
            kg_with_recent_report=10,
            total_children=300,
            missing_dob_count=100,
        )

        assert result["dimensions"]["timeliness"]["score"] == 100.0
        assert result["overall_score"] < 91.0

    def test_weighted_average_is_exact(self):
        result = _score(
            total_fields_required=100, total_fields_filled=50,   # completeness 50
            active_kg_count=10, kg_with_recent_report=6,          # timeliness   60
            total_children=100, missing_dob_count=30,             # validity     70
            total_enrollments=100, duplicate_count=20,            # uniqueness   80
        )

        expected = 50 * 0.30 + 60 * 0.20 + 70 * 0.30 + 80 * 0.20
        assert result["overall_score"] == pytest.approx(expected)
        assert result["overall_score"] == 64.0

    def test_zero_denominators_do_not_divide_by_zero(self):
        result = calculate_data_quality_score(
            total_children=0,
            missing_dob_count=0,
            missing_gender_count=0,
            invalid_age_count=0,
            duplicate_count=0,
            total_enrollments=0,
            active_kg_count=0,
            kg_with_recent_report=0,
            total_fields_required=0,
            total_fields_filled=0,
        )

        assert result["overall_score"] == 50.0  # completeness/timeliness 0, validity/uniqueness 100
        assert result["dimensions"]["completeness"]["score"] == 0.0
        assert result["dimensions"]["validity"]["score"] == 100.0

    def test_dimensions_clamped_to_range(self):
        """Counts from differently scoped queries cannot push a dimension out of 0-100."""
        result = _score(
            total_fields_required=100, total_fields_filled=500,  # >100% completeness
            total_children=10, missing_dob_count=999,            # deeply negative validity
        )

        assert result["dimensions"]["completeness"]["score"] == 100.0
        assert result["dimensions"]["validity"]["score"] == 0.0

    def test_bilingual_dimension_labels(self):
        """Mandate 1: every dimension label ships in Arabic and English."""
        result = _score()

        for dimension in result["dimensions"].values():
            assert dimension["label_ar"].strip()
            assert dimension["label_en"].strip()
            assert dimension["label_ar"] != dimension["label_en"]

        assert result["dimensions"]["completeness"]["label_ar"] == "الاكتمال"
        assert result["dimensions"]["validity"]["label_ar"] == "الصحة"

    def test_issues_block_surfaces_raw_counts(self):
        result = _score(
            missing_dob_count=3,
            missing_gender_count=4,
            invalid_age_count=5,
            duplicate_count=6,
            active_kg_count=10,
            kg_with_recent_report=7,
        )

        assert result["issues"] == {
            "missing_dob": 3,
            "missing_gender": 4,
            "invalid_age": 5,
            "duplicate_children": 6,
            "kindergartens_without_recent_report": 3,
        }

    def test_missing_gender_is_reported_but_not_scored(self):
        """Gender is reported as an issue; it is not part of any dimension.

        The specification lists missing_gender in the issues block only, and
        does not include it in the validity numerator. Pinning that here so a
        later change to the formula has to be deliberate.
        """
        with_gender_gap = _score(missing_gender_count=50)
        without = _score(missing_gender_count=0)

        assert with_gender_gap["overall_score"] == without["overall_score"]
        assert with_gender_gap["issues"]["missing_gender"] == 50
