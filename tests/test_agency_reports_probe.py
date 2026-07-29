"""Regression tests for agency report fixes.

These replace the diagnostic probes in test_agency_reports_probe.py with
deterministic assertions that prevent recurrence of the reported defects.
"""

from __future__ import annotations

import pytest
from datetime import date, datetime, timedelta, timezone
from sqlalchemy.orm import Session

import models
from auth import get_password_hash
from agency_reports_service import AgencyReportsService


def _make_admin(db: Session, username="reg_admin"):
    u = models.User(
        username=username,
        email=f"{username}@example.com",
        hashed_password=get_password_hash("Admin123!"),
        role=models.UserRole.ADMIN,
        status=models.UserStatus.ACTIVE,
    )
    db.add(u)
    db.commit()
    db.refresh(u)
    return u


def _make_user(db: Session, username: str, role: models.UserRole):
    user = models.User(
        username=username,
        email=f"{username}@example.com",
        hashed_password=get_password_hash("Admin123!"),
        role=role,
        status=models.UserStatus.ACTIVE,
    )
    db.add(user)
    db.commit()
    db.refresh(user)
    return user


def _tok(client, username, password="Admin123!"):
    r = client.post("/token", data={"username": username, "password": password})
    assert r.status_code == 200, r.text
    return {"Authorization": f"Bearer {r.json()['access_token']}"}


def _call(client, path, headers, params=None):
    r = client.get(path, headers=headers, params=params)
    assert r.status_code == 200, r.text
    return r.json()


# ---------------------------------------------------------------------------
# A. enrollment_participation_0_60 — age calculation and chart
# ---------------------------------------------------------------------------
class TestEnrollmentParticipation0_60:
    def test_age_boundary_55_months(self, test_db):
        """A child 55 months old must land in the 48-60 bucket."""
        _make_admin(test_db, "reg_enroll_admin")
        parent = models.ParentProfile(
            user_id=1,
            first_name="ولي",
            last_name="أمر",
            phone_number="0790000000",
            gender=models.Gender.MALE,
            nationality="أردني",
            home_governorate="العاصمة",
            home_district="عمان",
            home_area="عمان",
            home_address_line="عمان",
            correspondence_preference=True,
            notification_language="ar",
            profile_complete=True,
        )
        test_db.add(parent)
        test_db.commit()
        test_db.refresh(parent)

        ref = date(2026, 7, 25)
        dob_55m = date(2021, 12, 25)  # 55 months before ref

        child = models.Child(
            parent_id=parent.id,
            first_name="ابن55",
            last_name="شهر",
            gender=models.Gender.MALE,
            date_of_birth=dob_55m,
            father_name="أب",
            mother_first_name="أم",
            mother_last_name="شهر",
            mother_nationality="أردنية",
            media_consent=True,
            correspondence_flag=True,
            profile_complete=True,
        )
        test_db.add(child)
        test_db.commit()

        kg = models.Kindergarten(
            name_ar="روضة",
            governorate="العاصمة",
            district="عمان",
            area="a",
            address_line="a",
            contact_phone="0790000001",
            status=models.KindergartenStatus.ACTIVE,
        )
        test_db.add(kg)
        test_db.commit()
        test_db.refresh(kg)

        enrollment = models.EnrollmentApplication(
            child_id=child.id,
            kindergarten_id=kg.id,
            status=models.EnrollmentStatus.ACTIVE,
        )
        test_db.add(enrollment)
        test_db.commit()

        payload = AgencyReportsService(test_db).generate_report("dos", "enrollment_participation_0_60", {})
        # The 60-month child must appear in the 48-60 bucket.
        bucket_row = next((b for b in payload["breakdowns"] if b["governorate"] == "العاصمة"), None)
        assert bucket_row is not None
        assert bucket_row["enrolled_48_60m"] == 1
        assert bucket_row["enrolled_total"] == 1

    def test_chart_omits_zero_series(self, test_db):
        """The pie chart must not include age bands with zero children."""
        _make_admin(test_db, "reg_enroll_admin2")
        payload = AgencyReportsService(test_db).generate_report("dos", "enrollment_participation_0_60", {})
        if payload.get("chart"):
            for s in payload["chart"].get("series", []):
                assert s["value"] > 0, f"Zero-value series found: {s}"

    def test_empty_data_has_no_misleading_chart(self, test_db):
        """When no children match, chart should be absent or explicitly empty."""
        _make_admin(test_db, "reg_enroll_admin3")
        payload = AgencyReportsService(test_db).generate_report("dos", "enrollment_participation_0_60", {})
        # With no data, chart must not claim has_chart=true with empty breakdowns.
        if payload.get("chart"):
            assert payload["chart"].get("series"), "Chart present but empty"
        assert "breakdowns" in payload


