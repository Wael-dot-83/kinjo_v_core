"""
Comprehensive Monitoring and Health Check Service for KInJo Platform
"""
import asyncio
import logging
import time
import psutil
from dataclasses import dataclass, asdict
from datetime import datetime, timedelta, timezone
from typing import Dict, List, Any, Optional
from contextlib import asynccontextmanager
import threading
import os
import json

from sqlalchemy import text
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session
from database import get_db
from config import settings

logger = logging.getLogger(__name__)


@dataclass
class SystemMetric:
    timestamp: datetime
    cpu_percent: float = 0.0
    memory_percent: float = 0.0
    memory_used_mb: float = 0.0
    memory_available_mb: float = 0.0
    disk_usage_percent: float = 0.0
    disk_free_gb: float = 0.0
    network_connections: int = 0
    active_threads: int = 0
    active_coroutines: int = 0
    db_connections: int = 0
    cache_hit_rate: float = 0.0
    response_time_avg: float = 0.0
    error_rate: float = 0.0
    request_count: int = 0
    uptime_seconds: float = 0.0
    # Real-time feature metrics
    websocket_connections: int = 0
    websocket_messages_sent: int = 0
    cache_requests: int = 0
    cache_hits: int = 0
    realtime_updates: int = 0
    active_dashboard_sessions: int = 0

    def to_dict(self) -> Dict[str, Any]:
        data = asdict(self)
        data['timestamp'] = self.timestamp.isoformat()
        return data


@dataclass
class HealthCheckResult:
    status: str = "healthy"
    response_time: float = 0.0
    message: str = "OK"
    timestamp: datetime = None
    details: Dict[str, Any] = None

    def __post_init__(self):
        if self.timestamp is None:
            self.timestamp = datetime.now(timezone.utc)
        if self.details is None:
            self.details = {}

    def to_dict(self) -> Dict[str, Any]:
        data = asdict(self)
        data['timestamp'] = self.timestamp.isoformat()
        return data


@dataclass
class ScalingRecord:
    timestamp: datetime
    service: str
    action: str
    reason: str
    confidence: float
    metrics: Dict[str, Any]

    def to_dict(self) -> Dict[str, Any]:
        data = asdict(self)
        data['timestamp'] = self.timestamp.isoformat()
        return data


class MetricsCollector:
    """Collects system and application metrics"""

    def __init__(self):
        self.metrics_history: List[SystemMetric] = []
        self.max_history_size = 1000
        self.start_time = time.time()
        self.request_count = 0
        self.error_count = 0
        self.response_times: List[float] = []
        # Real-time feature metrics
        self.websocket_connections = 0
        self.websocket_messages_sent = 0
        self.cache_requests = 0
        self.cache_hits = 0
        self.realtime_updates = 0
        self.active_dashboard_sessions = 0
        self._lock = threading.Lock()

    def collect_system_metrics(self) -> SystemMetric:
        """Collect current system metrics"""
        try:
            cpu_percent = psutil.cpu_percent(interval=1)
            memory = psutil.virtual_memory()
            disk = psutil.disk_usage('/')

            # Network connections (TCP connections)
            net_connections = len(psutil.net_connections(kind='tcp'))

            # Active threads in current process
            active_threads = threading.active_count()

            # Database connections (simplified)
            db_connections = 0

            # Calculate uptime
            uptime_seconds = time.time() - self.start_time

            # Calculate error rate
            total_requests = self.request_count
            error_rate = (self.error_count / total_requests * 100) if total_requests > 0 else 0.0

            # Calculate average response time
            response_time_avg = sum(self.response_times[-100:]) / len(self.response_times[-100:]) if self.response_times else 0.0

            metric = SystemMetric(
                timestamp=datetime.now(timezone.utc),
                cpu_percent=cpu_percent,
                memory_percent=memory.percent,
                memory_used_mb=memory.used / 1024 / 1024,
                memory_available_mb=memory.available / 1024 / 1024,
                disk_usage_percent=disk.percent,
                disk_free_gb=disk.free / 1024 / 1024 / 1024,
                network_connections=net_connections,
                active_threads=active_threads,
                db_connections=db_connections,
                response_time_avg=response_time_avg,
                error_rate=error_rate,
                request_count=self.request_count,
                uptime_seconds=uptime_seconds,
                # Real-time feature metrics
                websocket_connections=self.websocket_connections,
                websocket_messages_sent=self.websocket_messages_sent,
                cache_requests=self.cache_requests,
                cache_hits=self.cache_hits,
                realtime_updates=self.realtime_updates,
                active_dashboard_sessions=self.active_dashboard_sessions
            )

            with self._lock:
                self.metrics_history.append(metric)
                if len(self.metrics_history) > self.max_history_size:
                    self.metrics_history.pop(0)

            return metric

        except (psutil.Error, OSError, RuntimeError, TypeError, ValueError) as e:
            logger.error(f"Error collecting system metrics: {e}")
            return SystemMetric(timestamp=datetime.now(timezone.utc))

    def record_request(self, response_time: float, is_error: bool = False):
        """Record a request for metrics calculation"""
        with self._lock:
            self.request_count += 1
            if is_error:
                self.error_count += 1
            self.response_times.append(response_time)
            if len(self.response_times) > 1000:
                self.response_times.pop(0)

    def record_websocket_connection(self, connected: bool = True):
        """Record WebSocket connection change"""
        with self._lock:
            if connected:
                self.websocket_connections += 1
            else:
                self.websocket_connections = max(0, self.websocket_connections - 1)

    def record_websocket_message(self):
        """Record WebSocket message sent"""
        with self._lock:
            self.websocket_messages_sent += 1

    def record_cache_request(self, is_hit: bool = False):
        """Record cache request"""
        with self._lock:
            self.cache_requests += 1
            if is_hit:
                self.cache_hits += 1

    def record_realtime_update(self):
        """Record real-time update sent"""
        with self._lock:
            self.realtime_updates += 1

    def record_dashboard_session(self, active: bool = True):
        """Record dashboard session change"""
        with self._lock:
            if active:
                self.active_dashboard_sessions += 1
            else:
                self.active_dashboard_sessions = max(0, self.active_dashboard_sessions - 1)

    def get_realtime_metrics(self) -> Dict[str, Any]:
        """Get current real-time feature metrics"""
        with self._lock:
            cache_hit_rate = (self.cache_hits / self.cache_requests * 100) if self.cache_requests > 0 else 0.0
            return {
                "websocket_connections": self.websocket_connections,
                "websocket_messages_sent": self.websocket_messages_sent,
                "cache_requests": self.cache_requests,
                "cache_hits": self.cache_hits,
                "cache_hit_rate": cache_hit_rate,
                "realtime_updates": self.realtime_updates,
                "active_dashboard_sessions": self.active_dashboard_sessions
            }

    def get_recent_metrics(self, minutes: int = 60) -> List[SystemMetric]:
        """Get metrics from the last N minutes"""
        cutoff = datetime.now(timezone.utc) - timedelta(minutes=minutes)
        with self._lock:
            return [m for m in self.metrics_history if m.timestamp >= cutoff]


