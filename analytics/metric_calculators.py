"""Thin calculator adapters over analytics_gap_service.

These are deliberately **not** re-implementations of the 33 metric computations
(see baseline audit: analytics_gap_service already owns that logic, and duplicating
~312KB of query code would be a regression risk). Each adapter:

  1. resolves the registry ``producer`` for a layer,
  2. invokes the corresponding AnalyticsGapService method,
  3. normalizes the legacy ``no_data`` sentinel into an explicit data-state, and
  4. annotates every MetricResponse with data_state / coverage / display.

This is the single entry point endpoints should call so data-state handling is
applied uniformly.
"""
from __future__ import annotations

from typing import List, Optional

from . import metric_registry
from . import metric_formatter as fmt

# layer -> the AnalyticsGapService method that produces it.
# Geographic layers share one producer selected by dimension.
_LAYER_METHOD = {
    "network": "get_network_metrics",
    "kindergarten": "get_kg_metrics",
    "child": "get_child_metrics",
    "predictive": "get_predictive_metrics",
    "governance": "get_governance_metrics",
}
_GEO_METHOD = {
    "GOVERNORATE": "get_governorate_metrics",
    "DISTRICT": "get_district_metrics",
    "AREA": "get_area_metrics",  # AREA == "City"
}


def _annotate_layer(layer_response, *, lang: str):
    """Replace the legacy single 'no_data' sentinel metric with an explicit
    empty-layer marker, and annotate all real metrics with their data-state."""
    metrics = list(getattr(layer_response, "metrics", []) or [])
    if len(metrics) == 1 and getattr(metrics[0], "metric", None) == "no_data":
        m = metrics[0]
        m.data_state = fmt.MISSING
        m.display = {"en": fmt.placeholder(fmt.MISSING), "ar": fmt.placeholder(fmt.MISSING)}
        m.coverage = {"denominator": 0, "minimum": None}
        return layer_response
    for m in metrics:
        fmt.annotate_metric(m, lang=lang)
    return layer_response


def compute_network(db, locale: str = "ar"):
    from analytics_gap_service import AnalyticsGapService
    resp = AnalyticsGapService(db).get_network_metrics(locale=locale)
    return _annotate_layer(resp, lang=locale)


def compute_geographic(db, dimension: str, value: str, locale: str = "ar"):
    """dimension in {GOVERNORATE, DISTRICT, AREA}. AREA is surfaced as 'City'."""
    dimension = dimension.upper()
    method = _GEO_METHOD.get(dimension)
    if method is None:
        raise ValueError(f"Unsupported geographic dimension: {dimension!r}")
    from analytics_gap_service import AnalyticsGapService
    resp = getattr(AnalyticsGapService(db), method)(value, locale=locale)
    return _annotate_layer(resp, lang=locale)


def compute_kindergarten(db, kg_id: int, locale: str = "ar"):
    from analytics_gap_service import AnalyticsGapService
    resp = AnalyticsGapService(db).get_kg_metrics(kg_id, locale=locale)
    return _annotate_layer(resp, lang=locale)


def compute_child(db, child_id: int, locale: str = "ar", *, authorized: bool = False):
    """Child-layer metrics are privacy_level=restricted. When ``authorized`` is False
    the values are suppressed (state=suppressed) rather than returned."""
    from analytics_gap_service import AnalyticsGapService
    resp = AnalyticsGapService(db).get_child_metrics(child_id, locale=locale)
    metrics = list(getattr(resp, "metrics", []) or [])
    for m in metrics:
        fmt.annotate_metric(m, suppressed=not authorized, lang=locale)
    return resp


def compute_predictive(db, locale: str = "ar"):
    from analytics_gap_service import AnalyticsGapService
    resp = AnalyticsGapService(db).get_predictive_metrics(locale=locale)
    return _annotate_layer(resp, lang=locale)


def compute_governance(db, locale: str = "ar"):
    from analytics_gap_service import AnalyticsGapService
    resp = AnalyticsGapService(db).get_governance_metrics(locale=locale)
    return _annotate_layer(resp, lang=locale)


def compute_layer(db, layer: str, locale: str = "ar", **kwargs):
    """Generic dispatcher by registry layer name.

    kwargs: dimension+value (geographic), kg_id (kindergarten), child_id+authorized (child).
    """
    layer = layer.lower()
    if layer == "network":
        return compute_network(db, locale)
    if layer == "geographic":
        return compute_geographic(db, kwargs["dimension"], kwargs["value"], locale)
    if layer == "kindergarten":
        return compute_kindergarten(db, kwargs["kg_id"], locale)
    if layer == "child":
        return compute_child(db, kwargs["child_id"], locale,
                             authorized=kwargs.get("authorized", False))
    if layer == "predictive":
        return compute_predictive(db, locale)
    if layer == "governance":
        return compute_governance(db, locale)
    raise ValueError(f"Unknown layer: {layer!r}")


def supported_layers() -> List[str]:
    return ["network", "geographic", "kindergarten", "child", "predictive", "governance"]
