"""
Standardized OLS regression for sub-indicators → main indicator.

Mathematical form (per the Heat Map tech spec §5.3.1):
    β = (XᵀX)⁻¹ Xᵀy   (on standardized X and y)
    SE(β) from covariance matrix
    t = β / SE
    R² = 1 − SSres / SStot

Flags |β_j| >= 0.20 as high-impact.

VIF (Variance Inflation Factor) is computed per sub-indicator to detect
multicollinearity; VIF > 10 is a red flag, VIF > 5 is a warning.
"""
from __future__ import annotations
from typing import Dict, List, Tuple

import numpy as np
import pandas as pd
from scipy import stats as scipy_stats

HIGH_IMPACT_THRESHOLD = 0.20
VIF_WARNING_THRESHOLD = 5.0
VIF_RED_FLAG_THRESHOLD = 10.0
RIDGE_LAMBDA = 0.10


def _standardize(arr: np.ndarray) -> np.ndarray:
    std = arr.std(ddof=1)
    return (arr - arr.mean()) / std if std > 0 else np.zeros_like(arr, dtype=float)


def _vif(X_std: np.ndarray, j: int) -> float:
    """
    Compute the Variance Inflation Factor for column j of an already-standardized
    design matrix.

    VIF_j = 1 / (1 − R²_j)
    where R²_j is the R² of regressing X[:, j] on the other columns.
    """
    k = X_std.shape[1]
    if k < 2:
        return 1.0
    y_j = X_std[:, j]
    others = np.delete(X_std, j, axis=1)
    # Regress y_j on the other columns
    XtX = others.T @ others
    Xty = others.T @ y_j
    try:
        beta = np.linalg.solve(XtX, Xty)
    except np.linalg.LinAlgError:
        beta = np.linalg.lstsq(XtX, Xty, rcond=None)[0]
    y_hat = others @ beta
    ss_res = float(np.sum((y_j - y_hat) ** 2))
    ss_tot = float(np.sum((y_j - y_j.mean()) ** 2))
    if ss_tot == 0:
        return 1.0
    r2 = 1.0 - ss_res / ss_tot
    if r2 >= 1.0:
        return float("inf")
    return 1.0 / (1.0 - r2)


def ols_standardized(
    X_df: pd.DataFrame,
    y_series: pd.Series,
    use_ridge: bool = False,
) -> Tuple[pd.DataFrame, Dict[str, float]]:
    """
    Run standardized OLS: standardize X and y, compute β = (XᵀX)⁻¹ Xᵀy.

    Parameters
    ----------
    X_df : DataFrame of sub-indicator columns.
    y_series : Series of the main indicator.
    use_ridge : when True, regularize with λI to handle k+1 ≥ n.

    Returns
    -------
    (coefficients_df, model_meta) where
        coefficients_df has columns:
            sub_indicator, beta_std, std_error, t_stat, p_value,
            high_impact, vif, vif_flag
        model_meta has:
            r_squared, adj_r_squared, n_samples, k_predictors, df_resid,
            ridge_used, condition_number
    """
    # Align on common non-null index
    valid_idx = X_df.index.intersection(y_series.dropna().index)
    valid_idx = valid_idx.intersection(X_df.dropna().index)
    X_raw = X_df.loc[valid_idx].values.astype(float)
    y_raw = y_series.loc[valid_idx].values.astype(float)

    n, k = X_raw.shape

    if n < k + 2 and not use_ridge:
        # Fall back to ridge automatically
        use_ridge = True

    if n < 3:
        empty = pd.DataFrame(columns=[
            "sub_indicator", "beta_std", "std_error", "t_stat", "p_value",
            "high_impact", "vif", "vif_flag",
        ])
        return empty, {"r_squared": 0.0, "n_samples": int(n), "k_predictors": int(k),
                        "df_resid": max(0, n - k - 1), "ridge_used": False,
                        "condition_number": float("inf")}

    # Standardize
    X_std = np.column_stack([_standardize(X_raw[:, j]) for j in range(k)])
    y_std = _standardize(y_raw)

    # β = (XᵀX + λI)⁻¹ Xᵀy  (ridge if use_ridge else OLS)
    XtX = X_std.T @ X_std
    Xty = X_std.T @ y_std
    if use_ridge:
        XtX = XtX + RIDGE_LAMBDA * np.eye(k)
    try:
        cond = float(np.linalg.cond(XtX))
    except np.linalg.LinAlgError:
        cond = float("inf")
    try:
        beta = np.linalg.solve(XtX, Xty)
    except np.linalg.LinAlgError:
        beta = np.linalg.lstsq(XtX, Xty, rcond=None)[0]

    # Standard errors
    y_hat = X_std @ beta
    residuals = y_std - y_hat
    df_resid = max(n - k - 1, 1)
    s2 = float(np.dot(residuals, residuals)) / df_resid
    try:
        cov_matrix = s2 * np.linalg.inv(XtX)
        # A near-singular XtX can yield tiny negative variance estimates on the
        # diagonal (numerical error). sqrt of those is meaningless — treat them as
        # unavailable (nan) explicitly rather than taking sqrt of a negative, which
        # both raises a RuntimeWarning and produces the same nan. Downstream already
        # maps se <= 0 to nan.
        diag = np.diag(cov_matrix)
        se = np.sqrt(np.where(diag >= 0.0, diag, np.nan))
    except np.linalg.LinAlgError:
        se = np.full(k, np.nan)

    t_stats = beta / np.where(se > 0, se, np.nan)
    p_values = 2 * scipy_stats.t.sf(np.abs(t_stats), df=df_resid)

    # R² and adjusted R²
    ss_res = float(np.sum(residuals ** 2))
    ss_tot = float(np.sum((y_std - y_std.mean()) ** 2))
    r_squared = 1.0 - ss_res / ss_tot if ss_tot > 0 else 0.0
    r_squared = max(0.0, min(1.0, r_squared))
    adj_r_squared = 1.0 - (1.0 - r_squared) * (n - 1) / df_resid if df_resid > 0 else 0.0

    # VIF per column
    vifs = []
    for j in range(k):
        v = _vif(X_std, j)
        vifs.append(v)

    rows = []
    for j, col in enumerate(X_df.columns):
        vif_val = vifs[j]
        if np.isinf(vif_val) or vif_val >= VIF_RED_FLAG_THRESHOLD:
            vif_flag = "red"
        elif vif_val >= VIF_WARNING_THRESHOLD:
            vif_flag = "warning"
        else:
            vif_flag = "ok"
        rows.append({
            "sub_indicator": col,
            "beta_std": round(float(beta[j]), 4),
            "std_error": round(float(se[j]), 4) if not np.isnan(se[j]) else None,
            "t_stat": round(float(t_stats[j]), 4) if not np.isnan(t_stats[j]) else None,
            "p_value": round(float(p_values[j]), 4) if not np.isnan(p_values[j]) else None,
            "high_impact": abs(float(beta[j])) >= HIGH_IMPACT_THRESHOLD,
            "vif": round(float(vif_val), 4) if not np.isinf(vif_val) else None,
            "vif_flag": vif_flag,
        })
    coef_df = pd.DataFrame(rows).sort_values("beta_std", key=lambda s: s.abs(), ascending=False)

    meta = {
        "r_squared": round(r_squared, 4),
        "adj_r_squared": round(adj_r_squared, 4),
        "n_samples": int(n),
        "k_predictors": int(k),
        "df_resid": int(df_resid),
        "ridge_used": use_ridge,
        "condition_number": round(cond, 4) if not np.isinf(cond) else None,
        "fit_warning": "weak fit" if r_squared < 0.30 else None,
    }
    return coef_df, meta


