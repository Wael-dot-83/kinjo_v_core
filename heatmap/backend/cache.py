"""
Caching layer for the Admin Heat Map endpoints.

Uses the existing `CacheService` to memoize the results of expensive
endpoints (`/data`, `/indicators`, `/correlations`, `/regression`,
`/governorates`, `/geojson`) for a short TTL. The cache is invalidated
by the daily pipeline via `invalidate_heat_map_cache()`.

Implements circuit breaker pattern: after N consecutive failures,
caching is disabled for TTL/2 seconds.
"""
from __future__ import annotations
import logging
import time
from typing import Any, Optional

try:
    from cache_service import get_cache
except ImportError:  # pragma: no cover
    get_cache = None

logger = logging.getLogger(__name__)

# Per-endpoint TTLs (seconds)
HEAT_MAP_TTL_SECONDS = 300        # 5 min for /data, /indicators, /geojson
HEAT_MAP_CORRELATION_TTL = 3600   # 1 h for /correlations, /regression
HEAT_MAP_GOVERNORATES_TTL = 3600  # 1 h for /governorates

# Circuit breaker settings
_CACHE_FAILURES = 0
_CACHE_DISABLED_UNTIL = 0.0
_CIRCUIT_BREAKER_THRESHOLD = 5
_CIRCUIT_BREAKER_TIMEOUT = 60  # seconds

# Cache key prefix
_PREFIX = "admin_heat_map"


def _key(name: str) -> str:
    return f"{_PREFIX}:{name}"


def _is_circuit_open() -> bool:
    """Check if circuit breaker is open (cache disabled due to failures)."""
    global _CACHE_FAILURES, _CACHE_DISABLED_UNTIL
    if _CACHE_FAILURES >= _CIRCUIT_BREAKER_THRESHOLD:
        if time.time() < _CACHE_DISABLED_UNTIL:
            return True
        # Reset breaker
        _CACHE_FAILURES = 0
        _CACHE_DISABLED_UNTIL = 0.0
    return False


def cached_get(name: str) -> Any:
    """Return a cached value or None on miss/error. Implements circuit breaker."""
    global _CACHE_FAILURES
    if get_cache is None or _is_circuit_open():
        return None
    try:
        cache = get_cache()
        value = cache.get(_key(name))
        _CACHE_FAILURES = 0  # Reset on success
        return value
    except Exception as exc:
        _CACHE_FAILURES += 1
        if _CACHE_FAILURES >= _CIRCUIT_BREAKER_THRESHOLD:
            _CACHE_DISABLED_UNTIL = time.time() + _CIRCUIT_BREAKER_TIMEOUT
        logger.warning("cache_get failed for %s: %s (circuit: %d failures)", name, exc, _CACHE_FAILURES)
        return None


def cached_set(name: str, value: Any, ttl: int = HEAT_MAP_TTL_SECONDS) -> None:
    """Store a value in cache with a TTL.  Silently no-ops on error."""
    global _CACHE_FAILURES
    if get_cache is None or _is_circuit_open():
        return
    try:
        cache = get_cache()
        cache.set(_key(name), value, ttl=ttl)
        _CACHE_FAILURES = 0  # Reset on success
    except Exception as exc:
        _CACHE_FAILURES += 1
        if _CACHE_FAILURES >= _CIRCUIT_BREAKER_THRESHOLD:
            _CACHE_DISABLED_UNTIL = time.time() + _CIRCUIT_BREAKER_TIMEOUT
        logger.warning("cache_set failed for %s: %s (circuit: %d failures)", name, exc, _CACHE_FAILURES)


def invalidate_heat_map_cache() -> None:
    """Invalidate every cached payload.  Called by the daily pipeline
    after a successful run so the next admin request gets fresh data.
    """
    global _CACHE_FAILURES
    if get_cache is None or _is_circuit_open():
        return
    keys = [
        "governorates",
        "indicators",
        "data",
        "geojson",
        "correlations",
        "regression",
        "daily_update",
    ]
    try:
        cache = get_cache()
        for name in keys:
            cache.delete(_key(name))
        _CACHE_FAILURES = 0  # Reset on success
        logger.info("Heat map cache invalidated (%d keys)", len(keys))
    except Exception as exc:
        _CACHE_FAILURES += 1
        if _CACHE_FAILURES >= _CIRCUIT_BREAKER_THRESHOLD:
            _CACHE_DISABLED_UNTIL = time.time() + _CIRCUIT_BREAKER_TIMEOUT
        logger.warning("invalidate_heat_map_cache failed: %s (circuit: %d failures)", exc, _CACHE_FAILURES)