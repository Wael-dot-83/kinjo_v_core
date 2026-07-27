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