class PerformanceMonitor:
    """Real performance monitoring with metrics collection"""

    def __init__(self):
        self.collector = MetricsCollector()
        self.monitoring_thread: Optional[threading.Thread] = None
        self.running = False
        self.collection_interval = 60  # seconds

    def start_monitoring(self):
        """Start the monitoring thread"""
        if self.running:
            return

        self.running = True
        self.monitoring_thread = threading.Thread(target=self._monitoring_loop, daemon=True)
        self.monitoring_thread.start()
        logger.info("Performance monitoring started")

    def stop_monitoring(self):
        """Stop the monitoring thread"""
        self.running = False
        if self.monitoring_thread:
            self.monitoring_thread.join(timeout=5)
        logger.info("Performance monitoring stopped")

    def _monitoring_loop(self):
        """Main monitoring loop"""
        while self.running:
            try:
                self.collector.collect_system_metrics()
                time.sleep(self.collection_interval)
            except (psutil.Error, OSError, RuntimeError, TypeError, ValueError) as e:
                logger.error(f"Error in monitoring loop: {e}")
                time.sleep(5)

    def get_system_health_score(self) -> float:
        """Calculate overall system health score (0-100)"""
        try:
            latest = self.collector.collect_system_metrics()

            # Weight different metrics
            cpu_score = max(0, 100 - latest.cpu_percent)
            memory_score = max(0, 100 - latest.memory_percent)
            disk_score = max(0, 100 - latest.disk_usage_percent)
            error_score = max(0, 100 - latest.error_rate)

            # Weighted average
            health_score = (
                cpu_score * 0.3 +
                memory_score * 0.3 +
                disk_score * 0.2 +
                error_score * 0.2
            )

            return round(health_score, 2)

        except (psutil.Error, RuntimeError, TypeError, ValueError) as e:
            logger.error(f"Error calculating health score: {e}")
            return 50.0

    def get_recent_metrics(self, minutes: int = 60) -> List[SystemMetric]:
        """Get recent metrics"""
        return self.collector.get_recent_metrics(minutes)

    def record_request(self, response_time: float, is_error: bool = False):
        """Record request metrics"""
        self.collector.record_request(response_time, is_error)


