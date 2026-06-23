"""Abstract base class for all chart builders."""

from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Any, Optional

import pandas as pd
import plotly.io as pio

from charts.colors import PLOTLY_LAYOUT_DEFAULTS
from charts.schemas import ChartRequest


class ChartBuilder(ABC):
    """Build a Plotly figure from a prepared DataFrame and return HTML."""

    def render(self, df: pd.DataFrame, req: ChartRequest) -> str:
        """Build figure and return full-html fragment suitable for embedding."""
        fig = self._build(df, req)
        # Merge brand layout defaults with any figure-specific overrides
        fig.update_layout(**{k: v for k, v in PLOTLY_LAYOUT_DEFAULTS.items()
                             if k not in ("colorway",)})
        fig.update_layout(colorway=PLOTLY_LAYOUT_DEFAULTS["colorway"])
        if req.title:
            fig.update_layout(title_text=req.title)
        return pio.to_html(
            fig,
            full_html=False,
            include_plotlyjs=False,
            config={"responsive": True, "displayModeBar": True, "displaylogo": False},
        )

    @abstractmethod
    def _build(self, df: pd.DataFrame, req: ChartRequest) -> Any:
        """Return a plotly.graph_objects.Figure."""
