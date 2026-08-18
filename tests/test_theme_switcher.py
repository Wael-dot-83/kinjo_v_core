"""The appearance control must be reachable, bilingual, and flash-free.

dark-mode.css shipped for months with no way to turn it off -- its own header
said "if an in-app toggle is added" -- so a user whose OS was dark got dark
involuntarily. These pin the control that fixes that.
"""

import re

import pytest
from fastapi.testclient import TestClient

from main import app


@pytest.fixture()
def admin_client(admin_token):
    with TestClient(app, raise_server_exceptions=False) as c:
        c.cookies.set("kinjo_token", admin_token)
        yield c


def _shell(client) -> str:
    r = client.get("/admin/dashboard")
    assert r.status_code == 200, f"admin shell did not render ({r.status_code})"
    return r.text


def test_all_three_appearance_states_are_offered(admin_client):
    """System is the default and the only state that follows the OS."""
    html = _shell(admin_client)
    states = set(re.findall(r'data-kinjo-theme="(\w+)"', html))
    assert states == {"system", "light", "dark"}, f"got {states}"


def test_appearance_labels_are_rendered_not_hardcoded_in_javascript(admin_client):
    """Arabic is the default language, so the labels must come from the template.

    theme_switcher.js copies whichever label the user picked onto the trigger
    rather than carrying its own copy of the wording, which is what keeps the
    Arabic default from drifting away from a second English-only copy in JS.
    """
    html = _shell(admin_client)
    assert "النظام" in html and "فاتح" in html and "داكن" in html

    source = (__import__("pathlib").Path(__file__).resolve().parent.parent
              / "static" / "js" / "theme_switcher.js").read_text(encoding="utf-8")
    for arabic in ("النظام", "فاتح", "داكن"):
        assert arabic not in source, "user-facing wording must not live in JS"
    assert not re.search(r'"(System|Light|Dark)"', source)


def test_theme_is_applied_before_the_stylesheets_load(admin_client):
    """Applying the stored theme after paint is a worse flash than no toggle."""
    html = _shell(admin_client)
    assert "kinjo_theme" in html, "no theme bootstrap script"
    assert html.index("kinjo_theme") < html.index("admin_design_system.css"), (
        "the theme must be set before the first stylesheet, or the page paints "
        "in the OS theme and then repaints"
    )


def test_dark_mode_media_query_yields_to_an_explicit_light_choice():
    """A bare :root meant an in-app light choice lost to a dark OS."""
    css = (__import__("pathlib").Path(__file__).resolve().parent.parent
           / "static" / "css" / "dark-mode.css").read_text(encoding="utf-8")
    block = css.split("@media (prefers-color-scheme: dark)", 1)[1][:200]
    assert ':root:not([data-theme="light"])' in block
