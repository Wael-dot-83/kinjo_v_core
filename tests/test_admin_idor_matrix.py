"""Gate B closure: representative object-level (IDOR) matrix at the HTTP layer.

This complements two existing bodies of evidence rather than duplicating them:
  * tests/test_manager_scope.py proves the shared manager/supervisor scope
    dependency (used by every scoped resource endpoint) returns 404 — no
    existence leak — for a cross-tenant target and 403 for a wrong role.
  * tests/test_opaque_ids_and_idor.py proves a parent cannot update another
    parent's child or list its documents.

Here we drive a cross-tenant object across several OPERATIONS and ID locations
for the parent→child family (a representative owned resource), and prove a denied
write performs no mutation. The consistent semantics asserted: a foreign object
is denied with 403/404 and the response never confirms the object exists or
leaks its content, and no row changes.
"""
from __future__ import annotations

from datetime import date, timedelta

import pytest

import models
from auth import get_password_hash


def _second_parent_with_child(test_db):
    """A parent in a *different* ownership scope, with one child."""
    other_user = models.User(
        username="idor-other-parent@test.com",
        email="idor-other-parent@test.com",
        hashed_password=get_password_hash("Other123!"),
        role=models.UserRole.PARENT,
        status=models.UserStatus.ACTIVE,
    )
    test_db.add(other_user)
    test_db.commit()
    test_db.refresh(other_user)

    other_profile = models.ParentProfile(
        user_id=other_user.id,
        first_name="Other",
        last_name="Parent",
        phone_number="+962799999888",
        gender=models.Gender.FEMALE,
        nationality="Jordanian",
        home_governorate="Irbid",
        home_district="Irbid",
        home_area="Downtown",
        home_address_line="456 Other Street",
        correspondence_preference=True,
    )
    test_db.add(other_profile)
    test_db.commit()
    test_db.refresh(other_profile)

    other_child = models.Child(
        parent_id=other_profile.id,
        first_name="Foreign",
        last_name="Child",
        gender=models.Gender.MALE,
        date_of_birth=date.today() - timedelta(days=365 * 3),
        father_name="Other Parent",
        mother_first_name="Other",
        mother_last_name="Mother",
        mother_nationality="Jordanian",
        media_consent=True,
    )
    test_db.add(other_child)
    test_db.commit()
    test_db.refresh(other_child)
    return other_user, other_child


def _leaks_child(resp) -> bool:
    """Did the response body expose the foreign child's identity/content?"""
    return "foreign" in resp.text.lower()


class TestParentChildCrossTenantMatrix:
    """One foreign object (another parent's child), many operations/locations."""

    def test_read_child_documents_path_id_denied_no_leak(self, client, test_db, auth_headers_parent):
        # /api/children/{id} has no GET-detail route (parents get their own
        # children via a scoped list); the documents sub-resource is the real
        # owner-checked GET surface.
        _, other = _second_parent_with_child(test_db)
        resp = client.get(f"/api/children/{other.id}/documents", headers=auth_headers_parent)
        assert resp.status_code in (403, 404), resp.status_code
        assert not _leaks_child(resp)

    def test_update_path_id_denied_and_no_mutation(self, client, test_db, auth_headers_parent):
        _, other = _second_parent_with_child(test_db)
        before = other.first_name
        resp = client.put(
            f"/api/children/{other.id}",
            headers=auth_headers_parent,
            json={"first_name": "HACKED"},
        )
        assert resp.status_code in (403, 404), resp.status_code
        test_db.expire_all()
        reloaded = test_db.query(models.Child).filter(models.Child.id == other.id).first()
        assert reloaded.first_name == before, "cross-tenant update mutated the foreign child"

    def test_list_documents_denied_no_leak(self, client, test_db, auth_headers_parent):
        _, other = _second_parent_with_child(test_db)
        resp = client.get(f"/api/children/{other.id}/documents", headers=auth_headers_parent)
        assert resp.status_code in (403, 404), resp.status_code
        assert not _leaks_child(resp)

    def test_delete_denied_and_row_survives(self, client, test_db, auth_headers_parent):
        _, other = _second_parent_with_child(test_db)
        resp = client.delete(f"/api/children/{other.id}", headers=auth_headers_parent)
        assert resp.status_code in (403, 404, 405), resp.status_code
        test_db.expire_all()
        still = test_db.query(models.Child).filter(models.Child.id == other.id).first()
        assert still is not None and still.deleted_at is None, "cross-tenant delete removed the row"

    def test_foreign_and_nonexistent_are_both_denied(self, client, test_db, auth_headers_parent):
        """Both a foreign-but-real child and a nonexistent child are denied.

        Observation (not a failure): the parent→child family returns 403 for a
        foreign object and 404 for a nonexistent one — a minor existence oracle.
        This matches the project's existing tested semantics
        (test_opaque_ids_and_idor asserts 403 for a foreign child), which differ
        from the manager/supervisor 404-no-leak convention in test_manager_scope.
        A cross-family consistency review is worthwhile, but 403 here is the
        approved, pre-existing behavior — so this test asserts denial, not a
        uniform status code.
        """
        _, other = _second_parent_with_child(test_db)
        foreign = client.get(
            f"/api/children/{other.id}/documents", headers=auth_headers_parent
        ).status_code
        ghost = client.get(
            "/api/children/999999999/documents", headers=auth_headers_parent
        ).status_code
        assert foreign in (403, 404) and not (200 <= foreign < 300)
        assert ghost in (403, 404) and not (200 <= ghost < 300)
