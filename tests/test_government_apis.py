"""tests/test_government_apis.py — Integration tests for Government Data Portal endpoints.

Endpoints covered:
  4.2  GET /api/ministry/enrollment-forecast
       GET /api/ministry/enrollment-forecast/export.csv
  4.3  GET /api/family/quality-certificates
  4.4  GET /api/development/dashboard
  4.5  GET /api/census/child-density

All tests run against the in-memory SQLite database configured in conftest.py.
Dialect-aware code paths in government_api.py handle SQLite vs PostgreSQL.

Usage:
    pytest tests/test_government_apis.py -v
"""
import os
import sys
from datetime import date, datetime, timedelta

import pytest
from fastapi.testclient import TestClient

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
os.environ.setdefault("TESTING", "true")

from auth import get_password_hash, create_access_token
import models


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _admin_token(user: models.User) -> str:
    return create_access_token(data={"sub": user.username})


def _auth_headers(token: str) -> dict:
    return {"Authorization": f"Bearer {token}"}


def _make_kindergarten(db, *, gov: str = "عمان", area: str = "ضاحية الرشيد") -> models.Kindergarten:
    kg = models.Kindergarten(
        name_ar="روضة الأمل",
        name_en="Hope Kindergarten",
        license_number="LIC-GOV-001",
        governorate=gov,
        city="Amman",
        area=area,
        address_line="1 Government St",
        contact_phone="+962791000001",
        contact_email="gov@test.jo",
        status=models.KindergartenStatus.ACTIVE,
        license_valid_until=date(2027, 12, 31),
    )
    db.add(kg)
    db.flush()
    return kg


def _make_admin_user(db, *, username: str = "govadmin") -> models.User:
    user = models.User(
        username=username,
        email=f"{username}@test.com",
        hashed_password=get_password_hash("Admin123!"),
        role=models.UserRole.ADMIN,
        status=models.UserStatus.ACTIVE,
    )
    db.add(user)
    db.flush()
    return user


