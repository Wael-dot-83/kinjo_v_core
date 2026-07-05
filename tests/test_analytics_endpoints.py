"""
Functional tests for analytics endpoints with real data fixtures.
All tests authenticate as admin and verify response shape and basic values.
"""
import pytest
from datetime import date


START = "2026-04-01"
END = "2026-05-31"
DATE_PARAMS = f"?start_date={START}&end_date={END}"


class TestOverviewEndpoint:
    def test_overview_returns_required_keys(self, client, auth_headers_admin, sample_kindergarten):
        resp = client.get(f"/api/analytics/overview{DATE_PARAMS}", headers=auth_headers_admin)
        assert resp.status_code == 200
        body = resp.json()
        assert "summary" in body
        assert "governorates" in body
        assert "period_start" in body
        assert "period_end" in body

    def test_summary_numeric_fields(self, client, auth_headers_admin, sample_kindergarten):
        resp = client.get("/api/analytics/overview", headers=auth_headers_admin)
        assert resp.status_code == 200
        summary = resp.json()["summary"]
        for field in ("total_kindergartens", "total_children", "attendance_rate", "incident_rate"):
            assert field in summary
            assert isinstance(summary[field], (int, float))


class TestAttendanceByClass:
    def test_by_class_returns_class_list(
        self, client, auth_headers_admin, sample_kindergarten, sample_class, sample_enrollment, sample_attendance
    ):
        url = f"/api/analytics/attendance/by-class?kindergarten_id={sample_kindergarten.id}{DATE_PARAMS[1:]}"
        resp = client.get("?" + url.split("?")[1], headers=auth_headers_admin)
        # Build proper URL
        resp = client.get(
            f"/api/analytics/attendance/by-class?kindergarten_id={sample_kindergarten.id}&start_date={START}&end_date={END}",
            headers=auth_headers_admin
        )
        assert resp.status_code == 200
        body = resp.json()
        assert "classes" in body
        assert isinstance(body["classes"], list)
        assert len(body["classes"]) >= 1
        cls = body["classes"][0]
        assert "class_id" in cls
        assert "attendance_rate" in cls
        assert 0.0 <= cls["attendance_rate"] <= 100.0

    def test_by_class_missing_kg_returns_422(self, client, auth_headers_admin):
        resp = client.get("/api/analytics/attendance/by-class", headers=auth_headers_admin)
        assert resp.status_code == 422


class TestChronicAbsence:
    def test_chronic_absence_shape(
        self, client, auth_headers_admin, sample_enrollment, sample_attendance
    ):
        resp = client.get(
            f"/api/analytics/attendance/chronic-absence{DATE_PARAMS}",
            headers=auth_headers_admin
        )
        assert resp.status_code == 200
        body = resp.json()
        assert "chronically_absent_children" in body
        assert "count" in body
        assert isinstance(body["chronically_absent_children"], list)

    def test_chronic_absence_threshold_100_flags_all(
        self, client, auth_headers_admin, sample_enrollment, sample_attendance
    ):
        resp = client.get(
            f"/api/analytics/attendance/chronic-absence?threshold_pct=100&start_date={START}&end_date={END}",
            headers=auth_headers_admin
        )
        assert resp.status_code == 200
        # threshold=100 means everyone is flagged since no one has perfect attendance
        body = resp.json()
        assert body["count"] >= 1

    def test_chronic_absence_threshold_0_flags_none(
        self, client, auth_headers_admin, sample_enrollment, sample_attendance
    ):
        resp = client.get(
            f"/api/analytics/attendance/chronic-absence?threshold_pct=0&start_date={START}&end_date={END}",
            headers=auth_headers_admin
        )
        assert resp.status_code == 200
        assert resp.json()["count"] == 0


class TestAttendanceByGovernorate:
    def test_by_governorate_shape(
        self, client, auth_headers_admin, sample_kindergarten
    ):
        resp = client.get(
            f"/api/analytics/attendance/by-governorate{DATE_PARAMS}",
            headers=auth_headers_admin
        )
        assert resp.status_code == 200
        body = resp.json()
        assert "governorates" in body
        assert isinstance(body["governorates"], list)
        if body["governorates"]:
            gov = body["governorates"][0]
            assert "governorate" in gov
            assert "attendance_rate" in gov


