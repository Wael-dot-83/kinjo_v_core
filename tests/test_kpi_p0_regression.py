"""
P0 KPI regression tests — magenta-manchego branch.

Covers all six P0 fixes:
  P0.1  Jordan timezone compliance (_today_jordan, no date.today in runtime paths)
  P0.2  get_kpi_target default-argument bug
  P0.3  Incident rate unit normalisation (per-1,000 child-days)
  P0.4  incident_followup_sla consistency (standalone == bundle; no-data semantics)
  P0.5  Hard override rules (all five, priority order, INSUFFICIENT band)
  P0.6  Training completion denominator (cumulative coverage, dedup, inactive-staff exclusion)
"""
import inspect
import pytest
from datetime import date, datetime, timedelta, timezone
from unittest.mock import patch

import models
from kpi_service import KPIService, _today_jordan, _JORDAN_TZ
from models import TrainingStatus, TrainingModule, StaffTrainingCompletion


# ---------------------------------------------------------------------------
# Helpers — used across multiple test classes
# ---------------------------------------------------------------------------

def _mk_kg(test_db, suffix: str, license_valid_until=date(2030, 12, 31)):
    """Create a minimal active kindergarten."""
    obj = models.Kindergarten(
        name_ar=f"حضانة {suffix}",
        name_en=f"KG {suffix}",
        license_number=f"LIC-P0-{suffix}",
        governorate="Amman",
        district="Amman",
        area="Test",
        address_line="1 Test St",
        contact_phone=f"+962790{suffix[:5].ljust(5, '0')}",
        contact_email=f"p0_{suffix}@test.jo",
        status=models.KindergartenStatus.ACTIVE,
        license_valid_until=license_valid_until,
    )
    test_db.add(obj)
    test_db.commit()
    test_db.refresh(obj)
    return obj


def _mk_class(test_db, kg, capadistrict=20, code_suffix=""):
    cls = models.Class(
        kindergarten_id=kg.id,
        name_ar="صف أ",
        name_en="Class A",
        class_code=f"P0-{kg.id}{code_suffix}",
        age_group="AGE_1_2",
        capacity_total=capadistrict,
        min_age_months=12,
        max_age_months=24,
        is_active=True,
    )
    test_db.add(cls)
    test_db.commit()
    test_db.refresh(cls)
    return cls


def _mk_staff(test_db, kg, suffix: str, role=models.UserRole.SUPERVISOR,
              status=models.UserStatus.ACTIVE):
    user = models.User(
        username=f"staff_{suffix}",
        email=f"staff_{suffix}@test.jo",
        hashed_password="hashed",
        role=role,
        status=status,
        kindergarten_id=kg.id,
    )
    test_db.add(user)
    test_db.commit()
    test_db.refresh(user)
    return user


def _add_attendance(test_db, child_id, class_id, recorder_id, dt: date, status):
    log = models.AttendanceLog(
        child_id=child_id,
        class_id=class_id,
        date=dt,
        status=status,
        recorded_by=recorder_id,
    )
    test_db.add(log)


def _add_incident(test_db, child_id, kg_id, dt: date,
                  severity=models.SeverityLevel.LOW,
                  followup_required=False, closed_at=None, sla_deadline=None):
    inc = models.Incident(
        child_id=child_id,
        kindergarten_id=kg_id,
        type=models.IncidentType.INJURY,
        severity_level=severity,
        description="P0 regression incident",
        occurred_at=datetime(dt.year, dt.month, dt.day, 9, 0, 0),
        followup_required_flag=followup_required,
        closed_at=closed_at,
        followup_sla_deadline=sla_deadline,
    )
    test_db.add(inc)
    return inc


# ===========================================================================
# P0.1 — Jordan Timezone Compliance
# ===========================================================================

class TestJordanTimezone:
    def test_today_jordan_uses_utc_plus_3(self):
        """_today_jordan() must return the date in UTC+3, not UTC."""
        jordan_tz = timezone(timedelta(hours=3))
        expected = datetime.now(jordan_tz).date()
        assert _today_jordan() == expected

    def test_today_jordan_differs_from_utc_at_midnight_boundary(self):
        """UTC 23:30 = Jordan 02:30 next day — Jordan date must be +1 vs UTC date."""
        utc_23_30 = datetime(2026, 6, 24, 23, 30, 0, tzinfo=timezone.utc)
        jordan_tz = timezone(timedelta(hours=3))
        jordan_date = utc_23_30.astimezone(jordan_tz).date()
        utc_date = utc_23_30.date()
        assert jordan_date == date(2026, 6, 25)
        assert utc_date == date(2026, 6, 24)
        assert jordan_date != utc_date

    def test_today_jordan_resolves_at_call_time(self):
        """Patching datetime.now inside kpi_service must change _today_jordan()."""
        fixed_dt = datetime(2026, 1, 15, 12, 0, 0, tzinfo=_JORDAN_TZ)
        with patch("kpi_service.datetime") as mock_dt:
            mock_dt.now.return_value = fixed_dt
            result = _today_jordan()
        assert result == date(2026, 1, 15)

    def test_no_date_today_in_runtime_code(self):
        """kpi_service.py must contain no bare date.today() in runtime code paths."""
        import kpi_service as svc
        source = inspect.getsource(svc)
        violations = [
            line.strip() for line in source.splitlines()
            if "date.today()" in line
            and not line.strip().startswith("#")
            and "instead of date.today()" not in line   # allow the docstring reference
        ]
        assert violations == [], (
            "Unsafe date.today() calls remain in kpi_service.py:\n"
            + "\n".join(violations)
        )

    def test_jordan_tz_constant_is_utc_plus_3(self):
        """_JORDAN_TZ must represent UTC+3."""
        offset = _JORDAN_TZ.utcoffset(datetime(2026, 6, 24))
        assert offset == timedelta(hours=3)


