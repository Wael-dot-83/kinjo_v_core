from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
TEMPLATE = ROOT / "templates" / "admin" / "import_kindergartens.html"


def test_dead_breadcrumb_block_removed():
    """9th confirmed occurrence of the dead-{% block breadcrumb %} bug
    class across the audit series -- admin_base.html only declares
    title/extra_head/page_header/content/extra_scripts."""
    html = TEMPLATE.read_text(encoding="utf-8")
    assert "{% block breadcrumb %}" not in html


def test_results_table_uses_the_actual_import_response_not_the_wrong_endpoint():
    """The page used to re-fetch GET /api/admin/kindergartens/imported to
    populate the "Imported / Updated Records" table -- but that endpoint
    reads the disjoint ImportedKindergarten table (only ever populated by
    an unreachable CLI helper), never the Kindergarten rows this page's own
    upload just inserted. Fixed to read data.inserted_records directly from
    the import-excel response, and that second fetch (which also bypassed
    fetchWithAuth and never checked .ok) is now gone entirely."""
    html = TEMPLATE.read_text(encoding="utf-8")
    assert "/api/admin/kindergartens/imported" not in html
    assert "data.inserted_records" in html


def test_dead_updated_stat_card_removed():
    """The pipeline only ever skips duplicates, it never updates them (that
    upsert-on-duplicate logic only exists in the disjoint, CLI-only
    KindergartenImportService), so "updatedCount" was hardcoded to 0 and
    could never show a real value -- dead UI presenting a feature the
    pipeline doesn't have."""
    html = TEMPLATE.read_text(encoding="utf-8")
    assert "updatedCount" not in html


def test_results_table_has_caption_and_column_scope():
    html = TEMPLATE.read_text(encoding="utf-8")
    assert '<caption class="visually-hidden">' in html
    assert html.count('<th scope="col">') == 7


def test_dead_response_ok_check_removed():
    """fetchWithAuth() already throws on any non-2xx response before
    returning, so the page's own `if (!response.ok)` re-check after
    `await fetchWithAuth(...)` was unreachable dead code -- the real error
    path was, and remains, the outer catch block reading the Error thrown
    by fetchWithAuth (which now surfaces the real backend message)."""
    html = TEMPLATE.read_text(encoding="utf-8")
    assert "if (!response.ok)" not in html
