"""
Comprehensive tests for the admin reporting and decision-support API.
"""
from datetime import date, timedelta

import models
from validators import calculate_required_supervisors


def test_kindergartens_detail_city_level(client, auth_headers_admin, sample_kindergarten, sample_class, sample_enrollment, sample_supervisor_assignment):
    resp = client.get(
        "/admin/reports/kindergartens/detail",
        headers=auth_headers_admin,
        params={"level": "city", "governorate": "Amman", "city": "Amman"},
    )
    assert resp.status_code == 200
    body = resp.json()
    assert "kindergartens" in body
    assert "summary" in body
    assert "interpretation" in body
    assert len(body["kindergartens"]) >= 1
    kg = body["kindergartens"][0]
    assert "children_count" in kg
    assert "supervisors_count" in kg
    assert "risk_status" in kg
    assert "classification" in kg
    assert "recommended_action_ar" in kg
    assert "recommended_action_en" in kg


def test_kindergartens_detail_governorate_level(client, auth_headers_admin, sample_kindergarten, sample_class, sample_enrollment):
    resp = client.get(
        "/admin/reports/kindergartens/detail",
        headers=auth_headers_admin,
        params={"level": "governorate", "governorate": "Amman"},
    )
    assert resp.status_code == 200
    body = resp.json()
    assert "kindergartens" in body
    assert len(body["kindergartens"]) >= 1


def test_kindergartens_detail_requires_admin(client, auth_headers_manager, sample_kindergarten):
    resp = client.get(
        "/admin/reports/kindergartens/detail",
        headers=auth_headers_manager,
        params={"level": "city", "governorate": "Amman", "city": "Amman"},
    )
    assert resp.status_code == 403


def test_classes_detail_requires_kindergarten_id(client, auth_headers_admin):
    resp = client.get(
        "/admin/reports/classes/detail",
        headers=auth_headers_admin,
        params={"level": "kindergarten"},
    )
    assert resp.status_code == 422


def test_classes_detail_kindergarten_level(client, auth_headers_admin, sample_kindergarten, sample_class, sample_enrollment, sample_supervisor_assignment):
    resp = client.get(
        "/admin/reports/classes/detail",
        headers=auth_headers_admin,
        params={"level": "kindergarten", "kindergarten_id": sample_kindergarten.id},
    )
    assert resp.status_code == 200
    body = resp.json()
    assert "classes" in body
    assert "summary" in body
    assert "interpretation" in body
    cls = body["classes"][0]
    assert "children_count" in cls
    assert "supervisors_count" in cls
    assert "required_supervisors" in cls
    assert "supervisor_gap" in cls
    assert "risk_status" in cls
    assert "recommended_action_ar" in cls
    assert "recommended_action_en" in cls


def test_supervisors_analytics_jordan_level(client, auth_headers_admin, sample_kindergarten, sample_class, sample_enrollment, sample_supervisor_assignment):
    resp = client.get(
        "/admin/reports/supervisors/analytics",
        headers=auth_headers_admin,
        params={"level": "jordan"},
    )
    assert resp.status_code == 200
    body = resp.json()
    assert "total_supervisors" in body
    assert "supervisors" in body
    assert "supervisors_with_errors" in body
    assert "error_table" in body
    assert "interpretation" in body


def test_supervisors_analytics_detects_errors(client, auth_headers_admin, test_db, sample_kindergarten):
    supervisor = models.User(
        username="errorsupervisor",
        email="error@test.com",
        hashed_password="x",
        role=models.UserRole.SUPERVISOR,
        status=models.UserStatus.ACTIVE,
        kindergarten_id=sample_kindergarten.id,
    )
    test_db.add(supervisor)
    test_db.commit()
    test_db.refresh(supervisor)

    another_kg = models.Kindergarten(
        name_ar="روضة أخرى",
        name_en="Another KG",
        governorate="Amman",
        district="Amman",
        area="Area",
        address_line="123 St",
        contact_phone="+962791234567",
        status=models.KindergartenStatus.ACTIVE,
    )
    test_db.add(another_kg)
    test_db.commit()
    test_db.refresh(another_kg)

    another_class = models.Class(
        kindergarten_id=another_kg.id,
        name_ar="فصل آخر",
        name_en="Another Class",
        class_code="A002",
        age_group="AGE_2_4",
        capacity_total=20,
        min_age_months=24,
        max_age_months=48,
        is_active=True,
    )
    test_db.add(another_class)
    test_db.commit()
    test_db.refresh(another_class)

    assignment = models.SupervisorAssignment(
        class_id=another_class.id,
        supervisor_id=supervisor.id,
        is_primary=True,
        full_time_dedication=True,
        start_date=date.today(),
    )
    test_db.add(assignment)
    test_db.commit()

    resp = client.get(
        "/admin/reports/supervisors/analytics",
        headers=auth_headers_admin,
        params={"level": "jordan"},
    )
    assert resp.status_code == 200
    body = resp.json()
    assert "supervisors" in body
    assert any(s["id"] == supervisor.id for s in body["supervisors"])


