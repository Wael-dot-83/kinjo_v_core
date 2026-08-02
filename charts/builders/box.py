"""Box plot — spread and outliers, optionally split by a group."""

from __future__ import annotations

import pandas as pd
import plotly.express as px

from charts.builders.base import BaseBuilder
from charts.schemas import ChartRequest


class BoxBuilder(BaseBuilder):
    chart_label = "Spread"

    def _figure(self, df: pd.DataFrame, request: ChartRequest):
        value = self._numeric_col(df)
        if value is None:
            return None
        group = request.group_by if request.group_by in df.columns else self._category_col(df)
        return px.box(df, x=group, y=value) if group else px.box(df, y=value)
