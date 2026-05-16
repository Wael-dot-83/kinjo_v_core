import json
import re
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
I18N_DIR = ROOT / "static" / "i18n"
ARABIC_RE = re.compile(r"[\u0600-\u06FF]")


def _load_json(path: Path):
    return json.loads(path.read_text(encoding="utf-8"))


def _iter_string_values(value):
    if isinstance(value, str):
        yield value
        return
    if isinstance(value, dict):
        for nested in value.values():
            yield from _iter_string_values(nested)
        return
    if isinstance(value, list):
        for nested in value:
            yield from _iter_string_values(nested)


def test_en_catalogs_have_no_arabic_values():
    files = [
        I18N_DIR / "app_en.json",
        I18N_DIR / "admin_en.json",
        I18N_DIR / "literal_en_overrides.json",
        I18N_DIR / "literal_en_quality_overrides.json",
    ]

    for path in files:
        data = _load_json(path)
        for value in _iter_string_values(data):
            assert not ARABIC_RE.search(value), (
                f"Arabic text found in English catalog {path.name}: {value}"
            )


def test_quality_overrides_have_no_garbled_keys():
    data = _load_json(I18N_DIR / "literal_en_quality_overrides.json")
    bad_keys = [key for key in data.keys() if "?" in key]
    assert not bad_keys, (
        "Found garbled keys in literal_en_quality_overrides.json: "
        + ", ".join(bad_keys[:5])
    )


def test_banned_terms_not_present_in_effective_literal_maps():
    merged = _load_json(I18N_DIR / "literal_en_overrides.json")
    merged.update(_load_json(I18N_DIR / "literal_en_quality_overrides.json"))

    banned_terms = ["rawdhati", "messaging pods"]
    values = [v.lower() for v in merged.values() if isinstance(v, str)]

    for term in banned_terms:
        assert not any(term in value for value in values), (
            f"Banned term '{term}' detected in literal English maps"
        )
