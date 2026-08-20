"""ADMIN-SCORING-003 — percentile-based risk ranking.

The headline case is the one named in specification section 3.3: rank 100
kindergartens and get exactly 10 critical, 15 warning, 25 elevated, 50 normal.
"""

import pytest

from services.admin.reports.scoring import (
    calculate_risk_score,
    rank_kindergartens_by_risk,
    summarize_risk_bands,
)


class TestRiskScore:
    def test_clean_kindergarten_scores_zero(self):
        assert calculate_risk_score(
            capacity_utilization_pct=0.0,
            supervisor_gap=0,
            children_count=0,
            has_missing_capacity=False,
            has_missing_coordinates=False,
            classes_without_supervisor=0,
        ) == 0.0

    def test_capacity_pressure_weight(self):
        """80% utilisation contributes 80 * 0.4 = 32."""
        assert calculate_risk_score(80.0, 0, 100, False, False, 0) == 32.0

    def test_capacity_pressure_capped_at_150(self):
        """A 400%-full facility is capped so it cannot swamp the other terms."""
        at_cap = calculate_risk_score(150.0, 0, 100, False, False, 0)
        way_over = calculate_risk_score(400.0, 0, 100, False, False, 0)

        assert at_cap == way_over == 60.0  # 150 * 0.4

    def test_staffing_pressure_capped_at_50(self):
        """Each missing supervisor is 20 points, capped at 50 before weighting."""
        assert calculate_risk_score(0.0, 1, 100, False, False, 0) == 8.0    # 20 * 0.4
        assert calculate_risk_score(0.0, 2, 100, False, False, 0) == 16.0   # 40 * 0.4
        assert calculate_risk_score(0.0, 3, 100, False, False, 0) == 20.0   # capped 50 * 0.4
        assert calculate_risk_score(0.0, 99, 100, False, False, 0) == 20.0

    def test_class_pressure_capped_at_30(self):
        assert calculate_risk_score(0.0, 0, 100, False, False, 1) == 2.0    # 10 * 0.2
        assert calculate_risk_score(0.0, 0, 100, False, False, 3) == 6.0    # 30 * 0.2
        assert calculate_risk_score(0.0, 0, 100, False, False, 50) == 6.0   # capped

    def test_unmeasurable_facilities_carry_a_bonus(self):
        """Missing capacity/coordinates is not risk, it is unmeasured risk."""
        assert calculate_risk_score(0.0, 0, 100, True, False, 0) == 10.0
        assert calculate_risk_score(0.0, 0, 100, False, True, 0) == 5.0
        assert calculate_risk_score(0.0, 0, 100, True, True, 0) == 15.0

    def test_score_capped_at_100(self):
        assert calculate_risk_score(400.0, 99, 500, True, True, 99) == 100.0

    def test_negative_inputs_treated_as_zero(self):
        assert calculate_risk_score(-50.0, -3, 0, False, False, -2) == 0.0

    def test_capacity_and_staffing_weigh_equally(self):
        """Business rule: 0.4 each. Equal pressure must give an equal score."""
        capacity_only = calculate_risk_score(50.0, 0, 100, False, False, 0)
        staffing_only = calculate_risk_score(0.0, 2, 100, False, False, 0)

        assert capacity_only == 20.0
        assert staffing_only == 16.0
        # 50 capacity units and 40 staffing units, each * 0.4
        assert capacity_only / 50.0 == staffing_only / 40.0


