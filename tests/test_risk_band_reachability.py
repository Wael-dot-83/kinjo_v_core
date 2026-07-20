"""Risk-score scale and band-reachability contract.

Background: sub-indicator risk was averaged into a 0-20 range (each per-sub
contribution is capped at 20) and then combined as if it were a 0-100 component:

    score = 0.65 * avg_indicator_risk + 0.35 * sub_risk + 0.1 * trend_penalty

With sub_risk <= 20 the ceiling was 0.65*100 + 0.35*20 + 3 = 75, and without a
trend penalty — which is the normal first-run case, since trend needs history —
the practical ceiling was 72. "critical" (>= 75) was therefore unreachable and
the escalation tier "تصعيد للإدارة العليا خلال 7 أيام" could never fire.

The fix rescales the sub mean onto 0-100. These tests pin the scale contract and
prove every declared band is reachable, so the defect cannot silently return.
"""
from datetime import date

import pytest

from heatmap.backend import constants as C
from heatmap.backend.pipeline import compute_risk_score

MAIN_KEYS = [m["key"] for m in C.MAIN_INDICATORS]


def _main(value):
    """All main indicators at one health value (0 = worst, 100 = best)."""
    return {k: float(value) for k in MAIN_KEYS}


def _subs_at_worst():
    """Every sub-indicator pushed far past its threshold in the unhealthy direction."""
    sub = {}
    for main_key, defs in C.SUB_INDICATORS.items():
        for d in defs:
            th = d.get("threshold_high") or 100
            # higher_is_better -> a value of 0 is worst; else far above threshold.
            sub[d["key"]] = 0 if d.get("higher_is_better") else th * 100
    return sub


def _subs_at_best():
    sub = {}
    for main_key, defs in C.SUB_INDICATORS.items():
        for d in defs:
            th = d.get("threshold_high") or 100
            sub[d["key"]] = th * 100 if d.get("higher_is_better") else 0
    return sub


class TestScaleContract:
    """Every intermediate value is on the documented 0-100 risk scale."""

    def test_best_case_is_zero_risk(self):
        score, level, _, _ = compute_risk_score(_main(100), _subs_at_best())
        assert score == 0.0
        assert level == "low"

    def test_worst_case_saturates_the_scale(self):
        score, level, _, _ = compute_risk_score(_main(0), _subs_at_worst())
        assert score == 100.0, (
            f"worst-case input must reach the top of the 0-100 scale, got {score}"
        )
        assert level == "critical"

    def test_score_is_clamped_to_0_100(self):
        for main_value in (0, 25, 50, 75, 100):
            for subs in (_subs_at_worst(), _subs_at_best()):
                score, _, _, _ = compute_risk_score(_main(main_value), subs)
                assert 0.0 <= score <= 100.0, f"score {score} outside [0, 100]"


