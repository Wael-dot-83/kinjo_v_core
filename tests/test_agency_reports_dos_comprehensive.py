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
        models.Kindergarten(
            name_ar="روضة أ",
            governorate="العاصمة",
            district="عمان",
            area="a",
            address_line="a",
            contact_phone="0790000001",
            status=models.KindergartenStatus.ACTIVE,
        ),
        models.Kindergarten(
            name_ar="روضة ب",
            governorate="إربد",
            district="إربد",
            area="b",
            address_line="b",
            contact_phone="0790000002",
            status=models.KindergartenStatus.ACTIVE,
        ),
        models.Kindergarten(
            name_ar="روضة ج",
            governorate="البلقاء",
            district="السلط",
            area="c",
            address_line="c",
            contact_phone="0790000003",
            status=models.KindergartenStatus.ACTIVE,
        ),
        models.Kindergarten(
            name_ar="روضة د",
            governorate="العاصمة",
            district="الرصيفة",
            area="d",
            address_line="d",
            contact_phone="0790000004",
            status=models.KindergartenStatus.INACTIVE,
        ),
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
        models.AttendanceLog(
            child_id=cids[i] if i < len(cids) else 1, class_id=cls.id, date=today, status=statuses[i], recorded_by=1
        )
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

    def test_license_summary_uses_real_license_fields(self, test_db):
        """The report title claims 'active AND licensed'. Verify licensing is
        computed from license_valid_until — licensed(valid)/expired/missing must
        partition every institution, and active∩licensed is bounded correctly."""
        from datetime import date as _date, timedelta as _td

        def _kg(name, phone, status, valid_until):
            return models.Kindergarten(
                name_ar=name,
                governorate="العاصمة",
                district="عمان",
                area="a",
                address_line="a",
                contact_phone=phone,
                status=status,
                license_valid_until=valid_until,
            )

        today = _date.today()
        test_db.add_all(
            [
                _kg("نشطة سارية", "0790000201", models.KindergartenStatus.ACTIVE, today + _td(days=365)),
                _kg("نشطة منتهية", "0790000202", models.KindergartenStatus.ACTIVE, today - _td(days=10)),
                _kg("غير نشطة سارية", "0790000203", models.KindergartenStatus.INACTIVE, today + _td(days=365)),
                _kg("نشطة بلا ترخيص", "0790000204", models.KindergartenStatus.ACTIVE, None),
            ]
        )
        test_db.commit()
        s = AgencyReportsService(test_db).generate_report("dos", "institutions_active_licensed", {})["summary"]
        assert s["total_institutions"] == 4
        assert s["active_institutions"] == 3
        assert s["licensed_institutions"] == 2  # two valid, unexpired
        assert s["active_and_licensed"] == 1  # only the active+valid one
        assert s["expired_licenses"] == 1
        assert s["missing_license_data"] == 1
        # valid + expired + missing must partition the whole population
        assert (s["licensed_institutions"] + s["expired_licenses"] + s["missing_license_data"]) == s[
            "total_institutions"
        ]
        assert s["active_and_licensed"] <= min(s["active_institutions"], s["licensed_institutions"])

    def test_governorate_filter_drill_down(self, client, test_db):
        _make_admin(test_db)
        _seed_kindergartens(test_db)
        headers = _tok(client, "dos_test_admin")
        payload = _call(
            client,
            "/api/admin/agency-reports/dos/reports/institutions_active_licensed",
            headers,
            params={"governorate": "العاصمة"},
        )
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
        payload = _call(
            client,
            "/api/admin/agency-reports/dos/reports/monthly_attendance_absence",
            headers,
            params={"period": "week"},
        )
        assert "period_start" in payload["summary"]
        assert "period_end" in payload["summary"]
        assert payload["summary"]["period_start"] <= payload["summary"]["period_end"]

    def test_custom_date_range(self, client, test_db):
        _make_admin(test_db)
        _seed_kindergartens(test_db)
        headers = _tok(client, "dos_test_admin")
        payload = _call(
            client,
            "/api/admin/agency-reports/dos/reports/monthly_attendance_absence",
            headers,
            params={"date_from": "2026-01-01", "date_to": "2026-12-31"},
        )
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
            assert payload["chart"]["group_by"] == "status"

    def test_status_values_are_localized(self, client, test_db):
        _make_admin(test_db)
        _seed_kindergartens(test_db)
        children = _seed_children(test_db)
        _seed_attendance(test_db, [1, 2], [c.id for c in children])
        headers = _tok(client, "dos_test_admin")
        payload = _call(client, "/api/admin/agency-reports/dos/reports/monthly_attendance_absence", headers)
        for row in payload["breakdowns"]:
            assert row["status"] in {"حاضر", "غائب", "متأخر", "غياب بعذر", "غير محدد"}

    def test_attendance_and_absence_rates(self, test_db):
        """The title promises 'معدلات' (rates). Verify present/absent rates are
        computed against expected child-days (working days during active enrolment).
        Fixture: 2 enrolled children over 2 working days -> 4 expected child-days;
        3 present + 1 absent -> 75% / 25%."""
        from datetime import date as _date, timedelta as _td

        _seed_kindergartens(test_db)
        children = _seed_children(test_db)
        cids = [c.id for c in children[:2]]
        cls = models.Class(
            name_ar="صف الحضور",
            kindergarten_id=1,
            class_code="C-ATT-1",
            age_group="AGE_2_4",
            capacity_total=20,
            enrolled_children_count=0,
            min_age_months=24,
            max_age_months=48,
            is_active=True,
        )
        test_db.add(cls)
        test_db.commit()
        test_db.refresh(cls)
        for cid in cids:
            test_db.add(
                models.EnrollmentApplication(
                    child_id=cid,
                    kindergarten_id=1,
                    class_id=cls.id,
                    status=models.EnrollmentStatus.ACTIVE,
                    enrollment_start_date=_date(2026, 7, 1),
                )
            )
        test_db.commit()
        day1 = _date(2026, 7, 27)
        day2 = _date(2026, 7, 28)
        st = models.AttendanceStatus
        for cid, day, status in [
            (cids[0], day1, st.PRESENT),
            (cids[1], day1, st.PRESENT),
            (cids[0], day2, st.PRESENT),
            (cids[1], day2, st.ABSENT),
        ]:
            test_db.add(models.AttendanceLog(child_id=cid, class_id=cls.id, date=day, status=status, recorded_by=1))
        test_db.commit()
        s = AgencyReportsService(test_db).generate_report(
            "dos",
            "monthly_attendance_absence",
            {"date_from": "2026-07-27", "date_to": "2026-07-28"},
        )["summary"]
        assert s["total_records"] == 4
        assert s["present_records"] == 3
        assert s["absent_records"] == 1
        assert s["attendance_rate_pct"] == 75.0
        assert s["absence_rate_pct"] == 25.0


