"""
Telemetry ingestion, storage, and analytics service.
Handles frontend Web Vitals, error reports, and API timing data.
"""
import logging
import time
from collections import defaultdict
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, Depends, HTTPException, Query, status
from pydantic import BaseModel, Field
from sqlalchemy import func, desc
from sqlalchemy.orm import Session

from database import get_db
from dependencies import get_current_user, require_admin
from models import (
    User, UserRole,
    TelemetryEvent, TelemetryEventType,
    WebVitalMetric, WebVitalType, VitalRating,
    ClientErrorReport,
)

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/telemetry", tags=["Telemetry"])


# ---------------------------------------------------------------------------
# Pydantic request/response schemas
# ---------------------------------------------------------------------------

class WebVitalItem(BaseModel):
    name: str
    value: float
    rating: Optional[str] = "good"
    timestamp_ms: Optional[int] = None


class WebVitalsPayload(BaseModel):
    session_id: str = Field(max_length=64)
    page: str = Field(max_length=255)
    role: Optional[str] = Field(default=None, max_length=50)
    lang: Optional[str] = Field(default="ar", max_length=10)
    direction: Optional[str] = Field(default="rtl", max_length=10)
    metrics: List[WebVitalItem]


class ErrorPayload(BaseModel):
    session_id: str = Field(max_length=64)
    page: str = Field(max_length=255)
    role: Optional[str] = Field(default=None, max_length=50)
    error_type: str = Field(max_length=50)
    message: str = Field(max_length=500)
    stack_hash: Optional[str] = Field(default=None, max_length=16)
    timestamp_ms: Optional[int] = None


class ApiCallItem(BaseModel):
    endpoint: str = Field(max_length=255)
    method: str = Field(max_length=10)
    status_code: int
    duration_ms: float
    cache_hit: Optional[bool] = None


class ApiCallsPayload(BaseModel):
    session_id: str = Field(max_length=64)
    role: Optional[str] = Field(default=None, max_length=50)
    calls: List[ApiCallItem]


class TelemetryStatsResponse(BaseModel):
    period_hours: int
    web_vitals: Dict[str, Any]
    errors: Dict[str, Any]
    api_latency: Dict[str, Any]
    summary: Dict[str, Any]


class P95Calculator:
    """In-memory percentile calculator with sliding window."""

    def __init__(self, max_entries: int = 5000):
        self._values: Dict[str, List[float]] = defaultdict(list)
        self._max = max_entries

    def add(self, key: str, value: float) -> None:
        self._values[key].append(value)
        if len(self._values[key]) > self._max:
            self._values[key] = self._values[key][-self._max:]

    def percentile(self, key: str, p: float) -> float:
        vals = self._values.get(key, [])
        if not vals:
            return 0.0
        sorted_vals = sorted(vals)
        idx = int(len(sorted_vals) * p / 100.0)
        idx = min(idx, len(sorted_vals) - 1)
        return sorted_vals[idx]

    def stats(self, key: str) -> Dict[str, float]:
        vals = self._values.get(key, [])
        if not vals:
            return {"count": 0, "p50": 0.0, "p95": 0.0, "p99": 0.0, "avg": 0.0}
        return {
            "count": len(vals),
            "avg": round(sum(vals) / len(vals), 2),
            "p50": round(self.percentile(key, 50), 2),
            "p95": round(self.percentile(key, 95), 2),
            "p99": round(self.percentile(key, 99), 2),
        }

    def all_keys(self) -> List[str]:
        return list(self._values.keys())

    def clear(self) -> None:
        self._values.clear()


_p95_vitals: Dict[str, List[float]] = defaultdict(list)
_p95_api: P95Calculator = P95Calculator()
_telemetry_stats: Dict[str, int] = defaultdict(int)

_VITAL_MAX = {"lcp": 10000.0, "fid": 5000.0, "cls": 5.0}


def _sanitize_page(page: str) -> str:
    if not page:
        return "/"
    if "?" in page:
        page = page.split("?", 1)[0]
    if "#" in page:
        page = page.split("#", 1)[0]
    return page[:255]


def _sanitize_message(msg: str) -> str:
    import re
    msg = re.sub(r"file:///[^\s]+", "[path]", msg)
    msg = re.sub(r"https?://[^\s]+", "[url]", msg)
    msg = re.sub(r"\b[a-zA-Z0-9._%+\-]+@[a-zA-Z0-9.\-]+\.[a-zA-Z]{2,}\b", "[email]", msg)
    return msg[:500]


