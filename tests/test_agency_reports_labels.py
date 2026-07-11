"""Tests for the agency-report Arabic label metadata + agency logo/icon source.

The opened-report UI must never show raw machine field names (e.g.
"eligible_children", "governorate"); the backend now ships Arabic
``summary_labels``/``column_labels`` alongside the data, and every agency in
the catalog exposes an ``icon`` used for its logo/branding badge.
"""
import models
from auth import get_password_hash
from agency_reports_service import AgencyReportsService


class _DummyDB:
    def query(self, *a, **k):
        class _Q:
            def scalar(self):
                return 0
        return _Q()


def _make_admin(db, username="agency_lbl_admin"):
    u = models.User(
        username=username, email=f"{username}@example.com",
        hashed_password=get_password_hash("Admin123!"),
        role=models.UserRole.ADMIN, status=models.UserStatus.ACTIVE,
    )
    db.add(u); db.commit(); db.refresh(u)
    return u


def _tok(client, username):
    r = client.post("/token", data={"username": username, "password": "Admin123!"})
    assert r.status_code == 200, r.text
    return {"Authorization": f"Bearer {r.json()['access_token']}"}


def _make_kg(db, name_ar, governorate, district):
    kg = models.Kindergarten(
        name_ar=name_ar, governorate=governorate, district=district,
        area="a", address_line="a", contact_phone="0790000000",
        status=models.KindergartenStatus.ACTIVE,
    )
    db.add(kg); db.commit()
    return kg


def test_every_catalog_agency_exposes_icon_for_logo_badge():
    catalog = AgencyReportsService(_DummyDB()).catalog()
    assert len(catalog["agencies"]) == 7
    # each agency must carry an icon so the UI renders a logo/branding badge
    assert all(a.get("icon") for a in catalog["agencies"])


def test_agency_report_payload_ships_arabic_labels(client, test_db):
    _make_admin(test_db, "agency_lbl_admin")
    _make_kg(test_db, "روضة عمّان", "عمان", "القويسمة")
    headers = _tok(client, "agency_lbl_admin")

    r = client.get(
        "/api/admin/agency-reports/mosd/reports/kindergarten_registry",
        headers=headers,
    )
    assert r.status_code == 200, r.text
    payload = r.json()
    assert "summary_labels" in payload and "column_labels" in payload

    # No raw machine key is left unlabeled, and known keys map to Arabic.
    assert payload["summary_labels"].get("total_kindergartens") == "إجمالي الحضانات"
    for key in payload["summary"]:
        assert payload["summary_labels"].get(key), f"missing label for summary key {key}"

    rows = payload.get("breakdowns") or []
    if rows:
        assert payload["column_labels"].get("governorate") == "المحافظة"
        for col in rows[0]:
            assert payload["column_labels"].get(col), f"missing label for column {col}"
        # labels must be non-ASCII (Arabic), never the raw English key
        assert payload["column_labels"]["governorate"] != "governorate"
