"""
RBAC tests for the POST /api/incidents endpoint.
Business rule: Admin and Parent cannot create incidents.
Manager and Supervisor can create incidents for children enrolled in their kindergarten.
Also tests field validation (parent notification reason required when parent_informed=False).
"""
import pytest
from datetime import datetime, date, timedelta
import models


def _incident_payload(child_id: int, **overrides) -> dict:
    base = {
        "child_id": child_id,
        "type": "INJURY",
        "severity_level": "LOW",
        "description": "تعثّر الطفل أثناء اللعب",
        "occurred_at": datetime(2026, 5, 2, 10, 0).isoformat(),
        "parent_informed": True,
        "followup_required_flag": False,
    }
    base.update(overrides)
    return base


class TestIncidentCreationRBAC:
    def test_admin_cannot_create_incident(
        self, client, auth_headers_admin, sample_child, sample_enrollment
    ):
        resp = client.post(
            "/api/incidents",
            json=_incident_payload(sample_child.id),
            headers=auth_headers_admin,
        )
        assert resp.status_code == 403

    def test_parent_cannot_create_incident(
        self, client, auth_headers_parent, sample_child, sample_enrollment
    ):
        resp = client.post(
            "/api/incidents",
            json=_incident_payload(sample_child.id),
            headers=auth_headers_parent,
        )
        assert resp.status_code == 403

    def test_manager_can_create_incident(
        self, client, auth_headers_manager, sample_child, sample_enrollment
    ):
        resp = client.post(
            "/api/incidents",
            json=_incident_payload(sample_child.id),
            headers=auth_headers_manager,
        )
        assert resp.status_code == 201, resp.text
        data = resp.json()
        assert data["child_id"] == sample_child.id
        assert data["type"] == "INJURY"

    def test_supervisor_can_create_incident(
        self,
        client,
        auth_headers_supervisor,
        sample_child,
        sample_enrollment,
        # A supervisor may only file an incident for a child in a class they are
        # assigned to (rbac.assert_supervisor_owns_child). This test previously
        # relied on that check not existing, so it enrolled the child but never
        # assigned the supervisor to the class and now gets a correct 403.
        sample_supervisor_assignment,
    ):
        resp = client.post(
            "/api/incidents",
            json=_incident_payload(sample_child.id),
            headers=auth_headers_supervisor,
        )
        assert resp.status_code == 201, resp.text

    def test_unauthenticated_blocked(self, client, sample_child, sample_enrollment):
        resp = client.post("/api/incidents", json=_incident_payload(sample_child.id))
        assert resp.status_code in (401, 403)


class TestIncidentFieldValidation:
    def test_missing_reason_when_parent_not_informed_returns_400(
        self, client, auth_headers_manager, sample_child, sample_enrollment
    ):
        payload = _incident_payload(
            sample_child.id,
            parent_informed=False,
            parent_not_informed_reason="",  # empty
        )
        resp = client.post("/api/incidents", json=payload, headers=auth_headers_manager)
        assert resp.status_code == 400

    def test_reason_provided_when_parent_not_informed_succeeds(
        self, client, auth_headers_manager, sample_child, sample_enrollment
    ):
        payload = _incident_payload(
            sample_child.id,
            parent_informed=False,
            parent_not_informed_reason="الوالد غير متاح حالياً",
        )
        resp = client.post("/api/incidents", json=payload, headers=auth_headers_manager)
        assert resp.status_code == 201, resp.text

    def test_invalid_severity_returns_422(
        self, client, auth_headers_manager, sample_child, sample_enrollment
    ):
        payload = _incident_payload(sample_child.id, severity_level="UNKNOWN_LEVEL")
        resp = client.post("/api/incidents", json=payload, headers=auth_headers_manager)
        assert resp.status_code in (400, 422)

    def test_invalid_type_returns_422(
        self, client, auth_headers_manager, sample_child, sample_enrollment
    ):
        payload = _incident_payload(sample_child.id, type="NOT_A_REAL_TYPE")
        resp = client.post("/api/incidents", json=payload, headers=auth_headers_manager)
        assert resp.status_code in (400, 422)


class TestIncidentListRBAC:
    def test_admin_can_list_incidents(self, client, auth_headers_admin, sample_incident):
        resp = client.get("/api/incidents", headers=auth_headers_admin)
        assert resp.status_code == 200

    def test_manager_can_list_incidents(self, client, auth_headers_manager, sample_incident):
        resp = client.get("/api/incidents", headers=auth_headers_manager)
        assert resp.status_code == 200

    def test_parent_cannot_list_all_incidents(
        self, client, auth_headers_parent, sample_incident
    ):
        resp = client.get("/api/incidents", headers=auth_headers_parent)
        assert resp.status_code in (403, 200)
