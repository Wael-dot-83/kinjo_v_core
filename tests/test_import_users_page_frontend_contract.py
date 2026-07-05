from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
TEMPLATE = ROOT / "templates" / "admin" / "import_users.html"


def test_dead_breadcrumb_block_removed():
    """13th confirmed occurrence of the dead-{% block breadcrumb %} bug
    class across the audit series -- admin_base.html only declares
    title/extra_head/page_header/content/extra_scripts."""
    html = TEMPLATE.read_text(encoding="utf-8")
    assert "{% block breadcrumb %}" not in html


def test_kinjo_lang_is_assigned():
    """window.KINJO_LANG was read (`const _isEn = window.KINJO_LANG ===
    'en';`) but never assigned anywhere on this page and no shared script
    loaded by admin_base.html sets it either -- _isEn was always false, so
    every JS-generated string (summary labels, button spinner text, the
    "select a file" alert) stayed Arabic regardless of the admin's actual
    language preference."""
    html = TEMPLATE.read_text(encoding="utf-8")
    assert 'window.KINJO_LANG = "{{ ui_lang }}"' in html
    assign_pos = html.index('window.KINJO_LANG = "{{ ui_lang }}"')
    read_pos = html.index("window.KINJO_LANG === 'en'")
    assert assign_pos < read_pos


def test_results_summary_reads_real_backend_field_names():
    """The import summary read data.imported/data.total, but the real
    CSVImportResult response has succeeded/total_rows (no imported/total
    keys at all) -- the "Imported" count was always 0 and "Total Rows"
    silently collapsed to just the error count, regardless of how many
    accounts were actually created. The per-row error table also read
    e.row (real field: row_number), so the "Row" column was always an
    em-dash."""
    html = TEMPLATE.read_text(encoding="utf-8")
    assert "data.imported" not in html
    assert "data.succeeded" in html
    assert "data.total ??" not in html
    assert "data.total_rows" in html
    assert "e.row ??" not in html
    assert "e.row_number ??" in html


def test_fetch_response_null_checked_before_use():
    """fetchWithAuth() returns null after a 401 redirect (it does not
    throw in that case) -- calling res.json() with no null check would
    throw "Cannot read properties of null", surfacing as a confusing
    generic "Upload failed" alert instead of letting the redirect happen
    cleanly."""
    html = TEMPLATE.read_text(encoding="utf-8")
    assert "if (!res) return;" in html


def test_errors_table_has_caption_and_column_scope():
    html = TEMPLATE.read_text(encoding="utf-8")
    assert '<caption class="visually-hidden">' in html
    assert html.count('<th scope="col">') == 3
