"""Filtering incidents by status must work, and bad input must not be a 500.

`GET /api/incidents?status=OPEN` returned **500**: `ValueError: 'OPEN' is not a valid
IncidentStatus`. `IncidentStatus` is the one enum in this area whose names and values
differ (`OPEN = "Open"`), and `IncidentStatus(raw)` looks up by *value*, so the value
the supervisor safety page's own dropdown sends never matched. The ValueError escaped
the handler, so an unrecognised filter — bad input — was reported as a server fault.

The dropdown was doubly wrong: it offered `UNDER_REVIEW`, which is not an
IncidentStatus name either, and omitted ACTION_REQUIRED and RESOLVED, so two of the
five states could not be filtered for at all.

This file pins the user's actual path: every value the dropdown can send must be
accepted by the API. A test that only checked `status=Open` would have passed
throughout while the page stayed broken.
"""
import re
from pathlib import Path

import pytest

import models

ROOT = Path(__file__).resolve().parents[1]
SAFETY_TEMPLATE = ROOT / "templates" / "supervisor" / "safety.html"


def _dropdown_status_values():
    """The status values the supervisor safety page actually sends."""
    html = SAFETY_TEMPLATE.read_text(encoding="utf-8")
    block = re.search(r'<select id="filterStatus".*?</select>', html, re.S)
    assert block, "filterStatus dropdown not found in templates/supervisor/safety.html"
    return [v for v in re.findall(r'<option value="([^"]*)"', block.group(0)) if v]


def test_dropdown_is_not_empty():
    """Non-vacuity: if the scrape breaks, the parametrised test below would silently
    verify nothing."""
    values = _dropdown_status_values()
    assert len(values) >= 3, f"only scraped {values} from the status dropdown"


@pytest.mark.parametrize("status_value", _dropdown_status_values())
def test_every_status_the_ui_offers_is_accepted(client, supervisor_token, status_value):
    """The exact request the page makes when a supervisor picks a status."""
    resp = client.get(
        f"/api/incidents?status={status_value}",
        headers={"Authorization": f"Bearer {supervisor_token}"},
    )
    assert resp.status_code != 500, (
        f"status={status_value!r} — the value the UI's own dropdown sends — returned "
        f"500: {resp.text[:200]}"
    )
    assert resp.status_code == 200, f"status={status_value!r} -> {resp.status_code}: {resp.text[:200]}"


def test_dropdown_values_are_all_real_incident_statuses():
    """Stops the dropdown drifting from the enum again. UNDER_REVIEW was offered for
    a status that does not exist, so that filter could never match anything."""
    names = {m.name for m in models.IncidentStatus}
    offered = set(_dropdown_status_values())
    unknown = offered - names
    assert not unknown, (
        f"the status dropdown offers values that are not IncidentStatus names: "
        f"{sorted(unknown)}. Valid names: {sorted(names)}"
    )


def test_enum_value_spelling_still_accepted(client, supervisor_token):
    """The API took the enum *value* before this fix; existing callers must keep working."""
    resp = client.get(
        "/api/incidents?status=Open",
        headers={"Authorization": f"Bearer {supervisor_token}"},
    )
    assert resp.status_code == 200, f"value spelling 'Open' -> {resp.status_code}: {resp.text[:200]}"


def test_unknown_status_is_a_422_not_a_500(client, supervisor_token):
    """Bad input is the client's fault, not a crash."""
    resp = client.get(
        "/api/incidents?status=NOT_A_STATUS",
        headers={"Authorization": f"Bearer {supervisor_token}"},
    )
    assert resp.status_code == 422, (
        f"an unknown status returned {resp.status_code}, expected 422: {resp.text[:200]}"
    )


def test_unknown_severity_is_a_422_not_a_500(client, supervisor_token):
    """Same handler, same trap: severity was coerced with a bare enum call too."""
    resp = client.get(
        "/api/incidents?severity=NOT_A_SEVERITY",
        headers={"Authorization": f"Bearer {supervisor_token}"},
    )
    assert resp.status_code == 422, (
        f"an unknown severity returned {resp.status_code}, expected 422: {resp.text[:200]}"
    )
