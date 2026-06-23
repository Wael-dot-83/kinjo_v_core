"""
Unit tests for KPI Service
"""
import pytest
from datetime import date, datetime, timedelta
from sqlalchemy.orm import Session
from kpi_service import KPIService, get_kpi_filters
import models
from database import get_db
from fastapi.testclient import TestClient
from main import app
from auth import get_password_hash


@pytest.fixture
def client(test_db):
    """
    Create a TestClient with test database dependency override
    """
    def override_get_db():
        try:
            yield test_db
        finally:
            pass

    app.dependency_overrides[get_db] = override_get_db

    with TestClient(app) as test_client:
        yield test_client

    app.dependency_overrides.clear()


@pytest.fixture
def admin_user(test_db):
    """
    Create an admin user for testing
    """
    from models import User, UserRole, UserStatus
    user = User(
        username="testadmin",
        email="admin@test.com",
        hashed_password=get_password_hash("Admin123!"),
        role=UserRole.ADMIN,
        status=UserStatus.ACTIVE
    )
    test_db.add(user)
    test_db.commit()
    test_db.refresh(user)
    return user


@pytest.fixture
def sample_kindergarten(test_db):
    """
    Create a sample kindergarten for testing
    """
    from models import Kindergarten, KindergartenStatus
    kindergarten = Kindergarten(
        name_ar="روضة الأمل",
        name_en="Hope Kindergarten",
        license_number="LIC-2026-001",
        governorate="Amman",
        city="Amman",
        area="Abdoun",
        address_line="123 Main Street",
        contact_phone="+962791234567",
        contact_email="contact@hope.jo",
        status=KindergartenStatus.ACTIVE,
        license_valid_until=date(2027, 12, 31)
    )
    test_db.add(kindergarten)
    test_db.commit()
    test_db.refresh(kindergarten)
    return kindergarten


def get_token_for_admin(client):
    """Get authentication token for admin user"""
    response = client.post(
        "/token",
        data={"username": "testadmin", "password": "Admin123!"}
    )
    assert response.status_code == 200
    return response.json()["access_token"]


def test_get_kpi_filters_arabic(client, admin_user, sample_kindergarten):
    """Test /api/kpi/filters with Arabic locale"""
    token = get_token_for_admin(client)
    headers = {"Authorization": f"Bearer {token}"}
    response = client.get("/api/kpi/filters?locale=ar", headers=headers)
    assert response.status_code == 200
    data = response.json()
    assert "kindergartens" in data
    assert "governorates" in data
    # Check that governorates are in Arabic
    assert any("عمان" in gov["name"] for gov in data["governorates"])


def test_get_kpi_filters_english(client, admin_user, sample_kindergarten):
    """Test /api/kpi/filters with English locale"""
    token = get_token_for_admin(client)
    headers = {"Authorization": f"Bearer {token}"}
    response = client.get("/api/kpi/filters?locale=en", headers=headers)
    assert response.status_code == 200
    data = response.json()
    assert "kindergartens" in data
    assert "governorates" in data
    # Check that governorates are in English
    assert any("Amman" in gov["name"] for gov in data["governorates"])


def test_dashboard_data_with_locale(client, admin_user, sample_kindergarten):
    """Test dashboard data returns localized names"""
    from datetime import date
    token = get_token_for_admin(client)
    headers = {"Authorization": f"Bearer {token}"}
    start = date.today().replace(day=1)
    end = date.today()
    
    response = client.get(f"/api/kpi/dashboard-data?period_start={start}&period_end={end}&locale=ar", headers=headers)
    assert response.status_code == 200
    # Test would check names are in Arabic, but depends on data


def test_kpi_dashboard_cache_hit(client, admin_user, sample_kindergarten):
    """Test that KPI dashboard data is cached and served from cache on second request"""
    from datetime import date
    from cache_service import dashboard_cache
    
    token = get_token_for_admin(client)
    headers = {"Authorization": f"Bearer {token}"}
    start = date.today().replace(day=1)
    end = date.today()
    url = f"/api/kpi/dashboard-data?period_start={start}&period_end={end}&locale=ar"
    
    # Clear cache first
    dashboard_cache.clear()
    
    # First request - should compute and cache
    response1 = client.get(url, headers=headers)
    assert response1.status_code == 200
    
    # Check cache has entry
    cache_key = f"kpi_dashboard:user_{admin_user.id}:role_ADMIN:kg_[]:gov_:start_{start}:end_{end}:gran_weekly:loc_ar"
    cached_data = dashboard_cache.get(cache_key)
    assert cached_data is not None
    
    # Second request - should serve from cache
    response2 = client.get(url, headers=headers)
    assert response2.status_code == 200
    assert response1.json() == response2.json()


