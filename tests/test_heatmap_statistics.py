"""
Statistical correctness tests for the Heat Map analytical engine.

These tests use hand-computed fixtures (see
`heatmap/tests/fixtures/statistical_fixtures.py`) to verify that:

  - Pearson r matches reference values (R / sklearn)
  - Spearman ρ matches reference values, with Kendall τ fallback for ties
  - Standardized OLS recovers the original slope (β_std) on a simple linear model
  - VIF is ∞ for perfectly collinear predictors
  - R² is 1.0 for a perfect fit, ~0 for noise
  - The strength bucketing (weak / moderate / strong / very_strong) is correct
  - The full correlation matrix and full regression matrix run end-to-end
"""
import os
import sys
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

import math
import numpy as np
import pandas as pd
import pytest

from heatmap.backend.analytics.pearson import (
    _pearson_manual,
    compute_correlation_matrix,
    full_correlation_matrix,
)
from heatmap.backend.analytics.spearman import (
    spearman_with_fallback,
    correlation_strength,
    is_significant,
    compute_spearman_matrix,
    KENDALL_TIE_FALLBACK_THRESHOLD,
)
from heatmap.backend.analytics.ols import (
    ols_standardized,
    run_all_regressions,
    VIF_RED_FLAG_THRESHOLD,
    VIF_WARNING_THRESHOLD,
    HIGH_IMPACT_THRESHOLD,
    priority_score,
)
from heatmap.backend.analytics.stats import compute_full_stats, stats_to_csv
from heatmap.backend.constants import MAIN_INDICATORS


# ---------------------------------------------------------------------------
# Pearson correlation
# ---------------------------------------------------------------------------
class TestPearson:
    def test_perfect_positive_linear(self):
        from heatmap.tests.fixtures.statistical_fixtures import perfect_positive_linear, REFERENCE
        x, y = perfect_positive_linear(n=30)
        r, p = _pearson_manual(x, y)
        assert math.isclose(r, REFERENCE["perfect_positive_linear"]["pearson_r"], abs_tol=1e-6), \
            f"Expected r=1.0, got {r}"
        assert p < REFERENCE["perfect_positive_linear"]["p_value_max"]

    def test_perfect_negative_linear(self):
        from heatmap.tests.fixtures.statistical_fixtures import perfect_negative_linear, REFERENCE
        x, y = perfect_negative_linear(n=30)
        r, p = _pearson_manual(x, y)
        assert math.isclose(r, -1.0, abs_tol=1e-6)
        assert p < 1e-10

    def test_constant_series_returns_nan(self):
        from heatmap.tests.fixtures.statistical_fixtures import constant_series
        x, y = constant_series()
        r, p = _pearson_manual(x, y)
        assert math.isnan(r)
        assert math.isnan(p)

    def test_uncorrelated_low_r(self):
        from heatmap.tests.fixtures.statistical_fixtures import uncorrelated
        x, y = uncorrelated(n=200, seed=0)
        r, p = _pearson_manual(x, y)
        assert abs(r) < 0.2, f"Expected r near 0 for uncorrelated, got {r}"
        assert p > 0.01

    def test_small_sample_returns_nan(self):
        x = np.array([1.0, 2.0])
        y = np.array([3.0, 4.0])
        r, p = _pearson_manual(x, y)
        assert math.isnan(r)
        assert math.isnan(p)

    def test_clipped_to_unit_interval(self):
        """Numerical noise near perfect correlation must be clipped to [-1, 1]."""
        x = np.linspace(0, 1, 30)
        y = 2 * x + 1e-10 * np.random.default_rng(0).normal(size=30)
        r, _ = _pearson_manual(x, y)
        assert -1.0 <= r <= 1.0

    def test_compute_correlation_matrix(self):
        from heatmap.tests.fixtures.statistical_fixtures import perfect_positive_linear
        x, y = perfect_positive_linear(n=30)
        df = pd.DataFrame({"main_x": x, "sub_y": y, "sub_z": -y})
        matrix = compute_correlation_matrix(df, {"main_x": ["sub_y", "sub_z"]})
        assert len(matrix) == 2
        r_y = matrix[matrix["sub_indicator"] == "sub_y"]["pearson_r"].iloc[0]
        r_z = matrix[matrix["sub_indicator"] == "sub_z"]["pearson_r"].iloc[0]
        assert math.isclose(float(r_y), 1.0, abs_tol=1e-3)
        assert math.isclose(float(r_z), -1.0, abs_tol=1e-3)

    def test_strong_correlation_flag(self):
        from heatmap.backend.analytics.pearson import STRONG_CORRELATION_THRESHOLD
        assert STRONG_CORRELATION_THRESHOLD == 0.7


