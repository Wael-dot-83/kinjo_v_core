"""Budgets that stop design-system drift from growing back.

An audit is a snapshot; a budget is a ratchet. Every number below was measured
at the time of writing and may only go DOWN. Adding a hardcoded colour, a new
font size, or another Arabic literal in markup fails here with the current and
allowed counts, so the drift is refused at the point it is introduced rather
than rediscovered in the next audit.

Lowering a budget after cleanup is expected and encouraged. Raising one needs a
reason in the commit message.
"""

from __future__ import annotations

import json
import re
from collections import Counter
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
CSS_DIR = ROOT / "static" / "css"
JS_DIR = ROOT / "static" / "js"
TPL_DIR = ROOT / "templates"

# The file that DEFINES the tokens is where literals are supposed to live.
TOKEN_FILE = "design-tokens.css"

HEX = re.compile(r"#[0-9a-fA-F]{3,8}\b")
COMMENT_CSS = re.compile(r"/\*.*?\*/", re.S)
COMMENT_HTML = re.compile(r"<!--.*?-->", re.S)


def _css_sources() -> list[tuple[str, str]]:
    out = []
    for p in sorted(CSS_DIR.glob("*.css")):
        if p.name == TOKEN_FILE:
            continue
        out.append((str(p.relative_to(ROOT)), COMMENT_CSS.sub("", p.read_text(encoding="utf-8", errors="replace"))))
    return out


def _template_sources() -> list[tuple[str, str]]:
    return [
        (str(p.relative_to(ROOT)), COMMENT_HTML.sub("", p.read_text(encoding="utf-8", errors="replace")))
        for p in sorted(TPL_DIR.rglob("*.html"))
    ]


# ---------------------------------------------------------------------------
# Colour
# ---------------------------------------------------------------------------

# Measured 2026-08-18 after the exact-value token migration.
MAX_HEX_IN_CSS = 1846
MAX_HEX_IN_TEMPLATES = 1037


def test_stylesheets_do_not_grow_more_hardcoded_colours():
    total = sum(len(HEX.findall(src)) for _, src in _css_sources())
    assert total <= MAX_HEX_IN_CSS, (
        f"static/css now holds {total} hardcoded hex colours, budget is {MAX_HEX_IN_CSS}. "
        f"Use a var(--kinjo-*) token from {TOKEN_FILE} instead of a literal, or lower the "
        f"budget in this test if you removed some."
    )


def test_templates_do_not_grow_more_hardcoded_colours():
    total = sum(len(HEX.findall(src)) for _, src in _template_sources())
    assert total <= MAX_HEX_IN_TEMPLATES, (
        f"templates/ now hold {total} hardcoded hex colours, budget is {MAX_HEX_IN_TEMPLATES}."
    )


@pytest.mark.parametrize(
    "literal, token",
    [
        ("#1F5E47", "--kinjo-brand"),
        ("#1E40AF", "--kinjo-action"),
        ("#1E3A8A", "--kinjo-action-hover"),
        ("#2563eb", "--kinjo-action"),
        ("#005ea8", "--kinjo-action"),
    ],
)
def test_consolidated_brand_colours_are_not_reintroduced_in_stylesheets(literal, token):
    """design-tokens.css says four competing primaries were unified: 'Do not add a fifth.'

    These are the exact literals that unification replaced. A stylesheet writing
    one of them by hand is re-forking the palette.
    """
    offenders = [name for name, src in _css_sources() if re.search(re.escape(literal), src, re.I)]
    assert not offenders, (
        f"{literal} is written literally in {offenders}. Use var({token}); "
        f"see the brand-vs-action note at the top of {TOKEN_FILE}."
    )


# ---------------------------------------------------------------------------
# Type scale
# ---------------------------------------------------------------------------

FONT_SIZE = re.compile(r"font-size\s*:\s*([0-9.]+)(px|rem|em)", re.I)

# 7 tokens are defined; 104 distinct values were in use when this was written.
MAX_DISTINCT_FONT_SIZES = 104


def test_font_size_scale_does_not_fragment_further():
    seen: Counter[str] = Counter()
    for _, src in _css_sources() + _template_sources():
        for num, unit in FONT_SIZE.findall(src):
            # .8rem and 0.8rem are the same size written two ways; normalise so
            # the count reflects rendered sizes, not spellings.
            seen[f"{float(num):g}{unit.lower()}"] += 1
    assert len(seen) <= MAX_DISTINCT_FONT_SIZES, (
        f"{len(seen)} distinct font sizes are now in use, budget is {MAX_DISTINCT_FONT_SIZES}. "
        f"Reach for a --kinjo-font-size-* token rather than a new value."
    )


# Icon-font sizing is exempt. `bi-circle-fill` at 0.4rem is a status dot, not
# text, and enlarging it to a text floor would just make the dot wrong. The rule
# below therefore skips any declaration whose selector or element is an icon.
ICON_CONTEXT = re.compile(r"(\.bi\b|bi-[a-z-]+|\bi\s*\{|<i\b|material-symbols|\bicon\b)", re.I)

