"""The conformance scanner must fail closed, never quietly degrade.

Background, and the reason this file exists at all: the impeccable detector runs
in two modes. With its HTML/CSS parsers present it walks a real DOM and resolves
custom properties and selectors. Without them it falls back to regex matching
and says so:

    impeccable detect: DEGRADED - HTML parser modules unavailable
    (htmlparser2, css-select, css-tree, domutils). Falling back to regex
    matching. Custom properties, selector matching and computed contrast are
    NOT evaluated; findings are an undercount, not a clean bill of health.

On this repository the difference is not marginal:

    degraded   ->  60 findings
    full       -> 221 findings          a 3.7x undercount

A degraded run still exits successfully and still prints a number, so it looks
exactly like a smaller, better result. That is the failure mode: it does not
break, it flatters. The parsers had already vanished once between sessions --
they are installed with `npm install --no-save` into a gitignored node_modules,
so nothing in the repository holds them in place.

So instrument validity is a release invariant here, not a convenience. A
conformance claim measured in degraded mode is void regardless of what it says.

The companion lesson lives in tests/test_browser_audit_contract.py: a browser
audit that measured the login page six times and reported it as six
authenticated surfaces. Same shape of error -- the tool ran, produced numbers,
and the numbers described something other than what was claimed.
"""
import json
import subprocess
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]

# The parsers the detector needs before its findings mean anything.
REQUIRED_PARSERS = ("htmlparser2", "css-select", "css-tree", "domutils")

_PROBE = r"""
const fs = require('fs'), path = require('path');
const mods = %s;
const out = {};
for (const m of mods) {
  try {
    const entry = require.resolve(m);
    // Read the manifest off disk: modern packages publish an `exports` map that
    // blocks require('<pkg>/package.json'), so the obvious probe reports a
    // false MISSING for a package that is installed and working.
    let d = path.dirname(entry);
    while (!fs.existsSync(path.join(d, 'package.json'))) d = path.dirname(d);
    out[m] = JSON.parse(fs.readFileSync(path.join(d, 'package.json'), 'utf8')).version;
  } catch (e) {
    out[m] = null;
  }
}
console.log(JSON.stringify(out));
"""


def _skill_dir():
    """Locate the impeccable skill.

    `.claude/` is gitignored, so the skill is not present in a git worktree even
    though it is present in the primary checkout. Look in the checkout first,
    then honour IMPECCABLE_SKILL_DIR, then fall back to any sibling checkout
    that has it. Returns None when it genuinely cannot be found.
    """
    import os
    candidates = [ROOT / ".claude" / "skills" / "impeccable"]
    env = os.environ.get("IMPECCABLE_SKILL_DIR")
    if env:
        candidates.append(Path(env))
    # a worktree sits beside/below the checkout that owns the skill
    for parent in list(ROOT.parents)[:4]:
        candidates.append(parent / ".claude" / "skills" / "impeccable")
    for c in candidates:
        try:
            if c.is_dir() and (c / "scripts" / "detect.mjs").is_file():
                return c
        except OSError:
            continue
    return None


def parser_versions():
    """{module: version or None} as resolved from the skill's directory."""
    skill = _skill_dir()
    if skill is None:
        pytest.skip("impeccable skill not present in this checkout")
    probe = _PROBE % json.dumps(list(REQUIRED_PARSERS))
    try:
        r = subprocess.run(["node", "-e", probe], cwd=skill,
                           capture_output=True, text=True, timeout=120)
    except (FileNotFoundError, subprocess.TimeoutExpired):
        pytest.skip("node unavailable")
    if r.returncode != 0 or not r.stdout.strip():
        return {m: None for m in REQUIRED_PARSERS}
    return json.loads(r.stdout.strip().splitlines()[-1])


def test_conformance_scan_runs_at_full_fidelity():
    """Every required parser must resolve, or a conformance run is not valid.

    This is deliberately a hard failure rather than a skip. A skip would let the
    exact situation this guards against -- an absent parser -- pass quietly,
    which is how the 60-vs-221 undercount happened in the first place.
    """
    versions = parser_versions()
    missing = sorted(m for m, v in versions.items() if not v)
    assert not missing, (
        "the impeccable detector's parsers are missing, so any scan run now is "
        "in DEGRADED mode and its findings are an undercount, not a clean bill "
        f"of health: {', '.join(missing)}.\n"
        "Install them before treating any conformance number as real:\n"
        "  npm install --no-save htmlparser2 css-select css-tree domutils\n"
        f"resolved: {versions}"
    )


def test_degraded_mode_is_detectable_from_the_detector_output():
    """Control: the harness must be able to *see* degradation, not assume it.

    Asserts the marker this repository keys on is the one the tool actually
    emits. If the detector ever changes that wording, this fails and the
    preflight is updated deliberately rather than silently trusting a degraded
    run because the string stopped matching.
    """
    skill = _skill_dir()
    if skill is None:
        pytest.skip("impeccable skill not reachable from this checkout")
    detect = skill / "scripts" / "detect.mjs"
    r = subprocess.run(["node", str(detect), "--help"],
                       cwd=skill, capture_output=True, text=True, timeout=120)
    help_text = (r.stdout or "") + (r.stderr or "")
    assert "detect" in help_text.lower(), "detector did not respond to --help"

    # The marker the preflight greps for must be a real, current token. Search
    # the detector tree rather than pinning one filename: it currently lives in
    # engines/static-html/detect-html.mjs, and that path is an implementation
    # detail of the skill, not a contract.
    marker = "DEGRADED"
    hits = [f for f in (skill / "scripts").rglob("*.mjs")
            if marker in f.read_text(encoding="utf-8", errors="replace")]
    assert hits, (
        f"the detector no longer emits the {marker!r} marker this repository's "
        "preflight relies on; update the preflight deliberately rather than "
        "letting a degraded run pass unnoticed"
    )


def test_required_parser_list_is_not_silently_shortened():
    """A shrinking requirement list is the other way this gate could rot.

    Pins the four parsers the detector names in its own degradation warning, so
    dropping one from REQUIRED_PARSERS to make a machine pass is a visible edit
    to this assertion rather than an invisible weakening of the gate.
    """
    assert set(REQUIRED_PARSERS) == {
        "htmlparser2", "css-select", "css-tree", "domutils"
    }
