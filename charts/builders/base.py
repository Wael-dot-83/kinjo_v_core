"""Shared behaviour for every chart builder.

Builders turn a DataFrame plus a ChartRequest into a self-contained HTML fragment.
Three concerns are handled here rather than in each of the nine subclasses:

* **Empty input renders a message, never an exception.** Charts are drawn from
  filtered queries that routinely return no rows; a raising builder surfaces as a
  500 on a dashboard tile.
* **Column selection is inferred** when the request does not name columns, so a
  builder works against whatever shape the source query produced.
* **Direction and palette follow the platform.** Arabic is the primary language
  (see CLAUDE.md), so ``lang == "ar"`` renders RTL, and colours come from
  ``charts.colors.PALETTE`` so every chart in the product matches.
"""

from __future__ import annotations

from typing import Optional

import pandas as pd

from charts.colors import PALETTE
from charts.schemas import ChartRequest

_EMPTY_AR = "لا توجد بيانات متاحة"
_EMPTY_EN = "No data available"


class BaseBuilder:
    """Base class for chart builders. Subclasses implement :meth:`_figure`."""

    #: Overridden by subclasses; used only for the default title.
    chart_label = "Chart"

    def render(self, df: pd.DataFrame, request: ChartRequest) -> str:
        """Return an HTML fragment for ``df``. Never raises on bad input."""
        if df is None or df.empty:
            return self._empty_state(request)

        try:
            frame = self._prepare(df, request)
            if frame.empty:
                return self._empty_state(request)
            figure = self._figure(frame, request)
        except Exception:  # noqa: BLE001 — a broken tile must not break the page
            return self._empty_state(request)

        if figure is None:
            return self._empty_state(request)

        figure.update_layout(
            title=self._title(request),
            template="plotly_white",
            colorway=list(PALETTE),
            margin=dict(l=40, r=40, t=60, b=40),
        )
        if self._is_rtl(request):
            # Mirror the plot for Arabic so the reading order matches the page.
            figure.update_layout(
                legend=dict(x=0, xanchor="left"),
                yaxis=dict(side="right"),
            )

        return figure.to_html(full_html=False, include_plotlyjs="cdn")

    # -- hooks ------------------------------------------------------------

    def _figure(self, df: pd.DataFrame, request: ChartRequest):
        raise NotImplementedError

    def _prepare(self, df: pd.DataFrame, request: ChartRequest) -> pd.DataFrame:
        """Apply ``top_n`` if the request asked for it."""
        if request.top_n:
            numeric = self._numeric_col(df)
            if numeric is not None:
                return df.nlargest(request.top_n, numeric)
            return df.head(request.top_n)
        return df

    # -- helpers ----------------------------------------------------------

    @staticmethod
    def _is_rtl(request: ChartRequest) -> bool:
        return (getattr(request, "lang", "ar") or "ar").lower().startswith("ar")

    def _title(self, request: ChartRequest) -> str:
        if request.title:
            return request.title
        source = getattr(request.source, "value", str(request.source))
        return f"{self.chart_label} — {source.replace('_', ' ').title()}"

    def _empty_state(self, request: ChartRequest) -> str:
        message = _EMPTY_AR if self._is_rtl(request) else _EMPTY_EN
        direction = "rtl" if self._is_rtl(request) else "ltr"
        return (
            f'<div class="chart-empty-state" dir="{direction}" '
            f'style="padding:2rem;text-align:center;color:#6b7280;">{message}</div>'
        )

    @staticmethod
    def _numeric_col(df: pd.DataFrame) -> Optional[str]:
        for name in df.columns:
            if pd.api.types.is_numeric_dtype(df[name]):
                return str(name)
        return None

    @staticmethod
    def _time_col(df: pd.DataFrame) -> Optional[str]:
        for name in df.columns:
            if pd.api.types.is_datetime64_any_dtype(df[name]):
                return str(name)
        return None

    @staticmethod
    def _category_col(df: pd.DataFrame) -> Optional[str]:
        for name in df.columns:
            if not pd.api.types.is_numeric_dtype(df[name]) and not pd.api.types.is_datetime64_any_dtype(df[name]):
                return str(name)
        return None

    def _xy(self, df: pd.DataFrame, request: ChartRequest) -> tuple[Optional[str], Optional[str]]:
        """Best-effort (x, y): prefer time then category for x, numeric for y."""
        y = self._numeric_col(df)
        x = self._time_col(df) or self._category_col(df)
        if x is None:
            # All-numeric frame: use the first column for x and a different one for y.
            columns = [str(c) for c in df.columns]
            if columns:
                x = columns[0]
                y = next((c for c in columns[1:] if c != x), y)
        if request.group_by and request.group_by in df.columns:
            x = request.group_by
        return x, y
