"""Production contracts for dashboard customization and Admin nursery paging."""

from __future__ import annotations

import copy
import inspect
import logging

import pytest

import models
from api import kindergartens as kindergarten_api
from cache_service import cache_service
from dashboard_customization import DashboardCustomizationService, dashboard_customization


def _clear_widget_cache(*user_ids: int) -> None:
    for user_id in user_ids:
        cache_service.delete(f"user_widgets:{user_id}")
        for role in DashboardCustomizationService.DEFAULT_WIDGETS:
            cache_service.delete(f"user_widgets:{user_id}:{role}")


def _admin_widgets() -> list[dict]:
    return copy.deepcopy(DashboardCustomizationService.DEFAULT_WIDGETS["admin"])


def _manager_widgets() -> list[dict]:
    return copy.deepcopy(DashboardCustomizationService.DEFAULT_WIDGETS["manager"])


def test_default_and_cached_widgets_are_isolated_between_callers(test_db):
    _clear_widget_cache(91001, 91002)

    first = dashboard_customization.get_user_widgets(91001, "admin", test_db)
    first[0]["enabled"] = False
    first[0]["title"] = "mutated"

    same_user_again = dashboard_customization.get_user_widgets(91001, "admin", test_db)
    second_user = dashboard_customization.get_user_widgets(91002, "admin", test_db)

    assert same_user_again[0]["enabled"] is True
    assert same_user_again[0]["title"] == "المؤشرات التشغيلية"
    assert second_user[0]["enabled"] is True
    assert DashboardCustomizationService.DEFAULT_WIDGETS["admin"][0]["enabled"] is True
    assert DashboardCustomizationService.DEFAULT_WIDGETS["admin"][0]["title"] == "المؤشرات التشغيلية"


def test_dashboard_service_uses_but_does_not_close_request_session(test_db):
    class TrackingSession:
        def __init__(self, wrapped):
            self.wrapped = wrapped
            self.closed = False

        def __getattr__(self, name):
            return getattr(self.wrapped, name)

        def close(self):
            self.closed = True

    session = TrackingSession(test_db)
    _clear_widget_cache(92001)

    dashboard_customization.get_user_widgets(92001, "admin", session)

    assert session.closed is False
    assert "next(get_db())" not in inspect.getsource(DashboardCustomizationService)


@pytest.mark.parametrize(
    "mutate",
    [
        lambda widgets: widgets[:-1],
        lambda widgets: widgets + [copy.deepcopy(widgets[-1])],
        lambda widgets: [*widgets[:-1], {**widgets[-1], "id": "unknown-widget"}],
        lambda widgets: [widgets[0], {**widgets[1], "id": widgets[0]["id"]}, *widgets[2:]],
        lambda widgets: [widgets[0], {**widgets[1], "order": widgets[0]["order"]}, *widgets[2:]],
        lambda widgets: [{**widgets[0], "extra": {"unbounded": True}}, *widgets[1:]],
    ],
    ids=["too-short", "too-long", "unknown-id", "duplicate-id", "duplicate-order", "extra-fields"],
)
def test_widget_update_rejects_malformed_configuration(client, auth_headers_admin, mutate):
    response = client.put(
        "/api/dashboard/widgets",
        json=mutate(_admin_widgets()),
        headers=auth_headers_admin,
    )

    assert response.status_code == 400
    assert response.json()["detail"] == "Invalid widget configuration"


def test_widget_update_rejects_widgets_unavailable_to_role(client, auth_headers_manager):
    response = client.put(
        "/api/dashboard/widgets",
        json=_admin_widgets(),
        headers=auth_headers_manager,
    )

    assert response.status_code == 400


def test_widget_update_accepts_canonical_role_configuration(client, auth_headers_manager):
    widgets = _manager_widgets()
    widgets[0]["enabled"] = False

    response = client.put(
        "/api/dashboard/widgets",
        json=widgets,
        headers=auth_headers_manager,
    )

    assert response.status_code == 200
    loaded = client.get("/api/dashboard/widgets", headers=auth_headers_manager)
    assert loaded.status_code == 200
    assert loaded.json()["widgets"][0]["enabled"] is False


def test_unknown_widget_toggle_fails_instead_of_reporting_success(client, auth_headers_admin):
    response = client.patch(
        "/api/dashboard/widgets/not-a-widget/toggle?enabled=false",
        headers=auth_headers_admin,
    )

    assert response.status_code == 404
    assert response.json()["detail"] == "Widget not found or operation invalid"