def test_kindergartens_classification(client, auth_headers_admin, sample_kindergarten, sample_class, sample_enrollment):
    resp = client.get(
        "/admin/reports/kindergartens/classification",
        headers=auth_headers_admin,
        params={"level": "governorate", "governorate": "Amman"},
    )
    assert resp.status_code == 200
    body = resp.json()
    assert "kindergartens" in body
    assert "classification_counts" in body
    assert "interpretation" in body


def test_kindergarten_detail_classifications(client, auth_headers_admin, sample_kindergarten):
    resp = client.get(
        "/admin/reports/kindergartens/detail",
        headers=auth_headers_admin,
        params={"level": "kindergarten", "kindergarten_id": sample_kindergarten.id},
    )
    assert resp.status_code == 200
    body = resp.json()
    kg = body["kindergartens"][0]
    assert kg["classification"] in {
        "inactive", "resource_underuse", "critical_risk", "normal",
        "under_supervised", "capacity_class_pressure", "over_capacity", "operational_issue",
    }


def test_classes_detail_supervisor_gap(client, auth_headers_admin, test_db, sample_kindergarten, parent_user):
    cls = models.Class(
        kindergarten_id=sample_kindergarten.id,
        name_ar="فصل اختبار",
        name_en="Test Class",
        class_code="T001",
        age_group="AGE_1_2",
        capacity_total=10,
        min_age_months=12,
        max_age_months=24,
        is_active=True,
    )
    test_db.add(cls)
    test_db.commit()
    test_db.refresh(cls)

    child = models.Child(
        parent_id=parent_user.parent_profile.id,
        first_name="Child",
        last_name="Test",
        gender=models.Gender.MALE,
        date_of_birth=date.today() - timedelta(days=400),
        father_name="Father",
        mother_first_name="Mother",
        mother_last_name="Test",
        mother_nationality="Jordanian",
        media_consent=True,
    )
    test_db.add(child)
    test_db.commit()
    test_db.refresh(child)

    enrollment = models.EnrollmentApplication(
        child_id=child.id,
        kindergarten_id=sample_kindergarten.id,
        class_id=cls.id,
        status=models.EnrollmentStatus.ACTIVE,
        source="WEB",
    )
    test_db.add(enrollment)
    test_db.commit()

    resp = client.get(
        "/admin/reports/classes/detail",
        headers=auth_headers_admin,
        params={"level": "kindergarten", "kindergarten_id": sample_kindergarten.id},
    )
    assert resp.status_code == 200
    body = resp.json()
    assert len(body["classes"]) >= 1
    cls_row = next((c for c in body["classes"] if c["id"] == cls.id), None)
    assert cls_row is not None
    assert cls_row["children_count"] == 1
    assert cls_row["supervisors_count"] == 0
    assert cls_row["risk_status"] == "critical"


def test_export_kindergartens_detail_csv(client, auth_headers_admin):
    response = client.get(
        "/admin/reports/export",
        headers=auth_headers_admin,
        params={"report_type": "kindergartens_detail", "export_format": "csv", "level": "jordan"},
    )
    assert response.status_code == 200
    assert "text/csv" in response.headers.get("content-type", "")


def test_export_supervisors_analytics_csv(client, auth_headers_admin):
    response = client.get(
        "/admin/reports/export",
        headers=auth_headers_admin,
        params={"report_type": "supervisors_analytics", "export_format": "csv", "level": "jordan"},
    )
    assert response.status_code == 200
    assert "text/csv" in response.headers.get("content-type", "")


