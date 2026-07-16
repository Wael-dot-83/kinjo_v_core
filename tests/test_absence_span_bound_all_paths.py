"""Every route that creates an absence must bound its span — not just the obvious one.

Approving an absence writes one attendance row per day in the span, so the span is the
loop bound of a write path and the parent picks it. There are **two** doors into the
same `absence_requests` table:

    POST /api/absence-requests              -> api/absence_requests.py
    POST /api/attendance/absence-requests   -> scripts/compat/missing_endpoints_orig.py

They take different field names (start_date/end_date vs from_date/to_date) and are easy
to mistake for one another. Bounding only the first left the second wide open —
measured, before this fix:

    /api/absence-requests            span=2,912,246 -> 422  (rejected)
    /api/attendance/absence-requests span=2,912,246 -> 201  <-- accepted

Both rows land with status=SUBMITTED and are approved by the same unbounded loop, so
the compat door was a complete bypass of the bound. This file exists because a
per-endpoint test would have passed while the hole stayed open: it asserts the property
across *every* creation route at once.
"""
from datetime import date, timedelta

import pytest

from api.absence_requests import MAX_ABSENCE_SPAN_DAYS

# (label, path, field names). Add a row here when a new creation route appears.
CREATION_ROUTES = [
    ("canonical", "/api/absence-requests", "start_date", "end_date"),
    ("compat", "/api/attendance/absence-requests", "from_date", "to_date"),
]


def _payload(child_id, start, end, start_field, end_field, reason="سبب ما"):
    return {
        "child_id": child_id,
        start_field: start.isoformat(),
        end_field: end.isoformat(),
        "reason": reason,
    }


@pytest.mark.parametrize("label,path,sf,ef", CREATION_ROUTES)
def test_absurd_span_is_rejected(client, auth_headers_parent, sample_child, active_enrollment, label, path, sf, ef):
    start = date.today() + timedelta(days=1)
    resp = client.post(path, json=_payload(sample_child.id, start, date(9999, 12, 31), sf, ef),
                       headers=auth_headers_parent)
    span = (date(9999, 12, 31) - start).days + 1
    assert resp.status_code != 201, (
        f"{label} route {path} accepted a {span:,}-day absence. Approving it loops once "
        "per day — roughly 2.9M SELECT+INSERT pairs on a sync worker."
    )
    assert resp.status_code in (400, 422), (
        f"{label} route {path} rejected the span with {resp.status_code}; expected a "
        f"4xx validation error: {resp.text[:160]}"
    )


@pytest.mark.parametrize("label,path,sf,ef", CREATION_ROUTES)
def test_span_at_the_limit_is_accepted(client, auth_headers_parent, sample_child, active_enrollment, label, path, sf, ef):
    """A bound that rejects everything would pass the test above. Both doors must still
    take a legitimate long absence — 366 days inclusive."""
    start = date.today() + timedelta(days=1)
    end = start + timedelta(days=MAX_ABSENCE_SPAN_DAYS - 1)
    resp = client.post(path, json=_payload(sample_child.id, start, end, sf, ef),
                       headers=auth_headers_parent)
    assert resp.status_code == 201, (
        f"{label} route {path} rejected a {MAX_ABSENCE_SPAN_DAYS}-day absence — the "
        f"documented limit — with {resp.status_code}: {resp.text[:160]}"
    )


def test_approve_refuses_a_stored_row_that_exceeds_the_bound(
    client, auth_headers_manager, manager_user, test_db, sample_child, active_enrollment
):
    """The loop is the thing the bound protects, so the loop must check too.

    Both creation routes are bounded, but that only protects rows created *after* the
    bound shipped. A row already in the table — persisted before this deploy, or written
    by a migration or a fixture — still walks ~2.9M days, one SELECT + one INSERT each.
    Planted directly in the DB, which is the only way to get one past the validators and
    therefore the only honest test of this guard.
    """
    import models

    absurd = models.AbsenceRequest(
        parent_id=sample_child.parent_id,
        child_id=sample_child.id,
        kindergarten_id=active_enrollment.kindergarten_id,
        class_id=active_enrollment.class_id,
        start_date=date.today() + timedelta(days=1),
        end_date=date(9999, 12, 31),
        reason="planted",
        status=models.AbsenceRequestStatus.SUBMITTED,
    )
    test_db.add(absurd)
    test_db.commit()
    test_db.refresh(absurd)

    resp = client.post(
        f"/api/absence-requests/{absurd.id}/approve",
        json={},
        headers=auth_headers_manager,
    )
    assert resp.status_code == 422, (
        f"approving a stored 2.9M-day absence returned {resp.status_code}; the loop ran "
        f"unbounded: {resp.text[:160]}"
    )

    # And nothing was written on the way to refusing.
    written = test_db.query(models.AttendanceLog).filter(
        models.AttendanceLog.child_id == sample_child.id
    ).count()
    assert written == 0, f"{written} attendance rows were written before the refusal"


def test_both_routes_are_actually_registered():
    """Non-vacuity: if a path 404s, its rejection assertions pass for the wrong reason."""
    from fastapi.routing import APIRoute, Mount

    from main import app

    def _join(prefix, path):
        return path if not prefix else f"{prefix.rstrip('/')}/{path.lstrip('/')}".replace("//", "/")

    def _walk(router, prefix=""):
        for route in getattr(router, "routes", []):
            if isinstance(route, Mount):
                continue
            if type(route).__name__ == "_IncludedRouter":
                ctx = getattr(route, "include_context", None)
                if ctx:
                    yield from _walk(ctx.included_router, _join(prefix, ctx.prefix or ""))
                continue
            if isinstance(route, APIRoute):
                yield _join(prefix, route.path), route

    posts = {p for p, r in _walk(app) if "POST" in (r.methods or [])}
    for label, path, _, _ in CREATION_ROUTES:
        assert path in posts, f"{label} route {path} is not registered — this file is testing nothing"
