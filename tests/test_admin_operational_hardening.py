"""Operational Admin-surface regressions for production-safe failure behavior."""

from pathlib import Path

import main


ROOT = Path(__file__).resolve().parents[1]


def test_legacy_process_local_heatmap_is_not_mounted_in_production():
    source = (ROOT / "main.py").read_text(encoding="utf-8")
    assert 'if settings.ENVIRONMENT.lower() != "production":' in source
    assert 'app.include_router(heat_map_router, prefix="/api/heatmap")' in source
    assert "Production uses the persistent canonical" in source


def test_admin_surface_rate_limit_covers_legacy_aliases():
    source = (ROOT / "main.py").read_text(encoding="utf-8")
    block = source[source.index("protected_prefixes = ("):source.index(")", source.index("protected_prefixes = ("))]
    assert '"/api/audit-logs"' in block
    assert '"/api/heatmap"' in block


def test_admin_access_logging_covers_legacy_aliases():
    source = (ROOT / "main.py").read_text(encoding="utf-8")
    assert 'audited_prefixes = ("/api/admin", "/api/audit-logs", "/api/heatmap", "/admin/charts")' in source


def test_unhealthy_admin_health_uses_503_without_exception_text(
    client, auth_headers_admin, monkeypatch
):
    async def fail_health_checks():
        raise RuntimeError("internal-health-secret")

    monkeypatch.setattr(main.health_checker, "run_health_checks", fail_health_checks)
    response = client.get("/api/health", headers=auth_headers_admin)
    assert response.status_code == 503
    assert response.json()["status"] == "unhealthy"
    assert "internal-health-secret" not in response.text


def test_metrics_failure_uses_503_without_exception_text(
    client, auth_headers_admin, monkeypatch
):
    def fail_metrics(_minutes):
        raise RuntimeError("internal-metrics-secret")

    monkeypatch.setattr(main.performance_monitor, "get_recent_metrics", fail_metrics)
    response = client.get("/api/metrics", headers=auth_headers_admin)
    assert response.status_code == 503
    assert response.json() == {"error": "Metrics unavailable"}
    assert "internal-metrics-secret" not in response.text


def test_scaling_failure_uses_503_without_exception_text(
    client, auth_headers_admin, monkeypatch
):
    def fail_history(_hours):
        raise RuntimeError("internal-scaling-secret")

    monkeypatch.setattr(main.auto_scaler, "get_scaling_history", fail_history)
    response = client.get("/api/scaling/history", headers=auth_headers_admin)
    assert response.status_code == 503
    assert response.json() == {"error": "Scaling history unavailable"}
    assert "internal-scaling-secret" not in response.text
