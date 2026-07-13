"""Tests for Phase 4 item 3 (data lineage) and item 4 (narrative NLP insights)."""

DATE_PARAMS = "?period_start=2026-01-01&period_end=2026-03-31"


class TestDataLineage:
    def test_admin_shape(self, client, auth_headers_admin, sample_kindergarten):
        resp = client.get("/api/analytics/data-lineage", headers=auth_headers_admin)
        assert resp.status_code == 200
        data = resp.json()
        assert "sources" in data and isinstance(data["sources"], list) and data["sources"]
        datasets = {s["dataset"] for s in data["sources"]}
        assert {"attendance", "incidents", "daily_reports", "kindergartens", "children"} <= datasets
        for s in data["sources"]:
            for key in ("table", "record_count", "status", "name_ar", "name_en"):
                assert key in s
            assert s["status"] in ("fresh", "recent", "stale", "empty", "unknown")
            assert s["record_count"] >= 0

    def test_kindergartens_count_reflects_seed(self, client, auth_headers_admin, sample_kindergarten):
        resp = client.get("/api/analytics/data-lineage", headers=auth_headers_admin)
        kg = next(s for s in resp.json()["sources"] if s["dataset"] == "kindergartens")
        assert kg["record_count"] >= 1
        assert kg["status"] != "empty"

    def test_rejects_non_admin(self, client, auth_headers_manager):
        resp = client.get("/api/analytics/data-lineage", headers=auth_headers_manager)
        assert resp.status_code == 403


class TestNarrativeSummary:
    def test_admin_produces_narrative(self, client, auth_headers_admin, sample_kindergarten):
        resp = client.get(f"/api/analytics/narrative-summary{DATE_PARAMS}", headers=auth_headers_admin)
        assert resp.status_code == 200
        data = resp.json()
        assert data["narrative_ar"] and data["narrative_en"]
        assert isinstance(data["sentences"], list) and len(data["sentences"]) >= 3
        for s in data["sentences"]:
            assert s["ar"] and s["en"]
            assert s["tone"] in ("positive", "neutral", "warning", "negative")
        # narrative_ar should be the concatenation of the sentence AR fragments
        assert data["sentences"][0]["ar"] in data["narrative_ar"]

    def test_invalid_period_is_422(self, client, auth_headers_admin):
        resp = client.get(
            "/api/analytics/narrative-summary?period_start=2026-03-31&period_end=2026-01-01",
            headers=auth_headers_admin,
        )
        assert resp.status_code == 422

    def test_requires_auth(self, client):
        resp = client.get(f"/api/analytics/narrative-summary{DATE_PARAMS}")
        assert resp.status_code in (401, 403)
