"""
Tests for Daily Report Analytics Module
========================================
Covers: summary, charts, export, anomaly, RBAC, sample-data endpoints.
"""
import os
import pytest
import secrets
from datetime import date, datetime, timedelta

os.environ["TESTING"] = "true"

from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from database import Base, get_db
from main import app
from auth import get_password_hash
import models


# ─── Fixtures ─────────────────────────────────────────────────────────────────

@pytest.fixture(scope="function")
def dr_db():
    engine = create_engine("sqlite:///:memory:", connect_args={"check_same_thread": False}, poolclass=StaticPool)
    Base.metadata.create_all(bind=engine)
    Session = sessionmaker(autocommit=False, autoflush=False, bind=engine)
    db = Session()
    try:
        yield db
    finally:
        db.close()
        Base.metadata.drop_all(bind=engine)


@pytest.fixture(scope="function")
def dr_client(dr_db):
    def _override():
        try:
            yield dr_db
        finally:
            pass

    app.dependency_overrides[get_db] = _override
    with TestClient(app) as c:
        yield c
    app.dependency_overrides.clear()


@pytest.fixture
def dr_kindergarten(dr_db):
    kg = models.Kindergarten(
        name_ar="حضانة التحليلات",
        name_en="Analytics KG",
        governorate="Amman",
        district="Amman",
        area="Downtown",
        address_line="1 Main St",
        contact_phone="+962790000000",
        status=models.KindergartenStatus.ACTIVE,
    )
    dr_db.add(kg)
    dr_db.commit()
    dr_db.refresh(kg)
    return kg


@pytest.fixture
def dr_admin(dr_db):
    u = models.User(
        username="dr_admin",
        email="dr_admin@test.com",
        hashed_password=get_password_hash("Admin123!"),
        role=models.UserRole.ADMIN,
        status=models.UserStatus.ACTIVE,
    )
    dr_db.add(u)
    dr_db.commit()
    dr_db.refresh(u)
    return u


@pytest.fixture
def dr_manager(dr_db, dr_kindergarten):
    u = models.User(
        username="dr_manager",
        email="dr_manager@test.com",
        hashed_password=get_password_hash("Manager123!"),
        role=models.UserRole.MANAGER,
        kindergarten_id=dr_kindergarten.id,
        status=models.UserStatus.ACTIVE,
    )
    dr_db.add(u)
    dr_db.commit()
    dr_db.refresh(u)
    return u


@pytest.fixture
def dr_supervisor(dr_db, dr_kindergarten):
    u = models.User(
        username="dr_supervisor",
        email="dr_supervisor@test.com",
        hashed_password=get_password_hash("Supervisor123!"),
        role=models.UserRole.SUPERVISOR,
        kindergarten_id=dr_kindergarten.id,
        status=models.UserStatus.ACTIVE,
    )
    dr_db.add(u)
    dr_db.flush()
    dr_db.add(models.SupervisorProfile(user_id=u.id, kindergarten_id=dr_kindergarten.id))
    dr_db.commit()
    dr_db.refresh(u)
    return u


@pytest.fixture
def dr_parent(dr_db):
    u = models.User(
        username="dr_parent@test.com",
        email="dr_parent@test.com",
        hashed_password=get_password_hash("Parent123!"),
        role=models.UserRole.PARENT,
        status=models.UserStatus.ACTIVE,
    )
    dr_db.add(u)
    dr_db.commit()
    dr_db.refresh(u)

    profile = models.ParentProfile(
        user_id=u.id,
        first_name="Test",
        last_name="Parent",
        phone_number="+962790000001",
        gender=models.Gender.MALE,
        nationality="Jordanian",
        national_id="9999999999",
        home_governorate="Amman",
        home_district="Amman",
        home_area="Abdoun",
        home_address_line="2 Main St",
        correspondence_preference=True,
    )
    dr_db.add(profile)
    dr_db.commit()
    dr_db.refresh(profile)
    u.parent_profile = profile
    dr_db.commit()
    dr_db.refresh(u)
    return u


def _make_child(dr_db, parent_profile_id, kindergarten_id, first_name="طفل"):
    child = models.Child(
        parent_id=parent_profile_id,
        first_name=first_name,
        last_name="تجربة",
        gender=models.Gender.MALE,
        date_of_birth=date(2022, 6, 15),
        father_name="أب",
        mother_first_name="أم",
        mother_last_name="أم",
        mother_nationality="Jordanian",
        media_consent=True,
    )
    dr_db.add(child)
    dr_db.commit()
    dr_db.refresh(child)
    return child