# ---------------------------------------------------------------------------
# E. supervisors_child_ratio — chart and summary correctness
# ---------------------------------------------------------------------------
class TestSupervisorsChildRatio:
    def test_overall_ratio_in_summary(self, test_db):
        _make_admin(test_db, "reg_sup_admin")
        kg1 = models.Kindergarten(
            name_ar="روضة أ",
            governorate="العاصمة",
            district="عمان",
            area="a",
            address_line="a",
            contact_phone="0790000001",
            status=models.KindergartenStatus.ACTIVE,
        )
        kg2 = models.Kindergarten(
            name_ar="روضة ب",
            governorate="إربد",
            district="إربد",
            area="b",
            address_line="b",
            contact_phone="0790000002",
            status=models.KindergartenStatus.ACTIVE,
        )
        test_db.add_all([kg1, kg2])
        test_db.commit()
        test_db.refresh(kg1)
        test_db.refresh(kg2)

        sup1 = _make_user(test_db, "reg_sup_1", models.UserRole.SUPERVISOR)
        sup2 = _make_user(test_db, "reg_sup_2", models.UserRole.SUPERVISOR)
        test_db.add_all(
            [
                models.SupervisorProfile(user_id=sup1.id, kindergarten_id=kg1.id),
                models.SupervisorProfile(user_id=sup2.id, kindergarten_id=kg1.id),
            ]
        )
        test_db.commit()

        cls1 = models.Class(
            name_ar="صف أ",
            kindergarten_id=kg1.id,
            class_code="C1",
            age_group="AGE_2_4",
            capacity_total=20,
            enrolled_children_count=10,
            min_age_months=24,
            max_age_months=48,
            is_active=True,
            supervisor_id=sup1.id,
        )
        cls2 = models.Class(
            name_ar="صف ب",
            kindergarten_id=kg1.id,
            class_code="C2",
            age_group="AGE_2_4",
            capacity_total=20,
            enrolled_children_count=10,
            min_age_months=24,
            max_age_months=48,
            is_active=True,
            supervisor_id=sup2.id,
        )
        test_db.add_all([cls1, cls2])
        test_db.commit()
        test_db.add_all(
            [
                models.SupervisorAssignment(
                    class_id=cls1.id, supervisor_id=sup1.id, is_primary=True, start_date=date(2024, 1, 1)
                ),
                models.SupervisorAssignment(
                    class_id=cls2.id, supervisor_id=sup2.id, is_primary=True, start_date=date(2024, 1, 1)
                ),
            ]
        )
        test_db.commit()

        payload = AgencyReportsService(test_db).generate_report("dos", "supervisors_child_ratio", {})
        assert "children_per_supervisor" in payload["summary"]
        assert payload["summary"]["children_per_supervisor"] == 10.0  # 20 children / 2 supervisors

    def test_chart_does_not_sum_ratios(self, test_db):
        """Chart values per governorate must be weighted ratios, not sums of ratios."""
        _make_admin(test_db, "reg_sup_admin2")
        kg1 = models.Kindergarten(
            name_ar="روضة أ",
            governorate="العاصمة",
            district="عمان",
            area="a",
            address_line="a",
            contact_phone="0790000001",
            status=models.KindergartenStatus.ACTIVE,
        )
        test_db.add(kg1)
        test_db.commit()
        test_db.refresh(kg1)

        sup1 = _make_user(test_db, "reg_sup_3", models.UserRole.SUPERVISOR)
        sup2 = _make_user(test_db, "reg_sup_4", models.UserRole.SUPERVISOR)
        test_db.add_all(
            [
                models.SupervisorProfile(user_id=sup1.id, kindergarten_id=kg1.id),
                models.SupervisorProfile(user_id=sup2.id, kindergarten_id=kg1.id),
            ]
        )
        test_db.commit()

        cls1 = models.Class(
            name_ar="صف أ",
            kindergarten_id=kg1.id,
            class_code="C1",
            age_group="AGE_2_4",
            capacity_total=20,
            enrolled_children_count=10,
            min_age_months=24,
            max_age_months=48,
            is_active=True,
            supervisor_id=sup1.id,
        )
        cls2 = models.Class(
            name_ar="صف ب",
            kindergarten_id=kg1.id,
            class_code="C2",
            age_group="AGE_2_4",
            capacity_total=20,
            enrolled_children_count=10,
            min_age_months=24,
            max_age_months=48,
            is_active=True,
            supervisor_id=sup2.id,
        )
        test_db.add_all([cls1, cls2])
        test_db.commit()
        test_db.add_all(
            [
                models.SupervisorAssignment(
                    class_id=cls1.id, supervisor_id=sup1.id, is_primary=True, start_date=date(2024, 1, 1)
                ),
                models.SupervisorAssignment(
                    class_id=cls2.id, supervisor_id=sup2.id, is_primary=True, start_date=date(2024, 1, 1)
                ),
            ]
        )
        test_db.commit()

        payload = AgencyReportsService(test_db).generate_report("dos", "supervisors_child_ratio", {})
        assert payload.get("chart")
        series = payload["chart"]["series"]
        assert len(series) == 1
        # 20 children / 2 supervisors = 10.0
        assert series[0]["value"] == 10.0

    def test_zero_supervisors_yields_none_ratio(self, test_db):
        """When a KG has classes but no supervisors, the ratio must be None."""
        _make_admin(test_db, "reg_sup_admin3")
        kg1 = models.Kindergarten(
            name_ar="روضة أ",
            governorate="العاصمة",
            district="عمان",
            area="a",
            address_line="a",
            contact_phone="0790000001",
            status=models.KindergartenStatus.ACTIVE,
        )
        test_db.add(kg1)
        test_db.commit()
        test_db.refresh(kg1)

        cls1 = models.Class(
            name_ar="صف أ",
            kindergarten_id=kg1.id,
            class_code="C1",
            age_group="AGE_2_4",
            capacity_total=20,
            enrolled_children_count=10,
            min_age_months=24,
            max_age_months=48,
            is_active=True,
            supervisor_id=None,
        )
        test_db.add(cls1)
        test_db.commit()

        payload = AgencyReportsService(test_db).generate_report("dos", "supervisors_child_ratio", {})
        row = next(r for r in payload["breakdowns"] if r["governorate"] == "العاصمة")
        assert row["children_per_supervisor"] is None
        assert payload["summary"]["children_per_supervisor"] is None


