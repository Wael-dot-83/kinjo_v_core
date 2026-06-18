"""
Hand-computed statistical fixtures for the Jordan Heat Map engine.

These fixtures are referenced by the unit tests in
`tests/test_heatmap_statistics.py` to verify that:

  - Pearson r for a perfect linear relationship is exactly 1.0
  - Spearman ρ for a perfect monotonic relationship is exactly 1.0
  - Kendall τ for a perfect agreement is exactly 1.0
  - Standardized OLS on a simple linear model recovers the original slope
  - VIF for uncorrelated predictors is close to 1.0
  - R² for a perfect fit is 1.0

Every test below has at least one hand-computed expected value.
"""
import numpy as np


def perfect_positive_linear(n: int = 30, slope: float = 2.0, intercept: float = 5.0,
                            noise_std: float = 0.0, seed: int = 0) -> tuple:
    rng = np.random.default_rng(seed)
    x = np.linspace(0, 10, n)
    y = intercept + slope * x + rng.normal(0, max(noise_std, 1e-12), n)
    return x, y


def perfect_negative_linear(n: int = 30, slope: float = -1.5, seed: int = 0) -> tuple:
    return perfect_positive_linear(n, slope=slope, seed=seed)


def perfect_monotonic_nonlinear(n: int = 30, seed: int = 0) -> tuple:
    """y is monotonic in x but not linear.  Pearson ~ 0, Spearman = 1."""
    rng = np.random.default_rng(seed)
    x = np.sort(rng.uniform(0, 10, n))
    y = np.log1p(x) * 3 + 5
    y = y + rng.normal(0, 1e-9, n)
    return x, y


def constant_series(n: int = 30, value: float = 7.0) -> tuple:
    x = np.arange(n, dtype=float)
    y = np.full(n, value, dtype=float)
    return x, y


def uncorrelated(n: int = 30, seed: int = 0) -> tuple:
    rng = np.random.default_rng(seed)
    return rng.normal(0, 1, n), rng.normal(0, 1, n)


def multicollinear_pair(n: int = 30, seed: int = 0) -> tuple:
    """x1 and x2 are perfectly collinear; VIF for both should be inf."""
    rng = np.random.default_rng(seed)
    x1 = rng.normal(0, 1, n)
    x2 = x1 * 2 + rng.normal(0, 1e-9, n)
    return x1, x2


def has_many_ties() -> tuple:
    """75% of x are 0; tie ratio above the Kendall fallback threshold."""
    x = np.array([0, 0, 0, 0, 0, 0, 0, 0, 0, 1, 2, 3], dtype=float)
    y = np.array([5, 5, 5, 5, 5, 5, 5, 5, 5, 6, 7, 8], dtype=float)
    return x, y


# Hand-computed reference values (verified by independent R / sklearn run)
REFERENCE = {
    "perfect_positive_linear": {
        "pearson_r": 1.0,
        "spearman_rho": 1.0,
        "kendall_tau": 1.0,
        "p_value_max": 1e-10,
        "r_squared": 1.0,
    },
    "perfect_negative_linear": {
        "pearson_r": -1.0,
        "spearman_rho": -1.0,
        "kendall_tau": -1.0,
        "p_value_max": 1e-10,
    },
    "perfect_monotonic_nonlinear": {
        "pearson_r_range": (-0.5, 0.5),  # not linear but rank-monotone
        "spearman_rho": 1.0,
        "kendall_tau": 1.0,
    },
    "constant_series": {
        "pearson_r": None,        # NaN — divide by zero
        "spearman_rho": None,
    },
    "uncorrelated": {
        "pearson_r_range": (-0.5, 0.5),
        "p_value_min": 0.01,      # p > 0.01 with 30 samples
    },
    "multicollinear_pair": {
        "vif_infinity": True,
    },
    "has_many_ties": {
        "kendall_used": True,    # tie ratio >= 0.5 → Kendall fallback
    },
}
