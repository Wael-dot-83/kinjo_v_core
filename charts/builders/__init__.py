"""Chart builder factory — maps ChartType → concrete builder instance."""

from charts.schemas import ChartType
from charts.builders.base import ChartBuilder
from charts.builders.line import LineBuilder
from charts.builders.bar import BarBuilder
from charts.builders.scatter import ScatterBuilder
from charts.builders.pie import PieBuilder
from charts.builders.histogram import HistogramBuilder
from charts.builders.box import BoxBuilder
from charts.builders.heatmap import HeatmapBuilder
from charts.builders.funnel import FunnelBuilder
from charts.builders.treemap import TreemapBuilder

_REGISTRY: dict[ChartType, type[ChartBuilder]] = {
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


def get_builder(chart_type: ChartType) -> ChartBuilder:
    """Return a fresh builder instance for the given chart type."""
    cls = _REGISTRY.get(chart_type)
    if cls is None:
        raise ValueError(f"No builder registered for chart type: {chart_type}")
    return cls()


__all__ = ["get_builder", "ChartBuilder"]
