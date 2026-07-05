from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
TEMPLATE = ROOT / "templates" / "admin" / "classification.html"
JS = ROOT / "static" / "js" / "admin_classification.js"


def test_table_has_caption_and_column_scope():
    """The results table had scope="col" on all 8 <th> but no <caption>."""
    html = TEMPLATE.read_text(encoding="utf-8")
    assert '<caption class="visually-hidden">' in html
    assert html.count('scope="col"') == 8


def test_no_fictitious_cyberlume_classes():
    """cyberlume-card/cyberlume-btn*/cyberlume-table are not defined
    anywhere in this app's CSS -- the Refresh button had no Bootstrap class
    at all and would render completely unstyled."""
    html = TEMPLATE.read_text(encoding="utf-8")
    assert "cyberlume" not in html


def test_no_raw_tailwind_utility_classes():
    """This app never loads Tailwind; the filter inputs/selects and
    several buttons used raw Tailwind-utility-class strings that render
    unstyled."""
    html = TEMPLATE.read_text(encoding="utf-8")
    for cls in ("bg-surface-container/50", "border-white/10", "text-on-surface\"",
                "outline-none", "appearance-none", "relative z-10",
                "text-cyber-light"):
        assert cls not in html, f"leftover Tailwind/fictitious class: {cls}"


def test_html_divs_are_balanced_in_content_block():
    """The #classificationRoot wrapper div (opened right after the page
    header) was never closed before {% endblock %} -- every section after
    it (summary cards, charts, results table, and the entire detail modal)
    ended up nested one level deeper than the markup implied."""
    html = TEMPLATE.read_text(encoding="utf-8")
    content = html.split("{% block content %}")[1].split("{% endblock %}")[0]
    opens = content.count("<div")
    closes = content.count("</div>")
    assert opens == closes, f"unbalanced <div> tags: {opens} opens vs {closes} closes"


def test_detail_modal_title_element_exists():
    """admin_classification.js's openDetail() looks up
    getElementById("classificationDetailTitle") and returns early (before
    ever calling modal.show()) if it's missing -- no such element existed
    anywhere in the template, so the "View Details" button never opened
    the modal on any row, on any tab."""
    html = TEMPLATE.read_text(encoding="utf-8")
    assert 'id="classificationDetailTitle"' in html
    js = JS.read_text(encoding="utf-8")
    assert 'getElementById("classificationDetailTitle")' in js


def test_district_filter_uses_matching_param_name():
    """The frontend serialized the District dropdown as `city`, but every
    consuming endpoint (kindergartens/managers/supervisors/detail) only
    ever declared a `district` query parameter -- FastAPI silently dropped
    the unrecognized `city` param, so the District filter had zero effect."""
    js = JS.read_text(encoding="utf-8")
    assert '["district", "citySelect"]' in js
    assert 'district: "citySelect"' in js
    assert '"city"' not in js
    assert "city: \"citySelect\"" not in js


def test_backend_endpoints_accept_district_param():
    import inspect
    import classification_service

    for fn_name in ("get_admin_kindergarten_leaderboard", "get_admin_manager_leaderboard",
                    "get_admin_supervisor_leaderboard"):
        fn = getattr(classification_service, fn_name)
        sig = inspect.signature(fn)
        assert "district" in sig.parameters


def test_export_button_is_wired_to_csv_generation():
    """#exportClassificationBtn had no onclick, no data-* action, and no
    matching JS event listener anywhere -- clicking it did nothing."""
    js = JS.read_text(encoding="utf-8")
    assert 'getElementById("exportClassificationBtn")' in js
    assert "exportClassificationCsv" in js


def test_toast_close_button_is_bilingual():
    """The toast's close-button aria-label was hardcoded to the English
    word "Close" regardless of window.KINJO_LANG."""
    js = JS.read_text(encoding="utf-8")
    assert 'aria-label="Close"' not in js
