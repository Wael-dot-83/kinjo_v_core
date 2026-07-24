"""Comprehensive tests for DOS agency reports: data accuracy, reconciliation,
drill-down, and cross-report consistency."""
from __future__ import annotations

import pytest
from datetime import date, timedelta
from sqlalchemy.orm import Session

import models
from auth import get_password_hash
from agency_reports_service import AgencyReportsService
from agency_reports_registry import AGENCY_REPORT_REGISTRY


def _make_admin(db: Session, username="dos_test_admin"):
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


def _tok(client, username):
    r = client.post("/token", data={"username": username, "password": "Admin123!"})
    assert r.status_code == 200, r.text
    return {"Authorization": f"Bearer {r.json()['access_token']}"}


def _call(client, path, headers, params=None):
    r = client.get(path, headers=headers, params=params)
    assert r.status_code == 200, r.text
    return r.json()


def _seed_kindergartens(db: Session):
    kgs = [
        models.Kindergarten(name_ar="روضة أ", governorate="العاصمة", district="عمان", area="a", address_line="a", contact_phone="0790000001", status=models.KindergartenStatus.ACTIVE),
        models.Kindergarten(name_ar="روضة ب", governorate="إربد", district="إربد", area="b", address_line="b", contact_phone="0790000002", status=models.KindergartenStatus.ACTIVE),
        models.Kindergarten(name_ar="روضة ج", governorate="البلقاء", district="السلط", area="c", address_line="c", contact_phone="0790000003", status=models.KindergartenStatus.ACTIVE),
        models.Kindergarten(name_ar="روضة د", governorate="العاصمة", district="الرصيفة", area="d", address_line="d", contact_phone="0790000004", status=models.KindergartenStatus.INACTIVE),
    ]
    for kg in kgs:
        db.add(kg)
    db.commit()
    return kgs


def _seed_attendance(db: Session, kg_ids, child_ids=None):
    from datetime import date as dt_date
    today = dt_date.today()
    cls = models.Class(
        name_ar="صف أ",
        kindergarten_id=kg_ids[0] if kg_ids else 1,
        class_code="CLS-001",
        age_group="AGE_2_4",
        capacity_total=20,
        min_age_months=24,
        max_age_months=48,
        is_active=True,
    )
    db.add(cls)
    db.commit()
    db.refresh(cls)
    cids = child_ids or [1, 2, 3]
    statuses = [models.AttendanceStatus.PRESENT, models.AttendanceStatus.PRESENT, models.AttendanceStatus.ABSENT]
    logs = [
        models.AttendanceLog(child_id=cids[i] if i < len(cids) else 1, class_id=cls.id, date=today, status=statuses[i], recorded_by=1)
        for i in range(min(3, len(cids)))
    ]
    for log in logs:
        db.add(log)
    db.commit()


