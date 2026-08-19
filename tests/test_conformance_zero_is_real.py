"""Conformance is at zero -- and that zero must stay a measurement, not a mood.

This repository scans clean against the impeccable slop rules. Getting there
involved suppressing findings that were proved false in a browser, per file and
with the measurement written into the file. That is a legitimate use of the
mechanism and a dangerous one, because the failure mode is silent: if a future
edit widens a suppression, disables a rule in .impeccable/config.json, or the
detector's parsers go missing, the scan still prints a number and the number is
still zero. Zero looks identical whether it means "clean" or "not looking".

So this pins both halves:

  * the repository scans to zero
  * a file that genuinely violates the rules still trips them

The second is the one that matters. Without it the first is unfalsifiable.

Sibling guards, same lesson in different clothes:
  * tests/test_conformance_instrument.py -- the detector silently degrading from
    221 findings to 60 when its HTML/CSS parsers are absent.
  * tests/test_browser_audit_contract.py -- a browser audit that measured the
    login page six times and reported it as six authenticated surfaces.
"""
import json
import os
import subprocess
import textwrap
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]

# A file that breaks the rules on purpose. Each block targets a different rule
# so the control cannot pass on a single lucky match:
#   .probe-a  #b8c4d0 on white is 1.9:1        -> low-contrast
#   .probe-b  visible boundary, zero inset     -> cramped-padding
#   .probe-c  9px body copy                    -> undersized-ui-text
#   .probe-d  uppercased, heavily tracked body -> all-caps-body
CONTROL_HTML = textwrap.dedent("""\
    <!doctype html>
    <html lang="ar" dir="rtl"><head><style>
      .probe-a { color: #b8c4d0; background: #ffffff; font-size: 14px; }
      .probe-b { border: 1px solid #ddd; background: #fafafa; padding: 0; }
      .probe-c { font-size: 9px; }
      .probe-d { text-transform: uppercase; letter-spacing: 0.3em; font-size: 13px; }
    </style></head><body>
      <div class="probe-a">نص منخفض التباين يجب أن يُكتشف</div>
      <div class="probe-b"><span>محتوى ملتصق بالحافة</span></div>
      <div class="probe-c">نص صغير جدا</div>
      <div class="probe-d">wide tracked all caps body text</div>
    </body></html>
    """)


def _skill_dir():
    """Locate the impeccable skill. Shared shape with test_conformance_instrument."""
    candidates = [ROOT / ".claude" / "skills" / "impeccable"]
    env = os.environ.get("IMPECCABLE_SKILL_DIR")
    if env:
        candidates.append(Path(env))
    for parent in list(ROOT.parents)[:4]:
        candidates.append(parent / ".claude" / "skills" / "impeccable")
    for c in candidates:
        try:
            if c.is_dir() and (c / "scripts" / "detect.mjs").is_file():
                return c
        except OSError:
            continue
    return None


def _scan(*targets):
    """Run the detector and return its findings list."""
    skill = _skill_dir()
    if skill is None:
        pytest.skip("impeccable skill not present in this checkout")
    detect = skill / "scripts" / "detect.mjs"
    try:
        r = subprocess.run(
            ["node", str(detect), "--json", *[str(t) for t in targets]],
            cwd=ROOT, capture_output=True, text=True, timeout=900,
        )
    except (FileNotFoundError, subprocess.TimeoutExpired):
        pytest.skip("node unavailable or detector timed out")
    if not r.stdout.strip():
        pytest.skip(f"detector produced no output: {r.stderr[:300]}")
    data = json.loads(r.stdout)
    return data if isinstance(data, list) else data.get("findings", data)


def test_the_rules_still_fire_on_a_real_violation():
    """The control. This is the assertion that gives the zero its meaning.

    A file that breaks the rules must still be caught. If the suppressions ever
    widen into a blanket, or a rule is switched off in config, this fails and
    the next person learns it here rather than from a design review.
    """
    probe = ROOT / "templates" / "_conformance_control_probe.html"
    probe.write_text(CONTROL_HTML, encoding="utf-8")
    try:
        findings = _scan(probe.relative_to(ROOT))
    finally:
        probe.unlink(missing_ok=True)

    fired = {f["antipattern"] for f in findings}
    assert fired, (
        "a deliberately broken file produced zero findings, so the detector is "
        "no longer checking anything. The repository's clean scan means nothing "
        "while this is true -- check .impeccable/config.json for a widened "
        "ignoreRules/ignoreFiles, and check that the parsers are installed."
    )
    # Contrast and padding are the two categories carrying suppressions, so
    # they are the two that most need proving still-live.
    for rule in ("low-contrast", "cramped-padding"):
        assert rule in fired, (
            f"{rule!r} did not fire on a file built to violate it. That rule "
            f"has been suppressed too broadly -- suppressions must stay scoped "
            f"to the specific files whose findings were disproved by "
            f"measurement, never applied globally. Fired: {sorted(fired)}"
        )


def test_first_party_surfaces_scan_clean():
    """The claim itself: templates/ and static/ carry no unexplained findings.

    Anything that fires here is either a real regression or a false positive
    that has not yet been disproved. Both are worth stopping for; neither should
    be waved through by widening a suppression.
    """
    findings = _scan("templates", "static")
    if findings:
        detail = "\n".join(
            f"  {f['antipattern']:24} {f.get('file','?')}" for f in findings[:25]
        )
        pytest.fail(
            f"{len(findings)} conformance finding(s) on first-party surfaces:\n{detail}\n\n"
            "Fix the defect. If it is genuinely a false positive, prove it in a "
            "browser first and record the measurement in an inline "
            "impeccable-disable comment on that file -- never by adding the rule "
            "to ignoreRules, which would blind every other file too."
        )


def test_suppressions_are_scoped_to_files_not_global():
    """config.json declares scan SCOPE only; it must never silence a rule.

    static/vendor/** is excluded because it holds third-party minified bundles
    nobody here authors. That is a statement about what is ours, not about which
    rules apply to our code.
    """
    cfg_path = ROOT / ".impeccable" / "config.json"
    if not cfg_path.is_file():
        pytest.skip("no .impeccable/config.json in this checkout")
    cfg = json.loads(cfg_path.read_text(encoding="utf-8"))
    detector = cfg.get("detector", {})

    assert not detector.get("ignoreRules"), (
        "a rule has been switched off repository-wide in .impeccable/config.json: "
        f"{detector.get('ignoreRules')}. Suppress a disproved finding on the file "
        "it lives on, with the measurement written beside it, so every other file "
        "stays covered."
    )
    assert not detector.get("ignoreValues"), (
        f"ignoreValues is set ({detector.get('ignoreValues')}), which silences "
        "findings by value across the whole repository."
    )
    for pattern in detector.get("ignoreFiles", []):
        assert pattern.startswith("static/vendor/"), (
            f"ignoreFiles pattern {pattern!r} reaches outside static/vendor/. "
            "Scope exclusions are for third-party code we do not author; first-party "
            "files must stay in scope."
        )
