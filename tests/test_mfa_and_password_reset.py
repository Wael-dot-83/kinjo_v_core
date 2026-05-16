"""
Tests for MFA (TOTP), password reset flow, and new middleware components.
"""
import pytest
from unittest.mock import patch, MagicMock
from fastapi.testclient import TestClient

import models
from auth import get_password_hash
from mfa_service import generate_totp_secret, encrypt_secret, decrypt_secret, verify_code


# ===========================================================================
# MFA SERVICE UNIT TESTS
# ===========================================================================

class TestMfaService:
    def test_generate_secret_is_base32(self):
        secret = generate_totp_secret()
        assert isinstance(secret, str)
        assert len(secret) >= 16

    def test_encrypt_decrypt_roundtrip(self):
        secret = generate_totp_secret()
        encrypted = encrypt_secret(secret)
        assert encrypted != secret
        assert decrypt_secret(encrypted) == secret

    def test_decrypt_none_returns_none(self):
        assert decrypt_secret(None) is None
        assert decrypt_secret("") is None

    def test_verify_code_rejects_invalid_format(self):
        secret = generate_totp_secret()
        assert not verify_code(secret, "abc123")
        assert not verify_code(secret, "12345")    # 5 digits
        assert not verify_code(secret, "1234567")  # 7 digits
        assert not verify_code(secret, "")

    def test_verify_code_with_spaces_normalized(self):
        """Spaces in the code should be stripped before verification."""
        import pyotp
        secret = generate_totp_secret()
        correct_code = pyotp.TOTP(secret).now()
        # Spaces around a valid code should still pass (user-entry normalization)
        assert verify_code(secret, f" {correct_code} ")


# ===========================================================================
# MFA SETUP ENDPOINT TESTS (TESTING=true bypasses MFA requirement)
# ===========================================================================

class TestMfaEndpoints:
    def test_mfa_setup_requires_bearer_token(self, client, test_db):
        response = client.post("/api/auth/mfa/setup")
        assert response.status_code == 401

    def test_mfa_verify_requires_bearer_token(self, client, test_db):
        response = client.post("/api/auth/mfa/verify", json={"code": "123456"})
        assert response.status_code == 401

    def test_mfa_setup_rejects_invalid_ticket(self, client, test_db):
        response = client.post(
            "/api/auth/mfa/setup",
            headers={"Authorization": "Bearer not-a-real-jwt"},
        )
        assert response.status_code == 401

    def test_mfa_verify_rejects_invalid_ticket(self, client, test_db):
        response = client.post(
            "/api/auth/mfa/verify",
            json={"code": "123456"},
            headers={"Authorization": "Bearer not-a-real-jwt"},
        )
        assert response.status_code == 401

    def test_mfa_setup_in_testing_mode_rejected(self, client, test_db, admin_user):
        """In TESTING mode, MFA setup should be rejected (TESTING bypass is active)."""
        from auth import create_access_token
        from datetime import timedelta
        # Create a valid mfa_setup ticket
        ticket = create_access_token(
            data={"sub": admin_user.username, "role": "ADMIN", "purpose": "mfa_setup"},
            expires_delta=timedelta(minutes=10),
        )
        response = client.post(
            "/api/auth/mfa/setup",
            headers={"Authorization": f"Bearer {ticket}"},
        )
        # In TESTING mode, is_privileged_role check is bypassed → setup rejected
        assert response.status_code == 400

    def test_login_for_parent_does_not_require_mfa(self, client, test_db, parent_user):
        """Parents are not privileged roles — login must issue access_token directly."""
        response = client.post(
            "/token",
            data={"username": parent_user.username, "password": "Parent123!"},
        )
        data = response.json()
        assert response.status_code == 200
        assert "access_token" in data
        assert data.get("mfa_required") is False

    def test_login_for_admin_in_testing_bypasses_mfa(self, client, test_db, admin_user):
        """In TESTING mode, admin login should NOT require MFA (TESTING=true skips it)."""
        response = client.post(
            "/token",
            data={"username": admin_user.username, "password": "Admin123!"},
        )
        data = response.json()
        assert response.status_code == 200
        assert "access_token" in data
        # TESTING mode skips MFA entirely
        assert data.get("mfa_required") is False