def _make_daily_report(dr_db, child_id, kindergarten_id, submitted_by, report_date,
                       status=models.DailyReportStatus.APPROVED, mood="happy",
                       breakfast=True, lunch=True, snack=True, milk=True,
                       nap_duration=60, bathroom_count=2,
                       rejected_reason=None, health_notes=None):
    """Helper to create a single DailyReport row."""
    r = models.DailyReport(
        child_id=child_id,
        kindergarten_id=kindergarten_id,
        date=report_date,
        status=status,
        submitted_by=submitted_by,
        arrival_time="07:30",
        leave_time="13:00",
        mood=mood,
        health_notes=health_notes,
        breakfast=breakfast,
        snack=snack,
        milk=milk,
        lunch=lunch,
        nap_start="11:00",
        nap_end="12:00",
        nap_duration_minutes=nap_duration,
        bathroom_count=bathroom_count,
        diaper_wet=False,
        diaper_soiled=False,
        activities="لعب حر",
        rejected_reason=rejected_reason,
        submitted_at=datetime(report_date.year, report_date.month, report_date.day, 14, 0, 0) if status != models.DailyReportStatus.DRAFT else None,
        approved_at=datetime(report_date.year, report_date.month, report_date.day, 16, 0, 0) if status in (models.DailyReportStatus.APPROVED, models.DailyReportStatus.SENT_TO_PARENT) else None,
    )
    dr_db.add(r)
    dr_db.commit()
    dr_db.refresh(r)
    return r


@pytest.fixture
def seeded_reports(dr_db, dr_kindergarten, dr_parent, dr_admin):
    """Create 5 children × 3 days = 15 daily reports."""
    children = []
    for i in range(5):
        c = _make_child(dr_db, dr_parent.parent_profile.id, dr_kindergarten.id, first_name=f"طفل{i}")
        children.append(c)

    reports = []
    base_date = date(2026, 2, 1)
    moods = ["happy", "happy", "normal", "sad", "sick"]
    statuses = [
        models.DailyReportStatus.APPROVED,
        models.DailyReportStatus.SENT_TO_PARENT,
        models.DailyReportStatus.APPROVED,
        models.DailyReportStatus.REJECTED,
        models.DailyReportStatus.DRAFT,
    ]

    for day_offset in range(3):
        d = base_date + timedelta(days=day_offset)
        for idx, child in enumerate(children):
            r = _make_daily_report(
                dr_db, child.id, dr_kindergarten.id, dr_admin.id, d,
                status=statuses[idx],
                mood=moods[idx],
                breakfast=(idx != 3),
                lunch=True,
                nap_duration=30 + idx * 15,
                bathroom_count=idx,
                rejected_reason="بيانات ناقصة" if statuses[idx] == models.DailyReportStatus.REJECTED else None,
                health_notes="حرارة خفيفة" if moods[idx] == "sick" else None,
            )
            reports.append(r)

    return children, reports


def _auth_headers(client, username, password):
    resp = client.post("/token", data={"username": username, "password": password})
    assert resp.status_code == 200
    token = resp.json()["access_token"]
    csrf = secrets.token_hex(32)
    return {
        "Authorization": f"Bearer {token}",
        "X-CSRF-Token": csrf,
        "Cookie": f"kinjo_csrf_token={csrf}",
    }


# ─── Tests ────────────────────────────────────────────────────────────────────