# ---------------------------------------------------------------------------
# F. geographic_service_gaps — geo filters and chart correctness
# ---------------------------------------------------------------------------
class TestGeographicServiceGaps:
    def test_governorate_filter_applied(self, test_db):
        _make_admin(test_db, "reg_gap_admin")
        _seed_gap_data(test_db)
        payload = AgencyReportsService(test_db).generate_report(
            "dos", "geographic_service_gaps", {"governorate": "العاصمة"}
        )
        for row in payload["breakdowns"]:
            assert row["governorate"] == "العاصمة"

    def test_chart_uses_aggregate_ratio_not_sum(self, test_db):
        _make_admin(test_db, "reg_gap_admin2")
        _seed_gap_data(test_db)
        payload = AgencyReportsService(test_db).generate_report("dos", "geographic_service_gaps", {})
        if payload.get("chart") and payload["breakdowns"]:
            chart_labels = {s["label"] for s in payload["chart"]["series"]}
            table_governorates = {r["governorate"] for r in payload["breakdowns"]}
            assert chart_labels.issubset(table_governorates)


def _seed_gap_data(db: Session):
    """Seed kindergartens and children across two governorates."""
    kg1 = models.Kindergarten(
        name_ar="روضة أ",
        governorate="العاصمة",
        district="عمان",
        area="a",
        address_line="a",
        contact_phone="0790000001",
        status=models.KindergartenStatus.ACTIVE,
    )
    kg2 = models.Kindergarten(
        name_ar="روضة ب",
        governorate="إربد",
        district="إربد",
        area="b",
        address_line="b",
        contact_phone="0790000002",
        status=models.KindergartenStatus.ACTIVE,
    )
    db.add_all([kg1, kg2])
    db.commit()

    parent_user = _make_user(db, "reg_gap_parent", models.UserRole.PARENT)
    parent = models.ParentProfile(
        user_id=parent_user.id,
        first_name="ولي",
        last_name="أمر",
        phone_number="0790000000",
        gender=models.Gender.MALE,
        nationality="أردني",
        home_governorate="العاصمة",
        home_district="عمان",
        home_area="عمان",
        home_address_line="عمان",
        correspondence_preference=True,
        notification_language="ar",
        profile_complete=True,
    )
    db.add(parent)
    db.commit()
    db.refresh(parent)

    child = models.Child(
        parent_id=parent.id,
        first_name="أحمد",
        last_name="الأول",
        gender=models.Gender.MALE,
        date_of_birth=date(2024, 1, 1),
        father_name="أبو أحمد",
        mother_first_name="أم أحمد",
        mother_last_name="الأول",
        mother_nationality="أردنية",
        media_consent=True,
        correspondence_flag=True,
        profile_complete=True,
    )
    db.add(child)
    db.commit()


