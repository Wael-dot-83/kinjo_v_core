"""
Pearson correlation between each sub-indicator and its parent main indicator.
Exact formula from spec:
    r = Σ(xi - x̄)(yi - ȳ) / sqrt(Σ(xi - x̄)² · Σ(yi - ȳ)²)

Flags |r| >= 0.7 as strong correlation.
"""
from __future__ import annotations
import numpy as np
import pandas as pd
from scipy import stats as scipy_stats

STRONG_CORRELATION_THRESHOLD = 0.7


def _pearson_manual(x: np.ndarray, y: np.ndarray) -> tuple[float, float]:
    """
    Exact formula from spec; returns (r, p_value).
    Falls back to scipy for p-value.
    """
    x = x.astype(float)
    y = y.astype(float)
    n = len(x)
    if n < 3:
        return float("nan"), float("nan")

    x_dev = x - x.mean()
    y_dev = y - y.mean()
    num = np.sum(x_dev * y_dev)
    denom = np.sqrt(np.sum(x_dev ** 2) * np.sum(y_dev ** 2))
    if denom == 0:
        return float("nan"), float("nan")

    r = num / denom
    r = float(np.clip(r, -1.0, 1.0))

    # two-tailed p-value using t-distribution
    t_stat = r * np.sqrt(n - 2) / np.sqrt(max(1e-15, 1 - r ** 2))
    p_value = float(2 * scipy_stats.t.sf(abs(t_stat), df=n - 2))
    return r, p_value


def compute_correlation_matrix(df: pd.DataFrame, indicator_map: dict[str, list[str]]) -> pd.DataFrame:
    """
    For each main indicator and each of its sub-indicators compute:
        main_indicator, sub_indicator, r, p_value, strong_correlation

    df must contain columns for both composite indicators and raw sub-indicators.
    Returns a DataFrame sorted by |r| descending.
    """
    rows = []
    for main_ind, sub_inds in indicator_map.items():
        if main_ind not in df.columns:
            continue
        y = df[main_ind].dropna().values
        for sub in sub_inds:
            if sub not in df.columns:
                continue
            # align on common index
            valid = df[[main_ind, sub]].dropna()
            x_arr = valid[sub].values
            y_arr = valid[main_ind].values
            r, p = _pearson_manual(x_arr, y_arr)
            rows.append({
                "main_indicator":    main_ind,
                "sub_indicator":     sub,
                "pearson_r":         round(r, 4) if not np.isnan(r) else None,
                "p_value":           round(p, 4) if not np.isnan(p) else None,
                "strong_correlation": abs(r) >= STRONG_CORRELATION_THRESHOLD if not np.isnan(r) else False,
            })

    result = pd.DataFrame(rows)
    if not result.empty:
        # Some pearson_r values may be None (insufficient data).  Sort by
        # absolute value, putting None entries at the end.
        result["_abs"] = result["pearson_r"].apply(
            lambda v: -1 if v is None or (isinstance(v, float) and np.isnan(v)) else abs(float(v))
        )
        result = result.sort_values("_abs", ascending=False).drop(columns=["_abs"]).reset_index(drop=True)
    return result


def full_correlation_matrix(df: pd.DataFrame) -> pd.DataFrame:
    """
    Returns the pairwise Pearson matrix for all numeric columns as a wide DataFrame.
    """
    num_df = df.select_dtypes(include=[np.number])
    return num_df.corr(method="pearson")