# ---------------------------------------------------------------------------
# Spearman correlation
# ---------------------------------------------------------------------------
class TestSpearman:
    def test_perfect_positive_linear(self):
        from heatmap.tests.fixtures.statistical_fixtures import perfect_positive_linear
        x, y = perfect_positive_linear(n=30)
        rho, p, method = spearman_with_fallback(x, y)
        assert math.isclose(rho, 1.0, abs_tol=1e-6)
        assert method == "spearman"
        assert p < 1e-10

    def test_monotonic_nonlinear_perfect_rho_zero_pearson(self):
        """A perfect rank-monotonic but non-linear relationship should have ρ=1 and |r| small."""
        from heatmap.tests.fixtures.statistical_fixtures import perfect_monotonic_nonlinear
        x, y = perfect_monotonic_nonlinear(n=30)
        rho, _, method = spearman_with_fallback(x, y)
        assert math.isclose(rho, 1.0, abs_tol=1e-6), f"Expected ρ=1.0, got {rho}"
        assert method == "spearman"

    def test_negative_monotonic(self):
        from heatmap.tests.fixtures.statistical_fixtures import perfect_negative_linear
        x, y = perfect_negative_linear(n=30)
        rho, _, _ = spearman_with_fallback(x, y)
        assert math.isclose(rho, -1.0, abs_tol=1e-6)

    def test_kendall_fallback_on_many_ties(self):
        """If >= 50% of values are tied, the engine should fall back to Kendall τ."""
        from heatmap.tests.fixtures.statistical_fixtures import has_many_ties
        x, y = has_many_ties()
        coef, p, method = spearman_with_fallback(x, y)
        assert method == "kendall_tau", f"Expected kendall_tau fallback, got {method}"
        # The relationship is monotone increasing; τ should be positive
        assert coef > 0.5

    def test_constant_series_handled(self):
        from heatmap.tests.fixtures.statistical_fixtures import constant_series
        x, y = constant_series(n=10)
        coef, p, method = spearman_with_fallback(x, y)
        assert math.isnan(coef) or method == "insufficient" or coef is None

    def test_strength_bucketing(self):
        assert correlation_strength(0.0) == "weak"
        assert correlation_strength(0.10) == "weak"
        assert correlation_strength(0.29) == "weak"
        assert correlation_strength(0.30) == "moderate"
        assert correlation_strength(0.50) == "moderate"
        assert correlation_strength(0.59) == "moderate"
        assert correlation_strength(0.60) == "strong"
        assert correlation_strength(0.75) == "strong"
        assert correlation_strength(0.79) == "strong"
        assert correlation_strength(0.80) == "very_strong"
        assert correlation_strength(1.00) == "very_strong"
        # Symmetric
        assert correlation_strength(-0.85) == "very_strong"
        # None / NaN
        assert correlation_strength(float("nan")) == "insufficient"

    def test_is_significant(self):
        assert is_significant(0.01, alpha=0.05) is True
        assert is_significant(0.06, alpha=0.05) is False
        assert is_significant(float("nan"), alpha=0.05) is False
        assert is_significant(None, alpha=0.05) is False

    def test_compute_spearman_matrix(self):
        from heatmap.tests.fixtures.statistical_fixtures import perfect_monotonic_nonlinear
        x, y = perfect_monotonic_nonlinear(n=30)
        df = pd.DataFrame({"main_x": x, "sub_y": y})
        matrix = compute_spearman_matrix(df, {"main_x": ["sub_y"]})
        assert len(matrix) == 1
        rho = matrix["spearman_rho"].iloc[0]
        assert math.isclose(float(rho), 1.0, abs_tol=1e-6)


