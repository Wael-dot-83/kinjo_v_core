from datetime import date, timedelta

import models


def test_admin_reports_overview_shape(client, auth_headers_admin, sample_kindergarten, sample_class, sample_enrollment, sample_supervisor_assignment):
    resp = client.get("/api/admin/reports/overview?level=jordan", headers=auth_headers_admin)
    assert resp.status_code == 200
    body = resp.json()
    assert body["report_type"] == "overview"
    assert body["level"] == "jordan"
    assert "kpis" in body
    assert "children" in body
    assert "quality" in body
    assert "interpretation" in body


def test_admin_reports_admin_only(client, auth_headers_manager, sample_kindergarten):
    resp = client.get("/api/admin/reports/overview?level=jordan", headers=auth_headers_manager)
    assert resp.status_code == 403


def test_city_level_requires_city_filter(client, auth_headers_admin, sample_kindergarten):
    resp = client.get(
        "/api/admin/reports/children/summary?level=city&governorate=Amman",
        headers=auth_headers_admin,
    )
    assert resp.status_code == 422


def test_age_buckets_returns_distribution(client, auth_headers_admin, sample_kindergarten, sample_class, sample_enrollment):
    resp = client.get("/api/admin/reports/children/age-buckets?level=jordan", headers=auth_headers_admin)
    assert resp.status_code == 200
    body = resp.json()
    assert "age_buckets" in body
    assert len(body["age_buckets"]) == 19
    assert "invalid_reasons" in body


def test_age_buckets_flags_too_young_child(
    client,
    auth_headers_admin,
    test_db,
    sample_kindergarten,
    sample_class,
    parent_user,
):
    from unittest.mock import patch

    # The report flags "too_young" only when age_days < 1 (born on the report's
    # "today"). We anchor the report's _today() to a safely-past date and give
    # the child that exact DOB: the child reads as 0 days old (too_young) while
    # the DOB stays <= CURRENT_DATE, so it never trips ck_children_dob_not_future
    # (CURRENT_DATE is UTC in SQLite; local date.today() can be a day ahead).
    dob = date.today() - timedelta(days=10)
    with patch("validators.validate_child_age_strict"), \
         patch("admin_reports_api._today", return_value=dob):
        child = models.Child(
            parent_id=parent_user.parent_profile.id,
            first_name="Baby",
            last_name="Young",
            gender=models.Gender.MALE,
            date_of_birth=dob,
            father_name="Father Young",
            mother_first_name="Mother",
            mother_last_name="Young",
            mother_nationality="Jordanian",
            media_consent=True,
        )
        test_db.add(child)
        test_db.commit()
        test_db.refresh(child)

        enrollment = models.EnrollmentApplication(
            child_id=child.id,
            kindergarten_id=sample_kindergarten.id,
            class_id=sample_class.id,
            status=models.EnrollmentStatus.ACTIVE,
            source="WEB",
        )
        test_db.add(enrollment)
        test_db.commit()

        today_str = date.today().isoformat()
        resp = client.get(f"/api/admin/reports/children/age-buckets?level=jordan&date_to={today_str}", headers=auth_headers_admin)
        assert resp.status_code == 200
        body = resp.json()
        assert body["invalid_reasons"]["too_young"] >= 1


def test_data_quality_and_compliance_endpoints(
    client,
    auth_headers_admin,
    sample_kindergarten,
    sample_class,
    sample_enrollment,
    sample_supervisor_assignment,
):
    dq = client.get("/api/admin/reports/data-quality?level=jordan", headers=auth_headers_admin)
    assert dq.status_code == 200
    dq_body = dq.json()
    assert "data_quality_score" in dq_body
    assert "issues" in dq_body

    comp = client.get("/api/admin/reports/compliance?level=jordan", headers=auth_headers_admin)
    assert comp.status_code == 200
    comp_body = comp.json()
    assert "compliance_score" in comp_body
    assert "violations" in comp_body


def test_risk_ranking_and_drilldown(
    client,
    auth_headers_admin,
    sample_kindergarten,
    sample_class,
    sample_enrollment,
):
    ranking = client.get("/api/admin/reports/risk-ranking?level=jordan", headers=auth_headers_admin)
    assert ranking.status_code == 200
    rank_body = ranking.json()
    assert "ranking" in rank_body
    assert isinstance(rank_body["ranking"], list)

    drilldown = client.get(
        f"/api/admin/reports/drilldown?level=kindergarten&governorate=Amman&city=Amman&kindergarten_id={sample_kindergarten.id}",
        headers=auth_headers_admin,
    )
    assert drilldown.status_code == 200
    d_body = drilldown.json()
    assert d_body["report_type"] == "drilldown"
    assert d_body["level"] == "kindergarten"


