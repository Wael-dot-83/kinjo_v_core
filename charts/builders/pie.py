"""Pie / donut chart builder."""

from __future__ import annotations

import pandas as pd
import plotly.express as px

from charts.builders.base import ChartBuilder
from charts.schemas import ChartRequest


class PieBuilder(ChartBuilder):
    def _build(self, df: pd.DataFrame, req: ChartRequest) -> px.pie:
        if df.empty:
            return px.pie(title=req.title or "No data")
        name_col = df.columns[0]
        val_col = _first_numeric(df, exclude=[name_col]) or df.columns[-1]
        fig = px.pie(
            df,
            names=name_col,
            values=val_col,
            hole=0.45,  # cleaner donut style
            title=req.title,
        )
        fig.update_traces(
            textposition="inside", 
            textinfo="percent+label",
            insidetextorientation="radial"
        )
        return fig


def _first_numeric(df: pd.DataFrame, exclude: list) -> str | None:
    for c in df.columns:
        if c not in exclude and pd.api.types.is_numeric_dtype(df[c]):
            return c
    return None