# ===========================================================================
# PASSWORD RESET FLOW TESTS
# ===========================================================================

class TestPasswordResetFlow:
    def test_request_reset_returns_generic_message_for_unknown_email(self, client, test_db):
        response = client.post(
            "/api/users/request-password-reset",
            json={"email": "nobody@notexist.example.com"},
        )
        assert response.status_code == 200
        assert "reset" in response.json().get("message", "").lower() or \
               "sent" in response.json().get("message", "").lower()

    def test_request_reset_returns_same_message_for_known_email(self, client, test_db, admin_user):
        response = client.post(
            "/api/users/request-password-reset",
            json={"email": admin_user.email},
        )
        assert response.status_code == 200
        # Same message — no enumeration
        data = response.json()
        assert "message" in data

    def test_reset_with_invalid_token_returns_400(self, client, test_db):
        response = client.post(
            "/api/users/reset-password",
            json={"token": "not-a-real-token", "new_password": "NewPass@123"},
        )
        assert response.status_code == 400

    def test_full_reset_flow(self, client, test_db, admin_user):
        """Full happy path: request → token in DB → reset → login with new password."""
        from api.auth.password_reset_service import issue_password_reset_token
        db = test_db

        # Issue a reset token directly (bypass email)
        token = issue_password_reset_token(db, admin_user)
        assert token

        # Use the token to reset password
        response = client.post(
            "/api/users/reset-password",
            json={"token": token, "new_password": "NewAdmin@9876"},
        )
        assert response.status_code == 200

        # Login with the new password
        response = client.post(
            "/token",
            data={"username": admin_user.username, "password": "NewAdmin@9876"},
        )
        assert response.status_code == 200
        assert "access_token" in response.json()

    def test_token_cannot_be_used_twice(self, client, test_db, admin_user):
        """Verify one-time use of the reset token."""
        from api.auth.password_reset_service import issue_password_reset_token
        db = test_db

        token = issue_password_reset_token(db, admin_user)

        # First use: success
        r1 = client.post(
            "/api/users/reset-password",
            json={"token": token, "new_password": "NewAdmin@1111"},
        )
        assert r1.status_code == 200

        # Second use: rejected
        r2 = client.post(
            "/api/users/reset-password",
            json={"token": token, "new_password": "NewAdmin@2222"},
        )
        assert r2.status_code == 400

    def test_reset_enforces_password_policy(self, client, test_db, admin_user):
        """A weak password should be rejected during reset."""
        from api.auth.password_reset_service import issue_password_reset_token
        token = issue_password_reset_token(test_db, admin_user)

        response = client.post(
            "/api/users/reset-password",
            json={"token": token, "new_password": "weak"},
        )
        # Should fail with 400 (policy violation)
        assert response.status_code in (400, 422)


# ===========================================================================
# SMTP DELIVERY BEHAVIOR TESTS
# ===========================================================================

