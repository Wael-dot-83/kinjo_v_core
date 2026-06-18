"""Tests for the pluggable CAPTCHA and virus-scanning layers (Round 3).

These exercise the service modules directly (with settings monkeypatched,
since the global test suite runs with TESTING=true which bypasses both by
design) and confirm the HTTP-facing endpoints respect that bypass.
"""
import socket

import pytest

import captcha_service
import virus_scan_service
from config import settings


# ============================================================================
# captcha_service
# ============================================================================

class TestCaptchaService:
    def test_disabled_by_default_allows_any_token(self):
        assert settings.CAPTCHA_ENABLED is False
        assert captcha_service.verify_captcha(None) is True
        assert captcha_service.verify_captcha("") is True

    def test_testing_flag_always_bypasses_even_if_enabled(self, monkeypatch):
        monkeypatch.setattr(settings, "CAPTCHA_ENABLED", True)
        assert settings.TESTING is True
        assert captcha_service.captcha_required() is False
        assert captcha_service.verify_captcha(None) is True

    def test_enabled_without_secret_key_fails_closed(self, monkeypatch):
        monkeypatch.setattr(settings, "TESTING", False)
        monkeypatch.setattr(settings, "CAPTCHA_ENABLED", True)
        monkeypatch.setattr(settings, "CAPTCHA_SECRET_KEY", "")
        assert captcha_service.captcha_required() is True
        assert captcha_service.verify_captcha("some-token") is False

    def test_enabled_missing_token_rejected(self, monkeypatch):
        monkeypatch.setattr(settings, "TESTING", False)
        monkeypatch.setattr(settings, "CAPTCHA_ENABLED", True)
        monkeypatch.setattr(settings, "CAPTCHA_SECRET_KEY", "fake-secret")
        assert captcha_service.verify_captcha(None) is False
        assert captcha_service.verify_captcha("") is False

    def test_unsupported_provider_rejected(self, monkeypatch):
        monkeypatch.setattr(settings, "TESTING", False)
        monkeypatch.setattr(settings, "CAPTCHA_ENABLED", True)
        monkeypatch.setattr(settings, "CAPTCHA_SECRET_KEY", "fake-secret")
        monkeypatch.setattr(settings, "CAPTCHA_PROVIDER", "not-a-real-provider")
        assert captcha_service.verify_captcha("some-token") is False

    def test_valid_token_accepted_via_mocked_provider_response(self, monkeypatch):
        monkeypatch.setattr(settings, "TESTING", False)
        monkeypatch.setattr(settings, "CAPTCHA_ENABLED", True)
        monkeypatch.setattr(settings, "CAPTCHA_SECRET_KEY", "fake-secret")

        class _FakeResponse:
            def raise_for_status(self):
                pass

            def json(self):
                return {"success": True}

        monkeypatch.setattr(captcha_service.httpx, "post", lambda *a, **k: _FakeResponse())
        assert captcha_service.verify_captcha("a-real-looking-token") is True

    def test_invalid_token_rejected_via_mocked_provider_response(self, monkeypatch):
        monkeypatch.setattr(settings, "TESTING", False)
        monkeypatch.setattr(settings, "CAPTCHA_ENABLED", True)
        monkeypatch.setattr(settings, "CAPTCHA_SECRET_KEY", "fake-secret")

        class _FakeResponse:
            def raise_for_status(self):
                pass

            def json(self):
                return {"success": False, "error-codes": ["invalid-input-response"]}

        monkeypatch.setattr(captcha_service.httpx, "post", lambda *a, **k: _FakeResponse())
        assert captcha_service.verify_captcha("a-bad-token") is False

    def test_provider_network_error_fails_closed(self, monkeypatch):
        monkeypatch.setattr(settings, "TESTING", False)
        monkeypatch.setattr(settings, "CAPTCHA_ENABLED", True)
        monkeypatch.setattr(settings, "CAPTCHA_SECRET_KEY", "fake-secret")

        def _raise(*a, **k):
            raise captcha_service.httpx.ConnectError("boom")

        monkeypatch.setattr(captcha_service.httpx, "post", _raise)
        assert captcha_service.verify_captcha("any-token") is False

    def test_error_message_is_bilingual(self):
        assert captcha_service.captcha_error_message("en") != captcha_service.captcha_error_message("ar")
        assert "CAPTCHA" in captcha_service.captcha_error_message("en")


