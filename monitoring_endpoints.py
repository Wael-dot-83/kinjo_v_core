"""
Monitoring and Health Check API Endpoints
"""
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session
from typing import Dict, List, Any, Optional
from datetime import datetime, timedelta, timezone
import logging
import os

from database import get_db
from monitoring_service import (
    performance_monitor,
    health_checker,
    SystemMetric,
    HealthCheckResult
)
from dependencies import get_current_user
from models import User, UserRole
from config import settings

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/monitoring", tags=["Monitoring"])


@router.get("/health", response_model=Dict[str, Any])
async def get_health_status(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """Get comprehensive health status of all system components"""
    if current_user.role not in [UserRole.ADMIN, UserRole.MANAGER]:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Only admins and managers can access monitoring data"
        )

    try:
        # Run all health checks
        health_results = await health_checker.run_health_checks()

        # Get overall status
        overall_status = health_checker.get_overall_health_status()

        # Get system health score
        health_score = performance_monitor.get_system_health_score()

        return {
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "overall_status": overall_status,
            "health_score": health_score,
            "checks": {name: check.to_dict() for name, check in health_results.items()},
            "summary": {
                "healthy": len([c for c in health_results.values() if c.status == "healthy"]),
                "warning": len([c for c in health_results.values() if c.status == "warning"]),
                "unhealthy": len([c for c in health_results.values() if c.status == "unhealthy"]),
                "critical": len([c for c in health_results.values() if c.status == "critical"])
            }
        }

    except (SQLAlchemyError, RuntimeError, TypeError, ValueError) as e:
        logger.error(f"Health check failed: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Health check failed: {str(e)}"
        )


@router.get("/metrics", response_model=Dict[str, Any])
async def get_system_metrics(
    minutes: int = 60,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """Get recent system performance metrics"""
    if current_user.role not in [UserRole.ADMIN, UserRole.MANAGER]:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Only admins and managers can access metrics"
        )

    try:
        metrics = performance_monitor.get_recent_metrics(minutes)

        if not metrics:
            return {
                "message": "No metrics available",
                "time_range_minutes": minutes,
                "metrics": []
            }

        # Calculate aggregates
        cpu_avg = sum(m.cpu_percent for m in metrics) / len(metrics)
        memory_avg = sum(m.memory_percent for m in metrics) / len(metrics)
        response_time_avg = sum(m.response_time_avg for m in metrics) / len(metrics)
        error_rate_avg = sum(m.error_rate for m in metrics) / len(metrics)

        return {
            "time_range_minutes": minutes,
            "metrics_count": len(metrics),
            "aggregates": {
                "cpu_percent_avg": round(cpu_avg, 2),
                "memory_percent_avg": round(memory_avg, 2),
                "response_time_avg": round(response_time_avg, 3),
                "error_rate_avg": round(error_rate_avg, 2)
            },
            "latest": metrics[-1].to_dict() if metrics else None,
            "metrics": [m.to_dict() for m in metrics[-10:]]  # Last 10 metrics
        }

    except (RuntimeError, TypeError, ValueError) as e:
        logger.error(f"Metrics retrieval failed: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Metrics retrieval failed: {str(e)}"
        )


@router.get("/metrics/detailed", response_model=List[Dict[str, Any]])
async def get_detailed_metrics(
    minutes: int = 60,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """Get detailed system metrics for monitoring dashboards"""
    if current_user.role != UserRole.ADMIN:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Only admins can access detailed metrics"
        )

    try:
        metrics = performance_monitor.get_recent_metrics(minutes)
        return [m.to_dict() for m in metrics]

    except (RuntimeError, TypeError, ValueError) as e:
        logger.error(f"Detailed metrics retrieval failed: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Detailed metrics retrieval failed: {str(e)}"
        )


@router.post("/health/run-checks", response_model=Dict[str, Any])
async def run_manual_health_checks(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """Manually trigger health checks"""
    if current_user.role != UserRole.ADMIN:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Only admins can trigger health checks"
        )

    try:
        health_results = await health_checker.run_health_checks()

        return {
            "message": "Health checks completed",
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "results": {name: check.to_dict() for name, check in health_results.items()}
        }

    except (SQLAlchemyError, RuntimeError, TypeError, ValueError) as e:
        logger.error(f"Manual health check failed: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Manual health check failed: {str(e)}"
        )


