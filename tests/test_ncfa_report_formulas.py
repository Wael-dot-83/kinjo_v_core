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
