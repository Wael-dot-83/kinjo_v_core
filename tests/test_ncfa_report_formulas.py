"""Unit tests for NCFA/agency report formula correctness.

These pin the production-grade behaviour of the shared indicator formulas that
the NCFA strong-alignment hub relies on:

* occupancy must read as "unavailable" (None), never a misleading 0%, when no
  class capacity is recorded;
* reporting participation must use exactly seven inclusive dates ending on the
  report end date (end-6 .. end), not an eight-day or "now"-anchored window.
"""
from datetime import date, timedelta

import models
from agency_reports_service import AgencyReportsService
from kpi_service import KPIService


def _active_kg(db, name: str):
    kg = models.Kindergarten(
        name_ar=name,
        name_en=name,
        license_number=f"LIC-{name}",
        governorate="Amman",
        district="Amman",
        area="Abdoun",
        address_line="123 Main Street",
        contact_phone="+962791234567",
        status=models.KindergartenStatus.ACTIVE,
        license_valid_until=date(2027, 12, 31),
    )
    db.add(kg)
    db.commit()
    db.refresh(kg)
    return kg


def _daily_report(db, kg_id: int, report_date: date, child_id: int):
    db.add(models.DailyReport(
        child_id=child_id,
        kindergarten_id=kg_id,
        date=report_date,
        submitted_by=1,
        arrival_time="08:00",
        status=models.DailyReportStatus.APPROVED,
    ))
    db.commit()


def test_occupancy_is_unavailable_without_capacity(test_db):
    """No recorded class capacity -> occupancy value is None (unavailable),
    with an explanatory note — not 0%."""
    _active_kg(test_db, "no-capacity")
    svc = AgencyReportsService(test_db)
    end = date(2026, 6, 15)
    result = svc._ind_occupancy_rate(None, end - timedelta(days=90), end)
    assert result["kpi"]["code"] == "occupancy_rate"
    assert result["kpi"]["value"] is None
    assert result["note"]


def test_reporting_participation_uses_exact_seven_day_window(test_db, sample_child):
    """Window is end-6 .. end inclusive (exactly 7 dates). A report on end-6 is
    counted; a report on end-7 is not."""
    end = date(2026, 6, 15)
    kg_in_end = _active_kg(test_db, "reported-on-end")
    kg_in_boundary = _active_kg(test_db, "reported-on-day7")
    kg_out = _active_kg(test_db, "reported-just-outside")
    _active_kg(test_db, "silent")  # active, never reported

    cid = sample_child.id
    _daily_report(test_db, kg_in_end.id, end, cid)                      # in window
    _daily_report(test_db, kg_in_boundary.id, end - timedelta(days=6), cid)  # boundary in
    _daily_report(test_db, kg_out.id, end - timedelta(days=7), cid)     # just outside

    svc = AgencyReportsService(test_db)
    result = svc._ind_data_quality_score(None, end - timedelta(days=90), end)

    row = result["rows"][0]
    assert row["النشطة"] == 4          # four active nurseries in scope
    assert row["المُبلِّغة"] == 2       # only the end and end-6 reporters count
    assert result["kpi"]["value"] == 50.0


def test_small_cell_suppression_blanks_small_counts(test_db, monkeypatch):
    """Category counts below the disclosure threshold are suppressed: chart
    points become a gap (None, never 0), table cells show "محجوب", and the count
    is reported in metadata. Values at/above the threshold are untouched."""
    monkeypatch.setenv("AGENCY_REPORT_MIN_CELL_SIZE", "5")
    svc = AgencyReportsService(test_db)
    charts = [{"type": "bar", "series": [
        {"label": "CRITICAL", "value": 2},
        {"label": "LOW", "value": 9},
    ]}]
    table = [
        {"المؤشر": "x", "الفئة": "CRITICAL", "القيمة": 2},
        {"المؤشر": "x", "الفئة": "LOW", "القيمة": 9},
    ]
    suppressed = svc._apply_small_cell_suppression(charts, table)

    assert suppressed == 1
    assert charts[0]["series"][0]["value"] is None      # gap, not zero
    assert charts[0]["series"][0]["suppressed"] is True
    assert charts[0]["series"][1]["value"] == 9          # above threshold, kept
    assert table[0]["القيمة"] == "محجوب"
    assert table[1]["القيمة"] == 9


def _active_enrollment(db, kg_id, child_id, e_start, e_end):
    db.add(models.EnrollmentApplication(
        child_id=child_id,
        kindergarten_id=kg_id,
        status=models.EnrollmentStatus.ACTIVE,
        enrollment_start_date=e_start,
        enrollment_end_date=e_end,
    ))
    db.commit()


def test_expected_child_days_matches_kpi_service(test_db, sample_child):
    """The batched aggregate expected-child-days must equal kpi_service's
    authoritative per-kindergarten computation (single source of truth)."""
    kg = _active_kg(test_db, "expected-eq")
    start, end = date(2026, 6, 1), date(2026, 6, 30)
    _active_enrollment(test_db, kg.id, sample_child.id, start - timedelta(days=10), None)

    agency_total, _ = AgencyReportsService(test_db)._expected_child_days([kg.id], start, end)
    kpi_total, _, _ = KPIService._count_expected_child_days(test_db, kg.id, start, end)

    assert agency_total == kpi_total
    assert agency_total > 0  # Sun-Thu working days in June 2026


def test_attendance_rate_denominator_is_expected_not_rows(test_db, sample_child):
    """With an active enrolment but no attendance recorded, the rate is 0%
    (missing records lower the rate) rather than being undefined or based on
    the number of existing attendance rows."""
    kg = _active_kg(test_db, "attend-expected")
    start, end = date(2026, 6, 1), date(2026, 6, 30)
    _active_enrollment(test_db, kg.id, sample_child.id, start, None)

    result = AgencyReportsService(test_db)._ind_attendance_rate(None, start, end)
    assert result["kpi"]["value"] == 0.0
    assert result["rows"][0]["أيام الحضور المتوقعة"] > 0
    assert result["rows"][0]["أيام حضور فعلية"] == 0


def test_attendance_rate_unavailable_without_active_enrollment(test_db):
    """No active enrolment -> no expected child-days -> unavailable (None),
    not a misleading 0%."""
    _active_kg(test_db, "attend-empty")
    start, end = date(2026, 6, 1), date(2026, 6, 30)
    result = AgencyReportsService(test_db)._ind_attendance_rate(None, start, end)
    assert result["kpi"]["value"] is None
    assert result["note"]
