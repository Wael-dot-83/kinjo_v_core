"""Regression tests for the /api/health reachability probe.

The front-end connectivity heartbeat (static/js/admin_components.js) pings
``HEAD /api/health`` on every admin-area page and shows the Arabic reconnect
banner whenever the response is not ``ok``. That probe must therefore succeed
for *any* authenticated role, not just ADMIN — otherwise managers/supervisors
see a permanent false "server unreachable" banner (fixed in commit f3ac641).

The comprehensive ``GET /api/health`` (system internals) stays admin-only.
"""


class TestHealthProbeHead:
    """HEAD /api/health — reachability probe, must accept any authenticated user."""

    def test_head_health_ok_for_manager(self, client, auth_headers_manager):
        resp = client.head("/api/health", headers=auth_headers_manager)
        assert resp.status_code == 200
        assert resp.headers.get("X-Health") == "OK"

    def test_head_health_ok_for_admin(self, client, auth_headers_admin):
        resp = client.head("/api/health", headers=auth_headers_admin)
        assert resp.status_code == 200
        assert resp.headers.get("X-Health") == "OK"

    def test_head_health_ok_for_supervisor(self, client, auth_headers_supervisor):
        resp = client.head("/api/health", headers=auth_headers_supervisor)
        assert resp.status_code == 200

    def test_head_health_unauthenticated_rejected(self, client):
        # No session -> banner *should* show; probe must not silently pass.
        resp = client.head("/api/health")
        assert resp.status_code == 401


class TestHealthProbeGet:
    """GET /api/health — comprehensive internals, must stay admin-only."""

    def test_get_health_forbidden_for_manager(self, client, auth_headers_manager):
        resp = client.get("/api/health", headers=auth_headers_manager)
        assert resp.status_code == 403

    def test_get_health_ok_for_admin(self, client, auth_headers_admin):
        resp = client.get("/api/health", headers=auth_headers_admin)
        assert resp.status_code == 200