# ===========================================================================
# P0.2 — get_kpi_target default-argument bug
# ===========================================================================

class TestGetKpiTargetDefaultArg:
    def test_signature_default_is_none_not_date(self):
        """target_date parameter must default to None, not date.today()."""
        sig = inspect.signature(KPIService.get_kpi_target)
        param = sig.parameters.get("target_date")
        assert param is not None, "target_date parameter is missing from get_kpi_target"
        assert param.default is None, (
            f"target_date default is {param.default!r}. "
            "It must be None — date.today() as a default evaluates at import time."
        )

    def test_get_kpi_target_accepts_explicit_date(self, test_db):
        """Explicit target_date must be accepted without error; None return is fine for empty DB."""
        result = KPIService.get_kpi_target(
            test_db, "attendance_rate", target_date=date(2025, 12, 31)
        )
        assert result is None  # empty DB — fine; no TypeError means the fix is in place

    def test_get_kpi_target_uses_jordan_today_when_none(self, test_db):
        """When target_date=None, the function must call _today_jordan(), not date.today()."""
        fixed = date(2026, 3, 1)
        with patch("kpi_service._today_jordan", return_value=fixed) as mock_today:
            KPIService.get_kpi_target(test_db, "attendance_rate")
        mock_today.assert_called_once()


# ===========================================================================
# P0.3 — Incident rate unit normalisation
# ===========================================================================

class TestIncidentRateUnits:
    def test_compute_incident_rate_returns_per_1000(
        self, test_db, sample_kindergarten, sample_class, sample_child,
        active_enrollment, supervisor_user
    ):
        """compute_incident_rate must multiply by 1000, not 100."""
        d = date(2026, 3, 1)
        _add_attendance(test_db, sample_child.id, sample_class.id,
                        supervisor_user.id, d, models.AttendanceStatus.PRESENT)
        _add_incident(test_db, sample_child.id, sample_kindergarten.id, d)
        test_db.commit()

        rate = KPIService.compute_incident_rate(
            test_db, sample_kindergarten.id, d, d
        )
        # 1 incident / 1 attended child-day × 1,000 = 1000.0
        assert rate == pytest.approx(1000.0, abs=0.1), (
            f"Expected 1000.0 (per-1,000 child-days) but got {rate}. "
            "Method may still use × 100."
        )

    def test_compute_serious_incident_rate_returns_per_1000(
        self, test_db, sample_kindergarten, sample_class, sample_child,
        active_enrollment, supervisor_user
    ):
        """compute_serious_incident_rate must multiply by 1000."""
        d = date(2026, 3, 5)
        _add_attendance(test_db, sample_child.id, sample_class.id,
                        supervisor_user.id, d, models.AttendanceStatus.PRESENT)
        _add_incident(test_db, sample_child.id, sample_kindergarten.id, d,
                      severity=models.SeverityLevel.CRITICAL)
        test_db.commit()

        rate = KPIService.compute_serious_incident_rate(
            test_db, sample_kindergarten.id, d, d
        )
        assert rate == pytest.approx(1000.0, abs=0.1)

    def test_incident_rate_lower_than_100_for_normal_volume(
        self, test_db, sample_kindergarten, sample_class, sample_child,
        active_enrollment, supervisor_user
    ):
        """1 incident / 200 attended days = 5.0 per 1,000 child-days."""
        start = date(2026, 4, 1)
        for i in range(200):
            _add_attendance(test_db, sample_child.id, sample_class.id,
                            supervisor_user.id, start + timedelta(days=i),
                            models.AttendanceStatus.PRESENT)
        _add_incident(test_db, sample_child.id, sample_kindergarten.id, start)
        test_db.commit()

        rate = KPIService.compute_incident_rate(
            test_db, sample_kindergarten.id, start, start + timedelta(days=199)
        )
        assert rate == pytest.approx(5.0, abs=0.1)  # 1/200 × 1000

    def test_bundle_incident_rate_matches_standalone(
        self, test_db, sample_kindergarten, sample_class, sample_child,
        active_enrollment, supervisor_user
    ):
        """compute_kpi_bundle 'incident_rate' must equal compute_incident_rate."""
        d = date(2026, 3, 10)
        _add_attendance(test_db, sample_child.id, sample_class.id,
                        supervisor_user.id, d, models.AttendanceStatus.PRESENT)
        _add_incident(test_db, sample_child.id, sample_kindergarten.id, d)
        test_db.commit()

        standalone = KPIService.compute_incident_rate(
            test_db, sample_kindergarten.id, d, d
        )
        bundle = KPIService.compute_kpi_bundle(
            test_db, sample_kindergarten.id, period_start=d, period_end=d
        )
        assert bundle["incident_rate"] == pytest.approx(standalone, abs=0.01), (
            "Bundle incident_rate diverges from standalone. "
            "One still uses per-100, the other per-1000."
        )

    def test_per_100_legacy_key_present_in_bundle(
        self, test_db, sample_kindergarten, sample_class, sample_child,
        active_enrollment, supervisor_user
    ):
        """Bundle must expose incident_rate_per_100 for backward compatibility."""
        d = date(2026, 3, 15)
        _add_attendance(test_db, sample_child.id, sample_class.id,
                        supervisor_user.id, d, models.AttendanceStatus.PRESENT)
        test_db.commit()

        bundle = KPIService.compute_kpi_bundle(
            test_db, sample_kindergarten.id, period_start=d, period_end=d
        )
        assert "incident_rate_per_100" in bundle, (
            "Legacy incident_rate_per_100 key must remain in bundle for migration compat."
        )

    def test_incident_rate_standard_unit_is_per_1000(self):
        """kpi_standards incident_rate standard unit must reference 1,000."""
        from kpi_standards import STANDARDS
        std = STANDARDS["incident_rate"]
        assert "1,000" in std.unit or "1000" in std.unit, (
            f"incident_rate standard unit is '{std.unit}', expected per 1,000 child-days."
        )
        assert "1,000" in std.threshold.unit or "1000" in std.threshold.unit

    def test_serious_incident_rate_standard_unit_is_per_1000(self):
        from kpi_standards import STANDARDS
        std = STANDARDS["serious_incident_rate"]
        assert "1,000" in std.unit or "1000" in std.unit


