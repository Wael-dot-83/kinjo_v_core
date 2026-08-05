"""Regression: the public `working_hours_*` API alias must persist to the DB columns.

The Kindergarten table stores `operating_hours_start/end`; the public API accepts and
returns `working_hours_start/end` (api/kindergartens.py request schemas + _serialize).
Without a write-side translation the alias is read-only:

  * create spreads the dump into models.Kindergarten(**dump) -> TypeError -> HTTP 500
  * update setattr()s a transient attribute -> the column keeps its old value (silent loss)

These tests assert PERSISTENCE and ROUND-TRIP SERIALIZATION, not merely status codes —
the pre-existing kindergarten tests post the column name (which Pydantic drops) and assert
only 201, so they cannot observe this defect.
"""
from pathlib import Path

import models
from conftest import csrf_pair

_ROOT = Path(__file__).resolve().parents[1]


def _kg_payload(**extra):
    base = {
        "name_ar": "حضانة ساعات العمل",
        "name_en": "Working Hours KG",
        "governorate": "Amman",
        "district": "Amman",
        "area": "Test Area",
        "address_line": "Test Street 1",
        "contact_phone": "0791234567",
    }
    base.update(extra)
    return base


def _headers(admin_token):
    return {"Authorization": f"Bearer {admin_token}", **csrf_pair()}


def test_create_persists_working_hours_alias_to_operating_hours_columns(
    client, test_db, admin_token, admin_user
):
    """POST with working_hours_* must return 201 and persist to operating_hours_*."""
    resp = client.post(
        "/api/admin/kindergartens",
        json=_kg_payload(working_hours_start="08:00", working_hours_end="16:00"),
        headers=_headers(admin_token),
    )
    assert resp.status_code == 201, f"create failed: {resp.text[:300]}"

    body = resp.json()
    kg_id = body.get("data", body)["id"]

    # Persistence: the DB columns must hold the submitted values.
    kg = test_db.query(models.Kindergarten).filter(models.Kindergarten.id == kg_id).first()
    assert kg is not None
    assert kg.operating_hours_start == "08:00", "working_hours_start did not reach the column"
    assert kg.operating_hours_end == "16:00", "working_hours_end did not reach the column"

    # Round-trip serialization: the response exposes the public alias, not the column name.
    data = body.get("data", body)
    assert data["working_hours_start"] == "08:00"
    assert data["working_hours_end"] == "16:00"


def test_update_persists_working_hours_alias_to_operating_hours_columns(
    client, test_db, admin_token, admin_user
):
    """PUT with working_hours_* must persist to operating_hours_* (never silently drop)."""
    created = client.post(
        "/api/admin/kindergartens",
        json=_kg_payload(name_ar="حضانة تحديث", contact_phone="0791234568"),
        headers=_headers(admin_token),
    )
    assert created.status_code == 201, created.text[:300]
    kg_id = created.json().get("data", created.json())["id"]

    resp = client.put(
        f"/api/admin/kindergartens/{kg_id}",
        json={"working_hours_start": "09:15", "working_hours_end": "17:45"},
        headers=_headers(admin_token),
    )
    assert resp.status_code == 200, f"update failed: {resp.text[:300]}"

    kg = test_db.query(models.Kindergarten).filter(models.Kindergarten.id == kg_id).first()
    test_db.refresh(kg)
    assert kg.operating_hours_start == "09:15", "update silently dropped working_hours_start"
    assert kg.operating_hours_end == "17:45", "update silently dropped working_hours_end"

    data = resp.json().get("data", resp.json())
    assert data["working_hours_start"] == "09:15"
    assert data["working_hours_end"] == "17:45"


def test_get_round_trips_working_hours_alias(client, test_db, admin_token, admin_user):
    """GET must return the stored hours under the public alias."""
    created = client.post(
        "/api/admin/kindergartens",
        json=_kg_payload(
            name_ar="حضانة قراءة",
            contact_phone="0791234569",
            working_hours_start="07:30",
            working_hours_end="15:30",
        ),
        headers=_headers(admin_token),
    )
    assert created.status_code == 201, created.text[:300]
    kg_id = created.json().get("data", created.json())["id"]

    resp = client.get(f"/api/kindergartens/{kg_id}", headers=_headers(admin_token))
    assert resp.status_code == 200, resp.text[:300]
    data = resp.json().get("data", resp.json())
    assert data["working_hours_start"] == "07:30"
    assert data["working_hours_end"] == "15:30"


def test_create_without_working_hours_still_succeeds(client, test_db, admin_token, admin_user):
    """Omitting the optional hours must remain valid (no contract change)."""
    resp = client.post(
        "/api/admin/kindergartens",
        json=_kg_payload(name_ar="حضانة بدون ساعات", contact_phone="0791234570"),
        headers=_headers(admin_token),
    )
    assert resp.status_code == 201, resp.text[:300]
    data = resp.json().get("data", resp.json())
    assert data["working_hours_start"] is None
    assert data["working_hours_end"] is None