def _make_parent_and_child(
    db,
    *,
    gov: str = "عمان",
    area: str = "ضاحية الرشيد",
    age_days: int = 2000,
) -> tuple:
    """Return (parent_user, parent_profile, child)."""
    parent_user = models.User(
        username=f"parent_{age_days}@test.com",
        email=f"parent_{age_days}@test.com",
        hashed_password=get_password_hash("Parent123!"),
        role=models.UserRole.PARENT,
        status=models.UserStatus.ACTIVE,
    )
    db.add(parent_user)
    db.flush()

    profile = models.ParentProfile(
        user_id=parent_user.id,
        first_name="Hana",
        last_name="Mansour",
        phone_number="+962791000002",
        gender=models.Gender.FEMALE,
        nationality="Jordanian",
        national_id=f"100{age_days}",
        home_governorate=gov,
        home_city="Amman",
        home_area=area,
        home_address_line="2 Test St",
        correspondence_preference=True,
    )
    db.add(profile)
    db.flush()

    dob = date.today() - timedelta(days=age_days)
    child = models.Child(
        parent_id=profile.id,
        first_name="Noor",
        last_name="Mansour",
        gender=models.Gender.FEMALE,
        date_of_birth=dob,
        father_name="Khalil Mansour",
        mother_first_name="Hana",
        mother_last_name="Mansour",
        mother_nationality="Jordanian",
        mother_national_id=f"200{age_days}",
    )
    db.add(child)
    db.flush()
    return parent_user, profile, child


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture()
def gov_setup(test_db):
    """Seed a complete government-API scenario and return a dict of objects."""
    kg = _make_kindergarten(test_db)
    admin = _make_admin_user(test_db)

    # Parent + child aged ~3 years (within kindergarten age limit of 56 months)
    _, profile, child = _make_parent_and_child(test_db, age_days=1100)

    # Supervisor user to record attendance
    supervisor = models.User(
        username="govsupervisor@test.com",
        email="govsupervisor@test.com",
        hashed_password=get_password_hash("Super123!"),
        role=models.UserRole.SUPERVISOR,
        status=models.UserStatus.ACTIVE,
        kindergarten_id=kg.id,
    )
    test_db.add(supervisor)
    test_db.flush()

    # Class in the kindergarten
    cls = models.Class(
        name_ar="الفصل أ",
        name_en="Class A",
        class_code="GOV-A-001",
        kindergarten_id=kg.id,
        capacity_total=20,
        age_group="AGE_2_4",
        min_age_months=24,
        max_age_months=48,
    )
    test_db.add(cls)
    test_db.flush()

    # Enrollment
    enrollment = models.EnrollmentApplication(
        child_id=child.id,
        kindergarten_id=kg.id,
        class_id=cls.id,
        status=models.EnrollmentStatus.ACTIVE,
        enrollment_start_date=date.today() - timedelta(days=30),
        source="online",
    )
    test_db.add(enrollment)
    test_db.flush()

    # Operating calendar — 10 open days in the last 30 days
    for delta in range(1, 11):
        test_db.add(models.OperatingCalendar(
            kindergarten_id=kg.id,
            date=date.today() - timedelta(days=delta),
            is_open=True,
        ))

    # Attendance log — child was present on 5 of those days
    for delta in range(1, 6):
        test_db.add(models.AttendanceLog(
            child_id=child.id,
            class_id=cls.id,
            date=date.today() - timedelta(days=delta),
            status=models.AttendanceStatus.PRESENT,
            check_in_at=datetime.now() - timedelta(days=delta),
            recorded_by=supervisor.id,
        ))

    # Daily report
    test_db.add(models.DailyReport(
        child_id=child.id,
        kindergarten_id=kg.id,
        date=date.today() - timedelta(days=1),
        status=models.DailyReportStatus.SUBMITTED,
        submitted_by=admin.id,
        arrival_time="08:00",
        leave_time="14:00",
        activities="Free play and circle time",
        notes="Great day",
        breakfast=True,
        snack=True,
        milk=True,
        lunch=True,
    ))

    # Survey + response
    survey = models.Survey(
        kindergarten_id=kg.id,
        title="Monthly Satisfaction Survey",
        start_date=date.today() - timedelta(days=30),
        end_date=date.today() + timedelta(days=30),
    )
    test_db.add(survey)
    test_db.flush()

    test_db.add(models.SurveyResponse(
        survey_id=survey.id,
        parent_id=profile.user_id,
        nps_score=8,
    ))

    test_db.commit()
    return {
        "kg":       kg,
        "admin":    admin,
        "child":    child,
        "profile":  profile,
        "token":    _admin_token(admin),
    }


# ---------------------------------------------------------------------------
# 4.2  Enrollment forecast — JSON
# ---------------------------------------------------------------------------

class TestEnrollmentForecast:
    def test_returns_200_with_forecast_keys(self, gov_setup, client):
        token = gov_setup["token"]
        resp = client.get(
            "/api/ministry/enrollment-forecast",
            headers=_auth_headers(token),
            params={"year": date.today().year + 1},
        )
        assert resp.status_code == 200, resp.text
        body = resp.json()
        assert "year" in body
        assert "forecasts" in body
        assert isinstance(body["forecasts"], list)

    def test_forecast_row_contains_expected_fields(self, gov_setup, client):
        token = gov_setup["token"]
        resp = client.get(
            "/api/ministry/enrollment-forecast",
            headers=_auth_headers(token),
        )
        assert resp.status_code == 200
        body = resp.json()
        if body["forecasts"]:
            row = body["forecasts"][0]
            for key in ("governorate", "predicted_count", "confidence_lower", "confidence_upper"):
                assert key in row, f"Missing key: {key}"

    def test_forecast_unauthenticated_returns_401_or_403(self, gov_setup, client):
        resp = client.get("/api/ministry/enrollment-forecast")
        assert resp.status_code in (401, 403)

    def test_forecast_default_year_is_next_year(self, gov_setup, client):
        token = gov_setup["token"]
        resp = client.get(
            "/api/ministry/enrollment-forecast",
            headers=_auth_headers(token),
        )
        assert resp.status_code == 200
        assert resp.json()["year"] == date.today().year + 1

    def test_forecast_year_param_respected(self, gov_setup, client):
        token = gov_setup["token"]
        resp = client.get(
            "/api/ministry/enrollment-forecast",
            headers=_auth_headers(token),
            params={"year": 2030},
        )
        assert resp.status_code == 200
        assert resp.json()["year"] == 2030


