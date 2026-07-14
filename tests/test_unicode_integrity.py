"""Permanent Unicode, Arabic localization, and charset regression gates."""

from __future__ import annotations

import importlib.util
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def _load_auditor():
    path = ROOT / "scripts/manual-diagnostics/audit_unicode_integrity.py"
    spec = importlib.util.spec_from_file_location("audit_unicode_integrity", path)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_first_party_text_is_clean_utf8_without_mojibake_or_stale_brand() -> None:
    auditor = _load_auditor()
    assert auditor.audit_source_files(ROOT) == []


def test_base_layouts_declare_utf8_explicitly() -> None:
    for relative in (
        "templates/base.html",
        "templates/admin_base.html",
        "templates/manager_base.html",
        "templates/500.html",
    ):
        text = (ROOT / relative).read_text(encoding="utf-8")
        assert '<meta charset="UTF-8"' in text


def test_server_and_database_enforce_utf8(client) -> None:
    main_source = (ROOT / "main.py").read_text(encoding="utf-8")
    database_source = (ROOT / "database.py").read_text(encoding="utf-8")

    assert "UTF8ContentTypeMiddleware" in main_source
    assert "charset=utf-8" in main_source
    assert '"client_encoding": "utf8"' in database_source
    assert "PRAGMA encoding = 'UTF-8'" in database_source

    html_response = client.get("/login")
    javascript_response = client.get("/static/js/auth.js")
    assert "text/html; charset=utf-8" in html_response.headers["content-type"].lower()
    assert "application/javascript; charset=utf-8" in javascript_response.headers[
        "content-type"
    ].lower()
