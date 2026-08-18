"""Every stylesheet a page loads must be able to resolve the tokens it uses.

Background: CSS custom properties are resolved at computed-value time, and a
declaration referencing an undefined property is *dropped silently*. The page
still returns 200 and still renders -- it just quietly loses whatever those
declarations were doing. Nothing in the UI says so, and no existing test
noticed.

This has now bitten the project twice:

  1. The Charts Explorer loaded a stylesheet whose tokens were defined only in
     a *different* page's stylesheet. 115 references resolved to nothing; the
     type scale collapsed to the inherited 16px and
     `outline: 2px solid var(--az-primary)` became `outline: none`, leaving
     keyboard users with no visible focus at all. design-tokens.css documents
     this in its own comments.

  2. base.html loaded kinjo.css but not design-tokens.css. Six tokens
     (--kinjo-brand, --kinjo-color-bg-body, --kinjo-color-border,
     --kinjo-color-border-subtle, --kinjo-color-text-muted,
     --kinjo-font-family-en) are defined only in design-tokens.css, so every
     declaration using them was dropped across **39 templates** -- the whole
     auth flow (login, register, forgot/reset password, MFA setup), the parent
     and supervisor modules, the public pages, 403/404 and the KPI dashboard.
     They lost component outlines, muted text colour and the Latin font stack.

     Worth recording how that number was arrived at: a hand audit of
     `grep -l 'extends "base.html"'` reported *four* templates, because it
     matched only the double-quoted form and was truncated by `head`. This
     gate, resolving the inheritance chain, reported thirty-nine. Hand-auditing
     a cascade is the thing that keeps failing here -- which is the argument
     for the gate.

Twice makes it a structural gap rather than an incident, so it gets a gate
rather than another point fix. The check is deliberately general: it does not
name base.html or design-tokens.css, it just asserts that whatever a document
loads is self-consistent.
"""
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
TEMPLATES = ROOT / "templates"
CSS_DIR = ROOT / "static" / "css"

# A <link> to a local stylesheet, cache-busting query stripped.
_CSS_LINK = re.compile(r"""href=["']/static/css/([^"'?]+)""")

# `--kinjo-foo:` at the start of a declaration -- i.e. a definition.
_DEFINES = re.compile(r"(?m)^\s*(--kinjo-[a-z0-9-]+)\s*:")

# `var(--kinjo-foo)` with no fallback. A call WITH a fallback still degrades
# gracefully, so it is not counted as a failure here.
_USES_NO_FALLBACK = re.compile(r"var\(\s*(--kinjo-[a-z0-9-]+)\s*\)")


_EXTENDS = re.compile(r"""{%-?\s*extends\s+["']([^"']+)["']""")


def _chain_text(path, _seen=None):
    """The template's own source plus every ancestor it extends.

    A child inherits its parent's <link> tags, so the set of stylesheets a
    rendered page actually loads is the union over the whole chain. Checking a
    child in isolation would report tokens the parent already supplies; checking
    only parents would miss a stylesheet the child adds.

    Note the chain must be followed rather than inferred from the presence of
    `<html`: templates/dashboard/index.html contains an `<html ...>` string
    inside a JS template literal that builds a print window, which makes a
    naive "is this a document?" test classify it as a root.
    """
    _seen = _seen or set()
    if path in _seen or not path.is_file():
        return ""
    _seen.add(path)
    text = path.read_text(encoding="utf-8", errors="replace")
    parent = _EXTENDS.search(text)
    if parent:
        text += _chain_text(TEMPLATES / parent.group(1), _seen)
    return text


def _rendered_documents():
    """Every template that results in a full page, with its inherited source."""
    for path in sorted(TEMPLATES.rglob("*.html")):
        text = _chain_text(path)
        # A real document either declares a doctype/<html> itself or inherits
        # one from an ancestor.
        if "<!doctype" in text.lower() or "<html" in text:
            yield path, text


def _css_text(name):
    path = CSS_DIR / name
    if not path.is_file():
        return ""
    return path.read_text(encoding="utf-8", errors="replace")


def test_every_document_can_resolve_the_kinjo_tokens_it_uses():
    offenders = []

    for path, html in _rendered_documents():
        sheets = []
        for name in _CSS_LINK.findall(html):
            if name not in sheets:
                sheets.append(name)
        if not sheets:
            continue

        defined = set()
        used = set()
        for name in sheets:
            css = _css_text(name)
            defined.update(_DEFINES.findall(css))
            used.update(_USES_NO_FALLBACK.findall(css))

        missing = sorted(used - defined)
        if missing:
            rel = path.relative_to(ROOT).as_posix()
            shown = ", ".join(missing[:6])
            if len(missing) > 6:
                shown += f", +{len(missing) - 6} more"
            offenders.append(f"{rel} loads {len(sheets)} stylesheet(s) but "
                             f"cannot resolve: {shown}")

    assert not offenders, (
        "these documents reference --kinjo-* tokens that none of the "
        "stylesheets they load define. Every such declaration is dropped at "
        "computed-value time and the page renders without it, silently:\n  "
        + "\n  ".join(offenders)
    )


def test_the_check_would_catch_a_missing_token_file():
    """Control: the gate above must be able to fail.

    A test that can only pass proves nothing. This re-runs the same logic
    against a document whose stylesheet uses a token nothing defines, and
    asserts the logic reports it.
    """
    defined = set(_DEFINES.findall("--kinjo-color-border: #064E32;"))
    used = set(_USES_NO_FALLBACK.findall(
        "a { border-color: var(--kinjo-color-border); "
        "color: var(--kinjo-color-text-muted); }"
    ))
    assert sorted(used - defined) == ["--kinjo-color-text-muted"]