class TestSupervisorPerformance:
    def test_supervisor_performance_shape(
        self, client, auth_headers_admin, sample_daily_report
    ):
        resp = client.get(
            f"/api/analytics/daily-reports/supervisor-performance{DATE_PARAMS}",
            headers=auth_headers_admin
        )
        assert resp.status_code == 200
        body = resp.json()
        assert "supervisors" in body
        assert isinstance(body["supervisors"], list)
        if body["supervisors"]:
            sup = body["supervisors"][0]
            assert "supervisor_id" in sup
            assert "total_reports" in sup
            assert "completion_rate" in sup

    def test_supervisor_performance_filtered_by_kg(
        self, client, auth_headers_admin, sample_kindergarten, sample_daily_report
    ):
        resp = client.get(
            f"/api/analytics/daily-reports/supervisor-performance?kindergarten_id={sample_kindergarten.id}&start_date={START}&end_date={END}",
            headers=auth_headers_admin
        )
        assert resp.status_code == 200


class TestEnrollmentTrends:
    def test_enrollment_trends_weekly(
        self, client, auth_headers_admin, sample_enrollment
    ):
        resp = client.get(
            f"/api/analytics/enrollment/trends?granularity=weekly{DATE_PARAMS[1:]}",
            headers=auth_headers_admin
        )
        resp = client.get(
            f"/api/analytics/enrollment/trends?granularity=weekly&start_date={START}&end_date={END}",
            headers=auth_headers_admin
        )
        assert resp.status_code == 200
        body = resp.json()
        assert "trends" in body
        assert isinstance(body["trends"], list)
        assert len(body["trends"]) > 0
        entry = body["trends"][0]
        assert "period" in entry
        assert "new_applications" in entry
        assert "cumulative" in entry

    def test_enrollment_trends_monthly(
        self, client, auth_headers_admin, sample_enrollment
    ):
        resp = client.get(
            f"/api/analytics/enrollment/trends?granularity=monthly&start_date={START}&end_date={END}",
            headers=auth_headers_admin
        )
        assert resp.status_code == 200
        body = resp.json()
        assert body["granularity"] == "monthly"

    def test_enrollment_trends_invalid_granularity(self, client, auth_headers_admin):
        resp = client.get(
            "/api/analytics/enrollment/trends?granularity=daily",
            headers=auth_headers_admin
        )
        assert resp.status_code == 422

    def test_enrollment_trends_cumulative_is_monotonic(
        self, client, auth_headers_admin, sample_enrollment
    ):
        resp = client.get(
            f"/api/analytics/enrollment/trends?granularity=weekly&start_date={START}&end_date={END}",
            headers=auth_headers_admin
        )
        assert resp.status_code == 200
        trends = resp.json()["trends"]
        for i in range(1, len(trends)):
            assert trends[i]["cumulative"] >= trends[i - 1]["cumulative"]


class TestKPINetworkSummary:
    def test_kpi_network_summary_shape(
        self, client, auth_headers_admin, sample_kindergarten
    ):
        resp = client.get("/api/kpi/network-summary", headers=auth_headers_admin)
        assert resp.status_code == 200
        body = resp.json()
        for field in ("kindergarten_count", "avg_attendance_rate", "avg_incident_rate",
                      "avg_ratio_compliance", "avg_gqi_score", "per_kindergarten"):
            assert field in body

    def test_kpi_network_summary_per_kg_fields(
        self, client, auth_headers_admin, sample_kindergarten
    ):
        resp = client.get("/api/kpi/network-summary", headers=auth_headers_admin)
        assert resp.status_code == 200
        body = resp.json()
        if body["per_kindergarten"]:
            kg = body["per_kindergarten"][0]
            assert "kindergarten_id" in kg
            assert "attendance_rate" in kg
            assert "governance_band" in kg
            assert kg["governance_band"] in ("RED", "AMBER", "GREEN", "INSUFFICIENT")
            # kindergarten_name/governorate were missing entirely -- the
            # /admin/kpi table, chart labels, and search box all read these
            # fields and rendered/matched nothing without them.
            assert "kindergarten_name" in kg
            assert kg["kindergarten_name"]
            assert "governorate" in kg
            assert kg["governorate"]

    def test_kpi_network_summary_governorate_filter(
        self, client, auth_headers_admin, sample_kindergarten
    ):
        """The frontend's governorate dropdown sent a `governorate` query
        param that the endpoint silently ignored (no such parameter
        existed), so selecting a governorate never filtered anything."""
        resp = client.get("/api/kpi/network-summary", headers=auth_headers_admin)
        body = resp.json()
        if not body["per_kindergarten"]:
            return
        gov = body["per_kindergarten"][0]["governorate"]
        filtered = client.get(
            "/api/kpi/network-summary",
            params={"governorate": gov},
            headers=auth_headers_admin,
        ).json()
        assert filtered["kindergarten_count"] <= body["kindergarten_count"]
        assert all(kg["governorate"] == gov for kg in filtered["per_kindergarten"])
