"""Every custom property the Charts Explorer's CSS relies on must actually be
defined in a stylesheet the page loads.

The page's inline CSS referenced --font-ar, --az-primary*, --slate-* and --r-*
115 times, but those were defined only in admin_analytics_v2.css -- a page
stylesheet that /admin/analytics loads and /admin/analytics/charts does not.
An unresolvable var() makes the whole declaration invalid at computed-value
time, so all 115 were silently dropped in the browser:

  authored .ce-kpi-strip__label  font: 600 0.625rem/1.2 var(--font-ar)
  computed                       16px          (inherited -- rule dropped)

  authored :focus-visible        outline: 2px solid var(--az-primary)
  computed                       outline-style: none   (no visible focus)

Both were confirmed on production with a real browser before the fix.

The page's own --ce-* source palette is deliberately scoped to
#chartsExplorerRoot/.ce-hero and resolved correctly throughout -- it is
excluded here rather than "fixed", because scoping it is the right design.
"""
import re
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
TEMPLATE = ROOT / "templates" / "admin" / "analytics" / "charts_dashboard.html"
ADMIN_BASE = ROOT / "templates" / "admin_base.html"
CSS_DIR = ROOT / "static" / "css"

# Scoped to the page's own root/hero; verified resolving in-browser.
PAGE_SCOPED = {"--ce-rose", "--ce-saffron", "--ce-olive", "--ce-teal",
               "--ce-plum", "--ce-ink", "--ce-sand"}
# Provided by Bootstrap at runtime, and every use carries a fallback.
VENDOR = {"--bs-body-bg", "--bs-border-color"}


def _inline_css() -> str:
    return re.search(r"<style[^>]*>(.*?)</style>", TEMPLATE.read_text(encoding="utf-8"), re.S).group(1)


def _shell_stylesheets():
    """The stylesheets admin_base.html actually links, in load order."""
    base = ADMIN_BASE.read_text(encoding="utf-8")
    return [CSS_DIR / n for n in re.findall(r'href="/static/css/([a-z0-9_.-]+\.css)', base)]


def _defined_by_shell():
    names = set()
    for path in _shell_stylesheets():
        if path.exists():
            names |= set(re.findall(r"^\s*(--[a-zA-Z0-9-]+)\s*:", path.read_text(encoding="utf-8"), re.M))
    return names


def _defined_in_page():
    return set(re.findall(r"^\s*(--[a-zA-Z0-9-]+)\s*:", _inline_css(), re.M))


def _uses_with_fallback(css):
    """var(--x, fallback) survives even when --x is undefined."""
    return {m.group(1) for m in re.finditer(r"var\(\s*(--[a-zA-Z0-9-]+)\s*,", css)}


def test_every_referenced_token_resolves():
    css = _inline_css()
    referenced = set(re.findall(r"var\(\s*(--[a-zA-Z0-9-]+)", css))
    assert referenced, "expected the page to reference custom properties"

    available = _defined_by_shell() | _defined_in_page() | PAGE_SCOPED | VENDOR | _uses_with_fallback(css)
    missing = sorted(referenced - available)
    assert not missing, (
        "these custom properties are referenced by the Charts Explorer but "
        f"defined in no stylesheet it loads, so every declaration using them "
        f"is dropped at computed-value time: {missing}"
    )


@pytest.mark.parametrize("token", [
    "--font-ar", "--az-primary", "--az-danger",
    "--slate-50", "--slate-200", "--slate-800",
    "--r-sm", "--r-md", "--r-lg", "--r-full",
])
def test_shared_tokens_live_in_a_shell_stylesheet(token):
    """They must come from a sheet every admin page loads, not from a page
    stylesheet only one other surface happens to link."""
    assert token in _defined_by_shell(), (
        f"{token} is not defined by any stylesheet admin_base.html loads"
    )


def test_focus_ring_token_is_resolvable():
    """The specific declaration that left keyboard users with no focus ring."""
    css = _inline_css()
    focus_rules = re.findall(r":focus-visible[^{]*\{([^}]*)\}", css)
    assert focus_rules, "expected a :focus-visible rule on this page"
    outlines = [b for b in focus_rules if "outline" in b]
    assert outlines, "no :focus-visible rule sets an outline"
    available = _defined_by_shell() | _defined_in_page() | PAGE_SCOPED | VENDOR
    for body in outlines:
        for tok in re.findall(r"var\(\s*(--[a-zA-Z0-9-]+)\s*\)", body):
            assert tok in available, (
                f"the focus outline depends on {tok}, which does not resolve; "
                "the declaration is dropped and focus becomes invisible"
            )


def test_detector_catches_a_missing_token():
    """Control: the resolver must report a token that genuinely is absent, so
    this contract cannot rot into a test that always passes."""
    css = _inline_css()
    available = _defined_by_shell() | _defined_in_page() | PAGE_SCOPED | VENDOR
    assert "--definitely-not-defined-anywhere" not in available
