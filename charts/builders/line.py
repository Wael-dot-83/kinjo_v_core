"""Line chart — trends over a time axis."""

from __future__ import annotations

import pandas as pd
import plotly.express as px

from charts.builders.base import BaseBuilder
from charts.schemas import ChartRequest


class LineBuilder(BaseBuilder):
    chart_label = "Trend"

    def _figure(self, df: pd.DataFrame, request: ChartRequest):
        x, y = self._xy(df, request)
        if x is None or y is None:
            return None
        color = request.group_by if request.group_by in df.columns and request.group_by != x else None
        return px.line(df, x=x, y=y, color=color, markers=True)
