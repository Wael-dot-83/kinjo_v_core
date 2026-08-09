"""
Tests for enrollment feature enhancements:
  1. Parent registration — emergency contact, work address, relationship
  2. Enrollment apply — child second_name/last_name matching, conditional identity
  3. List children — filters, sort, pagination
  4. Child photo upload
  5. Child document management (upload, list, verify, delete)
  6. Bulk export — CSV / JSON
"""
import io
import csv
import json
import pytest
import secrets
from datetime import date, timedelta
from unittest.mock import patch

import models
from auth import get_password_hash


# ──────────────────────────────────────────────────────────────────
# Helpers
# ──────────────────────────────────────────────────────────────────

def _valid_parent_payload(overrides=None):
    data = {
        "first_name": "سمير",
        "second_name": "عبدالله",
        "last_name": "الحسن",
        "phone_number": "+962791234567",
        "gender": "male",
        "nationality": "Jordanian",
        "national_id": "1234567890",
        "home_governorate": "Amman",
        "home_district": "Amman",
        "home_area": "Abdoun",
        "home_address_line": "123 Main St",
        # Required since 3d33ece: ParentRegistrationRequest changed this from
        # `Optional[bool] = True` to `bool`, so the caller now has to state the
        # preference instead of having True assumed for them. The registration
        # form sends it (templates/auth/register.html), so the endpoint is the
        # contract of record and this payload was the stale side.
        "correspondence_preference": True,
        "email": f"parent_{secrets.token_hex(4)}@test.com",
        "password": "Str0ng!Pass",
        "work_address": "45 Corporate Blvd, Amman",
        "emergency_contact_name": "خالد الحسن",
        "emergency_contact_phone": "+962799876543",
        "emergency_contact_relationship": "عم / Uncle",
        "relationship_to_child": "أب / Father",
    }
    if overrides:
        data.update(overrides)
    return data


def _valid_enrollment_payload(kindergarten_id, overrides=None):
    dob = (date.today() - timedelta(days=365 * 3)).isoformat()
    data = {
        "first_name": "ليلى",
        "second_name": "عبدالله",
        "last_name": "الحسن",
        "gender": "female",
        "date_of_birth": dob,
        "nationality": "Jordanian",
        "national_id": "9876543210",
        "father_name": "سمير عبدالله الحسن",
        "mother_first_name": "فاطمة",
        "mother_last_name": "القاسم",
        "mother_nationality": "Jordanian",
        "mother_national_id": "1122334455",
        "kindergarten_id": kindergarten_id,
        "media_consent": True,
    }
    if overrides:
        data.update(overrides)
    return data


def _register_parent_and_get_headers(client, overrides=None):
    """Register a parent and return (auth_headers, user_data)."""
    payload = _valid_parent_payload(overrides)
    resp = client.post("/api/register/parent", json=payload)
    assert resp.status_code == 201, resp.text
    user_data = resp.json()
    # login
    login_resp = client.post("/token", data={
        "username": payload["email"],
        "password": payload["password"],
    })
    assert login_resp.status_code == 200
    token = login_resp.json()["access_token"]
    csrf = secrets.token_hex(32)
    headers = {
        "Authorization": f"Bearer {token}",
        "X-CSRF-Token": csrf,
        "Cookie": f"kinjo_csrf_token={csrf}",
    }
    return headers, user_data


# ══════════════════════════════════════════════════════════════════
# 1. Parent Registration — new fields
# ══════════════════════════════════════════════════════════════════

class TestParentRegistrationFields:
    def test_register_with_emergency_and_work_fields(self, client, test_db):
        """Parent registration stores emergency contact and work address."""
        headers, data = _register_parent_and_get_headers(client)
        # Verify stored in DB
        profile = test_db.query(models.ParentProfile).filter(
            models.ParentProfile.user_id == data["id"]
        ).first()
        assert profile is not None
        assert profile.work_address == "45 Corporate Blvd, Amman"
        assert profile.emergency_contact_name == "خالد الحسن"
        assert profile.emergency_contact_phone == "+962799876543"
        assert profile.emergency_contact_relationship == "عم / Uncle"
        assert profile.relationship_to_child == "أب / Father"

    def test_register_without_optional_fields(self, client, test_db):
        """Parent registration works without optional emergency fields."""
        payload = _valid_parent_payload()
        del payload["work_address"]
        del payload["emergency_contact_name"]
        del payload["emergency_contact_phone"]
        del payload["emergency_contact_relationship"]
        del payload["relationship_to_child"]
        resp = client.post("/api/register/parent", json=payload)
        assert resp.status_code == 201


