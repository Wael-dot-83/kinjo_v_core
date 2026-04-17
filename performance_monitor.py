"""
Performance monitoring middleware and utilities
"""
import time
import logging
from typing import Callable, Dict, Any, List, Optional
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import Response
from monitoring_service import performance_monitor as _base_monitor

logger = logging.getLogger(__name__)


class _ExtendedPerformanceMonitor:
    """Wraps the base PerformanceMonitor and adds the extra query-level
    methods expected by admin_endpoints.py."""

    def __init__(self, base):
        self._base = base
        # In-memory stores for db query tracking
        self._db_queries: List[Dict[str, Any]] = []
        self._max_queries = 500

    # --- delegate everything we don't override to the base monitor ---
    def __getattr__(self, name):
        return getattr(self._base, name)

    # --- request-level metrics (aggregated from the collector) ---
    def get_request_metrics(self) -> Dict[str, Any]:
        """Return high-level request metrics."""
        collector = self._base.collector
        total = collector.request_count
        errors = collector.error_count
        avg_rt = (
            sum(collector.response_times[-100:]) / len(collector.response_times[-100:])
            if collector.response_times else 0.0
        )
        return {
            "total_requests": total,
            "error_count": errors,
            "error_rate": round((errors / total * 100) if total else 0.0, 2),
            "avg_response_time_ms": round(avg_rt * 1000, 2),
            "uptime_seconds": round(time.time() - collector.start_time, 1),
        }

    # --- database query tracking ---
    def record_db_query(self, query: str, duration: float, params: Optional[str] = None):
        entry = {
            "query": query[:500],
            "duration_ms": round(duration * 1000, 2),
            "params": params,
            "timestamp": time.time(),
        }
        self._db_queries.append(entry)
        if len(self._db_queries) > self._max_queries:
            self._db_queries = self._db_queries[-self._max_queries:]

    def get_db_metrics(self, limit: int = 100) -> List[Dict[str, Any]]:
        """Return the most recent database queries."""
        return self._db_queries[-limit:]

    def get_slow_queries(self, threshold_seconds: float = 2.0) -> List[Dict[str, Any]]:
        """Return queries slower than *threshold_seconds*."""
        threshold_ms = threshold_seconds * 1000
        return [q for q in self._db_queries if q["duration_ms"] >= threshold_ms]

    # --- system-level metrics ---
    def get_system_metrics(self, limit: int = 50) -> List[Dict[str, Any]]:
        """Return recent system-level snapshots."""
        recent = self._base.get_recent_metrics(minutes=120)
        items = [m.to_dict() for m in recent[-limit:]]
        if not items:
            # Collect a fresh snapshot so there's always at least one result
            fresh = self._base.collector.collect_system_metrics()
            items = [fresh.to_dict()]
        return items


# Re-export as the name admin_endpoints expects
performance_monitor = _ExtendedPerformanceMonitor(_base_monitor)


def get_performance_report() -> Dict[str, Any]:
    """Comprehensive performance report consumed by GET /performance/metrics."""
    request_metrics = performance_monitor.get_request_metrics()
    system_metrics = performance_monitor.get_system_metrics(limit=10)
    health_score = performance_monitor.get_system_health_score()
    slow_queries = performance_monitor.get_slow_queries(2.0)

    return {
        "health_score": health_score,
        "request_metrics": request_metrics,
        "system_metrics": system_metrics,
        "slow_queries_count": len(slow_queries),
        "slow_queries": slow_queries[:20],
    }


class PerformanceMiddleware(BaseHTTPMiddleware):
    """Performance monitoring middleware that tracks request metrics"""

    @staticmethod
    def _should_count_as_error(status_code: int) -> bool:
        """Count only actionable failures as errors for platform health.
        Expected auth/not-found client responses should not degrade health score.
        """
        if status_code in (401, 403, 404):
            return False
        return status_code >= 400

    async def dispatch(self, request: Request, call_next: Callable) -> Response:
        start_time = time.time()

        try:
            # Process the request
            response = await call_next(request)

            # Calculate response time
            response_time = time.time() - start_time

            # Determine if this should impact error-rate health metrics.
            is_error = self._should_count_as_error(response.status_code)

            # Record the request metrics
            performance_monitor.record_request(response_time, is_error)

            # Log slow requests
            if response_time > 1.0:  # More than 1 second
                logger.warning(
                    f"Slow request: {request.method} {request.url.path} "
                    f"took {response_time:.2f}s (status: {response.status_code})"
                )

            # Log errors with severity by status class. 4xx auth/not-found responses
            # are expected in many normal flows (session expiry, protected routes).
            if is_error:
                status_code = response.status_code
                message = (
                    f"Request error: {request.method} {request.url.path} "
                    f"returned {status_code} in {response_time:.2f}s"
                )
                if status_code >= 500:
                    logger.error(message)
                elif status_code in (401, 403, 404):
                    logger.info(message)
                else:
                    logger.warning(message)

            return response

        except Exception as e:
            # Record failed request
            response_time = time.time() - start_time
            performance_monitor.record_request(response_time, is_error=True)

            logger.error(
                f"Request exception: {request.method} {request.url.path} "
                f"failed in {response_time:.2f}s: {str(e)}"
            )
            raise


