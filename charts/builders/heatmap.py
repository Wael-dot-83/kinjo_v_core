"""Heatmap / correlation matrix builder."""

from __future__ import annotations

import numpy as np
import pandas as pd
import plotly.express as px
import plotly.graph_objects as go

from charts.builders.base import ChartBuilder
from charts.colors import diverging_colorscale
from charts.schemas import ChartRequest


class HeatmapBuilder(ChartBuilder):
    def _build(self, df: pd.DataFrame, req: ChartRequest) -> go.Figure:
        if df.empty:
            return go.Figure(layout={"title": req.title or "No data"})

        num_cols = [c for c in df.columns if pd.api.types.is_numeric_dtype(df[c])]

        if len(num_cols) >= 2:
            corr = df[num_cols].corr(method="pearson").round(2)
            z = corr.values
            labels = list(corr.columns)
            fig = go.Figure(go.Heatmap(
                z=z,
                x=labels,
                y=labels,
                colorscale=diverging_colorscale(),
                zmid=0,
                text=np.round(z, 2),
                texttemplate="%{text}",
                showscale=True,
            ))
        else:
            # Pivot on first two non-numeric columns as a frequency heatmap
            cat_cols = [c for c in df.columns if not pd.api.types.is_numeric_dtype(df[c])]
            if len(cat_cols) >= 2:
                pivot = df.groupby([cat_cols[0], cat_cols[1]]).size().unstack(fill_value=0)
                fig = px.imshow(
                    pivot,
                    color_continuous_scale=diverging_colorscale(),
                    title=req.title,
                    aspect="auto",
                )
            else:
                fig = go.Figure(layout={"title": req.title or "Insufficient columns for heatmap"})

        if req.title:
            fig.update_layout(title_text=req.title)
        return fig
