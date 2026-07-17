"""Injection and boundary behaviour of the admin audit-log filters.

Asserts what the endpoint RETURNS for hostile input, not that a helper was
called. A test that checks `escape_csv_formula` appears in the source proves
nothing about the bytes a spreadsheet opens; a test that checks a filter
"exists" proves nothing about whether it was applied. Both mistakes have
already been made on this branch.

Every case here is a way to make the endpoint answer a different question than
the caller asked while still returning 200 — the defect class this branch
exists to remove.
"""
import pytest

import models

# Payloads that must never widen the result set, execute, or 500.
INJECTION_PAYLOADS = [
    "2026-07-17' OR '1'='1",
    "2026-07-17; DROP TABLE audit_logs; --",
    "2026-07-17' UNION SELECT * FROM users --",
    "<script>alert(1)</script>",
    "../../etc/passwd",
    "%00",
    "2026-07-17\x00",
    "{{7*7}}",
    "${jndi:ldap://x}",
]


@pytest.fixture
def one_row(test_db, admin_user):
    test_db.add(models.AuditLog(
        action="INJECTION_PROBE", entity_type="TestEntity", user_id=admin_user.id,
    ))
    test_db.commit()


@pytest.mark.parametrize("payload", INJECTION_PAYLOADS)
def test_date_filter_rejects_injection_payloads_without_widening(
    client, auth_headers_admin, one_row, payload
):
    """A rejected filter must fail closed, never fall back to 'return all'."""
    response = client.get(
        "/api/admin/audit-logs/export",
        params={"format": "json", "period": "all", "date": payload},
        headers=auth_headers_admin,
    )
    assert response.status_code == 422, (
        f"{payload!r} produced {response.status_code}. A 200 means the filter was "
        f"dropped and every audit row was returned; a 500 means it reached the "
        f"query layer."
    )


@pytest.mark.parametrize("payload", INJECTION_PAYLOADS)
def test_period_filter_rejects_injection_payloads_without_widening(
    client, auth_headers_admin, one_row, payload
):
    response = client.get(
        "/api/admin/audit-logs/export",
        params={"format": "json", "period": payload},
        headers=auth_headers_admin,
    )
    assert response.status_code == 422, (
        f"{payload!r} produced {response.status_code}, not 422"
    )


@pytest.mark.parametrize("payload", INJECTION_PAYLOADS)
def test_list_date_filter_rejects_injection_payloads(
    client, auth_headers_admin, one_row, payload
):
    """The list is the hot path — the UI hits it on every filter change."""
    response = client.get(
        "/api/admin/audit-logs",
        params={"date": payload},
        headers=auth_headers_admin,
    )
    assert response.status_code == 422, (
        f"{payload!r} produced {response.status_code}, not 422"
    )


def test_the_audit_table_still_exists_after_the_injection_sweep(
    client, auth_headers_admin, one_row
):
    """Anti-vacuity: proves the sweep above ran against a live table rather
    than erroring out early, and that nothing it sent was destructive."""
    response = client.get(
        "/api/admin/audit-logs?limit=100", headers=auth_headers_admin
    )
    assert response.status_code == 200
    assert any(r["action"] == "INJECTION_PROBE" for r in response.json()["logs"])


# ── boundaries ───────────────────────────────────────────────────────────────

@pytest.mark.parametrize("period,expected", [
    ("all", 200), ("7", 200), ("30", 200), ("90", 200), ("365", 200), ("0", 200),
    ("99999", 200),          # the pattern's upper bound, ~273 years
    ("-1", 422), ("-5", 422),        # a negative cutoff lands in the FUTURE
    ("100000", 422),                 # 6 digits: past the bound
    ("999999999", 422),              # timedelta OverflowError -> 500 before
    ("", 422), (" ", 422), ("7.5", 422), ("1e3", 422), ("0x7", 422),
    ("٧", 422),                      # Arabic-Indic: int() accepts, [0-9] must not
    ("७", 422),                      # Devanagari
])
def test_period_boundaries(client, auth_headers_admin, one_row, period, expected):
    response = client.get(
        "/api/admin/audit-logs/export",
        params={"format": "json", "period": period},
        headers=auth_headers_admin,
    )
    assert response.status_code == expected, (
        f"period={period!r}: expected {expected}, got {response.status_code}"
    )


