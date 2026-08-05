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
import models
from conftest import csrf_pair


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
