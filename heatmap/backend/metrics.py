"""
Lightweight metrics for the Admin Heat Map.

Uses the project's existing `performance_monitor` to record per-endpoint
metrics.  Exposes a single `record_heat_map_request(endpoint, duration)`
function that the heat map router uses as a FastAPI dependency.
"""
from __future__ import annotations
import logging
import time
from typing import Optional

try:
    from performance_monitor import performance_monitor
    MONITORING_AVAILABLE = True
except ImportError:  # pragma: no cover
    MONITORING_AVAILABLE = False

logger = logging.getLogger(__name__)


def record_heat_map_request(endpoint: str, duration_ms: float, status_code: int = 200) -> None:
    """Record a single request to a heat map endpoint.

    `endpoint` should be the route name (e.g. "data", "correlations").
    `duration_ms` is the wall-clock duration in milliseconds.
    """
    if not MONITORING_AVAILABLE:
        return
    try:
        # Existing performance monitor has `record_db_query`; we add a
        # generic counter via `record_request` if it exists, otherwise we
        # silently skip.  The key insight is that this code never raises
        # into the request handler.
        if hasattr(performance_monitor, "collector"):
            collector = performance_monitor.collector
            if hasattr(collector, "record_request"):
                collector.record_request(
                    endpoint=f"heat_map.{endpoint}",
                    duration=duration_ms / 1000.0,
                    status_code=status_code,
                )
    except Exception as exc:
        logger.debug("record_heat_map_request failed: %s", exc)
