"""An unrecognised incident filter must be a 422, not a 500.

`GET /api/incidents?status=OPEN` returned **500**: `ValueError: 'OPEN' is not a valid
IncidentStatus`. `IncidentStatus` is the one enum in this area whose names and values
differ (`OPEN = "Open"`); `IncidentStatus(raw)` looks up by *value*, and an unknown
value raised a bare ValueError straight out of the handler. Bad input is the caller's
fault, so it must never be reported as a server fault. Same trap on `severity`.

**Scope, stated honestly.** The live safety page (`/safety` →
`templates/safety/index.html`) sends the enum *values* — "Open", "Under Investigation"
— which the old coercion accepted, so that page was never broken. The 500 was reachable
by a hand-crafted URL, by any client sending the enum *names*, and by
`templates/supervisor/safety.html` — which offered names, but which **no route
renders**; it is an orphaned template, so no user could reach it. An earlier version of
this file claimed the supervisor page was the user path. That was wrong, and the
correction matters: the fix here is robustness (no unhandled 500, and either spelling
accepted), not the repair of a user-facing outage.

The live page's values are pinned below so that a fix aimed at the names cannot
silently break the spelling the working page actually sends.
"""
import re
from pathlib import Path

import pytest

import models

ROOT = Path(__file__).resolve().parents[1]
LIVE_SAFETY_TEMPLATE = ROOT / "templates" / "safety" / "index.html"


def _live_dropdown_status_values():
    """The status values the LIVE safety page (/safety) actually sends."""
    html = LIVE_SAFETY_TEMPLATE.read_text(encoding="utf-8")
    block = re.search(r'<select id="filterStatus".*?</select>', html, re.S)
    assert block, f"filterStatus dropdown not found in {LIVE_SAFETY_TEMPLATE}"
    return [v for v in re.findall(r'<option value="([^"]*)"', block.group(0)) if v]


def test_scrape_is_not_vacuous():
    """If the scrape breaks, the parametrised test below would verify nothing."""
    values = _live_dropdown_status_values()
    assert len(values) >= 3, f"only scraped {values} from the live status dropdown"


@pytest.mark.parametrize("status_value", _live_dropdown_status_values())
def test_every_status_the_live_page_offers_is_accepted(client, supervisor_token, status_value):
    """The request /safety makes when a supervisor picks a status. These are enum
    values and always worked — pinned so the name-handling fix cannot break them."""
    resp = client.get(
        f"/api/incidents?status={status_value}",
        headers={"Authorization": f"Bearer {supervisor_token}"},
    )
    assert resp.status_code == 200, (
        f"status={status_value!r} — sent by the live /safety page — returned "
        f"{resp.status_code}: {resp.text[:200]}"
    )


@pytest.mark.parametrize("name", [m.name for m in models.IncidentStatus])
def test_every_enum_name_is_also_accepted(client, supervisor_token, name):
    """The spelling that used to 500. Any client sending names — and any future page
    built from IncidentStatus.name — now gets an answer instead of a crash."""
    resp = client.get(
        f"/api/incidents?status={name}",
        headers={"Authorization": f"Bearer {supervisor_token}"},
    )
    assert resp.status_code != 500, (
        f"status={name!r} (an IncidentStatus NAME) returned 500 — the bare enum "
        f"coercion is back: {resp.text[:200]}"
    )
    assert resp.status_code == 200, f"status={name!r} -> {resp.status_code}: {resp.text[:200]}"


def test_unknown_status_is_a_422_not_a_500(client, supervisor_token):
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


def test_valid_severity_still_works(client, supervisor_token):
    """_resolve_enum replaced `SeverityLevel(severity.upper())`; the old spelling must
    keep working."""
    for sev in ("HIGH", "high"):
        resp = client.get(
            f"/api/incidents?severity={sev}",
            headers={"Authorization": f"Bearer {supervisor_token}"},
        )
        assert resp.status_code == 200, f"severity={sev!r} -> {resp.status_code}: {resp.text[:150]}"