# ══════════════════════════════════════════════════════════════════
# 2. Enrollment — Name Matching & Conditional Identity
# ══════════════════════════════════════════════════════════════════

class TestEnrollmentNameMatching:
    def test_enrollment_last_name_mismatch_rejected(self, client, test_db, sample_kindergarten):
        """Child's last_name must match parent's last_name."""
        headers, _ = _register_parent_and_get_headers(client)
        payload = _valid_enrollment_payload(sample_kindergarten.id, {
            "last_name": "الخطيب",  # different from parent's "الحسن"
        })
        resp = client.post("/api/enrollment/apply", json=payload, headers=headers)
        assert resp.status_code == 400
        assert "last name" in resp.json()["detail"].lower() or "العائلة" in resp.json()["detail"]

    def test_enrollment_second_name_mismatch_rejected(self, client, test_db, sample_kindergarten):
        """Child's second_name must match parent's second_name."""
        headers, _ = _register_parent_and_get_headers(client)
        payload = _valid_enrollment_payload(sample_kindergarten.id, {
            "second_name": "محمد",  # different from parent's "عبدالله"
        })
        resp = client.post("/api/enrollment/apply", json=payload, headers=headers)
        assert resp.status_code == 400
        assert "second name" in resp.json()["detail"].lower() or "الثاني" in resp.json()["detail"]

    def test_enrollment_matching_names_accepted(self, client, test_db, sample_kindergarten):
        """Enrollment succeeds when names match."""
        headers, _ = _register_parent_and_get_headers(client)
        payload = _valid_enrollment_payload(sample_kindergarten.id)
        resp = client.post("/api/enrollment/apply", json=payload, headers=headers)
        assert resp.status_code == 201

    def test_jordanian_child_without_national_id_rejected(self, client, test_db, sample_kindergarten):
        """Jordanian children must provide national_id."""
        headers, _ = _register_parent_and_get_headers(client)
        payload = _valid_enrollment_payload(sample_kindergarten.id, {
            "nationality": "Jordanian",
            "national_id": None,
        })
        resp = client.post("/api/enrollment/apply", json=payload, headers=headers)
        assert resp.status_code == 400
        assert "national_id" in resp.json()["detail"].lower() or "الوطني" in resp.json()["detail"]

    def test_non_jordanian_child_without_passport_rejected(self, client, test_db, sample_kindergarten):
        """Non-Jordanian children must provide passport_number."""
        headers, _ = _register_parent_and_get_headers(client)
        payload = _valid_enrollment_payload(sample_kindergarten.id, {
            "nationality": "Syrian",
            "national_id": None,
            "passport_number": None,
        })
        resp = client.post("/api/enrollment/apply", json=payload, headers=headers)
        assert resp.status_code == 400
        assert "passport" in resp.json()["detail"].lower() or "جواز" in resp.json()["detail"]

    def test_non_jordanian_with_passport_accepted(self, client, test_db, sample_kindergarten):
        """Non-Jordanian with passport succeeds."""
        headers, _ = _register_parent_and_get_headers(client)
        payload = _valid_enrollment_payload(sample_kindergarten.id, {
            "nationality": "Syrian",
            "national_id": None,
            "passport_number": "P999888",
        })
        resp = client.post("/api/enrollment/apply", json=payload, headers=headers)
        assert resp.status_code == 201

    def test_health_and_educational_notes_stored(self, client, test_db, sample_kindergarten):
        """Health/educational notes on enrollment are persisted on child record."""
        headers, _ = _register_parent_and_get_headers(client)
        payload = _valid_enrollment_payload(sample_kindergarten.id, {
            "health_notes": "حساسية من الفول السوداني / Peanut allergy",
            "educational_notes": "يحتاج دعم إضافي / Needs extra support",
        })
        resp = client.post("/api/enrollment/apply", json=payload, headers=headers)
        assert resp.status_code == 201
        child_id = resp.json()["child_id"]
        child = test_db.get(models.Child, child_id)
        assert child.health_notes == "حساسية من الفول السوداني / Peanut allergy"
        assert child.educational_notes == "يحتاج دعم إضافي / Needs extra support"


# ══════════════════════════════════════════════════════════════════
# 3. List Children — filters, sort, pagination
# ══════════════════════════════════════════════════════════════════