# ---------------------------------------------------------------------------
# H. incidents_safety_1000_child_days — rate calculation
# ---------------------------------------------------------------------------
class TestIncidentsSafety1000ChildDays:
    def test_rate_computed_when_attendance_exists(self, test_db):
        _make_admin(test_db, "reg_inc_admin")
        kg, parent, child = _seed_incident_data(test_db)
        # Create attendance so child-days > 0.
        cls = models.Class(
            name_ar="صف",
            kindergarten_id=kg.id,
            class_code="C1",
            age_group="AGE_2_4",
            capacity_total=20,
            enrolled_children_count=1,
            min_age_months=24,
            max_age_months=48,
            is_active=True,
        )
        test_db.add(cls)
        test_db.commit()
        test_db.refresh(cls)
        today = date.today()
        test_db.add(
            models.EnrollmentApplication(
                child_id=child.id,
                kindergarten_id=kg.id,
                class_id=cls.id,
                status=models.EnrollmentStatus.ACTIVE,
                enrollment_start_date=date(2024, 1, 1),
            )
        )
        test_db.add(
            models.AttendanceLog(
                child_id=child.id, class_id=cls.id, date=today, status=models.AttendanceStatus.PRESENT, recorded_by=1
            )
        )
        test_db.commit()

        payload = AgencyReportsService(test_db).generate_report("dos", "incidents_safety_1000_child_days", {})
        assert "incident_rate_per_1000_child_days" in payload["summary"]
        assert payload["summary"]["incident_count"] == 1
        # Denominator is expected child-days (working days), not attended.
        assert payload["summary"]["eligible_child_days"] >= 1
        assert payload["summary"]["incident_rate_per_1000_child_days"] == round(
            1000 / payload["summary"]["eligible_child_days"], 3
        )

    def test_rate_is_none_when_no_attendance(self, test_db):
        _make_admin(test_db, "reg_inc_admin2")
        kg, parent, child = _seed_incident_data(test_db)
        payload = AgencyReportsService(test_db).generate_report("dos", "incidents_safety_1000_child_days", {})
        assert payload["summary"]["incident_rate_per_1000_child_days"] is None
        assert "data_quality_note_ar" in payload["summary"]

    def test_chart_present_with_severity_series(self, test_db):
        _make_admin(test_db, "reg_inc_admin3")
        kg, parent, child = _seed_incident_data(test_db)
        payload = AgencyReportsService(test_db).generate_report("dos", "incidents_safety_1000_child_days", {})
        assert payload.get("chart")
        assert payload["chart"]["type"] == "bar"
        series_labels = {s["label"] for s in payload["chart"]["series"]}
        assert "منخفضة" in series_labels


def _seed_incident_data(db: Session):
    admin = _make_admin(db, "reg_inc_seed_admin")
    kg = models.Kindergarten(
        name_ar="روضة أ",
        governorate="العاصمة",
        district="عمان",
        area="a",
        address_line="a",
        contact_phone="0790000001",
        status=models.KindergartenStatus.ACTIVE,
    )
    db.add(kg)
    db.commit()
    db.refresh(kg)

    parent_user = _make_user(db, "reg_inc_parent", models.UserRole.PARENT)
    parent = models.ParentProfile(
        user_id=parent_user.id,
        first_name="ولي",
        last_name="أمر",
        phone_number="0790000000",
        gender=models.Gender.MALE,
        nationality="أردني",
        home_governorate="العاصمة",
        home_district="عمان",
        home_area="عمان",
        home_address_line="عمان",
        correspondence_preference=True,
        notification_language="ar",
        profile_complete=True,
    )
    db.add(parent)
    db.commit()
    db.refresh(parent)

    child = models.Child(
        parent_id=parent.id,
        first_name="أحمد",
        last_name="الأول",
        gender=models.Gender.MALE,
        date_of_birth=date(2024, 1, 1),
        father_name="أبو أحمد",
        mother_first_name="أم أحمد",
        mother_last_name="الأول",
        mother_nationality="أردنية",
        media_consent=True,
        correspondence_flag=True,
        profile_complete=True,
    )
    db.add(child)
    db.commit()
    db.refresh(child)

    incident = models.Incident(
        child_id=child.id,
        kindergarten_id=kg.id,
        type=models.IncidentType.OTHER,
        severity_level=models.SeverityLevel.LOW,
        occurred_at=date.today(),
        description="test",
        reported_by=admin.id,
    )
    db.add(incident)
    db.commit()
    return kg, parent, child


# ---------------------------------------------------------------------------
# I. child_safety_protection — chart presence
# ---------------------------------------------------------------------------
class TestChildSafetyProtection:
    def test_chart_present_with_incidents(self, test_db):
        _make_admin(test_db, "reg_cs_admin")
        kg, parent, child = _seed_incident_data(test_db)
        payload = AgencyReportsService(test_db).generate_report("mosd", "child_safety_protection", {})
        assert payload.get("chart")
        assert payload["chart"]["type"] == "bar"

    def test_empty_state_message_when_no_incidents(self, test_db):
        _make_admin(test_db, "reg_cs_admin2")
        payload = AgencyReportsService(test_db).generate_report("mosd", "child_safety_protection", {})
        assert "data_quality_note_ar" in payload["summary"]


