"""Line chart builder."""

from __future__ import annotations

import pandas as pd
import plotly.express as px

from charts.builders.base import ChartBuilder
from charts.schemas import ChartRequest


class LineBuilder(ChartBuilder):
    def _build(self, df: pd.DataFrame, req: ChartRequest) -> px.line:
        if df.empty:
            return px.line(title=req.title or "No data")
        date_col = _first_col(df, "date") or df.columns[0]
        val_col = _first_numeric(df, exclude=[date_col]) or df.columns[-1]
        color_col = req.group_by if req.group_by and req.group_by in df.columns else None
        fig = px.line(
            df,
            x=date_col,
            y=val_col,
            color=color_col,
            markers=True,
            title=req.title,
        )
        fig.update_traces(line_width=2.5)
        return fig


def _first_col(df: pd.DataFrame, hint: str) -> str | None:
    if hint in ("date", "time"):
        for c in df.columns:
            if pd.api.types.is_datetime64_any_dtype(df[c]):
                return c
            is_str = pd.api.types.is_object_dtype(df[c]) or pd.api.types.is_string_dtype(df[c])
            if is_str and not pd.api.types.is_numeric_dtype(df[c]):
                sample = df[c].dropna().head(5).astype(str)
                if len(sample) > 0 and sample.str.match(r"^\d{4}-\d{2}-\d{2}").all():
                    return c

    for c in df.columns:
        if hint in str(c).lower():
            return c
    return None


def _first_numeric(df: pd.DataFrame, exclude: list) -> str | None:
    for c in df.columns:
        if c not in exclude and pd.api.types.is_numeric_dtype(df[c]):
            return c
    return None