def _classify_vital_rating(name: str, value: float) -> str:
    if name == "lcp":
        if value <= 2500:
            return "good"
        elif value <= 4000:
            return "needs-improvement"
        return "poor"
    elif name == "fid":
        if value <= 100:
            return "good"
        elif value <= 300:
            return "needs-improvement"
        return "poor"
    elif name == "cls":
        if value <= 0.1:
            return "good"
        elif value <= 0.25:
            return "needs-improvement"
        return "poor"
    return "good"


def _safe_vital_value(name: str, value: float) -> float:
    cap = _VITAL_MAX.get(name, 10000.0)
    return min(max(value, 0.0), cap)


# ---------------------------------------------------------------------------
# Ingestion endpoints
# ---------------------------------------------------------------------------

@router.post("/vitals", status_code=status.HTTP_202_ACCEPTED)
async def ingest_web_vitals(payload: WebVitalsPayload):
    try:
        now_ms = int(time.time() * 1000)
        page = _sanitize_page(payload.page)
        count = 0
        for item in payload.metrics:
            name = (item.name or "").lower().strip()
            if name not in ("lcp", "fid", "cls"):
                continue
            value = _safe_vital_value(name, item.value)
            rating = item.rating or _classify_vital_rating(name, value)
            record: Dict[str, Any] = {
                "session_id": payload.session_id[:64],
                "page": page,
                "role": payload.role,
                "lang": payload.lang or "ar",
                "direction": payload.direction or "rtl",
                "metric_name": name,
                "value": round(value, 3),
                "rating": rating,
                "timestamp_ms": item.timestamp_ms or now_ms,
            }
            _p95_vitals[name].append(record["value"])
            if len(_p95_vitals[name]) > 5000:
                _p95_vitals[name] = _p95_vitals[name][-5000:]
            _telemetry_stats["vitals_ingested"] += 1
            count += 1

        logger.info("telemetry_vitals ingested=%d session=%s page=%s", count, payload.session_id[:12], page)
        return {"accepted": count, "session_id": payload.session_id}
    except (ValueError, TypeError, KeyError) as exc:
        logger.error("telemetry_vitals_failed session=%s error=%s", payload.session_id, str(exc))
        raise HTTPException(status_code=400, detail="Invalid vitals data")


@router.post("/errors", status_code=status.HTTP_202_ACCEPTED)
async def ingest_client_errors(payload: ErrorPayload):
    try:
        now_ms = int(time.time() * 1000)
        page = _sanitize_page(payload.page)
        message = _sanitize_message(payload.message or "")
        record = {
            "session_id": payload.session_id[:64],
            "page": page,
            "role": payload.role,
            "error_type": (payload.error_type or "unknown")[:50],
            "message": message,
            "stack_hash": payload.stack_hash[:16] if payload.stack_hash else None,
            "timestamp_ms": payload.timestamp_ms or now_ms,
        }
        _telemetry_stats["errors_ingested"] += 1
        logger.info(
            "telemetry_error session=%s type=%s page=%s hash=%s",
            payload.session_id[:12], record["error_type"], page, record.get("stack_hash"),
        )
        return {"accepted": 1, "session_id": payload.session_id}
    except (ValueError, TypeError) as exc:
        logger.error("telemetry_error_failed session=%s error=%s", payload.session_id, str(exc))
        raise HTTPException(status_code=400, detail="Invalid error data")


@router.post("/api", status_code=status.HTTP_202_ACCEPTED)
async def ingest_api_metrics(payload: ApiCallsPayload):
    try:
        count = 0
        for item in payload.calls:
            endpoint = (item.endpoint or "").split("?")[0][:255]
            if not endpoint.startswith("/"):
                continue
            _p95_api.add(endpoint, item.duration_ms)
            if item.cache_hit is not None:
                key = f"{endpoint}:cache"
                _p95_api.add(key, 1.0 if item.cache_hit else 0.0)
            _telemetry_stats["api_calls_ingested"] += 1
            count += 1

        logger.info("telemetry_api ingested=%d session=%s", count, payload.session_id[:12])
        return {"accepted": count, "session_id": payload.session_id}
    except (ValueError, TypeError) as exc:
        logger.error("telemetry_api_failed session=%s error=%s", payload.session_id, str(exc))
        raise HTTPException(status_code=400, detail="Invalid API metrics data")