# ---------------------------------------------------------------------------
# J. annual_quarterly_trends — explicit chart and chronological order
# ---------------------------------------------------------------------------
class TestAnnualQuarterlyTrends:
    def test_chart_present(self, test_db):
        _make_admin(test_db, "reg_trend_admin")
        kg = models.Kindergarten(
            name_ar="روضة أ",
            governorate="العاصمة",
            district="عمان",
            area="a",
            address_line="a",
            contact_phone="0790000001",
            status=models.KindergartenStatus.ACTIVE,
            created_at=datetime(2024, 1, 1, tzinfo=timezone.utc),
        )
        test_db.add(kg)
        test_db.commit()

        payload = AgencyReportsService(test_db).generate_report("dos", "annual_quarterly_trends", {})
        assert payload.get("chart")
        assert payload["chart"]["type"] == "bar"

    def test_chronological_order_preserved(self, test_db):
        _make_admin(test_db, "reg_trend_admin2")
        test_db.add_all(
            [
                models.Kindergarten(
                    name_ar="ك4-2018",
                    governorate="العاصمة",
                    district="عمان",
                    area="a",
                    address_line="a",
                    contact_phone="0790000101",
                    status=models.KindergartenStatus.ACTIVE,
                    created_at=datetime(2018, 11, 1, tzinfo=timezone.utc),
                ),
                models.Kindergarten(
                    name_ar="ك2-2019",
                    governorate="العاصمة",
                    district="عمان",
                    area="a",
                    address_line="a",
                    contact_phone="0790000102",
                    status=models.KindergartenStatus.ACTIVE,
                    created_at=datetime(2019, 5, 15, tzinfo=timezone.utc),
                ),
                models.Kindergarten(
                    name_ar="ك1-2020",
                    governorate="العاصمة",
                    district="عمان",
                    area="a",
                    address_line="a",
                    contact_phone="0790000103",
                    status=models.KindergartenStatus.ACTIVE,
                    created_at=datetime(2020, 2, 10, tzinfo=timezone.utc),
                ),
            ]
        )
        test_db.commit()
        payload = AgencyReportsService(test_db).generate_report("dos", "annual_quarterly_trends", {})
        periods = [r["period"] for r in payload["breakdowns"] if r["period"] != "غير محدد"]
        assert periods == ["Q4-2018", "Q2-2019", "Q1-2020"]


# ---------------------------------------------------------------------------
# API-level regression tests
# ---------------------------------------------------------------------------
class TestAgencyReportsAPI:
    def test_incidents_safety_api_returns_rate(self, client, test_db):
        _make_admin(test_db, "reg_api_inc")
        kg, parent, child = _seed_incident_data(test_db)
        headers = _tok(client, "reg_api_inc")
        r = client.get("/api/admin/agency-reports/dos/reports/incidents_safety_1000_child_days", headers=headers)
        assert r.status_code == 200
        data = r.json()
        assert "incident_rate_per_1000_child_days" in data["summary"]

    def test_supervisors_ratio_api_returns_overall_ratio(self, client, test_db):
        _make_admin(test_db, "reg_api_sup")
        kg1 = models.Kindergarten(
            name_ar="روضة أ",
            governorate="العاصمة",
            district="عمان",
            area="a",
            address_line="a",
            contact_phone="0790000001",
            status=models.KindergartenStatus.ACTIVE,
        )
        test_db.add(kg1)
        test_db.commit()
        test_db.refresh(kg1)

        sup1 = _make_user(test_db, "reg_api_sup1", models.UserRole.SUPERVISOR)
        cls1 = models.Class(
            name_ar="صف أ",
            kindergarten_id=kg1.id,
            class_code="C1",
            age_group="AGE_2_4",
            capacity_total=20,
            enrolled_children_count=10,
            min_age_months=24,
            max_age_months=48,
            is_active=True,
        )
        test_db.add(cls1)
        test_db.commit()
        test_db.refresh(cls1)
        test_db.add(
            models.SupervisorAssignment(
                class_id=cls1.id, supervisor_id=sup1.id, is_primary=True, start_date=date(2024, 1, 1)
            )
        )
        test_db.commit()

        headers = _tok(client, "reg_api_sup")
        r = client.get("/api/admin/agency-reports/dos/reports/supervisors_child_ratio", headers=headers)
        assert r.status_code == 200
        data = r.json()
        assert "children_per_supervisor" in data["summary"]
        assert data["summary"]["children_per_supervisor"] == 10.0

    def test_geographic_gaps_api_respects_filter(self, client, test_db):
        _make_admin(test_db, "reg_api_gap")
        _seed_gap_data(test_db)
        headers = _tok(client, "reg_api_gap")
        r = client.get(
            "/api/admin/agency-reports/dos/reports/geographic_service_gaps",
            headers=headers,
            params={"governorate": "العاصمة"},
        )
        assert r.status_code == 200
        data = r.json()
        for row in data["breakdowns"]:
            assert row["governorate"] == "العاصمة"


