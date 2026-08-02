"""Treemap — nested proportions, e.g. governorate → kindergarten → enrolled."""

from __future__ import annotations

import pandas as pd
import plotly.express as px

from charts.builders.base import BaseBuilder
from charts.schemas import ChartRequest


class TreemapBuilder(BaseBuilder):
    chart_label = "Composition"

    def _figure(self, df: pd.DataFrame, request: ChartRequest):
        value = self._numeric_col(df)
        if value is None:
            return None
        path = [str(c) for c in df.columns if c != value and not pd.api.types.is_numeric_dtype(df[c])]
        if not path:
            return None
        return px.treemap(df, path=path, values=value)
