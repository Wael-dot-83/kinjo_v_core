"""Charts Explorer surfaces and text must adapt to the theme.

Un-gating dark-mode.css from RTL gave the English admin a dark theme for the
first time, which exposed a defect that had always been present in Arabic
dark: this page painted its cards, table and panels with unconditional #fff
while the shell's foreground went light -- white text on white surfaces.

Repairing the token graph made it worse before it made it better. Once
--slate-600/700/800 resolved, text bound to them became genuinely dark, so on
a now-dark card the KPI value rendered dark-on-dark and disappeared entirely.
Measured in the browser: the value was invisible until those colours were
bound to adaptive tokens.

Both halves are therefore contracts: adaptive surfaces must not be
unconditionally white, and text on them must not be pinned to a fixed dark
value. Scoped to the specific Charts Explorer selectors -- #fff is legitimate
elsewhere on this page (text on coloured buttons, the fixed-dark tooltip).
"""
import re
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
TEMPLATE = ROOT / "templates" / "admin" / "analytics" / "charts_dashboard.html"
DESIGN_SYSTEM = ROOT / "static" / "css" / "admin_design_system.css"

ADAPTIVE_SURFACES = [
    ".ce-kpi-strip__card",
    ".ce-source-card",
    ".ce-pinned-card",
    ".ce-rec-chip",
    ".ce-ct-btn",
    ".ce-glass-card",
]
BARE_WHITE = re.compile(r"background(?:-color)?:\s*(#fff(?:fff)?|white)\s*;", re.I)
FIXED_DARK_TEXT = re.compile(r"color:\s*var\(--slate-(?:600|700|800)\)\s*;")


def _page_css() -> str:
    return re.search(r"<style[^>]*>(.*?)</style>", TEMPLATE.read_text(encoding="utf-8"), re.S).group(1)


def _rule_bodies(css: str, selector: str):
    return [m.group(1) for m in
            re.finditer(re.escape(selector) + r"[^{]*\{([^}]*)\}", css)]


@pytest.mark.parametrize("selector", ADAPTIVE_SURFACES)
def test_adaptive_surface_is_not_unconditionally_white(selector):
    css = _page_css()
    bodies = _rule_bodies(css, selector)
    assert bodies, f"{selector} has no rule in the page CSS"
    for body in bodies:
        offending = BARE_WHITE.findall(body)
        assert not offending, (
            f"{selector} paints an unconditional white surface {offending}; on a "
            "dark shell that renders light text on a white card"
        )


def test_adaptive_surfaces_use_a_theme_token():
    """At least the KPI card and the data table must name a semantic surface."""
    css = _page_css()
    kpi = " ".join(_rule_bodies(css, ".ce-kpi-strip__card"))
    assert "var(--kinjo-color-bg-surface" in kpi, (
        "the KPI card must take its background from the shared surface token"
    )
    ds = DESIGN_SYSTEM.read_text(encoding="utf-8")
    table = " ".join(_rule_bodies(ds, ".ce-data-table"))
    assert "var(--kinjo-color-bg-surface" in table, (
        "the data table set no background at all and inherited Bootstrap's "
        "white, which stayed white against the dark shell"
    )


def test_charts_explorer_text_is_not_pinned_to_a_fixed_dark_value():
    """The second half: text on those now-adaptive surfaces must flip too."""
    for name, body in (("page", _page_css()),
                       ("design-system", DESIGN_SYSTEM.read_text(encoding="utf-8"))):
        sel = None
        for line in body.splitlines():
            s = line.strip()
            if s.endswith("{") and not s.startswith("@"):
                sel = s[:-1].strip()
            if sel and ".ce-" in sel and FIXED_DARK_TEXT.match(s):
                pytest.fail(
                    f"[{name}] {sel} pins text to a fixed dark slate value ({s}); "
                    "on a dark card this renders dark-on-dark and vanishes"
                )


def test_semantic_and_data_colours_are_left_alone():
    """Guard the opposite failure: this contract must not push the release
    into recolouring the source palette or the status colours."""
    css = _page_css()
    for token in ("--ce-rose", "--ce-saffron", "--ce-olive", "--ce-teal", "--ce-plum"):
        assert f"{token}:" in css, f"{token} definition was removed"
    assert "#16a34a" in css or "--ce-" in css  # delta-up semantic pair retained


def test_detectors_catch_the_defects_they_exist_for():
    """Non-vacuity control for both matchers."""
    assert BARE_WHITE.findall("background: #fff;")
    assert BARE_WHITE.findall("background-color: white;")
    assert not BARE_WHITE.findall("background: var(--kinjo-color-bg-surface, #fff);")
    assert FIXED_DARK_TEXT.match("color: var(--slate-800);")
    assert not FIXED_DARK_TEXT.match("color: var(--kinjo-color-text-primary, #1e293b);")
