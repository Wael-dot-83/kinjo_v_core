"""
Combined statistics module: runs Pearson + Spearman + OLS, emits a
unified DataFrame suitable for storage in `map_correlation_snapshot` and
`map_regression_snapshot` and for display in the dashboard.

Outputs: r / ρ / τ, p_value, beta_std, se, t_stat, r_squared per
(main_indicator, sub_indicator) pair.
"""
from __future__ import annotations
import io
import logging
import pandas as pd

from .pearson import compute_correlation_matrix
from .spearman import compute_spearman_matrix
from .ols import run_all_regressions

logger = logging.getLogger(__name__)


def compute_full_stats(df: pd.DataFrame, indicator_map: dict[str, list[str]]) -> pd.DataFrame:
    """
    Returns a merged table with columns:
        main_indicator, sub_indicator,
        pearson_r, pearson_p, pearson_strength,
        spearman_rho, spearman_p, spearman_method, spearman_strength,
        beta_std, std_error, t_stat, ols_p_value, high_impact,
        r_squared, adj_r_squared, vif, vif_flag, fit_warning, n_samples

    `indicator_map` is {main_indicator_key: [sub_indicator_key, ...]}.
    """
    pearson_df = compute_correlation_matrix(df, indicator_map)
    spearman_df = compute_spearman_matrix(df, indicator_map)
    ols_results = run_all_regressions(df, indicator_map)

    # Flatten OLS results: each main_indicator now maps to a dict with
    # 'coefficients' (DataFrame) and 'meta' (dict).
    ols_rows: list[pd.DataFrame] = []
    ols_meta: dict[str, dict] = {}
    for main_ind, payload in ols_results.items():
        coef_df = payload["coefficients"]
        ols_meta[main_ind] = payload["meta"]
        if coef_df is None or len(coef_df) == 0:
            continue
        coef_with_main = coef_df.copy()
        coef_with_main["main_indicator"] = main_ind
        ols_rows.append(coef_with_main)

    if ols_rows:
        ols_all = pd.concat(ols_rows, ignore_index=True)
        ols_all = ols_all.rename(columns={"p_value": "ols_p_value"})
    else:
        ols_all = pd.DataFrame()

    # Start from Pearson as the base frame; merge Spearman and OLS.
    if not pearson_df.empty:
        pearson_df = pearson_df.copy()
        pearson_df["pearson_strength"] = pearson_df["strong_correlation"]
        pearson_df = pearson_df.rename(columns={"p_value": "pearson_p"})
        # normalize n_samples column (pearson) → n_samples_pearson
        if "n_samples" in pearson_df.columns:
            pearson_df = pearson_df.rename(columns={"n_samples": "n_samples_pearson"})

    merged = pearson_df
    if not spearman_df.empty:
        spearman_df = spearman_df.copy()
        spearman_df = spearman_df.rename(columns={
            "p_value": "spearman_p",
            "strong_correlation": "spearman_strength",
            "method_used": "spearman_method",
            "n_samples": "n_samples_spearman",
        })
        # drop duplicate n_samples columns
        if "n_samples" in merged.columns and "n_samples_spearman" in spearman_df.columns:
            merged = merged.drop(columns=["n_samples"])
        if "n_samples" in spearman_df.columns and "n_samples_spearman" not in spearman_df.columns:
            spearman_df = spearman_df.rename(columns={"n_samples": "n_samples_spearman"})
        merged = merged.merge(
            spearman_df[["main_indicator", "sub_indicator", "spearman_rho",
                          "spearman_p", "spearman_method", "spearman_strength",
                          "n_samples_spearman"]],
            on=["main_indicator", "sub_indicator"],
            how="outer",
        )
    if not ols_all.empty:
        ols_cols = ["main_indicator", "sub_indicator", "beta_std", "std_error",
                    "t_stat", "ols_p_value", "high_impact", "vif", "vif_flag"]
        if "r_squared" in ols_all.columns:
            ols_cols.append("r_squared")
        if "adj_r_squared" in ols_all.columns:
            ols_cols.append("adj_r_squared")
        merged = merged.merge(
            ols_all[[c for c in ols_cols if c in ols_all.columns]],
            on=["main_indicator", "sub_indicator"],
            how="outer",
        )
        # Attach fit_warning and ridge_used from the per-main meta
        for main_ind, meta in ols_meta.items():
            mask = merged["main_indicator"] == main_ind
            if "r_squared" in meta and mask.any():
                # r_squared is already in the per-row OLS output; nothing to do.
                pass
            if "fit_warning" in meta and mask.any():
                if "fit_warning" not in merged.columns:
                    merged["fit_warning"] = None
                merged.loc[mask, "fit_warning"] = meta["fit_warning"]

    if merged.empty:
        return merged

    # Reorder columns for readability
    preferred_order = [
        "main_indicator", "sub_indicator",
        "pearson_r", "pearson_p", "pearson_strength",
        "spearman_rho", "spearman_p", "spearman_method", "spearman_strength",
        "beta_std", "std_error", "t_stat", "ols_p_value", "high_impact",
        "r_squared", "adj_r_squared", "vif", "vif_flag", "fit_warning",
        "n_samples",
    ]
    cols = [c for c in preferred_order if c in merged.columns]
    other = [c for c in merged.columns if c not in cols]
    return merged[cols + other].sort_values(
        "main_indicator",
        key=lambda s: s.map({k: i for i, k in enumerate(indicator_map.keys())}).fillna(len(indicator_map)),
    ).reset_index(drop=True)


