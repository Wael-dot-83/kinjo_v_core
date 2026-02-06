from datetime import date

import models


def create_kindergarten(test_db, name_suffix, governorate, phone_suffix):
    kindergarten = models.Kindergarten(
        name_ar=f"روضة {name_suffix}",
        name_en=f"KG {name_suffix}",
        governorate=governorate,
        city="City",
        area="Area",
        address_line="Address Line",
        contact_phone=f"+96279000{phone_suffix}",
        status=models.KindergartenStatus.ACTIVE
    )
    test_db.add(kindergarten)
    test_db.commit()
    test_db.refresh(kindergarten)
    return kindergarten


def create_staff(test_db, username, role, kindergarten_id):
    user = models.User(
        username=username,
        email=f"{username}@test.com",
        hashed_password="hashed",
        role=role,
        status=models.UserStatus.ACTIVE,
        kindergarten_id=kindergarten_id
    )
    test_db.add(user)
    test_db.commit()
    test_db.refresh(user)
    return user


def create_parent(test_db, username, home_governorate, enrollment_kindergarten_ids=None):
    user = models.User(
        username=username,
        email=f"{username}@test.com",
        hashed_password="hashed",
        role=models.UserRole.PARENT,
        status=models.UserStatus.ACTIVE
    )
    test_db.add(user)
    test_db.commit()
    test_db.refresh(user)

    profile = models.ParentProfile(
        user_id=user.id,
        first_name="Parent",
        last_name=username,
        phone_number=f"+96279{user.id:07d}",
        gender=models.Gender.MALE,
        nationality="Jordanian",
        home_governorate=home_governorate,
        home_city="City",
        home_area="Area",
        home_address_line="Address",
        correspondence_preference=True
    )
    test_db.add(profile)
    test_db.commit()
    test_db.refresh(profile)

    for index, kg_id in enumerate(enrollment_kindergarten_ids or []):
        child = models.Child(
            parent_id=profile.id,
            first_name=f"Child{index}",
            last_name="Test",
            gender=models.Gender.MALE,
            date_of_birth=date(2021, 1, 1),
            father_name="Father",
            mother_first_name="Mother",
            mother_last_name="Last",
            mother_nationality="Jordanian",
            media_consent=True
        )
        test_db.add(child)
        test_db.commit()
        test_db.refresh(child)

        enrollment = models.EnrollmentApplication(
            child_id=child.id,
            kindergarten_id=kg_id,
            status=models.EnrollmentStatus.ACTIVE
        )
        test_db.add(enrollment)
        test_db.commit()

    return user


def test_admin_send_all_users_and_roles(
    client,
    test_db,
    auth_headers_admin,
    sample_kindergarten,
    manager_user,
    supervisor_user,
    parent_user,
    parent_enrollment
):
    kg_irbid = create_kindergarten(test_db, "إربد", "Irbid", "2001")
    manager_irbid = create_staff(test_db, "manager_irbid", models.UserRole.MANAGER, kg_irbid.id)
    supervisor_irbid = create_staff(test_db, "supervisor_irbid", models.UserRole.SUPERVISOR, kg_irbid.id)
    parent_irbid = create_parent(test_db, "parent_irbid", "Irbid", [kg_irbid.id])

    response = client.post(
        "/api/admin/messages",
        json={
            "subject": "All users",
            "message_body": "Hello everyone",
            "target": {"mode": "ALL_USERS"}
        },
        headers=auth_headers_admin
    )
    assert response.status_code == 201
    msg_id = response.json()["id"]
    recipient_ids = {
        row.recipient_user_id
        for row in test_db.query(models.MessageRecipient).filter(
            models.MessageRecipient.message_id == msg_id
        ).all()
    }
    assert recipient_ids == {
        manager_user.id,
        supervisor_user.id,
        parent_user.id,
        manager_irbid.id,
        supervisor_irbid.id,
        parent_irbid.id
    }

    response = client.post(
        "/api/admin/messages",
        json={
            "subject": "Managers only",
            "message_body": "Hello managers",
            "target": {"mode": "ALL_MANAGERS"}
        },
        headers=auth_headers_admin
    )
    assert response.status_code == 201
    msg_id = response.json()["id"]
    recipient_ids = {
        row.recipient_user_id
        for row in test_db.query(models.MessageRecipient).filter(
            models.MessageRecipient.message_id == msg_id
        ).all()
    }
    assert recipient_ids == {manager_user.id, manager_irbid.id}

    response = client.post(
        "/api/admin/messages",
        json={
            "subject": "Parents only",
            "message_body": "Hello parents",
            "target": {"mode": "ALL_PARENTS"}
        },
        headers=auth_headers_admin
    )
    assert response.status_code == 201
    msg_id = response.json()["id"]
    recipient_ids = {
        row.recipient_user_id
        for row in test_db.query(models.MessageRecipient).filter(
            models.MessageRecipient.message_id == msg_id
        ).all()
    }
    assert recipient_ids == {parent_user.id, parent_irbid.id}


