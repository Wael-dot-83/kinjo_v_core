"""Arabic text must render with normal tracking. Enforced, not documented.

Arabic is a cursive script and CSS Text directs a UA not to insert spacing
where that would sever a cursive connection. Arabic is this product's default
language, so how tracking behaves on it is a primary-surface question.

Whether tracking breaks those joins depends on the engine, which is exactly why
this is an invariant and not a judgement call. Measured at 32px with 4px
tracking on the string "الحضانة":

    chromium   +0.00px      suppressed inside the cursive run
    firefox    +0.00px      suppressed
    webkit    +28.00px      applied -- the joins come apart

So on Safari and every browser on iOS this was a real rendering defect. On
Blink and Gecko the same declaration is inert inside words while still landing
on word gaps and on Latin embedded in Arabic, which is unwanted on its own.
Measuring only Chromium produced a confident wrong answer here once already;
the rule is engine-independent so the outcome does not depend on which one
someone happens to test in.

It also exists because the conformance detector reports this repository clean.
`wide-tracking` and `extreme-negative-tracking` are calibrated for Latin, and
the 25 rules that put tracking on 142 Arabic nodes all sat below their
thresholds. A clean scan is scoped to the rules someone wrote.

So the gate has to be script-aware, and it has to be falsifiable. Three cases:

    Arabic text + non-normal tracking  -> FAIL
    Arabic text + normal tracking      -> pass
    Latin-only text + tracking         -> still permitted

The third matters as much as the first. A gate that simply banned tracking
everywhere would pass this file while wrecking the English UI, and nobody would
notice until a designer complained.

Siblings, same shape of lesson:
  * tests/test_conformance_zero_is_real.py -- a zero that cannot be falsified
  * tests/test_conformance_instrument.py   -- a detector that degrades silently
  * tests/test_browser_audit_contract.py   -- an audit that measured the wrong page
"""
import re
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
CSS = ROOT / "static" / "css" / "kinjo.css"

ARABIC = re.compile(r"[؀-ۿ]")

# The invariant, as it must appear in the shipped stylesheet.
GUARD_SELECTOR = '[dir="rtl"] *:not([lang="en"])'


def test_the_rtl_tracking_guard_is_present_in_the_shipped_stylesheet():
    """Static half: the rule exists, is scoped to RTL, and keeps its escapes.

    Cheap, runs everywhere, and catches the most likely regression -- somebody
    deleting the rule while tidying the stylesheet.
    """
    assert CSS.is_file(), f"{CSS} is missing"
    css = CSS.read_text(encoding="utf-8")

    assert GUARD_SELECTOR in css, (
        "the RTL tracking guard is gone from kinjo.css. Without it, tracking "
        "reaches Arabic text again -- uneven word gaps, tracked Latin fragments "
        "inside Arabic sentences, and a declaration whose effect depends on "
        "engine behaviour this project has only verified in Chromium. "
        "25 rules were putting tracking on Arabic when the guard was written."
    )
    guard = css[css.index(GUARD_SELECTOR):]
    guard = guard[:guard.index("}") + 1]

    assert "letter-spacing" in guard and "normal" in guard, (
        "the guard no longer sets letter-spacing: normal"
    )
    assert "!important" in guard, (
        "the guard lost its !important. Two rules in this codebase declare "
        "tracking !important themselves (.sidebar-section-title, .kpi-value), "
        "so a guard without it loses the cascade and silently does nothing."
    )
    for escape in ('[lang="en"]', ".allow-tracking"):
        assert escape in guard, (
            f"the guard lost its {escape} escape. The rule has to stay "
            "overridable for genuinely Latin content, or it will be worked "
            "around with something worse."
        )


def test_the_guard_is_scoped_to_rtl_and_leaves_the_english_ui_alone():
    """Control: the fix must not be a blanket ban on tracking.

    A guard that applied in both directions would satisfy the Arabic assertion
    while destroying intentional Latin tracking. Pinning the RTL scope makes
    that regression visible here instead of in the English UI.
    """
    css = CSS.read_text(encoding="utf-8")
    guard_line = next(
        line for line in css.splitlines() if GUARD_SELECTOR in line
    )
    assert guard_line.strip().startswith('[dir="rtl"]'), (
        "the tracking guard is no longer scoped to [dir=rtl], so it now applies "
        "to the English UI too and removes tracking that is there on purpose: "
        f"{guard_line.strip()!r}"
    )


# --------------------------------------------------------------------------
# The browser half. Skipped unless a server is running, because it is the only
# way to know what actually rendered -- but when it runs it is the real gate.
# --------------------------------------------------------------------------

