"""
Unit tests for KPI calculation formulas using known, seeded data.
Tests verify that KPIService methods produce mathematically correct results.
"""
import pytest
from datetime import date, datetime, timedelta
import models
from kpi_service import KPIService


PERIOD_START = date(2026, 5, 1)
PERIOD_END = date(2026, 5, 7)  # 7-day test window


class TestAttendanceRate:
    def test_perfect_attendance_is_100(
        self, test_db, sample_kindergarten, sample_child, sample_enrollment,
        supervisor_user
    ):
        # 1 child enrolled; seed 7 attendance logs for 7 days
        for i in range(7):
            d = PERIOD_START + timedelta(days=i)
            test_db.add(models.AttendanceLog(
                child_id=sample_child.id,
                class_id=sample_enrollment.class_id,
                date=d,
                status=models.AttendanceStatus.PRESENT,
                check_in_at=datetime(d.year, d.month, d.day, 8, 0),
                recorded_by=supervisor_user.id
            ))
        test_db.commit()

        rate = KPIService.compute_attendance_rate(
            test_db, sample_kindergarten.id, PERIOD_START, PERIOD_END
        )
        assert rate == 100.0

    def test_zero_attendance_is_zero(
        self, test_db, sample_kindergarten, sample_child, sample_enrollment
    ):
        rate = KPIService.compute_attendance_rate(
            test_db, sample_kindergarten.id, PERIOD_START, PERIOD_END
        )
        assert rate == 0.0

    def test_partial_attendance(
        self, test_db, sample_kindergarten, sample_child, sample_enrollment,
        supervisor_user
    ):
        # 1 child; 3 out of 7 days attended → 3/7 * 100 ≈ 42.86%
        for i in range(3):
            d = PERIOD_START + timedelta(days=i)
            test_db.add(models.AttendanceLog(
                child_id=sample_child.id,
                class_id=sample_enrollment.class_id,
                date=d,
                status=models.AttendanceStatus.PRESENT,
                check_in_at=datetime(d.year, d.month, d.day, 8, 0),
                recorded_by=supervisor_user.id
            ))
        test_db.commit()

        rate = KPIService.compute_attendance_rate(
            test_db, sample_kindergarten.id, PERIOD_START, PERIOD_END
        )
        expected = round(3 / 7 * 100, 2)
        assert rate == expected

    def test_no_enrollments_returns_zero(self, test_db, sample_kindergarten):
        rate = KPIService.compute_attendance_rate(
            test_db, sample_kindergarten.id, PERIOD_START, PERIOD_END
        )
        assert rate == 0.0


class TestIncidentRate:
    def test_no_incidents_no_attendance_returns_zero(
        self, test_db, sample_kindergarten
    ):
        rate = KPIService.compute_incident_rate(
            test_db, sample_kindergarten.id, PERIOD_START, PERIOD_END
        )
        assert rate == 0.0

    def test_incident_rate_formula(
        self, test_db, sample_kindergarten, sample_child, supervisor_user,
        sample_enrollment, sample_attendance
    ):
        # sample_attendance provides 1 log (May 1); add 2 more to make 3 total
        for d_offset in [3, 4]:  # May 4, May 5
            d = PERIOD_START + timedelta(days=d_offset)
            test_db.add(models.AttendanceLog(
                child_id=sample_child.id,
                class_id=sample_enrollment.class_id,
                date=d,
                status=models.AttendanceStatus.PRESENT,
                check_in_at=datetime(d.year, d.month, d.day, 8, 0),
                recorded_by=supervisor_user.id
            ))
        test_db.add(models.Incident(
            child_id=sample_child.id,
            kindergarten_id=sample_kindergarten.id,
            type=models.IncidentType.INJURY,
            severity_level=models.SeverityLevel.LOW,
            description="تعثّر",
            occurred_at=datetime(2026, 5, 1, 10, 0),
            followup_required_flag=False
        ))
        test_db.commit()

        rate = KPIService.compute_incident_rate(
            test_db, sample_kindergarten.id, PERIOD_START, PERIOD_END
        )
        # 3 attendance logs (May 1, 4, 5); 1 incident / 3 attended days * 100
        expected = round(1 / 3 * 100, 2)
        assert rate == expected


