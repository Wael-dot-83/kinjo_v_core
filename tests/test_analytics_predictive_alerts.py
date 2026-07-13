"""Tests for Phase 4 item 2 (predictive alerts) and P3a (Islamic-holiday annotations)."""
from datetime import date, timedelta

from analytics_domain import SeriesPoint
from analytics_service import (
    _forecast_breach_alert,
    _get_jordan_holidays,
    get_predictive_alerts,
)


# --- Endpoint: shape, RBAC, validation --------------------------------------
class TestPredictiveAlertsEndpoint:
    def test_admin_gets_well_formed_payload(self, client, auth_headers_admin):
        resp = client.get("/api/analytics/predictive-alerts", headers=auth_headers_admin)
        assert resp.status_code == 200
        data = resp.json()
        for key in ("generated_at", "horizon_days", "alerts", "count"):
            assert key in data
        assert isinstance(data["alerts"], list)
        assert data["count"] == len(data["alerts"])

    def test_rejects_non_admin(self, client, auth_headers_manager):
        resp = client.get("/api/analytics/predictive-alerts", headers=auth_headers_manager)
        assert resp.status_code == 403

    def test_requires_auth(self, client):
        resp = client.get("/api/analytics/predictive-alerts")
        assert resp.status_code in (401, 403)

    def test_horizon_out_of_range_is_422(self, client, auth_headers_admin):
        resp = client.get(
            "/api/analytics/predictive-alerts?horizon_days=999", headers=auth_headers_admin
        )
        assert resp.status_code == 422


# --- Unit: the breach detector ----------------------------------------------
class TestForecastBreachAlert:
    def _series(self, values):
        start = date(2026, 1, 1)
        return [SeriesPoint(date=start + timedelta(days=i), value=v) for i, v in enumerate(values)]

    def test_declining_attendance_breaches_target(self):
        today = date(2026, 1, 30)
        series = self._series([95 - i for i in range(30)])  # 95 -> 66, clearly falling
        alert = _forecast_breach_alert(
            series, horizon_days=14, today=today, threshold=85.0,
            higher_is_better=True, metric="attendance", unit="%",
            name_ar="الحضور", name_en="Attendance",
        )
        assert alert is not None
        assert alert["metric"] == "attendance"
        assert alert["severity"] in ("HIGH", "MEDIUM", "LOW")
        assert alert["predicted_value"] < 85.0
        assert alert["message_ar"] and alert["message_en"]

    def test_healthy_attendance_no_alert(self):
        today = date(2026, 1, 30)
        series = self._series([95.0] * 30)  # flat, well above target
        alert = _forecast_breach_alert(
            series, horizon_days=14, today=today, threshold=85.0,
            higher_is_better=True, metric="attendance", unit="%",
            name_ar="الحضور", name_en="Attendance",
        )
        assert alert is None

    def test_too_short_series_returns_none(self):
        alert = _forecast_breach_alert(
            self._series([90, 88, 80]), horizon_days=14, today=date(2026, 1, 4),
            threshold=85.0, higher_is_better=True, metric="attendance", unit="%",
            name_ar="الحضور", name_en="Attendance",
        )
        assert alert is None


# --- Unit: P3a Islamic + fixed holidays -------------------------------------
class TestJordanHolidays:
    def test_islamic_and_fixed_merged(self):
        names = {h["name_en"] for h in _get_jordan_holidays(date(2026, 1, 1), date(2026, 12, 31))}
        assert {"Eid al-Fitr", "Eid al-Adha", "Islamic New Year", "Prophet's Birthday"} <= names
        assert {"Labour Day", "Independence Day"} <= names  # fixed still present

    def test_all_entries_bilingual(self):
        for h in _get_jordan_holidays(date(2025, 1, 1), date(2027, 12, 31)):
            assert h["name_ar"] and h["name_en"] and isinstance(h["date"], date)

    def test_year_without_table_does_not_crash(self):
        assert isinstance(_get_jordan_holidays(date(2030, 1, 1), date(2030, 12, 31)), list)
