"""Round 3: opaque public_id fields + IDOR (cross-tenant access) protection.

GWS S.5.10-026 asks for opaque, non-sequential public identifiers. A full
migration of every route to opaque IDs is a large, risky change (see
GWS_COMPLIANCE_AUDIT_REPORT.md §10/§15), so this audit instead:
  1. Adds an opaque `public_id` (UUID4) to the most sensitive models
     (User, Child, EnrollmentApplication) as a foundation, exposed
     alongside (not instead of) the internal integer id.
  2. Verifies the authorization checks that already mitigate the
     practical risk of sequential IDs (IDOR) actually hold.
"""
import re
from datetime import date, timedelta

import models
from auth import get_password_hash

UUID_RE = re.compile(r"^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$", re.IGNORECASE)


class TestOpaquePublicId:
    def test_user_has_a_valid_public_id(self, test_db, parent_user):
        assert parent_user.public_id is not None
        assert UUID_RE.match(parent_user.public_id)

    def test_child_has_a_valid_public_id(self, test_db, sample_child):
        assert sample_child.public_id is not None
        assert UUID_RE.match(sample_child.public_id)

    def test_public_ids_are_unique_per_row(self, test_db, parent_user, sample_child):
        assert parent_user.public_id != sample_child.public_id

    def test_users_me_exposes_public_id_alongside_internal_id(self, client, auth_headers_parent):
        resp = client.get("/api/users/me", headers=auth_headers_parent)
        assert resp.status_code == 200
        body = resp.json()
        assert "id" in body and "public_id" in body
        assert UUID_RE.match(body["public_id"])


class TestChildIdorProtection:
    """A parent must never be able to read or modify another parent's
    child record by guessing/incrementing the (sequential, non-opaque)
    integer id — this is the practical mitigation for S.5.10-026 while a
    full opaque-ID migration remains a documented future PARTIAL item."""

    def _second_parent_with_child(self, test_db):
        other_user = models.User(
            username="other-parent@test.com",
            email="other-parent@test.com",
            hashed_password=get_password_hash("OtherParent123!"),
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
            phone_number="+962799999999",
            gender=models.Gender.FEMALE,
            nationality="Jordanian",
            home_governorate="Irbid",
            home_city="Irbid",
            home_area="Downtown",
            home_address_line="456 Other Street",
            correspondence_preference=True,
        )
        test_db.add(other_profile)
        test_db.commit()
        test_db.refresh(other_profile)

        other_child = models.Child(
            parent_id=other_profile.id,
            first_name="Someone",
            last_name="Else",
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

    def test_parent_cannot_update_another_parents_child(self, client, test_db, auth_headers_parent, parent_user):
        _, other_child = self._second_parent_with_child(test_db)

        resp = client.put(
            f"/api/children/{other_child.id}",
            json={"first_name": "Hacked"},
            headers=auth_headers_parent,
        )
        assert resp.status_code == 403

    def test_parent_cannot_list_another_parents_child_documents(self, client, test_db, auth_headers_parent, parent_user):
        _, other_child = self._second_parent_with_child(test_db)

        resp = client.get(
            f"/api/children/{other_child.id}/documents",
            headers=auth_headers_parent,
        )
        assert resp.status_code == 403

    def test_parent_cannot_upload_photo_for_another_parents_child(self, client, test_db, auth_headers_parent, parent_user):
        import io

        _, other_child = self._second_parent_with_child(test_db)

        fake_image = io.BytesIO(b"\x89PNG\r\n" + b"\x00" * 100)
        resp = client.post(
            f"/api/children/{other_child.id}/photo",
            files={"file": ("photo.png", fake_image, "image/png")},
            headers=auth_headers_parent,
        )
        assert resp.status_code == 403

    def test_parent_can_still_update_their_own_child(self, client, test_db, auth_headers_parent, sample_child):
        """Sanity check: the protection above is about cross-tenant access,
        not a blanket regression — a parent can still edit their own child."""
        resp = client.put(
            f"/api/children/{sample_child.id}",
            json={"first_name": "UpdatedName"},
            headers=auth_headers_parent,
        )
        assert resp.status_code == 200
