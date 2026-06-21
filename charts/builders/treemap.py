"""Treemap builder."""

from __future__ import annotations

import pandas as pd
import plotly.express as px

from charts.builders.base import ChartBuilder
from charts.schemas import ChartRequest


class TreemapBuilder(ChartBuilder):
    def _build(self, df: pd.DataFrame, req: ChartRequest) -> px.treemap:
        if df.empty:
            return px.treemap(title=req.title or "No data")
        cat_cols = [c for c in df.columns if not pd.api.types.is_numeric_dtype(df[c])]
        val_col = _first_numeric(df, exclude=cat_cols) or df.columns[-1]
        path = cat_cols[:2] if len(cat_cols) >= 2 else cat_cols[:1] if cat_cols else [df.columns[0]]
        fig = px.treemap(
            df,
            path=path,
            values=val_col,
            color=val_col,
            color_continuous_scale=["#f0f7f4", "#1F5E47"],
            title=req.title,
        )
        fig.update_traces(textinfo="label+value+percent parent")
        return fig


def _first_numeric(df: pd.DataFrame, exclude: list) -> str | None:
    for c in df.columns:
        if c not in exclude and pd.api.types.is_numeric_dtype(df[c]):
            return c
    return None
