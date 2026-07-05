import shutil
import subprocess

import pytest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
TEMPLATE = ROOT / "templates" / "admin" / "users" / "form.html"


def test_username_pattern_matches_backend_and_is_valid_regex():
    """Backend (admin_security.py UserCreateSchema) allows
    ^[a-zA-Z0-9_-]+$ (letters, digits, underscore, AND hyphen), but the
    frontend pattern only allowed [a-zA-Z0-9_]+ -- an admin creating a
    username with a hyphen (which the backend explicitly permits) was
    silently blocked by browser-native validation before the request was
    ever sent.

    Discovered live while fixing this: naively adding an unescaped
    trailing hyphen ([a-zA-Z0-9_-]+) is valid traditional regex but
    Chrome's HTMLInputElement pattern validation (native `v`-flag/unicode-
    sets regex mode) rejects it with 'Invalid character in character
    class', breaking checkValidity() entirely and passing native
    validation checks vacuously true for a form that would otherwise
    never submit. Must escape it: [a-zA-Z0-9_\\-]+."""
    html = TEMPLATE.read_text(encoding="utf-8")
    assert 'pattern="[a-zA-Z0-9_\\-]+"' in html
    assert 'pattern="[a-zA-Z0-9_-]+"' not in html

    node = shutil.which("node")
    if not node:
        pytest.skip("node not available to verify pattern validity")
    # Reproduce the exact browser-native validation path: HTMLInputElement's
    # pattern attribute is compiled as new RegExp(`^(?:${pattern})$`, 'v')
    # in modern Chromium -- confirm it does NOT throw.
    script = (
        "new RegExp('^(?:[a-zA-Z0-9_\\\\-]+)$', 'v'); "
        "console.log('OK');"
    )
    result = subprocess.run(
        [node, "-e", script], capture_output=True, text=True, encoding="utf-8"
    )
    assert result.returncode == 0, f"pattern is invalid under v-flag regex: {result.stderr}"


def test_username_help_text_mentions_hyphen():
    html = TEMPLATE.read_text(encoding="utf-8")
    assert "underscores, and hyphens only" in html
    assert "وشرطة سفلية وشرطة فقط" in html


def test_username_has_client_side_max_length_matching_backend():
    """Backend: Field(..., min_length=3, max_length=50)."""
    html = TEMPLATE.read_text(encoding="utf-8")
    assert 'maxlength="50"' in html


def test_submit_error_handler_surfaces_real_backend_message():
    """Relies on the fetchWithAuth fix (auth.js) to populate error.message
    with the real backend detail instead of a generic HTTP reason phrase --
    verified live: duplicate-username submission on this page returns
    {"error":{"message":"Username already exists",...}} and the toast now
    shows that exact text instead of "Conflict"."""
    html = TEMPLATE.read_text(encoding="utf-8")
    assert "showToast(error.message ||" in html