def test_admin_governorate_targeting(
    client,
    test_db,
    auth_headers_admin,
    sample_kindergarten,
    manager_user,
    supervisor_user,
    parent_user,
    parent_enrollment
):
    kg_irbid = create_kindergarten(test_db, "إربد", "Irbid", "2002")
    manager_irbid = create_staff(test_db, "manager_irbid", models.UserRole.MANAGER, kg_irbid.id)
    supervisor_irbid = create_staff(test_db, "supervisor_irbid", models.UserRole.SUPERVISOR, kg_irbid.id)
    parent_irbid = create_parent(test_db, "parent_irbid", "Irbid", [kg_irbid.id])
    parent_home_only = create_parent(test_db, "parent_home_only", "Irbid", [])
    parent_home_enrolled_elsewhere = create_parent(test_db, "parent_home_else", "Irbid", [sample_kindergarten.id])

    response = client.post(
        "/api/admin/messages",
        json={
            "subject": "Irbid update",
            "message_body": "Irbid only",
            "target": {
                "mode": "GOVERNORATE",
                "roles": ["MANAGER", "SUPERVISOR", "PARENT"],
                "governorates": ["Irbid"]
            }
        },
        headers=auth_headers_admin
    )
    assert response.status_code == 201
    msg_id = response.json()["id"]
    recipient_ids = {
        row.recipient_user_id
        for row in test_db.query(models.MessageRecipient).filter(
            models.MessageRecipient.message_id == msg_id
        ).all()
    }
    assert recipient_ids == {
        manager_irbid.id,
        supervisor_irbid.id,
        parent_irbid.id,
        parent_home_only.id
    }
    assert manager_user.id not in recipient_ids
    assert supervisor_user.id not in recipient_ids
    assert parent_user.id not in recipient_ids
    assert parent_home_enrolled_elsewhere.id not in recipient_ids


def test_admin_kindergarten_targeting_dedup(
    client,
    test_db,
    auth_headers_admin,
    sample_kindergarten
):
    kg_irbid = create_kindergarten(test_db, "إربد", "Irbid", "2003")
    parent_multi = create_parent(test_db, "parent_multi", "Amman", [sample_kindergarten.id, kg_irbid.id])
    parent_irbid = create_parent(test_db, "parent_irbid", "Irbid", [kg_irbid.id])

    response = client.post(
        "/api/admin/messages",
        json={
            "subject": "Selected KGs",
            "message_body": "Two kindergartens",
            "target": {
                "mode": "KINDERGARTENS",
                "roles": ["PARENT"],
                "kindergarten_ids": [sample_kindergarten.id, kg_irbid.id]
            }
        },
        headers=auth_headers_admin
    )
    assert response.status_code == 201
    msg_id = response.json()["id"]
    recipients = test_db.query(models.MessageRecipient).filter(
        models.MessageRecipient.message_id == msg_id
    ).all()
    recipient_ids = {row.recipient_user_id for row in recipients}
    assert recipient_ids == {parent_multi.id, parent_irbid.id}
    assert test_db.query(models.MessageRecipient).filter(
        models.MessageRecipient.message_id == msg_id,
        models.MessageRecipient.recipient_user_id == parent_multi.id
    ).count() == 1