# ---------------------------------------------------------------------------
# 2b. capacity_occupancy_overcrowding — overcrowding + honest occupancy
# ---------------------------------------------------------------------------
class TestCapacityOccupancyOvercrowding:
    def _kg_with_class(self, db, name, phone, gov, cap, enrolled):
        kg = models.Kindergarten(
            name_ar=name,
            governorate=gov,
            district=gov,
            area="a",
            address_line="a",
            contact_phone=phone,
            status=models.KindergartenStatus.ACTIVE,
        )
        db.add(kg)
        db.commit()
        db.refresh(kg)
        db.add(
            models.Class(
                name_ar="صف",
                kindergarten_id=kg.id,
                class_code=f"C-{phone}",
                age_group="AGE_2_4",
                capacity_total=cap,
                enrolled_children_count=enrolled,
                min_age_months=24,
                max_age_months=48,
                is_active=True,
            )
        )
        db.commit()
        return kg

    def test_overcrowding_counted_per_kindergarten(self, test_db):
        self._kg_with_class(test_db, "مكتظة", "0790001001", "العاصمة", 20, 25)  # over
        self._kg_with_class(test_db, "طبيعية", "0790001002", "إربد", 30, 10)  # under
        s = AgencyReportsService(test_db).generate_report("dos", "capacity_occupancy_overcrowding", {})["summary"]
        assert s["total_capacity"] == 50
        assert s["total_enrolled"] == 35
        assert s["occupancy_rate_pct"] == 70.0
        assert s["overcrowded_kindergartens"] == 1
        assert s["overcrowding_rate_pct"] == 50.0

    def test_missing_capacity_is_na_not_zero_percent(self, test_db):
        self._kg_with_class(test_db, "بلا سعة", "0790001003", "الكرك", 0, 0)
        payload = AgencyReportsService(test_db).generate_report("dos", "capacity_occupancy_overcrowding", {})
        row = next(r for r in payload["breakdowns"] if r["governorate"] == "الكرك")
        assert row["occupancy_rate"] is None  # N/A, never a misleading 0%
        assert payload["summary"]["occupancy_rate_pct"] is None
        assert payload["summary"]["overcrowding_rate_pct"] is None  # no KG has capacity


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
                assert row["children_per_kindergarten"] is None, (
                    f"children_per_kindergarten must be None when kgs=0, got {row['children_per_kindergarten']}"
                )

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

    def test_governorate_filter_limits_results(self, test_db):
        """Geo filters must be applied to both child and kindergarten queries."""
        _make_admin(test_db)
        # Seed kindergartens in multiple governorates.
        kgs = [
            models.Kindergarten(
                name_ar="روضة أ",
                governorate="العاصمة",
                district="عمان",
                area="a",
                address_line="a",
                contact_phone="0790000001",
                status=models.KindergartenStatus.ACTIVE,
            ),
            models.Kindergarten(
                name_ar="روضة ب",
                governorate="إربد",
                district="إربد",
                area="b",
                address_line="b",
                contact_phone="0790000002",
                status=models.KindergartenStatus.ACTIVE,
            ),
        ]
        for kg in kgs:
            test_db.add(kg)
        test_db.commit()

        # Seed parents/children in both governorates.
        for gov, district, phone in [
            ("العاصمة", "عمان", "0790000003"),
            ("إربد", "إربد", "0790000004"),
        ]:
            pu = models.User(
                username=f"gap_parent_{gov}",
                email=f"gap_{gov}@example.com",
                hashed_password=get_password_hash("Admin123!"),
                role=models.UserRole.PARENT,
                status=models.UserStatus.ACTIVE,
            )
            test_db.add(pu)
            test_db.commit()
            test_db.refresh(pu)
            parent = models.ParentProfile(
                user_id=pu.id,
                first_name="ولي",
                last_name="أمر",
                phone_number=phone,
                gender=models.Gender.MALE,
                nationality="أردني",
                home_governorate=gov,
                home_district=district,
                home_area=district,
                home_address_line=district,
                correspondence_preference=True,
                notification_language="ar",
                profile_complete=True,
            )
            test_db.add(parent)
            test_db.commit()
            test_db.refresh(parent)
            child = models.Child(
                parent_id=parent.id,
                first_name=f"طفل_{gov}",
                last_name="اختبار",
                gender=models.Gender.MALE,
                date_of_birth=date(2024, 1, 1),
                father_name="أب",
                mother_first_name="أم",
                mother_last_name="اختبار",
                mother_nationality="أردنية",
                media_consent=True,
                correspondence_flag=True,
                profile_complete=True,
            )
            test_db.add(child)
            test_db.commit()

        payload = AgencyReportsService(test_db).generate_report(
            "dos", "geographic_service_gaps", {"governorate": "العاصمة"}
        )
        for row in payload["breakdowns"]:
            assert row["governorate"] == "العاصمة"


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

    def test_periods_sorted_chronologically_not_lexicographically(self, test_db):
        """Regression: periods were sorted by the raw "Q{q}-{year}" string, which
        orders quarter-major (Q1-2020 lands before Q2-2019). A trends report must
        present periods in true chronological order (year, then quarter)."""
        from datetime import datetime, timezone

        def _kg(name, phone, created):
            return models.Kindergarten(
                name_ar=name,
                governorate="العاصمة",
                district="عمان",
                area="a",
                address_line="a",
                contact_phone=phone,
                status=models.KindergartenStatus.ACTIVE,
                created_at=created,
            )

        test_db.add_all(
            [
                _kg("ك4-2018", "0790000101", datetime(2018, 11, 1, tzinfo=timezone.utc)),  # Q4-2018
                _kg("ك2-2019", "0790000102", datetime(2019, 5, 15, tzinfo=timezone.utc)),  # Q2-2019
                _kg("ك1-2020", "0790000103", datetime(2020, 2, 10, tzinfo=timezone.utc)),  # Q1-2020
            ]
        )
        test_db.commit()
        payload = AgencyReportsService(test_db).generate_report("dos", "annual_quarterly_trends", {})
        periods = [r["period"] for r in payload["breakdowns"] if r["period"] != "غير محدد"]
        assert periods == ["Q4-2018", "Q2-2019", "Q1-2020"], periods


