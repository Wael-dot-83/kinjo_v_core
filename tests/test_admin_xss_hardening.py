"""Regression contracts for Admin values that cross into HTML rendering."""

from pathlib import Path

from starlette.requests import Request

from main import _get_request_ip


ROOT = Path(__file__).resolve().parents[1]


def source(path: str) -> str:
    return (ROOT / path).read_text(encoding="utf-8")


def request_with_ip(header_value: str | None, client_host: str = "127.0.0.1") -> Request:
    headers = []
    if header_value is not None:
        headers.append((b"x-forwarded-for", header_value.encode("utf-8")))
    return Request(
        {
            "type": "http",
            "method": "GET",
            "path": "/api/auth/login",
            "headers": headers,
            "client": (client_host, 12345),
        }
    )


def test_audit_ip_ingestion_rejects_markup_and_normalizes_valid_addresses():
    assert _get_request_ip(request_with_ip('<img src=x onerror="alert(1)">')) == "127.0.0.1"
    assert _get_request_ip(request_with_ip("2001:0db8::1, 10.0.0.1")) == "2001:db8::1"


def test_audit_log_api_values_are_html_escaped_before_inner_html_rendering():
    js = source("static/js/audit-logs.js")
    for expression in (
        "this.escapeHtml(this.getActionLabel(log.action))",
        "this.escapeHtml(this.getEntityTypeLabel(log.entity_type) || \"-\")",
        "this.escapeHtml(log.entity_id || \"-\")",
        "this.escapeHtml(log.ip_address || \"-\")",
    ):
        assert expression in js
    assert '<td>${log.ip_address || "-"}</td>' not in js


def test_agency_chart_fallback_uses_text_nodes_for_stored_labels():
    js = source("static/js/agency_report_components.js")
    assert "labelCell.textContent = String(localizedValue(point.label));" in js
    assert "valueCell.textContent = point.value == null" in js
    assert "tr.append(labelCell, valueCell);" in js
    assert "tr.innerHTML = `<td>${String(localizedValue(point.label))}" not in js


def test_drilldown_navigation_uses_data_attributes_and_event_listeners():
    js = source("static/js/admin_analytics_drilldown.js")
    assert "function drilldownEscapeHtml(value)" in js
    assert 'data-drill-id="${drilldownEscapeHtml(r.id)}"' in js
    assert 'row.addEventListener("click"' in js
    assert "drillHref(row.dataset.drillType, row.dataset.drillId)" in js
    assert 'onclick="window.location.href=drillHref' not in js
