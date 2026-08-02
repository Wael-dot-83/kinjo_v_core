"""Pie chart — share of a whole across a small number of categories."""

from __future__ import annotations

import pandas as pd
import plotly.express as px

from charts.builders.base import BaseBuilder
from charts.schemas import ChartRequest


class PieBuilder(BaseBuilder):
    chart_label = "Distribution"

    def _figure(self, df: pd.DataFrame, request: ChartRequest):
        names = self._category_col(df)
        values = self._numeric_col(df)
        if names is None or values is None:
            return None
        return px.pie(df, names=names, values=values, hole=0.35)
