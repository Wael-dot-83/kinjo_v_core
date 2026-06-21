"""Histogram builder."""

from __future__ import annotations

import pandas as pd
import plotly.express as px

from charts.builders.base import ChartBuilder
from charts.schemas import ChartRequest


class HistogramBuilder(ChartBuilder):
    def _build(self, df: pd.DataFrame, req: ChartRequest) -> px.histogram:
        if df.empty:
            return px.histogram(title=req.title or "No data")
        num_cols = [c for c in df.columns if pd.api.types.is_numeric_dtype(df[c])]
        x_col = num_cols[0] if num_cols else df.columns[0]
        color_col = req.group_by if req.group_by and req.group_by in df.columns else None
        fig = px.histogram(
            df,
            x=x_col,
            color=color_col,
            nbins=min(30, max(5, len(df) // 5)),
            title=req.title,
            marginal="box",
        )
        fig.update_layout(bargap=0.05)
        return fig