def test_export_kindergartens_classification_csv(client, auth_headers_admin):
    response = client.get(
        "/admin/reports/export",
        headers=auth_headers_admin,
        params={"report_type": "kindergartens_classification", "export_format": "csv", "level": "governorate", "governorate": "Amman"},
    )
    assert response.status_code == 200
    assert "text/csv" in response.headers.get("content-type", "")


def test_kindergarten_detail_empty_scope(client, auth_headers_admin):
    resp = client.get(
        "/admin/reports/kindergartens/detail",
        headers=auth_headers_admin,
        params={"level": "city", "governorate": "NonExistent", "city": "NoWhere"},
    )
    assert resp.status_code == 200
    body = resp.json()
    assert body["kindergartens"] == []
    assert body["summary"]["total_kindergartens"] == 0


def test_supervisors_analytics_empty_scope(client, auth_headers_admin):
    resp = client.get(
        "/admin/reports/supervisors/analytics",
        headers=auth_headers_admin,
        params={"level": "jordan"},
    )
    assert resp.status_code == 200
    body = resp.json()
    assert "error_table" in body
    assert isinstance(body["error_table"], list)


def test_admin_reports_overview_shape_with_new_fields(client, auth_headers_admin, sample_kindergarten, sample_class, sample_enrollment, sample_supervisor_assignment):
    resp = client.get("/admin/reports/overview?level=jordan", headers=auth_headers_admin)
    assert resp.status_code == 200
    body = resp.json()
    assert body["report_type"] == "overview"
    assert "kpis" in body
    assert "children" in body
    assert "quality" in body
    assert "interpretation" in body


def test_children_summary_city_level(client, auth_headers_admin, sample_kindergarten, sample_class, sample_enrollment):
    resp = client.get(
        "/admin/reports/children/summary?level=city&governorate=Amman&city=Amman",
        headers=auth_headers_admin,
    )
    assert resp.status_code == 200
    body = resp.json()
    assert "kpis" in body
    assert "tables" in body


def test_children_geography(client, auth_headers_admin, sample_kindergarten):
    resp = client.get(
        "/admin/reports/children/geography?level=jordan",
        headers=auth_headers_admin,
    )
    assert resp.status_code == 200
    body = resp.json()
    assert "governorates" in body


def test_kindergartens_summary_city_level(client, auth_headers_admin, sample_kindergarten, sample_class, sample_enrollment):
    resp = client.get(
        "/admin/reports/kindergartens/summary?level=city&governorate=Amman&city=Amman",
        headers=auth_headers_admin,
    )
    assert resp.status_code == 200
    body = resp.json()
    assert "kpis" in body


def test_supervisors_coverage_city_level(client, auth_headers_admin, sample_kindergarten, sample_class, sample_enrollment):
    resp = client.get(
        "/admin/reports/supervisors/coverage?level=city&governorate=Amman&city=Amman",
        headers=auth_headers_admin,
    )
    assert resp.status_code == 200
    body = resp.json()
    assert "kpis" in body


def test_drilldown_kindergarten_level(client, auth_headers_admin, sample_kindergarten, sample_class, sample_enrollment):
    resp = client.get(
        f"/admin/reports/drilldown?level=kindergarten&governorate=Amman&city=Amman&kindergarten_id={sample_kindergarten.id}",
        headers=auth_headers_admin,
    )
    assert resp.status_code == 200
    body = resp.json()
    assert "level" in body
    assert body["level"] == "kindergarten"


def test_data_quality_city_level(client, auth_headers_admin, sample_kindergarten):
    resp = client.get(
        "/admin/reports/data-quality?level=city&governorate=Amman&city=Amman",
        headers=auth_headers_admin,
    )
    assert resp.status_code == 200
    body = resp.json()
    assert "data_quality_score" in body
    assert "status" in body


def test_compliance_city_level(client, auth_headers_admin, sample_kindergarten):
    resp = client.get(
        "/admin/reports/compliance?level=city&governorate=Amman&city=Amman",
        headers=auth_headers_admin,
    )
    assert resp.status_code == 200
    body = resp.json()
    assert "compliance_score" in body
    assert "violations" in body
    assert body["status"] in {"green", "yellow", "orange", "red"}


