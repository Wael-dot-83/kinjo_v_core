"""Histogram — distribution of a single numeric column."""

from __future__ import annotations

import pandas as pd
import plotly.express as px

from charts.builders.base import BaseBuilder
from charts.schemas import ChartRequest


class HistogramBuilder(BaseBuilder):
    chart_label = "Distribution"

    def _figure(self, df: pd.DataFrame, request: ChartRequest):
        value = self._numeric_col(df)
        if value is None:
            return None
        return px.histogram(df, x=value)