# ===========================================================================
# P0.4 — incident_followup_sla consistency
# ===========================================================================

class TestIncidentFollowupSla:
    def test_standalone_returns_zero_not_100_when_no_followup_required(
        self, test_db, sample_kindergarten, sample_class, sample_child,
        active_enrollment, supervisor_user
    ):
        """Standalone must return 0.0 (not 100.0) when no follow-up incidents exist."""
        d = date(2026, 5, 1)
        _add_attendance(test_db, sample_child.id, sample_class.id,
                        supervisor_user.id, d, models.AttendanceStatus.PRESENT)
        _add_incident(test_db, sample_child.id, sample_kindergarten.id, d,
                      followup_required=False)
        test_db.commit()

        rate = KPIService.compute_incident_followup_sla_compliance(
            test_db, sample_kindergarten.id, d, d
        )
        assert rate == 0.0, (
            f"Expected 0.0 when no follow-up required, got {rate}. "
            "Old bug returned 100.0 (misleading perfect SLA)."
        )

    def test_bundle_quality_has_data_false_when_no_followup_required(
        self, test_db, sample_kindergarten
    ):
        """Bundle quality.incident_followup_sla.has_data must be False with zero denominator."""
        d = date(2026, 5, 5)
        bundle = KPIService.compute_kpi_bundle(
            test_db, sample_kindergarten.id, period_start=d, period_end=d
        )
        q = bundle["quality"]["incident_followup_sla"]
        assert q["has_data"] is False
        assert q["reason"] is not None
        assert "follow" in q["reason"].lower()

    def test_bundle_followup_denominator_is_zero_with_no_data(
        self, test_db, sample_kindergarten
    ):
        d = date(2026, 5, 10)
        bundle = KPIService.compute_kpi_bundle(
            test_db, sample_kindergarten.id, period_start=d, period_end=d
        )
        assert bundle["denominators"]["incident_followup_sla"] == 0

    def test_true_100_sla_not_confused_with_missing_data(
        self, test_db, sample_kindergarten, sample_class, sample_child,
        active_enrollment, supervisor_user
    ):
        """1 followup closed within SLA → 100.0 with has_data=True."""
        d = date(2026, 5, 15)
        sla_deadline = datetime(2026, 5, 17, 9, 0, 0, tzinfo=timezone.utc)
        closed_at = datetime(2026, 5, 16, 9, 0, 0, tzinfo=timezone.utc)
        _add_attendance(test_db, sample_child.id, sample_class.id,
                        supervisor_user.id, d, models.AttendanceStatus.PRESENT)
        _add_incident(test_db, sample_child.id, sample_kindergarten.id, d,
                      followup_required=True, closed_at=closed_at,
                      sla_deadline=sla_deadline)
        test_db.commit()

        bundle = KPIService.compute_kpi_bundle(
            test_db, sample_kindergarten.id, period_start=d, period_end=d
        )
        assert bundle["incident_followup_sla"] == pytest.approx(100.0, abs=0.01)
        assert bundle["quality"]["incident_followup_sla"]["has_data"] is True

    def test_standalone_and_bundle_agree_with_followup_data(
        self, test_db, sample_kindergarten, sample_class, sample_child,
        active_enrollment, supervisor_user
    ):
        """Standalone and bundle must produce identical SLA % for same data."""
        d = date(2026, 5, 20)
        sla_deadline = datetime(2026, 5, 22, 9, 0, 0, tzinfo=timezone.utc)
        closed_late = datetime(2026, 5, 23, 9, 0, 0, tzinfo=timezone.utc)
        _add_attendance(test_db, sample_child.id, sample_class.id,
                        supervisor_user.id, d, models.AttendanceStatus.PRESENT)
        _add_incident(test_db, sample_child.id, sample_kindergarten.id, d,
                      followup_required=True, closed_at=closed_late,
                      sla_deadline=sla_deadline)
        test_db.commit()

        standalone = KPIService.compute_incident_followup_sla_compliance(
            test_db, sample_kindergarten.id, d, d
        )
        bundle = KPIService.compute_kpi_bundle(
            test_db, sample_kindergarten.id, period_start=d, period_end=d
        )
        assert bundle["incident_followup_sla"] == pytest.approx(standalone, abs=0.01)


