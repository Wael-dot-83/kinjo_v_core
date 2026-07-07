"""S1 — CSV formula-injection safety for the manager analytics export.

A cell whose text starts with = + - @ tab or CR can be executed as a formula by
Excel/LibreOffice. The export must neutralize those by prefixing a single quote,
while leaving numeric cells untouched and preserving RFC 4180 quoting.
"""
import csv
import io

import models
from main import app
from dependencies import get_current_user
from manager_analytics_endpoints import _csv_safe, _SafeCsvWriter


class TestCsvSafeHelper:
    def test_neutralizes_formula_prefixes(self):
        for payload in ('=HYPERLINK("http://evil","x")', "+1+1", "-2+3", "@SUM(A1)",
                        "\tstart", "\rstart"):
            out = _csv_safe(payload)
            assert out.startswith("'"), f"not neutralized: {payload!r} -> {out!r}"
            assert out[1:] == payload

    def test_leaves_plain_text_untouched(self):
        assert _csv_safe("الصف الأول") == "الصف الأول"
        assert _csv_safe("Class A") == "Class A"

    def test_leaves_numbers_untouched(self):
        # numbers can't be formulas; must not become text like "'-5"
        assert _csv_safe(5) == 5
        assert _csv_safe(-5) == -5
        assert _csv_safe(98.6) == 98.6
        assert _csv_safe(None) == ""

    def test_wrapper_sanitizes_every_cell(self):
        buf = io.StringIO()
        _SafeCsvWriter(csv.writer(buf)).writerow(["safe", "=EVIL()", 3])
        row = next(csv.reader(io.StringIO(buf.getvalue())))
        assert row == ["safe", "'=EVIL()", "3"]


def test_export_neutralizes_malicious_class_name(client, test_db, manager_user):
    """A class named =HYPERLINK(...) must export as an inert (quote-prefixed) cell."""
    evil = '=HYPERLINK("http://evil","x")'
    cls = models.Class(
        kindergarten_id=manager_user.kindergarten_id,
        name_ar=evil,
        name_en=evil,
        class_code="EVIL1",
        age_group="AGE_1_2",
        capacity_total=20,
        min_age_months=24,
        max_age_months=48,
        is_active=True,
    )
    test_db.add(cls)
    test_db.commit()

    app.dependency_overrides[get_current_user] = lambda: manager_user
    try:
        resp = client.get("/api/manager/analytics/export/csv?report_type=drilldown")
        assert resp.status_code == 200, resp.text
        # Parse the CSV back (this reverses RFC 4180 quoting) and assert the
        # class-name cell is the neutralized, inert form — never the raw formula.
        rows = list(csv.reader(io.StringIO(resp.text)))
        cells = [c for row in rows for c in row]
        assert evil not in cells, "unescaped formula cell present in export"
        assert ("'" + evil) in cells
    finally:
        app.dependency_overrides.pop(get_current_user, None)