class TestSeriousIncidentRate:
    def test_low_incidents_not_counted_as_serious(
        self, test_db, sample_kindergarten, sample_child, supervisor_user,
        sample_enrollment, sample_attendance
    ):
        test_db.add(models.Incident(
            child_id=sample_child.id,
            kindergarten_id=sample_kindergarten.id,
            type=models.IncidentType.INJURY,
            severity_level=models.SeverityLevel.LOW,
            description="خدش بسيط",
            occurred_at=datetime(2026, 5, 1, 10, 0),
            followup_required_flag=False
        ))
        test_db.commit()

        rate = KPIService.compute_serious_incident_rate(
            test_db, sample_kindergarten.id, PERIOD_START, PERIOD_END
        )
        assert rate == 0.0

    def test_critical_incident_counted_as_serious(
        self, test_db, sample_kindergarten, sample_child, supervisor_user,
        sample_enrollment, sample_attendance
    ):
        test_db.add(models.Incident(
            child_id=sample_child.id,
            kindergarten_id=sample_kindergarten.id,
            type=models.IncidentType.INJURY,
            severity_level=models.SeverityLevel.CRITICAL,
            description="حادث خطير",
            occurred_at=datetime(2026, 5, 1, 10, 0),
            followup_required_flag=True
        ))
        test_db.commit()

        rate = KPIService.compute_serious_incident_rate(
            test_db, sample_kindergarten.id, PERIOD_START, PERIOD_END
        )
        assert rate > 0.0


class TestChronicAbsenceRate:
    def test_fully_absent_child_is_chronic(
        self, test_db, sample_kindergarten, sample_child, sample_enrollment
    ):
        # No attendance logs → 0% attendance, 100% absent → chronic
        rate = KPIService.compute_chronic_absence_rate(
            test_db, sample_kindergarten.id, PERIOD_START, PERIOD_END,
            threshold_percent=10.0
        )
        # 1 child, 0 attended, 100% absence ≥ 10% threshold → 100% chronic
        assert rate == 100.0

    def test_perfect_attendance_not_chronic(
        self, test_db, sample_kindergarten, sample_child, sample_enrollment,
        supervisor_user
    ):
        for i in range(7):
            d = PERIOD_START + timedelta(days=i)
            test_db.add(models.AttendanceLog(
                child_id=sample_child.id,
                class_id=sample_enrollment.class_id,
                date=d,
                status=models.AttendanceStatus.PRESENT,
                check_in_at=datetime(d.year, d.month, d.day, 8, 0),
                recorded_by=supervisor_user.id
            ))
        test_db.commit()

        rate = KPIService.compute_chronic_absence_rate(
            test_db, sample_kindergarten.id, PERIOD_START, PERIOD_END,
            threshold_percent=10.0
        )
        assert rate == 0.0


class TestRatioCompliance:
    def test_no_compliance_data_returns_zero(self, test_db, sample_kindergarten):
        rate = KPIService.compute_ratio_compliance(
            test_db, sample_kindergarten.id, PERIOD_START, PERIOD_END
        )
        assert rate == 0.0

    def test_full_compliance(self, test_db, sample_kindergarten):
        test_db.add(models.RatioCompliance(
            kindergarten_id=sample_kindergarten.id,
            date=PERIOD_START,
            operating_minutes=480,
            compliant_minutes=480,
            staff_count_avg=2.0,
            child_count_avg=15.0
        ))
        test_db.commit()

        rate = KPIService.compute_ratio_compliance(
            test_db, sample_kindergarten.id, PERIOD_START, PERIOD_END
        )
        assert rate == 100.0

    def test_partial_compliance(self, test_db, sample_kindergarten):
        test_db.add(models.RatioCompliance(
            kindergarten_id=sample_kindergarten.id,
            date=PERIOD_START,
            operating_minutes=480,
            compliant_minutes=240,
            staff_count_avg=1.0,
            child_count_avg=15.0
        ))
        test_db.commit()

        rate = KPIService.compute_ratio_compliance(
            test_db, sample_kindergarten.id, PERIOD_START, PERIOD_END
        )
        assert rate == 50.0


class TestFollowupSLACompliance:
    def test_no_followup_required_returns_100(self, test_db, sample_kindergarten):
        rate = KPIService.compute_incident_followup_sla_compliance(
            test_db, sample_kindergarten.id, PERIOD_START, PERIOD_END
        )
        assert rate == 100.0

    def test_all_closed_within_sla_returns_100(
        self, test_db, sample_kindergarten, sample_child, supervisor_user, sample_enrollment
    ):
        incident = models.Incident(
            child_id=sample_child.id,
            kindergarten_id=sample_kindergarten.id,
            type=models.IncidentType.INJURY,
            severity_level=models.SeverityLevel.LOW,
            description="test",
            occurred_at=datetime(2026, 5, 1, 10, 0),
            followup_required_flag=True,
            followup_sla_deadline=datetime(2026, 5, 3),
            closed_at=datetime(2026, 5, 2)  # closed before deadline
        )
        test_db.add(incident)
        test_db.commit()

        rate = KPIService.compute_incident_followup_sla_compliance(
            test_db, sample_kindergarten.id, PERIOD_START, PERIOD_END
        )
        assert rate == 100.0