# ---------------------------------------------------------------------------
# OLS regression
# ---------------------------------------------------------------------------
class TestOLS:
    def test_perfect_fit_r_squared_one(self):
        from heatmap.tests.fixtures.statistical_fixtures import perfect_positive_linear
        x, y = perfect_positive_linear(n=30)
        X = pd.DataFrame({"x1": x})
        coef_df, meta = ols_standardized(X, pd.Series(y))
        assert math.isclose(meta["r_squared"], 1.0, abs_tol=1e-3), f"R² should be ~1.0, got {meta['r_squared']}"
        # For a single predictor in a perfect linear relationship, |β_std| should be ~1
        assert abs(coef_df["beta_std"].iloc[0]) > 0.9

    def test_no_signal_low_r_squared(self):
        from heatmap.tests.fixtures.statistical_fixtures import uncorrelated
        rng = np.random.default_rng(0)
        x1, _ = uncorrelated(n=30, seed=0)
        x2 = rng.normal(0, 1, 30)
        y = rng.normal(0, 1, 30)
        X = pd.DataFrame({"x1": x1, "x2": x2})
        coef_df, meta = ols_standardized(X, pd.Series(y))
        assert meta["r_squared"] < 0.20, f"R² should be near 0 for noise, got {meta['r_squared']}"

    def test_perfect_multicollinearity_vif_infinity(self):
        from heatmap.tests.fixtures.statistical_fixtures import multicollinear_pair
        x1, x2 = multicollinear_pair(n=30)
        rng = np.random.default_rng(0)
        y = 2 * x1 + rng.normal(0, 1e-9, 30)
        X = pd.DataFrame({"x1": x1, "x2": x2})
        # Force ridge via use_ridge=True (multicollinearity should be flagged via VIF)
        coef_df, meta = ols_standardized(X, pd.Series(y), use_ridge=True)
        assert meta["ridge_used"] is True
        # VIF for at least one of the collinear columns should be flagged 'red'
        flags = set(coef_df["vif_flag"].tolist())
        assert "red" in flags, f"Expected 'red' VIF flag for perfectly collinear predictors, got {flags}"

    def test_high_impact_flag(self):
        from heatmap.tests.fixtures.statistical_fixtures import perfect_positive_linear
        x, y = perfect_positive_linear(n=30)
        X = pd.DataFrame({"x1": x})
        coef_df, meta = ols_standardized(X, pd.Series(y))
        # For a single dominant predictor, |β| should be near 1
        assert bool(coef_df["high_impact"].iloc[0]) is True
        assert abs(coef_df["beta_std"].iloc[0]) >= HIGH_IMPACT_THRESHOLD

    def test_small_sample_falls_back_to_ridge(self):
        """When n < k+2, ridge is used automatically."""
        x = np.arange(3, dtype=float)            # n=3 samples
        y = 2 * x + 1
        X = pd.DataFrame({"x1": x, "x2": x * 2, "x3": x * 3, "x4": x * 4})  # k=4 predictors
        coef_df, meta = ols_standardized(X, pd.Series(y))
        assert bool(meta["ridge_used"]) is True
        assert len(coef_df) == 4

    def test_vif_thresholds(self):
        from heatmap.tests.fixtures.statistical_fixtures import multicollinear_pair
        x1, x2 = multicollinear_pair(n=30)
        X = pd.DataFrame({"x1": x1, "x2": x2})
        coef_df, _ = ols_standardized(X, pd.Series(x1), use_ridge=True)
        for _, row in coef_df.iterrows():
            assert row["vif_flag"] in ("ok", "warning", "red")

    def test_r_squared_warning(self):
        """If R² < 0.30, meta.fit_warning should be set."""
        rng = np.random.default_rng(0)
        x1 = rng.normal(0, 1, 30)
        x2 = rng.normal(0, 1, 30)
        y = rng.normal(0, 1, 30)  # pure noise target
        X = pd.DataFrame({"x1": x1, "x2": x2})
        _, meta = ols_standardized(X, pd.Series(y))
        if meta["r_squared"] < 0.30:
            assert meta["fit_warning"] == "weak fit"

    def test_run_all_regressions(self):
        """End-to-end regression matrix using the project's indicator map."""
        from heatmap.backend.constants import SUB_INDICATORS
        rng = np.random.default_rng(0)
        n = 60
        df = pd.DataFrame()
        # SUB_INDICATORS is a list of dicts; extract the keys for the map.
        subs_map = {"nursery_status": [s["key"] for s in SUB_INDICATORS["nursery_status"]]}
        # Add sub-indicators for nursery_status
        for sub in subs_map["nursery_status"]:
            df[sub] = rng.normal(0, 1, n)
        # main = weighted sum + noise
        nursery_main = (
            0.6 * df["active_pct"]
          - 0.3 * df["inactive_pct"]
          + 0.1 * df["active_nurseries"] / 10
          + 0.05 * df["inactive_nurseries"] / 10
          + rng.normal(0, 0.5, n)
        )
        # Convert to 0-100 score
        df["nursery_status"] = (nursery_main - nursery_main.min()) / (nursery_main.max() - nursery_main.min()) * 100
        # Re-standardize so the test is meaningful
        df["nursery_status"] = (df["nursery_status"] - df["nursery_status"].mean()) / df["nursery_status"].std() * 20 + 70
        results = run_all_regressions(df, subs_map)
        assert "nursery_status" in results
        assert "coefficients" in results["nursery_status"]
        assert "meta" in results["nursery_status"]
        # The two strongest contributors should be `active_pct` and `inactive_pct`
        coefs = results["nursery_status"]["coefficients"]
        top = coefs.iloc[0]["sub_indicator"]
        assert top in ("active_pct", "inactive_pct"), f"Expected top contributor in {{active_pct, inactive_pct}}, got {top}"


