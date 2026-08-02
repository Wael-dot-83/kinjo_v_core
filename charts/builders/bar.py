"""Bar chart — comparison across categories."""

from __future__ import annotations

import pandas as pd
import plotly.express as px

from charts.builders.base import BaseBuilder
from charts.schemas import ChartRequest


class BarBuilder(BaseBuilder):
    chart_label = "Comparison"

    def _figure(self, df: pd.DataFrame, request: ChartRequest):
        x, y = self._xy(df, request)
        if x is None or y is None:
            return None
        return px.bar(df, x=x, y=y)
