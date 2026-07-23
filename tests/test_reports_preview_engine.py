"""Smoke + accuracy coverage for the Reports Center engine.

POST /api/analytics/reports/preview must serve every report type the Reports
Center page exposes (11 tabs), return the ReportPreviewResponse shape the
frontend renders, and NOT fall into the per-branch "Failed to load ..."
exception path (which previously masked broken column references in the
staff_training / capacity / full_audit branches).
"""

import pytest

REPORT_TYPES = [
    "attendance",
    "incidents",
    "compliance",
    "enrollment",
    "full_audit",
    "staff_training",
    "welfare",
    "trends",
    "capacity",
    "parent_engagement",
    "data_quality",
]

PERIOD = {"period_start": "2026-01-01", "period_end": "2026-12-31"}

# Substrings that only appear when a branch threw and was swallowed.
_FAILURE_MARKERS = ["Failed to load", "تعذر تحميل"]


def _preview(client, headers, report_type, filters=None):
    body = {"report_type": report_type, "filters": filters or {}, **PERIOD}
    return client.post("/api/analytics/reports/preview", json=body, headers=headers)


@pytest.mark.parametrize("report_type", REPORT_TYPES)
def test_preview_returns_expected_shape(client, auth_headers_admin, report_type):
    resp = _preview(client, auth_headers_admin, report_type)
    assert resp.status_code == 200, resp.text
    data = resp.json()
    assert data["report_type"] == report_type
    assert isinstance(data["kpis"], list)
    assert isinstance(data["charts"], list)
    assert isinstance(data["sample_data"], list)
    assert "completeness_percent" in data["data_quality"]


@pytest.mark.parametrize("report_type", REPORT_TYPES)
def test_preview_branches_do_not_throw(client, auth_headers_admin, report_type):
    """No branch should hit its except-and-warn path on a clean run."""
    resp = _preview(client, auth_headers_admin, report_type)
    assert resp.status_code == 200, resp.text
    warn_text = " ".join(
        (w.get("en", "") + " " + w.get("ar", "")) if isinstance(w, dict) else str(w)
        for w in resp.json().get("warnings", [])
    )
    for marker in _FAILURE_MARKERS:
        assert marker not in warn_text, f"{report_type} warned: {warn_text!r}"


def test_incident_filters_accepted(client, auth_headers_admin):
    """Incident-specific filters must be accepted (not 4xx)."""
    resp = _preview(
        client,
        auth_headers_admin,
        "incidents",
        filters={
            "statuses": ["OPEN"],
            "severities": ["CRITICAL"],
            "incident_types": ["INJURY"],
            "sla_status": "overdue",
            "parent_informed": "no",
        },
    )
    assert resp.status_code == 200, resp.text


def test_preview_requires_period(client, auth_headers_admin):
    resp = client.post(
        "/api/analytics/reports/preview",
        json={"report_type": "attendance", "filters": {}},
        headers=auth_headers_admin,
    )
    assert resp.status_code == 400


def test_preview_rejects_unknown_type(client, auth_headers_admin):
    resp = _preview(client, auth_headers_admin, "not_a_real_report")
    assert resp.status_code == 400
