def test_admin_dashboard_api_returns_dashboard_contract(client, auth_headers_admin):
    response = client.get("/api/admin/dashboard", headers=auth_headers_admin)
    assert response.status_code == 200

    payload = response.json()
    for key in ("summary", "system_overview", "kindergartens", "charts", "alerts", "kpi_cards", "generated_at"):
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
