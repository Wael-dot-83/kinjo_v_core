"""
Tests for the admin dashboard USWDS redesign contract additions.

Verifies backward-compatible new fields on /api/admin/dashboard:
- hero_status
- mission_kpis
- action_center
- security_summary
- government_readiness
- activity_summary
"""


def _create_admin(db):
    from auth import get_password_hash
    import models
    user = models.User(
        username="redesign_admin",
        email="redesign_admin@test.com",
        hashed_password=get_password_hash("Admin123!"),
        role=models.UserRole.ADMIN,
        status=models.UserStatus.ACTIVE,
    )
    db.add(user)
    db.commit()
    db.refresh(user)
    return user


def _get_token(client, username, password="Admin123!"):
    r = client.post("/token", data={"username": username, "password": password})
    assert r.status_code == 200
    return r.json()["access_token"]


def test_admin_dashboard_includes_redesign_fields(client, test_db):
    _create_admin(test_db)
    token = _get_token(client, "redesign_admin")
    r = client.get("/api/admin/dashboard", headers={"Authorization": f"Bearer {token}"})
    assert r.status_code == 200
    data = r.json()
    assert "summary" in data
    assert "system_overview" in data
    assert "kpi_trends" in data
    assert "hero_status" in data
    assert "mission_kpis" in data
    assert "action_center" in data
    assert "security_summary" in data
    assert "government_readiness" in data
    assert "activity_summary" in data


def test_hero_status_has_expected_shape(client, test_db):
    _create_admin(test_db)
    token = _get_token(client, "redesign_admin")
    r = client.get("/api/admin/dashboard", headers={"Authorization": f"Bearer {token}"})
    assert r.status_code == 200
    data = r.json()
    hero = data.get("hero_status") or {}
    assert "status" in hero
    assert hero["status"] in {"healthy", "degraded", "critical"}
    assert "all_services_available" in hero
    assert "requests_needing_review" in hero


def test_mission_kpis_include_core_labels(client, test_db):
    _create_admin(test_db)
    token = _get_token(client, "redesign_admin")
    r = client.get("/api/admin/dashboard", headers={"Authorization": f"Bearer {token}"})
    assert r.status_code == 200
    data = r.json()
    kpis = data.get("mission_kpis") or []
    keys = {k.get("key") for k in kpis}
    assert "kindergartens" in keys
    assert "children" in keys
    assert "data_quality" in keys
    for kpi in kpis:
        assert "label_ar" in kpi
        assert "label_en" in kpi
        assert "value" in kpi
        assert "icon" in kpi
        assert "color" in kpi


def test_action_center_items_have_shape(client, test_db):
    _create_admin(test_db)
    token = _get_token(client, "redesign_admin")
    r = client.get("/api/admin/dashboard", headers={"Authorization": f"Bearer {token}"})
    assert r.status_code == 200
    data = r.json()
    items = data.get("action_center") or []
    assert len(items) >= 4
    for item in items:
        assert "id" in item
        assert "count" in item
        assert "severity" in item
        assert item["severity"] in {"info", "warning", "error"}
        assert "action_url" in item


def test_security_summary_has_counts(client, test_db):
    _create_admin(test_db)
    token = _get_token(client, "redesign_admin")
    r = client.get("/api/admin/dashboard", headers={"Authorization": f"Bearer {token}"})
    assert r.status_code == 200
    data = r.json()
    sec = data.get("security_summary") or {}
    assert "failed_logins_24h" in sec
    assert "critical_incidents_count" in sec
    assert sec["failed_logins_24h"] >= 0
    assert sec["critical_incidents_count"] >= 0


def test_government_readiness_has_agencies(client, test_db):
    _create_admin(test_db)
    token = _get_token(client, "redesign_admin")
    r = client.get("/api/admin/dashboard", headers={"Authorization": f"Bearer {token}"})
    assert r.status_code == 200
    data = r.json()
    gov = data.get("government_readiness") or []
    assert len(gov) >= 3
    for item in gov:
        assert "agency_ar" in item
        assert "status" in item
        assert item["status"] in {"ready", "needs_data", "needs_review"}


def test_activity_summary_counts_are_non_negative(client, test_db):
    _create_admin(test_db)
    token = _get_token(client, "redesign_admin")
    r = client.get("/api/admin/dashboard", headers={"Authorization": f"Bearer {token}"})
    assert r.status_code == 200
    data = r.json()
    act = data.get("activity_summary") or {}
    assert act.get("logins_today", -1) >= 0
    assert act.get("failed_logins_today", -1) >= 0
    assert act.get("user_changes_today", -1) >= 0
    assert act.get("exports_today", -1) >= 0


def test_dashboard_response_backward_compatible_with_existing_keys(client, test_db):
    _create_admin(test_db)
    token = _get_token(client, "redesign_admin")
    r = client.get("/api/admin/dashboard", headers={"Authorization": f"Bearer {token}"})
    assert r.status_code == 200
    data = r.json()
    for key in ("summary", "system_overview", "kindergartens", "charts", "alerts", "kpis", "kpi_trends", "data_quality_reasons", "recent_activity", "generated_at"):
        assert key in data, f"missing backward-compatible key: {key}"
