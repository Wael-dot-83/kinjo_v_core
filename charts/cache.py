"""Redis cache layer for chart data and rendered HTML."""

from __future__ import annotations

import hashlib
import json
import logging
from typing import Optional

logger = logging.getLogger(__name__)

_RAW_TTL = 300      # 5 min — raw query data


def _make_key(namespace: str, params: dict) -> str:
    canonical = json.dumps(params, sort_keys=True, default=str)
    digest = hashlib.sha256(canonical.encode()).hexdigest()[:16]
    return f"kinjo:charts:{namespace}:{digest}"


def _get_redis():
    """Return a live Redis client or None on any connection error."""
    try:
        from config import settings
        import redis

        url = getattr(settings, "REDIS_URL", None) or getattr(settings, "CELERY_BROKER_URL", None)
        if not url:
            return None
        client = redis.from_url(url, decode_responses=True, socket_timeout=1)
        client.ping()
        return client
    except Exception as exc:
        logger.debug("Redis unavailable for chart cache: %s", exc)
        return None


def get_raw(params: dict) -> Optional[str]:
    r = _get_redis()
    if r is None:
        return None
    try:
        return r.get(_make_key("raw", params))
    except Exception:
        return None


def set_raw(params: dict, value: str, ttl: int = _RAW_TTL) -> None:
    r = _get_redis()
    if r is None:
        return
    try:
        r.setex(_make_key("raw", params), ttl, value)
    except Exception as exc:
        logger.debug("chart cache set_raw failed: %s", exc)


def invalidate(params: dict) -> None:
    r = _get_redis()
    if r is None:
        return
    try:
        r.delete(_make_key("raw", params))
    except Exception:
        pass