# ---------------------------------------------------------------------------
# Analytics & dashboard endpoints
# ---------------------------------------------------------------------------

@router.get("/stats", response_model=TelemetryStatsResponse)
async def get_telemetry_stats(
    period_hours: int = Query(default=24, ge=1, le=168),
    current_user: User = Depends(require_admin),
):
    window = []
    now = datetime.now(timezone.utc)

    web_vitals_summary: Dict[str, Any] = {}
    for name in ("lcp", "fid", "cls"):
        vals = _p95_vitals.get(name, [])
        if not vals:
            web_vitals_summary[name] = {"count": 0, "p50": 0, "p95": 0, "avg": 0, "status": "no_data"}
            continue
        sorted_vals = sorted(vals)
        p95 = sorted_vals[min(int(len(sorted_vals) * 0.95), len(sorted_vals) - 1)]
        if name == "lcp":
            status_str = "good" if p95 <= 2500 else ("needs-improvement" if p95 <= 4000 else "poor")
        elif name == "fid":
            status_str = "good" if p95 <= 100 else ("needs-improvement" if p95 <= 300 else "poor")
        else:
            status_str = "good" if p95 <= 0.1 else ("needs-improvement" if p95 <= 0.25 else "poor")

        web_vitals_summary[name] = {
            "count": len(vals),
            "avg": round(sum(vals) / len(vals), 2),
            "p50": round(sorted_vals[int(len(sorted_vals) * 0.5)], 2),
            "p95": round(p95, 2),
            "status": status_str,
        }

    all_endpoints = _p95_api.all_keys()
    api_endpoints = [k for k in all_endpoints if not k.endswith(":cache")]
    api_summary: Dict[str, Any] = {}
    for ep in api_endpoints[:50]:
        api_summary[ep] = _p95_api.stats(ep)

    error_count = _telemetry_stats.get("errors_ingested", 0)
    vitals_count = _telemetry_stats.get("vitals_ingested", 0)
    api_count = _telemetry_stats.get("api_calls_ingested", 0)

    return TelemetryStatsResponse(
        period_hours=period_hours,
        web_vitals=web_vitals_summary,
        errors={
            "total_ingested": error_count,
        },
        api_latency=api_summary,
        summary={
            "total_vitals": vitals_count,
            "total_errors": error_count,
            "total_api_calls": api_count,
            "tracked_endpoints": len(api_endpoints),
        },
    )


@router.get("/health", response_model=Dict[str, Any])
async def get_telemetry_health():
    vitals_healthy = True
    for name in ("lcp", "fid", "cls"):
        vals = _p95_vitals.get(name, [])
        if vals:
            p95 = sorted(vals)[min(int(len(vals) * 0.95), len(vals) - 1)]
            if name == "lcp" and p95 > 4000:
                vitals_healthy = False
            elif name == "fid" and p95 > 300:
                vitals_healthy = False
            elif name == "cls" and p95 > 0.25:
                vitals_healthy = False

    errors_healthy = _telemetry_stats.get("errors_ingested", 0) < 100

    all_eps = [k for k in _p95_api.all_keys() if not k.endswith(":cache")]
    api_healthy = True
    for ep in all_eps:
        stats = _p95_api.stats(ep)
        if stats["p95"] > 2000:
            api_healthy = False
            break

    overall_healthy = vitals_healthy and errors_healthy and api_healthy
    return {
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "status": "healthy" if overall_healthy else "degraded",
        "checks": {
            "vitals": {"healthy": vitals_healthy, "status": "good" if vitals_healthy else "degraded"},
            "errors": {"healthy": errors_healthy, "status": "good" if errors_healthy else "elevated"},
            "api_latency": {"healthy": api_healthy, "status": "good" if api_healthy else "degraded"},
        },
    }


@router.delete("/cache", status_code=status.HTTP_200_OK)
async def clear_telemetry_cache(current_user: User = Depends(require_admin)):
    for key in list(_p95_vitals.keys()):
        del _p95_vitals[key]
    _p95_api.clear()
    for key in list(_telemetry_stats.keys()):
        _telemetry_stats[key] = 0
    logger.info("telemetry_cache_cleared by user=%s", current_user.id)
    return {"cleared": True}