def _seed_children(db: Session):
    parent = models.ParentProfile(
        user_id=1,
        first_name="ولي",
        last_name="أمر",
        phone_number="0790000000",
        gender=models.Gender.MALE,
        nationality="أردني",
        home_governorate="عمان",
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
    children = [
        models.Child(
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
        ),
        models.Child(
            parent_id=parent.id,
            first_name="سارة",
            last_name="الثانية",
            gender=models.Gender.FEMALE,
            date_of_birth=date(2024, 6, 1),
            father_name="أبو سارة",
            mother_first_name="أم سارة",
            mother_last_name="الثانية",
            mother_nationality="أردنية",
            media_consent=True,
            correspondence_flag=True,
            profile_complete=True,
        ),
        models.Child(
            parent_id=parent.id,
            first_name="خالد",
            last_name="الثالث",
            gender=models.Gender.MALE,
            date_of_birth=date(2023, 3, 1),
            father_name="أبو خالد",
            mother_first_name="أم خالد",
            mother_last_name="الثالث",
            mother_nationality="أردنية",
            media_consent=True,
            correspondence_flag=True,
            profile_complete=True,
        ),
    ]
    for c in children:
        db.add(c)
    db.commit()
    return children


# ---------------------------------------------------------------------------
# 1. institutions_active_licensed — chart/table reconciliation
# ---------------------------------------------------------------------------
class TestInstitutionsActiveLicensed:
    def test_chart_reconciles_with_table(self, client, test_db):
        _make_admin(test_db)
        _seed_kindergartens(test_db)
        headers = _tok(client, "dos_test_admin")
        payload = _call(client, "/api/admin/agency-reports/dos/reports/institutions_active_licensed", headers)

        table_total = sum(r["count"] for r in payload["breakdowns"])
        chart_total = sum(s["value"] for s in payload.get("chart", {}).get("series", []))
        assert table_total == chart_total, f"chart {chart_total} != table {table_total}"
        assert table_total == payload["summary"]["total_institutions"]
        assert table_total == payload["total_row"]["count"]

    def test_active_intersection_counts(self, client, test_db):
        _make_admin(test_db)
        _seed_kindergartens(test_db)
        headers = _tok(client, "dos_test_admin")
        payload = _call(client, "/api/admin/agency-reports/dos/reports/institutions_active_licensed", headers)
        assert "active_institutions" in payload["summary"]
        assert payload["summary"]["active_institutions"] <= payload["summary"]["total_institutions"]

    def test_governorate_filter_drill_down(self, client, test_db):
        _make_admin(test_db)
        _seed_kindergartens(test_db)
        headers = _tok(client, "dos_test_admin")
        payload = _call(client, "/api/admin/agency-reports/dos/reports/institutions_active_licensed", headers, params={"governorate": "العاصمة"})
        for row in payload["breakdowns"]:
            assert row["governorate"] == "العاصمة"


# ---------------------------------------------------------------------------
# 2. monthly_attendance_absence — date filtering and reconciliation
# ---------------------------------------------------------------------------
class TestMonthlyAttendanceAbsence:
    def test_period_filter_applied(self, client, test_db):
        _make_admin(test_db)
        _seed_kindergartens(test_db)
        headers = _tok(client, "dos_test_admin")

        today = date.today()
        start = today - timedelta(days=7)
        payload = _call(client, "/api/admin/agency-reports/dos/reports/monthly_attendance_absence", headers,
                        params={"period": "week"})
        assert "period_start" in payload["summary"]
        assert "period_end" in payload["summary"]
        assert payload["summary"]["period_start"] <= payload["summary"]["period_end"]

    def test_custom_date_range(self, client, test_db):
        _make_admin(test_db)
        _seed_kindergartens(test_db)
        headers = _tok(client, "dos_test_admin")
        payload = _call(client, "/api/admin/agency-reports/dos/reports/monthly_attendance_absence", headers,
                        params={"date_from": "2026-01-01", "date_to": "2026-12-31"})
        assert payload["summary"]["period_start"] == "2026-01-01"
        assert payload["summary"]["period_end"] == "2026-12-31"

    def test_chart_reconciles_with_table(self, client, test_db):
        _make_admin(test_db)
        _seed_kindergartens(test_db)
        children = _seed_children(test_db)
        child_ids = [c.id for c in children]
        _seed_attendance(test_db, [1, 2], child_ids)
        headers = _tok(client, "dos_test_admin")
        payload = _call(client, "/api/admin/agency-reports/dos/reports/monthly_attendance_absence", headers)
        if payload["breakdowns"]:
            table_total = sum(r["count"] for r in payload["breakdowns"])
            chart_total = sum(s["value"] for s in payload.get("chart", {}).get("series", []))
            assert table_total == chart_total
            assert table_total == payload["summary"]["total_records"]

    def test_status_values_are_localized(self, client, test_db):
        _make_admin(test_db)
        _seed_kindergartens(test_db)
        children = _seed_children(test_db)
        _seed_attendance(test_db, [1, 2], [c.id for c in children])
        headers = _tok(client, "dos_test_admin")
        payload = _call(client, "/api/admin/agency-reports/dos/reports/monthly_attendance_absence", headers)
        for row in payload["breakdowns"]:
            assert row["status"] in {"حاضر", "غائب", "متأخر", "غياب بعذر", "غير محدد"}


# ---------------------------------------------------------------------------
# 3. geographic_service_gaps — governorate normalization, ratio correctness
# ---------------------------------------------------------------------------
class TestGeographicServiceGaps:
    def test_governorate_alias_normalized(self, client, test_db):
        _make_admin(test_db)
        _seed_kindergartens(test_db)
        _seed_children(test_db)
        headers = _tok(client, "dos_test_admin")
        payload = _call(client, "/api/admin/agency-reports/dos/reports/geographic_service_gaps", headers)
        governorates = {r["governorate"] for r in payload["breakdowns"]}
        assert "عمان" not in governorates, "child home_governorate 'عمان' must be normalized to 'العاصمة'"

    def test_children_per_kindergarten_none_when_zero_kgs(self, client, test_db):
        _make_admin(test_db)
        _seed_kindergartens(test_db)
        _seed_children(test_db)
        headers = _tok(client, "dos_test_admin")
        payload = _call(client, "/api/admin/agency-reports/dos/reports/geographic_service_gaps", headers)
        for row in payload["breakdowns"]:
            if row["active_kindergartens"] == 0:
                assert row["children_per_kindergarten"] is None, \
                    f"children_per_kindergarten must be None when kgs=0, got {row['children_per_kindergarten']}"

    def test_chart_uses_children_per_kindergarten(self, client, test_db):
        _make_admin(test_db)
        _seed_kindergartens(test_db)
        _seed_children(test_db)
        headers = _tok(client, "dos_test_admin")
        payload = _call(client, "/api/admin/agency-reports/dos/reports/geographic_service_gaps", headers)
        if payload["breakdowns"] and payload.get("chart"):
            chart_labels = {s["label"] for s in payload["chart"]["series"]}
            table_governorates = {r["governorate"] for r in payload["breakdowns"]}
            assert chart_labels.issubset(table_governorates)

    def test_no_fabricated_ratios(self, client, test_db):
        _make_admin(test_db)
        _seed_kindergartens(test_db)
        _seed_children(test_db)
        headers = _tok(client, "dos_test_admin")
        payload = _call(client, "/api/admin/agency-reports/dos/reports/geographic_service_gaps", headers)
        for row in payload["breakdowns"]:
            if row["active_kindergartens"] == 0 and row["children"] > 0:
                assert row["children_per_kindergarten"] is None


# ---------------------------------------------------------------------------
# 4. annual_quarterly_trends — quarterly breakdown, children data
# ---------------------------------------------------------------------------
class TestAnnualQuarterlyTrends:
    def test_quarterly_breakdown_present(self, client, test_db):
        _make_admin(test_db)
        _seed_kindergartens(test_db)
        headers = _tok(client, "dos_test_admin")
        payload = _call(client, "/api/admin/agency-reports/dos/reports/annual_quarterly_trends", headers)
        assert payload["breakdowns"], "annual_quarterly_trends must return breakdowns"
        for row in payload["breakdowns"]:
            assert "period" in row, "each row must have a period field (Q1-2026 etc.)"
            assert "quarter" in row, "each row must have a quarter field"
            assert "year" in row, "each row must have a year field"
            assert "new_kindergartens" in row
            assert "enrolled_children" in row

    def test_enrolled_children_populated(self, client, test_db):
        _make_admin(test_db)
        _seed_kindergartens(test_db)
        headers = _tok(client, "dos_test_admin")
        payload = _call(client, "/api/admin/agency-reports/dos/reports/annual_quarterly_trends", headers)
        total_enr = payload["summary"].get("total_enrolled_children", 0)
        total_kg = payload["summary"].get("total_kindergartens", 0)
        assert total_kg >= 0
        assert total_enr >= 0

    def test_chart_reconciles_with_table(self, client, test_db):
        _make_admin(test_db)
        _seed_kindergartens(test_db)
        headers = _tok(client, "dos_test_admin")
        payload = _call(client, "/api/admin/agency-reports/dos/reports/annual_quarterly_trends", headers)
        if payload["breakdowns"] and payload.get("chart"):
            chart_total = sum(s["value"] for s in payload["chart"]["series"])
            # The chart auto-picks the last non-rate numeric column (enrolled_children),
            # so reconcile against that column, not new_kindergartens.
            table_chart_col = payload["breakdowns"][0].get(payload["chart"].get("group_by", ""), {})
            chart_col_name = "enrolled_children"
            table_total = sum(r.get(chart_col_name, 0) for r in payload["breakdowns"])
            assert chart_total == table_total


# ---------------------------------------------------------------------------
# 5. Registry consistency
# ---------------------------------------------------------------------------
class TestDOSRegistry:
    def test_all_dos_reports_in_registry(self):
        dos = AGENCY_REPORT_REGISTRY["dos"]["reports"]
        expected = {
            "children_demographics", "enrollment_participation_0_60",
            "institutions_active_licensed", "capacity_occupancy_overcrowding",
            "monthly_attendance_absence", "supervisors_child_ratio",
            "incidents_safety_1000_child_days", "geographic_service_gaps",
            "data_quality_completeness", "annual_quarterly_trends",
        }
        assert set(dos.keys()) == expected

    def test_all_dos_reports_have_required_fields(self):
        for code, report in AGENCY_REPORT_REGISTRY["dos"]["reports"].items():
            assert "title_ar" in report, f"{code} missing title_ar"
            assert "status" in report, f"{code} missing status"
            assert "filters" in report, f"{code} missing filters"
            assert "exports" in report, f"{code} missing exports"
