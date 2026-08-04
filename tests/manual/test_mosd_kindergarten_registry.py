"""Tests for MOSD Kindergarten Registry Report.
"""
import pytest
from sqlalchemy.orm import Session

import models
from database import SessionLocal
from agency_reports_registry import AGENCY_REPORT_REGISTRY
from agency_reports_service import AgencyReportsService
from agency_reports_export import to_csv


from database import SessionLocal, engine


@pytest.fixture
def db():
    models.Base.metadata.create_all(bind=engine)
    session = SessionLocal()
    try:
        yield session
    finally:
        session.close()


def test_mosd_registry_configuration():
    assert "mosd" in AGENCY_REPORT_REGISTRY
    mosd = AGENCY_REPORT_REGISTRY["mosd"]
    assert mosd["name_ar"] == "وزارة التنمية الاجتماعية"
    assert "kindergarten_registry" in mosd["reports"]


def test_mosd_kindergarten_registry_generation(db: Session):
    svc = AgencyReportsService(db)
    payload = svc.generate_report("mosd", "kindergarten_registry", {})
    assert payload["metadata"]["agency_code"] == "mosd"
    assert payload["metadata"]["report_code"] == "kindergarten_registry"
    assert "summary" in payload
    assert "total_kindergartens" in payload["summary"]
    assert "active_kindergartens" in payload["summary"]
    assert "breakdowns" in payload
    assert isinstance(payload["breakdowns"], list)
    if payload.get("chart"):
        assert payload["chart"]["type"] == "bar"
        assert payload["chart"]["group_by"] in ("governorate", "district")
    assert "license_chart" in payload
    assert payload["license_chart"]["type"] == "pie"


def test_mosd_kindergarten_registry_filters(db: Session):
    svc = AgencyReportsService(db)
    payload = svc.generate_report("mosd", "kindergarten_registry", {"governorate": "إربد"})
    assert payload["metadata"]["filters"]["governorate"] == "إربد"
    if payload.get("chart"):
        assert payload["chart"]["group_by"] == "district"
