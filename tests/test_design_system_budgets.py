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

import hashlib
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
#
# Raised from 1846 to 1859 when the multi-role AI assistant landed (c65cb79 and
# its predecessors). chatbot.css introduces a Navy/Gold palette --
# #002f6c "KinJo Navy" and #c5a059 "Soft Gold" -- which is a fifth and sixth
# brand colour in a product whose token file says in as many words: "Do not add
# a fifth." That is a design decision for whoever owns the assistant, not
# something to silently rewrite from here, so the budget records it rather than
# hiding it. If the assistant adopts the existing palette, drop this back.
MAX_HEX_IN_CSS = 1859
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
# Raised 962 -> 963 for the render failsafe in admin_base.html and
# manager_base.html. Both shells hide <html> until script clears it, and the
# reveal used to sit at the end of a long IIFE: one throw or parse error and
# the whole panel rendered blank, with the <noscript> fallback inert because
# scripting was enabled. The guard costs ~340 bytes across the two shells.
#
# It is deliberately exempt from this budget's own remediation advice. Moving
# it to a file under static/js would reintroduce the failure it exists to
# prevent: an external script that fails to fetch or parse never runs, and the
# page stays hidden. A failsafe cannot depend on the thing it is insuring.
# Raised 963 -> 964 for the text-safe status palettes on the KPI pages. Those
# pages render status words with a colour chosen in JS, and the fill palette
# they used measured 2.15-3.76:1 as text. The accessible parallel palette has
# to live beside the logic that picks it; moving it to a cached file would
# separate the two halves of one decision for ~1 KB.
MAX_INLINE_SCRIPT_KB = 964


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


# ---------------------------------------------------------------------------
# Cache keys
# ---------------------------------------------------------------------------

_ASSET_REF = re.compile(r"/static/((?:css|js)/[^\"?']+)\?v=([A-Za-z0-9._-]+)")


def _asset_references() -> dict[str, set[tuple[str, str]]]:
    refs: dict[str, set[tuple[str, str]]] = {}
    for tpl in TPL_DIR.rglob("*.html"):
        for m in _ASSET_REF.finditer(tpl.read_text(encoding="utf-8", errors="replace")):
            refs.setdefault(m.group(1), set()).add((m.group(2), str(tpl.relative_to(ROOT))))
    return refs


def test_one_cache_key_per_asset():
    """The same file must not be requested under two different ?v= values.

    Static assets are served with a long max-age, so two keys for one file means
    two cached copies: a user who loads page A and then page B can be running
    last month's JavaScript against this month's markup, with nothing in the UI
    to indicate it. agency_reports.css was referenced as v=3.2, v=3.4 and v=3.5
    from three templates; chatbot.css and chatbot.js each carried two.
    """
    split = {
        asset: sorted(pairs)
        for asset, pairs in _asset_references().items()
        if len({v for v, _ in pairs}) > 1
    }
    assert not split, "assets referenced under more than one cache key: " + repr(split)


def canonical_asset_hash(path):
    """The release identity of a static asset: sha256 of its COMMITTED bytes.

    Every blob in static/ is stored LF, and this repo is checked out with
    core.autocrlf=true on Windows, so the working tree carries CRLF while the
    commit does not. Hashing the raw working-tree bytes therefore produced a
    different answer on a Windows clone than on a Linux one for identical
    committed content -- the defect fix/platform-independent-cache-keys
    (cac8d1a) is about.

    Normalising CRLF to LF reproduces the committed blob byte-for-byte for all
    73 versioned assets (verified), so this is the canonical identity without
    the test needing to shell out to git.
    """
    return hashlib.sha256(
        path.read_bytes().replace(bytes([13, 10]), bytes([10]))
    ).hexdigest()[:12]


def test_asset_hash_is_independent_of_checkout_line_endings(tmp_path):
    """Control: identical committed content must yield one identity.

    Simulates the same blob checked out with core.autocrlf=true (CRLF) and
    false (LF). A hash that disagrees between them cannot be a release
    identity, which is exactly how this went wrong before."""
    import hashlib as _h
    content = bytes([10]).join([b"a{color:#fff}", b"b{color:#000}", b""])
    lf = tmp_path / "lf.css"; lf.write_bytes(content)
    crlf = tmp_path / "crlf.css"; crlf.write_bytes(content.replace(bytes([10]), bytes([13, 10])))
    assert lf.read_bytes() != crlf.read_bytes(), 'fixture must actually differ on disk'
    assert canonical_asset_hash(lf) == canonical_asset_hash(crlf)
    # and it must equal the committed (LF) content's hash
    assert canonical_asset_hash(lf) == _h.sha256(content).hexdigest()[:12]


def test_content_hash_cache_keys_match_the_file():
    """A ?v=<12 hex> key is a content hash and must match the bytes on disk.

    A stale hash is worse than a version string: it looks precise while pinning
    returning users to superseded bytes for as long as the max-age lasts.
    """
    import hashlib

    stale = []
    for asset, pairs in _asset_references().items():
        path = ROOT / "static" / asset
        if not path.exists():
            continue
        actual = canonical_asset_hash(path)
        for version, tpl in pairs:
            if re.fullmatch(r"[0-9a-f]{12}", version) and version != actual:
                stale.append(f"{asset} in {tpl}: references {version}, content is {actual}")
    assert not stale, "stale content-hash cache keys: " + "; ".join(sorted(stale))
