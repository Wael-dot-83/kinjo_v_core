"""The admin period UIs must only send windows the API can resolve.

Tightening the backend to reject an unresolvable `period=custom` (rather than
silently substituting a different window) exposed two frontends that sent exactly
that:

* `admin_activity_filters.js` reloads the moment "Custom range" is picked — before
  either date is filled in — and rehydrates state from a bookmarked
  `?period=custom` URL.
* `kg_overview.js` had a Custom button and two date inputs, but never sent the
  dates at all; the server always answered with its default 30-day window, so
  choosing a range appeared to work while changing nothing.

These are static contract checks on the shipped JS: they need no browser, and they
fail if either page starts sending an incomplete custom range again.
"""
import re
from pathlib import Path

import pytest

ACTIVITY_JS = Path("static/js/admin_activity_filters.js")
KG_OVERVIEW_JS = Path("static/js/kg_overview.js")


@pytest.fixture(scope="module")
def activity_src():
    return ACTIVITY_JS.read_text(encoding="utf-8")


@pytest.fixture(scope="module")
def kg_overview_src():
    return KG_OVERVIEW_JS.read_text(encoding="utf-8")


class TestActivityFilterBar:
    def test_period_is_gated_on_a_complete_custom_range(self, activity_src):
        """`period` must not be sent for an incomplete custom range."""
        assert re.search(
            r"this\.state\.period\s*!==\s*[\"']custom[\"']\s*\|\|\s*customRangeReady",
            activity_src,
        ), (
            "load() must omit `period` when period=custom lacks both dates; "
            "otherwise selecting 'Custom range' fires an unresolvable request"
        )

    def test_custom_dates_are_only_sent_together(self, activity_src):
        assert "start_date" in activity_src and "end_date" in activity_src
        assert re.search(
            r"customRangeReady\s*=\s*Boolean\(this\.state\.start_date\s*&&\s*this\.state\.end_date\)",
            activity_src,
        ), "start_date/end_date must be gated on both being present"


class TestKgOverviewControlBar:
    def test_custom_period_sends_both_dates(self, kg_overview_src):
        """Regression: the Custom button sent `period=custom` with no dates, so the
        server silently used its 30-day default and the date inputs did nothing."""
        assert "ko-date-from" in kg_overview_src and "ko-date-to" in kg_overview_src
        loader = re.search(
            r"#loadOverviewData\(\)\s*\{(.*?)\n  \}", kg_overview_src, re.S
        )
        assert loader, "#loadOverviewData not found"
        body = loader.group(1)
        assert "ko-date-from" in body and "ko-date-to" in body, (
            "#loadOverviewData must read the custom date inputs — otherwise the "
            "chosen range is never sent to the server"
        )
        assert "start_date" in body and "end_date" in body, (
            "#loadOverviewData must send start_date/end_date for period=custom"
        )

    def test_incomplete_custom_range_does_not_request_custom(self, kg_overview_src):
        loader = re.search(
            r"#loadOverviewData\(\)\s*\{(.*?)\n  \}", kg_overview_src, re.S
        )
        body = loader.group(1)
        assert re.search(r"if\s*\(from\s*&&\s*to\)", body), (
            "period=custom must only be sent when both dates are present"
        )

    def test_changing_a_custom_date_refetches(self, kg_overview_src):
        """The server resolves the window, so a date change must refetch rather
        than only re-filtering the rows already in memory."""
        handler = re.search(
            r"\['ko-date-from','ko-date-to'\]\.forEach\((.*?)\}\);", kg_overview_src, re.S
        )
        assert handler, "date-range change handler not found"
        assert "#onPeriodChange" in handler.group(1), (
            "a custom date change must trigger a refetch (#onPeriodChange), not "
            "just #onFilterChange"
        )

    def test_preset_periods_remain_supported(self, kg_overview_src):
        """The control bar's presets must stay within what the API accepts
        (today|week|month|custom), or they 422."""
        periods_block = re.search(r"const periods = \[(.*?)\];", kg_overview_src, re.S)
        assert periods_block
        keys = set(re.findall(r"key:\s*'([^']+)'", periods_block.group(1)))
        assert keys <= {"today", "week", "month"}, f"unsupported period presets: {keys}"
