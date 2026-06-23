"""Box plot builder."""

from __future__ import annotations

import pandas as pd
import plotly.express as px

from charts.builders.base import ChartBuilder
from charts.schemas import ChartRequest


class BoxBuilder(ChartBuilder):
    def _build(self, df: pd.DataFrame, req: ChartRequest) -> px.box:
        if df.empty:
            return px.box(title=req.title or "No data")
        num_cols = [c for c in df.columns if pd.api.types.is_numeric_dtype(df[c])]
        y_col = num_cols[0] if num_cols else df.columns[-1]
        x_col = req.group_by if req.group_by and req.group_by in df.columns else None
        fig = px.box(
            df,
            x=x_col,
            y=y_col,
            points="outliers",
            title=req.title,
            color=x_col,
        )
        return fig
