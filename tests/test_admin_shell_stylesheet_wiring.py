"""The admin shell's stylesheet graph: direction and theme are independent axes.

dark-mode.css used to be nested inside `{% if ui_dir == 'rtl' %}` alongside
rtl.css, so the entire English admin had no dark theme. Observed in a browser
against production before this fix: with kinjo_lang=en and
prefers-color-scheme:dark the media query matched, but the stylesheet was never
requested and body stayed rgb(250,249,246); the identical run in Arabic went
rgb(11,18,32).

These assertions are structural -- against admin_base.html rather than a
rendered response -- on purpose. The TestClient cannot drive ui_dir: setting
the kinjo_lang cookie to "en" still renders dir="rtl" in this harness, so an
HTTP-level "rtl.css must be absent in English" test would never exercise the
LTR branch and would pass vacuously. The structural form encodes the same
guarantee and actually fails when the fix is reverted. Real LTR/dark rendering
is verified in the browser instead.
"""
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
ADMIN_BASE = ROOT / "templates" / "admin_base.html"

RTL_LINK = re.compile(r'<link[^>]*href="[^"]*\brtl\.css(?:\?[^"]*)?"[^>]*>')
DARK_LINK = re.compile(r'<link[^>]*href="[^"]*\bdark-mode\.css(?:\?[^"]*)?"[^>]*>')
RTL_BRANCH = re.compile(r"{%\s*if ui_dir == 'rtl'\s*%}(.*?){%\s*endif\s*%}", re.S)


def _html():
    return ADMIN_BASE.read_text(encoding="utf-8")


def test_theme_sheet_is_linked_exactly_once():
    links = DARK_LINK.findall(_html())
    assert links, "dark-mode.css is not linked at all"
    assert len(links) == 1, f"dark-mode.css linked {len(links)} times: {links}"


def test_theme_sheet_is_not_gated_on_direction():
    """The regression: a theme sheet must not live in a direction branch."""
    html = _html()
    branches = RTL_BRANCH.findall(html)
    assert branches, "expected an `ui_dir == 'rtl'` branch in admin_base.html"
    for body in branches:
        assert "dark-mode.css" not in body, (
            "dark-mode.css is inside an `ui_dir == 'rtl'` branch again -- the "
            "English admin loses its dark theme entirely when it is"
        )


def test_direction_sheet_stays_gated_on_direction():
    """rtl.css genuinely is direction-specific and must not be un-gated with
    the theme sheet."""
    html = _html()
    links = RTL_LINK.findall(html)
    assert len(links) == 1, f"rtl.css should be linked once, got {links}"
    inside = any("rtl.css" in body for body in RTL_BRANCH.findall(html))
    assert inside, "rtl.css must stay inside the `ui_dir == 'rtl'` branch"


def test_matchers_still_detect_the_defect():
    """Control: the matchers must react to the shapes they exist to catch, so
    relaxing them later cannot silently disarm the tests above."""
    reverted = """{% if ui_dir == 'rtl' %}
      <link rel="stylesheet" href="/static/css/rtl.css?v=1.1" />
      <link rel="stylesheet" href="/static/css/dark-mode.css?v=1.0" />
      {% endif %}"""
    assert any("dark-mode.css" in b for b in RTL_BRANCH.findall(reverted)), (
        "the branch matcher no longer detects a gated dark-mode.css"
    )
    assert DARK_LINK.findall(reverted), "the dark-mode matcher stopped matching"
    assert DARK_LINK.findall('<link href="/static/css/dark-mode.css" />')
    assert not DARK_LINK.findall('<link href="/static/css/kinjo.css?v=2" />')