def test_kpi_dashboard_cache_miss(client, admin_user, sample_kindergarten):
    """Test that cache miss occurs when parameters change"""
    from datetime import date
    from cache_service import dashboard_cache
    
    token = get_token_for_admin(client)
    headers = {"Authorization": f"Bearer {token}"}
    start = date.today().replace(day=1)
    end = date.today()
    
    # Clear cache
    dashboard_cache.clear()
    
    # First request
    url1 = f"/api/kpi/dashboard-data?period_start={start}&period_end={end}&locale=ar"
    response1 = client.get(url1, headers=headers)
    assert response1.status_code == 200
    
    # Second request with different date (ensure start2 < end)
    start2 = start.replace(day=min(15, end.day - 1))  # Ensure start2 is before end
    url2 = f"/api/kpi/dashboard-data?period_start={start2}&period_end={end}&locale=ar"
    response2 = client.get(url2, headers=headers)
    assert response2.status_code == 200
    
    # Should be different responses
    assert response1.json() != response2.json()


def test_compute_attendance_rate_excludes_absent_logs(
    test_db,
    sample_kindergarten,
    sample_class,
    sample_child,
    active_enrollment,
    supervisor_user,
):
    start = date(2026, 1, 1)
    end = date(2026, 1, 2)

    test_db.add_all(
        [
            models.AttendanceLog(
                child_id=sample_child.id,
                class_id=sample_class.id,
                date=start,
                status=models.AttendanceStatus.PRESENT,
                recorded_by=supervisor_user.id,
            ),
            models.AttendanceLog(
                child_id=sample_child.id,
                class_id=sample_class.id,
                date=end,
                status=models.AttendanceStatus.ABSENT,
                recorded_by=supervisor_user.id,
            ),
        ]
    )
    test_db.commit()

    rate = KPIService.compute_attendance_rate(test_db, sample_kindergarten.id, start, end)
    assert rate == 50.0


def test_compute_incident_rate_uses_attended_child_days_denominator(
    test_db,
    sample_kindergarten,
    sample_class,
    sample_child,
    active_enrollment,
    supervisor_user,
):
    start = date(2026, 2, 1)
    end = date(2026, 2, 2)

    test_db.add_all(
        [
            models.AttendanceLog(
                child_id=sample_child.id,
                class_id=sample_class.id,
                date=start,
                status=models.AttendanceStatus.PRESENT,
                recorded_by=supervisor_user.id,
            ),
            models.AttendanceLog(
                child_id=sample_child.id,
                class_id=sample_class.id,
                date=end,
                status=models.AttendanceStatus.ABSENT,
                recorded_by=supervisor_user.id,
            ),
            models.Incident(
                child_id=sample_child.id,
                kindergarten_id=sample_kindergarten.id,
                type=models.IncidentType.INJURY,
                severity_level=models.SeverityLevel.MEDIUM,
                description="Test incident",
                occurred_at=datetime(2026, 2, 2, 9, 0, 0),
                followup_required_flag=False,
            ),
        ]
    )
    test_db.commit()

    # 1 incident / 1 attended child-day * 100
    rate = KPIService.compute_incident_rate(test_db, sample_kindergarten.id, start, end)
    assert rate == 100.0


def test_compute_chronic_absence_rate_uses_working_days_not_logged_days(
    test_db,
    sample_kindergarten,
    sample_class,
    sample_child,
    active_enrollment,
    supervisor_user,
):
    start = date(2026, 2, 10)
    end = date(2026, 2, 12)  # 3 working days in test mode

    # Only one attended day is logged, missing days must count as absence.
    test_db.add(
        models.AttendanceLog(
            child_id=sample_child.id,
            class_id=sample_class.id,
            date=start,
            status=models.AttendanceStatus.PRESENT,
            recorded_by=supervisor_user.id,
        )
    )
    test_db.commit()

    rate = KPIService.compute_chronic_absence_rate(test_db, sample_kindergarten.id, start, end)
    assert rate == 100.0


