"""Chart builders, one per :class:`~charts.schemas.ChartType`.

Every builder exposes ``render(df, ChartRequest) -> str`` and returns a
self-contained HTML fragment. Look up a builder with :func:`get_builder` rather
than importing the classes directly, so a new chart type only has to be
registered in one place.
"""

from __future__ import annotations

from charts.builders.bar import BarBuilder
from charts.builders.base import BaseBuilder
from charts.builders.box import BoxBuilder
from charts.builders.funnel import FunnelBuilder
from charts.builders.heatmap import HeatmapBuilder
from charts.builders.histogram import HistogramBuilder
from charts.builders.line import LineBuilder
from charts.builders.pie import PieBuilder
from charts.builders.scatter import ScatterBuilder
from charts.builders.treemap import TreemapBuilder
from charts.schemas import ChartType

_BUILDERS: dict[ChartType, type[BaseBuilder]] = {
    ChartType.LINE: LineBuilder,
    ChartType.BAR: BarBuilder,
    ChartType.SCATTER: ScatterBuilder,
    ChartType.PIE: PieBuilder,
    ChartType.HISTOGRAM: HistogramBuilder,
    ChartType.BOX: BoxBuilder,
    ChartType.HEATMAP: HeatmapBuilder,
    ChartType.FUNNEL: FunnelBuilder,
    ChartType.TREEMAP: TreemapBuilder,
}

__all__ = [
    "BaseBuilder",
    "BarBuilder",
    "BoxBuilder",
    "FunnelBuilder",
    "HeatmapBuilder",
    "HistogramBuilder",
    "LineBuilder",
    "PieBuilder",
    "ScatterBuilder",
    "TreemapBuilder",
    "get_builder",
]


def get_builder(chart_type: ChartType | str) -> BaseBuilder:
    """Return a builder instance for ``chart_type``.

    Accepts the enum or its string value. Raises ``ValueError`` for anything
    unrecognised — silently substituting a default would render a chart that
    quietly misrepresents the data.
    """
    try:
        resolved = ChartType(chart_type)
    except ValueError as exc:
        valid = ", ".join(t.value for t in ChartType)
        raise ValueError(f"Unknown chart type {chart_type!r}. Valid types: {valid}") from exc

    builder_cls = _BUILDERS.get(resolved)
    if builder_cls is None:  # pragma: no cover — guards a future enum addition
        raise ValueError(f"No builder registered for chart type {resolved.value!r}")
    return builder_cls()