def test_admin_preview_breakdown_counts(
    client,
    test_db,
    auth_headers_admin,
    sample_kindergarten
):
    kg_irbid = create_kindergarten(test_db, "إربد", "Irbid", "3005")
    manager_irbid = create_staff(test_db, "manager_preview", models.UserRole.MANAGER, kg_irbid.id)
    parent_preview = create_parent(test_db, "parent_preview", "Irbid", [kg_irbid.id])

    response = client.get(
        "/api/admin/message-recipients/preview",
        params={
            "mode": "KINDERGARTENS",
            "kindergarten_ids": [sample_kindergarten.id, kg_irbid.id],
            "roles": ["PARENT", "MANAGER"]
        },
        headers=auth_headers_admin
    )
    assert response.status_code == 200
    payload = response.json()
    assert payload["total_count"] >= 2
    assert payload["by_role"]["PARENT"] >= 1
    assert payload["by_role"]["MANAGER"] >= 1
    assert "by_governorate" in payload
    assert "by_kindergarten" in payload


def test_admin_search_filtering(
    client,
    test_db,
    auth_headers_admin,
    sample_kindergarten
):
    unique_parent = create_parent(test_db, "search_unique", "Amman", [sample_kindergarten.id])
    another_parent = create_parent(test_db, "other_parent", "Irbid", [])

    response = client.get(
        "/api/admin/message-recipients",
        params={
            "roles": ["PARENT"],
            "search": "search_unique"
        },
        headers=auth_headers_admin
    )
    assert response.status_code == 200
    data = response.json()
    assert len(data["items"]) == 1
    assert data["items"][0]["id"] == unique_parent.id


def test_admin_deduplication_across_governorate_and_kindergarten(
    client,
    test_db,
    auth_headers_admin,
    sample_kindergarten
):
    kg_irbid = create_kindergarten(test_db, "إربد 2", "Irbid", "3006")
    parent_multi = create_parent(test_db, "parent_overlap", "Irbid", [sample_kindergarten.id, kg_irbid.id])

    response = client.post(
        "/api/admin/messages",
        json={
            "subject": "Overlap dedupe",
            "message_body": "This parent should only receive once",
            "target": {
                "mode": "GOVERNORATE",
                "governorates": ["Irbid"],
                "roles": ["PARENT"]
            }
        },
        headers=auth_headers_admin
    )
    assert response.status_code == 201
    recipients = test_db.query(models.MessageRecipient).filter(
        models.MessageRecipient.message_id == response.json()["id"]
    ).all()
    assert {row.recipient_user_id for row in recipients} == {parent_multi.id}


def test_admin_endpoints_require_admin(
    client,
    auth_headers_manager,
    auth_headers_parent
):
    response = client.get("/api/admin/message-recipients", headers=auth_headers_manager)
    assert response.status_code == 403

    response = client.post(
        "/api/admin/messages",
        json={
            "subject": "Nope",
            "message_body": "Nope",
            "target": {"mode": "ALL_USERS"}
        },
        headers=auth_headers_manager
    )
    assert response.status_code == 403

    response = client.get("/api/admin/message-recipients", headers=auth_headers_parent)
    assert response.status_code == 403


def test_manager_cannot_target_outside_kindergarten(
    client,
    test_db,
    manager_token,
    sample_kindergarten
):
    other_kg = create_kindergarten(test_db, "الزرقاء", "Zarqa", "2004")
    headers_manager = {"Authorization": f"Bearer {manager_token}"}

    response = client.post(
        "/comm/messages",
        json={
            "subject": "Out of scope",
            "message_body": "Should be blocked",
            "message_type": "announcement",
            "audience": {
                "roles": ["PARENT"],
                "kindergarten_ids": [other_kg.id]
            }
        },
        headers=headers_manager
    )
    assert response.status_code == 403


def test_inbox_visibility_no_leakage(
    client,
    auth_headers_admin,
    auth_headers_manager,
    auth_headers_parent,
    manager_user
):
    response = client.post(
        "/api/admin/messages",
        json={
            "subject": "Managers only",
            "message_body": "Managers announcement",
            "target": {"mode": "ALL_MANAGERS"}
        },
        headers=auth_headers_admin
    )
    assert response.status_code == 201
    msg_id = response.json()["id"]

    response = client.get("/comm/messages", headers=auth_headers_manager)
    assert response.status_code == 200
    items = response.json()["items"]
    assert any(item["id"] == msg_id for item in items)

    response = client.get("/comm/messages", headers=auth_headers_parent)
    assert response.status_code == 200
    items = response.json()["items"]
    assert all(item["id"] != msg_id for item in items)
