"""
P3-1: Verify that admin_en.json and admin_ar.json contain identical key sets.
Any key present in one file but absent in the other fails the build, catching
translation drift before it reaches production.
"""
import json
import os
from pathlib import Path
from typing import Set

import pytest

_I18N_DIR = Path(__file__).resolve().parent.parent / "static" / "i18n"


def _load(filename: str) -> dict:
    path = _I18N_DIR / filename
    # Handle files with or without UTF-8 BOM
    for enc in ("utf-8-sig", "utf-8"):
        try:
            return json.loads(path.read_bytes().decode(enc))
        except (UnicodeDecodeError, json.JSONDecodeError):
            continue
    raise ValueError(f"Could not decode {filename} as UTF-8")


def _flatten(obj: dict, prefix: str = "") -> Set[str]:
    """Return flat dot-notation key paths for all leaf values."""
    keys: Set[str] = set()
    for k, v in obj.items():
        full = f"{prefix}.{k}" if prefix else k
        if isinstance(v, dict):
            keys |= _flatten(v, full)
        else:
            keys.add(full)
    return keys


@pytest.fixture(scope="module")
def en_keys() -> Set[str]:
    return _flatten(_load("admin_en.json"))


@pytest.fixture(scope="module")
def ar_keys() -> Set[str]:
    return _flatten(_load("admin_ar.json"))


def test_no_keys_missing_in_arabic(en_keys, ar_keys):
    """Every key in EN must also exist in AR."""
    missing = sorted(en_keys - ar_keys)
    assert not missing, (
        f"{len(missing)} key(s) present in admin_en.json but missing in admin_ar.json:\n"
        + "\n".join(f"  - {k}" for k in missing)
    )


def test_no_extra_keys_in_arabic(en_keys, ar_keys):
    """Every key in AR must also exist in EN (catches orphaned Arabic-only keys)."""
    extra = sorted(ar_keys - en_keys)
    assert not extra, (
        f"{len(extra)} key(s) present in admin_ar.json but missing in admin_en.json:\n"
        + "\n".join(f"  - {k}" for k in extra)
    )


def test_i18n_files_exist():
    """Both i18n files must be present and non-empty."""
    for name in ("admin_en.json", "admin_ar.json"):
        path = _I18N_DIR / name
        assert path.exists(), f"Missing i18n file: {path}"
        assert path.stat().st_size > 0, f"Empty i18n file: {path}"