@pytest.mark.parametrize(
    "order",
    [
        ["operational_metrics"],
        [
            "operational_metrics",
            "attendance_trend",
            "incidents_trend",
            "enrollment_trend",
            "gcei_trend",
            "not-a-widget",
        ],
        [
            "operational_metrics",
            "operational_metrics",
            "incidents_trend",
            "enrollment_trend",
            "gcei_trend",
            "alerts",
        ],
    ],
    ids=["incomplete", "unknown", "duplicate"],
)
def test_widget_reorder_rejects_incomplete_unknown_or_duplicate_ids(
    client, auth_headers_admin, order
):
    response = client.put(
        "/api/dashboard/widgets/reorder",
        json=order,
        headers=auth_headers_admin,
    )

    assert response.status_code == 400


def _add_paged_nursery(test_db, index: int, children: int) -> models.Kindergarten:
    nursery = models.Kindergarten(
        name_ar=f"حضانة عقد التصفح {index}",
        name_en=f"Pagination Contract Nursery {index}",
        license_number=f"PAGE-CONTRACT-{index}",
        governorate="Amman",
        district="Amman",
        area="Abdoun",
        address_line=f"Contract road {index}",
        contact_phone=f"+96279001{index:04d}",
        status=models.KindergartenStatus.ACTIVE,
        current_child_count=children,
        total_capacity=40,
    )
    test_db.add(nursery)
    return nursery


def test_metric_filters_define_total_and_pages_before_pagination(
    client, test_db, auth_headers_admin
):
    for index, children in enumerate((5, 10, 20, 30, 40), start=1):
        _add_paged_nursery(test_db, index, children)
    test_db.commit()

    params = {
        "q": "Pagination Contract Nursery",
        "min_children": 20,
        "min_occupancy": 50,
        "limit": 2,
    }
    first = client.get(
        "/api/kindergartens", params={**params, "skip": 0}, headers=auth_headers_admin
    )
    second = client.get(
        "/api/kindergartens", params={**params, "skip": 2}, headers=auth_headers_admin
    )

    assert first.status_code == 200
    assert second.status_code == 200
    first_data = first.json()["data"]
    second_data = second.json()["data"]
    assert first_data["total"] == second_data["total"] == 3
    assert first_data["returned"] == 2
    assert second_data["returned"] == 1
    assert [item["child_count"] for item in first_data["items"]] == [40, 30]
    assert [item["child_count"] for item in second_data["items"]] == [20]
    assert all(
        item["occupancy_pct"] >= 50
        for item in [*first_data["items"], *second_data["items"]]
    )


def _create_with_manager_payload() -> dict:
    return {
        "kindergarten": {
            "name_ar": "حضانة اختبار الخطأ الداخلي",
            "name_en": "Internal Error Nursery",
            "governorate": "Amman",
            "district": "Amman",
            "area": "Abdoun",
            "address_line": "Contract road",
            "contact_phone": "+962790099991",
            "license_number": "INTERNAL-ERROR-1",
        },
        "manager": {
            "full_name": "Contract Manager",
            "phone_number": "+962790099992",
            "nationality": "Jordanian",
            "national_id": "9891234999",
            "username": "internal_error_manager",
            "email": "internal-error-manager@example.com",
            "password": "Manager123!",
        },
    }


def test_create_with_manager_logs_but_does_not_disclose_internal_exception(
    client, test_db, auth_headers_admin, monkeypatch, caplog
):
    secret_detail = "database-password=do-not-expose"

    def fail_hash(_password):
        raise RuntimeError(secret_detail)

    monkeypatch.setattr(kindergarten_api, "get_password_hash", fail_hash)
    caplog.set_level(logging.ERROR, logger=kindergarten_api.__name__)
    before = test_db.query(models.Kindergarten).count()

    response = client.post(
        "/api/admin/kindergartens/with-manager",
        json=_create_with_manager_payload(),
        headers=auth_headers_admin,
    )

    assert response.status_code == 500
    body = response.json()
    assert body["success"] is False
    assert body["message"].startswith("تعذر إنشاء الحضانة والمدير")
    assert "nursery" in body["message"].lower()
    assert secret_detail not in response.text
    assert secret_detail in caplog.text
    test_db.expire_all()
    assert test_db.query(models.Kindergarten).count() == before


def test_read_only_kindergarten_detail_does_not_acquire_row_lock():
    source = inspect.getsource(kindergarten_api.get_kindergarten)

    assert ".with_for_update()" not in source