class TestCaptchaEndpointIntegration:
    """Confirm public endpoints stay reachable under the default
    (disabled) CAPTCHA config — the normal state for every other test
    in this suite — and reject when enabled with a bad/missing token."""

    def test_contact_form_works_with_captcha_disabled(self, client, test_db):
        resp = client.post(
            "/api/contact",
            json={
                "name": "Test User",
                "email": "captcha-test@example.com",
                "subject": "other",
                "message": "Hello, this is a test message.",
            },
        )
        assert resp.status_code == 200

    def test_contact_form_rejects_when_captcha_enabled_and_no_token(self, client, test_db, monkeypatch):
        # Patch the route's imported references directly (rather than toggling
        # settings.TESTING globally) so CSRF enforcement — which also keys off
        # TESTING — stays bypassed and only the CAPTCHA behavior is exercised.
        import api.public as public_api

        monkeypatch.setattr(public_api, "captcha_required", lambda: True)
        monkeypatch.setattr(public_api, "verify_captcha", lambda token: False)

        resp = client.post(
            "/api/contact",
            json={
                "name": "Test User",
                "email": "captcha-test2@example.com",
                "subject": "other",
                "message": "Hello, this is a test message.",
            },
        )
        assert resp.status_code == 400

    def test_contact_form_accepts_when_captcha_enabled_and_token_valid(self, client, test_db, monkeypatch):
        import api.public as public_api

        monkeypatch.setattr(public_api, "captcha_required", lambda: True)
        monkeypatch.setattr(public_api, "verify_captcha", lambda token: token == "good-token")

        resp = client.post(
            "/api/contact",
            json={
                "name": "Test User",
                "email": "captcha-test3@example.com",
                "subject": "other",
                "message": "Hello, this is a test message.",
                "captcha_token": "good-token",
            },
        )
        assert resp.status_code == 200


# ============================================================================
# virus_scan_service
# ============================================================================

class TestVirusScanService:
    def test_disabled_by_default_is_noop(self):
        assert settings.VIRUS_SCAN_ENABLED is False
        virus_scan_service.scan_bytes(b"anything, even eicar-like bytes")  # must not raise

    def test_testing_flag_always_bypasses_even_if_enabled(self, monkeypatch):
        monkeypatch.setattr(settings, "VIRUS_SCAN_ENABLED", True)
        assert settings.TESTING is True
        assert virus_scan_service.scanning_required() is False
        virus_scan_service.scan_bytes(b"anything")  # must not raise

    def test_unsupported_provider_raises_unavailable(self, monkeypatch):
        monkeypatch.setattr(settings, "TESTING", False)
        monkeypatch.setattr(settings, "VIRUS_SCAN_ENABLED", True)
        monkeypatch.setattr(settings, "VIRUS_SCAN_PROVIDER", "not-clamav")
        with pytest.raises(virus_scan_service.VirusScanUnavailable):
            virus_scan_service.scan_bytes(b"content")

    def test_scanner_unreachable_fails_closed(self, monkeypatch):
        monkeypatch.setattr(settings, "TESTING", False)
        monkeypatch.setattr(settings, "VIRUS_SCAN_ENABLED", True)

        def _raise(*a, **k):
            raise OSError("connection refused")

        monkeypatch.setattr(socket, "create_connection", _raise)
        with pytest.raises(virus_scan_service.VirusScanUnavailable):
            virus_scan_service.scan_bytes(b"content")

    def test_clean_response_does_not_raise(self, monkeypatch):
        monkeypatch.setattr(settings, "TESTING", False)
        monkeypatch.setattr(settings, "VIRUS_SCAN_ENABLED", True)

        class _FakeSocket:
            def __enter__(self):
                return self

            def __exit__(self, *a):
                return False

            def sendall(self, data):
                pass

            def recv(self, n):
                return b"stream: OK\0"

        monkeypatch.setattr(socket, "create_connection", lambda *a, **k: _FakeSocket())
        virus_scan_service.scan_bytes(b"clean content")  # must not raise

    def test_infected_response_raises_virus_found(self, monkeypatch):
        monkeypatch.setattr(settings, "TESTING", False)
        monkeypatch.setattr(settings, "VIRUS_SCAN_ENABLED", True)

        class _FakeSocket:
            def __enter__(self):
                return self

            def __exit__(self, *a):
                return False

            def sendall(self, data):
                pass

            def recv(self, n):
                return b"stream: Eicar-Test-Signature FOUND\0"

        monkeypatch.setattr(socket, "create_connection", lambda *a, **k: _FakeSocket())
        with pytest.raises(virus_scan_service.VirusFoundError) as exc_info:
            virus_scan_service.scan_bytes(b"infected content")
        assert "Eicar" in exc_info.value.signature

    def test_error_message_is_bilingual_and_distinguishes_infected_vs_unavailable(self):
        infected_en = virus_scan_service.scan_error_message("en", infected=True)
        infected_ar = virus_scan_service.scan_error_message("ar", infected=False)
        assert infected_en != infected_ar
        assert "malicious" in infected_en.lower()