def test_compute_report_submission_rate_uses_expected_reports(
    test_db,
    sample_kindergarten,
    sample_child,
    active_enrollment,
    supervisor_user,
):
    start = date(2026, 3, 1)
    end = date(2026, 3, 2)

    test_db.add_all(
        [
            models.DailyReport(
                child_id=sample_child.id,
                kindergarten_id=sample_kindergarten.id,
                date=start,
                status=models.DailyReportStatus.SUBMITTED,
                submitted_by=supervisor_user.id,
                arrival_time="08:00",
            ),
            models.DailyReport(
                child_id=sample_child.id,
                kindergarten_id=sample_kindergarten.id,
                date=end,
                status=models.DailyReportStatus.DRAFT,
                submitted_by=supervisor_user.id,
                arrival_time="08:00",
            ),
        ]
    )
    test_db.commit()

    # 1 submitted / 2 expected reports (1 active child x 2 days) * 100
    rate = KPIService.compute_report_submission_rate(test_db, sample_kindergarten.id, start, end)
    assert rate == 50.0


def test_compute_parent_satisfaction_score_from_surveys(
    test_db,
    sample_kindergarten,
    parent_user,
    sample_child,
    active_enrollment,
):
    start = date.today() - timedelta(days=7)
    end = date.today()

    survey = models.Survey(
        kindergarten_id=sample_kindergarten.id,
        title="Parent Pulse",
        description="Weekly NPS",
        nps_question_enabled=True,
        start_date=start,
        end_date=end,
    )
    test_db.add(survey)
    test_db.flush()

    test_db.add(
        models.SurveyResponse(
            survey_id=survey.id,
            parent_id=parent_user.id,
            nps_score=10,
            feedback_text="Great experience",
        )
    )
    test_db.commit()

    score = KPIService.compute_parent_satisfaction_score(
        test_db, sample_kindergarten.id, start, end
    )
    assert score == 100.0

    details = KPIService.compute_parent_satisfaction_details(
        test_db, sample_kindergarten.id, start, end
    )
    assert details[0] == 100.0
    assert details[2] == 1  # responses_count
    assert details[3] >= 1  # eligible_parents


def test_compute_checklist_compliance_uses_daily_checklist_records(
    test_db,
    sample_kindergarten,
    manager_user,
):
    start = date(2026, 1, 5)
    end = date(2026, 1, 6)

    for checklist_type in ("opening", "safety", "closing"):
        test_db.add(
            models.DailyChecklist(
                kindergarten_id=sample_kindergarten.id,
                checklist_date=start,
                checklist_type=checklist_type,
                status=models.DailyChecklistStatus.COMPLETED,
                submitted_by=manager_user.id,
            )
        )
    # day 2 intentionally missing to validate denominator coverage
    test_db.commit()

    rate = KPIService.compute_checklist_compliance(
        test_db, sample_kindergarten.id, start, end
    )
    assert rate == 50.0


def test_attendance_rate_excludes_excused(
    test_db,
    sample_kindergarten,
    sample_class,
    sample_child,
    active_enrollment,
    supervisor_user,
):
    """EXCUSED absences must NOT be counted as physical attendance."""
    start = date(2026, 4, 1)
    end = date(2026, 4, 3)  # 3 days

    test_db.add_all([
        models.AttendanceLog(child_id=sample_child.id, class_id=sample_class.id,
                             date=start, status=models.AttendanceStatus.PRESENT,
                             recorded_by=supervisor_user.id),
        models.AttendanceLog(child_id=sample_child.id, class_id=sample_class.id,
                             date=start + timedelta(days=1),
                             status=models.AttendanceStatus.EXCUSED,  # must NOT count
                             recorded_by=supervisor_user.id),
        models.AttendanceLog(child_id=sample_child.id, class_id=sample_class.id,
                             date=start + timedelta(days=2),
                             status=models.AttendanceStatus.ABSENT,
                             recorded_by=supervisor_user.id),
    ])
    test_db.commit()

    rate = KPIService.compute_attendance_rate(test_db, sample_kindergarten.id, start, end)
    # 1 PRESENT / 3 expected days = 33.33%
    assert rate == pytest.approx(33.33, abs=0.1)