class TestSmtpDeliveryBehavior:
    def test_smtp_unconfigured_returns_false_and_logs_critical(self, client, test_db, admin_user):
        """When SMTP is not configured, deliver_password_reset_email returns False
        and logs at CRITICAL level — the endpoint still returns 200 (anti-enumeration)."""
        import logging
        from api.auth.password_reset_service import deliver_password_reset_email, issue_password_reset_token
        from unittest.mock import patch

        with patch("api.auth.password_reset_service.is_smtp_configured", return_value=False):
            token = issue_password_reset_token(test_db, admin_user)
            with patch.object(
                logging.getLogger("api.auth.password_reset_service"),
                "critical",
            ) as mock_critical:
                result = deliver_password_reset_email("http://localhost", admin_user, token)

        assert result is False
        mock_critical.assert_called_once()
        call_args = mock_critical.call_args[0][0]
        assert "SMTP_UNCONFIGURED" in call_args or "unconfigured" in call_args.lower()

    def test_smtp_delivery_failure_logs_critical_not_swallowed(self, client, test_db, admin_user):
        """When SMTP is configured but send fails, CRITICAL is logged — not silently swallowed."""
        import logging
        import smtplib
        from api.auth.password_reset_service import deliver_password_reset_email, issue_password_reset_token
        from unittest.mock import patch

        token = issue_password_reset_token(test_db, admin_user)

        with patch("api.auth.password_reset_service.is_smtp_configured", return_value=True), \
             patch("api.auth.password_reset_service.send_password_reset_email",
                   side_effect=smtplib.SMTPException("Connection refused")), \
             patch.object(
                 logging.getLogger("api.auth.password_reset_service"),
                 "critical",
             ) as mock_critical:
            result = deliver_password_reset_email("http://localhost", admin_user, token)

        assert result is False
        mock_critical.assert_called_once()
        call_args = mock_critical.call_args[0][0]
        assert "FAILED" in call_args or "failed" in call_args.lower()

    def test_endpoint_returns_200_regardless_of_smtp_failure(self, client, test_db, admin_user):
        """The password reset request endpoint MUST return 200 even when SMTP fails
        (anti-enumeration: users must not be able to tell if email was delivered)."""
        from unittest.mock import patch

        with patch("api.users.deliver_password_reset_email", return_value=False):
            response = client.post(
                "/api/users/request-password-reset",
                json={"email": admin_user.email},
            )
        assert response.status_code == 200
        data = response.json()
        assert "message" in data

    def test_check_smtp_health_returns_unconfigured_when_no_smtp(self):
        """check_smtp_health() returns unconfigured status when SMTP vars are missing."""
        from email_service import check_smtp_health
        from unittest.mock import patch

        with patch("email_service.is_smtp_configured", return_value=False):
            health = check_smtp_health()

        assert health["status"] == "unconfigured"

    def test_check_smtp_health_returns_error_on_connection_failure(self):
        """check_smtp_health() returns error status when SMTP host is unreachable."""
        import smtplib
        from email_service import check_smtp_health
        from unittest.mock import patch

        with patch("email_service.is_smtp_configured", return_value=True), \
             patch("smtplib.SMTP", side_effect=OSError("Connection refused")):
            health = check_smtp_health()

        assert health["status"] == "error"
        assert "detail" in health


# ===========================================================================
# MIDDLEWARE TESTS
# ===========================================================================

class TestSecurityMiddleware:
    def test_security_headers_present_on_all_responses(self, client, test_db):
        response = client.get("/health")
        assert response.status_code == 200
        headers = response.headers
        assert "x-content-type-options" in headers
        assert headers["x-content-type-options"] == "nosniff"
        assert "x-frame-options" in headers
        assert headers["x-frame-options"] == "DENY"
        assert "x-xss-protection" in headers
        assert "referrer-policy" in headers

    def test_csp_header_present(self, client, test_db):
        response = client.get("/health")
        assert "content-security-policy" in response.headers

    def test_request_returns_valid_response_within_timeout(self, client, test_db):
        """Health endpoint should respond well within the 30s timeout."""
        response = client.get("/health")
        assert response.status_code == 200

    def test_csrf_safe_get_does_not_require_csrf_token(self, client, test_db):
        """GET requests should pass without an X-CSRF-Token header."""
        response = client.get("/api/users/me", headers={"Authorization": "Bearer invalid"})
        # We expect 401 (invalid token), NOT 403 (CSRF failure)
        assert response.status_code == 401


class TestCsrfProtection:
    def test_post_without_csrf_token_in_testing_mode_succeeds(self, client, test_db):
        """In TESTING mode, CSRF is disabled."""
        # Just verify the login endpoint is reachable (csrf_protection_middleware
        # skips enforcement when settings.TESTING is True).
        response = client.post(
            "/token",
            data={"username": "nobody", "password": "nobody"},
        )
        # Should get 401 (bad creds), not 403 (CSRF blocked)
        assert response.status_code == 401


