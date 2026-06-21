"""Scatter plot builder."""

from __future__ import annotations

import pandas as pd
import plotly.express as px

from charts.builders.base import ChartBuilder
from charts.schemas import ChartRequest


class ScatterBuilder(ChartBuilder):
    def _build(self, df: pd.DataFrame, req: ChartRequest) -> px.scatter:
        if df.empty:
            return px.scatter(title=req.title or "No data")
        num_cols = [c for c in df.columns if pd.api.types.is_numeric_dtype(df[c])]
        x_col = num_cols[0] if len(num_cols) >= 1 else df.columns[0]
        y_col = num_cols[1] if len(num_cols) >= 2 else df.columns[-1]
        color_col = req.group_by if req.group_by and req.group_by in df.columns else None
        fig = px.scatter(
            df,
            x=x_col,
            y=y_col,
            color=color_col,
            title=req.title,
        )
        return fig
