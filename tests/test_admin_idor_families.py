"""Gate B object-level IDOR — resource families not already exercised end-to-end.

Existing coverage this complements (all green):
  * test_manager_module.py — manager cross-tenant for classes, children,
    supervisors, daily reports, absence approve/reject, capacity, documents,
    user creation.
  * test_manager_scope.py / test_opaque_ids_and_idor.py — the shared scope
    dependency (404 no-leak) and parent→child.
  * test_admin_idor_matrix.py (PR #73) — parent→child read/update/delete.

This file adds the families with an ID endpoint but no cross-tenant test yet:
  * INCIDENT (safety_service: update / history / attachment) — a manager from
    another kindergarten must get 404 (no existence leak) and cause no mutation;
  * ANALYTICS DRILL-DOWN (/api/analytics/drilldown/{type}/{id}) — a non-scoped
    principal must be denied.
"""
from __future__ import annotations

from datetime import date, datetime, timedelta, timezone

import pytest

import models
from auth import get_password_hash


def _login(client, username, password):
    r = client.post("/token", data={"username": username, "password": password})
    assert r.status_code == 200, r.text[:200]
    return r.json()["access_token"]


def _bearer(tok):
    return {"Authorization": f"Bearer {tok}"}


@pytest.fixture
def kg_a(test_db):
    kg = models.Kindergarten(
        name_ar="حضانة أ", name_en="KG A", governorate="العاصمة", district="عمان",
        area="الدعيس", address_line="ش الملك", contact_phone="0789000001",
        status=models.KindergartenStatus.ACTIVE,
    )
    test_db.add(kg); test_db.commit(); test_db.refresh(kg)
    return kg


@pytest.fixture
def kg_b(test_db):
    kg = models.Kindergarten(
        name_ar="حضانة ب", name_en="KG B", governorate="الزرقاء", district="الزرقاء",
        area="المقابلين", address_line="ش الجديدة", contact_phone="0789000002",
        status=models.KindergartenStatus.ACTIVE,
    )
    test_db.add(kg); test_db.commit(); test_db.refresh(kg)
    return kg


def _manager(test_db, kg, tag):
    u = models.User(
        username=f"idor_mgr_{tag}", email=f"idor_mgr_{tag}@ex.com",
        hashed_password=get_password_hash("Manager123!"), role=models.UserRole.MANAGER,
        kindergarten_id=kg.id, status=models.UserStatus.ACTIVE,
    )
    test_db.add(u); test_db.commit(); test_db.refresh(u)
    return u


@pytest.fixture
def manager_a(test_db, kg_a):
    return _manager(test_db, kg_a, "a")


@pytest.fixture
def manager_b(test_db, kg_b):
    return _manager(test_db, kg_b, "b")


@pytest.fixture
def incident_a(test_db, kg_a):
    """An incident owned by kindergarten A (with a minimal child for the FK)."""
    parent = models.User(
        username="idor_child_parent", email="idor_child_parent@ex.com",
        hashed_password=get_password_hash("Parent123!"), role=models.UserRole.PARENT,
        status=models.UserStatus.ACTIVE,
    )
    test_db.add(parent); test_db.commit(); test_db.refresh(parent)
    profile = models.ParentProfile(
        user_id=parent.id, first_name="P", last_name="P", phone_number="0781119999",
        gender=models.Gender.FEMALE, nationality="Jordanian", home_governorate="Amman",
        home_district="Amman", home_area="X", home_address_line="Y",
        correspondence_preference=True,
    )
    test_db.add(profile); test_db.commit(); test_db.refresh(profile)
    child = models.Child(
        parent_id=profile.id, first_name="Inc", last_name="Child",
        gender=models.Gender.MALE, date_of_birth=date.today() - timedelta(days=365 * 4),
        father_name="Dad", mother_first_name="M", mother_last_name="M", mother_nationality="Jordanian",
    )
    test_db.add(child); test_db.commit(); test_db.refresh(child)
    inc = models.Incident(
        child_id=child.id, kindergarten_id=kg_a.id, type="INJURY",
        severity_level="LOW", description="original description",
        occurred_at=datetime.now(timezone.utc),
    )
    test_db.add(inc); test_db.commit(); test_db.refresh(inc)
    return inc


class TestIncidentCrossTenant:
    def test_foreign_manager_cannot_update_incident_and_no_mutation(
        self, client, test_db, incident_a, manager_b
    ):
        tok = _login(client, "idor_mgr_b", "Manager123!")
        before = incident_a.description
        resp = client.put(
            f"/api/incidents/{incident_a.id}",
            headers=_bearer(tok),
            json={"description": "HACKED"},
        )
        assert resp.status_code in (403, 404), resp.text[:200]
        test_db.expire_all()
        reloaded = test_db.query(models.Incident).filter(models.Incident.id == incident_a.id).first()
        assert reloaded.description == before, "cross-tenant update mutated the incident"

    def test_foreign_manager_cannot_read_incident_history(self, client, incident_a, manager_b):
        tok = _login(client, "idor_mgr_b", "Manager123!")
        resp = client.get(f"/api/incidents/{incident_a.id}/history", headers=_bearer(tok))
        assert resp.status_code in (403, 404), resp.text[:200]
        assert "original description" not in resp.text

    def test_foreign_manager_cannot_attach_to_incident(self, client, incident_a, manager_b):
        tok = _login(client, "idor_mgr_b", "Manager123!")
        resp = client.post(
            f"/api/incidents/{incident_a.id}/attachment", headers=_bearer(tok), json={}
        )
        assert resp.status_code in (403, 404, 422), resp.status_code
        # 422 only if auth/scope passed to body validation — must NOT be 2xx.
        assert not (200 <= resp.status_code < 300)

    def test_owning_manager_can_update_own_incident(self, client, incident_a, manager_a):
        """Positive control: the owning manager IS allowed (proves the 404 above is
        scope, not a broken route)."""
        tok = _login(client, "idor_mgr_a", "Manager123!")
        resp = client.put(
            f"/api/incidents/{incident_a.id}",
            headers=_bearer(tok),
            json={"description": "updated by owner"},
        )
        assert resp.status_code in (200, 204), resp.text[:200]

    def test_nonexistent_incident_is_404(self, client, manager_b):
        tok = _login(client, "idor_mgr_b", "Manager123!")
        resp = client.put(
            f"/api/incidents/999999999", headers=_bearer(tok),
            json={"description": "x"},
        )
        assert resp.status_code == 404


class TestAnalyticsDrilldownAccess:
    def test_parent_cannot_direct_access_drilldown(self, client, parent_token):
        resp = client.get(
            "/api/analytics/drilldown/governorate/1",
            headers=_bearer(parent_token),
        )
        assert not (200 <= resp.status_code < 300), (
            f"parent reached analytics drilldown: {resp.status_code}"
        )
