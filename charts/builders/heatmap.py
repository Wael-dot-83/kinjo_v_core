"""Heatmap — correlation between the numeric columns of a frame.

Named for the chart type, not for the geographic heat map feature
(`heatmap/` package), which is unrelated.
"""

from __future__ import annotations

import pandas as pd
import plotly.express as px

from charts.builders.base import BaseBuilder
from charts.schemas import ChartRequest


class HeatmapBuilder(BaseBuilder):
    chart_label = "Correlation"

    def _figure(self, df: pd.DataFrame, request: ChartRequest):
        numeric = df.select_dtypes(include="number")
        if numeric.shape[1] < 2:
            return None
        matrix = numeric.corr()
        return px.imshow(
            matrix,
            x=[str(c) for c in matrix.columns],
            y=[str(i) for i in matrix.index],
            zmin=-1,
            zmax=1,
            text_auto=".2f",
            color_continuous_scale="RdBu_r",
        )