def test_export_csv_success(client, auth_headers_admin):
    response = client.get(
        "/api/admin/reports/export",
        headers=auth_headers_admin,
        params={"report_type": "overview", "export_format": "csv", "level": "jordan"},
    )
    assert response.status_code == 200
    assert "text/csv" in response.headers.get("content-type", "")
    assert "content-disposition" in {k.lower(): v for k, v in response.headers.items()}


def test_export_requires_admin(client):
    response = client.get("/api/admin/reports/export", params={"report_type": "overview", "export_format": "csv"})
    assert response.status_code in (401, 403)


def test_overview_city_level_requires_city_filter(client, auth_headers_admin):
    response = client.get(
        "/api/admin/reports/overview",
        headers=auth_headers_admin,
        params={"level": "city"},
    )
    assert response.status_code == 422
    assert "city" in response.json()["detail"].lower()


def test_geography_lookups_reports(client, auth_headers_admin, sample_kindergarten):
    # Test reports lookup
    resp = client.get("/api/admin/reports/geography/districts?governorate=Amman", headers=auth_headers_admin)
    assert resp.status_code == 200
    assert "Amman" in resp.json()["districts"]

    resp = client.get("/api/admin/reports/geography/areas?governorate=Amman&district=Amman", headers=auth_headers_admin)
    assert resp.status_code == 200
    assert "Abdoun" in resp.json()["areas"]


def test_geography_lookups_analytics(client, auth_headers_admin, sample_kindergarten):
    # Test analytics lookup
    resp = client.get("/api/admin/analytics/districts?governorate=Amman", headers=auth_headers_admin)
    assert resp.status_code == 200
    assert "Amman" in resp.json()["districts"]

    resp = client.get("/api/admin/analytics/areas?governorate=Amman&district=Amman", headers=auth_headers_admin)
    assert resp.status_code == 200
    assert "Abdoun" in resp.json()["areas"]


def test_district_area_analytics_detail(client, auth_headers_admin, sample_kindergarten):
    resp = client.get("/api/admin/analytics/district/Amman", headers=auth_headers_admin)
    assert resp.status_code == 200
    assert resp.json()["layer"] == "district"

    resp = client.get("/api/admin/analytics/area/Abdoun", headers=auth_headers_admin)
    assert resp.status_code == 200
    assert resp.json()["layer"] == "area"


def test_area_level_requires_area_filter(client, auth_headers_admin):
    resp = client.get(
        "/api/admin/reports/overview?level=area&governorate=Amman&city=Amman",
        headers=auth_headers_admin,
    )
    assert resp.status_code == 422
    assert "area" in resp.json()["detail"].lower()


def test_reports_with_area_filtering(client, auth_headers_admin, sample_kindergarten, sample_class, sample_enrollment):
    resp = client.get(
        "/api/admin/reports/overview?level=area&governorate=Amman&city=Amman&area=Abdoun",
        headers=auth_headers_admin,
    )
    assert resp.status_code == 200
    assert resp.json()["level"] == "area"

    # Test geography endpoint contains areas and doesn't crash
    resp_geo = client.get(
        "/api/admin/reports/children/geography?level=area&governorate=Amman&city=Amman&area=Abdoun",
        headers=auth_headers_admin,
    )
    assert resp_geo.status_code == 200
    data_geo = resp_geo.json()
    assert "areas" in data_geo
    assert len(data_geo["areas"]) > 0
    assert data_geo["areas"][0]["area"] == "Abdoun"

    # Test kindergartens classification endpoint returns filters
    resp_class = client.get(
        "/api/admin/reports/kindergartens/classification?level=area&governorate=Amman&city=Amman&area=Abdoun",
        headers=auth_headers_admin,
    )
    assert resp_class.status_code == 200
    data_class = resp_class.json()
    assert "filters" in data_class
    assert data_class["filters"]["area"] == "Abdoun"
    assert data_class["filters"]["city"] == "Amman"
    assert data_class["filters"]["governorate"] == "Amman"

