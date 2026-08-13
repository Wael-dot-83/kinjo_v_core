"""Risk Intelligence card on /admin/analytics (Overview tab).

risk_radar rows are children (get_high_risk_children), which the UI presented as
facilities in two places.
"""

from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
TEMPLATE = ROOT / "templates" / "admin" / "analytics" / "dashboard.html"
SERVICE = ROOT / "analytics_service.py"


def _html() -> str:
    return TEMPLATE.read_text(encoding="utf-8")


def test_risk_rows_really_are_children():
    """Guards the premise: if the backend ever returns facilities instead, the
    UI corrections below need revisiting."""
    source = SERVICE.read_text(encoding="utf-8")
    body = source.split("def get_high_risk_children", 1)[1].split("\n    @staticmethod", 1)[0]
    assert '"child_id"' in body and '"child_name"' in body
    assert '"risk_type": "Low Attendance"' in body
    assert '"risk_type": "Multiple Incidents"' in body


def test_facility_chip_counts_facilities_not_children():
    """Three at-risk children in one kindergarten must not read as three
    facilities needing review."""
    html = _html()
    block = html.split("/* Risk count.", 1)[1].split("addChip", 1)[0]
    assert "new Set(" in block
    assert "kindergarten_id" in block
    assert ".size" in block
    # The old row-count form must be gone.
    assert "riskArr.filter(function (r) { return window._classifyRisk(r) === 'critical'; }).length" not in html


def test_null_facility_ids_are_not_counted():
    """A missing kindergarten_id would otherwise add a phantom facility."""
    block = _html().split("/* Risk count.", 1)[1].split("addChip", 1)[0]
    assert "id != null" in block


def test_card_action_names_the_facility_it_opens():
    """The card shows a child's name; an unqualified "view facility details"
    made the child's name read as the facility."""
    html = _html()
    assert "r.kindergarten_name ||" in html
    assert "'عرض المرفق: '" in html
    assert "'View facility: '" in html


def test_score_carries_its_unit():
    """risk_value is an attendance percentage for one risk type and a raw
    incident count for the other; a bare number makes 3.0 look milder than
    80.0 when it is the critical one."""
    html = _html()
    block = html.split("const rawScore", 1)[1].split("return [", 1)[0]
    assert "Multiple Incidents" in block
    assert "حادثة" in block and "inc." in block
    assert "'%'" in block or '+ "%"' in block or "toFixed(1) + '%'" in block


def test_score_is_numeric_safe():
    """toFixed on a non-numeric value throws and would blank the whole card."""
    block = _html().split("const rawScore", 1)[1].split("return [", 1)[0]
    assert "Number(r.risk_value)" in block
    assert "Number.isFinite(rawScore)" in block


def test_classifier_still_branches_on_risk_type():
    """Both scales must keep their own thresholds -- a single numeric cutoff
    cannot classify a percentage and a count."""
    html = _html()
    block = html.split("window._classifyRisk = function", 1)[1].split("};", 1)[0]
    assert "Multiple Incidents" in block
    assert "critical" in block and "high" in block and "medium" in block