class TestRiskRanking:
    def test_spec_section_3_3_band_distribution(self):
        """100 kindergartens with distinct scores split exactly 10/15/25/50."""
        rows = [{"id": i, "raw_score": float(i)} for i in range(100)]

        ranked = rank_kindergartens_by_risk(rows)

        assert summarize_risk_bands(ranked) == {
            "critical": 10,
            "warning": 15,
            "elevated": 25,
            "normal": 50,
        }

    def test_ranked_worst_first(self):
        rows = [{"id": i, "raw_score": float(i)} for i in range(100)]

        ranked = rank_kindergartens_by_risk(rows)

        assert ranked[0]["raw_score"] == 99.0
        assert ranked[0]["risk_status"] == "critical"
        assert ranked[-1]["raw_score"] == 0.0
        assert ranked[-1]["risk_status"] == "normal"
        scores = [row["raw_score"] for row in ranked]
        assert scores == sorted(scores, reverse=True)

    def test_percentile_and_population_recorded(self):
        rows = [{"id": i, "raw_score": float(i)} for i in range(100)]

        ranked = rank_kindergartens_by_risk(rows)

        assert ranked[0]["percentile_rank"] == 100.0
        assert ranked[0]["population_size"] == 100
        assert all(row["population_size"] == 100 for row in ranked)

    def test_empty_population(self):
        assert rank_kindergartens_by_risk([]) == []

    def test_single_kindergarten_population(self):
        """A population of one is at the 100th percentile of itself.

        It ranks critical, which is the honest answer: relative risk needs a
        population, and callers should not read a band off a single row.
        """
        ranked = rank_kindergartens_by_risk([{"id": 1, "raw_score": 42.0}])

        assert ranked[0]["percentile_rank"] == 100.0
        assert ranked[0]["population_size"] == 1

    def test_bilingual_risk_labels(self):
        """Mandate 1: every band label ships in Arabic and English."""
        rows = [{"id": i, "raw_score": float(i)} for i in range(100)]

        ranked = rank_kindergartens_by_risk(rows)

        seen = {}
        for row in ranked:
            assert row["risk_label_ar"].strip()
            assert row["risk_label_en"].strip()
            seen[row["risk_status"]] = (row["risk_label_ar"], row["risk_label_en"])

        assert seen["critical"] == ("حرج", "Critical")
        assert seen["warning"] == ("تحذير", "Warning")
        assert seen["elevated"] == ("مرتفع", "Elevated")
        assert seen["normal"] == ("طبيعي", "Normal")

    def test_bands_are_relative_not_absolute(self):
        """The defect that motivated ADMIN-SCORING-003.

        The old thresholds (>=60 critical, >=35 warning) meant a uniformly
        healthy network reported zero at-risk facilities and a uniformly
        stressed one reported everything critical. Percentile bands always
        surface the worst 10%, which is what an inspection schedule needs.
        """
        healthy = [{"id": i, "raw_score": float(i) / 100} for i in range(100)]
        stressed = [{"id": i, "raw_score": 90.0 + float(i) / 100} for i in range(100)]

        assert summarize_risk_bands(rank_kindergartens_by_risk(healthy))["critical"] == 10
        assert summarize_risk_bands(rank_kindergartens_by_risk(stressed))["critical"] == 10

    def test_ties_share_a_percentile(self):
        """Documented behaviour: tied scores are not split arbitrarily.

        ``kind="rank"`` averages the ranks of tied values, so a population of
        100 identical scores puts every row at the mean rank (50.5) rather
        than splitting them into bands on an arbitrary tiebreak. The 10/15/25/50
        shares therefore hold only for distinct scores -- which is the honest
        outcome, since there is no defensible way to call one of two identical
        facilities riskier than the other.
        """
        rows = [{"id": i, "raw_score": 50.0} for i in range(100)]

        ranked = rank_kindergartens_by_risk(rows)

        assert {row["percentile_rank"] for row in ranked} == {50.5}
        assert summarize_risk_bands(ranked) == {
            "critical": 0,
            "warning": 0,
            "elevated": 100,
            "normal": 0,
        }

    def test_ordering_is_stable_across_runs(self):
        """Same input, same order -- a ranking that reshuffles is unusable."""
        def build():
            return [
                {"id": i, "raw_score": float(i % 10)}
                for i in range(50)
            ]

        first = [row["id"] for row in rank_kindergartens_by_risk(build())]
        second = [row["id"] for row in rank_kindergartens_by_risk(build())]

        assert first == second

    def test_end_to_end_scores_then_ranks(self):
        """calculate_risk_score feeding rank_kindergartens_by_risk."""
        rows = []
        for i in range(100):
            rows.append({
                "id": i,
                "raw_score": calculate_risk_score(
                    capacity_utilization_pct=float(i),
                    supervisor_gap=i // 40,
                    children_count=i,
                    has_missing_capacity=False,
                    has_missing_coordinates=False,
                    classes_without_supervisor=0,
                ),
            })

        ranked = rank_kindergartens_by_risk(rows)
        bands = summarize_risk_bands(ranked)

        assert sum(bands.values()) == 100
        assert bands["critical"] == 10
        assert ranked[0]["raw_score"] >= ranked[-1]["raw_score"]