def test_risk_ranking_city_level(client, auth_headers_admin, sample_kindergarten):
    resp = client.get(
        "/admin/reports/risk-ranking?level=city&governorate=Amman&city=Amman",
        headers=auth_headers_admin,
    )
    assert resp.status_code == 200
    body = resp.json()
    assert "ranking" in body
    assert isinstance(body["ranking"], list)


def test_export_json_format(client, auth_headers_admin):
    response = client.get(
        "/admin/reports/export",
        headers=auth_headers_admin,
        params={"report_type": "overview", "export_format": "json", "level": "jordan"},
    )
    assert response.status_code == 200
    assert response.headers.get("content-type", "").startswith("application/json")


def test_children_age_buckets_has_dominant_bucket(client, auth_headers_admin, sample_kindergarten, sample_class, sample_enrollment):
    resp = client.get("/admin/reports/children/age-buckets?level=jordan", headers=auth_headers_admin)
    assert resp.status_code == 200
    body = resp.json()
    assert "dominant_bucket" in body


def test_children_gender_percentages(client, auth_headers_admin, sample_kindergarten, sample_class, sample_enrollment):
    resp = client.get("/admin/reports/children/gender?level=jordan", headers=auth_headers_admin)
    assert resp.status_code == 200
    body = resp.json()
    assert "percentages" in body
    pct = body["percentages"]
    assert "male_pct" in pct
    assert "female_pct" in pct
    assert "unknown_pct" in pct
    assert "gender_balance_ratio" in pct


def test_kindergartens_supervision_endpoint(client, auth_headers_admin, sample_kindergarten, sample_class, sample_enrollment):
    resp = client.get("/admin/reports/kindergartens/supervision?level=jordan", headers=auth_headers_admin)
    assert resp.status_code == 200
    body = resp.json()
    assert "required_supervisors" in body
    assert "actual_supervisors" in body
    assert "supervisor_gap" in body


def test_admin_reports_admin_only_all_endpoints(client, auth_headers_manager, sample_kindergarten):
    endpoints = [
        "/admin/reports/overview?level=jordan",
        "/admin/reports/children/summary?level=jordan",
        "/admin/reports/children/geography?level=jordan",
        "/admin/reports/children/age-buckets?level=jordan",
        "/admin/reports/children/gender?level=jordan",
        "/admin/reports/kindergartens/summary?level=jordan",
        "/admin/reports/kindergartens/supervision?level=jordan",
        "/admin/reports/supervisors/coverage?level=jordan",
        "/admin/reports/data-quality?level=jordan",
        "/admin/reports/compliance?level=jordan",
        "/admin/reports/risk-ranking?level=jordan",
        "/admin/reports/kindergartens/detail?level=city&governorate=Amman&city=Amman",
        "/admin/reports/supervisors/analytics?level=jordan",
        "/admin/reports/kindergartens/classification?level=governorate&governorate=Amman",
    ]
    for endpoint in endpoints:
        resp = client.get(endpoint, headers=auth_headers_manager)
        assert resp.status_code == 403, f"Expected 403 for {endpoint}, got {resp.status_code}"


def test_city_level_requires_city_filter_all_endpoints(client, auth_headers_admin, sample_kindergarten):
    endpoints_missing_city = [
        "/admin/reports/children/summary?level=city&governorate=Amman",
        "/admin/reports/kindergartens/summary?level=city&level=city&governorate=Amman",
    ]
    for endpoint in endpoints_missing_city:
        resp = client.get(endpoint, headers=auth_headers_admin)
        assert resp.status_code == 422, f"Expected 422 for {endpoint}, got {resp.status_code}"


def test_empty_data_quality_returns_score(client, auth_headers_admin):
    resp = client.get("/admin/reports/data-quality?level=jordan", headers=auth_headers_admin)
    assert resp.status_code == 200
    body = resp.json()
    assert "data_quality_score" in body
    assert "status" in body
    assert body["status"] in {"green", "yellow", "orange", "red"}


def test_empty_compliance_returns_score(client, auth_headers_admin):
    resp = client.get("/admin/reports/compliance?level=jordan", headers=auth_headers_admin)
    assert resp.status_code == 200
    body = resp.json()
    assert "compliance_score" in body
    assert "status" in body
    assert body["status"] in {"green", "yellow", "orange", "red"}