class TestListChildren:
    def _seed_children(self, test_db, parent_user, sample_kindergarten, sample_class, count=5):
        """Create multiple children with ACTIVE enrollments."""
        children = []
        for i in range(count):
            child = models.Child(
                parent_id=parent_user.parent_profile.id,
                first_name=f"Child{i}",
                last_name="Al-Rashid",
                gender=models.Gender.MALE if i % 2 == 0 else models.Gender.FEMALE,
                date_of_birth=date.today() - timedelta(days=365 * 3 + i * 30),
                father_name="Ahmad Al-Rashid",
                mother_first_name="Fatima",
                mother_last_name="Hassan",
                mother_nationality="Jordanian",
                mother_national_id="0987654321",
                media_consent=True,
            )
            test_db.add(child)
            test_db.flush()
            enrollment = models.EnrollmentApplication(
                child_id=child.id,
                kindergarten_id=sample_kindergarten.id,
                class_id=sample_class.id,
                status=models.EnrollmentStatus.ACTIVE,
            )
            test_db.add(enrollment)
            children.append(child)
        test_db.commit()
        return children

    def test_list_with_pagination(self, client, test_db, auth_headers_admin,
                                  parent_user, sample_kindergarten, sample_class):
        self._seed_children(test_db, parent_user, sample_kindergarten, sample_class, count=5)
        resp = client.get("/api/children?page=1&page_size=2", headers=auth_headers_admin)
        assert resp.status_code == 200
        data = resp.json()
        assert len(data["children"]) == 2
        assert data["pagination"]["total_count"] >= 5
        assert data["pagination"]["page"] == 1
        assert data["pagination"]["page_size"] == 2
        assert data["pagination"]["total_pages"] >= 3

    def test_list_filter_by_kindergarten(self, client, test_db, auth_headers_admin,
                                         parent_user, sample_kindergarten, sample_class):
        self._seed_children(test_db, parent_user, sample_kindergarten, sample_class, count=3)
        resp = client.get(
            f"/api/children?kindergarten_id={sample_kindergarten.id}",
            headers=auth_headers_admin,
        )
        assert resp.status_code == 200
        assert resp.json()["pagination"]["total_count"] >= 3

    def test_list_filter_by_class(self, client, test_db, auth_headers_admin,
                                   parent_user, sample_kindergarten, sample_class):
        self._seed_children(test_db, parent_user, sample_kindergarten, sample_class, count=3)
        resp = client.get(
            f"/api/children?class_id={sample_class.id}",
            headers=auth_headers_admin,
        )
        assert resp.status_code == 200
        assert resp.json()["pagination"]["total_count"] >= 3

    def test_list_filter_by_status(self, client, test_db, auth_headers_admin,
                                    parent_user, sample_kindergarten, sample_class):
        self._seed_children(test_db, parent_user, sample_kindergarten, sample_class, count=2)
        resp = client.get(
            "/api/children?enrollment_status=ACTIVE",
            headers=auth_headers_admin,
        )
        assert resp.status_code == 200
        assert resp.json()["pagination"]["total_count"] >= 2

    def test_list_search_by_name(self, client, test_db, auth_headers_admin,
                                  parent_user, sample_kindergarten, sample_class):
        self._seed_children(test_db, parent_user, sample_kindergarten, sample_class, count=3)
        resp = client.get(
            "/api/children?search=Child0",
            headers=auth_headers_admin,
        )
        assert resp.status_code == 200
        children = resp.json()["children"]
        assert any(c["first_name"] == "Child0" for c in children)

    def test_list_sort_by_name(self, client, test_db, auth_headers_admin,
                                parent_user, sample_kindergarten, sample_class):
        self._seed_children(test_db, parent_user, sample_kindergarten, sample_class, count=3)
        resp = client.get(
            "/api/children?sort_by=name&sort_order=desc",
            headers=auth_headers_admin,
        )
        assert resp.status_code == 200
        names = [c["first_name"] for c in resp.json()["children"]]
        assert len(names) >= 3
        assert names == sorted(names, reverse=True)


# ══════════════════════════════════════════════════════════════════
# 4. Child Photo Upload
# ══════════════════════════════════════════════════════════════════

