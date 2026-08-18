"""Colour literals may not grow. New ones must go through design-tokens.css.

Why a ratchet and not a ban: there are 3,201 colour literals across 89 files.
A big-bang rewrite of that surface cannot be reviewed, cannot be visually
verified without a browser, and would collide with work in flight. A hard ban
would be switched off within a week. So the invariant is monotonic instead:
**a file may never carry more colour literals than its recorded baseline**, and
a file with no baseline entry must carry none.

That makes the drift one-directional. Every file that gets tokenised lowers its
number and can never silently climb back, and a brand-new stylesheet starts
clean with no negotiation.

What counts as a colour literal
-------------------------------
`#rgb`, `#rgba`, `#rrggbb` and `#rrggbbaa`, in either case. Everything else
beginning with `#` is deliberately excluded, because `#` is heavily overloaded
in this codebase and false positives are what get a gate disabled:

  * `url(#gradientId)`      SVG paint references
  * `href="#section"`       in-page anchors

An earlier version of this detector also stripped anything shaped like a CSS id
selector (`#name` after whitespace or a combinator). That was wrong, and the
controls below caught it: hex digits *are* letters, so the rule silently
swallowed `#fff`, `#bada55`, `#e2e8f0` and 549 other genuine colours. Validity
is now decided by the token alone -- exactly 3, 4, 6 or 8 hex digits and nothing
else -- which is both stricter and simpler. A real id selector that happened to
be valid hex would be a false positive; none exist in this tree.

Vendored code is out of scope -- it is not ours to tokenise:

  * static/vendor/**        Bootstrap, USWDS, Chart.js, Plotly and friends
  * static/js/tailwind.js   a vendored Tailwind build, 329 literals on its own

design-tokens.css is exempt because it is the sanctioned home for literals.
That is the whole point: values live there and nowhere else.

Lowering the baseline
---------------------
Tokenise, run this test, and it will tell you the new number to record. Do not
raise an entry. If a change genuinely requires a new colour, add it to
design-tokens.css as a semantic token and reference it -- that is the
remediation this gate exists to push people toward.
"""
import json
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
BASELINE_PATH = Path(__file__).resolve().parent / "color_literal_baseline.json"

_HEX = re.compile(r"#[0-9a-fA-F]{3,8}\b")

# `#` is overloaded; strip the non-colour uses before looking for colours.
_URL_REF = re.compile(r"url\(\s*#[^)]*\)")
_ANCHOR = re.compile(r"""href\s*=\s*["']#[^"']*["']""")

_VENDOR_PREFIXES = ("static/vendor/",)
_VENDOR_FILES = ("static/js/tailwind.js",)
# The one place colour literals belong.
_SANCTIONED = ("static/css/design-tokens.css",)


def _scrub(line):
    line = _URL_REF.sub("", line)
    line = _ANCHOR.sub("", line)
    return line


def find_literals(text):
    """[(line_no, literal)] for every colour literal in `text`."""
    found = []
    for n, line in enumerate(text.splitlines(), 1):
        for m in _HEX.finditer(_scrub(line)):
            token = m.group(0)
            if len(token) - 1 in (3, 4, 6, 8):
                found.append((n, token))
    return found


def _in_scope():
    for pattern in (ROOT / "static" / "css", ROOT / "templates", ROOT / "static" / "js"):
        suffix = {"css": "*.css", "templates": "*.html", "js": "*.js"}[pattern.name]
        for path in sorted(pattern.rglob(suffix)):
            rel = path.relative_to(ROOT).as_posix()
            if rel.startswith(_VENDOR_PREFIXES) or rel in _VENDOR_FILES:
                continue
            if rel in _SANCTIONED:
                continue
            yield rel, path


def _baseline():
    return json.loads(BASELINE_PATH.read_text(encoding="utf-8"))["files"]