@pytest.mark.parametrize("date_value,expected", [
    ("2026-07-17", 200),
    ("2026-02-29", 422),     # not a leap year — a real calendar check
    ("2024-02-29", 200),     # is a leap year
    ("2026-13-01", 422),
    ("2026-00-01", 422),
    ("2026-07-32", 422),
    ("26-07-17", 422),
    # strptime's %m/%d accept an unpadded month/day, and "2026-7-17" parses to
    # exactly 2026-07-17 — the date the caller meant. Leniency that resolves to
    # the right question is not the defect this file is about, so it is pinned
    # as accepted rather than tightened for tidiness.
    ("2026-7-17", 200),
    ("20260717", 422),       # date.fromisoformat took this; strptime must not
    ("2026-07-17T00:00:00", 422),
    ("", 200),               # empty == "no filter", not a bad filter
])
def test_date_boundaries(client, auth_headers_admin, one_row, date_value, expected):
    response = client.get(
        "/api/admin/audit-logs/export",
        params={"format": "json", "period": "all", "date": date_value},
        headers=auth_headers_admin,
    )
    assert response.status_code == expected, (
        f"date={date_value!r}: expected {expected}, got {response.status_code}: "
        f"{response.text[:160]}"
    )


def test_period_zero_returns_no_rows_rather_than_every_row(
    client, auth_headers_admin, one_row
):
    """period=0 means "the last zero days". It must not mean "everything".

    Documented because it is the one boundary where an empty result is the
    honest answer: the cutoff is now, so nothing precedes it. 'all' is the
    supported way to ask for everything.
    """
    response = client.get(
        "/api/admin/audit-logs/export?format=json&period=0",
        headers=auth_headers_admin,
    )
    assert response.status_code == 200
    assert response.json() == []


# ── rendered output, not helper calls ────────────────────────────────────────

CSV_FORMULA_PAYLOADS = [
    "=SUM(A1)",
    "+1+1",
    "-1+1",
    "@SUM(A1)",
    '=HYPERLINK("http://evil","click")',
    "=cmd|'/c calc'!A1",
    "\t=1+1",
]


@pytest.mark.parametrize("payload", CSV_FORMULA_PAYLOADS)
def test_exported_csv_neutralises_formulas_in_the_rendered_bytes(
    test_db, client, auth_headers_admin, admin_user, payload
):
    """Parse what a spreadsheet would open, not what a helper returns.

    tests/test_admin_coverage_extra.py asserts
    `_escape_csv_formula("=SUM(A1)") == "'=SUM(A1)"` — a helper in isolation.
    That passes whether or not the export ever calls it, and whether or not the
    csv writer re-mangles the result. This drives the real endpoint and inspects
    the response body.
    """
    import csv
    import io

    test_db.add(models.AuditLog(
        action="CSV_INJECTION_PROBE",
        entity_type="TestEntity",
        details=payload,
        user_id=admin_user.id,
    ))
    test_db.commit()

    response = client.get(
        "/api/admin/audit-logs/export?format=csv&period=all",
        headers=auth_headers_admin,
    )
    assert response.status_code == 200
    assert "text/csv" in response.headers["content-type"]

    rows = list(csv.reader(io.StringIO(response.text)))
    probe = [r for r in rows if any("CSV_INJECTION_PROBE" in c for c in r)]
    assert probe, (
        "the probe row is not in the exported CSV — the test would otherwise "
        f"pass vacuously. body: {response.text[:200]!r}"
    )

    details_cell = probe[0][4]  # headers: Timestamp, User, Action, Entity, Details, IP
    assert details_cell.startswith("'"), (
        f"details cell {details_cell!r} is not formula-neutralised; a spreadsheet "
        f"would evaluate it on open"
    )
    # The payload must survive as readable text, not be silently dropped.
    assert payload.strip() in details_cell


def test_exported_json_does_not_html_escape_or_mangle_details(
    test_db, client, auth_headers_admin, admin_user
):
    """The JSON export is data, not markup: it must round-trip exactly.

    Over-escaping here would be its own silent lie — the export would claim to
    be the audit record while differing from it.
    """
    payload = '<script>alert(1)</script> & "quotes" & \'apostrophes\''
    test_db.add(models.AuditLog(
        action="JSON_ROUNDTRIP_PROBE",
        entity_type="TestEntity",
        details=payload,
        user_id=admin_user.id,
    ))
    test_db.commit()

    response = client.get(
        "/api/admin/audit-logs/export?format=json&period=all",
        headers=auth_headers_admin,
    )
    assert response.status_code == 200
    probe = [r for r in response.json() if r["action"] == "JSON_ROUNDTRIP_PROBE"]
    assert probe, "probe row missing — test would pass vacuously"
    assert probe[0]["details"] == payload