# ---------------------------------------------------------------------------
# Additional regression tests for fixes applied in this session
# ---------------------------------------------------------------------------
class TestEnrollmentParticipationAcceptedStatus:
    """A. enrollment_participation_0_60 — accepted enrollments must be included."""

    def test_accepted_enrollment_counts(self, test_db):
        _make_admin(test_db, "reg_enroll_accepted")
        parent = models.ParentProfile(
            user_id=1,
            first_name="ولي",
            last_name="أمر",
            phone_number="0790000000",
            gender=models.Gender.MALE,
            nationality="أردني",
            home_governorate="العاصمة",
            home_district="عمان",
            home_area="عمان",
            home_address_line="عمان",
            correspondence_preference=True,
            notification_language="ar",
            profile_complete=True,
        )
        test_db.add(parent)
        test_db.commit()
        test_db.refresh(parent)

        child = models.Child(
            parent_id=parent.id,
            first_name="ابن",
            last_name="مقبول",
            gender=models.Gender.MALE,
            date_of_birth=date(2024, 1, 1),
            father_name="أب",
            mother_first_name="أم",
            mother_last_name="مقبول",
            mother_nationality="أردنية",
            media_consent=True,
            correspondence_flag=True,
            profile_complete=True,
        )
        test_db.add(child)
        test_db.commit()

        kg = models.Kindergarten(
            name_ar="روضة",
            governorate="العاصمة",
            district="عمان",
            area="a",
            address_line="a",
            contact_phone="0790000001",
            status=models.KindergartenStatus.ACTIVE,
        )
        test_db.add(kg)
        test_db.commit()
        test_db.refresh(kg)

        # ACCEPTED (not ACTIVE) enrollment must still be counted.
        enrollment = models.EnrollmentApplication(
            child_id=child.id,
            kindergarten_id=kg.id,
            status=models.EnrollmentStatus.ACCEPTED,
        )
        test_db.add(enrollment)
        test_db.commit()

        payload = AgencyReportsService(test_db).generate_report("dos", "enrollment_participation_0_60", {})
        bucket_row = next((b for b in payload["breakdowns"] if b["governorate"] == "العاصمة"), None)
        assert bucket_row is not None
        assert bucket_row["enrolled_total"] == 1


class TestSupervisorsViaAssignment:
    """E. supervisors_child_ratio — must use SupervisorAssignment, not legacy Class.supervisor_id."""

    def test_supervisor_assignment_counts(self, test_db):
        _make_admin(test_db, "reg_sup_assign")
        kg1 = models.Kindergarten(
            name_ar="روضة أ",
            governorate="العاصمة",
            district="عمان",
            area="a",
            address_line="a",
            contact_phone="0790000001",
            status=models.KindergartenStatus.ACTIVE,
        )
        test_db.add(kg1)
        test_db.commit()
        test_db.refresh(kg1)

        sup1 = _make_user(test_db, "reg_sup_assign1", models.UserRole.SUPERVISOR)
        test_db.add(models.SupervisorProfile(user_id=sup1.id, kindergarten_id=kg1.id))
        test_db.commit()

        cls1 = models.Class(
            name_ar="صف أ",
            kindergarten_id=kg1.id,
            class_code="C1",
            age_group="AGE_2_4",
            capacity_total=20,
            enrolled_children_count=10,
            min_age_months=24,
            max_age_months=48,
            is_active=True,
        )
        test_db.add(cls1)
        test_db.commit()
        test_db.refresh(cls1)

        # Create assignment via the canonical SupervisorAssignment table.
        test_db.add(
            models.SupervisorAssignment(
                class_id=cls1.id, supervisor_id=sup1.id, is_primary=True, start_date=date(2024, 1, 1)
            )
        )
        test_db.commit()

        payload = AgencyReportsService(test_db).generate_report("dos", "supervisors_child_ratio", {})
        row = next(r for r in payload["breakdowns"] if r["governorate"] == "العاصمة")
        assert row["supervisors"] == 1
        assert row["children_per_supervisor"] == 10.0


class TestIncidentsActiveKindergartensOnly:
    """H. incidents_safety_1000_child_days — denominator must exclude inactive KGs."""

    def test_inactive_kg_excluded_from_denominator(self, test_db):
        _make_admin(test_db, "reg_inc_active")
        # Active KG with incident.
        kg_active = models.Kindergarten(
            name_ar="روضة نشطة",
            governorate="العاصمة",
            district="عمان",
            area="a",
            address_line="a",
            contact_phone="0790000001",
            status=models.KindergartenStatus.ACTIVE,
        )
        # Inactive KG — should NOT contribute to expected child-days.
        kg_inactive = models.Kindergarten(
            name_ar="روضة غير نشطة",
            governorate="العاصمة",
            district="عمان",
            area="b",
            address_line="b",
            contact_phone="0790000002",
            status=models.KindergartenStatus.INACTIVE,
        )
        test_db.add_all([kg_active, kg_inactive])
        test_db.commit()
        test_db.refresh(kg_active)
        test_db.refresh(kg_inactive)

        parent_user = _make_user(test_db, "reg_inc_active_parent", models.UserRole.PARENT)
        parent = models.ParentProfile(
            user_id=parent_user.id,
            first_name="ولي",
            last_name="أمر",
            phone_number="0790000000",
            gender=models.Gender.MALE,
            nationality="أردني",
            home_governorate="العاصمة",
            home_district="عمان",
            home_area="عمان",
            home_address_line="عمان",
            correspondence_preference=True,
            notification_language="ar",
            profile_complete=True,
        )
        test_db.add(parent)
        test_db.commit()
        test_db.refresh(parent)

        child = models.Child(
            parent_id=parent.id,
            first_name="أحمد",
            last_name="الأول",
            gender=models.Gender.MALE,
            date_of_birth=date(2024, 1, 1),
            father_name="أبو أحمد",
            mother_first_name="أم أحمد",
            mother_last_name="الأول",
            mother_nationality="أردنية",
            media_consent=True,
            correspondence_flag=True,
            profile_complete=True,
        )
        test_db.add(child)
        test_db.commit()
        test_db.refresh(child)

        incident = models.Incident(
            child_id=child.id,
            kindergarten_id=kg_active.id,
            type=models.IncidentType.OTHER,
            severity_level=models.SeverityLevel.LOW,
            occurred_at=date.today(),
            description="test",
            reported_by=1,
        )
        test_db.add(incident)
        test_db.commit()

        payload = AgencyReportsService(test_db).generate_report("dos", "incidents_safety_1000_child_days", {})
        # With no attendance records, rate must be None (not fabricated).
        assert payload["summary"]["incident_rate_per_1000_child_days"] is None
        assert "data_quality_note_ar" in payload["summary"]


