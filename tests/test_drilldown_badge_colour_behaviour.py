"""getScoreColor's real behaviour, executed in node — not grepped for.

A test that asserts "the null guard appears in the source" passes whether or
not the guard works, and whether or not anything calls it. This extracts the
function and runs it, so the assertions are about returned values.

The defect: null/undefined fail every threshold comparison (null >= 90 is
false), so an unmeasured kindergarten fell through to bg-danger — "—" rendered
inside a red critical badge. That is the same "no data == zero == bad"
conflation the analytics rates removed by returning null instead of 0, and it
was already handled one line away for governance_band === "INSUFFICIENT".
"""
import json
import pathlib
import re
import shutil
import subprocess

import pytest

ROOT = pathlib.Path(__file__).resolve().parents[1]
DRILLDOWN_JS = ROOT / "static" / "js" / "admin_analytics_drilldown.js"

pytestmark = pytest.mark.skipif(
    shutil.which("node") is None, reason="node is required to execute the JS"
)


def _eval_get_score_color(cases):
    """Run the real getScoreColor source in node against `cases`."""
    src = DRILLDOWN_JS.read_text(encoding="utf-8")
    match = re.search(r"function getScoreColor\(.*?\n\}", src, re.S)
    assert match, "getScoreColor not found — the extraction, not the code, is broken"

    script = (
        match.group(0)
        + "\nconst cases = "
        + json.dumps(cases)
        + ";\nconsole.log(JSON.stringify(cases.map(c => getScoreColor(c[0], c[1]))));\n"
    )
    out = subprocess.run(
        ["node", "-e", script], capture_output=True, text=True, timeout=60
    )
    assert out.returncode == 0, f"node failed: {out.stderr[:300]}"
    return json.loads(out.stdout.strip())


def test_missing_score_is_neutral_not_critical():
    """null/undefined/NaN must not render as danger."""
    results = _eval_get_score_color([[None, True], [None, False]])
    for colour in results:
        assert "danger" not in colour, (
            f"a missing score renders {colour!r} — a red 'critical' badge around "
            f"an em dash, which reads as 'this kindergarten is failing' when the "
            f"truth is 'nobody recorded anything'"
        )
        assert "secondary" in colour


def test_real_scores_still_band_correctly():
    """Anti-overcorrection: the guard must not swallow genuine values,
    including a genuine, measured zero."""
    attendance = _eval_get_score_color([[95, True], [85, True], [40, True], [0, True]])
    assert "success" in attendance[0]
    assert "warning" in attendance[1]
    assert "danger" in attendance[2]
    # A measured 0% attendance IS critical and must stay red — the guard
    # distinguishes "unknown" from "zero", which is the entire point.
    assert "danger" in attendance[3]

    governance = _eval_get_score_color([[90, False], [70, False], [10, False]])
    assert governance == ["bg-success", "bg-warning", "bg-danger"]
