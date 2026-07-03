import re
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
DASHBOARD_JS = ROOT / "static" / "js" / "dashboard.js"
DASHBOARD_FILTERS_JS = ROOT / "static" / "js" / "dashboard_filters.js"
DECISION_SUPPORT_JS = ROOT / "static" / "js" / "decision_support.js"


def test_kpi_cards_expose_status_attribute_used_by_filter_layer():
    source = DASHBOARD_JS.read_text(encoding="utf-8")
    assert 'data-status="${kpi.band}"' in source
    assert 'data-kpi-status="${kpi.band}"' in source

    filters = DASHBOARD_FILTERS_JS.read_text(encoding="utf-8")
    assert 'document.querySelectorAll("[data-kpi-status]")' in filters


def test_dashboard_summary_uses_csrf_aware_fetch_when_available():
    source = DASHBOARD_FILTERS_JS.read_text(encoding="utf-8")
    assert 'typeof window.fetchWithAuth === "function" ? window.fetchWithAuth : fetch' in source
    assert 'credentials: "same-origin"' in source
    assert 'fetch("/api/dashboard/summary"' not in source


def test_decision_support_charts_have_fallback_paths():
    source = DECISION_SUPPORT_JS.read_text(encoding="utf-8")
    for helper in (
        "function canRenderChart()",
        "function showCanvasFallback(",
        "function prepareCanvas(",
        "function renderDecisionSupportFallback()",
    ):
        assert helper in source

    assert re.search(r"catch\s*\(err\)\s*\{[^}]*renderDecisionSupportFallback\(\)", source, re.S)
    assert source.count("showCanvasFallback(chartEl, dsText(\"ds.no_data\"));") >= 4
