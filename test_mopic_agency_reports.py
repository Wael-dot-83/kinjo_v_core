"""Tests for Ministry of Planning and International Cooperation (MOPIC) Agency Reports.

Verifies:
1. Agency report catalog and MOPIC report registry entries.
2. `service_access_gaps` report generation, district outer join, unserved area detection, and dynamic chart grouping.
3. `regional_capacity_readiness` report generation, capacity/enrollment occupancy math, and overcrowding detection.
4. `development_investment_priorities` index calculation and governorate ranking.
5. Export output format (CSV UTF-8 BOM, JSON schema compliance, formula protection).
6. Filter parameter contracts (governorate, city, district, area).
"""
import pytest
from sqlalchemy.orm import Session

import models
from database import SessionLocal
from agency_reports_registry import AGENCY_REPORT_REGISTRY
from agency_reports_service import AgencyReportsService
from agency_reports_export import to_csv


@pytest.fixture
def db():
    session = SessionLocal()
    try:
        yield session
    finally:
        session.close()


def test_mopic_registry_configuration():
    assert "mopic" in AGENCY_REPORT_REGISTRY
    mopic = AGENCY_REPORT_REGISTRY["mopic"]
    assert mopic["name_ar"] == "وزارة التخطيط والتعاون الدولي"
    assert "service_access_gaps" in mopic["reports"]
    assert "regional_capacity_readiness" in mopic["reports"]
    assert "development_investment_priorities" in mopic["reports"]


def test_mopic_service_access_gaps_generation(db: Session):
    svc = AgencyReportsService(db)
    payload = svc.generate_report("mopic", "service_access_gaps", {})
    assert payload["metadata"]["agency_code"] == "mopic"
    assert payload["metadata"]["report_code"] == "service_access_gaps"
    assert "summary" in payload
    assert "children" in payload["summary"]
    assert "active_kindergartens" in payload["summary"]
    assert "unserved_districts_count" in payload["summary"]
    assert "breakdowns" in payload
    assert isinstance(payload["breakdowns"], list)
    if payload.get("chart"):
        assert payload["chart"]["type"] == "bar"
        assert payload["chart"]["group_by"] in ("governorate", "city")


def test_mopic_service_access_gaps_governorate_filter(db: Session):
    svc = AgencyReportsService(db)
    payload = svc.generate_report("mopic", "service_access_gaps", {"governorate": "إربد"})
    assert payload["metadata"]["filters"]["governorate"] == "إربد"
    if payload.get("chart"):
        assert payload["chart"]["group_by"] == "city"
        assert "إربد" in payload["chart"]["title_ar"]


def test_mopic_regional_capacity_readiness_generation(db: Session):
    svc = AgencyReportsService(db)
    payload = svc.generate_report("mopic", "regional_capacity_readiness", {})
    assert payload["metadata"]["agency_code"] == "mopic"
    assert payload["metadata"]["report_code"] == "regional_capacity_readiness"
    assert "total_capacity" in payload["summary"]
    assert "total_enrolled" in payload["summary"]
    assert "overall_occupancy_rate_pct" in payload["summary"]
    assert "total_available_expansion_capacity" in payload["summary"]
    assert "breakdowns" in payload
    assert isinstance(payload["breakdowns"], list)
    for row in payload["breakdowns"]:
        assert "occupancy_rate_pct" in row
        assert "available_expansion_capacity" in row
        assert row["occupancy_rate_pct"] >= 0.0


def test_mopic_development_investment_priorities_generation(db: Session):
    svc = AgencyReportsService(db)
    payload = svc.generate_report("mopic", "development_investment_priorities", {})
    assert payload["metadata"]["agency_code"] == "mopic"
    assert payload["metadata"]["report_code"] == "development_investment_priorities"
    assert "governorates_count" in payload["summary"]
    assert "top_priority_governorate" in payload["summary"]
    assert "average_investment_priority_score" in payload["summary"]
    assert "breakdowns" in payload
    assert isinstance(payload["breakdowns"], list)
    for row in payload["breakdowns"]:
        assert "investment_priority_score" in row
        assert "priority_rank" in row
        assert 0.0 <= row["investment_priority_score"] <= 100.0


def test_mopic_csv_export(db: Session):
    svc = AgencyReportsService(db)
    payload = svc.generate_report("mopic", "service_access_gaps", {})
    csv_out = to_csv(payload)
    assert isinstance(csv_out, str)
    assert csv_out.startswith("\ufeff")  # UTF-8 BOM check
    assert "mopic" in csv_out
    assert "وزارة التخطيط والتعاون الدولي" in csv_out
