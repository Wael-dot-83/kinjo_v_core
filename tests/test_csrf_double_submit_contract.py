"""Contract tests for double-submit CSRF on state-changing requests.

These exist because ~103 test failures were once traced to auth-only headers
hitting the CSRF validator, and the tempting "fix" was to bypass the validator
under TESTING. That would have deleted a real security boundary.

**Why this file was rewritten.** It previously imported
`admin_endpoints._validate_csrf_token`. That per-endpoint validator no longer
exists — enforcement moved into `middleware.csrf.csrf_protection_middleware` —
so every test here failed at import with

    ImportError: cannot import name '_validate_csrf_token' from 'admin_endpoints'

which meant the double-submit boundary had *no* working test coverage at all.
The tests now exercise the middleware that actually enforces it.

The middleware is driven directly rather than through TestClient so each rule
of the policy is exercised in isolation: same code, no side effects. The
middleware has **no TESTING conditional** (D-2 consolidation deleted the old
seam), so these tests exercise exactly what production runs.
"""

import inspect
import secrets

import pytest
from fastapi.responses import JSONResponse
from starlette.requests import Request

from config import settings
from conftest import CSRF_COOKIE_NAME, csrf_pair
from middleware.csrf import CSRF_SAFE_METHODS, csrf_protection_middleware

WRITE_PATH = "/api/admin/users/1"


def _make_request(method: str = "DELETE", path: str = WRITE_PATH, *, cookies=None, headers=None):
    """Build a real Starlette Request with the given cookies/headers."""
    raw_headers = [(b"host", b"testserver")]
    for key, value in (headers or {}).items():
        raw_headers.append((key.lower().encode(), str(value).encode()))
    if cookies:
        cookie_header = "; ".join(f"{k}={v}" for k, v in cookies.items())
        raw_headers.append((b"cookie", cookie_header.encode()))
    return Request(
        {
            "type": "http",
            "method": method,
            "path": path,
            "raw_path": path.encode(),
            "headers": raw_headers,
            "query_string": b"",
            "scheme": "http",
            "server": ("testserver", 80),
            "client": ("127.0.0.1", 12345),
            "root_path": "",
        }
    )


async def _passthrough(_request):
    """Stand-in for the rest of the stack; reaching it means CSRF allowed the request."""
    return JSONResponse({"reached_endpoint": True})


async def _run(request):
    return await csrf_protection_middleware(request, _passthrough)


def _is_rejected(response) -> bool:
    return response.status_code == 400


class TestDoubleSubmitContract:
    """Header and cookie must both be present and must match."""

    @pytest.mark.asyncio
    async def test_matching_pair_is_accepted(self):
        token = secrets.token_hex(32)
        response = await _run(_make_request(cookies={CSRF_COOKIE_NAME: token}, headers={"X-CSRF-Token": token}))
        assert response.status_code == 200, "a matching CSRF pair must reach the endpoint"

    @pytest.mark.asyncio
    async def test_missing_both_passes_through_to_auth(self):
        """No cookies and no header means no ambient authority — nothing to forge.

        CSRF rides ambient credentials (cookies). A request carrying none cannot
        be a forgery of anything, so the middleware passes it through and
        authentication downstream answers 401. This is also what preserves
        curl-style API clients and anonymous 401 semantics. A browser never
        looks like this in practice: the middleware provisions the CSRF cookie
        on the first safe response, so real browser writes always land in the
        enforced branch.
        """
        response = await _run(_make_request())
        assert response.status_code == 200, (
            "a credential-less request must reach the endpoint so auth can "
            "reject it with 401; CSRF blocking it would mask the real cause"
        )

    @pytest.mark.asyncio
    async def test_header_without_cookie_is_rejected(self):
        response = await _run(_make_request(headers={"X-CSRF-Token": secrets.token_hex(32)}))
        assert _is_rejected(response)

    @pytest.mark.asyncio
    async def test_cookie_without_header_is_rejected(self):
        response = await _run(_make_request(cookies={CSRF_COOKIE_NAME: secrets.token_hex(32)}))
        assert _is_rejected(response)

    @pytest.mark.asyncio
    async def test_mismatched_pair_is_rejected(self):
        """A forged header cannot be paired with an unrelated cookie."""
        response = await _run(
            _make_request(
                cookies={CSRF_COOKIE_NAME: secrets.token_hex(32)},
                headers={"X-CSRF-Token": secrets.token_hex(32)},
            )
        )
        assert _is_rejected(response)

    @pytest.mark.asyncio
    async def test_empty_values_are_rejected(self):
        """Empty strings compare equal — they must not count as a valid pair."""
        response = await _run(_make_request(cookies={CSRF_COOKIE_NAME: ""}, headers={"X-CSRF-Token": ""}))
        assert _is_rejected(response)

    @pytest.mark.asyncio
    async def test_cross_site_origin_is_rejected(self):
        """Even a valid pair must not be honoured from a foreign origin."""
        token = secrets.token_hex(32)
        response = await _run(
            _make_request(
                cookies={CSRF_COOKIE_NAME: token},
                headers={"X-CSRF-Token": token, "Origin": "https://evil.example"},
            )
        )
        assert _is_rejected(response)

    @pytest.mark.parametrize(
        "path",
        [
            "/api/contact",
            "/api/users/request-password-reset",
            "/api/users/reset-password",
            "/api/ui-language",
        ],
    )
    @pytest.mark.asyncio
    async def test_public_pre_auth_flows_are_exempt_from_csrf(self, path):
        """Public contact and password-reset pages should not require a CSRF pair."""
        token = secrets.token_hex(32)
        response = await _run(_make_request(method="POST", path=path, cookies={CSRF_COOKIE_NAME: token}))
        assert response.status_code == 200, f"{path} should be allowed to reach the endpoint without a CSRF pair"

    @pytest.mark.asyncio
    async def test_cross_site_referer_is_rejected(self):
        token = secrets.token_hex(32)
        response = await _run(
            _make_request(
                cookies={CSRF_COOKIE_NAME: token},
                headers={"X-CSRF-Token": token, "Referer": "https://evil.example/page"},
            )
        )
        assert _is_rejected(response)

    @pytest.mark.parametrize("method", sorted(CSRF_SAFE_METHODS))
    @pytest.mark.asyncio
    async def test_safe_methods_are_not_blocked(self, method):
        """Reads must never require a token, or the whole UI breaks."""
        response = await _run(_make_request(method=method, path="/api/admin/users"))
        assert response.status_code == 200