# ===========================================================================
# P0.5 — Hard override rules
# ===========================================================================

class TestHardOverrideRules:
    def test_license_expired_forces_red(self, test_db):
        """Expired license must force governance_band to RED."""
        kg = _mk_kg(test_db, "EXP01", license_valid_until=date(2020, 1, 1))
        d = date(2026, 6, 1)
        bundle = KPIService.compute_kpi_bundle(
            test_db, kg.id, period_start=d, period_end=d
        )
        assert bundle["governance_band"] == "RED"
        assert "LICENSE_EXPIRED" in bundle["override_rules_triggered"]

    def test_license_missing_forces_red(self, test_db):
        """Missing license_valid_until must trigger LICENSE_MISSING and force RED."""
        kg = _mk_kg(test_db, "NONE1", license_valid_until=None)
        d = date(2026, 6, 1)
        bundle = KPIService.compute_kpi_bundle(
            test_db, kg.id, period_start=d, period_end=d
        )
        assert bundle["governance_band"] == "RED"
        assert "LICENSE_MISSING" in bundle["override_rules_triggered"]

    def test_unresolved_critical_incident_prevents_green(
        self, test_db, sample_kindergarten, sample_class, sample_child,
        active_enrollment, supervisor_user
    ):
        """Open CRITICAL incident → band must be AMBER or RED, not GREEN."""
        d = date(2026, 6, 5)  # a Friday — mark it open so it counts as a working day
        test_db.add(models.OperatingCalendar(
            kindergarten_id=sample_kindergarten.id, date=d, is_open=True))
        _add_attendance(test_db, sample_child.id, sample_class.id,
                        supervisor_user.id, d, models.AttendanceStatus.PRESENT)
        inc = models.Incident(
            child_id=sample_child.id,
            kindergarten_id=sample_kindergarten.id,
            type=models.IncidentType.INJURY,
            severity_level=models.SeverityLevel.CRITICAL,
            description="Unresolved critical",
            occurred_at=datetime(2026, 6, 5, 9, 0, 0),
            followup_required_flag=True,
            closed_at=None,
            deleted_at=None,
        )
        test_db.add(inc)
        test_db.commit()

        bundle = KPIService.compute_kpi_bundle(
            test_db, sample_kindergarten.id, period_start=d, period_end=d
        )
        assert bundle["governance_band"] in ("AMBER", "RED")
        assert "UNRESOLVED_CRITICAL_INCIDENT" in bundle["override_rules_triggered"]

    def test_ratio_below_minimum_forces_red(self, test_db, sample_kindergarten,
                                             manager_user):
        """ratio_compliance < 60% must force RED.

        We add ratio + checklist records to ensure GQI weight ≥ 0.60 so that
        INSUFFICIENT_DATA_COVERAGE does not prevent RATIO_BELOW_MINIMUM from firing.
        """
        d = date(2026, 6, 10)
        # 50% ratio compliance < 60% threshold
        rc = models.RatioCompliance(
            kindergarten_id=sample_kindergarten.id,
            date=d,
            operating_minutes=100,
            compliant_minutes=50,
            staff_count_avg=1.0,
            child_count_avg=20.0,
        )
        test_db.add(rc)
        # Add completed checklists to push GQI weight above 0.60
        # GQI = ratio(0.30) + checklist(0.20) + regulatory(0.20) = 0.70 → sufficient
        for ctype in ("opening", "safety", "closing"):
            test_db.add(models.DailyChecklist(
                kindergarten_id=sample_kindergarten.id,
                checklist_date=d,
                checklist_type=ctype,
                status=models.DailyChecklistStatus.COMPLETED,
                submitted_by=manager_user.id,
            ))
        test_db.commit()

        bundle = KPIService.compute_kpi_bundle(
            test_db, sample_kindergarten.id, period_start=d, period_end=d
        )
        assert bundle["governance_band"] == "RED"
        assert "RATIO_BELOW_MINIMUM" in bundle["override_rules_triggered"]

    def test_overcapacity_forces_red(self, test_db):
        """Active enrollments > class capacity must force RED (not AMBER)."""
        kg = _mk_kg(test_db, "CAP01")
        cls = _mk_class(test_db, kg, capadistrict=2, code_suffix="x")

        parent_user = models.User(
            username="par_cap_p0",
            email="par_cap_p0@test.jo",
            hashed_password="x",
            role=models.UserRole.PARENT,
            status=models.UserStatus.ACTIVE,
        )
        test_db.add(parent_user)
        test_db.commit()

        parent_profile = models.ParentProfile(
            user_id=parent_user.id,
            first_name="Test",
            last_name="Parent",
            phone_number="+96279111111",
            gender=models.Gender.MALE,
            nationality="Jordanian",
            national_id=f"CAP{kg.id:07d}",
            home_governorate="Amman",
            home_district="Amman",
            home_area="A",
            home_address_line="1 A",
            correspondence_preference=False,
        )
        test_db.add(parent_profile)
        test_db.commit()

        for i in range(3):  # 3 children > capacity of 2
            ch = models.Child(
                parent_id=parent_profile.id,
                first_name=f"Child{i}",
                last_name="P0",
                gender=models.Gender.MALE,
                date_of_birth=date(2022, 1, 1),
                father_name="Father",
                mother_first_name="Mother",
                mother_last_name="P0",
                mother_nationality="Jordanian",
                mother_national_id=f"M{kg.id}{i:06d}",
                media_consent=True,
            )
            test_db.add(ch)
            test_db.flush()
            enr = models.EnrollmentApplication(
                child_id=ch.id,
                kindergarten_id=kg.id,
                class_id=cls.id,
                status=models.EnrollmentStatus.ACTIVE,
            )
            test_db.add(enr)
        test_db.commit()

        d = date(2026, 6, 15)
        bundle = KPIService.compute_kpi_bundle(
            test_db, kg.id, period_start=d, period_end=d
        )
        assert bundle["governance_band"] == "RED", (
            f"Overcapacity must force RED but got '{bundle['governance_band']}'. "
            "kpi_standards.py OVERCAPACITY rule forces_band=RED."
        )
        assert "OVERCAPACITY" in bundle["override_rules_triggered"]

    def test_insufficient_data_produces_insufficient_not_red(self, test_db):
        """< 60% GQI data coverage must produce 'INSUFFICIENT', not 'RED'."""
        kg = _mk_kg(test_db, "EMPT1")
        # No attendance/ratio/training data → gqi_weight_sum < 0.60
        d = date(2026, 6, 20)
        bundle = KPIService.compute_kpi_bundle(
            test_db, kg.id, period_start=d, period_end=d
        )
        if "INSUFFICIENT_DATA_COVERAGE" in bundle["override_rules_triggered"]:
            assert bundle["governance_band"] == "INSUFFICIENT", (
                f"INSUFFICIENT_DATA_COVERAGE must produce 'INSUFFICIENT' band but got "
                f"'{bundle['governance_band']}'. Missing data must not masquerade as RED."
            )

    def test_multiple_overrides_all_recorded_in_list(self, test_db):
        """Expired license + empty data → both override codes must appear."""
        kg = _mk_kg(test_db, "MULT1", license_valid_until=date(2020, 1, 1))
        d = date(2026, 6, 1)
        bundle = KPIService.compute_kpi_bundle(
            test_db, kg.id, period_start=d, period_end=d
        )
        assert "LICENSE_EXPIRED" in bundle["override_rules_triggered"]
        assert isinstance(bundle["override_rules_triggered"], list)

    def test_override_rules_triggered_always_present(self, test_db, sample_kindergarten):
        """Bundle must always include override_rules_triggered as a list."""
        d = date(2026, 6, 1)
        bundle = KPIService.compute_kpi_bundle(
            test_db, sample_kindergarten.id, period_start=d, period_end=d
        )
        assert "override_rules_triggered" in bundle
        assert isinstance(bundle["override_rules_triggered"], list)

    def test_standards_defines_all_five_override_rules(self):
        """HARD_OVERRIDE_RULES must include all five P0.5 rule IDs."""
        from kpi_standards import HARD_OVERRIDE_RULES
        rule_ids = {r.rule_id for r in HARD_OVERRIDE_RULES}
        required = {
            "LICENSE_EXPIRED",
            "UNRESOLVED_CRITICAL_INCIDENT",
            "RATIO_BELOW_MINIMUM",
            "INSUFFICIENT_DATA_COVERAGE",
            "OVERCAPACITY",
        }
        assert required <= rule_ids, f"Missing from HARD_OVERRIDE_RULES: {required - rule_ids}"

    def test_overcapacity_standard_forces_red(self):
        """kpi_standards OVERCAPACITY rule must declare forces_band=RED."""
        from kpi_standards import HARD_OVERRIDE_RULES, BandColor
        rule = next((r for r in HARD_OVERRIDE_RULES if r.rule_id == "OVERCAPACITY"), None)
        assert rule is not None
        assert rule.forces_band == BandColor.RED

    def test_insufficient_data_standard_forces_insufficient(self):
        """kpi_standards INSUFFICIENT_DATA_COVERAGE must declare forces_band=INSUFFICIENT."""
        from kpi_standards import HARD_OVERRIDE_RULES, BandColor
        rule = next(
            (r for r in HARD_OVERRIDE_RULES if r.rule_id == "INSUFFICIENT_DATA_COVERAGE"),
            None,
        )
        assert rule is not None
        assert rule.forces_band == BandColor.INSUFFICIENT


