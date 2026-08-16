"""Focused regressions for Admin bulk-create and recipient-query parity."""

from __future__ import annotations

from sqlalchemy.exc import IntegrityError

import models
from auth import get_password_hash
from config import settings


def _staff_payload(username: str, email: str, kg_id: int) -> dict:
    return {
        "username": username,
        "email": email,
        "password": "BulkUser123!",
        "role": "SUPERVISOR",
        "kindergarten_id": kg_id,
    }


def _make_supervisors(db, kg_id: int, count: int, prefix: str) -> list[models.User]:
    users = [
        models.User(
            username=f"{prefix}_{index}",
            email=f"{prefix}_{index}@example.com",
            hashed_password=get_password_hash("Supervisor123!"),
            role=models.UserRole.SUPERVISOR,
            status=models.UserStatus.ACTIVE,
            kindergarten_id=kg_id,
        )
        for index in range(count)
    ]
    db.add_all(users)
    db.commit()
    return users


def test_bulk_create_rejects_intra_payload_username_and_email_duplicates(
    client, test_db, sample_kindergarten, auth_headers_admin
):
    payloads = [
        _staff_payload("batch_unique", "batch_unique@example.com", sample_kindergarten.id),
        _staff_payload("batch_unique", "second@example.com", sample_kindergarten.id),
        _staff_payload("third_unique", "batch_unique@example.com", sample_kindergarten.id),
    ]

    response = client.post(
        "/api/admin/users/bulk-create",
        json={"users": payloads},
        headers=auth_headers_admin,
    )
    assert response.status_code == 200, response.text
    body = response.json()
    assert body["succeeded_count"] == 1
    assert body["failed_count"] == 2
    assert [(error["row"], error["field"]) for error in body["errors"]] == [
        (2, "username"),
        (3, "email"),
    ]


def test_bulk_created_staff_have_temporary_credentials_and_supervisor_profile(
    client, test_db, sample_kindergarten, auth_headers_admin
):
    response = client.post(
        "/api/admin/users/bulk-create",
        json={
            "users": [
                _staff_payload(
                    "profiled_supervisor",
                    "profiled_supervisor@example.com",
                    sample_kindergarten.id,
                )
            ]
        },
        headers=auth_headers_admin,
    )
    assert response.status_code == 200, response.text
    created = test_db.query(models.User).filter_by(username="profiled_supervisor").one()
    assert created.must_change_password is True
    profile = test_db.query(models.SupervisorProfile).filter_by(user_id=created.id).one()
    assert profile.kindergarten_id == sample_kindergarten.id


def test_bulk_insert_race_is_isolated_and_error_is_sanitized(
    client, test_db, sample_kindergarten, auth_headers_admin, monkeypatch
):
    original_flush = test_db.flush
    raised = False

    def racing_flush(*args, **kwargs):
        nonlocal raised
        if not raised and any(
            isinstance(obj, models.User) and obj.username == "race_loser"
            for obj in test_db.new
        ):
            raised = True
            raise IntegrityError(
                "INSERT users password=plaintext-secret", {}, Exception("unique")
            )
        return original_flush(*args, **kwargs)

    monkeypatch.setattr(test_db, "flush", racing_flush)
    response = client.post(
        "/api/admin/users/bulk-create",
        json={
            "users": [
                _staff_payload("race_loser", "race_loser@example.com", sample_kindergarten.id),
                _staff_payload("race_winner", "race_winner@example.com", sample_kindergarten.id),
            ]
        },
        headers=auth_headers_admin,
    )
    assert response.status_code == 200, response.text
    body = response.json()
    assert body["succeeded_count"] == 1
    assert body["failed_count"] == 1
    assert "plaintext-secret" not in response.text
    assert body["errors"][0]["error"] == "Username or email became unavailable"
    assert test_db.query(models.User).filter_by(username="race_loser").first() is None
    assert test_db.query(models.User).filter_by(username="race_winner").one()


