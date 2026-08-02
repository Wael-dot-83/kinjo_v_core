"""Funnel — stage-by-stage drop-off, e.g. an enrollment pipeline."""

from __future__ import annotations

import pandas as pd
import plotly.express as px

from charts.builders.base import BaseBuilder
from charts.schemas import ChartRequest


class FunnelBuilder(BaseBuilder):
    chart_label = "Funnel"

    def _figure(self, df: pd.DataFrame, request: ChartRequest):
        stage = self._category_col(df)
        value = self._numeric_col(df)
        if stage is None or value is None:
            return None
        ordered = df.sort_values(value, ascending=False)
        return px.funnel(ordered, x=value, y=stage)

    def _prepare(self, df: pd.DataFrame, request: ChartRequest) -> pd.DataFrame:
        # A funnel's stages are its meaning; truncating to top_n would misrepresent it.
        return df