def stats_to_csv(stats_df: pd.DataFrame) -> str:
    """Serialize stats DataFrame to CSV string."""
    buf = io.StringIO()
    stats_df.to_csv(buf, index=False)
    return buf.getvalue()


def rolling_health_alert_hotspot(
    df: pd.DataFrame,
    window_days: int = 3,
    pct_increase_threshold: float = 0.50,
) -> list[dict]:
    """
    Detects admin units where absences_health_alerts increased > threshold%
    over the rolling window vs the same-length baseline preceding it.

    Returns list of {admin_id, date, current_avg, baseline_avg, pct_change}.
    """
    # The computed frame only carries the sub-indicators named in INDICATOR_MAP,
    # which deliberately excludes absences_health_alerts ("no defensible source").
    # Callers may therefore hand us a frame without it; that is a data-coverage
    # gap, not a server fault, so report no hotspots instead of raising KeyError.
    if "absences_health_alerts" not in df.columns:
        logger.warning(
            "rolling_health_alert_hotspot: no absences_health_alerts column in input; "
            "returning no hotspots"
        )
        return []

    df = df.sort_values(["admin_id", "date"]).copy()
    df["date"] = pd.to_datetime(df["date"])
    hotspots = []

    for admin_id, group in df.groupby("admin_id"):
        group = group.set_index("date")["absences_health_alerts"].sort_index()
        if len(group) < window_days * 2:
            continue
        dates = sorted(group.index)
        for i in range(window_days, len(dates)):
            window_dates = dates[i - window_days: i]
            baseline_dates = dates[max(0, i - window_days * 2): i - window_days]
            if not baseline_dates:
                continue
            current_avg = group.loc[window_dates].mean()
            baseline_avg = group.loc[baseline_dates].mean()
            if baseline_avg == 0:
                continue
            pct_change = (current_avg - baseline_avg) / baseline_avg
            if pct_change > pct_increase_threshold:
                hotspots.append({
                    "admin_id":     admin_id,
                    "date":         dates[i].strftime("%Y-%m-%d"),
                    "current_avg":  round(float(current_avg), 2),
                    "baseline_avg": round(float(baseline_avg), 2),
                    "p_change":   round(float(pct_change * 100), 1),
                })
    return hotspots