PROBE_JS = r"""() => {
  const AR = /[؀-ۿ]/;
  const out = [];
  document.querySelectorAll('*').forEach(el => {
    const t = [...el.childNodes].filter(n => n.nodeType === 3)
                .map(n => n.nodeValue.trim()).join('');
    if (!t || !AR.test(t)) return;
    const cs = getComputedStyle(el);
    if (cs.display === 'none' || cs.visibility === 'hidden') return;
    const r = el.getBoundingClientRect();
    if (r.width < 1 || r.height < 1) return;
    const ls = cs.letterSpacing;
    if (!ls || ls === 'normal' || parseFloat(ls) === 0) return;
    out.push({
      ls,
      size: cs.fontSize,
      tag: el.tagName.toLowerCase(),
      cls: String(el.className || '').slice(0, 40),
      text: t.slice(0, 24),
    });
  });
  return out;
}"""

# A page that violates the invariant on purpose, to prove the probe can see it.
CONTROL_HTML = """<!doctype html>
<html lang="ar" dir="rtl"><head><style>
  .bad { letter-spacing: 0.08em; font-size: 14px; }
  .fine { font-size: 14px; }
  .latin { letter-spacing: 0.12em; font-size: 14px; }
</style></head><body>
  <div class="bad">حروف عربية متباعدة</div>
  <div class="fine">حروف عربية سليمة</div>
  <div class="latin" lang="en">TRACKED LATIN LABEL</div>
</body></html>"""


def _page(pw):
    b = pw.chromium.launch()
    ctx = b.new_context(locale="ar-JO", viewport={"width": 1440, "height": 950})
    return b, ctx


def test_probe_detects_arabic_tracking_and_permits_latin_tracking():
    """The synthetic control. Runs with no server -- it uses a data: URL.

    Without this, `zero Arabic nodes with tracking` is unfalsifiable: a probe
    that silently matched nothing would produce the same clean result as a
    correctly styled page.
    """
    pw = pytest.importorskip("playwright.sync_api")
    with pw.sync_playwright() as p:
        b, ctx = _page(p)
        try:
            pg = ctx.new_page()
            pg.set_content(CONTROL_HTML)
            hits = pg.evaluate(PROBE_JS)
        finally:
            b.close()

    texts = {h["text"] for h in hits}
    assert any("متباعدة" in t for t in texts), (
        "the probe did not flag Arabic text carrying 0.08em tracking, so it "
        "cannot detect the defect it exists to prevent. A clean result from "
        "this probe means nothing while this assertion fails."
    )
    assert not any("سليمة" in t for t in texts), (
        "the probe flagged correctly-set Arabic text -- it is reporting false "
        "positives and would force real rules to be weakened"
    )
    assert not any("LATIN" in t for t in texts), (
        "the probe flagged a lang=\"en\" element. Latin tracking is legitimate "
        "and must stay permitted; a gate that bans it will be worked around."
    )


@pytest.mark.parametrize("route", [
    "/", "/login", "/register", "/forgot-password", "/services",
])
def test_no_arabic_tracking_on_public_routes(route):
    """The real assertion, on the surfaces reachable without an account.

    Authenticated routes are covered by the same probe in the release sweep;
    they need seeded credentials, which do not belong in the unit suite.
    """
    pw = pytest.importorskip("playwright.sync_api")
    import urllib.error
    import urllib.request

    base = "http://127.0.0.1:8096"
    try:
        urllib.request.urlopen(base + "/login", timeout=3)
    except (urllib.error.URLError, OSError):
        pytest.skip("no dev server on 127.0.0.1:8096")

    with pw.sync_playwright() as p:
        b, ctx = _page(p)
        try:
            ctx.add_cookies([{"name": "kinjo_lang", "value": "ar", "url": base}])
            pg = ctx.new_page()
            pg.goto(base + route, wait_until="networkidle")
            pg.evaluate("document.fonts.ready")
            pg.wait_for_timeout(600)
            assert pg.evaluate("document.documentElement.dir") == "rtl", (
                f"{route} did not render RTL, so this measurement would not "
                "describe the Arabic surface"
            )
            hits = pg.evaluate(PROBE_JS)
        finally:
            b.close()

    if hits:
        detail = "\n".join(
            f"  {h['ls']:>9} at {h['size']:>6}  <{h['tag']} class={h['cls']!r}>  {h['text']!r}"
            for h in hits[:12]
        )
        pytest.fail(
            f"{len(hits)} Arabic text node(s) on {route} render with non-normal "
            f"letter-spacing, which breaks cursive joining:\n{detail}\n\n"
            "Fix the rule that sets it, or -- if the text is genuinely Latin -- "
            'mark it lang="en". Do not widen the guard.'
        )