def setup_database_monitoring(engine):
    """Setup database connection pool monitoring"""
    try:
        # Enable SQLAlchemy engine logging for slow queries
        logging.getLogger('sqlalchemy.engine').setLevel(logging.WARNING)

        # Log connection pool stats periodically
        import threading

        def log_pool_stats():
            while True:
                try:
                    pool = engine.pool
                    logger.info(
                        f"DB Pool - size: {pool.size()}, checked_in: {pool.checkedin()}, "
                        f"checked_out: {pool.checkedout()}, overflow: {pool.overflow()}"
                    )
                    time.sleep(300)  # Log every 5 minutes
                except Exception as e:
                    logger.error(f"Error logging pool stats: {e}")
                    time.sleep(60)

        # Start pool monitoring thread
        monitor_thread = threading.Thread(target=log_pool_stats, daemon=True)
        monitor_thread.start()

        logger.info("Database monitoring setup completed")

    except Exception as e:
        logger.error(f"Failed to setup database monitoring: {e}")


def start_system_monitoring():
    """Start comprehensive system monitoring"""
    try:
        # Start performance monitoring
        performance_monitor.start_monitoring()

        # Start auto-scaling monitoring
        from monitoring_service import auto_scaler
        auto_scaler.start_auto_scaling()

        logger.info("System monitoring started successfully")

    except Exception as e:
        logger.error(f"Failed to start system monitoring: {e}")


class RequestMetricsCollector:
    """Utility class for collecting detailed request metrics"""

    def __init__(self):
        self.request_count = 0
        self.error_count = 0
        self.response_times = []
        self.status_codes = {}
        self.endpoint_metrics = {}

    def record_request(self, method: str, path: str, status_code: int, response_time: float):
        """Record a request"""
        self.request_count += 1

        if status_code >= 400:
            self.error_count += 1

        self.response_times.append(response_time)
        if len(self.response_times) > 1000:
            self.response_times.pop(0)

        # Track status codes
        self.status_codes[status_code] = self.status_codes.get(status_code, 0) + 1

        # Track endpoint metrics
        endpoint_key = f"{method} {path}"
        if endpoint_key not in self.endpoint_metrics:
            self.endpoint_metrics[endpoint_key] = {
                'count': 0,
                'total_time': 0.0,
                'errors': 0
            }

        metrics = self.endpoint_metrics[endpoint_key]
        metrics['count'] += 1
        metrics['total_time'] += response_time
        if status_code >= 400:
            metrics['errors'] += 1

    def get_summary(self) -> dict:
        """Get metrics summary"""
        total_requests = self.request_count
        error_rate = (self.error_count / total_requests * 100) if total_requests > 0 else 0

        avg_response_time = (
            sum(self.response_times) / len(self.response_times)
            if self.response_times else 0
        )

        return {
            'total_requests': total_requests,
            'error_count': self.error_count,
            'error_rate': round(error_rate, 2),
            'avg_response_time': round(avg_response_time, 3),
            'status_codes': self.status_codes,
            'top_endpoints': sorted(
                [
                    {
                        'endpoint': endpoint,
                        'count': metrics['count'],
                        'avg_time': round(metrics['total_time'] / metrics['count'], 3),
                        'error_rate': round(metrics['errors'] / metrics['count'] * 100, 2)
                    }
                    for endpoint, metrics in self.endpoint_metrics.items()
                ],
                key=lambda x: x['count'],
                reverse=True
            )[:10]  # Top 10 endpoints
        }


# Global metrics collector
request_metrics = RequestMetricsCollector()