def run_all_regressions(df: pd.DataFrame, indicator_map: dict[str, list[str]]) -> Dict[str, dict]:
    """
    Run standardized OLS for every (main indicator, sub-indicators) pair.

    Returns {main_indicator: {"coefficients": DataFrame, "meta": dict}}.
    """
    results: Dict[str, dict] = {}
    for main_ind, sub_inds in indicator_map.items():
        available_subs = [s for s in sub_inds if s in df.columns]
        if main_ind not in df.columns or not available_subs:
            continue
        X_df = df[available_subs].copy()
        y_series = df[main_ind].copy()
        coef_df, meta = ols_standardized(X_df, y_series)
        results[main_ind] = {"coefficients": coef_df, "meta": meta}
    return results


def priority_score(coefficients: pd.DataFrame, current_values: pd.Series, network_mean: pd.Series, network_std: pd.Series) -> pd.DataFrame:
    """
    Compute the priority score per governorate:

        priority = Σⱼ |βⱼ| × |xⱼ − x̄_net| / σ_netⱼ

    Parameters
    ----------
    coefficients : output of `ols_standardized` (must have `sub_indicator`, `beta_std`).
    current_values : the governorate's current values for the sub-indicators in the model.
    network_mean  : the network-wide mean for each sub-indicator.
    network_std   : the network-wide std for each sub-indicator.

    Returns
    -------
    DataFrame with sub_indicator, beta_std, deviation, contribution, priority_score (0-100).
    """
    rows = []
    for _, r in coefficients.iterrows():
        sub = r["sub_indicator"]
        beta = abs(float(r["beta_std"]))
        x = float(current_values.get(sub, 0))
        mu = float(network_mean.get(sub, 0))
        sd = float(network_std.get(sub, 1))
        z = (x - mu) / sd if sd > 0 else 0.0
        deviation = abs(z)
        contribution = beta * deviation
        rows.append({
            "sub_indicator": sub,
            "beta_std": beta,
            "deviation_z": round(deviation, 4),
            "contribution": round(contribution, 4),
        })
    if not rows:
        return pd.DataFrame()
    df = pd.DataFrame(rows)
    total = df["contribution"].sum()
    df["priority_pct"] = (df["contribution"] / total * 100).round(2) if total > 0 else 0
    return df
