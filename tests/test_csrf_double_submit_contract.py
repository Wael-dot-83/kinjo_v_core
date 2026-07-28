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

The middleware is driven directly rather than through TestClient because
`csrf_protection_middleware` short-circuits when `settings.TESTING` is true, and
the whole suite runs with TESTING=true. Flipping that flag around a real request
would also re-enable Redis-backed caching and other TESTING-gated paths, so the
middleware is called as the pure function it is: same code, no side effects.
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


@pytest.fixture
def strict_csrf(monkeypatch):
    """Run the middleware with its production behaviour (TESTING off)."""
    monkeypatch.setattr(settings, "TESTING", False)
    return settings


async def _run(request):
    return await csrf_protection_middleware(request, _passthrough)


def _is_rejected(response) -> bool:
    return response.status_code == 403


class TestDoubleSubmitContract:
    """Header and cookie must both be present and must match."""

    @pytest.mark.asyncio
    async def test_matching_pair_is_accepted(self, strict_csrf):
        token = secrets.token_hex(32)
        response = await _run(
            _make_request(cookies={CSRF_COOKIE_NAME: token}, headers={"X-CSRF-Token": token})
        )
        assert response.status_code == 200, "a matching CSRF pair must reach the endpoint"

    @pytest.mark.asyncio
    async def test_missing_both_is_rejected(self, strict_csrf):
        assert _is_rejected(await _run(_make_request()))

    @pytest.mark.asyncio
    async def test_header_without_cookie_is_rejected(self, strict_csrf):
        response = await _run(_make_request(headers={"X-CSRF-Token": secrets.token_hex(32)}))
        assert _is_rejected(response)

    @pytest.mark.asyncio
    async def test_cookie_without_header_is_rejected(self, strict_csrf):
        response = await _run(_make_request(cookies={CSRF_COOKIE_NAME: secrets.token_hex(32)}))
        assert _is_rejected(response)

    @pytest.mark.asyncio
    async def test_mismatched_pair_is_rejected(self, strict_csrf):
        """A forged header cannot be paired with an unrelated cookie."""
        response = await _run(
            _make_request(
                cookies={CSRF_COOKIE_NAME: secrets.token_hex(32)},
                headers={"X-CSRF-Token": secrets.token_hex(32)},
            )
        )
        assert _is_rejected(response)

    @pytest.mark.asyncio
    async def test_empty_values_are_rejected(self, strict_csrf):
        """Empty strings compare equal — they must not count as a valid pair."""
        response = await _run(
            _make_request(cookies={CSRF_COOKIE_NAME: ""}, headers={"X-CSRF-Token": ""})
        )
        assert _is_rejected(response)

    @pytest.mark.asyncio
    async def test_cross_site_origin_is_rejected(self, strict_csrf):
        """Even a valid pair must not be honoured from a foreign origin."""
        token = secrets.token_hex(32)
        response = await _run(
            _make_request(
                cookies={CSRF_COOKIE_NAME: token},
                headers={"X-CSRF-Token": token, "Origin": "https://evil.example"},
            )
        )
        assert _is_rejected(response)

    @pytest.mark.asyncio
    async def test_cross_site_referer_is_rejected(self, strict_csrf):
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
    async def test_safe_methods_are_not_blocked(self, strict_csrf, method):
        """Reads must never require a token, or the whole UI breaks."""
        response = await _run(_make_request(method=method, path="/api/admin/users"))
        assert response.status_code == 200


class TestValidatorHasNoBypass:
    """Static guarantees about the enforcement code itself."""

    def test_middleware_uses_constant_time_comparison(self):
        source = inspect.getsource(csrf_protection_middleware)
        assert "compare_digest" in source, (
            "csrf_protection_middleware must compare the double-submit pair in "
            "constant time"
        )

    def test_remaining_endpoint_validators_use_constant_time_comparison(self):
        """Modules that still carry their own validator must also compare safely."""
        from analytics_service import _validate_csrf_token as analytics_validator
        from heatmap.backend.admin_router import _validate_csrf_token as heatmap_validator

        for validator in (analytics_validator, heatmap_validator):
            source = inspect.getsource(validator)
            assert "compare_digest" in source, (
                f"{validator.__module__}._validate_csrf_token must compare in "
                "constant time"
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

    def test_middleware_test_bypass_cannot_apply_in_production(self):
        """The middleware's TESTING short-circuit is the one env-conditional path.

        It is deliberate — the suite could not drive authenticated writes without
        it — but it must never be reachable in production, so it is pinned to
        `not settings.is_production`.
        """
        source = inspect.getsource(csrf_protection_middleware)
        assert "settings.TESTING and not settings.is_production" in source, (
            "the CSRF test bypass must remain gated on `not settings.is_production`"
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
