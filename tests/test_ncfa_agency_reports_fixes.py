"""Regression tests for three /admin/agency-reports fixes.

1. Malformed enum filter values (e.g. lowercase "male") must not 500 the report
   (was: uncaught ValueError from models.Gender("male")).
2. Admin surfaces must NOT apply small-cell suppression: the interactive
   custom-report view and the CSV export both show real, complete values —
   no masked ("محجوب") cells anywhere an authorized admin reviews the data.
3. Report catalog exposes localized data-source names (no raw English model
   names like "Child"/"ParentProfile" leaking into the UI).
"""
from unittest.mock import patch

import pytest

import models
from agency_reports_service import AgencyReportsService, _coerce_enum
from dependencies import get_current_user
from main import app

VALID_SCOPE = {
    "agency": "mosd",
    "level": "national",
    "period": "year",
    "indicators": ["children_count", "gender_distribution"],
}


# --------------------------------------------------------------------------
# Issue 1 — enum coercion guard
# --------------------------------------------------------------------------
def test_coerce_enum_case_insensitive_and_safe():
    assert _coerce_enum(models.Gender, "male") is models.Gender.MALE
    assert _coerce_enum(models.Gender, "MALE") is models.Gender.MALE
    assert _coerce_enum(models.Gender, "Female") is models.Gender.FEMALE
    assert _coerce_enum(models.Gender, "garbage") is None
    assert _coerce_enum(models.Gender, "") is None
    assert _coerce_enum(models.Gender, None) is None
    assert _coerce_enum(models.KindergartenStatus, "active") is models.KindergartenStatus.ACTIVE
    assert _coerce_enum(models.SeverityLevel, "high") is models.SeverityLevel.HIGH


@pytest.mark.parametrize("gender", ["male", "MALE", "female", "garbage", ""])
def test_child_family_profile_gender_filter_never_500(client, admin_user, gender):
    app.dependency_overrides[get_current_user] = lambda: admin_user
    try:
        resp = client.get(
            "/api/admin/agency-reports/ncfa/reports/child_family_profile",
            params={"gender": gender},
        )
        assert resp.status_code == 200, resp.text
    finally:
        app.dependency_overrides.clear()


# --------------------------------------------------------------------------
# Issue 2 — suppression off on every admin surface (view + CSV export)
# --------------------------------------------------------------------------
def test_custom_report_interactive_endpoint_does_not_suppress(client, admin_user):
    app.dependency_overrides[get_current_user] = lambda: admin_user
    try:
        resp = client.post("/api/admin/agency-reports/custom", json=VALID_SCOPE)
        assert resp.status_code == 200, resp.text
        dq = resp.json()["data"]["data_quality"]
        assert dq["suppressed_cells"] == 0
    finally:
        app.dependency_overrides.clear()


def test_custom_report_export_csv_does_not_suppress(client, admin_user, sample_child):
    """The CSV export must carry the same complete values as the on-screen
    view: with one recorded child the gender breakdown has small cells (< 5),
    which must appear as real numbers — never as "محجوب"."""
    app.dependency_overrides[get_current_user] = lambda: admin_user
    try:
        resp = client.post("/api/admin/agency-reports/custom/export.csv", json=VALID_SCOPE)
        assert resp.status_code == 200, resp.text
        assert "محجوب" not in resp.text
    finally:
        app.dependency_overrides.clear()


def test_custom_report_suppress_flag_gates_disclosure_control(test_db):
    svc = AgencyReportsService(test_db)
    with patch.object(svc, "_apply_small_cell_suppression", return_value=0) as m:
        svc.custom_report(dict(VALID_SCOPE), suppress=False)
    assert not m.called, "admin surfaces must not run small-cell suppression"

    with patch.object(svc, "_apply_small_cell_suppression", return_value=0) as m:
        svc.custom_report(dict(VALID_SCOPE), suppress=True)
    assert m.called, "the suppress flag must still gate disclosure control at the service level"


# --------------------------------------------------------------------------
# Issue 3 — localized data-source names (no raw model-name leakage)
# --------------------------------------------------------------------------
_RAW_MODEL_NAMES = {
    "Child", "ParentProfile", "EnrollmentApplication", "Kindergarten", "Class",
    "Incident", "AttendanceLog", "DailyReport", "User", "Message",
    "SupervisorAssignment", "StaffTrainingCompletion",
}


def test_catalog_localizes_data_source_names(test_db):
    catalog = AgencyReportsService(test_db).catalog()
    for agency in catalog["agencies"]:
        for report in agency["reports"]:
            assert "data_sources_ar" in report
            assert len(report["data_sources_ar"]) == len(report["data_sources"])
            for name in report["data_sources_ar"]:
                assert name not in _RAW_MODEL_NAMES, (
                    f"raw model name leaked in {report['report_code']}: {name}"
                )
    ncfa = next(a for a in catalog["agencies"] if a["code"] == "ncfa")
    profile = next(r for r in ncfa["reports"] if r["report_code"] == "child_family_profile")
    assert profile["data_sources_ar"] == ["سجل الأطفال", "ملفات أولياء الأمور", "سجلات التسجيل"]
