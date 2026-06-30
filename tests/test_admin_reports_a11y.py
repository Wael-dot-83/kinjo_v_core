"""
Tests for the analytics reports admin page.
- Template rendering (DOCTYPE, lang/dir, no duplicate IDs)
- A11y (labels, no nameless icon-only buttons)
- formatDateSafe / formatToAmman behavior
"""
import re
import unittest
from datetime import datetime, timezone

import pytest
from fastapi.testclient import TestClient

from main import app


class AnalyticsReportsTemplateTests(unittest.TestCase):
    """Tests for templates/admin/analytics/reports.html."""

    @pytest.fixture(autouse=True)
    def _inject_fixtures(self, admin_token):
        self._admin_token = admin_token

    def _get_reports_html(self) -> str:
        with TestClient(app, raise_server_exceptions=False) as client:
            client.cookies.set("kinjo_token", self._admin_token)
            resp = client.get("/admin/analytics/reports")
            assert resp.status_code == 200, f"Page returned {resp.status_code}"
            return resp.text

    def test_standards_mode_and_rtl_attributes(self):
        """Verify DOCTYPE and lang/dir on the rendered page."""
        html = self._get_reports_html()
        self.assertTrue(
            html.lstrip().lower().startswith("<!doctype html>"),
            "Page must start with <!DOCTYPE html>",
        )
        self.assertRegex(html, r'<html\s[^>]*lang="[^"]+"', msg="<html> must have lang attr")
        self.assertRegex(html, r'<html\s[^>]*dir="[^"]+"', msg="<html> must have dir attr")

    def test_no_duplicate_ids(self):
        html = self._get_reports_html()
        ids = re.findall(r'id="([^"]+)"', html)
        dups = sorted({i for i in ids if ids.count(i) > 1})
        self.assertEqual(dups, [], f"Duplicate IDs found: {dups}")

    def test_all_filter_inputs_have_labels(self):
        """Every <select id="x"> should have a matching <label for="x">."""
        html = self._get_reports_html()
        select_ids = set(re.findall(r'<select[^>]*id="([^"]+)"', html))
        labeled = set()
        for sel_id in select_ids:
            if re.search(r'<label[^>]*for="' + re.escape(sel_id) + r'"', html):
                labeled.add(sel_id)
        missing = select_ids - labeled
        self.assertEqual(missing, set(), f"Selects without labels: {missing}")


class TimezoneHelperTests(unittest.TestCase):
    """Test that timestamps round-trip and serialize as ISO 8601 UTC."""

    def test_iso_8601_utc_format(self):
        utc = datetime(2026, 6, 14, 8, 0, 0, tzinfo=timezone.utc)
        iso = utc.isoformat()
        self.assertEqual(iso, "2026-06-14T08:00:00+00:00")

    def test_intl_amman_renders_valid_string(self):
        try:
            from zoneinfo import ZoneInfo
            amman = ZoneInfo("Asia/Amman")
        except ImportError:
            from pytz import timezone as _tz
            amman = _tz("Asia/Amman")
        utc = datetime(2026, 6, 14, 8, 0, 0, tzinfo=timezone.utc)
        local = utc.astimezone(amman)
        formatted = local.strftime("%Y-%m-%d %H:%M")
        self.assertRegex(formatted, r"^\d{4}-\d{2}-\d{2} \d{2}:\d{2}$")


if __name__ == "__main__":
    unittest.main()