def test_excused_absence_rate_counts_excused(
    test_db,
    sample_kindergarten,
    sample_class,
    sample_child,
    active_enrollment,
    supervisor_user,
):
    """Excused absence rate: EXCUSED / expected × 100."""
    start = date(2026, 4, 7)
    end = date(2026, 4, 8)  # 2 days

    test_db.add_all([
        models.AttendanceLog(child_id=sample_child.id, class_id=sample_class.id,
                             date=start, status=models.AttendanceStatus.EXCUSED,
                             recorded_by=supervisor_user.id),
        models.AttendanceLog(child_id=sample_child.id, class_id=sample_class.id,
                             date=start + timedelta(days=1),
                             status=models.AttendanceStatus.PRESENT,
                             recorded_by=supervisor_user.id),
    ])
    test_db.commit()

    rate = KPIService.compute_excused_absence_rate(test_db, sample_kindergarten.id, start, end)
    assert rate == 50.0


def test_kpi_standards_endpoint_returns_all_kpis(client, admin_user):
    token = get_token_for_admin(client)
    headers = {"Authorization": f"Bearer {token}"}
    r = client.get("/api/kpi/standards", headers=headers)
    assert r.status_code == 200
    data = r.json()
    assert "standards" in data
    assert "hard_override_rules" in data
    assert len(data["standards"]) >= 15
    assert len(data["hard_override_rules"]) >= 3
    # Every standard must have source metadata
    for std in data["standards"]:
        assert "threshold_source" in std
        assert std["threshold_source"]["source_name"]


def test_kpi_bundle_endpoint_returns_enriched_kpis(client, admin_user, sample_kindergarten):
    token = get_token_for_admin(client)
    headers = {"Authorization": f"Bearer {token}"}
    r = client.get(f"/api/kpi/bundle/{sample_kindergarten.id}", headers=headers)
    assert r.status_code == 200
    data = r.json()
    assert "kpis" in data
    assert "overall_band" in data
    assert "period_start" in data
    kpis = data["kpis"]
    for key in ("attendance_rate", "ratio_compliance", "incident_rate", "overall_gcei"):
        assert key in kpis, f"Missing KPI: {key}"
        kpi = kpis[key]
        assert "value" in kpi
        assert "band" in kpi
        assert "confidence" in kpi
        assert "trend" in kpi
        assert "meaning_en" in kpi
        assert "decision_guidance_en" in kpi


def test_kpi_definitions_endpoint(client, admin_user):
    token = get_token_for_admin(client)
    headers = {"Authorization": f"Bearer {token}"}
    r = client.get("/api/kpi/definitions?locale=ar", headers=headers)
    assert r.status_code == 200
    data = r.json()
    assert "definitions" in data
    assert data["count"] >= 10


def test_kpi_alerts_endpoint_no_alerts_for_empty_kg(client, admin_user, sample_kindergarten):
    token = get_token_for_admin(client)
    headers = {"Authorization": f"Bearer {token}"}
    r = client.get(
        f"/api/kpi/alerts?kindergarten_id={sample_kindergarten.id}",
        headers=headers,
    )
    assert r.status_code == 200
    data = r.json()
    assert "alerts" in data


def test_kpi_levels_country_admin_only(client, admin_user, sample_kindergarten):
    token = get_token_for_admin(client)
    headers = {"Authorization": f"Bearer {token}"}
    r = client.get("/api/kpi/levels/country", headers=headers)
    assert r.status_code == 200
    data = r.json()
    assert data["level"] == "country"
    assert "kpis" in data


def test_kpi_standards_aliases_resolve(client, admin_user):
    """attendance_rate and parent_satisfaction aliases must resolve in standards."""
    from kpi_standards import STANDARDS
    assert "attendance_rate" in STANDARDS
    assert "parent_satisfaction" in STANDARDS
    assert STANDARDS["attendance_rate"] is STANDARDS["physical_attendance_rate"]


def test_compute_confidence_levels():
    """compute_confidence returns correct levels based on denominator size."""
    from kpi_standards import compute_confidence, ConfidenceLevel
    assert compute_confidence(50, 30, 50, True) == ConfidenceLevel.HIGH
    assert compute_confidence(30, 30, 50, True) == ConfidenceLevel.MEDIUM  # exactly at min_denominator
    assert compute_confidence(29, 30, 50, True) == ConfidenceLevel.LOW     # below min_denominator
    assert compute_confidence(0, 30, 50, False) == ConfidenceLevel.INSUFFICIENT


if __name__ == "__main__":
    pytest.main([__file__])
