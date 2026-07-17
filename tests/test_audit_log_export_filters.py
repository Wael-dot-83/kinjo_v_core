"""Behavioural tests for the admin audit-log export filters.

These exist because the first attempt at covering the date filter asserted only
that `export_audit_logs` has a parameter named `date` and that the JS reads
`#dateFilter` — which would pass verbatim against a body of `if date: pass`.
The filter was in fact silently dropped on any parse failure, and the tests said
nothing. So: call the endpoint, assert on the rows that come back.

Two properties, both security-relevant on an export of the audit trail itself:

1. A filter that cannot be honoured must FAIL, not silently widen the result.
   Dropping it returns every audit row across all dates with a 200 while the
   export's own audit record still reports `date_filter=<value>` — the trail
   asserting a scope that was never applied.
2. The day boundary is the JORDAN day (UTC+3), not the UTC day. created_at is
   stored UTC (server_default=func.now()), so an event at 01:30 Jordan on D is
   22:30 UTC on D-1 and a naive func.date() files it under the wrong day.
"""
from datetime import datetime, time, timedelta, timezone

import pytest

import models

_JORDAN_TZ = timezone(timedelta(hours=3))


def _utc_naive(jordan_dt: datetime) -> datetime:
    """Storage form: the UTC instant, naive (matches server_default=func.now())."""
    return jordan_dt.astimezone(timezone.utc).replace(tzinfo=None)


@pytest.fixture
def audit_rows(test_db, admin_user):
    """Three rows around a Jordan day boundary.

    01:30 Jordan on the 17th is the load-bearing one: it lives on the 16th in
    UTC, so a UTC-day filter misses it while a Jordan-day filter finds it.
    """
    rows = [
        ("EARLY_HOURS_JORDAN_17", datetime(2026, 7, 17, 1, 30, tzinfo=_JORDAN_TZ)),
        ("MIDDAY_JORDAN_17", datetime(2026, 7, 17, 12, 0, tzinfo=_JORDAN_TZ)),
        ("MIDDAY_JORDAN_16", datetime(2026, 7, 16, 12, 0, tzinfo=_JORDAN_TZ)),
    ]
    for action, jordan_dt in rows:
        test_db.add(models.AuditLog(
            action=action,
            entity_type="TestEntity",
            user_id=admin_user.id,
            created_at=_utc_naive(jordan_dt),
        ))
    test_db.commit()
    return rows


def test_export_date_filter_uses_the_jordan_day_not_the_utc_day(
    client, auth_headers_admin, audit_rows
):
    response = client.get(
        "/api/admin/audit-logs/export?format=json&period=all&date=2026-07-17",
        headers=auth_headers_admin,
    )
    assert response.status_code == 200, response.text[:300]
    actions = {row["action"] for row in response.json()}

    # 01:30 Jordan on the 17th == 22:30 UTC on the 16th. func.date(created_at)
    # would file it under the 16th and drop it from this result.
    assert "EARLY_HOURS_JORDAN_17" in actions, (
        "the 01:30 Jordan event is missing — the filter is using the UTC day"
    )
    assert "MIDDAY_JORDAN_17" in actions
    assert "MIDDAY_JORDAN_16" not in actions, "a different Jordan day leaked in"


def test_export_rejects_an_unparseable_date_instead_of_dropping_the_filter(
    client, auth_headers_admin, audit_rows
):
    """The silent-lie shape: 200 + every row, and the caller cannot tell."""
    response = client.get(
        "/api/admin/audit-logs/export?format=json&period=all&date=not-a-date",
        headers=auth_headers_admin,
    )
    assert response.status_code == 422, (
        f"expected 422; got {response.status_code}. If this is a 200, the filter "
        f"was silently dropped and the export returned every matching row."
    )


@pytest.mark.parametrize("bad_date", ["2026-13-45", "2026/07/17", "yesterday",
                                      "2026-07-17T00:00:00"])
def test_export_rejects_every_unparseable_date_shape(
    client, auth_headers_admin, audit_rows, bad_date
):
    """Includes an ISO datetime: a plausible client value that strptime rejects."""
    response = client.get(
        f"/api/admin/audit-logs/export?format=json&period=all&date={bad_date}",
        headers=auth_headers_admin,
    )
    assert response.status_code == 422, (
        f"{bad_date!r} produced {response.status_code}, not 422"
    )


def test_export_without_a_date_filter_still_returns_every_row(
    client, auth_headers_admin, audit_rows
):
    """Guards the fix from overcorrecting into rejecting the no-filter case."""
    response = client.get(
        "/api/admin/audit-logs/export?format=json&period=all",
        headers=auth_headers_admin,
    )
    assert response.status_code == 200
    actions = {row["action"] for row in response.json()}
    assert {"EARLY_HOURS_JORDAN_17", "MIDDAY_JORDAN_17", "MIDDAY_JORDAN_16"} <= actions
