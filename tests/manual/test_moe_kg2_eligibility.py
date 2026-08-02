"""Tests for MOE KG2 Eligibility Report.
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


def test_moe_registry_configuration():
    assert "moe" in AGENCY_REPORT_REGISTRY
    moe = AGENCY_REPORT_REGISTRY["moe"]
    assert moe["name_ar"] == "وزارة التربية والتعليم"
    assert "kg2_eligibility" in moe["reports"]


def test_moe_kg2_eligibility_report_generation(db: Session):
    svc = AgencyReportsService(db)
    payload = svc.generate_report("moe", "kg2_eligibility", {})
    assert payload["metadata"]["agency_code"] == "moe"
    assert payload["metadata"]["report_code"] == "kg2_eligibility"
    assert "summary" in payload
    assert "eligible_children" in payload["summary"]
    assert "ineligible_children" in payload["summary"]
    assert "unevaluatable_records" in payload["summary"]
    assert "eligibility_rate" in payload["summary"]
    assert "data_completeness_rate" in payload["summary"]
    assert "highest_governorate" in payload["summary"]
    assert "interpretation_ar" in payload["summary"]
    assert "decision_implications" in payload["summary"]
    assert "breakdowns" in payload
    assert isinstance(payload["breakdowns"], list)
    if payload.get("chart"):
        assert payload["chart"]["type"] == "bar"
        assert payload["chart"]["group_by"] in ("governorate", "district", "area")
    assert "license_chart" in payload
    assert payload["license_chart"]["type"] == "pie"


def test_moe_kg2_eligibility_filters(db: Session):
    svc = AgencyReportsService(db)
    payload = svc.generate_report("moe", "kg2_eligibility", {"governorate": "إربد"})
    assert payload["metadata"]["filters"]["governorate"] == "إربد"
    if payload.get("chart"):
        assert payload["chart"]["group_by"] == "district"

    payload_city = svc.generate_report("moe", "kg2_eligibility", {"governorate": "إربد", "city": "الوسطية"})
    if payload_city.get("chart"):
        assert payload_city["chart"]["group_by"] == "area"


def test_moe_kg2_csv_export(db: Session):
    svc = AgencyReportsService(db)
    payload = svc.generate_report("moe", "kg2_eligibility", {})
    csv_out = to_csv(payload)
    assert isinstance(csv_out, str)
    assert csv_out.startswith("\ufeff")  # UTF-8 BOM check
    assert "moe" in csv_out
    assert "وزارة التربية والتعليم" in csv_out