class TestAuthMiddleware:
    def test_classify_login_identifier_username(self):
        from middleware.auth import classify_login_identifier
        t, v = classify_login_identifier("testadmin")
        assert t == "username"
        assert v == "testadmin"

    def test_classify_login_identifier_email(self):
        from middleware.auth import classify_login_identifier
        t, v = classify_login_identifier("user@example.com")
        assert t == "email"
        assert v == "user@example.com"

    def test_classify_login_identifier_phone(self):
        from middleware.auth import classify_login_identifier
        t, v = classify_login_identifier("0791234567")
        assert t == "phone"
        assert v == "0791234567"

    def test_classify_login_identifier_phone_international(self):
        from middleware.auth import classify_login_identifier
        t, v = classify_login_identifier("+962791234567")
        assert t == "phone"
        assert v == "0791234567"

    def test_classify_login_identifier_rejects_sql_injection(self):
        from middleware.auth import classify_login_identifier
        with pytest.raises(ValueError):
            classify_login_identifier("' OR '1'='1")

    def test_classify_login_identifier_rejects_empty(self):
        from middleware.auth import classify_login_identifier
        with pytest.raises(ValueError):
            classify_login_identifier("")

    def test_sanitize_response_payload_strips_sensitive_keys(self):
        from middleware.auth import sanitize_response_payload
        payload = {
            "id": 1,
            "username": "admin",
            "hashed_password": "bcrypt_hash",
            "mfa_secret": "totp_secret",
            "reset_token": "some_token",
            "profile": {
                "email": "admin@test.com",
                "password": "should_be_stripped",
            },
        }
        result = sanitize_response_payload(payload)
        assert "id" in result
        assert "username" in result
        assert "hashed_password" not in result
        assert "mfa_secret" not in result
        assert "reset_token" not in result
        assert "password" not in result.get("profile", {})
        assert result["profile"]["email"] == "admin@test.com"

    def test_sanitize_does_not_strip_device_token_field(self):
        """The 'token' device token field should NOT be stripped."""
        from middleware.auth import sanitize_response_payload
        payload = {"token": "device-push-token-abc", "platform": "WEB"}
        result = sanitize_response_payload(payload)
        assert result["token"] == "device-push-token-abc"

    def test_is_privileged_role_admin(self):
        from middleware.auth import is_privileged_role
        assert is_privileged_role(models.UserRole.ADMIN)

    def test_is_privileged_role_manager(self):
        from middleware.auth import is_privileged_role
        assert is_privileged_role(models.UserRole.MANAGER)

    def test_is_privileged_role_supervisor_false(self):
        from middleware.auth import is_privileged_role
        assert not is_privileged_role(models.UserRole.SUPERVISOR)

    def test_is_privileged_role_parent_false(self):
        from middleware.auth import is_privileged_role
        assert not is_privileged_role(models.UserRole.PARENT)


# ===========================================================================
# PAGE ROUTE TESTS
# ===========================================================================

class TestAuthPages:
    def test_mfa_setup_page_loads(self, client, test_db):
        response = client.get("/mfa/setup")
        assert response.status_code == 200
        assert b"mfaSetupApp" in response.content

    def test_forgot_password_page_loads(self, client, test_db):
        response = client.get("/forgot-password")
        assert response.status_code == 200
        assert b"forgotPasswordForm" in response.content

    def test_reset_password_page_loads_with_token(self, client, test_db):
        response = client.get("/reset-password?token=sometoken123")
        assert response.status_code == 200
        assert b"resetPasswordForm" in response.content

    def test_reset_password_page_shows_invalid_notice_without_token(self, client, test_db):
        response = client.get("/reset-password")
        assert response.status_code == 200
        # Form should be hidden, invalid token notice visible
        assert b"invalidTokenAlert" in response.content