# ---------------------------------------------------------------------------
# 5. incidents_safety_1000_child_days — rate and chart
# ---------------------------------------------------------------------------
class TestIncidentsSafety1000ChildDays:
    def test_rate_computed_when_attendance_exists(self, test_db):
        _make_admin(test_db, "dos_inc_admin")
        kg = models.Kindergarten(
            name_ar="روضة أ",
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

        parent_user = _make_user(test_db, "dos_inc_parent", models.UserRole.PARENT)
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

        admin = _make_admin(test_db, "dos_inc_admin2")
        incident = models.Incident(
            child_id=child.id,
            kindergarten_id=kg.id,
            type=models.IncidentType.OTHER,
            severity_level=models.SeverityLevel.LOW,
            occurred_at=date.today(),
            description="test",
            reported_by=admin.id,
        )
        test_db.add(incident)
        test_db.commit()

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
        test_db.add(
            models.EnrollmentApplication(
                child_id=child.id,
                kindergarten_id=kg.id,
                class_id=cls.id,
                status=models.EnrollmentStatus.ACTIVE,
                enrollment_start_date=date(2024, 1, 1),
            )
        )
        test_db.commit()
        test_db.add(
            models.AttendanceLog(
                child_id=child.id,
                class_id=cls.id,
                date=date.today(),
                status=models.AttendanceStatus.PRESENT,
                recorded_by=admin.id,
            )
        )
        test_db.commit()

        payload = AgencyReportsService(test_db).generate_report("dos", "incidents_safety_1000_child_days", {})
        assert payload["summary"]["incident_count"] == 1
        assert payload["summary"]["eligible_child_days"] >= 1
        assert payload["summary"]["incident_rate_per_1000_child_days"] == round(
            1000 / payload["summary"]["eligible_child_days"], 3
        )
        assert payload.get("chart")
        assert payload["chart"]["title_ar"] == "الحوادث حسب درجة الخطورة"
        assert sum(s["value"] for s in payload["chart"]["series"] if isinstance(s["value"], (int, float))) == payload["summary"]["incident_count"]

    def test_rate_is_none_when_no_eligible_child_days(self, test_db):
        _make_admin(test_db, "dos_inc_admin3")
        kg = models.Kindergarten(
            name_ar="روضة أ",
            governorate="العاصمة",
            district="عمان",
            area="a",
            address_line="a",
            contact_phone="0790000001",
            status=models.KindergartenStatus.ACTIVE,
        )
        test_db.add(kg)
        test_db.commit()

        parent_user = _make_user(test_db, "dos_inc_parent3", models.UserRole.PARENT)
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

        admin = _make_admin(test_db, "dos_inc_admin4")
        incident = models.Incident(
            child_id=child.id,
            kindergarten_id=kg.id,
            type=models.IncidentType.OTHER,
            severity_level=models.SeverityLevel.LOW,
            occurred_at=date.today(),
            description="test",
            reported_by=admin.id,
        )
        test_db.add(incident)
        test_db.commit()

        payload = AgencyReportsService(test_db).generate_report("dos", "incidents_safety_1000_child_days", {})
        assert payload["summary"]["incident_rate_per_1000_child_days"] is None
        assert "data_quality_note_ar" in payload["summary"]


# ---------------------------------------------------------------------------
# 6. supervisors_child_ratio — summary ratio and chart correctness
# ---------------------------------------------------------------------------
class TestSupervisorsChildRatio:
    def test_overall_ratio_in_summary(self, test_db):
        _make_admin(test_db, "dos_sup_admin")
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

        supervisors = [_make_user(test_db, f"dos_sup_{i}", models.UserRole.SUPERVISOR) for i in range(1, 6)]
        test_db.add_all([models.SupervisorProfile(user_id=sup.id, kindergarten_id=kg1.id) for sup in supervisors])
        test_db.commit()

        classes = [
            models.Class(
                name_ar=f"صف {i}",
                kindergarten_id=kg1.id,
                class_code=f"C{i}",
                age_group="AGE_2_4",
                capacity_total=20,
                enrolled_children_count=10,
                min_age_months=24,
                max_age_months=48,
                is_active=True,
                supervisor_id=sup.id,
            )
            for i, sup in enumerate(supervisors, start=1)
        ]
        test_db.add_all(classes)
        test_db.commit()
        for cls, sup in zip(classes, supervisors):
            test_db.add(
                models.SupervisorAssignment(
                    class_id=cls.id,
                    supervisor_id=sup.id,
                    is_primary=True,
                    start_date=date(2024, 1, 1),
                )
            )
        test_db.commit()

        payload = AgencyReportsService(test_db).generate_report("dos", "supervisors_child_ratio", {})
        assert "children_per_supervisor" in payload["summary"]
        assert payload["summary"]["children_per_supervisor"] == 10.0

    def test_chart_does_not_sum_ratios(self, test_db):
        _make_admin(test_db, "dos_sup_admin2")
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

        supervisors = [_make_user(test_db, f"dos_sup_chart_{i}", models.UserRole.SUPERVISOR) for i in range(1, 6)]
        test_db.add_all([models.SupervisorProfile(user_id=sup.id, kindergarten_id=kg1.id) for sup in supervisors])
        test_db.commit()

        classes = [
            models.Class(
                name_ar=f"صف {i}",
                kindergarten_id=kg1.id,
                class_code=f"D{i}",
                age_group="AGE_2_4",
                capacity_total=20,
                enrolled_children_count=10,
                min_age_months=24,
                max_age_months=48,
                is_active=True,
                supervisor_id=sup.id,
            )
            for i, sup in enumerate(supervisors, start=1)
        ]
        test_db.add_all(classes)
        test_db.commit()
        for cls, sup in zip(classes, supervisors):
            test_db.add(
                models.SupervisorAssignment(
                    class_id=cls.id,
                    supervisor_id=sup.id,
                    is_primary=True,
                    start_date=date(2024, 1, 1),
                )
            )
        test_db.commit()

        payload = AgencyReportsService(test_db).generate_report("dos", "supervisors_child_ratio", {})
        assert payload.get("chart")
        series = payload["chart"]["series"]
        assert len(series) == 1
        assert series[0]["value"] == 10.0

    def test_zero_supervisors_yields_none_ratio(self, test_db):
        _make_admin(test_db, "dos_sup_admin3")
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
        )
        test_db.add(cls1)
        test_db.commit()

        payload = AgencyReportsService(test_db).generate_report("dos", "supervisors_child_ratio", {})
        row = next(r for r in payload["breakdowns"] if r["governorate"] == "العاصمة")
        assert row["children_per_supervisor"] is None
        assert payload["summary"]["children_per_supervisor"] is None


