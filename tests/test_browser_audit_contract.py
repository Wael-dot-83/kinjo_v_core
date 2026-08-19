"""A browser audit must prove which page it measured.

This exists because of a specific, expensive mistake. An audit reported "zero
contrast failures across nine surfaces". Six of those nine were the login page:
repeated test logins had tripped the account lockout, every authenticated
request returned 423, and the browser measured the lockout screen six times
while the report attributed the numbers to six admin routes. The tool ran, the
numbers were real, and they described the wrong document.

The fix is a contract, not more care: an audit refuses to return measurements
for a page whose identity it has not established. This module pins that contract
so the harness cannot quietly regress to "navigate, then measure whatever
loaded".

Its sibling is tests/test_conformance_instrument.py, which pins the other half
of the same lesson -- the detector silently degrading from 221 findings to 60
when its parsers are absent.
"""
import pytest

# The states that make a measurement invalid rather than merely bad.
INVALID_STATUSES = (401, 403, 423)


class RouteIdentityError(AssertionError):
    """Raised when the page measured is not the page requested."""


def verify_route_identity(requested, final, status, marker_found=None):
    """The contract the browser harness implements.

    Returns evidence on success and raises on every way the audit could end up
    describing the wrong document. Kept as a pure function precisely so it can
    be tested without a browser -- a guard that only runs inside the slow path
    tends not to run at all.
    """
    if status in INVALID_STATUSES:
        raise RouteIdentityError(
            f"{requested}: HTTP {status} is not an authenticated render. "
            "423 in particular means the account is locked out, which is how an "
            "audit ends up measuring the lockout screen and calling it an admin page."
        )
    if final != requested:
        raise RouteIdentityError(f"{requested}: landed on {final} instead")
    if "/login" in final and requested != "/login":
        raise RouteIdentityError(f"{requested}: login substitution detected")
    if marker_found is False:
        raise RouteIdentityError(
            f"{requested}: the route's own marker was absent, so the document "
            "did not actually render even though the URL and status looked right"
        )
    return {"requested": requested, "final": final, "status": status,
            "marker_found": marker_found}


def test_a_correct_render_is_accepted():
    ev = verify_route_identity("/admin/heatmap", "/admin/heatmap", 200, marker_found=True)
    assert ev["status"] == 200 and ev["marker_found"] is True


@pytest.mark.parametrize("status", INVALID_STATUSES)
def test_auth_failure_statuses_invalidate_the_measurement(status):
    """423/401/403 must abort, not produce numbers.

    This is the exact shape of the original failure: the harness asked for an
    admin route, got 423, and measured what came back.
    """
    with pytest.raises(RouteIdentityError) as e:
        verify_route_identity("/admin/kpi", "/admin/kpi", status)
    assert str(status) in str(e.value)


def test_login_substitution_is_rejected():
    with pytest.raises(RouteIdentityError):
        verify_route_identity("/admin/dashboard", "/login", 200, marker_found=True)


def test_landing_on_a_different_route_is_rejected():
    with pytest.raises(RouteIdentityError):
        verify_route_identity("/admin/kpi", "/admin/dashboard", 200, marker_found=True)


def test_a_200_without_the_route_marker_is_rejected():
    """The subtlest case, and a real one from this workstream.

    /admin/kpi returned 200 at the right URL with a real page behind it, but the
    marker the harness was checking did not exist -- the page uses ids rather
    than kpi-* classes. The audit refused to report, which was correct: at that
    moment the harness could not tell a rendered page from an empty shell. The
    marker was then fixed deliberately instead of the check being dropped.
    """
    with pytest.raises(RouteIdentityError) as e:
        verify_route_identity("/admin/kpi", "/admin/kpi", 200, marker_found=False)
    assert "marker" in str(e.value)


def test_the_harness_implements_this_same_contract():
    """The audit harness must actually enforce the contract, not re-derive it.

    Skips when the harness is not importable (it lives beside the browser
    tooling, not in the app package), but when it is present its guard must
    exist and be named the same thing, so a future edit that deletes the check
    fails here rather than silently returning to measure-whatever-loaded.
    """
    import importlib.util
    import os
    from pathlib import Path

    candidates = [
        Path(os.environ.get("KINJO_AUDIT_HARNESS", "")),
        Path(__file__).resolve().parents[1] / "tests" / "browser" / "audit_harness.py",
    ]
    harness = next((c for c in candidates if c and c.is_file()), None)
    if harness is None:
        pytest.skip("browser audit harness not vendored into this checkout")

    src = harness.read_text(encoding="utf-8")
    assert "RouteIdentityError" in src, "harness lost its route-identity guard"
    assert "marker" in src, "harness no longer checks a route-specific marker"
    for code in ("401", "403", "423"):
        assert code in src, f"harness no longer treats {code} as an invalid render"
