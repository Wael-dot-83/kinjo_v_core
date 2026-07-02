def test_admin_dashboard_api_returns_dashboard_contract(client, auth_headers_admin):
    response = client.get("/api/admin/dashboard", headers=auth_headers_admin)
    assert response.status_code == 200

    payload = response.json()
    for key in ("summary", "system_overview", "kindergartens", "charts", "alerts", "kpi_trends", "generated_at"):
        assert key in payload

    if payload["kindergartens"]:
        first = payload["kindergartens"][0]
        for key in (
            "id",
            "name_ar",
            "status",
            "license_status",
            "enrollments",
            "attendance_today",
            "pending_reports",
                "capacity_utilization",
            ):
                assert key in first


def test_decision_support_dashboard_contract_admin(client, auth_headers_admin, sample_enrollment):
    response = client.get("/api/dashboard/decision-support", headers=auth_headers_admin)
    assert response.status_code == 200

    payload = response.json()
    for key in (
        "total_kindergartens",
        "total_children",
        "total_capacity",
        "network_utilization_pct",
        "network_attendance_pct",
        "geo_distribution",
        "classification_bands",
        "capacity_tiers",
        "predictions",
        "risk_items",
        "enrollment_funnel",
        "age_group_distribution",
    ):
        assert key in payload

    assert payload["total_kindergartens"] == 1
    assert payload["total_children"] == 1
    assert payload["total_capacity"] == 20
    assert payload["geo_distribution"][0]["total_enrolled"] == 1
    assert payload["enrollment_funnel"]["active"] == 1


def test_decision_support_dashboard_scopes_to_manager_kindergarten(
    client, auth_headers_manager, sample_enrollment
):
    response = client.get("/api/dashboard/decision-support", headers=auth_headers_manager)
    assert response.status_code == 200

    payload = response.json()
    assert payload["total_kindergartens"] == 1
    assert payload["total_children"] == 1


def test_decision_support_dashboard_rejects_supervisor(client, auth_headers_supervisor):
    response = client.get("/api/dashboard/decision-support", headers=auth_headers_supervisor)
    assert response.status_code == 403
