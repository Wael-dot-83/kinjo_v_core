"""Scatter plot — relationship between two numeric columns."""

from __future__ import annotations

import pandas as pd
import plotly.express as px

from charts.builders.base import BaseBuilder
from charts.schemas import ChartRequest


class ScatterBuilder(BaseBuilder):
    chart_label = "Relationship"

    def _figure(self, df: pd.DataFrame, request: ChartRequest):
        numeric = [str(c) for c in df.columns if pd.api.types.is_numeric_dtype(df[c])]
        if len(numeric) < 2:
            return None
        color = request.group_by if request.group_by in df.columns else None
        return px.scatter(df, x=numeric[0], y=numeric[1], color=color)