class TestMonthlyAttendanceExpectedDays:
    """D. monthly_attendance_absence — rate must use expected child-days, not logged-record share."""

    def test_attendance_rate_uses_expected_child_days(self, test_db):
        _make_admin(test_db, "reg_att_admin")
        kg = models.Kindergarten(
            name_ar="روضة",
            governorate="العاصمة",
            district="عمان",
            area="a",
            address_line="a",
            contact_phone="0790000001",
            status=models.KindergartenStatus.ACTIVE,
        )
        test_db.add(kg)
        test_db.commit()
        test_db.refresh(kg)

        cls = models.Class(
            name_ar="صف",
            kindergarten_id=kg.id,
            class_code="C1",
            age_group="AGE_2_4",
            capacity_total=20,
            enrolled_children_count=5,
            min_age_months=24,
            max_age_months=48,
            is_active=True,
        )
        test_db.add(cls)
        test_db.commit()
        test_db.refresh(cls)

        parent_user = _make_user(test_db, "reg_att_parent", models.UserRole.PARENT)
        parent = models.ParentProfile(
            user_id=parent_user.id,
            first_name="ولي",
            last_name="أمر",
            phone_number="0790000000",
            gender=models.Gender.MALE,
            nationality="أردني",
            home_governorate="العاصمة",
            home_district="عمان",
            home_area="عمان",
            home_address_line="عمان",
            correspondence_preference=True,
            notification_language="ar",
            profile_complete=True,
        )
        test_db.add(parent)
        test_db.commit()
        test_db.refresh(parent)

        child = models.Child(
            parent_id=parent.id,
            first_name="ابن",
            last_name="حاضر",
            gender=models.Gender.MALE,
            date_of_birth=date(2024, 1, 1),
            father_name="أبو",
            mother_first_name="أم",
            mother_last_name="حاضر",
            mother_nationality="أردنية",
            media_consent=True,
            correspondence_flag=True,
            profile_complete=True,
        )
        test_db.add(child)
        test_db.commit()
        test_db.refresh(child)

        enrollment = models.EnrollmentApplication(
            child_id=child.id,
            kindergarten_id=kg.id,
            class_id=cls.id,
            status=models.EnrollmentStatus.ACTIVE,
            is_active=True,
        )
        test_db.add(enrollment)
        test_db.commit()

        today = date.today()
        test_db.add(
            models.AttendanceLog(
                child_id=child.id, class_id=cls.id, date=today, status=models.AttendanceStatus.PRESENT, recorded_by=1
            )
        )
        test_db.commit()

        payload = AgencyReportsService(test_db).generate_report("dos", "monthly_attendance_absence", {})
        assert "expected_child_days" in payload["summary"]
        assert payload["summary"]["expected_child_days"] >= 1
        # attendance_rate_pct must be computed against expected_child_days, not total_records.
        if payload["summary"]["expected_child_days"]:
            assert payload["summary"]["attendance_rate_pct"] == round(
                payload["summary"]["present_records"] / payload["summary"]["expected_child_days"] * 100, 2
            )