def test_recipient_list_and_both_previews_share_exact_db_pagination(
    client, test_db, sample_kindergarten, auth_headers_admin
):
    _make_supervisors(test_db, sample_kindergarten.id, 5, "paged_sup")

    list_pages = []
    for page in (1, 2):
        response = client.get(
            "/api/admin/message-recipients",
            params={"roles": "SUPERVISOR", "page": page, "page_size": 2},
            headers=auth_headers_admin,
        )
        assert response.status_code == 200, response.text
        list_pages.append(response.json())
    assert list_pages[0]["pagination"]["total"] == 5
    assert list_pages[1]["pagination"]["total"] == 5
    assert {item["id"] for item in list_pages[0]["items"]}.isdisjoint(
        {item["id"] for item in list_pages[1]["items"]}
    )

    post_pages = []
    for page in (1, 2):
        response = client.post(
            "/api/admin/messages/preview",
            json={
                "target": {"mode": "ALL_SUPERVISORS"},
                "page": page,
                "page_size": 2,
            },
            headers=auth_headers_admin,
        )
        assert response.status_code == 200, response.text
        post_pages.append(response.json())
    assert post_pages[0]["pagination"]["total"] == 5
    assert post_pages[1]["pagination"]["total"] == 5
    assert {item["id"] for item in post_pages[0]["items"]}.isdisjoint(
        {item["id"] for item in post_pages[1]["items"]}
    )

    get_pages = []
    for page in (1, 2):
        response = client.get(
            "/api/admin/message-recipients/preview",
            params={"mode": "ALL_SUPERVISORS", "page": page, "page_size": 2},
            headers=auth_headers_admin,
        )
        assert response.status_code == 200, response.text
        get_pages.append(response.json())
    assert get_pages[0]["total_count"] == 5
    assert get_pages[0]["by_role"] == {"SUPERVISOR": 5}
    assert get_pages[1]["by_role"] == {"SUPERVISOR": 5}
    assert {item["id"] for item in get_pages[0]["sample_recipients"]}.isdisjoint(
        {item["id"] for item in get_pages[1]["sample_recipients"]}
    )


def test_preview_totals_are_not_truncated_before_send_limit_check(
    client, test_db, sample_kindergarten, auth_headers_admin, monkeypatch
):
    _make_supervisors(test_db, sample_kindergarten.id, 3, "over_limit_sup")
    monkeypatch.setattr(settings, "MAX_MESSAGE_RECIPIENTS", 2)

    get_preview = client.get(
        "/api/admin/message-recipients/preview",
        params={"mode": "ALL_SUPERVISORS"},
        headers=auth_headers_admin,
    )
    assert get_preview.status_code == 200
    assert get_preview.json()["total_count"] == 3
    assert get_preview.json()["by_role"] == {"SUPERVISOR": 3}

    post_preview = client.post(
        "/api/admin/messages/preview",
        json={"target": {"mode": "ALL_SUPERVISORS"}},
        headers=auth_headers_admin,
    )
    assert post_preview.status_code == 200
    assert post_preview.json()["pagination"]["total"] == 3

    send = client.post(
        "/api/admin/messages",
        json={
            "subject": "Limit check",
            "message_body": "Must reject the exact over-limit recipient set.",
            "target": {"mode": "ALL_SUPERVISORS"},
        },
        headers=auth_headers_admin,
    )
    assert send.status_code == 400
    assert "Too many recipients (3)" in send.text


def test_malformed_governorate_option_source_returns_422_instead_of_widening(
    client, auth_headers_admin, monkeypatch
):
    import services.jordan_locations

    monkeypatch.setattr(
        services.jordan_locations,
        "get_all_governorates",
        lambda: [{"name_ar": "عمان"}],
    )
    response = client.get(
        "/api/admin/options/governorates", headers=auth_headers_admin
    )
    assert response.status_code == 422
    assert response.json()["error"]["fields"] == {"governorates": "invalid"}
