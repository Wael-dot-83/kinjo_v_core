"""
Spearman rank correlation between each sub-indicator and its parent main indicator.

Method selection (per the Heat Map tech spec §5.2.1):
    - Pearson  : continuous, normally distributed data (Shapiro-Wilk p > 0.05)
    - Spearman : ordinal, ranked, or non-normal data
    - Kendall τ : fallback when the rank transform produces too many ties

Mathematical form (the rank form of Pearson):
    rₛ = Pearson(R(x), R(y))
where R(·) is the average rank (ties broken by mean rank).

P-value is computed using the t-distribution approximation for n ≥ 10
and a permutation-based p-value for smaller n.
"""
from __future__ import annotations
from typing import Tuple

import numpy as np
import pandas as pd
from scipy import stats as scipy_stats


STRONG_CORRELATION_THRESHOLD = 0.7
KENDALL_TIE_FALLBACK_THRESHOLD = 0.5  # if >= 50% of values are tied, switch to Kendall


def _average_ranks(x: np.ndarray) -> np.ndarray:
    """Convert values to average ranks. Ties share the mean rank."""
    s = pd.Series(x)
    return s.rank(method="average").to_numpy()


def _spearman_r_and_p(x: np.ndarray, y: np.ndarray) -> Tuple[float, float]:
    """
    Spearman correlation with a two-tailed p-value.

    Returns (rho, p_value).  For n < 3 returns (nan, nan).
    """
    x = np.asarray(x, dtype=float)
    y = np.asarray(y, dtype=float)
    n = len(x)
    if n < 3:
        return float("nan"), float("nan")

    # Drop NaNs (any pair with NaN in either column is dropped)
    mask = ~(np.isnan(x) | np.isnan(y))
    x = x[mask]
    y = y[mask]
    n = len(x)
    if n < 3:
        return float("nan"), float("nan")

    rx = _average_ranks(x)
    ry = _average_ranks(y)

    # Pearson on the ranks
    x_dev = rx - rx.mean()
    y_dev = ry - ry.mean()
    denom = np.sqrt(np.sum(x_dev ** 2) * np.sum(y_dev ** 2))
    if denom == 0:
        return float("nan"), float("nan")
    rho = float(np.sum(x_dev * y_dev) / denom)
    rho = float(np.clip(rho, -1.0, 1.0))

    # p-value: t-distribution for n ≥ 10, permutation for smaller samples
    if n >= 10:
        t_stat = rho * np.sqrt(n - 2) / np.sqrt(max(1e-15, 1 - rho ** 2))
        p_value = float(2 * scipy_stats.t.sf(abs(t_stat), df=n - 2))
    else:
        # Permutation-based p-value (exact small-sample)
        rng = np.random.default_rng(seed=42)
        perm_count = 2000
        permuted_rhos = np.empty(perm_count, dtype=float)
        for i in range(perm_count):
            ry_perm = rng.permutation(ry)
            d = ry_perm - ry_perm.mean()
            denom_p = np.sqrt(np.sum(x_dev ** 2) * np.sum(d ** 2))
            if denom_p == 0:
                permuted_rhos[i] = 0.0
            else:
                permuted_rhos[i] = float(np.sum(x_dev * d) / denom_p)
        p_value = float((np.sum(np.abs(permuted_rhos) >= abs(rho)) + 1) / (perm_count + 1))
    return rho, p_value


def _kendall_tau_and_p(x: np.ndarray, y: np.ndarray) -> Tuple[float, float]:
    """Kendall's τ-b with two-tailed p-value. Used when rank ties are too many."""
    x = np.asarray(x, dtype=float)
    y = np.asarray(y, dtype=float)
    mask = ~(np.isnan(x) | np.isnan(y))
    x = x[mask]
    y = y[mask]
    if len(x) < 3:
        return float("nan"), float("nan")
    tau, p_value = scipy_stats.kendalltau(x, y, variant="b")
    return float(tau), float(p_value)


def _tie_ratio(x: np.ndarray) -> float:
    """Return the proportion of repeated values in x (0 = no ties, 1 = all same)."""
    if len(x) == 0:
        return 0.0
    _, counts = np.unique(x, return_counts=True)
    max_count = counts.max()
    return float(max_count) / float(len(x))


def spearman_with_fallback(x: np.ndarray, y: np.ndarray) -> Tuple[float, float, str]:
    """
    Compute Spearman ρ, with Kendall τ-b fallback when there are too many ties.

    Returns (coefficient, p_value, method_used).
    """
    rho, p = _spearman_r_and_p(x, y)
    if np.isnan(rho):
        return float("nan"), float("nan"), "insufficient"

    if _tie_ratio(x) >= KENDALL_TIE_FALLBACK_THRESHOLD or _tie_ratio(y) >= KENDALL_TIE_FALLBACK_THRESHOLD:
        tau, p_tau = _kendall_tau_and_p(x, y)
        if not np.isnan(tau):
            return tau, p_tau, "kendall_tau"
    return rho, p, "spearman"


def correlation_strength(value: float) -> str:
    """Map a |r| value to a strength bucket per the Heat Map spec."""
    if value is None or np.isnan(value):
        return "insufficient"
    a = abs(value)
    if a >= 0.80:
        return "very_strong"
    if a >= 0.60:
        return "strong"
    if a >= 0.30:
        return "moderate"
    return "weak"


def is_significant(p_value: float, alpha: float = 0.05) -> bool:
    """Return True iff p_value is not NaN and is below the alpha threshold."""
    if p_value is None or (isinstance(p_value, float) and np.isnan(p_value)):
        return False
    return float(p_value) < alpha


def compute_spearman_matrix(
    df: pd.DataFrame,
    indicator_map: dict[str, list[str]],
) -> pd.DataFrame:
    """
    For each main indicator and each of its sub-indicators, compute Spearman ρ
    (with Kendall τ-b fallback) and a p-value.

    df must contain columns for both composite indicators and raw sub-indicators.

    Returns a DataFrame with columns:
        main_indicator, sub_indicator, spearman_rho, p_value, strong_correlation,
        method_used, n_samples
    """
    rows = []
    for main_ind, sub_inds in indicator_map.items():
        if main_ind not in df.columns:
            continue
        for sub in sub_inds:
            if sub not in df.columns:
                continue
            valid = df[[main_ind, sub]].dropna()
            x_arr = valid[sub].to_numpy(dtype=float)
            y_arr = valid[main_ind].to_numpy(dtype=float)
            if len(x_arr) < 3:
                rows.append({
                    "main_indicator": main_ind,
                    "sub_indicator": sub,
                    "spearman_rho": None,
                    "p_value": None,
                    "strong_correlation": False,
                    "method_used": "insufficient",
                    "n_samples": int(len(x_arr)),
                })
                continue
            coef, p, method = spearman_with_fallback(x_arr, y_arr)
            rows.append({
                "main_indicator": main_ind,
                "sub_indicator": sub,
                "spearman_rho": round(float(coef), 4) if not np.isnan(coef) else None,
                "p_value": round(float(p), 4) if not np.isnan(p) else None,
                "strong_correlation": abs(coef) >= STRONG_CORRELATION_THRESHOLD if not np.isnan(coef) else False,
                "method_used": method,
                "n_samples": int(len(x_arr)),
            })

    result = pd.DataFrame(rows)
    if not result.empty:
        result["_abs"] = result["spearman_rho"].apply(
            lambda v: -1 if v is None or (isinstance(v, float) and np.isnan(v)) else abs(float(v))
        )
        result = result.sort_values("_abs", ascending=False).drop(columns=["_abs"]).reset_index(drop=True)
    return result