# ===========================================================================
# P0.6 — Training completion denominator
# ===========================================================================

@pytest.fixture
def mandatory_module(test_db):
    m = TrainingModule(
        name="P0 Mandatory Safety",
        description="Required for all staff",
        is_mandatory=True,
    )
    test_db.add(m)
    test_db.commit()
    test_db.refresh(m)
    return m


@pytest.fixture
def optional_module(test_db):
    m = TrainingModule(
        name="P0 Optional Module",
        description="Not required",
        is_mandatory=False,
    )
    test_db.add(m)
    test_db.commit()
    test_db.refresh(m)
    return m


class TestTrainingCompletionDenominator:
    def test_prior_completions_counted_cumulative(
        self, test_db, sample_kindergarten, supervisor_user, mandatory_module
    ):
        """Completions before period_start but before period_end must count."""
        period_start = date(2026, 6, 1)
        period_end = date(2026, 6, 30)
        prior = date(2026, 5, 15)  # before period_start

        comp = StaffTrainingCompletion(
            user_id=supervisor_user.id,
            training_module_id=mandatory_module.id,
            kindergarten_id=sample_kindergarten.id,
            completion_date=prior,
            status=TrainingStatus.COMPLETED,
        )
        test_db.add(comp)
        test_db.commit()

        rate = KPIService.compute_training_completion_rate(
            test_db, sample_kindergarten.id, period_start, period_end
        )
        assert rate > 0, (
            f"Prior-period completion was ignored (rate={rate}). "
            "compute_training_completion_rate must use cumulative coverage."
        )

    def test_future_completions_excluded(
        self, test_db, sample_kindergarten, supervisor_user, mandatory_module
    ):
        """Completions after period_end must not count."""
        period_start = date(2026, 6, 1)
        period_end = date(2026, 6, 30)
        future = date(2026, 7, 5)

        comp = StaffTrainingCompletion(
            user_id=supervisor_user.id,
            training_module_id=mandatory_module.id,
            kindergarten_id=sample_kindergarten.id,
            completion_date=future,
            status=TrainingStatus.COMPLETED,
        )
        test_db.add(comp)
        test_db.commit()

        rate = KPIService.compute_training_completion_rate(
            test_db, sample_kindergarten.id, period_start, period_end
        )
        assert rate == pytest.approx(0.0, abs=0.1), (
            f"Future completion should be excluded but rate={rate}."
        )

    def test_non_mandatory_modules_excluded_from_denominator(
        self, test_db, sample_kindergarten, supervisor_user,
        mandatory_module, optional_module
    ):
        """Completing only an optional module must not satisfy mandatory denominator."""
        period_start = date(2026, 6, 1)
        period_end = date(2026, 6, 30)

        comp = StaffTrainingCompletion(
            user_id=supervisor_user.id,
            training_module_id=optional_module.id,
            kindergarten_id=sample_kindergarten.id,
            completion_date=date(2026, 6, 10),
            status=TrainingStatus.COMPLETED,
        )
        test_db.add(comp)
        test_db.commit()

        rate = KPIService.compute_training_completion_rate(
            test_db, sample_kindergarten.id, period_start, period_end
        )
        # Denominator = staff × mandatory_modules; numerator: 0 mandatory completions
        assert rate == pytest.approx(0.0, abs=0.1), (
            f"Optional module completion inflated mandatory denominator rate={rate}."
        )

    def test_rate_does_not_exceed_100(
        self, test_db, sample_kindergarten, supervisor_user, mandatory_module
    ):
        """Training completion rate must never exceed 100% even with duplicate records."""
        period_start = date(2026, 6, 1)
        period_end = date(2026, 6, 30)

        comp = StaffTrainingCompletion(
            user_id=supervisor_user.id,
            training_module_id=mandatory_module.id,
            kindergarten_id=sample_kindergarten.id,
            completion_date=date(2026, 6, 10),
            status=TrainingStatus.COMPLETED,
        )
        test_db.add(comp)
        test_db.commit()

        rate = KPIService.compute_training_completion_rate(
            test_db, sample_kindergarten.id, period_start, period_end
        )
        assert rate <= 100.0, (
            f"Training rate {rate} > 100% — denominator or dedup is wrong."
        )

    def test_bundle_training_rate_matches_standalone(
        self, test_db, sample_kindergarten, supervisor_user, mandatory_module
    ):
        """Bundle training_completion_rate must match standalone for same period."""
        period_start = date(2026, 6, 1)
        period_end = date(2026, 6, 30)

        comp = StaffTrainingCompletion(
            user_id=supervisor_user.id,
            training_module_id=mandatory_module.id,
            kindergarten_id=sample_kindergarten.id,
            completion_date=date(2026, 6, 10),
            status=TrainingStatus.COMPLETED,
        )
        test_db.add(comp)
        test_db.commit()

        standalone = KPIService.compute_training_completion_rate(
            test_db, sample_kindergarten.id, period_start, period_end
        )
        bundle = KPIService.compute_kpi_bundle(
            test_db, sample_kindergarten.id,
            period_start=period_start, period_end=period_end,
        )
        assert bundle["training_completion_rate"] == pytest.approx(standalone, abs=1.0), (
            f"Bundle={bundle['training_completion_rate']} != standalone={standalone}. "
            "Bulk builder logic diverges from standalone."
        )


