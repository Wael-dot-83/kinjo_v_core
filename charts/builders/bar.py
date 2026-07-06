"""Bar chart builder."""

from __future__ import annotations

import pandas as pd
import plotly.express as px

from charts.builders.base import ChartBuilder
from charts.schemas import ChartRequest


class BarBuilder(ChartBuilder):
    def _build(self, df: pd.DataFrame, req: ChartRequest) -> px.bar:
        if df.empty:
            return px.bar(title=req.title or "No data")
        x_col = df.columns[0]
        y_col = _first_numeric(df, exclude=[x_col]) or df.columns[-1]
        color_col = req.group_by if req.group_by and req.group_by in df.columns else None
        if req.top_n:
            df = df.nlargest(req.top_n, y_col)
        fig = px.bar(
            df,
            x=x_col,
            y=y_col,
            color=color_col,
            title=req.title,
            text_auto=True,
        )
        fig.update_traces(textposition="auto")
        if len(df) > 6:
            fig.update_xaxes(tickangle=-45)
        return fig


def _first_numeric(df: pd.DataFrame, exclude: list) -> str | None:
    for c in df.columns:
        if c not in exclude and pd.api.types.is_numeric_dtype(df[c]):
            return c
    return None