class TestPhotoUpload:
    def test_upload_photo_by_parent(self, client, test_db, auth_headers_parent,
                                     parent_user, sample_child):
        fake_image = io.BytesIO(b"\x89PNG\r\n" + b"\x00" * 100)
        resp = client.post(
            f"/api/children/{sample_child.id}/photo",
            files={"file": ("photo.png", fake_image, "image/png")},
            headers=auth_headers_parent,
        )
        assert resp.status_code == 200
        assert "photo_url" in resp.json()
        assert resp.json()["photo_url"].startswith("/static/uploads/photos/")

    def test_upload_photo_invalid_type_rejected(self, client, test_db, auth_headers_parent,
                                                  parent_user, sample_child):
        fake_file = io.BytesIO(b"not a real image")
        resp = client.post(
            f"/api/children/{sample_child.id}/photo",
            files={"file": ("virus.exe", fake_file, "application/x-executable")},
            headers=auth_headers_parent,
        )
        assert resp.status_code == 400

    def test_upload_photo_rejected_when_virus_scan_finds_malware(
        self, client, test_db, auth_headers_parent, parent_user, sample_child, monkeypatch
    ):
        """When virus scanning is enabled, an infected upload must be rejected
        before it's ever written to disk (Round 3: S.5.7-017)."""
        import api.children as children_api
        from virus_scan_service import VirusFoundError

        def _fake_scan(content):
            raise VirusFoundError("Eicar-Test-Signature")

        monkeypatch.setattr(children_api, "scan_bytes", _fake_scan)

        fake_image = io.BytesIO(b"\x89PNG\r\n" + b"\x00" * 100)
        resp = client.post(
            f"/api/children/{sample_child.id}/photo",
            files={"file": ("photo.png", fake_image, "image/png")},
            headers=auth_headers_parent,
        )
        assert resp.status_code == 400

    def test_upload_photo_rejected_when_scanner_unavailable(
        self, client, test_db, auth_headers_parent, parent_user, sample_child, monkeypatch
    ):
        """A scanner that can't be reached must fail closed (reject), not be
        silently treated as clean."""
        import api.children as children_api
        from virus_scan_service import VirusScanUnavailable

        def _fake_scan(content):
            raise VirusScanUnavailable("connection refused")

        monkeypatch.setattr(children_api, "scan_bytes", _fake_scan)

        fake_image = io.BytesIO(b"\x89PNG\r\n" + b"\x00" * 100)
        resp = client.post(
            f"/api/children/{sample_child.id}/photo",
            files={"file": ("photo.png", fake_image, "image/png")},
            headers=auth_headers_parent,
        )
        assert resp.status_code == 503


# ══════════════════════════════════════════════════════════════════
# 5. Document Management
# ══════════════════════════════════════════════════════════════════

class TestDocumentManagement:
    def _upload_doc(self, client, headers, child_id, doc_type="birth_certificate"):
        fake_pdf = io.BytesIO(b"%PDF-1.4" + b"\x00" * 200)
        return client.post(
            f"/api/children/{child_id}/documents?document_type={doc_type}",
            files={"file": ("cert.pdf", fake_pdf, "application/pdf")},
            headers=headers,
        )

    def test_upload_document(self, client, test_db, auth_headers_parent,
                              parent_user, sample_child):
        resp = self._upload_doc(client, auth_headers_parent, sample_child.id)
        assert resp.status_code == 200
        data = resp.json()
        assert data["document_type"] == "birth_certificate"
        assert data["verified"] is False

    def test_list_documents(self, client, test_db, auth_headers_parent,
                             parent_user, sample_child):
        self._upload_doc(client, auth_headers_parent, sample_child.id, "birth_certificate")
        self._upload_doc(client, auth_headers_parent, sample_child.id, "health_certificate")
        resp = client.get(
            f"/api/children/{sample_child.id}/documents",
            headers=auth_headers_parent,
        )
        assert resp.status_code == 200
        assert len(resp.json()["documents"]) >= 2

    def test_list_documents_filter_by_type(self, client, test_db, auth_headers_parent,
                                            parent_user, sample_child):
        self._upload_doc(client, auth_headers_parent, sample_child.id, "birth_certificate")
        self._upload_doc(client, auth_headers_parent, sample_child.id, "health_certificate")
        resp = client.get(
            f"/api/children/{sample_child.id}/documents?document_type=health_certificate",
            headers=auth_headers_parent,
        )
        assert resp.status_code == 200
        docs = resp.json()["documents"]
        assert all(d["document_type"] == "health_certificate" for d in docs)

    def test_verify_document_manager(self, client, test_db, auth_headers_parent,
                                      auth_headers_manager, parent_user, sample_child,
                                      parent_enrollment):
        upload_resp = self._upload_doc(client, auth_headers_parent, sample_child.id)
        doc_id = upload_resp.json()["id"]
        resp = client.put(
            f"/api/children/documents/{doc_id}/verify",
            headers=auth_headers_manager,
        )
        assert resp.status_code == 200
        assert resp.json()["verified"] is True

    def test_verify_document_parent_forbidden(self, client, test_db, auth_headers_parent,
                                               parent_user, sample_child):
        upload_resp = self._upload_doc(client, auth_headers_parent, sample_child.id)
        doc_id = upload_resp.json()["id"]
        resp = client.put(
            f"/api/children/documents/{doc_id}/verify",
            headers=auth_headers_parent,
        )
        assert resp.status_code == 403

    def test_delete_document_by_parent(self, client, test_db, auth_headers_parent,
                                        parent_user, sample_child):
        upload_resp = self._upload_doc(client, auth_headers_parent, sample_child.id)
        doc_id = upload_resp.json()["id"]
        resp = client.delete(
            f"/api/children/documents/{doc_id}",
            headers=auth_headers_parent,
        )
        assert resp.status_code == 200
        # Verify deleted
        list_resp = client.get(
            f"/api/children/{sample_child.id}/documents",
            headers=auth_headers_parent,
        )
        assert all(d["id"] != doc_id for d in list_resp.json()["documents"])

    def test_invalid_document_type_rejected(self, client, test_db, auth_headers_parent,
                                              parent_user, sample_child):
        fake_pdf = io.BytesIO(b"%PDF-1.4" + b"\x00" * 200)
        resp = client.post(
            f"/api/children/{sample_child.id}/documents?document_type=invalid_type",
            files={"file": ("cert.pdf", fake_pdf, "application/pdf")},
            headers=auth_headers_parent,
        )
        assert resp.status_code == 400