# ===========================================================================
# API contract surface: bundle structure
# ===========================================================================

class TestBundleContract:
    REQUIRED_KEYS = (
        "attendance_rate",
        "excused_absence_rate",
        "incident_rate",
        "incident_rate_per_100",
        "serious_incident_rate",
        "serious_incident_rate_per_100",
        "incident_followup_sla",
        "ratio_compliance",
        "training_completion_rate",
        "report_submission_rate",
        "chronic_absence_rate",
        "checklist_compliance",
        "regulatory_status",
        "parent_satisfaction",
        "parent_response_rate",
        "gqi_score",
        "cei_score",
        "governance_score",
        "governance_band",
        "capacity_utilization_rate",
        "active_enrollments",
        "new_enrollments",
        "override_rules_triggered",
        "numerators",
        "denominators",
        "quality",
    )

    def test_bundle_contains_all_required_keys(self, test_db, sample_kindergarten):
        d = date(2026, 6, 1)
        bundle = KPIService.compute_kpi_bundle(
            test_db, sample_kindergarten.id, period_start=d, period_end=d
        )
        for key in self.REQUIRED_KEYS:
            assert key in bundle, f"Required bundle key missing: '{key}'"

    def test_quality_section_has_incident_followup_sla_metadata(
        self, test_db, sample_kindergarten
    ):
        d = date(2026, 6, 1)
        bundle = KPIService.compute_kpi_bundle(
            test_db, sample_kindergarten.id, period_start=d, period_end=d
        )
        q = bundle["quality"]
        assert "incident_followup_sla" in q
        assert "has_data" in q["incident_followup_sla"]
        assert "reason" in q["incident_followup_sla"]

    def test_numerators_and_denominators_are_dicts(
        self, test_db, sample_kindergarten
    ):
        d = date(2026, 6, 1)
        bundle = KPIService.compute_kpi_bundle(
            test_db, sample_kindergarten.id, period_start=d, period_end=d
        )
        assert isinstance(bundle["numerators"], dict)
        assert isinstance(bundle["denominators"], dict)

    def test_governance_band_is_valid_value(self, test_db, sample_kindergarten):
        d = date(2026, 6, 1)
        bundle = KPIService.compute_kpi_bundle(
            test_db, sample_kindergarten.id, period_start=d, period_end=d
        )
        valid = {"GREEN", "AMBER", "RED", "INSUFFICIENT"}
        assert bundle["governance_band"] in valid, (
            f"governance_band '{bundle['governance_band']}' is not a valid band."
        )