@router.get("/system/info", response_model=Dict[str, Any])
async def get_system_info(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """Get basic system information"""
    if current_user.role not in [UserRole.ADMIN, UserRole.MANAGER]:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Only admins and managers can access system info"
        )

    try:
        import platform
        import psutil
        from config import settings

        system_info = {
            "platform": platform.platform(),
            "python_version": platform.python_version(),
            "cpu_count": psutil.cpu_count(),
            "memory_total_gb": round(psutil.virtual_memory().total / (1024**3), 2),
            "disk_total_gb": round(psutil.disk_usage('/').total / (1024**3), 2),
            "environment": settings.ENVIRONMENT,
            "debug_mode": settings.TESTING,
            "uptime_seconds": performance_monitor.collector.uptime_seconds if hasattr(performance_monitor, 'collector') else 0
        }

        return system_info

    except (ImportError, AttributeError, OSError, RuntimeError, TypeError, ValueError) as e:
        logger.error(f"System info retrieval failed: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"System info retrieval failed: {str(e)}"
        )


@router.get("/realtime/metrics", response_model=Dict[str, Any])
async def get_realtime_metrics(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """Get real-time feature metrics (WebSocket, cache, dashboard sessions)"""
    if current_user.role not in [UserRole.ADMIN, UserRole.MANAGER]:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Only admins and managers can access real-time metrics"
        )

    try:
        realtime_metrics = performance_monitor.collector.get_realtime_metrics()

        return {
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "metrics": realtime_metrics,
            "summary": {
                "active_websocket_connections": realtime_metrics.get("websocket_connections", 0),
                "total_websocket_messages": realtime_metrics.get("websocket_messages_sent", 0),
                "cache_hit_rate": round(
                    (realtime_metrics.get("cache_hits", 0) /
                     max(realtime_metrics.get("cache_requests", 1), 1)) * 100, 2
                ),
                "active_dashboard_sessions": realtime_metrics.get("active_dashboard_sessions", 0),
                "total_realtime_updates": realtime_metrics.get("realtime_updates", 0)
            }
        }

    except (RuntimeError, TypeError, ValueError) as e:
        logger.error(f"Real-time metrics retrieval failed: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Real-time metrics retrieval failed: {str(e)}"
        )


