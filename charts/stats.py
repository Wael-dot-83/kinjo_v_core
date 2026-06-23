"""Statistical analysis helpers using only pandas + numpy (no scipy/statsmodels)."""

from __future__ import annotations

from typing import Any, Dict, List, Optional, Tuple
import math

import numpy as np
import pandas as pd

from charts.schemas import DataProfile


def profile_dataframe(df: pd.DataFrame) -> DataProfile:
    """Derive a DataProfile from an arbitrary DataFrame."""
    if df.empty:
        return DataProfile(row_count=0)

    time_cols = [c for c in df.columns if _is_time_col(df[c])]
    cat_cols = [c for c in df.columns if _is_category_col(df[c])]
    num_cols = [c for c in df.columns if pd.api.types.is_numeric_dtype(df[c])]

    cardinality = {c: int(df[c].nunique()) for c in cat_cols}
    n_categories = sum(cardinality.values())

    time_span: Optional[int] = None
    if time_cols:
        ts = pd.to_datetime(df[time_cols[0]], errors="coerce").dropna()
        if len(ts) >= 2:
            time_span = (ts.max() - ts.min()).days

    skewness: Optional[float] = None
    has_negative = False
    if num_cols:
        primary_num = df[num_cols[-1]].dropna()
        if len(primary_num) >= 3:
            skewness = float(primary_num.skew())
        has_negative = bool((primary_num < 0).any())

    return DataProfile(
        row_count=len(df),
        has_time_series=bool(time_cols),
        has_categories=bool(cat_cols),
        has_numeric=bool(num_cols),
        n_categories=len(cat_cols),
        n_numeric_cols=len(num_cols),
        cardinality=cardinality,
        time_span_days=time_span,
        skewness=skewness,
        has_negative=has_negative,
    )


def compute_trend(series: pd.Series) -> Tuple[float, float]:
    """Return (slope, r_squared) for a numeric series via OLS (numpy only)."""
    y = series.dropna().values.astype(float)
    if len(y) < 2:
        return 0.0, 0.0
    x = np.arange(len(y), dtype=float)
    x_mean, y_mean = x.mean(), y.mean()
    ss_xy = float(((x - x_mean) * (y - y_mean)).sum())
    ss_xx = float(((x - x_mean) ** 2).sum())
    slope = ss_xy / ss_xx if ss_xx != 0 else 0.0
    y_hat = slope * (x - x_mean) + y_mean
    ss_res = float(((y - y_hat) ** 2).sum())
    ss_tot = float(((y - y_mean) ** 2).sum())
    r2 = 1.0 - (ss_res / ss_tot) if ss_tot != 0 else 0.0
    return slope, max(0.0, min(1.0, r2))


def detect_outliers_iqr(series: pd.Series) -> pd.Series:
    """Boolean mask of outliers using IQR (1.5× rule)."""
    q1 = series.quantile(0.25)
    q3 = series.quantile(0.75)
    iqr = q3 - q1
    return (series < q1 - 1.5 * iqr) | (series > q3 + 1.5 * iqr)


def compute_correlation_matrix(df: pd.DataFrame, cols: List[str]) -> pd.DataFrame:
    """Pearson correlation matrix for the given numeric columns."""
    numeric = df[cols].select_dtypes(include="number")
    return numeric.corr(method="pearson")


def resample_timeseries(
    df: pd.DataFrame,
    date_col: str,
    value_col: str,
    freq: str = "ME",
    agg: str = "sum",
) -> pd.DataFrame:
    """Resample a date column to the given pandas frequency alias."""
    df = df.copy()
    df[date_col] = pd.to_datetime(df[date_col], errors="coerce")
    df = df.dropna(subset=[date_col]).set_index(date_col)
    resampled = df[[value_col]].resample(freq).agg(agg).reset_index()
    return resampled


def safe_pct_change(series: pd.Series) -> pd.Series:
    """Percentage change with NaN fill for the first element."""
    return series.pct_change().fillna(0.0) * 100


def _is_time_col(col: pd.Series) -> bool:
    if pd.api.types.is_datetime64_any_dtype(col):
        return True
    # Handle object and pandas 3+ StringDtype
    if pd.api.types.is_object_dtype(col) or pd.api.types.is_string_dtype(col):
        if pd.api.types.is_numeric_dtype(col):
            return False
        sample = col.dropna().head(5).astype(str)
        return sample.str.match(r"^\d{4}-\d{2}-\d{2}").all() if len(sample) > 0 else False
    return False


def _is_category_col(col: pd.Series) -> bool:
    if isinstance(col.dtype, pd.CategoricalDtype):
        return True
    # Pandas 3+ uses StringDtype instead of object for string columns
    is_str = pd.api.types.is_object_dtype(col) or pd.api.types.is_string_dtype(col)
    if is_str and not pd.api.types.is_numeric_dtype(col):
        return col.nunique() < max(50, len(col) * 0.5)
    return False


def moving_average(series: pd.Series, window: int = 7) -> pd.Series:
    """Simple rolling mean — NaNs padded with first valid value."""
    return series.rolling(window=window, min_periods=1).mean()
