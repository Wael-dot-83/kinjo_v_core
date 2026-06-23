"""Funnel chart builder."""

from __future__ import annotations

import pandas as pd
import plotly.express as px

from charts.builders.base import ChartBuilder
from charts.schemas import ChartRequest


class FunnelBuilder(ChartBuilder):
    def _build(self, df: pd.DataFrame, req: ChartRequest) -> px.funnel:
        if df.empty:
            return px.funnel(title=req.title or "No data")
        x_col = df.columns[0]
        y_col = _first_numeric(df, exclude=[x_col]) or df.columns[-1]
        fig = px.funnel(
            df,
            x=y_col,
            y=x_col,
            title=req.title,
        )
        return fig


def _first_numeric(df: pd.DataFrame, exclude: list) -> str | None:
    for c in df.columns:
        if c not in exclude and pd.api.types.is_numeric_dtype(df[c]):
            return c
    return None
