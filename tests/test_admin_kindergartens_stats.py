"""Tests for GET /api/admin/kindergartens/stats — the KPI summary endpoint
backing the admin Kindergartens list page's summary cards.

Covers: admin gets the expected envelope + shape, counts reflect real status,
and non-admin roles are forbidden (403).
"""
import models
from auth import get_password_hash


def _make_admin(db, username="stats_admin"):
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


def _make_user(db, username, role=models.UserRole.SUPERVISOR):
    u = models.User(
        username=username,
        email=f"{username}@example.com",
        hashed_password=get_password_hash("Pass123!"),
        role=role,
        status=models.UserStatus.ACTIVE,
    )
    db.add(u)
    db.commit()
    db.refresh(u)
    return u


def _tok(client, username, password="Admin123!"):
    r = client.post("/token", data={"username": username, "password": password})
    assert r.status_code == 200, f"Login failed for {username}: {r.text}"
    return {"Authorization": f"Bearer {r.json()['access_token']}"}


def _make_kg(db, name_ar, status=models.KindergartenStatus.ACTIVE, capacity=100):
    kg = models.Kindergarten(
        name_ar=name_ar,
        governorate="عمان",
        district="عمان",
        area="test",
        address_line="test",
        contact_phone="0790000000",
        total_capacity=capacity,
        status=status,
    )
    db.add(kg)
    db.commit()
    db.refresh(kg)
    return kg


EXPECTED_KEYS = {
    "total", "active", "frozen", "draft", "inactive",
    "deleted", "avg_occupancy", "total_children", "active_children", "total_capacity",
}


def test_stats_admin_returns_expected_shape(client, test_db):
    _make_admin(test_db, "stats_admin_shape")
    _make_kg(test_db, "روضة نشطة", models.KindergartenStatus.ACTIVE, capacity=100)
    headers = _tok(client, "stats_admin_shape")

    r = client.get("/api/admin/kindergartens/stats", headers=headers)
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["success"] is True
    data = body["data"]
    assert EXPECTED_KEYS.issubset(data.keys()), f"missing keys: {EXPECTED_KEYS - set(data)}"
    # every count is a non-negative int; avg_occupancy is numeric
    for k in ("total", "active", "frozen", "draft", "inactive", "deleted",
              "total_children", "active_children", "total_capacity"):
        assert isinstance(data[k], int) and data[k] >= 0
    assert isinstance(data["avg_occupancy"], (int, float))
    # the active roster excludes deleted and includes our seeded active KG
    assert data["active"] >= 1
    assert data["total"] >= 1


def test_stats_counts_reflect_status(client, test_db):
    _make_admin(test_db, "stats_admin_counts")
    _make_kg(test_db, "نشطة 1", models.KindergartenStatus.ACTIVE)
    _make_kg(test_db, "مجمدة 1", models.KindergartenStatus.FROZEN)
    _make_kg(test_db, "محذوفة 1", models.KindergartenStatus.DELETED)
    headers = _tok(client, "stats_admin_counts")

    data = client.get("/api/admin/kindergartens/stats", headers=headers).json()["data"]
    assert data["active"] >= 1
    assert data["frozen"] >= 1
    assert data["deleted"] >= 1
    # total is the non-deleted roster, so it must not count the deleted KG
    assert data["total"] == data["active"] + data["frozen"] + data["draft"] + data["inactive"]


def test_stats_forbidden_for_non_admin(client, test_db):
    _make_user(test_db, "stats_supervisor", role=models.UserRole.SUPERVISOR)
    headers = _tok(client, "stats_supervisor", password="Pass123!")
    r = client.get("/api/admin/kindergartens/stats", headers=headers)
    assert r.status_code == 403


def test_stats_requires_authentication(client, test_db):
    r = client.get("/api/admin/kindergartens/stats")
    assert r.status_code in (401, 403)