class HealthChecker:
    """Comprehensive health checker for all system components"""

    def __init__(self):
        self.last_checks: Dict[str, HealthCheckResult] = {}
        self.check_timeout = 10  # seconds

    async def run_health_checks(self) -> Dict[str, HealthCheckResult]:
        """Run all health checks"""
        checks = {}

        # Database health check
        checks["database"] = await self._check_database()

        # System resources check
        checks["system"] = await self._check_system_resources()

        # Application health check
        checks["application"] = await self._check_application()

        # External services check
        checks["external_services"] = await self._check_external_services()

        # Cache/store results
        self.last_checks.update(checks)

        return checks

    async def _check_database(self) -> HealthCheckResult:
        """Check database connectivity and performance"""
        start_time = time.time()
        db_gen = get_db()
        db = None
        try:
            db = next(db_gen)
            # Simple query to test connectivity
            result = db.execute(text("SELECT 1")).fetchone()
            response_time = time.time() - start_time

            if result and result[0] == 1:
                return HealthCheckResult(
                    status="healthy",
                    response_time=response_time,
                    message="Database connection successful",
                    details={"query_time": response_time}
                )
            else:
                return HealthCheckResult(
                    status="unhealthy",
                    response_time=response_time,
                    message="Database query failed",
                    details={"error": "Invalid response"}
                )

        except (SQLAlchemyError, RuntimeError, StopIteration) as e:
            response_time = time.time() - start_time
            return HealthCheckResult(
                status="unhealthy",
                response_time=response_time,
                message=f"Database connection failed: {str(e)}",
                details={"error": str(e)}
            )
        finally:
            try:
                if db is not None:
                    db.close()
                db_gen.close()
            except RuntimeError:
                pass

    async def _check_system_resources(self) -> HealthCheckResult:
        """Check system resource usage"""
        start_time = time.time()
        try:
            cpu_percent = psutil.cpu_percent()
            memory = psutil.virtual_memory()
            disk = psutil.disk_usage('/')

            response_time = time.time() - start_time

            # Define thresholds
            status = "healthy"
            message = "System resources OK"

            if cpu_percent > 90:
                status = "warning"
                message = f"High CPU usage: {cpu_percent}%"
            elif memory.percent > 90:
                status = "warning"
                message = f"High memory usage: {memory.percent}%"
            elif disk.percent > 95:
                status = "critical"
                message = f"Critical disk usage: {disk.percent}%"

            return HealthCheckResult(
                status=status,
                response_time=response_time,
                message=message,
                details={
                    "cpu_percent": cpu_percent,
                    "memory_percent": memory.percent,
                    "disk_percent": disk.percent
                }
            )

        except (psutil.Error, OSError, RuntimeError, TypeError, ValueError) as e:
            response_time = time.time() - start_time
            return HealthCheckResult(
                status="unhealthy",
                response_time=response_time,
                message=f"System resource check failed: {str(e)}",
                details={"error": str(e)}
            )

    async def _check_application(self) -> HealthCheckResult:
        """Check application-specific health"""
        start_time = time.time()
        try:
            # Check if critical modules can be imported
            import models
            import auth
            import validators

            # Check configuration
            if not settings.SECRET_KEY:
                return HealthCheckResult(
                    status="unhealthy",
                    response_time=time.time() - start_time,
                    message="Missing SECRET_KEY configuration"
                )

            response_time = time.time() - start_time
            return HealthCheckResult(
                status="healthy",
                response_time=response_time,
                message="Application components OK",
                details={"modules_loaded": ["models", "auth", "validators"]}
            )

        except (ImportError, AttributeError, RuntimeError, TypeError, ValueError) as e:
            response_time = time.time() - start_time
            return HealthCheckResult(
                status="unhealthy",
                response_time=response_time,
                message=f"Application health check failed: {str(e)}",
                details={"error": str(e)}
            )

    async def _check_external_services(self) -> HealthCheckResult:
        """Check external service dependencies"""
        start_time = time.time()
        try:
            services_status = {}

            # Check Redis if configured
            if hasattr(settings, 'REDIS_URL') and settings.REDIS_URL:
                # Redis check would go here
                services_status["redis"] = "not_implemented"

            # Check email service
            if hasattr(settings, 'SMTP_SERVER') and settings.SMTP_SERVER:
                services_status["smtp"] = "configured"
            else:
                services_status["smtp"] = "not_configured"

            response_time = time.time() - start_time
            return HealthCheckResult(
                status="healthy",
                response_time=response_time,
                message="External services check completed",
                details=services_status
            )

        except (AttributeError, RuntimeError, TypeError, ValueError) as e:
            response_time = time.time() - start_time
            return HealthCheckResult(
                status="warning",
                response_time=response_time,
                message=f"External services check partially failed: {str(e)}",
                details={"error": str(e)}
            )

    def get_overall_health_status(self) -> str:
        """Get overall health status"""
        if not self.last_checks:
            return "unknown"

        statuses = [check.status for check in self.last_checks.values()]

        if "unhealthy" in statuses:
            return "unhealthy"
        elif "critical" in statuses:
            return "critical"
        elif "warning" in statuses:
            return "warning"
        else:
            return "healthy"


class AutoScaler:
    """Auto-scaling service (stub with monitoring)"""

    def __init__(self):
        self.scaling_history: List[ScalingRecord] = []
        self.running = False

    def start_auto_scaling(self):
        """Start auto-scaling monitoring"""
        self.running = True
        logger.info("Auto-scaling monitoring started")

    def stop_auto_scaling(self):
        """Stop auto-scaling monitoring"""
        self.running = False
        logger.info("Auto-scaling monitoring stopped")

    def get_scaling_history(self, hours: int = 24) -> List[ScalingRecord]:
        """Get scaling history"""
        cutoff = datetime.now(timezone.utc) - timedelta(hours=hours)
        return [record for record in self.scaling_history if record.timestamp >= cutoff]


# Global instances
performance_monitor = PerformanceMonitor()
health_checker = HealthChecker()
auto_scaler = AutoScaler()