# ══════════════════════════════════════════════════════════════════
# 6. Bulk Export — CSV / JSON
# ══════════════════════════════════════════════════════════════════

class TestBulkExport:
    def _seed_active_enrollment(self, test_db, parent_user, sample_kindergarten, sample_class):
        child = models.Child(
            parent_id=parent_user.parent_profile.id,
            first_name="ExportChild",
            last_name="Al-Rashid",
            gender=models.Gender.FEMALE,
            date_of_birth=date.today() - timedelta(days=365 * 3),
            nationality="Jordanian",
            national_id="5566778899",
            father_name="Ahmad",
            mother_first_name="Fatima",
            mother_last_name="Hassan",
            mother_nationality="Jordanian",
            mother_national_id="0987654321",
            health_notes="No allergies",
            media_consent=True,
        )
        test_db.add(child)
        test_db.flush()
        enrollment = models.EnrollmentApplication(
            child_id=child.id,
            kindergarten_id=sample_kindergarten.id,
            class_id=sample_class.id,
            status=models.EnrollmentStatus.ACTIVE,
        )
        test_db.add(enrollment)
        test_db.commit()
        return child

    def test_export_csv(self, client, test_db, auth_headers_admin,
                         parent_user, sample_kindergarten, sample_class):
        self._seed_active_enrollment(test_db, parent_user, sample_kindergarten, sample_class)
        resp = client.get("/api/children/export?format=csv", headers=auth_headers_admin)
        assert resp.status_code == 200
        assert "text/csv" in resp.headers["content-type"]
        content = resp.content.decode("utf-8-sig")
        reader = csv.DictReader(io.StringIO(content))
        rows = list(reader)
        assert len(rows) >= 1
        assert "first_name" in rows[0]
        assert any(r["first_name"] == "ExportChild" for r in rows)

    def test_export_json(self, client, test_db, auth_headers_admin,
                          parent_user, sample_kindergarten, sample_class):
        self._seed_active_enrollment(test_db, parent_user, sample_kindergarten, sample_class)
        resp = client.get("/api/children/export?format=json", headers=auth_headers_admin)
        assert resp.status_code == 200
        data = json.loads(resp.content)
        assert len(data) >= 1
        assert any(r["first_name"] == "ExportChild" for r in data)

    def test_export_selected_fields(self, client, test_db, auth_headers_admin,
                                     parent_user, sample_kindergarten, sample_class):
        self._seed_active_enrollment(test_db, parent_user, sample_kindergarten, sample_class)
        resp = client.get(
            "/api/children/export?format=json&fields=first_name,last_name,health_notes",
            headers=auth_headers_admin,
        )
        assert resp.status_code == 200
        data = json.loads(resp.content)
        assert len(data) >= 1
        assert set(data[0].keys()) == {"first_name", "last_name", "health_notes"}

    def test_export_forbidden_for_parent(self, client, test_db, auth_headers_parent,
                                          parent_user, sample_kindergarten, sample_class):
        resp = client.get("/api/children/export?format=csv", headers=auth_headers_parent)
        assert resp.status_code == 403
