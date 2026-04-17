"""
Server-side language integrity helpers.

This module enforces a no-mixed-language HTML response for English mode by
replacing known Arabic UI literals with their English equivalents.
"""

from __future__ import annotations

import json
import re
from functools import lru_cache
from pathlib import Path
from typing import Any


ROOT_DIR = Path(__file__).resolve().parent
I18N_DIR = ROOT_DIR / "static" / "i18n"
TEMPLATES_DIR = ROOT_DIR / "templates"
JS_DIR = ROOT_DIR / "static" / "js"

ARABIC_RE = re.compile(r"[\u0600-\u06FF]")
ARABIC_TOKEN_RE = re.compile(r"^[\u0600-\u06FF]+$")
REMAINING_ARABIC_SEQ_RE = re.compile(r"[\u0600-\u06FF]+")
SCRIPT_STYLE_RE = re.compile(
    r"(<script\b[^>]*>.*?</script>|<style\b[^>]*>.*?</style>)",
    re.IGNORECASE | re.DOTALL,
)
JINJA_IF_UI_LANG_RE = re.compile(
    r"\{%\s*if\s+ui_lang\s*==\s*['\"]en['\"]\s*%\}(.*?)\{%\s*else\s*%\}(.*?)\{%\s*endif\s*%\}",
    re.DOTALL,
)
JS_PAIR_RE = re.compile(
    r'"((?:\\.|[^"\\])*)"\s*:\s*"((?:\\.|[^"\\])*)"',
    re.DOTALL,
)
TWO_ARG_CALL_RE = re.compile(
    r"""\b[A-Za-z_]\w*\(\s*(['"])((?:\\.|(?!\1).)*)\1\s*,\s*(['"])((?:\\.|(?!\3).)*)\3\s*\)""",
    re.DOTALL,
)
THREE_ARG_CALL_RE = re.compile(
    r"""\b[A-Za-z_]\w*\(\s*(['"])((?:\\.|(?!\1).)*)\1\s*,\s*(['"])((?:\\.|(?!\3).)*)\3\s*,\s*(['"])((?:\\.|(?!\5).)*)\5\s*\)""",
    re.DOTALL,
)


def _normalize_space(value: str) -> str:
    return " ".join(str(value or "").split()).strip()


def _has_arabic(value: str) -> bool:
    return bool(ARABIC_RE.search(value or ""))


def _load_json(path: Path) -> dict[str, Any]:
    if not path.exists():
        return {}
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return {}


def _flatten_strings(value: Any, prefix: str = "", out: dict[str, str] | None = None) -> dict[str, str]:
    if out is None:
        out = {}
    if isinstance(value, str):
        if prefix:
            out[prefix] = value
        return out
    if isinstance(value, dict):
        for key, nested in value.items():
            next_key = f"{prefix}.{key}" if prefix else str(key)
            _flatten_strings(nested, next_key, out)
    elif isinstance(value, list):
        for idx, nested in enumerate(value):
            next_key = f"{prefix}.{idx}" if prefix else str(idx)
            _flatten_strings(nested, next_key, out)
    return out


def _decode_js_string(token: str) -> str:
    value = token or ""
    return (
        value.replace(r"\\", "\\")
        .replace(r"\"", '"')
        .replace(r"\'", "'")
        .replace(r"\n", " ")
        .replace(r"\r", " ")
        .replace(r"\t", " ")
        .strip()
    )


def _add_pair(pairs: dict[str, str], ar_text: str, en_text: str) -> None:
    ar_value = _normalize_space(ar_text)
    en_value = _normalize_space(en_text)
    if not ar_value or not en_value:
        return
    if not _has_arabic(ar_value):
        return
    if _has_arabic(en_value):
        return
    pairs[ar_value] = en_value


def _collect_pairs_from_catalog(ar_file: Path, en_file: Path, pairs: dict[str, str]) -> None:
    ar_data = _load_json(ar_file)
    en_data = _load_json(en_file)
    if not ar_data or not en_data:
        return
    ar_flat = _flatten_strings(ar_data)
    en_flat = _flatten_strings(en_data)
    for key, ar_value in ar_flat.items():
        _add_pair(pairs, ar_value, en_flat.get(key, ""))


def _collect_pairs_from_literal_overrides(path: Path, pairs: dict[str, str]) -> None:
    data = _load_json(path)
    if not isinstance(data, dict):
        return
    for ar_value, en_value in data.items():
        if isinstance(ar_value, str) and isinstance(en_value, str):
            _add_pair(pairs, ar_value, en_value)


def _collect_pairs_from_js_literals(path: Path, pairs: dict[str, str]) -> None:
    if not path.exists():
        return
    try:
        source = path.read_text(encoding="utf-8")
    except Exception:
        return
    for match in JS_PAIR_RE.finditer(source):
        ar_candidate = _decode_js_string(match.group(1))
        en_candidate = _decode_js_string(match.group(2))
        _add_pair(pairs, ar_candidate, en_candidate)


def _collect_pairs_from_bilingual_calls(path: Path, pairs: dict[str, str]) -> None:
    if not path.exists():
        return
    try:
        source = path.read_text(encoding="utf-8")
    except Exception:
        return

    # Patterns like: tr("AR", "EN")
    for match in TWO_ARG_CALL_RE.finditer(source):
        ar_candidate = _decode_js_string(match.group(2))
        en_candidate = _decode_js_string(match.group(4))
        _add_pair(pairs, ar_candidate, en_candidate)

    # Patterns like: helper("key", "AR", "EN")
    for match in THREE_ARG_CALL_RE.finditer(source):
        ar_candidate = _decode_js_string(match.group(4))
        en_candidate = _decode_js_string(match.group(6))
        _add_pair(pairs, ar_candidate, en_candidate)