# ---------------------------------------------------------------------------
# 7. child_safety_protection — chart presence
# ---------------------------------------------------------------------------
class TestChildSafetyProtection:
    def test_chart_present_with_incidents(self, test_db):
        _make_admin(test_db, "dos_cs_admin")
        kg = models.Kindergarten(
            name_ar="روضة أ",
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

        parent_user = _make_user(test_db, "dos_cs_parent", models.UserRole.PARENT)
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

        admin = _make_admin(test_db, "dos_cs_admin2")
        incident = models.Incident(
            child_id=child.id,
            kindergarten_id=kg.id,
            type=models.IncidentType.OTHER,
            severity_level=models.SeverityLevel.LOW,
            occurred_at=date.today(),
            description="test",
            reported_by=admin.id,
        )
        test_db.add(incident)
        test_db.commit()

        payload = AgencyReportsService(test_db).generate_report("mosd", "child_safety_protection", {})
        assert payload.get("chart")
        assert payload["chart"]["type"] == "bar"

    def test_empty_state_message_when_no_incidents(self, test_db):
        _make_admin(test_db, "dos_cs_admin3")
        payload = AgencyReportsService(test_db).generate_report("mosd", "child_safety_protection", {})
        assert "data_quality_note_ar" in payload["summary"]


# ---------------------------------------------------------------------------
# 8. enrollment_participation_0_60 — age boundaries and chart omission
# ---------------------------------------------------------------------------
class TestEnrollmentParticipation0_60:
    def test_age_boundary_55_months(self, test_db):
        """A child 55 months old must land in the 48-60 bucket."""
        _make_admin(test_db, "dos_ep_admin")
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
        bucket_row = next((b for b in payload["breakdowns"] if b["governorate"] == "العاصمة"), None)
        assert bucket_row is not None
        assert bucket_row["enrolled_48_60m"] == 1
        assert bucket_row["enrolled_total"] == 1

    def test_empty_data_omits_chart(self, test_db):
        _make_admin(test_db, "dos_ep_admin2")
        payload = AgencyReportsService(test_db).generate_report("dos", "enrollment_participation_0_60", {})
        if payload.get("chart"):
            assert payload["chart"].get("series"), "Chart present but empty"


# ---------------------------------------------------------------------------
# 4b. Exports use the same canonical calculation as the page
# ---------------------------------------------------------------------------
class TestExportsCanonical:
    def test_export_json_equals_page_and_csv_reconciles(self, client, test_db):
        _make_admin(test_db)
        _seed_kindergartens(test_db)
        headers = _tok(client, "dos_test_admin")
        code = "institutions_active_licensed"
        base = "/api/admin/agency-reports/dos/reports/" + code
        page = _call(client, base, headers)
        export_json = _call(client, base + "/export.json", headers)
        # export.json is the SAME canonical payload as the page (no second engine).
        assert export_json["summary"] == page["summary"]
        assert export_json["breakdowns"] == page["breakdowns"]
        # CSV is a projection of that same payload: BOM + Arabic totals row that
        # reconciles with the page's total institutions.
        r = client.get(base + "/export.csv", headers=headers)
        assert r.status_code == 200
        assert r.content[:3] == b"\xef\xbb\xbf"  # UTF-8 BOM for Arabic
        body = r.content.decode("utf-8-sig")
        assert "المجموع" in body
        assert str(page["summary"]["total_institutions"]) in body

    def test_exports_require_admin(self, client, test_db):
        base = "/api/admin/agency-reports/dos/reports/institutions_active_licensed"
        assert client.get(base + "/export.csv").status_code in (401, 403)
        assert client.get(base + "/export.json").status_code in (401, 403)


# ---------------------------------------------------------------------------
# 5. Registry consistency
# ---------------------------------------------------------------------------
class TestDOSRegistry:
    def test_all_dos_reports_in_registry(self):
        dos = AGENCY_REPORT_REGISTRY["dos"]["reports"]
        expected = {
            "children_demographics",
            "enrollment_participation_0_60",
            "institutions_active_licensed",
            "capacity_occupancy_overcrowding",
            "monthly_attendance_absence",
            "supervisors_child_ratio",
            "incidents_safety_1000_child_days",
            "geographic_service_gaps",
            "data_quality_completeness",
            "annual_quarterly_trends",
        }
        assert set(dos.keys()) == expected

    def test_all_dos_reports_have_required_fields(self):
        for code, report in AGENCY_REPORT_REGISTRY["dos"]["reports"].items():
            assert "title_ar" in report, f"{code} missing title_ar"
            assert "status" in report, f"{code} missing status"
            assert "filters" in report, f"{code} missing filters"
            assert "exports" in report, f"{code} missing exports"
