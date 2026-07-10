"""Tests for the Custom Reports (التقارير المخصصة) section of /admin/agency-reports.

Covers page access + RBAC, the schema endpoint, the run endpoint (validation +
stable envelope + no fabricated data), and the CSV export.
"""
import re

import pytest

from dependencies import get_current_user, get_current_user_or_redirect
from main import app

# ----------------------------- page (frontend) -----------------------------

def test_admin_can_access_agency_reports_page_with_custom_section(client, admin_user):
    app.dependency_overrides[get_current_user_or_redirect] = lambda: admin_user
    try:
        resp = client.get("/admin/agency-reports")
        assert resp.status_code == 200
        html = resp.text
        # Custom Reports section is present in Arabic + wired to backend-driven JS.
        assert "التقارير المخصصة" in html
        assert 'id="custom-report-form"' in html
        assert "admin_agency_reports_custom.js" in html
        # Arabic RTL document.
        assert 'lang="ar"' in html and 'dir="rtl"' in html
        # No raw i18n keys / mojibake in the page.
        assert not re.search(r"\{\{\s*[\w.]+\s*\|\s*trans", html)
        for junk in ("â€", "Ã", "Ø›Ø", "ï»¿", "�"):
            assert junk not in html
    finally:
        app.dependency_overrides.clear()


@pytest.mark.parametrize("role_fixture", ["manager_user", "supervisor_user", "parent_user"])
def test_non_admin_cannot_access_agency_reports_page(client, request, role_fixture):
    user = request.getfixturevalue(role_fixture)
    app.dependency_overrides[get_current_user_or_redirect] = lambda: user
    try:
        resp = client.get("/admin/agency-reports", follow_redirects=False)
        assert resp.status_code in (302, 307)
    finally:
        app.dependency_overrides.clear()


# ----------------------------- schema endpoint -----------------------------

def test_custom_schema_admin(client, admin_user):
    app.dependency_overrides[get_current_user] = lambda: admin_user
    try:
        resp = client.get("/api/admin/agency-reports/custom/schema")
        assert resp.status_code == 200
        body = resp.json()
        assert body["success"] is True
        data = body["data"]
        assert {a["code"] for a in data["agencies"]} >= {"mosd", "moe", "moh", "mol", "dos", "ncfa"}
        assert {lvl["code"] for lvl in data["levels"]} >= {"national", "governorate", "city", "kindergarten", "class", "child", "supervisor", "manager"}
        assert {p["code"] for p in data["periods"]} >= {"day", "week", "month", "quarter", "half_year", "year", "custom"}
        assert len(data["domains"]) >= 8
        # every domain exposes indicators
        assert all(d.get("indicators") for d in data["domains"])
    finally:
        app.dependency_overrides.clear()


@pytest.mark.parametrize("role_fixture", ["manager_user", "supervisor_user", "parent_user"])
def test_custom_schema_forbidden_for_non_admin(client, request, role_fixture):
    user = request.getfixturevalue(role_fixture)
    app.dependency_overrides[get_current_user] = lambda: user
    try:
        resp = client.get("/api/admin/agency-reports/custom/schema")
        assert resp.status_code == 403
    finally:
        app.dependency_overrides.clear()


# ----------------------------- run endpoint --------------------------------

def test_custom_run_returns_stable_envelope(client, admin_user):
    app.dependency_overrides[get_current_user] = lambda: admin_user
    try:
        resp = client.post("/api/admin/agency-reports/custom", json={
            "agency": "mosd", "level": "national", "period": "year",
            "indicators": ["children_count", "gender_distribution", "kindergarten_status"],
        })
        assert resp.status_code == 200
        body = resp.json()
        assert body["success"] is True
        data = body["data"]
        for key in ("title", "scope", "kpis", "table", "charts", "summary_ar", "decision_notes_ar", "data_quality"):
            assert key in data, f"missing envelope key: {key}"
        assert data["scope"]["agency"] == "mosd"
        assert data["scope"]["start_date"] and data["scope"]["end_date"]
        assert isinstance(data["kpis"], list) and len(data["kpis"]) >= 1
        assert data["data_quality"]["status"] in ("sufficient", "limited", "incomplete")
    finally:
        app.dependency_overrides.clear()


def test_custom_run_unavailable_indicator_not_fabricated(client, admin_user):
    app.dependency_overrides[get_current_user] = lambda: admin_user
    try:
        resp = client.post("/api/admin/agency-reports/custom", json={
            "agency": "moh", "level": "national", "period": "year",
            "indicators": ["vaccination_coverage"],
        })
        assert resp.status_code == 200
        data = resp.json()["data"]
        # No fabricated KPI for an unavailable indicator; reported in data_quality.
        assert all(k["code"] != "vaccination_coverage" for k in data["kpis"])
        assert data["data_quality"]["status"] in ("incomplete", "limited")
        assert any("المطاعيم" in note or "بيانات" in note for note in data["data_quality"]["notes"])
    finally:
        app.dependency_overrides.clear()


@pytest.mark.parametrize("payload", [
    {"agency": "zzz", "indicators": ["children_count"]},          # bad agency
    {"agency": "mosd", "indicators": []},                          # no indicators
    {"agency": "mosd", "level": "bogus", "indicators": ["children_count"]},  # bad level
    {"agency": "mosd", "period": "nope", "indicators": ["children_count"]},  # bad period
    {"agency": "mosd", "indicators": ["not_a_real_indicator"]},    # unknown indicator
    {"agency": "mosd", "period": "custom", "indicators": ["children_count"]},  # missing custom dates
])
def test_custom_run_validates_bad_filters(client, admin_user, payload):
    app.dependency_overrides[get_current_user] = lambda: admin_user
    try:
        resp = client.post("/api/admin/agency-reports/custom", json=payload)
        assert resp.status_code == 400
    finally:
        app.dependency_overrides.clear()


@pytest.mark.parametrize("role_fixture", ["manager_user", "supervisor_user", "parent_user"])
def test_custom_run_forbidden_for_non_admin(client, request, role_fixture):
    user = request.getfixturevalue(role_fixture)
    app.dependency_overrides[get_current_user] = lambda: user
    try:
        resp = client.post("/api/admin/agency-reports/custom", json={"agency": "mosd", "indicators": ["children_count"]})
        assert resp.status_code == 403
    finally:
        app.dependency_overrides.clear()


# ----------------------------- CSV export ----------------------------------

def test_custom_export_csv(client, admin_user):
    app.dependency_overrides[get_current_user] = lambda: admin_user
    try:
        resp = client.post("/api/admin/agency-reports/custom/export.csv", json={
            "agency": "mosd", "level": "national", "period": "year",
            "indicators": ["children_count", "gender_distribution"],
        })
        assert resp.status_code == 200
        assert resp.headers["content-type"].startswith("text/csv")
        assert resp.text.startswith("﻿")  # UTF-8 BOM for Arabic
        assert "المؤشر" in resp.text
    finally:
        app.dependency_overrides.clear()


def test_custom_export_csv_forbidden_for_non_admin(client, manager_user):
    app.dependency_overrides[get_current_user] = lambda: manager_user
    try:
        resp = client.post("/api/admin/agency-reports/custom/export.csv", json={"agency": "mosd", "indicators": ["children_count"]})
        assert resp.status_code == 403
    finally:
        app.dependency_overrides.clear()