# ---------------------------------------------------------------------------
# 4.2  Enrollment forecast — CSV export
# ---------------------------------------------------------------------------

class TestEnrollmentForecastCSV:
    def test_csv_returns_200_and_content_type(self, gov_setup, client):
        token = gov_setup["token"]
        resp = client.get(
            "/api/ministry/enrollment-forecast/export.csv",
            headers=_auth_headers(token),
        )
        assert resp.status_code == 200, resp.text
        assert "text/csv" in resp.headers.get("content-type", "")

    def test_csv_unauthenticated_returns_401_or_403(self, gov_setup, client):
        resp = client.get("/api/ministry/enrollment-forecast/export.csv")
        assert resp.status_code in (401, 403)

    def test_csv_has_header_row(self, gov_setup, client):
        token = gov_setup["token"]
        resp = client.get(
            "/api/ministry/enrollment-forecast/export.csv",
            headers=_auth_headers(token),
        )
        assert resp.status_code == 200
        content = resp.text
        assert "governorate" in content
        assert "predicted_count" in content


# ---------------------------------------------------------------------------
# 4.3  Quality certificate
# ---------------------------------------------------------------------------

class TestQualityCertificates:
    def test_returns_200_with_score_rating_valid_until(self, gov_setup, client):
        kg_id = gov_setup["kg"].id
        token = gov_setup["token"]
        resp = client.get(
            "/api/family/quality-certificates",
            headers=_auth_headers(token),
            params={"nursery_id": kg_id},
        )
        assert resp.status_code == 200, resp.text
        body = resp.json()
        assert "score" in body
        assert "rating" in body
        assert "valid_until" in body

    def test_score_is_between_0_and_100(self, gov_setup, client):
        kg_id = gov_setup["kg"].id
        token = gov_setup["token"]
        resp = client.get(
            "/api/family/quality-certificates",
            headers=_auth_headers(token),
            params={"nursery_id": kg_id},
        )
        assert resp.status_code == 200
        score = resp.json()["score"]
        assert 0.0 <= score <= 100.0

    def test_rating_is_valid_string(self, gov_setup, client):
        kg_id = gov_setup["kg"].id
        token = gov_setup["token"]
        resp = client.get(
            "/api/family/quality-certificates",
            headers=_auth_headers(token),
            params={"nursery_id": kg_id},
        )
        assert resp.status_code == 200
        assert resp.json()["rating"] in ("Excellent", "Good", "Average", "Poor")

    def test_valid_until_is_365_days_from_now(self, gov_setup, client):
        kg_id = gov_setup["kg"].id
        token = gov_setup["token"]
        resp = client.get(
            "/api/family/quality-certificates",
            headers=_auth_headers(token),
            params={"nursery_id": kg_id},
        )
        assert resp.status_code == 200
        valid_until = date.fromisoformat(resp.json()["valid_until"])
        expected = date.today() + timedelta(days=365)
        assert valid_until == expected

    def test_breakdown_contains_components(self, gov_setup, client):
        kg_id = gov_setup["kg"].id
        token = gov_setup["token"]
        resp = client.get(
            "/api/family/quality-certificates",
            headers=_auth_headers(token),
            params={"nursery_id": kg_id},
        )
        assert resp.status_code == 200
        breakdown = resp.json()["breakdown"]
        for key in (
            "incident_rate_score",
            "attendance_score",
            "report_completeness_score",
            "parent_satisfaction_score",
        ):
            assert key in breakdown, f"Missing breakdown key: {key}"

    def test_unknown_nursery_returns_404(self, gov_setup, client):
        token = gov_setup["token"]
        resp = client.get(
            "/api/family/quality-certificates",
            headers=_auth_headers(token),
            params={"nursery_id": 99999},
        )
        assert resp.status_code == 404

    def test_quality_cert_unauthenticated_returns_401_or_403(self, gov_setup, client):
        resp = client.get("/api/family/quality-certificates", params={"nursery_id": 1})
        assert resp.status_code in (401, 403)


# ---------------------------------------------------------------------------
# 4.4  Development dashboard
# ---------------------------------------------------------------------------

