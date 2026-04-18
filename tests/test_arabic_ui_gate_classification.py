import re
from pathlib import Path


ARABIC_RE = re.compile(r"[\u0600-\u06FF]")
LATIN_RE = re.compile(r"[A-Za-z]")
STRING_LITERAL_RE = re.compile(r"(['\"`])((?:\\.|(?!\1).)*)\1", re.DOTALL)


def _strip_template_markup(content: str) -> str:
    content = re.sub(r"{%.*?%}", " ", content, flags=re.DOTALL)
    content = re.sub(r"{{.*?}}", " ", content, flags=re.DOTALL)
    content = re.sub(r"<[^>]+>", " ", content)
    return content


def _strip_html_from_js_string(value: str) -> str:
    value = re.sub(r"<[^>]+>", " ", value)
    value = re.sub(r"\$\{[^}]+\}", " ", value)
    return value


def test_new_templates_contain_arabic_visible_text():
    """Templates must contain Arabic UI text (bilingual templates also pass)."""
    template_paths = [
        Path("templates/admin/classification.html"),
        Path("templates/manager/benchmarking.html"),
        Path("templates/supervisor/performance.html"),
    ]

    for path in template_paths:
        content = path.read_text(encoding="utf-8")
        visible_text = _strip_template_markup(content)
        assert ARABIC_RE.search(visible_text), f"لا يوجد نص عربي في {path}"


def test_new_js_ui_strings_do_not_mix_arabic_with_latin():
    js_paths = [
        Path("static/js/admin_classification.js"),
        Path("static/js/manager_benchmarking.js"),
        Path("static/js/supervisor_performance.js"),
    ]

    for path in js_paths:
        content = path.read_text(encoding="utf-8")
        for _, raw_value in STRING_LITERAL_RE.findall(content):
            value = _strip_html_from_js_string(raw_value).strip()
            if not value:
                continue
            if not ARABIC_RE.search(value):
                continue
            assert not LATIN_RE.search(value), f"يوجد مزج عربي/لاتيني في نص واجهة داخل {path}: {value}"