class TestValidatorHasNoBypass:
    """Static guarantees about the enforcement code itself."""

    def test_middleware_uses_constant_time_comparison(self):
        source = inspect.getsource(csrf_protection_middleware)
        assert "compare_digest" in source, (
            "csrf_protection_middleware must compare the double-submit pair in constant time"
        )

    def test_remaining_endpoint_validators_use_constant_time_comparison(self):
        """Modules that still carry their own validator must also compare safely."""
        from analytics_service import _validate_csrf_token as analytics_validator
        from heatmap.backend.admin_router import _validate_csrf_token as heatmap_validator

        for validator in (analytics_validator, heatmap_validator):
            source = inspect.getsource(validator)
            assert "compare_digest" in source, (
                f"{validator.__module__}._validate_csrf_token must compare in constant time"
            )

    def test_endpoint_validators_contain_no_environment_bypass(self):
        """No TESTING/DEBUG escape hatch may short-circuit a per-endpoint check."""
        from analytics_service import _validate_csrf_token as analytics_validator
        from heatmap.backend.admin_router import _validate_csrf_token as heatmap_validator

        forbidden = ("TESTING", "DEBUG", "is_production", "ENVIRONMENT")
        for validator in (analytics_validator, heatmap_validator):
            source = inspect.getsource(validator)
            for token in forbidden:
                assert token not in source, (
                    f"{validator.__module__}._validate_csrf_token references "
                    f"{token!r} — CSRF must not be conditional on environment"
                )

    def test_middleware_has_no_environment_bypass(self):
        """The middleware must run identical semantics in every environment.

        The old TESTING seam was deleted by the D-2 consolidation: the suite
        authenticates with bearer tokens (CSRF-exempt) or dependency overrides
        (cookie-less, so nothing to forge), so no test-only short-circuit is
        needed — and none may ever return, because a seam that relaxes CSRF
        under TESTING is exactly how a real regression ships undetected.
        """
        source = inspect.getsource(csrf_protection_middleware)
        for token in ("TESTING", "DEBUG", "is_production", "ENVIRONMENT"):
            assert token not in source, (
                f"csrf_protection_middleware references {token!r} — CSRF must not be conditional on environment"
            )

    def test_csrf_pair_helper_matches_production_cookie_name(self):
        """The canonical helper must target the cookie the app actually reads."""
        pair = csrf_pair()
        assert pair["Cookie"].startswith(f"{settings.CSRF_COOKIE_NAME}=")
        assert pair["X-CSRF-Token"] == pair["Cookie"].split("=", 1)[1]

    def test_csrf_cookie_name_not_drifted(self):
        """Older test modules build the pair inline with the literal cookie name.

        The canonical helper reads settings.CSRF_COOKIE_NAME, but many modules
        still hardcode "kinjo_csrf_token". If that setting is ever renamed, those
        inline pairs would satisfy a cookie the app no longer reads and pass
        vacuously. Pin the literal to the setting so a rename fails loudly here,
        pointing at the modules to update, instead of silently.
        """
        assert settings.CSRF_COOKIE_NAME == "kinjo_csrf_token", (
            "CSRF cookie name changed. Inline pairs in the test suite hardcode "
            "'kinjo_csrf_token'; update them (or route them through "
            "conftest.csrf_pair) before changing this assertion."
        )
