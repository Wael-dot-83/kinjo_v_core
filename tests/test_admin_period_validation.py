"""Custom-period validation for the admin endpoints that accept `period=custom`.

Both endpoints previously resolved invalid custom input by silently substituting
their default window:

* `/api/admin/dashboard/activity` matched `period == "custom" and start_date and
  end_date`, so `period=custom` with a missing date applied *no* date filter at
  all and returned the full history.
* `/api/admin/kg-overview` documented `custom` but accepted no dates and fell
  through its `else` branch to a 30-day window — as did any unknown period.

Answering a different question than the caller asked, with a 200, is the defect
these tests pin down.
"""
from datetime import date, timedelta

import pytest

ACTIVITY_URL = "/api/admin/dashboard/activity"
KG_OVERVIEW_URL = "/api/admin/kg-overview"


class TestActivityPeriodValidation:
    def test_custom_without_dates_is_rejected(self, client, admin_user, auth_headers_admin):
        r = client.get(ACTIVITY_URL, params={"period": "custom"}, headers=auth_headers_admin)
        assert r.status_code == 422, r.text
        assert "start_date" in r.json()["detail"]

    def test_custom_with_only_start_is_rejected(self, client, admin_user, auth_headers_admin):
        r = client.get(
            ACTIVITY_URL,
            params={"period": "custom", "start_date": "2026-01-01"},
            headers=auth_headers_admin,
        )
        assert r.status_code == 422, r.text

    def test_reversed_range_is_rejected(self, client, admin_user, auth_headers_admin):
        r = client.get(
            ACTIVITY_URL,
            params={"period": "custom", "start_date": "2026-06-30", "end_date": "2026-06-01"},
            headers=auth_headers_admin,
        )
        assert r.status_code == 422, r.text
        assert "on or before" in r.json()["detail"]

    def test_excessive_range_is_rejected(self, client, admin_user, auth_headers_admin):
        r = client.get(
            ACTIVITY_URL,
            params={"period": "custom", "start_date": "2020-01-01", "end_date": "2026-01-01"},
            headers=auth_headers_admin,
        )
        assert r.status_code == 422, r.text
        assert "exceed" in r.json()["detail"]

    def test_unknown_period_is_rejected(self, client, admin_user, auth_headers_admin):
        r = client.get(ACTIVITY_URL, params={"period": "banana"}, headers=auth_headers_admin)
        assert r.status_code == 422, r.text

    def test_valid_custom_range_is_accepted(self, client, admin_user, auth_headers_admin):
        today = date.today()
        r = client.get(
            ACTIVITY_URL,
            params={
                "period": "custom",
                "start_date": (today - timedelta(days=7)).isoformat(),
                "end_date": today.isoformat(),
            },
            headers=auth_headers_admin,
        )
        assert r.status_code == 200, r.text

    def test_single_day_range_is_accepted(self, client, admin_user, auth_headers_admin):
        """start == end is one inclusive day, not an empty window."""
        today = date.today().isoformat()
        r = client.get(
            ACTIVITY_URL,
            params={"period": "custom", "start_date": today, "end_date": today},
            headers=auth_headers_admin,
        )
        assert r.status_code == 200, r.text

    @pytest.mark.parametrize("period", ["today", "24h", "7d", "30d", "month"])
    def test_preset_periods_still_work(self, client, admin_user, auth_headers_admin, period):
        r = client.get(ACTIVITY_URL, params={"period": period}, headers=auth_headers_admin)
        assert r.status_code == 200, r.text

    def test_omitted_period_still_works(self, client, admin_user, auth_headers_admin):
        r = client.get(ACTIVITY_URL, headers=auth_headers_admin)
        assert r.status_code == 200, r.text


class TestKgOverviewPeriodValidation:
    def test_custom_without_dates_is_rejected(self, client, admin_user, auth_headers_admin):
        """Regression: `custom` was documented but silently became a 30-day window."""
        r = client.get(KG_OVERVIEW_URL, params={"period": "custom"}, headers=auth_headers_admin)
        assert r.status_code == 422, r.text

    def test_unknown_period_is_rejected(self, client, admin_user, auth_headers_admin):
        """Regression: any unknown period fell through `else` to 30 days."""
        r = client.get(KG_OVERVIEW_URL, params={"period": "banana"}, headers=auth_headers_admin)
        assert r.status_code == 422, r.text

    def test_reversed_range_is_rejected(self, client, admin_user, auth_headers_admin):
        r = client.get(
            KG_OVERVIEW_URL,
            params={"period": "custom", "start_date": "2026-06-30", "end_date": "2026-06-01"},
            headers=auth_headers_admin,
        )
        assert r.status_code == 422, r.text

    def test_valid_custom_range_is_accepted(self, client, admin_user, auth_headers_admin):
        today = date.today()
        r = client.get(
            KG_OVERVIEW_URL,
            params={
                "period": "custom",
                "start_date": (today - timedelta(days=7)).isoformat(),
                "end_date": today.isoformat(),
            },
            headers=auth_headers_admin,
        )
        assert r.status_code == 200, r.text

    @pytest.mark.parametrize("period", ["today", "week", "month"])
    def test_preset_periods_still_work(self, client, admin_user, auth_headers_admin, period):
        r = client.get(KG_OVERVIEW_URL, params={"period": period}, headers=auth_headers_admin)
        assert r.status_code == 200, r.text
