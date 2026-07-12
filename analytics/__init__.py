"""Canonical analytics metric catalog package.

Public surface:
    from analytics import metric_registry
    metric_registry.get_metric(key)          -> enriched definition
    metric_registry.list_metrics(layer=..., dimension=...)
    metric_registry.validate_registry()      -> list of problems ([] == healthy)
"""
from . import metric_registry  # noqa: F401