class TestBandReachability:
    """Each declared band must be reachable from some real input."""

    def test_every_declared_band_is_reachable(self):
        reached = set()
        worst, best = _subs_at_worst(), _subs_at_best()
        for main_value in range(0, 101):
            for subs in (best, worst):
                _, level, _, _ = compute_risk_score(_main(main_value), subs)
                reached.add(level)
        declared = {r["key"] for r in C.RISK_LEVELS}
        assert declared <= reached, (
            f"unreachable risk band(s): {sorted(declared - reached)} — "
            "a declared band that no input can produce is a dead escalation tier"
        )

    def test_critical_reachable_without_trend_history(self):
        """First run has no previous_main, so no trend penalty is available.

        The original defect was masked by assuming a trend penalty could make up
        the shortfall; it cannot on a first run.
        """
        score, level, _, _ = compute_risk_score(
            _main(0), _subs_at_worst(), previous_main=None
        )
        assert level == "critical", (
            f"critical must be reachable with no trend history, got {level} ({score})"
        )

    @pytest.mark.parametrize("beta", [1.0, 0.5, 0.3, 0.2, 0.1, 0.01])
    def test_critical_reachable_under_regression_weights(self, beta):
        """Reachability must not depend on the magnitude of regression weights.

        run_daily_pipeline always passes regression_weights built from
        MapRegressionSnapshot.beta_std once snapshots exist, and standardized
        betas are routinely well below 1. An earlier fix divided the *weighted*
        contribution sum by the plain count, so the mean shrank with the weights:
        at beta_std = 0.2 the ceiling fell back to exactly 72.0 — the original
        unreachable-critical bug, returning precisely in the mature-data state.
        """
        weights = {
            f"{main_key}.{d['key']}": beta
            for main_key, defs in C.SUB_INDICATORS.items()
            for d in defs
        }
        score, level, _, _ = compute_risk_score(
            _main(0), _subs_at_worst(), regression_weights=weights
        )
        assert level == "critical", (
            f"critical unreachable with beta_std={beta}: score={score}"
        )

    def test_weighted_best_case_is_still_zero(self):
        """The weighted mean must not inflate a healthy score either."""
        weights = {
            f"{main_key}.{d['key']}": 0.2
            for main_key, defs in C.SUB_INDICATORS.items()
            for d in defs
        }
        score, level, _, _ = compute_risk_score(
            _main(100), _subs_at_best(), regression_weights=weights
        )
        assert score == 0.0
        assert level == "low"

    def test_non_uniform_weights_do_not_break_the_ceiling(self):
        """Real beta_std values differ per sub-indicator, not a single constant."""
        import random

        rng = random.Random(7)
        weights = {
            f"{main_key}.{d['key']}": rng.uniform(0.05, 0.9)
            for main_key, defs in C.SUB_INDICATORS.items()
            for d in defs
        }
        score, level, _, _ = compute_risk_score(
            _main(0), _subs_at_worst(), regression_weights=weights
        )
        assert level == "critical", f"score={score} with non-uniform weights"

    def test_critical_threshold_not_lowered(self):
        """The fix must be the scale, not a moved goalpost."""
        critical = next(r for r in C.RISK_LEVELS if r["key"] == "critical")
        assert critical["min"] == 75, (
            "critical threshold changed — the unreachable-band defect must be "
            "fixed by correcting the scale, never by lowering the threshold"
        )


class TestBandBoundaries:
    """Classification is correct immediately below, at, and above each threshold."""

    @pytest.mark.parametrize(
        "score,expected",
        [
            (0.0, "low"), (24.9, "low"),
            (25.0, "medium"), (49.9, "medium"),
            (50.0, "high"), (74.9, "high"),
            (75.0, "critical"), (100.0, "critical"),
        ],
    )
    def test_risk_level_for_score_boundaries(self, score, expected):
        assert C.risk_level_for_score(score)["key"] == expected

    def test_arabic_escalation_label_matches_critical_band(self):
        """The Arabic label operators act on must belong to the critical band."""
        critical = next(r for r in C.RISK_LEVELS if r["key"] == "critical")
        assert critical["name_ar"] == "حرج"
        assert C.risk_level_for_score(80.0)["name_ar"] == "حرج"


class TestInsufficientData:
    """Unavailable data must never be scored as risk-free or as critical."""

    def test_all_indicators_unavailable_is_not_critical(self):
        score, level, _, _ = compute_risk_score(
            {k: None for k in MAIN_KEYS}, {}
        )
        assert score == 0.0
        assert level == "low", (
            "absent evidence must not be escalated as critical risk"
        )

    def test_unavailable_indicators_are_excluded_not_zeroed(self):
        """A None indicator must not be scored as 0 health (= 100 risk)."""
        partial = _main(100)
        partial[MAIN_KEYS[0]] = None
        score_partial, _, _, _ = compute_risk_score(partial, _subs_at_best())
        score_full, _, _, _ = compute_risk_score(_main(100), _subs_at_best())
        assert score_partial == score_full, (
            "excluding an unavailable indicator must not change the score of the "
            "remaining healthy ones; a None treated as 0 would spike risk"
        )
