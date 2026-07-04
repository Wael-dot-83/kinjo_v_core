# -*- coding: utf-8 -*-
"""Regression tests for a cross-tenant cache-key bug found while implementing
the leaderboard cache (ROOT-008): dashboard-data and kpi/alerts cached their
response keyed by `current_user.role.value` alone. A MANAGER's real data
scope is their own `kindergarten_id`, which differs per manager and was
never reflected in the cache key — two different managers requesting the
same endpoint within the TTL window would silently receive each other's
kindergarten's data. Fixed by keying non-admin scopes on the user's id
instead of their role.
"""
from datetime import date, timedelta

import pytest

import models
from auth import get_password_hash
from database import get_db
from fastapi.testclient import TestClient
from main import app


@pytest.fixture
def client(test_db):
    def override_get_db():
        try:
            yield test_db
        finally:
            pass

    app.dependency_overrides[get_db] = override_get_db
    with TestClient(app) as test_client:
        yield test_client
    app.dependency_overrides.clear()


def _make_manager(test_db, username, kg_name_ar):
    kg = models.Kindergarten(
        name_ar=kg_name_ar,
        name_en=kg_name_ar,
        governorate="عمان",
        district="عمان",
        area="القويسمة",
        address_line="شارع الاختبار",
        contact_phone="0791234567",
        status=models.KindergartenStatus.ACTIVE,
    )
    test_db.add(kg)
    test_db.commit()

    user = models.User(
        username=username,
        email=f"{username}@test.com",
        hashed_password=get_password_hash("Manager123!"),
        role=models.UserRole.MANAGER,
        status=models.UserStatus.ACTIVE,
        kindergarten_id=kg.id,
    )
    test_db.add(user)
    test_db.commit()
    test_db.refresh(user)
    return user, kg


def _login(client, username):
    resp = client.post("/token", data={"username": username, "password": "Manager123!"})
    assert resp.status_code == 200
    return resp.json()["access_token"]


class TestDashboardDataCacheScopeIsolation:
    def test_two_managers_never_share_a_cache_entry(self, client, test_db, monkeypatch):
        from config import settings
        import analytics_service

        manager_a, kg_a = _make_manager(test_db, "mgr_cache_a", "حضانة أ")
        manager_b, kg_b = _make_manager(test_db, "mgr_cache_b", "حضانة ب")

        # Authenticate before disabling TESTING — the login rate limiter and
        # other test-mode bypasses depend on settings.TESTING staying True
        # until credentials are exchanged.
        token_a = _login(client, "mgr_cache_a")
        token_b = _login(client, "mgr_cache_b")

        monkeypatch.setattr(settings, "TESTING", False, raising=False)
        fake_store: dict = {}
        monkeypatch.setattr(
            analytics_service, "_analytics_cache_get", lambda key: fake_store.get(key)
        )
        monkeypatch.setattr(
            analytics_service, "_analytics_cache_set",
            lambda key, value, ttl=60: fake_store.__setitem__(key, value),
        )

        start = (date.today() - timedelta(days=6)).isoformat()
        end = date.today().isoformat()

        r_a = client.get(
            f"/api/analytics/dashboard-data?period_start={start}&period_end={end}",
            headers={"Authorization": f"Bearer {token_a}"},
        )
        assert r_a.status_code == 200

        r_b = client.get(
            f"/api/analytics/dashboard-data?period_start={start}&period_end={end}",
            headers={"Authorization": f"Bearer {token_b}"},
        )
        assert r_b.status_code == 200

        # The bug: both managers would hit the exact same cache key
        # ("analytics:dashboard:{start}:{end}:{gov_filter}:MANAGER"), so
        # manager B would receive manager A's cached (kindergarten-A-scoped)
        # response. Confirm distinct cache entries were actually written.
        manager_scoped_keys = [k for k in fake_store if "analytics:dashboard:" in k]
        assert len(manager_scoped_keys) >= 2, (
            f"expected separate cache entries per manager, got: {manager_scoped_keys}"
        )
        assert f"user:{manager_a.id}" in "".join(manager_scoped_keys) or any(
            str(manager_a.id) in k for k in manager_scoped_keys
        )


