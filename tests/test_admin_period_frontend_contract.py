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
    @staticmethod
    def _loader_body(src):
        loader = re.search(r"#loadOverviewData\(\)\s*\{(.*?)\n  \}", src, re.S)
        assert loader, "#loadOverviewData not found"
        return loader.group(1)

    def test_custom_period_sends_both_dates(self, kg_overview_src):
        """Regression: the Custom button sent `period=custom` with no dates, so the
        server silently used its 30-day default and the date inputs did nothing."""
        body = self._loader_body(kg_overview_src)
        assert "start_date" in body and "end_date" in body, (
            "#loadOverviewData must send start_date/end_date for period=custom"
        )

    def test_loader_reads_the_range_from_the_store_not_the_dom(self, kg_overview_src):
        """init() loads data *before* #buildControlBar(), so the date inputs do not
        exist during the first load. Reading the DOM there meant a persisted
        period='custom' silently fell back to the month window while the control bar
        rendered "Custom" as active — the UI showing one range and the data another.
        """
        body = self._loader_body(kg_overview_src)
        assert "getElementById" not in body, (
            "#loadOverviewData must not read the DOM: it runs before the control "
            "bar exists, so the inputs would be null on a reload"
        )
        assert "dateFrom" in body and "dateTo" in body, (
            "#loadOverviewData must read the custom range from the store"
        )

    def test_init_loads_before_building_the_control_bar(self, kg_overview_src):
        """Pins the ordering the store-based fix depends on. If the control bar is
        ever built first it must be re-verified that its dropdowns, which read the
        loaded `kgs`, are still populated."""
        init = re.search(r"async init\(\)\s*\{(.*?)\n  \}", kg_overview_src, re.S)
        assert init, "init() not found"
        body = init.group(1)
        assert body.index("#loadOverviewData") < body.index("#buildControlBar"), (
            "init() order changed — re-check that #loadOverviewData no longer "
            "depends on control-bar DOM and that the filter dropdowns still populate"
        )

    def test_custom_range_is_persisted_with_the_period(self, kg_overview_src):
        """Persisting `period='custom'` without its dates is what let a reload
        resolve to a different window than the bar displayed."""
        prefs = re.search(r"#savePrefs\(\)\s*\{(.*?)\n  \}", kg_overview_src, re.S)
        assert prefs, "#savePrefs not found"
        body = prefs.group(1)
        assert "dateFrom" in body and "dateTo" in body, (
            "#savePrefs must persist the custom range alongside `period`"
        )

    def test_store_seeds_the_custom_range(self, kg_overview_src):
        """The store must always hold a usable range, so period=custom can never be
        restored without dates."""
        assert re.search(r"dateFrom:\s*saved\.dateFrom\s*\|\|", kg_overview_src)
        assert re.search(r"dateTo:\s*saved\.dateTo\s*\|\|", kg_overview_src)

    def test_changing_a_custom_date_syncs_the_store_and_refetches(self, kg_overview_src):
        """The server resolves the window, so a date change must reach the store
        (which the loader reads) and refetch — not just re-filter rows in memory."""
        handler = re.search(
            r"\[\['ko-date-from', 'dateFrom'\], \['ko-date-to', 'dateTo'\]\]\.forEach\("
            r"([\s\S]*?)\n    \}\);",
            kg_overview_src,
        )
        assert handler, "date-range change handler not found"
        body = handler.group(1)
        assert "#store.set" in body, "a date change must update the store"
        assert "#onPeriodChange" in body, (
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