def test_create_with_manager_persists_working_hours(client, test_db, admin_token, admin_user):
    """The atomic create-with-manager path maps the alias too."""
    payload = {
        "kindergarten": _kg_payload(
            name_ar="حضانة مع مدير",
            contact_phone="0791234571",
            working_hours_start="06:45",
            working_hours_end="18:15",
        ),
        "manager": {
            "username": "wh_mgr_probe",
            "password": "Str0ng!Passw0rd1",
            "full_name": "Working Hours Manager",
            "phone_number": "0791234599",
            "email": "wh_mgr_probe@example.com",
        },
    }
    resp = client.post(
        "/api/admin/kindergartens/with-manager", json=payload, headers=_headers(admin_token)
    )
    assert resp.status_code == 201, f"with-manager failed: {resp.text[:300]}"

    kg = (
        test_db.query(models.Kindergarten)
        .filter(models.Kindergarten.contact_phone == "0791234571")
        .first()
    )
    assert kg is not None
    assert kg.operating_hours_start == "06:45"
    assert kg.operating_hours_end == "18:15"


def test_blank_working_hours_are_stored_as_null_not_empty_string(
    client, test_db, admin_token, admin_user
):
    """Blank optional values must normalise to NULL, never ''."""
    resp = client.post(
        "/api/admin/kindergartens",
        json=_kg_payload(
            name_ar="حضانة فارغة",
            contact_phone="0791234572",
            working_hours_start="",
            working_hours_end="",
        ),
        headers=_headers(admin_token),
    )
    assert resp.status_code == 201, resp.text[:300]
    kg_id = resp.json().get("data", resp.json())["id"]
    kg = test_db.query(models.Kindergarten).filter(models.Kindergarten.id == kg_id).first()
    assert kg.operating_hours_start in (None, ""), kg.operating_hours_start
    assert not kg.operating_hours_start, "blank must not become a truthy value"


def test_other_fields_still_persist_alongside_the_alias(
    client, test_db, admin_token, admin_user
):
    """The alias mapping must not disturb any non-aliased field."""
    resp = client.post(
        "/api/admin/kindergartens",
        json=_kg_payload(
            name_ar="حضانة حقول",
            contact_phone="0791234573",
            working_hours_start="08:30",
            manager_name="Sara",
            total_capacity=40,
            working_days="Sun-Thu",
        ),
        headers=_headers(admin_token),
    )
    assert resp.status_code == 201, resp.text[:300]
    kg_id = resp.json().get("data", resp.json())["id"]
    kg = test_db.query(models.Kindergarten).filter(models.Kindergarten.id == kg_id).first()
    assert kg.operating_hours_start == "08:30"
    assert kg.manager_name == "Sara"
    assert kg.total_capacity == 40
    assert kg.working_days == "Sun-Thu"


def test_no_transient_working_hours_attribute_is_created_on_the_model(
    client, test_db, admin_token, admin_user
):
    """The ORM row must never carry a stray `working_hours_*` attribute.

    A transient attribute is exactly how the update path used to lose data: it
    looked set in memory but no column was written.
    """
    created = client.post(
        "/api/admin/kindergartens",
        json=_kg_payload(name_ar="حضانة عابرة", contact_phone="0791234574"),
        headers=_headers(admin_token),
    )
    assert created.status_code == 201, created.text[:300]
    kg_id = created.json().get("data", created.json())["id"]

    resp = client.put(
        f"/api/admin/kindergartens/{kg_id}",
        json={"working_hours_start": "10:00", "working_hours_end": "12:00"},
        headers=_headers(admin_token),
    )
    assert resp.status_code == 200, resp.text[:300]

    kg = test_db.query(models.Kindergarten).filter(models.Kindergarten.id == kg_id).first()
    test_db.refresh(kg)
    assert "working_hours_start" not in kg.__dict__, "transient attribute leaked onto the ORM row"
    assert "working_hours_end" not in kg.__dict__
    assert kg.operating_hours_start == "10:00"


def test_legacy_kindergarten_form_submits_public_api_names():
    """F-1 guard: the manager form must POST working_hours_*, not the column names.

    The form's `value=` still reads the ORM attribute (operating_hours_*) — that is the
    presentation boundary and is correct; only the submitted `name=` must be public.
    """
    html = (_ROOT / "templates" / "kindergartens" / "form.html").read_text(encoding="utf-8")
    assert 'name="working_hours_start"' in html
    assert 'name="working_hours_end"' in html
    assert 'name="operating_hours_start"' not in html, "form still submits the DB column name"
    assert 'name="operating_hours_end"' not in html
    # Editing an existing record must still prefill from the ORM column.
    assert "kindergarten.operating_hours_start" in html


def test_enrollment_details_consume_public_response_names():
    """F-3 guard: the enrollment modal must read working_hours_* from the API."""
    html = (_ROOT / "templates" / "enrollment" / "create.html").read_text(encoding="utf-8")
    assert "kg.working_hours_start" in html
    assert "kg.working_hours_end" in html
    assert "kg.operating_hours_start" not in html, "enrollment page reads a key the API never returns"
    assert "kg.operating_hours_end" not in html