def _strip_jinja_controls(value: str) -> str:
    stripped = re.sub(r"\{#[\s\S]*?#\}", " ", value)
    stripped = re.sub(r"\{%-?[\s\S]*?-?%\}", " ", stripped)
    stripped = re.sub(r"\{\{[\s\S]*?\}\}", " ", stripped)
    return _normalize_space(stripped)


def _collect_pairs_from_template_conditionals(pairs: dict[str, str]) -> None:
    if not TEMPLATES_DIR.exists():
        return
    for template_path in TEMPLATES_DIR.rglob("*.html"):
        try:
            content = template_path.read_text(encoding="utf-8")
        except Exception:
            continue
        for match in JINJA_IF_UI_LANG_RE.finditer(content):
            en_raw = _strip_jinja_controls(match.group(1))
            ar_raw = _strip_jinja_controls(match.group(2))
            _add_pair(pairs, ar_raw, en_raw)


def _build_literal_map() -> dict[str, str]:
    pairs: dict[str, str] = {}

    # Catalog pairs.
    _collect_pairs_from_catalog(I18N_DIR / "app_ar.json", I18N_DIR / "app_en.json", pairs)
    _collect_pairs_from_catalog(I18N_DIR / "admin_ar.json", I18N_DIR / "admin_en.json", pairs)

    # Manual literal overrides.
    _collect_pairs_from_literal_overrides(I18N_DIR / "literal_en_overrides.json", pairs)
    _collect_pairs_from_literal_overrides(I18N_DIR / "literal_en_quality_overrides.json", pairs)

    # Existing client-side literal dictionaries.
    _collect_pairs_from_js_literals(JS_DIR / "app_i18n.js", pairs)
    _collect_pairs_from_js_literals(JS_DIR / "admin_i18n.js", pairs)
    for js_path in JS_DIR.rglob("*.js"):
        _collect_pairs_from_bilingual_calls(js_path, pairs)
    for template_path in TEMPLATES_DIR.rglob("*.html"):
        _collect_pairs_from_bilingual_calls(template_path, pairs)

    # Any explicit EN/AR branches already present in templates.
    _collect_pairs_from_template_conditionals(pairs)

    # Core shell fallbacks.
    fallback_pairs = {
        "لوحة التحكم": "Dashboard",
        "مسار التنقل": "Breadcrumb",
        "الرئيسية": "Home",
        "إغلاق": "Close",
        "إلغاء": "Cancel",
        "بحث": "Search",
        "تسجيل الدخول": "Sign in",
        "تسجيل الخروج": "Log out",
        "جاري التحميل": "Loading",
        "غير متاح": "Not available",
        "غير محدد": "Unspecified",
    }
    for ar_value, en_value in fallback_pairs.items():
        _add_pair(pairs, ar_value, en_value)

    return pairs


class EnglishHtmlTranslator:
    def __init__(self) -> None:
        self.literal_map = _build_literal_map()
        self.normalized_literal_map = {
            _normalize_space(key): value for key, value in self.literal_map.items()
        }
        phrase_keys: list[str] = []
        token_keys: list[str] = []
        for key in self.literal_map.keys():
            if ARABIC_TOKEN_RE.fullmatch(key):
                token_keys.append(key)
            else:
                phrase_keys.append(key)

        phrase_keys = sorted(phrase_keys, key=len, reverse=True)
        token_keys = sorted(token_keys, key=len, reverse=True)

        phrase_parts: list[str] = []
        for key in phrase_keys:
            part = re.escape(key).replace(r"\ ", r"\s+")
            phrase_parts.append(part)
        self.phrase_pattern = re.compile("|".join(phrase_parts)) if phrase_parts else None
        self.token_pattern = (
            re.compile(
                rf"(?<![\u0600-\u06FF])(?:{'|'.join(re.escape(key) for key in token_keys)})(?![\u0600-\u06FF])"
            )
            if token_keys
            else None
        )

    def _translate_segment(self, segment: str) -> str:
        if not _has_arabic(segment):
            return segment

        translated = segment
        if self.phrase_pattern:
            translated = self.phrase_pattern.sub(
                lambda match: self.normalized_literal_map.get(
                    _normalize_space(match.group(0)),
                    match.group(0),
                ),
                translated,
            )
        if self.token_pattern and _has_arabic(translated):
            translated = self.token_pattern.sub(
                lambda match: self.literal_map.get(match.group(0), match.group(0)),
                translated,
            )
        if _has_arabic(translated):
            # Hard no-mix fallback for English mode: remove any residual Arabic
            # literals that were not captured by catalogs/heuristics.
            translated = REMAINING_ARABIC_SEQ_RE.sub(" ", translated)
        return translated

    def translate_html(self, html: str) -> str:
        if not html or not _has_arabic(html):
            return html
        parts = SCRIPT_STYLE_RE.split(html)
        for idx in range(0, len(parts), 2):
            parts[idx] = self._translate_segment(parts[idx])
        return "".join(parts)


_ENGLISH_TRANSLATOR = EnglishHtmlTranslator()


@lru_cache(maxsize=32)
def _translate_cached_html(html: str) -> str:
    return _ENGLISH_TRANSLATOR.translate_html(html)


def enforce_english_html_integrity(html: str) -> str:
    """Translate known Arabic UI literals in HTML into English."""
    if not html or not _has_arabic(html):
        return html
    return _translate_cached_html(html)