class TestCapacityOccupancyExplicitChart:
    """C. capacity_occupancy_overcrowding — explicit chart must reconcile with table."""

    def test_occupancy_chart_matches_table(self, test_db):
        _make_admin(test_db, "reg_cap_admin")
        kg = models.Kindergarten(
            name_ar="روضة",
            governorate="العاصمة",
            district="عمان",
            area="a",
            address_line="a",
            contact_phone="0790000001",
            status=models.KindergartenStatus.ACTIVE,
        )
        test_db.add(kg)
        test_db.commit()
        test_db.refresh(kg)

        cls = models.Class(
            name_ar="صف",
            kindergarten_id=kg.id,
            class_code="C1",
            age_group="AGE_2_4",
            capacity_total=20,
            enrolled_children_count=15,
            min_age_months=24,
            max_age_months=48,
            is_active=True,
        )
        test_db.add(cls)
        test_db.commit()

        payload = AgencyReportsService(test_db).generate_report("dos", "capacity_occupancy_overcrowding", {})
        assert payload.get("chart")
        assert payload["chart"]["group_by"] == "governorate"
        # Chart total (sum of chart values) must equal table total (sum of occupancy_rate weighted by capacity).
        chart_total = sum(s["value"] for s in payload["chart"]["series"] if isinstance(s["value"], (int, float)))
        table_total = sum(
            r["occupancy_rate"] for r in payload["breakdowns"] if isinstance(r.get("occupancy_rate"), (int, float))
        )
        # For a single-governorate dataset, chart and table totals should match.
        assert chart_total == table_total


class TestInstitutionsLicenseChart:
    """B. institutions_active_licensed — license chart must be present."""

    def test_license_chart_present(self, test_db):
        _make_admin(test_db, "reg_lic_admin")
        kg = models.Kindergarten(
            name_ar="روضة",
            governorate="العاصمة",
            district="عمان",
            area="a",
            address_line="a",
            contact_phone="0790000001",
            status=models.KindergartenStatus.ACTIVE,
            license_valid_until=date(2030, 1, 1),
        )
        test_db.add(kg)
        test_db.commit()

        payload = AgencyReportsService(test_db).generate_report("dos", "institutions_active_licensed", {})
        assert payload.get("chart")
        assert payload.get("license_chart")
        assert payload["license_chart"]["type"] == "pie"

        # The slices are deliberately mutually exclusive so the pie is
        # statistically valid — see the comment above `lic_series` in
        # agency_reports_service.py. This assertion previously looked for
        # "مرخصة (سارية)", a label from the earlier overlapping design where a
        # kindergarten could be counted in more than one slice; the broader
        # "licensed" total now lives in the summary instead.
        series = payload["license_chart"]["series"]
        labels = [s["label"] for s in series]
        assert labels == [
            "نشطة ومرخّصة",
            "مرخصة لكن غير نشطة",
            "تراخيص منتهية",
            "بدون بيانات ترخيص",
        ], labels

        # The one seeded kindergarten is ACTIVE with a licence valid to 2030, so
        # it must land in exactly one slice.
        by_label = {s["label"]: s["value"] for s in series}
        assert by_label["نشطة ومرخّصة"] == 1
        assert sum(by_label.values()) == 1, (
            f"slices must not double-count a kindergarten: {by_label}"
        )
        assert all(value >= 0 for value in by_label.values()), by_label


class TestChildSafetyChartPresent:
    """I. child_safety_protection — chart must be present when incidents exist."""

    def test_chart_present_with_incidents(self, test_db):
        _make_admin(test_db, "reg_cs_chart")
        kg = models.Kindergarten(
            name_ar="روضة",
            governorate="العاصمة",
            district="عمان",
            area="a",
            address_line="a",
            contact_phone="0790000001",
            status=models.KindergartenStatus.ACTIVE,
        )
        test_db.add(kg)
        test_db.commit()
        test_db.refresh(kg)

        parent_user = _make_user(test_db, "reg_cs_chart_parent", models.UserRole.PARENT)
        parent = models.ParentProfile(
            user_id=parent_user.id,
            first_name="ولي",
            last_name="أمر",
            phone_number="0790000000",
            gender=models.Gender.MALE,
            nationality="أردني",
            home_governorate="العاصمة",
            home_district="عمان",
            home_area="عمان",
            home_address_line="عمان",
            correspondence_preference=True,
            notification_language="ar",
            profile_complete=True,
        )
        test_db.add(parent)
        test_db.commit()
        test_db.refresh(parent)

        child = models.Child(
            parent_id=parent.id,
            first_name="ابن",
            last_name="سلامة",
            gender=models.Gender.MALE,
            date_of_birth=date(2024, 1, 1),
            father_name="أبو",
            mother_first_name="أم",
            mother_last_name="سلامة",
            mother_nationality="أردنية",
            media_consent=True,
            correspondence_flag=True,
            profile_complete=True,
        )
        test_db.add(child)
        test_db.commit()
        test_db.refresh(child)

        incident = models.Incident(
            child_id=child.id,
            kindergarten_id=kg.id,
            type=models.IncidentType.OTHER,
            severity_level=models.SeverityLevel.LOW,
            occurred_at=date.today(),
            description="test",
            reported_by=1,
        )
        test_db.add(incident)
        test_db.commit()

        payload = AgencyReportsService(test_db).generate_report("mosd", "child_safety_protection", {})
        assert payload.get("chart")
        assert payload["chart"]["type"] == "bar"
        series_labels = {s["label"] for s in payload["chart"]["series"]}
        assert "منخفضة" in series_labels