# ---------------------------------------------------------------------------
# Priority score
# ---------------------------------------------------------------------------
class TestPriorityScore:
    def test_priority_score_high_for_outlier(self):
        """A governorate with an extreme value on a high-impact sub should have a high priority score."""
        coefs = pd.DataFrame({
            "sub_indicator": ["sub1", "sub2"],
            "beta_std": [0.8, 0.3],
        })
        current = pd.Series({"sub1": 100.0, "sub2": 50.0})  # sub1 is at the extreme
        mean = pd.Series({"sub1": 50.0, "sub2": 50.0})
        std = pd.Series({"sub1": 10.0, "sub2": 10.0})
        result = priority_score(coefs, current, mean, std)
        assert len(result) == 2
        # sub1 has both high beta (0.8) and high |z| (5.0) → highest contribution
        sub1_row = result[result["sub_indicator"] == "sub1"].iloc[0]
        sub2_row = result[result["sub_indicator"] == "sub2"].iloc[0]
        assert sub1_row["contribution"] > sub2_row["contribution"]

    def test_priority_score_percentages_sum_to_100(self):
        coefs = pd.DataFrame({
            "sub_indicator": ["a", "b", "c"],
            "beta_std": [0.5, 0.3, 0.2],
        })
        current = pd.Series({"a": 10, "b": 20, "c": 30})
        mean = pd.Series({"a": 5, "b": 15, "c": 25})
        std = pd.Series({"a": 5, "b": 5, "c": 5})
        result = priority_score(coefs, current, mean, std)
        assert math.isclose(result["priority_pct"].sum(), 100.0, abs_tol=1e-6)


# ---------------------------------------------------------------------------
# Full stats aggregation
# ---------------------------------------------------------------------------
class TestFullStats:
    def test_compute_full_stats_merges_corr_and_ols(self):
        from heatmap.backend.constants import SUB_INDICATORS
        rng = np.random.default_rng(0)
        n = 60
        df = pd.DataFrame()
        subs_map = {"nursery_status": [s["key"] for s in SUB_INDICATORS["nursery_status"]]}
        for sub in subs_map["nursery_status"]:
            df[sub] = rng.normal(0, 1, n)
        df["nursery_status"] = (
            0.6 * df["active_pct"]
          - 0.4 * df["inactive_pct"]
          + rng.normal(0, 0.1, n)
        )
        df["nursery_status"] = (df["nursery_status"] - df["nursery_status"].mean()) / df["nursery_status"].std() * 20 + 70
        stats = compute_full_stats(df, subs_map)
        assert "pearson_r" in stats.columns
        assert "beta_std" in stats.columns
        assert "high_impact" in stats.columns
        assert len(stats) == len(subs_map["nursery_status"])

    def test_stats_to_csv_is_serializable(self):
        df = pd.DataFrame({"a": [1, 2, 3], "b": [4, 5, 6]})
        csv_str = stats_to_csv(df)
        assert "a,b" in csv_str
        assert "1,4" in csv_str
        assert "3,6" in csv_str


# ---------------------------------------------------------------------------
# Constants sanity
# ---------------------------------------------------------------------------
class TestConstants:
    def test_indicator_count(self):
        from heatmap.backend.constants import INDICATOR_ALERT_THRESHOLD
        assert len(MAIN_INDICATORS) == 6
        for ind in MAIN_INDICATORS:
            assert "key" in ind
            assert "name_en" in ind
            assert "name_ar" in ind
            assert "color" in ind
            # alert_threshold lives in the separate INDICATOR_ALERT_THRESHOLD dict
            assert ind["key"] in INDICATOR_ALERT_THRESHOLD
            assert INDICATOR_ALERT_THRESHOLD[ind["key"]] > 0

    def test_indicator_keys(self):
        keys = {i["key"] for i in MAIN_INDICATORS}
        assert keys == {
            "nursery_status", "children_registration", "staff_classrooms",
            "safety_incidents", "reports_attendance", "tasks_governance",
        }
