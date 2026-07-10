"""Tests for GET /api/reference/governorates.

The governorate dropdown (kindergarten filter + create/edit form) must list ALL
of Jordan's official governorates, not only the ones that already have data.
"""
import models
from auth import get_password_hash
from config import settings


def _make_admin(db, username="ref_admin"):
    u = models.User(
        username=username,
        email=f"{username}@example.com",
        hashed_password=get_password_hash("Admin123!"),
        role=models.UserRole.ADMIN,
        status=models.UserStatus.ACTIVE,
    )
    db.add(u)
    db.commit()
    db.refresh(u)
    return u


def _tok(client, username, password="Admin123!"):
    r = client.post("/token", data={"username": username, "password": password})
    assert r.status_code == 200, r.text
    return {"Authorization": f"Bearer {r.json()['access_token']}"}


def _make_kg(db, name_ar, governorate, district):
    kg = models.Kindergarten(
        name_ar=name_ar, governorate=governorate, district=district,
        area="a", address_line="a", contact_phone="0790000000",
        status=models.KindergartenStatus.ACTIVE,
    )
    db.add(kg)
    db.commit()
    return kg


def test_reference_governorates_returns_all_canonical(client, test_db):
    _make_admin(test_db, "ref_admin_all")
    # Only one governorate has data, yet all official governorates must appear.
    _make_kg(test_db, "روضة عمان", "عمان", "القويسمة")
    headers = _tok(client, "ref_admin_all")

    body = client.get("/api/reference/governorates", headers=headers).json()
    names = {g["name_ar"] for g in body["governorates"]}
    # every canonical governorate is present, including ones with no data
    assert set(settings.JORDAN_GOVERNORATES).issubset(names), \
        f"missing: {set(settings.JORDAN_GOVERNORATES) - names}"
    assert len(body["governorates"]) >= len(settings.JORDAN_GOVERNORATES)
    # each entry exposes an English label and a cities list
    for g in body["governorates"]:
        assert g["name_en"]
        assert isinstance(g["cities"], list)


def test_reference_governorates_includes_data_districts(client, test_db):
    _make_admin(test_db, "ref_admin_dist")
    _make_kg(test_db, "روضة إربد", "إربد", "الرمثا")
    headers = _tok(client, "ref_admin_dist")

    body = client.get("/api/reference/governorates", headers=headers).json()
    irbid = next(g for g in body["governorates"] if g["name_ar"] == "إربد")
    assert "الرمثا" in irbid["cities"]