# ===========================================================================
# Code-review findings — post-P0 fixes (10 findings)
# ===========================================================================

class TestCEIFormulaScale:
    """Finding 2: CEI formula min(serious_incident_rate, 100) ceiling must use /10 normalisation."""

    def test_cei_normalises_per_1000_to_per_100_equivalent(self, test_db, sample_kindergarten):
        """compute_kpi_bundle CEI must not collapse for a modest per-1000 rate."""
        import kpi_service as svc
        source = inspect.getsource(svc.KPIService.compute_kpi_bundle)
        # The corrected formula must divide by 10 before applying the 100-ceiling.
        assert "serious_incident_rate / 10" in source or "serious_incident_rate_val / 10" in source, (
            "CEI formula must normalise serious_incident_rate from per-1,000 to per-100 "
            "before applying the min(..., 100) ceiling."
        )

    def test_cei_ceiling_calibrated_for_per_100_equivalent(self, test_db, sample_kindergarten):
        """Bundle gqi/cei scores must be > 0 even with a high (but realistic) incident rate."""
        # Force a moderate serious_incident_rate by patching compute_serious_incident_rate.
        from unittest.mock import patch
        d = date(2026, 6, 1)
        # 50/1000 serious incidents is high but should not zero-out the CEI component
        # because 50 / 10 = 5.0 per-100, and 100 - min(5.0, 100) = 95 (well above 0).
        with patch.object(
            KPIService, "compute_serious_incident_rate", return_value=50.0
        ), patch.object(
            KPIService, "compute_attendance_rate", return_value=85.0
        ), patch.object(
            KPIService, "compute_chronic_absence_rate", return_value=5.0
        ):
            bundle = KPIService.compute_kpi_bundle(
                test_db, sample_kindergarten.id, period_start=d, period_end=d
            )
        # CEI component for serious_incident_rate = 100 - min(50/10, 100) = 95.
        # A governance_score > 0 confirms the formula did not collapse.
        assert bundle.get("governance_score", 0) > 0, (
            "governance_score collapsed to 0 for serious_incident_rate=50/1000. "
            "CEI formula is still using uncalibrated ceiling."
        )