class TestSummaryEndpoint:
    """GET /api/reports-analytics/summary"""

    def test_admin_gets_summary(self, dr_client, seeded_reports, dr_admin):
        headers = _auth_headers(dr_client, "dr_admin", "Admin123!")
        resp = dr_client.get(
            "/api/reports-analytics/summary",
            params={"date_from": "2026-02-01", "date_to": "2026-02-03"},
            headers=headers,
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["total_reports"] == 15
        assert "attendance" in data
        assert "mood_trends" in data
        assert "meal_completion" in data
        assert "nap_analytics" in data
        assert "diaper_bathroom" in data
        assert "workflow_metrics" in data
        assert "health_flags" in data
        assert "status_funnel" in data

    def test_empty_range_returns_zero(self, dr_client, seeded_reports, dr_admin):
        headers = _auth_headers(dr_client, "dr_admin", "Admin123!")
        resp = dr_client.get(
            "/api/reports-analytics/summary",
            params={"date_from": "2030-01-01", "date_to": "2030-01-05"},
            headers=headers,
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["total_reports"] == 0
        assert data["meal_completion"]["breakfast"] is None
        assert data["nap_analytics"]["avg_duration"] is None
        assert data["nap_analytics"]["nap_rate"] is None
        assert data["workflow_metrics"]["avg_approval_hours"] is None
        assert data["workflow_metrics"]["rejection_rate"] is None
        assert data["health_flags"]["sick_rate"] is None
        assert data["diaper_bathroom"]["avg_bathroom"] is None
        assert data["diaper_bathroom"]["wet_rate"] is None
        assert data["diaper_bathroom"]["soiled_rate"] is None

    def test_filter_by_kindergarten(self, dr_client, seeded_reports, dr_admin, dr_kindergarten):
        headers = _auth_headers(dr_client, "dr_admin", "Admin123!")
        resp = dr_client.get(
            "/api/reports-analytics/summary",
            params={
                "date_from": "2026-02-01",
                "date_to": "2026-02-03",
                "kindergarten_id": dr_kindergarten.id,
            },
            headers=headers,
        )
        assert resp.status_code == 200
        assert resp.json()["total_reports"] == 15

    def test_attendance_values(self, dr_client, seeded_reports, dr_admin):
        headers = _auth_headers(dr_client, "dr_admin", "Admin123!")
        resp = dr_client.get(
            "/api/reports-analytics/summary",
            params={"date_from": "2026-02-01", "date_to": "2026-02-03"},
            headers=headers,
        )
        att = resp.json()["attendance"]
        assert att["avg_arrival"] == "07:30"
        assert att["avg_leave"] == "13:00"

    def test_mood_distribution(self, dr_client, seeded_reports, dr_admin):
        headers = _auth_headers(dr_client, "dr_admin", "Admin123!")
        resp = dr_client.get(
            "/api/reports-analytics/summary",
            params={"date_from": "2026-02-01", "date_to": "2026-02-03"},
            headers=headers,
        )
        moods = resp.json()["mood_trends"]["overall"]
        # 2 happy + 1 normal + 1 sad + 1 sick per day × 3 days
        assert moods.get("happy", 0) > 0
        assert moods.get("sick", 0) > 0


class TestChartsEndpoint:
    """GET /api/reports-analytics/charts"""

    def test_charts_returns_all_keys(self, dr_client, seeded_reports, dr_admin):
        headers = _auth_headers(dr_client, "dr_admin", "Admin123!")
        resp = dr_client.get(
            "/api/reports-analytics/charts",
            params={"date_from": "2026-02-01", "date_to": "2026-02-03"},
            headers=headers,
        )
        assert resp.status_code == 200
        charts = resp.json()["charts"]
        expected_keys = [
            "mood_pie", "mood_line", "meal_bar", "meal_trend",
            "status_funnel", "attendance_line", "rejection_bar",
            "nap_histogram", "diaper_trend",
        ]
        for key in expected_keys:
            assert key in charts, f"Missing chart: {key}"

    def test_charts_plotly_structure(self, dr_client, seeded_reports, dr_admin):
        headers = _auth_headers(dr_client, "dr_admin", "Admin123!")
        resp = dr_client.get(
            "/api/reports-analytics/charts",
            params={"date_from": "2026-02-01", "date_to": "2026-02-03"},
            headers=headers,
        )
        charts = resp.json()["charts"]
        for key, chart in charts.items():
            assert "data" in chart, f"Chart {key} missing 'data'"

    def test_empty_charts(self, dr_client, dr_admin):
        headers = _auth_headers(dr_client, "dr_admin", "Admin123!")
        resp = dr_client.get(
            "/api/reports-analytics/charts",
            params={"date_from": "2030-01-01", "date_to": "2030-01-05"},
            headers=headers,
        )
        assert resp.status_code == 200
        assert resp.json()["charts"] == {}


class TestExportEndpoint:
    """GET /api/reports-analytics/export"""

    def test_export_csv(self, dr_client, seeded_reports, dr_admin):
        headers = _auth_headers(dr_client, "dr_admin", "Admin123!")
        resp = dr_client.get(
            "/api/reports-analytics/export",
            params={"date_from": "2026-02-01", "date_to": "2026-02-03", "format": "csv"},
            headers=headers,
        )
        assert resp.status_code == 200
        assert "text/csv" in resp.headers.get("content-type", "")
        body = resp.text
        # CSV should have BOM + header row
        assert "id" in body or "child_name" in body or "arrival_time" in body

    def test_export_json(self, dr_client, seeded_reports, dr_admin):
        headers = _auth_headers(dr_client, "dr_admin", "Admin123!")
        resp = dr_client.get(
            "/api/reports-analytics/export",
            params={"date_from": "2026-02-01", "date_to": "2026-02-03", "format": "json"},
            headers=headers,
        )
        assert resp.status_code == 200
        assert "application/json" in resp.headers.get("content-type", "")
        data = resp.json()
        assert isinstance(data, list)
        assert len(data) == 15

    def test_export_no_data_404(self, dr_client, dr_admin):
        headers = _auth_headers(dr_client, "dr_admin", "Admin123!")
        resp = dr_client.get(
            "/api/reports-analytics/export",
            params={"date_from": "2030-01-01", "date_to": "2030-01-05", "format": "csv"},
            headers=headers,
        )
        assert resp.status_code == 404


class TestAnomaliesEndpoint:
    """GET /api/reports-analytics/anomalies"""

    def test_anomalies_detected(self, dr_client, seeded_reports, dr_admin):
        headers = _auth_headers(dr_client, "dr_admin", "Admin123!")
        resp = dr_client.get(
            "/api/reports-analytics/anomalies",
            params={"date_from": "2026-02-01", "date_to": "2026-02-03"},
            headers=headers,
        )
        assert resp.status_code == 200
        assert "anomalies" in resp.json()
        assert isinstance(resp.json()["anomalies"], list)

    def test_anomalies_empty_range(self, dr_client, dr_admin):
        headers = _auth_headers(dr_client, "dr_admin", "Admin123!")
        resp = dr_client.get(
            "/api/reports-analytics/anomalies",
            params={"date_from": "2030-01-01", "date_to": "2030-01-05"},
            headers=headers,
        )
        assert resp.status_code == 200
        assert resp.json()["anomalies"] == []


class TestSampleDataEndpoint:
    """GET /api/reports-analytics/sample-data"""

    def test_sample_data_limit(self, dr_client, seeded_reports, dr_admin):
        headers = _auth_headers(dr_client, "dr_admin", "Admin123!")
        resp = dr_client.get(
            "/api/reports-analytics/sample-data",
            params={"date_from": "2026-02-01", "date_to": "2026-02-03", "limit": 5},
            headers=headers,
        )
        assert resp.status_code == 200
        data = resp.json()
        assert len(data["rows"]) == 5
        assert data["total"] == 15

    def test_sample_data_empty(self, dr_client, dr_admin):
        headers = _auth_headers(dr_client, "dr_admin", "Admin123!")
        resp = dr_client.get(
            "/api/reports-analytics/sample-data",
            params={"date_from": "2030-01-01", "date_to": "2030-01-05"},
            headers=headers,
        )
        assert resp.status_code == 200
        assert resp.json()["rows"] == []
        assert resp.json()["total"] == 0


class TestSQLQueriesEndpoint:
    """GET /api/reports-analytics/sql-queries"""

    def test_admin_sees_sql(self, dr_client, dr_admin):
        headers = _auth_headers(dr_client, "dr_admin", "Admin123!")
        resp = dr_client.get("/api/reports-analytics/sql-queries", headers=headers)
        assert resp.status_code == 200
        queries = resp.json()["queries"]
        assert "1_daily_attendance" in queries
        assert "2_status_funnel" in queries

    def test_manager_forbidden_sql(self, dr_client, dr_manager, dr_kindergarten):
        headers = _auth_headers(dr_client, "dr_manager", "Manager123!")
        resp = dr_client.get("/api/reports-analytics/sql-queries", headers=headers)
        assert resp.status_code == 403


class TestRBAC:
    """Role-based access control tests."""

    def test_parent_forbidden_summary(self, dr_client, dr_parent):
        headers = _auth_headers(dr_client, "dr_parent@test.com", "Parent123!")
        resp = dr_client.get(
            "/api/reports-analytics/summary",
            params={"date_from": "2026-02-01", "date_to": "2026-02-03"},
            headers=headers,
        )
        assert resp.status_code == 403

    def test_parent_forbidden_charts(self, dr_client, dr_parent):
        headers = _auth_headers(dr_client, "dr_parent@test.com", "Parent123!")
        resp = dr_client.get(
            "/api/reports-analytics/charts",
            params={"date_from": "2026-02-01", "date_to": "2026-02-03"},
            headers=headers,
        )
        assert resp.status_code == 403

    def test_parent_forbidden_export(self, dr_client, dr_parent):
        headers = _auth_headers(dr_client, "dr_parent@test.com", "Parent123!")
        resp = dr_client.get(
            "/api/reports-analytics/export",
            params={"date_from": "2026-02-01", "date_to": "2026-02-03"},
            headers=headers,
        )
        assert resp.status_code == 403

    def test_manager_scoped_to_own_kg(self, dr_client, seeded_reports, dr_manager, dr_kindergarten):
        headers = _auth_headers(dr_client, "dr_manager", "Manager123!")
        resp = dr_client.get(
            "/api/reports-analytics/summary",
            params={"date_from": "2026-02-01", "date_to": "2026-02-03"},
            headers=headers,
        )
        assert resp.status_code == 200
        assert resp.json()["total_reports"] == 15

    def test_manager_cannot_see_other_kg(self, dr_client, dr_db, dr_manager, dr_kindergarten):
        # Create another KG
        kg2 = models.Kindergarten(
            name_ar="حضانة أخرى",
            governorate="Zarqa",
            district="Zarqa",
            area="Center",
            address_line="5 St",
            contact_phone="+962790000099",
            status=models.KindergartenStatus.ACTIVE,
        )
        dr_db.add(kg2)
        dr_db.commit()
        dr_db.refresh(kg2)

        headers = _auth_headers(dr_client, "dr_manager", "Manager123!")
        resp = dr_client.get(
            "/api/reports-analytics/summary",
            params={
                "date_from": "2026-02-01",
                "date_to": "2026-02-03",
                "kindergarten_id": kg2.id,
            },
            headers=headers,
        )
        assert resp.status_code == 403

    def test_supervisor_is_scoped_to_assigned_kindergarten(
        self, dr_client, dr_db, seeded_reports, dr_supervisor, dr_kindergarten
    ):
        other_kg = models.Kindergarten(
            name_ar="حضانة خارج نطاق المشرفة",
            governorate="Zarqa",
            district="Zarqa",
            area="Center",
            address_line="5 St",
            contact_phone="+962790000098",
            status=models.KindergartenStatus.ACTIVE,
        )
        dr_db.add(other_kg)
        dr_db.commit()
        dr_db.refresh(other_kg)
        headers = _auth_headers(dr_client, "dr_supervisor", "Supervisor123!")

        own_scope = dr_client.get(
            "/api/reports-analytics/summary",
            params={"date_from": "2026-02-01", "date_to": "2026-02-03"},
            headers=headers,
        )
        outside_scope = dr_client.get(
            "/api/reports-analytics/sample-data",
            params={
                "date_from": "2026-02-01",
                "date_to": "2026-02-03",
                "kindergarten_id": other_kg.id,
            },
            headers=headers,
        )
        assert own_scope.status_code == 200
        assert own_scope.json()["total_reports"] == 15
        assert outside_scope.status_code == 403


class TestAnalyticsComputations:
    """Verify computed values from known data."""

    def test_meal_completion_rates(self, dr_client, seeded_reports, dr_admin):
        headers = _auth_headers(dr_client, "dr_admin", "Admin123!")
        resp = dr_client.get(
            "/api/reports-analytics/summary",
            params={"date_from": "2026-02-01", "date_to": "2026-02-03"},
            headers=headers,
        )
        meal = resp.json()["meal_completion"]
        # 4 out of 5 children per day eat breakfast × 3 days = 12/15 = 80%
        assert meal["breakfast"] == 80.0
        # All eat lunch
        assert meal["lunch"] == 100.0

    def test_nap_average(self, dr_client, seeded_reports, dr_admin):
        headers = _auth_headers(dr_client, "dr_admin", "Admin123!")
        resp = dr_client.get(
            "/api/reports-analytics/summary",
            params={"date_from": "2026-02-01", "date_to": "2026-02-03"},
            headers=headers,
        )
        nap = resp.json()["nap_analytics"]
        # nap_durations: 30, 45, 60, 75, 90 per day × 3 days
        # avg = (30+45+60+75+90)/5 = 60
        assert nap["avg_duration"] == 60.0

    def test_status_funnel(self, dr_client, seeded_reports, dr_admin):
        headers = _auth_headers(dr_client, "dr_admin", "Admin123!")
        resp = dr_client.get(
            "/api/reports-analytics/summary",
            params={"date_from": "2026-02-01", "date_to": "2026-02-03"},
            headers=headers,
        )
        funnel = resp.json()["status_funnel"]["status_counts"]
        # 3 days × 1 APPROVED, 1 SENT, 1 APPROVED, 1 REJECTED, 1 DRAFT
        # = 6 APPROVED, 3 SENT, 3 REJECTED, 3 DRAFT
        assert funnel.get("APPROVED", 0) == 6
        assert funnel.get("SENT_TO_PARENT", 0) == 3
        assert funnel.get("REJECTED", 0) == 3
        assert funnel.get("DRAFT", 0) == 3

    def test_health_flags(self, dr_client, seeded_reports, dr_admin):
        headers = _auth_headers(dr_client, "dr_admin", "Admin123!")
        resp = dr_client.get(
            "/api/reports-analytics/summary",
            params={"date_from": "2026-02-01", "date_to": "2026-02-03"},
            headers=headers,
        )
        health = resp.json()["health_flags"]
        # 1 child per day with mood=sick × 3 days = 3
        assert health["sick_count"] == 3

    def test_zero_denominator_rates_are_unavailable(
        self, dr_client, dr_db, dr_kindergarten, dr_parent, dr_admin
    ):
        child = _make_child(
            dr_db, dr_parent.parent_profile.id, dr_kindergarten.id, first_name="لا بيانات"
        )
        report = _make_daily_report(
            dr_db,
            child.id,
            dr_kindergarten.id,
            dr_admin.id,
            date(2026, 3, 1),
            status=models.DailyReportStatus.DRAFT,
            breakfast=None,
            lunch=None,
            snack=None,
            milk=None,
            nap_duration=None,
            bathroom_count=None,
        )
        report.diaper_wet = None
        report.diaper_soiled = None
        dr_db.commit()

        headers = _auth_headers(dr_client, "dr_admin", "Admin123!")
        response = dr_client.get(
            "/api/reports-analytics/summary",
            params={"date_from": "2026-03-01", "date_to": "2026-03-01"},
            headers=headers,
        )
        assert response.status_code == 200
        data = response.json()
        conversions = data["status_funnel"]["conversion_rates"]
        assert conversions["draft_to_submitted"] == 0
        assert conversions["submitted_to_approved"] is None
        assert conversions["approved_to_sent"] is None
        assert data["meal_completion"]["breakfast"] is None
        assert data["nap_analytics"]["avg_duration"] is None
        # bathroom_count has a model-level zero default, so this is a measured zero.
        assert data["diaper_bathroom"]["avg_bathroom"] == 0
        assert data["diaper_bathroom"]["wet_rate"] is None
        assert data["diaper_bathroom"]["soiled_rate"] is None


class TestAnalyticsDashboardPageRenders:
    """The /reports/analytics HTML page, not just its JSON API.

    This page 500s on a bare `UndefinedError: 'get_impersonation' is undefined`.
    daily_report_analytics.py defines its own `_language_context_processor`
    supplying only ui_lang/ui_dir, but the template extends base.html, which
    includes components/impersonation_banner.html; that partial resolves
    `impersonation` or calls a `get_impersonation()` global that is never
    registered. The canonical processor in scripts/compat/frontend_orig.py
    supplies `impersonation`, so the duplicate silently diverged.

    Every existing test here hits the JSON API, which uses no template — so the
    whole suite passed green while the page itself was unreachable.
    """

    def test_analytics_dashboard_page_renders_for_admin(self, dr_client, dr_admin):
        headers = _auth_headers(dr_client, "dr_admin", "Admin123!")
        response = dr_client.get("/reports/analytics", headers=headers)
        assert response.status_code == 200, response.text[:300]
        # Proves the banner partial actually rendered rather than the route
        # merely returning some other 200.
        assert "wfDraftSub" in response.text

    def test_language_context_processor_supplies_impersonation(self):
        """Guards the specific key whose absence caused the 500."""
        from starlette.requests import Request

        from daily_report_analytics import _language_context_processor

        scope = {
            "type": "http", "method": "GET", "path": "/reports/analytics",
            "headers": [], "query_string": b"",
        }
        context = _language_context_processor(Request(scope))
        assert "impersonation" in context
        assert context["ui_lang"] == "ar"


class TestDiaperRateDenominatorSemantics:
    """The diaper rates count RECORDED observations, not all reports.

    a22a52f5 changed `df[col].fillna(False).sum() / total_reports` to
    `observed.sum() / len(observed)` where `observed = df[col].dropna()`. Its
    message described only the zero-denominator guard, but this also changes the
    value on ordinary non-zero data, so the intent is pinned here rather than
    left to be rediscovered from a diff.

    The old form treated "nobody recorded a diaper check" as "the diaper was not
    wet" — asserting an observation that was never made, and understating the
    rate in exactly the reports where staff logged least. The denominator is now
    the reports that actually carry an observation; unrecorded is unknown, not
    false. `None` (no observations at all) is likewise unknown, not 0%.
    """

    def test_wet_rate_denominator_is_recorded_observations_not_all_reports(
        self, dr_db, dr_kindergarten, dr_parent, dr_admin
    ):
        from daily_report_analytics import DailyReportAnalytics, _load_reports_df

        child = _make_child(dr_db, dr_parent.parent_profile.id, dr_kindergarten.id)
        base = date(2026, 3, 1)
        # 4 reports: 2 recorded a diaper check (1 wet), 2 recorded nothing.
        for i, wet in enumerate([True, False, None, None]):
            r = _make_daily_report(
                dr_db, child.id, dr_kindergarten.id, dr_admin.id,
                base - timedelta(days=i), status=models.DailyReportStatus.APPROVED,
            )
            r.diaper_wet = wet
        dr_db.commit()

        df = _load_reports_df(dr_db, base - timedelta(days=5), base, [dr_kindergarten.id])
        result = DailyReportAnalytics(df).diaper_bathroom()

        # 1 wet of 2 recorded == 50.0. The old fillna(False)/total form gave
        # 1/4 == 25.0 by counting the two unrecorded reports as "not wet".
        assert result["wet_rate"] == 50.0, (
            f"expected 50.0 (1 wet of 2 recorded); got {result['wet_rate']}. "
            "25.0 means unrecorded reports are being counted as 'not wet'."
        )


class TestMealRateDenominatorSemantics:
    """Meal rates count only the reports that RECORDED the meal.

    a22a52f5 changed the denominator from `total_reports` to the non-null
    observations (`observed.sum() / len(observed)`), and the page's own "How to
    read this page" text went on claiming "the share of reports recording each
    meal" for two more commits. With 100 reports where 40 recorded breakfast and
    30 of those ate it, the sentence promised 40% and the card rendered 75%.

    Nothing caught it because the only meal-rate test
    (TestCalculations::test_meal_completion_rates) uses a fixture with NO nulls:
    12/15 == 80% under `fillna(False)/total_reports` and under
    `sum/len(observed)` alike, so reverting the change leaves the suite green.
    A null-bearing fixture is what makes the formula falsifiable.
    """

    def test_meal_rate_excludes_reports_that_did_not_record_the_meal(
        self, dr_db, dr_kindergarten, dr_parent, dr_admin
    ):
        from daily_report_analytics import DailyReportAnalytics, _load_reports_df

        child = _make_child(dr_db, dr_parent.parent_profile.id, dr_kindergarten.id)
        base = date(2026, 4, 1)
        # 4 reports: 2 recorded breakfast (1 ate, 1 did not), 2 recorded nothing.
        for i, eaten in enumerate([True, False, None, None]):
            r = _make_daily_report(
                dr_db, child.id, dr_kindergarten.id, dr_admin.id,
                base - timedelta(days=i), status=models.DailyReportStatus.APPROVED,
            )
            r.breakfast = eaten
        dr_db.commit()

        df = _load_reports_df(dr_db, base - timedelta(days=5), base, [dr_kindergarten.id])
        result = DailyReportAnalytics(df).meal_completion()

        # 1 eaten of 2 recorded == 50.0.
        # The old fillna(False)/total_reports form gives 1/4 == 25.0 by counting
        # the two unrecorded reports as "did not eat".
        assert result["breakfast"] == 50.0, (
            f"expected 50.0 (1 eaten of 2 recorded); got {result['breakfast']}. "
            "25.0 means unrecorded reports are being counted as 'not eaten'."
        )

    def test_meal_rate_is_unavailable_when_no_report_recorded_the_meal(
        self, dr_db, dr_kindergarten, dr_parent, dr_admin
    ):
        """No observations is unknown, not 0% — the zero-denominator rule."""
        from daily_report_analytics import DailyReportAnalytics, _load_reports_df

        child = _make_child(dr_db, dr_parent.parent_profile.id, dr_kindergarten.id)
        base = date(2026, 5, 1)
        for i in range(3):
            r = _make_daily_report(
                dr_db, child.id, dr_kindergarten.id, dr_admin.id,
                base - timedelta(days=i), status=models.DailyReportStatus.APPROVED,
            )
            r.breakfast = None
        dr_db.commit()

        df = _load_reports_df(dr_db, base - timedelta(days=5), base, [dr_kindergarten.id])
        assert DailyReportAnalytics(df).meal_completion()["breakfast"] is None


def test_the_page_text_names_the_denominator_the_code_uses():
    """The copy and the formula must move together — they did not, for two commits."""
    import pathlib

    tpl = (pathlib.Path(__file__).resolve().parents[1]
           / "templates" / "reports" / "analytics_dashboard.html").read_text(encoding="utf-8")
    assert "meal rates are the share of reports recording each meal" not in tpl, (
        "the help text claims the denominator is all reports; meal_completion() "
        "divides by the reports that RECORDED the meal"
    )
    assert "حصة التقارير التي سجلت كل وجبة" not in tpl
    assert "count only the reports that recorded that meal" in tpl
    assert "تحتسب التقارير التي سجّلت تلك الوجبة فقط" in tpl


# ─── New dimension filter + drill-down endpoint tests ─────────────────────────

class TestChildrenEndpoint:
    """GET /api/reports-analytics/children"""

    def test_returns_children_with_last_report(self, dr_client, seeded_reports, dr_admin):
        headers = _auth_headers(dr_client, "dr_admin", "Admin123!")
        resp = dr_client.get(
            "/api/reports-analytics/children",
            params={"date_from": "2026-02-01", "date_to": "2026-02-03"},
            headers=headers,
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["pagination"]["total"] == 5
        assert len(data["children"]) == 5
        assert "last_report_date" in data["children"][0]
        assert "last_report_status" in data["children"][0]

    def test_empty_period_returns_empty(self, dr_client, seeded_reports, dr_admin):
        headers = _auth_headers(dr_client, "dr_admin", "Admin123!")
        resp = dr_client.get(
            "/api/reports-analytics/children",
            params={"date_from": "2030-01-01", "date_to": "2030-01-05"},
            headers=headers,
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["pagination"]["total"] == 0
        assert data["children"] == []

    def test_gender_filter(self, dr_client, seeded_reports, dr_admin):
        headers = _auth_headers(dr_client, "dr_admin", "Admin123!")
        resp = dr_client.get(
            "/api/reports-analytics/children",
            params={"date_from": "2026-02-01", "date_to": "2026-02-03", "gender": "MALE"},
            headers=headers,
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["pagination"]["total"] == 5
        for c in data["children"]:
            assert c["gender"] == "MALE"


class TestChildDailyReportsEndpoint:
    """GET /api/reports-analytics/children/{child_id}/daily-reports"""

    def test_returns_paginated_reports(self, dr_client, seeded_reports, dr_admin):
        child = seeded_reports[0][0]
        headers = _auth_headers(dr_client, "dr_admin", "Admin123!")
        resp = dr_client.get(
            f"/api/reports-analytics/children/{child.id}/daily-reports",
            params={"date_from": "2026-02-01", "date_to": "2026-02-03"},
            headers=headers,
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["child_id"] == child.id
        assert len(data["reports"]) == 3
        assert data["pagination"]["total"] == 3

    def test_non_admin_forbidden(self, dr_client, seeded_reports, dr_manager):
        child = seeded_reports[0][0]
        headers = _auth_headers(dr_client, "dr_manager", "Manager123!")
        resp = dr_client.get(
            f"/api/reports-analytics/children/{child.id}/daily-reports",
            params={"date_from": "2026-02-01", "date_to": "2026-02-03"},
            headers=headers,
        )
        assert resp.status_code == 403

    def test_health_notes_inaccessible_for_non_admin(self, dr_client, seeded_reports, dr_manager):
        child = seeded_reports[0][0]
        headers = _auth_headers(dr_client, "dr_manager", "Manager123!")
        resp = dr_client.get(
            f"/api/reports-analytics/children/{child.id}/daily-reports",
            params={"date_from": "2026-02-01", "date_to": "2026-02-03"},
            headers=headers,
        )
        assert resp.status_code == 403


class TestAlertsEndpoint:
    """GET /api/reports-analytics/alerts"""

    def test_returns_empty_when_no_alerts(self, dr_client, seeded_reports, dr_admin):
        headers = _auth_headers(dr_client, "dr_admin", "Admin123!")
        resp = dr_client.get(
            "/api/reports-analytics/alerts",
            params={"date_from": "2026-02-01", "date_to": "2026-02-03"},
            headers=headers,
        )
        assert resp.status_code == 200
        data = resp.json()
        assert "alerts" in data
        assert "count" in data
        assert data["count"] == len(data["alerts"])

    def test_child_daily_reports_404_for_missing_child(self, dr_client, seeded_reports, dr_admin):
        """Non-existent child_id returns 404, not 500."""
        headers = _auth_headers(dr_client, "dr_admin", "Admin123!")
        resp = dr_client.get(
            "/api/reports-analytics/children/999999/daily-reports",
            params={"date_from": "2026-02-01", "date_to": "2026-02-03"},
            headers=headers,
        )
        assert resp.status_code == 404
