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


def test_dashboard_summary_forces_manager_kindergarten_scope(
    client, auth_headers_manager, sample_kindergarten, sample_enrollment
):
    response = client.post(
        "/api/dashboard/summary",
        headers=auth_headers_manager,
        json={"range": "week", "kindergarten_id": sample_kindergarten.id + 999},
    )

    assert response.status_code == 404

    own_response = client.post(
        "/api/dashboard/summary",
        headers=auth_headers_manager,
        json={"range": "week"},
    )
    assert own_response.status_code == 200
    assert own_response.json()["children"] == 1


def test_dashboard_summary_forces_supervisor_scope_and_rejects_parents(
    client,
    auth_headers_supervisor,
    auth_headers_parent,
    sample_enrollment,
):
    supervisor_response = client.post(
        "/api/dashboard/summary",
        headers=auth_headers_supervisor,
        json={"range": "week"},
    )
    assert supervisor_response.status_code == 200
    assert supervisor_response.json()["children"] == 1

    parent_response = client.post(
        "/api/dashboard/summary",
        headers=auth_headers_parent,
        json={"range": "week"},
    )
    assert parent_response.status_code == 403


def test_suggested_actions_are_scoped_to_manager_kindergarten(
    client,
    auth_headers_manager,
    test_db,
    sample_child,
    sample_enrollment,
):
    import models

    other_kindergarten = models.Kindergarten(
        name_ar="حضانة أخرى",
        name_en="Other Kindergarten",
        license_number="LIC-DASHBOARD-SCOPE",
        governorate="Amman",
        district="Amman",
        area="Shmeisani",
        address_line="Other address",
        contact_phone="+962790000001",
        contact_email="other-dashboard@test.invalid",
        status=models.KindergartenStatus.ACTIVE,
    )
    test_db.add(other_kindergarten)
    test_db.flush()
    other_child = models.Child(
        parent_id=sample_child.parent_id,
        first_name="Other",
        last_name="Child",
        gender=models.Gender.FEMALE,
        date_of_birth=sample_child.date_of_birth,
        father_name="Other Father",
        mother_first_name="Other",
        mother_last_name="Mother",
        mother_nationality="Jordanian",
        mother_national_id="DASHBOARD-SCOPE-MOTHER",
        media_consent=False,
    )
    test_db.add(other_child)
    test_db.flush()
    test_db.add(
        models.EnrollmentApplication(
            child_id=other_child.id,
            kindergarten_id=other_kindergarten.id,
            status=models.EnrollmentStatus.PENDING_REVIEW,
            source="WEB",
        )
    )
    test_db.commit()

    response = client.get(
        "/api/dashboard/suggested-actions", headers=auth_headers_manager
    )

    assert response.status_code == 200
    pending_action = next(
        item for item in response.json()["data"] if item["id"] == "pending_enrollments"
    )
    assert pending_action["pending_count"] == 0


def test_dashboard_summary_attendance_matches_the_canonical_definition(
    client,
    auth_headers_manager,
    test_db,
    sample_child,
    sample_enrollment,
    manager_user,
):
    """The dashboard summary now uses the one canonical attendance definition.

    This test used to assert that the summary scoped attendance by the CLASS a log was
    recorded in (so a child enrolled here but marked present in another kindergarten's
    class counted as 0). That was an inline quirk of the old summary endpoint. Every
    other attendance surface — kg-overview, the KPI dashboard, the analytics services —
    attributes attendance by ENROLLMENT (the child is enrolled here and was physically
    present), via KPIService, and reports 100 for this scenario.

    The summary was routed through that same canonical definition to end the 333% window
    scaling, so it now agrees: attendance is enrollment-scoped everywhere. In normal data
    (attendance recorded in the enrolled kindergarten's own classes) the two scopings are
    identical; they differ only for cross-kindergarten attendance logs, which are a data
    anomaly. Consistency across surfaces is the point of this branch, so the summary is
    pinned to the canonical value rather than to the old per-endpoint behavior.
    """
    from datetime import date

    import models
    from kpi_service import KPIService

    other_kindergarten = models.Kindergarten(
        name_ar="حضانة سجل الحضور",
        name_en="Attendance Scope KG",
        license_number="LIC-ATTENDANCE-SCOPE",
        governorate="Amman",
        district="Amman",
        area="Khalda",
        address_line="Attendance scope address",
        contact_phone="+962790000002",
        contact_email="attendance-scope@example.com",
        status=models.KindergartenStatus.ACTIVE,
    )
    test_db.add(other_kindergarten)
    test_db.flush()
    other_class = models.Class(
        kindergarten_id=other_kindergarten.id,
        name_ar="صف آخر",
        name_en="Other Class",
        class_code="ATT-SCOPE",
        age_group="AGE_1_2",
        capacity_total=20,
        min_age_months=24,
        max_age_months=48,
        is_active=True,
    )
    test_db.add(other_class)
    test_db.flush()
    test_db.add(
        models.AttendanceLog(
            child_id=sample_child.id,
            class_id=other_class.id,
            date=date.today(),
            status=models.AttendanceStatus.PRESENT,
            recorded_by=manager_user.id,
        )
    )
    test_db.commit()

    summary = client.post(
        "/api/dashboard/summary",
        headers=auth_headers_manager,
        json={"range": "today"},
    )
    assert summary.status_code == 200

    # The canonical rate for the manager's kindergarten today: the enrolled child was
    # physically present, so 100 — and the summary must report exactly that.
    canonical = KPIService.compute_attendance_rate(
        test_db, manager_user.kindergarten_id, date.today(), date.today()
    )
    assert canonical == 100.0  # guards the fixture: enrolled + present today
    assert summary.json()["attendance"] == canonical
    assert summary.json()["chart"][-1] == canonical

    # suggested-actions' week-over-week indicator is a separate "% of logged attendance
    # that was present" metric, still scoped to the manager's own classes, so it has no
    # data here — left unchanged by the canonical-rate work.
    actions = client.get(
        "/api/dashboard/suggested-actions", headers=auth_headers_manager
    )
    attendance_action = next(
        item for item in actions.json()["data"] if item["id"] == "attendance_trend"
    )
    assert attendance_action["current_rate"] is None


def test_dashboard_summary_attendance_does_not_scale_with_window(
    client,
    auth_headers_manager,
    test_db,
    sample_child,
    sample_enrollment,
    sample_class,
    manager_user,
):
    """/api/dashboard/summary once divided window-wide PRESENT rows by a single-day
    headcount, so a 'month' view reported attendance far above 100%. It now uses the
    canonical bounded definition, so a multi-day window can never exceed 100%."""
    from datetime import date, timedelta

    import models

    # Enrolled for one working day, present that day only.
    for i in range(20):
        d = date.today() - timedelta(days=i)
        test_db.add(models.AttendanceLog(
            child_id=sample_child.id, class_id=sample_class.id, date=d,
            status=models.AttendanceStatus.PRESENT, recorded_by=manager_user.id,
        ))
    test_db.commit()

    for rng in ("today", "week", "month", "quarter"):
        resp = client.post(
            "/api/dashboard/summary", headers=auth_headers_manager, json={"range": rng},
        )
        assert resp.status_code == 200, resp.text[:200]
        att = resp.json()["attendance"]
        assert 0.0 <= att <= 100.0, f"range={rng} reported attendance={att}%, must be <= 100"
        for point in resp.json()["chart"]:
            assert 0.0 <= point <= 100.0, f"range={rng} trend point {point} out of range"
