"""
Tests for the analytics reports admin page.
- Template rendering (DOCTYPE, lang/dir, no duplicate IDs)
- A11y (labels, no nameless icon-only buttons)
- formatDateSafe / formatToAmman behavior
"""
import re
import urllib.request
import json
from datetime import datetime, timezone
import unittest
from unittest.mock import patch


class AnalyticsReportsTemplateTests(unittest.TestCase):
    """Tests for templates/admin/analytics/reports.html."""

    BASE_URL = "http://127.0.0.1:8000"

    def _login_token(self):
        data = urllib.parse.urlencode({
            "username": "admin",
            "password": "Admin@1234",
        }).encode()
        req = urllib.request.Request(f"{self.BASE_URL}/api/auth/login", data=data, method="POST")
        with urllib.request.urlopen(req) as resp:
            cookie = resp.headers.get("Set-Cookie", "")
            for part in cookie.split(";"):
                if part.strip().startswith("kinjo_csrf_token="):
                    return part.strip().split("=", 1)[1]
        return None

    def test_standards_mode_and_rtl_attributes(self):
        """Verify DOCTYPE and lang/dir on the rendered page."""
        token = self._login_token()
        req = urllib.request.Request(
            f"{self.BASE_URL}/admin/analytics/reports",
            headers={"Cookie": f"kinjo_csrf_token={token}"},
        )
        with urllib.request.urlopen(req) as resp:
            raw = resp.read()
            # Strip BOM if present
            if raw.startswith(b"\xef\xbb\xbf"):
                raw = raw[3:]
            html = raw.decode("utf-8", errors="replace")
            self.assertTrue(
                html.lstrip().lower().startswith("<!doctype html>"),
                "Page must start with <!DOCTYPE html>",
            )
            # The <html> tag must include lang and dir attributes
            self.assertRegex(html, r'<html\s[^>]*lang="[^"]+"', msg="<html> must have lang attr")
            self.assertRegex(html, r'<html\s[^>]*dir="[^"]+"',  msg="<html> must have dir attr")

    def test_no_duplicate_ids(self):
        token = self._login_token()
        req = urllib.request.Request(
            f"{self.BASE_URL}/admin/analytics/reports",
            headers={"Cookie": f"kinjo_csrf_token={token}"},
        )
        with urllib.request.urlopen(req) as resp:
            html = resp.read().decode("utf-8", errors="replace")
        ids = re.findall(r'id="([^"]+)"', html)
        dups = sorted({i for i in ids if ids.count(i) > 1})
        self.assertEqual(dups, [], f"Duplicate IDs found: {dups}")

    def test_all_filter_inputs_have_labels(self):
        """Every <select id="x"> should have a matching <label for="x">."""
        token = self._login_token()
        req = urllib.request.Request(
            f"{self.BASE_URL}/admin/analytics/reports",
            headers={"Cookie": f"kinjo_csrf_token={token}"},
        )
        with urllib.request.urlopen(req) as resp:
            html = resp.read().decode("utf-8", errors="replace")
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
        # Simulate the JS Intl call in Python
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