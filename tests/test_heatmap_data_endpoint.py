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
        data = r.json()["data"]
        # The seed DB has no GovernanceScore rows, so governance is unavailable
        # everywhere. Assert it unconditionally: not one governorate may report a
        # fabricated numeric governance_score (0 would render as the worst band).
        assert data, "expected governorate data"
        for slug, entry in data.items():
            indicator = (entry.get("main_indicators") or {}).get("tasks_governance")
            assert indicator is None, f"{slug}: expected unavailable governance in seed state"
            assert entry["governance_score"] is None, (
                f"{slug}: governance unavailable but reported as "
                f"{entry['governance_score']!r} (0 would read as 'failing')"
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

    def test_incidents_total_reflects_real_count(
        self, client, test_db, sample_kindergarten, sample_class, sample_child,
        admin_user, auth_headers_admin,
    ):
        """Seed real incidents and assert the reported total equals their count.

        Non-vacuous by construction: 3 NON-critical incidents in Amman (the
        sample kindergarten's governorate).
          * old service decode 100 - (100 - critical*10) = critical*10 -> 0
          * old fallback decode total*5                                -> 15
          * correct count                                              -> 3
        Only the real count passes.
        """
        from datetime import datetime, timezone

        import models

        for i in range(3):
            test_db.add(models.Incident(
                child_id=sample_child.id,
                kindergarten_id=sample_kindergarten.id,
                class_id=sample_class.id,
                type="injury",
                severity_level=models.SeverityLevel.LOW,
                description=f"non-critical incident {i}",
                occurred_at=datetime.now(timezone.utc),
                reported_by=admin_user.id,
                status=models.IncidentStatus.OPEN,
            ))
        test_db.commit()

        r = client.get("/api/admin/heatmap-data", headers=auth_headers_admin)
        assert r.status_code == 200, r.text
        amman = r.json()["data"]["amman"]
        assert amman["incidents_total"] == 3, (
            f"expected the real incident count 3, got {amman['incidents_total']} "
            "— looks decoded from a 0-100 score rather than counted"
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
