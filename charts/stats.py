"""Statistical profiling for the chart advisor, using pandas only."""

from __future__ import annotations

from typing import Optional

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


def _is_time_col(col: pd.Series) -> bool:
    if pd.api.types.is_datetime64_any_dtype(col):
        return True
    # Handle object and pandas 3+ StringDtype
    if pd.api.types.is_object_dtype(col) or pd.api.types.is_string_dtype(col):
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


# ---------------------------------------------------------------------------
# Series analytics used by the advisor and the builders.
#
# All of these are defensive about short or empty input: charts are rendered from
# whatever a filtered query happens to return, which is routinely 0 or 1 rows, and
# a raising helper there would surface as a 500 on a dashboard tile.
# ---------------------------------------------------------------------------


def compute_trend(series: pd.Series) -> tuple[float, float]:
    """Least-squares slope and R² of a series against its own ordinal index.

    Returns ``(0.0, 0.0)`` for empty or single-point input, and ``r2 = 0.0`` for a
    flat series, where the variance is zero and R² is undefined rather than perfect.
    """
    values = pd.to_numeric(pd.Series(series), errors="coerce").dropna()
    n = len(values)
    if n < 2:
        return 0.0, 0.0

    x = pd.Series(range(n), dtype="float64")
    y = values.reset_index(drop=True).astype("float64")

    x_mean, y_mean = x.mean(), y.mean()
    denominator = ((x - x_mean) ** 2).sum()
    if denominator == 0:
        return 0.0, 0.0

    slope = float(((x - x_mean) * (y - y_mean)).sum() / denominator)
    intercept = float(y_mean - slope * x_mean)

    ss_total = float(((y - y_mean) ** 2).sum())
    if ss_total == 0:
        # Flat series: slope is 0 and R² is undefined; report no explanatory power.
        return slope, 0.0
    ss_residual = float(((y - (slope * x + intercept)) ** 2).sum())
    return slope, 1.0 - (ss_residual / ss_total)


def detect_outliers_iqr(series: pd.Series, factor: float = 1.5) -> pd.Series:
    """Boolean mask of values outside ``[Q1 - factor*IQR, Q3 + factor*IQR]``.

    The mask keeps the input's index and length so callers can filter or highlight
    in place. An all-False mask is returned when the IQR is zero.
    """
    values = pd.to_numeric(pd.Series(series), errors="coerce")
    if values.dropna().empty:
        return pd.Series([False] * len(values), index=values.index, dtype=bool)

    q1, q3 = values.quantile(0.25), values.quantile(0.75)
    iqr = q3 - q1
    if iqr == 0:
        return pd.Series([False] * len(values), index=values.index, dtype=bool)

    mask = (values < q1 - factor * iqr) | (values > q3 + factor * iqr)
    return mask.fillna(False).astype(bool)


def moving_average(series: pd.Series, window: int = 7) -> pd.Series:
    """Rolling mean that preserves the input length.

    ``min_periods=1`` so the leading positions carry a partial average rather than
    NaN — a chart with a blank first week looks like missing data, not smoothing.
    """
    values = pd.to_numeric(pd.Series(series), errors="coerce")
    if len(values) == 0:
        return values
    window = max(1, int(window))
    return values.rolling(window=window, min_periods=1).mean()


def safe_pct_change(series: pd.Series) -> pd.Series:
    """Percentage change with the first element defined as 0.0.

    ``Series.pct_change`` yields NaN for the first element and ``inf`` when the
    previous value is 0. Both render badly, so both are normalised to 0.0.
    """
    values = pd.to_numeric(pd.Series(series), errors="coerce").astype("float64")
    if len(values) == 0:
        return values
    previous = values.shift(1)
    changed = (values - previous) / previous.replace(0, pd.NA) * 100.0
    return changed.replace([float("inf"), float("-inf")], 0.0).fillna(0.0).astype("float64")


def resample_timeseries(
    df: pd.DataFrame,
    time_col: str,
    value_col: str,
    freq: str = "D",
    agg: str = "sum",
) -> pd.DataFrame:
    """Resample ``value_col`` over ``time_col`` at ``freq``, returning a flat frame.

    The time column is returned as a column rather than an index so builders can
    treat every frame the same way.
    """
    if df.empty or time_col not in df.columns or value_col not in df.columns:
        return pd.DataFrame(columns=[time_col, value_col])

    frame = df[[time_col, value_col]].copy()
    frame[time_col] = pd.to_datetime(frame[time_col], errors="coerce")
    frame = frame.dropna(subset=[time_col])
    if frame.empty:
        return pd.DataFrame(columns=[time_col, value_col])

    resampled = frame.set_index(time_col)[value_col].resample(freq).agg(agg)
    return resampled.reset_index()