@router.get("/dashboard/overview", response_model=Dict[str, Any])
async def get_monitoring_dashboard_overview(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """Get comprehensive monitoring dashboard overview"""
    if current_user.role not in [UserRole.ADMIN, UserRole.MANAGER]:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Only admins and managers can access monitoring dashboard"
        )

    try:
        # Get recent system metrics (last 5 minutes)
        recent_metrics = performance_monitor.get_recent_metrics(5)

        # Get real-time metrics
        realtime_metrics = performance_monitor.collector.get_realtime_metrics()

        # Get health status
        health_results = await health_checker.run_health_checks()
        overall_health = health_checker.get_overall_health_status()
        health_score = performance_monitor.get_system_health_score()

        # Calculate key metrics
        dashboard_data = {
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "system_health": {
                "overall_status": overall_health,
                "health_score": health_score,
                "checks_summary": {
                    "healthy": len([c for c in health_results.values() if c.status == "healthy"]),
                    "warning": len([c for c in health_results.values() if c.status == "warning"]),
                    "unhealthy": len([c for c in health_results.values() if c.status == "unhealthy"]),
                    "critical": len([c for c in health_results.values() if c.status == "critical"])
                }
            },
            "performance": {
                "current_cpu_percent": recent_metrics[-1].cpu_percent if recent_metrics else 0,
                "current_memory_percent": recent_metrics[-1].memory_percent if recent_metrics else 0,
                "avg_response_time": round(sum(m.response_time_avg for m in recent_metrics) / len(recent_metrics), 3) if recent_metrics else 0,
                "current_error_rate": recent_metrics[-1].error_rate if recent_metrics else 0
            },
            "realtime_features": {
                "active_websocket_connections": realtime_metrics.get("websocket_connections", 0),
                "websocket_messages_per_minute": realtime_metrics.get("websocket_messages_sent", 0),
                "cache_hit_rate": round(
                    (realtime_metrics.get("cache_hits", 0) /
                     max(realtime_metrics.get("cache_requests", 1), 1)) * 100, 2
                ),
                "active_dashboard_sessions": realtime_metrics.get("active_dashboard_sessions", 0),
                "realtime_updates_per_minute": realtime_metrics.get("realtime_updates", 0)
            },
            "alerts": []  # Will be populated with active alerts/warnings
        }

        # Add alerts based on thresholds
        if dashboard_data["performance"]["current_cpu_percent"] > 80:
            dashboard_data["alerts"].append({
                "type": "warning",
                "title": "High CPU Usage",
                "message": f"CPU usage is {dashboard_data['performance']['current_cpu_percent']:.1f}%",
                "priority": "high"
            })

        if dashboard_data["performance"]["current_memory_percent"] > 85:
            dashboard_data["alerts"].append({
                "type": "warning",
                "title": "High Memory Usage",
                "message": f"Memory usage is {dashboard_data['performance']['current_memory_percent']:.1f}%",
                "priority": "high"
            })

        if dashboard_data["performance"]["current_error_rate"] > 5:
            dashboard_data["alerts"].append({
                "type": "error",
                "title": "High Error Rate",
                "message": f"Error rate is {dashboard_data['performance']['current_error_rate']:.1f}%",
                "priority": "critical"
            })

        if dashboard_data["realtime_features"]["cache_hit_rate"] < 70:
            dashboard_data["alerts"].append({
                "type": "warning",
                "title": "Low Cache Hit Rate",
                "message": f"Cache hit rate is {dashboard_data['realtime_features']['cache_hit_rate']:.1f}%",
                "priority": "medium"
            })

        return dashboard_data

    except (SQLAlchemyError, RuntimeError, TypeError, ValueError) as e:
        logger.error(f"Dashboard overview retrieval failed: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Dashboard overview retrieval failed: {str(e)}"
        )


@router.get("/metrics/history", response_model=Dict[str, Any])
async def get_metrics_history(
    hours: int = 24,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """Get historical metrics for trend analysis"""
    if current_user.role not in [UserRole.ADMIN, UserRole.MANAGER]:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Only admins and managers can access metrics history"
        )

    try:
        minutes = hours * 60
        metrics = performance_monitor.get_recent_metrics(minutes)

        if not metrics:
            return {
                "message": "No historical metrics available",
                "time_range_hours": hours,
                "data_points": 0,
                "metrics": []
            }

        # Group metrics by hour for trend analysis
        hourly_data = {}
        for metric in metrics:
            hour_key = metric.timestamp.replace(minute=0, second=0, microsecond=0)
            if hour_key not in hourly_data:
                hourly_data[hour_key] = []
            hourly_data[hour_key].append(metric)

        # Calculate hourly averages
        trend_data = []
        for hour, hour_metrics in sorted(hourly_data.items()):
            trend_data.append({
                "timestamp": hour.isoformat(),
                "cpu_percent_avg": round(sum(m.cpu_percent for m in hour_metrics) / len(hour_metrics), 2),
                "memory_percent_avg": round(sum(m.memory_percent for m in hour_metrics) / len(hour_metrics), 2),
                "response_time_avg": round(sum(m.response_time_avg for m in hour_metrics) / len(hour_metrics), 3),
                "error_rate_avg": round(sum(m.error_rate for m in hour_metrics) / len(hour_metrics), 2),
                "data_points": len(hour_metrics)
            })

        return {
            "time_range_hours": hours,
            "data_points": len(metrics),
            "hourly_trends": trend_data
        }

    except (RuntimeError, TypeError, ValueError) as e:
        logger.error(f"Metrics history retrieval failed: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Metrics history retrieval failed: {str(e)}"
        )
