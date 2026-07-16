"""Manager dashboard licence-expiry alert wording.

An expired licence was reported as "License expires in -5 days", because one
message template served both sides of the expiry date. The alert text is also
shown in an Arabic-primary UI, so it must carry both language variants rather
than English only.
"""
from datetime import date, timedelta

import models

MANAGER_DASHBOARD_URL = "/api/manager/dashboard"


def _license_alert(client, headers):
    r = client.get(MANAGER_DASHBOARD_URL, headers=headers)
    assert r.status_code == 200, r.text
    alerts = [a for a in r.json()["alerts"] if a["type"] == "license_expiry"]
    return alerts[0] if alerts else None


class TestLicenseExpiryWording:
    def test_expired_license_is_not_worded_as_negative_days(
        self, client, test_db, sample_kindergarten, manager_user, auth_headers_manager
    ):
        """Regression: produced 'License expires in -5 days'."""
        sample_kindergarten.license_valid_until = date.today() - timedelta(days=5)
        test_db.commit()

        alert = _license_alert(client, auth_headers_manager)
        assert alert is not None, "an expired licence must still raise an alert"
        assert "-" not in alert["message_en"], f"negative-day wording leaked: {alert['message_en']!r}"
        assert "expired" in alert["message_en"].lower()
        assert "5" in alert["message_en"]
        assert alert["priority"] == "critical"

    def test_expiring_license_uses_future_wording(
        self, client, test_db, sample_kindergarten, manager_user, auth_headers_manager
    ):
        sample_kindergarten.license_valid_until = date.today() + timedelta(days=10)
        test_db.commit()

        alert = _license_alert(client, auth_headers_manager)
        assert alert is not None
        assert "expires in" in alert["message_en"].lower()
        assert "10" in alert["message_en"]
        assert alert["priority"] == "high"

    def test_license_expiring_today_is_not_reported_as_expired(
        self, client, test_db, sample_kindergarten, manager_user, auth_headers_manager
    ):
        """Boundary: 0 days left is still valid today, not lapsed."""
        sample_kindergarten.license_valid_until = date.today()
        test_db.commit()

        alert = _license_alert(client, auth_headers_manager)
        assert alert is not None
        assert "expired" not in alert["message_en"].lower()
        assert alert["priority"] == "high"

    def test_far_future_license_raises_no_alert(
        self, client, test_db, sample_kindergarten, manager_user, auth_headers_manager
    ):
        sample_kindergarten.license_valid_until = date.today() + timedelta(days=365)
        test_db.commit()

        assert _license_alert(client, auth_headers_manager) is None


class TestAlertsAreBilingual:
    def test_every_alert_carries_both_languages(
        self, client, test_db, sample_kindergarten, sample_child, manager_user,
        auth_headers_manager
    ):
        """The UI is Arabic-primary; an English-only alert cannot be rendered."""
        sample_kindergarten.license_valid_until = date.today() - timedelta(days=3)
        test_db.commit()
        test_db.add(models.EnrollmentApplication(
            child_id=sample_child.id,
            kindergarten_id=sample_kindergarten.id,
            status=models.EnrollmentStatus.PENDING_REVIEW,
        ))
        test_db.commit()

        r = client.get(MANAGER_DASHBOARD_URL, headers=auth_headers_manager)
        assert r.status_code == 200, r.text
        alerts = r.json()["alerts"]
        assert alerts, "expected at least one alert for this fixture"
        for alert in alerts:
            assert alert.get("message_ar"), f"alert missing Arabic text: {alert}"
            assert alert.get("message_en"), f"alert missing English text: {alert}"
            # `message` is retained as a compatibility alias for the English text.
            assert alert["message"] == alert["message_en"]