def test_colour_literals_do_not_grow():
    baseline = _baseline()
    over, unlisted = [], []

    for rel, path in _in_scope():
        hits = find_literals(path.read_text(encoding="utf-8", errors="replace"))
        if not hits:
            continue
        allowed = baseline.get(rel)
        if allowed is None:
            first = ", ".join(f"line {n}: {v}" for n, v in hits[:3])
            unlisted.append(f"{rel}: {len(hits)} colour literal(s) -- {first}")
        elif len(hits) > allowed:
            # Name the ones past the budget so the failure is actionable.
            extra = hits[allowed:]
            shown = ", ".join(f"line {n}: {v}" for n, v in extra[:5])
            over.append(f"{rel}: {len(hits)} literals, budget {allowed} "
                        f"(+{len(hits) - allowed}) -- {shown}")

    problems = over + unlisted
    assert not problems, (
        "colour literals increased. Add the colour to static/css/design-tokens.css "
        "as a semantic token and reference it with var(), rather than inlining a "
        "hex value:\n  " + "\n  ".join(problems)
    )


def test_baseline_has_no_stale_entries():
    """A file that has been tokenised must have its budget lowered.

    Without this the ratchet leaks: a file could be cleaned up and its old,
    generous budget would sit there ready to absorb new literals silently.
    """
    baseline = _baseline()
    actual = {rel: len(find_literals(p.read_text(encoding="utf-8", errors="replace")))
              for rel, p in _in_scope()}
    stale = []
    for rel, allowed in sorted(baseline.items()):
        now = actual.get(rel, 0)
        if now < allowed:
            stale.append(f"{rel}: budget {allowed} but only {now} present "
                         f"-- lower it to {now}")
    assert not stale, (
        "these baseline entries are looser than the code needs; tighten them so "
        "the ratchet cannot slip backwards:\n  " + "\n  ".join(stale)
    )


# --------------------------------------------------------------------------
# Controls. A gate that cannot fail proves nothing, so these assert the
# detector's behaviour directly rather than trusting the tree to stay clean.
# --------------------------------------------------------------------------

def test_control_detects_every_forbidden_literal_form():
    css = """
    .a { color: #fff; }
    .b { color: #FFFF; }
    .c { color: #1e40af; }
    .d { color: #1E40AFCC; }
    """
    found = [v for _, v in find_literals(css)]
    assert found == ["#fff", "#FFFF", "#1e40af", "#1E40AFCC"], found


def test_control_ignores_the_non_colour_uses_of_hash():
    noise = """
    .icon { fill: url(#brandGradient); }
    #chartsExplorerRoot { display: block; }
    .x > #inner, #other ~ #sib { color: inherit; }
    <a href="#main-content">skip</a>
    """
    assert find_literals(noise) == [], find_literals(noise)


def test_control_does_not_swallow_colours_that_look_like_identifiers():
    """Regression control for this detector's own first bug.

    `#fff` and `#bada55` begin with letters, so an id-selector heuristic strips
    them. That silently hid 552 real literals, including the second most common
    colour value in the codebase.
    """
    css = ".a { color: #fff; } .b { background: #bada55; } .c { border: #e2e8f0; }"
    assert [v for _, v in find_literals(css)] == ["#fff", "#bada55", "#e2e8f0"]


def test_control_rejects_a_regression_introduced_into_a_real_file():
    """Simulate a developer inlining a hex value into an existing stylesheet.

    Uses a file that is actually in the baseline, so this exercises the real
    budget comparison and not just the regex.
    """
    baseline = _baseline()
    rel = "static/css/agency_reports.css"
    assert rel in baseline, "expected this file to carry a budget"

    original = (ROOT / rel).read_text(encoding="utf-8", errors="replace")
    budget = baseline[rel]
    assert len(find_literals(original)) <= budget

    regressed = original + "\n.newly-added { color: #bada55; }\n"
    hits = find_literals(regressed)
    assert len(hits) == budget + 1, (len(hits), budget)
    assert ("#bada55" in [v for _, v in hits])
