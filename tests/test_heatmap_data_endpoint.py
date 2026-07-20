"""Regression coverage for GET /api/admin/heatmap-data.

This endpoint had no test at all, which is why it returned 500 in production
while the suite was green. `children_registration` became correctly unavailable
(None) in 49b85238, but the handler did:

    int(g.get("main_indicators", {}).get("children_registration", 0))

dict.get(key, default) returns None when the key exists with a None value, so
the default never applied and int(None) raised TypeError.

It was also a category error: children_registration is a 0-100 indicator, not a
headcount. Counts now travel in their own kg_count / student_count fields.
"""
import pytest


class TestHeatmapDataEndpoint:
    def test_returns_200_with_unavailable_indicators(self, client, auth_headers_admin):
        """The defining regression: an unavailable indicator must not 500."""
        r = client.get("/api/admin/heatmap-data", headers=auth_headers_admin)
        assert r.status_code == 200, r.text

    def test_counts_are_integers_not_decoded_indicators(self, client, auth_headers_admin):
        r = client.get("/api/admin/heatmap-data", headers=auth_headers_admin)
        assert r.status_code == 200, r.text
        payload = r.json()
        governorates = payload.get("data", payload)
        assert isinstance(governorates, dict) and governorates

        for slug, entry in governorates.items():
            assert isinstance(entry["kindergarten_count"], int), slug
            assert isinstance(entry["children_count"], int), slug
            assert entry["kindergarten_count"] >= 0, slug
            assert entry["children_count"] >= 0, slug

    def test_unavailable_indicator_is_not_fabricated_as_zero(self, client, auth_headers_admin):
        """children_registration must stay unavailable, never become a number."""
        r = client.get("/api/admin/heatmap-data", headers=auth_headers_admin)
        assert r.status_code == 200, r.text
        governorates = r.json().get("data", r.json())
        for slug, entry in governorates.items():
            value = (entry.get("main_indicators") or {}).get("children_registration")
            assert value is None, (
                f"{slug}: children_registration has no defensible population "
                f"denominator and must be reported unavailable, got {value!r}"
            )

    def test_governance_score_stays_unavailable_not_zero(self, client, auth_headers_admin):
        """0 is the worst governance band — it must not stand in for 'unmeasured'.

        tasks_governance is legitimately None when no GovernanceScore rows exist.
        Defaulting it to 0 reported every un-assessed governorate as failing.
        """
        r = client.get("/api/admin/heatmap-data", headers=auth_headers_admin)
        assert r.status_code == 200, r.text
        for slug, entry in r.json()["data"].items():
            indicator = (entry.get("main_indicators") or {}).get("tasks_governance")
            if indicator is None:
                assert entry["governance_score"] is None, (
                    f"{slug}: governance unavailable but reported as "
                    f"{entry['governance_score']!r}"
                )

    def test_incidents_total_is_a_count_not_a_decoded_score(self, client, auth_headers_admin):
        """incidents_total must come from the real count field.

        It was derived as 100 - safety_incidents. On the service path
        safety_incidents = 100 - critical*10, so the result was ten times the
        *critical* count, ignored every non-critical incident, and saturated at
        100 — three different ways of not being the incident total.
        """
        r = client.get("/api/admin/heatmap-data", headers=auth_headers_admin)
        assert r.status_code == 200, r.text
        for slug, entry in r.json()["data"].items():
            total = entry["incidents_total"]
            assert isinstance(total, int) and total >= 0, f"{slug}: {total!r}"
            safety = (entry.get("main_indicators") or {}).get("safety_incidents")
            if safety is not None and total != 0:
                assert total != int(100 - safety) or safety == 100 - total, (
                    f"{slug}: incidents_total still looks decoded from safety_incidents"
                )

    def test_requires_admin(self, client):
        r = client.get("/api/admin/heatmap-data")
        assert r.status_code in (401, 403)

    def test_no_empty_phantom_governorate_entries(self, client, auth_headers_admin):
        """Every returned governorate must carry data.

        The response model declared `tafilah` while the canonical slug is
        `tafileh`; with extra='allow' the real data arrived under the undeclared
        name and the declared field stayed {} forever.
        """
        r = client.get("/api/admin/heatmap-data", headers=auth_headers_admin)
        assert r.status_code == 200, r.text
        empty = [slug for slug, entry in r.json()["data"].items() if not entry]
        assert not empty, f"governorate keys returned with no data: {empty}"


class TestSchemaMatchesCanonicalSlugs:
    def test_response_model_fields_match_canonical_governorates(self):
        """Guards the slug drift that produced the phantom empty entry."""
        from admin_endpoints import HeatmapGovernorateData
        from heatmap.backend.constants import GOVERNORATES

        declared = set(HeatmapGovernorateData.model_fields)
        canonical = {g["slug"] for g in GOVERNORATES}
        assert declared == canonical, (
            f"schema/constants slug drift — only in schema: "
            f"{sorted(declared - canonical)}; only in constants: "
            f"{sorted(canonical - declared)}"
        )
