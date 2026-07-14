"""Tests for the DOS (Department of Statistics) agency reports."""
from pathlib import Path

import pytest
import models
from auth import get_password_hash
from agency_reports_service import AgencyReportsService


def _make_admin(db, username="dos_admin"):
    u = models.User(
        username=username, email=f"{username}@example.com",
        hashed_password=get_password_hash("Admin123!"),
        role=models.UserRole.ADMIN, status=models.UserStatus.ACTIVE,
    )
    db.add(u); db.commit(); db.refresh(u)
    return u


def _tok(client, username):
    r = client.post("/token", data={"username": username, "password": "Admin123!"})
    assert r.status_code == 200, r.text
    return {"Authorization": f"Bearer {r.json()['access_token']}"}


def test_dos_in_catalog():
    class _DummyDB:
        def query(self, *a, **k):
            class _Q:
                def scalar(self):
                    return 0
            return _Q()
            
    catalog = AgencyReportsService(_DummyDB()).catalog()
    dos_agency = next((a for a in catalog["agencies"] if a["code"] == "dos"), None)
    assert dos_agency is not None
    assert len(dos_agency["reports"]) == 10
    
    expected_reports = {
        "children_demographics",
        "enrollment_participation_0_60",
        "institutions_active_licensed",
        "capacity_occupancy_overcrowding",
        "monthly_attendance_absence",
        "supervisors_child_ratio",
        "incidents_safety_1000_child_days",
        "geographic_service_gaps",
        "data_quality_completeness",
        "annual_quarterly_trends"
    }
    
    actual_reports = {r["report_code"] for r in dos_agency["reports"]}
    assert actual_reports == expected_reports


def test_dos_report_execution(client, test_db):
    _make_admin(test_db, "dos_admin")
    
    # Setup some basic data
    kg = models.Kindergarten(
        name_ar="روضة تجريبية", governorate="عمان", district="ماركا",
        area="a", address_line="a", contact_phone="0790000000",
        status=models.KindergartenStatus.ACTIVE,
    )
    test_db.add(kg)
    test_db.commit()
    
    headers = _tok(client, "dos_admin")
    
    # Test one of the DOS reports
    r = client.get(
        "/api/admin/agency-reports/dos/reports/institutions_active_licensed",
        headers=headers,
    )
    assert r.status_code == 200, r.text
    payload = r.json()
    
    assert "summary" in payload
    assert "breakdowns" in payload
    assert "summary_labels" in payload
    assert "column_labels" in payload
    
    # DOS reports on early-childhood *institutions* (مؤسسات), which is a distinct
    # concept from the kindergarten registry's total_kindergartens (الحضانات).
    assert "total_institutions" in payload["summary"]
    assert "active_institutions" in payload["summary"]
    assert payload["summary"]["total_institutions"] == 1
    assert payload["summary"]["active_institutions"] == 1