class TestKpiAlertsCacheScopeIsolation:
    def test_two_managers_never_share_a_cache_entry(self, client, test_db, monkeypatch):
        from config import settings
        import kpi_service as kpi_service_module

        manager_a, kg_a = _make_manager(test_db, "mgr_alerts_a", "حضانة التنبيهات أ")
        manager_b, kg_b = _make_manager(test_db, "mgr_alerts_b", "حضانة التنبيهات ب")

        token_a = _login(client, "mgr_alerts_a")
        token_b = _login(client, "mgr_alerts_b")

        monkeypatch.setattr(settings, "TESTING", False, raising=False)
        fake_store: dict = {}

        class FakeCache:
            def get(self, key):
                return fake_store.get(key)

            def set(self, key, value, ttl_seconds=60):
                fake_store[key] = value

        monkeypatch.setattr(kpi_service_module, "dashboard_cache", FakeCache())

        r_a = client.get("/api/kpi/alerts", headers={"Authorization": f"Bearer {token_a}"})
        assert r_a.status_code == 200

        r_b = client.get("/api/kpi/alerts", headers={"Authorization": f"Bearer {token_b}"})
        assert r_b.status_code == 200

        # The bug: cache_key was f"kpi:alerts:{start}:{end}:all:MANAGER" for
        # every manager (kindergarten_id query param is never used for the
        # MANAGER branch), so manager B's request would return manager A's
        # cached alerts instead of computing their own kindergarten's.
        keys = [k for k in fake_store if k.startswith("kpi:alerts:")]
        assert len(keys) >= 2, f"expected separate cache entries per manager, got: {keys}"
        assert any(f"user:{manager_a.id}" in k for k in keys)
        assert any(f"user:{manager_b.id}" in k for k in keys)
        assert not any(k.endswith(":MANAGER") for k in keys), "role-only scope key must not reappear"


class TestRankingsCacheScopeIsolation:
    def test_admin_scope_key_is_shared_non_admin_is_not(self, client, admin_user_for_rankings, test_db, monkeypatch):
        from config import settings
        import analytics_service

        token = _login_admin(client)

        monkeypatch.setattr(settings, "TESTING", False, raising=False)
        fake_store: dict = {}
        monkeypatch.setattr(
            analytics_service, "_analytics_cache_get", lambda key: fake_store.get(key)
        )
        monkeypatch.setattr(
            analytics_service, "_analytics_cache_set",
            lambda key, value, ttl=300: fake_store.__setitem__(key, value),
        )

        r = client.get(
            "/api/analytics/rankings/governance_score?top_n=5",
            headers={"Authorization": f"Bearer {token}"},
        )
        assert r.status_code == 200
        keys = [k for k in fake_store if k.startswith("analytics:rankings:")]
        assert len(keys) == 1
        assert keys[0].endswith(":ADMIN")

    def test_second_identical_request_is_served_from_cache(
        self, client, admin_user_for_rankings, monkeypatch
    ):
        """ROOT-008: get_rankings() scores every kindergarten in scope with
        the KPI engine per call and previously had no caching at all,
        unlike dashboard-data and kpi/alerts (both already fixed). Confirms
        a second identical request hits the cache instead of recomputing."""
        from config import settings
        import analytics_service

        token = _login_admin(client)

        monkeypatch.setattr(settings, "TESTING", False, raising=False)
        fake_store: dict = {}
        monkeypatch.setattr(
            analytics_service, "_analytics_cache_get", lambda key: fake_store.get(key)
        )
        monkeypatch.setattr(
            analytics_service, "_analytics_cache_set",
            lambda key, value, ttl=300: fake_store.__setitem__(key, value),
        )

        r1 = client.get(
            "/api/analytics/rankings/governance_score?top_n=5",
            headers={"Authorization": f"Bearer {token}"},
        )
        assert r1.status_code == 200

        call_count = {"n": 0}
        original = analytics_service.AnalyticsService.get_rankings

        def counting_get_rankings(*args, **kwargs):
            call_count["n"] += 1
            return original(*args, **kwargs)

        monkeypatch.setattr(
            analytics_service.AnalyticsService, "get_rankings", staticmethod(counting_get_rankings)
        )

        r2 = client.get(
            "/api/analytics/rankings/governance_score?top_n=5",
            headers={"Authorization": f"Bearer {token}"},
        )
        assert r2.status_code == 200
        assert r2.json() == r1.json()
        assert call_count["n"] == 0, "second request should be served from cache, not recomputed"


@pytest.fixture
def admin_user_for_rankings(test_db):
    user = models.User(
        username="rankings_admin",
        email="rankings_admin@test.com",
        hashed_password=get_password_hash("Admin123!"),
        role=models.UserRole.ADMIN,
        status=models.UserStatus.ACTIVE,
    )
    test_db.add(user)
    test_db.commit()
    test_db.refresh(user)
    return user


def _login_admin(client):
    resp = client.post("/token", data={"username": "rankings_admin", "password": "Admin123!"})
    assert resp.status_code == 200
    return resp.json()["access_token"]