class TestDevelopmentDashboard:
    def test_returns_200_with_required_keys(self, gov_setup, client):
        token = gov_setup["token"]
        resp = client.get(
            "/api/development/dashboard",
            headers=_auth_headers(token),
        )
        assert resp.status_code == 200, resp.text
        body = resp.json()
        for key in ("total_nurseries", "total_children", "avg_attendance_pct",
                    "incident_trend", "top5_density_areas"):
            assert key in body, f"Missing key: {key}"

    def test_total_nurseries_is_int(self, gov_setup, client):
        token = gov_setup["token"]
        resp = client.get(
            "/api/development/dashboard",
            headers=_auth_headers(token),
        )
        assert resp.status_code == 200
        assert isinstance(resp.json()["total_nurseries"], int)

    def test_total_children_gte_zero(self, gov_setup, client):
        token = gov_setup["token"]
        resp = client.get(
            "/api/development/dashboard",
            headers=_auth_headers(token),
        )
        assert resp.status_code == 200
        assert resp.json()["total_children"] >= 0

    def test_seeded_nursery_appears_in_count(self, gov_setup, client):
        token = gov_setup["token"]
        resp = client.get(
            "/api/development/dashboard",
            headers=_auth_headers(token),
        )
        assert resp.status_code == 200
        assert resp.json()["total_nurseries"] >= 1

    def test_dashboard_unauthenticated_returns_401_or_403(self, gov_setup, client):
        resp = client.get("/api/development/dashboard")
        assert resp.status_code in (401, 403)


# ---------------------------------------------------------------------------
# 4.5  Child density GeoJSON
# ---------------------------------------------------------------------------

class TestChildDensity:
    def test_returns_200_geojson_feature_collection(self, gov_setup, client):
        token = gov_setup["token"]
        resp = client.get(
            "/api/census/child-density",
            headers=_auth_headers(token),
        )
        assert resp.status_code == 200, resp.text
        body = resp.json()
        assert body["type"] == "FeatureCollection"
        assert "features" in body
        assert isinstance(body["features"], list)

    def test_features_have_geometry_and_properties(self, gov_setup, client):
        token = gov_setup["token"]
        resp = client.get(
            "/api/census/child-density",
            headers=_auth_headers(token),
        )
        assert resp.status_code == 200
        features = resp.json()["features"]
        if features:
            feat = features[0]
            assert "geometry" in feat
            assert "properties" in feat
            assert feat["geometry"]["type"] == "Point"
            assert "density_per_km2" in feat["properties"]

    def test_governorate_filter_returns_matching_features(self, gov_setup, client):
        token = gov_setup["token"]
        resp = client.get(
            "/api/census/child-density",
            headers=_auth_headers(token),
            params={"governorate": "عمان"},
        )
        assert resp.status_code == 200
        body = resp.json()
        for feat in body["features"]:
            assert feat["properties"]["governorate"] == "عمان"

    def test_density_unauthenticated_returns_401_or_403(self, gov_setup, client):
        resp = client.get("/api/census/child-density")
        assert resp.status_code in (401, 403)


# ---------------------------------------------------------------------------
# Audit log
# ---------------------------------------------------------------------------

class TestAuditLogging:
    def test_government_api_requests_are_logged(self, gov_setup, client, test_db):
        token = gov_setup["token"]

        # Trigger one government endpoint
        client.get(
            "/api/development/dashboard",
            headers=_auth_headers(token),
        )

        audit_count = (
            test_db.query(models.AuditLog)
            .filter(models.AuditLog.entity_type == "government_api")
            .count()
        )
        assert audit_count > 0, "Expected at least one audit log entry for government_api"

    def test_multiple_endpoints_each_create_audit_entry(self, gov_setup, client, test_db):
        token = gov_setup["token"]
        kg_id = gov_setup["kg"].id

        endpoints = [
            ("/api/development/dashboard", {}),
            ("/api/census/child-density", {}),
            ("/api/family/quality-certificates", {"nursery_id": kg_id}),
        ]
        for path, params in endpoints:
            client.get(path, headers=_auth_headers(token), params=params)

        audit_count = (
            test_db.query(models.AuditLog)
            .filter(models.AuditLog.entity_type == "government_api")
            .count()
        )
        assert audit_count >= 3, (
            f"Expected at least 3 audit entries, found {audit_count}"
        )