# Text below 10px is illegible in Arabic and was fixed. The 10-12px band is
# known debt: 12px is the floor Arabic really wants, and this budget walks the
# remaining declarations down rather than pretending they are already gone.
MAX_TEXT_UNDER_12PX = 73


def _small_text_declarations() -> list[str]:
    """Font sizes under 12px that are not icon glyphs."""
    found = []
    for name, src in _css_sources() + _template_sources():
        for m in FONT_SIZE.finditer(src):
            value, unit = float(m.group(1)), m.group(2).lower()
            rem = value / 16 if unit == "px" else value
            if rem >= 0.75:
                continue
            # Look back far enough to catch the selector or the opening tag.
            context = src[max(0, m.start() - 220): m.start()]
            if ICON_CONTEXT.search(context):
                continue
            found.append(f"{name}: {m.group(1)}{unit}")
    return found


def test_no_arabic_text_is_rendered_below_ten_pixels():
    """Arabic is the default language, and it needs more room than Latin.

    Arabic has no x-height/cap-height distinction to fall back on, and the marks
    that distinguish its letterforms are the first thing to disappear as the
    size drops. Text that is merely small in English is unreadable in Arabic.
    Below 10px there is no defensible case.
    """
    offenders = []
    for decl in _small_text_declarations():
        value = float(re.search(r"([0-9.]+)", decl.split(":")[-1]).group(1))
        unit = "px" if decl.rstrip().endswith("px") else "rem"
        px = value if unit == "px" else value * 16
        if px < 10:
            offenders.append(decl)
    assert not offenders, (
        "Arabic text below 10px is not readable: " + ", ".join(sorted(set(offenders)))
    )


def test_small_text_debt_only_shrinks():
    """The 10-12px band, ratcheted. 12px is the real Arabic floor."""
    found = _small_text_declarations()
    assert len(found) <= MAX_TEXT_UNDER_12PX, (
        f"{len(found)} text declarations sit below the 12px Arabic floor, budget is "
        f"{MAX_TEXT_UNDER_12PX}. Prefer var(--kinjo-font-size-xs) (0.75rem)."
    )


# ---------------------------------------------------------------------------
# Bilingual debt
# ---------------------------------------------------------------------------

OVERRIDES = ROOT / "static" / "i18n" / "literal_en_overrides.json"

# Arabic literals hardcoded in markup, translated at runtime by a DOM TreeWalker.
# This is a migration backlog, not a feature. It may only shrink.
MAX_LITERAL_OVERRIDES = 1472


def test_runtime_arabic_literal_overrides_only_shrink():
    data = json.loads(OVERRIDES.read_text(encoding="utf-8"))
    assert len(data) <= MAX_LITERAL_OVERRIDES, (
        f"literal_en_overrides.json now holds {len(data)} entries, budget is "
        f"{MAX_LITERAL_OVERRIDES}. New user-facing strings belong in "
        f"static/i18n/admin_ar.json + admin_en.json with a real key, not as an "
        f"Arabic literal in markup patched at runtime. CLAUDE.md: 'Do not hardcode "
        f"Arabic-only strings.'"
    )


def test_structured_catalogues_stay_in_parity():
    """The sanctioned path must not itself drift while the backlog is worked down."""
    ar = json.loads((ROOT / "static" / "i18n" / "admin_ar.json").read_text(encoding="utf-8"))
    en = json.loads((ROOT / "static" / "i18n" / "admin_en.json").read_text(encoding="utf-8"))

    def flat(o, p=""):
        for k, v in o.items():
            if isinstance(v, dict):
                yield from flat(v, f"{p}{k}.")
            else:
                yield f"{p}{k}"

    assert set(flat(ar)) == set(flat(en))


# ---------------------------------------------------------------------------
# Page weight
# ---------------------------------------------------------------------------

INLINE_SCRIPT = re.compile(r"<script\b(?![^>]*\bsrc=)[^>]*>(.*?)</script>", re.S | re.I)

# Inline script cannot be cached. The project versions static assets with ?v=
# content hashes and serves them with a long max-age; bytes inlined into a
# template get none of that and are re-downloaded on every page view.
MAX_INLINE_SCRIPT_KB = 962


def test_inline_script_weight_does_not_grow():
    total = sum(
        sum(len(m) for m in INLINE_SCRIPT.findall(src))
        for _, src in _template_sources()
    )
    kb = total / 1024
    assert kb <= MAX_INLINE_SCRIPT_KB, (
        f"templates carry {kb:.0f} KB of inline <script>, budget is {MAX_INLINE_SCRIPT_KB} KB. "
        f"Move it to a file under static/js and reference it with a ?v= content hash so it caches."
    )