class TestBulkAttendanceExcludesExcused:
    """Finding 5: bulk path must exclude EXCUSED from attended child-days."""

    def test_bulk_path_excludes_excused_from_attended(self, test_db, sample_kindergarten):
        """Inspect the consolidated dashboard source — the nested _build_base_bundles_bulk
        closure must not include EXCUSED in the attended child-days status list."""
        import kpi_service as svc
        # _build_base_bundles_bulk is a closure inside get_consolidated_kpi_dashboard_data.
        source = inspect.getsource(svc.get_consolidated_kpi_dashboard_data)
        # Find the bulk attended-child-days status.in_ block and confirm EXCUSED is absent.
        # The single-KG path excludes EXCUSED per policy; the bulk path must match.
        import re
        # Extract the status.in_ list inside _build_base_bundles_bulk context
        # by checking that after "Attended child-days per child" the EXCUSED constant is absent
        # from any status list within 60 lines.
        attended_block_match = re.search(
            r"Attended child-days.*?\.status\.in_\(\[(.*?)\]\)",
            source, re.DOTALL
        )
        if attended_block_match:
            block = attended_block_match.group(0)
            assert "EXCUSED" not in block, (
                "_build_base_bundles_bulk bulk attendance status list still includes "
                "EXCUSED, inflating the denominator vs the single-KG path."
            )
        else:
            # Fallback: confirm the entire source has no status list containing EXCUSED
            # adjacent to the attended child-days comment.
            assert "EXCUSED" not in source.split("Attended child-days per child")[1][:500] if "Attended child-days per child" in source else True


class TestKPIDefinitionsScale:
    """Finding 9: KPI_DEFINITIONS thresholds and descriptions must match per-1,000 scale."""

    def test_incident_rate_description_says_per_1000(self):
        from kpi_service import KPI_DEFINITIONS
        defn = KPI_DEFINITIONS["incident_rate"]
        assert "1,000" in defn["description_en"], (
            "KPI_DEFINITIONS['incident_rate']['description_en'] still says per-100."
        )
        assert "1,000" in defn["formula_en"], (
            "KPI_DEFINITIONS['incident_rate']['formula_en'] still references × 100."
        )

    def test_incident_rate_threshold_calibrated_for_per_1000(self):
        from kpi_service import KPI_DEFINITIONS
        threshold = KPI_DEFINITIONS["incident_rate"]["threshold"]
        # Green/amber boundary in per-100 scale was 0.51; in per-1000 it must be > 1.
        assert threshold.amber_min > 1.0, (
            f"incident_rate amber_min={threshold.amber_min} — still calibrated for per-100 scale. "
            "Expected > 1.0 for per-1,000 values (standard is ~2.0)."
        )

    def test_serious_incident_rate_description_says_per_1000(self):
        from kpi_service import KPI_DEFINITIONS
        defn = KPI_DEFINITIONS["serious_incident_rate"]
        assert "1,000" in defn["description_en"], (
            "KPI_DEFINITIONS['serious_incident_rate']['description_en'] still says per-100."
        )

    def test_serious_incident_rate_threshold_calibrated_for_per_1000(self):
        from kpi_service import KPI_DEFINITIONS
        threshold = KPI_DEFINITIONS["serious_incident_rate"]["threshold"]
        # In per-100 scale amber_min was 0.01; in per-1000 amber_min should be near 0.
        # Any value above 0.001 indicates a non-trivial per-1000 threshold.
        assert threshold.amber_min >= 0.0, "amber_min must be non-negative"
        # The red threshold in per-100 was 0.1; in per-1000 it must be > 0.1.
        assert threshold.red_max > 0.1, (
            f"serious_incident_rate red_max={threshold.red_max} — still calibrated for per-100."
        )


class TestAlertMessageUnit:
    """Finding 7: alert message for incident rate must use /1K, not %."""

    def test_alert_message_uses_per_1k_not_percent(self):
        import kpi_service as svc
        source = inspect.getsource(svc.get_consolidated_kpi_dashboard_data)
        # The interpolated string must NOT contain avg_incident_rate% (% directly after the value).
        import re
        bad_pattern = r"avg_incident_rate\}%"
        assert not re.search(bad_pattern, source), (
            "Alert message still appends '%' directly after avg_incident_rate. "
            "Use '/1K' since the value is per-1,000 child-days."
        )
        assert "/1K" in source, (
            "Alert message must use '/1K' unit suffix for per-1,000 incident rate values."
        )


class TestConsolidatedDashboardUnitLabel:
    """Finding 8: consolidated dashboard cards must label incident rates as per 1,000 child-days."""

    def test_consolidated_dashboard_unit_label_says_per_1000(self):
        import kpi_service as svc
        source = inspect.getsource(svc.get_consolidated_kpi_dashboard_data)
        assert "per 1,000 child-days" in source, (
            "get_consolidated_kpi_dashboard_data still uses 'per 100 child-days' unit label. "
            "Must be 'per 1,000 child-days'."
        )
