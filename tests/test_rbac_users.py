import pytest
from jose import jwt
from auth import get_password_hash, verify_password
import models


def _create_kindergarten(db, name_suffix):
    kg = models.Kindergarten(
        name_ar=f"روضة اختبار {name_suffix}",
        name_en=f"Test KG {name_suffix}",
        license_number=f"LIC-{name_suffix}-001",
        governorate="Amman",
        city="Amman",
        area="Abdoun",
        address_line="123 Test Street",
        contact_phone="+962791234567",
        contact_email=f"contact-{name_suffix}@kg.jo",
        status=models.KindergartenStatus.ACTIVE
    )
    db.add(kg)
    db.commit()
    db.refresh(kg)
    return kg


def _create_user(db, username, email, role, kindergarten_id=None, password="User12345!"):
    user = models.User(
        username=username,
        email=email,
        hashed_password=get_password_hash(password),
        role=role,
        status=models.UserStatus.ACTIVE,
        kindergarten_id=kindergarten_id
    )
    db.add(user)
    db.commit()
    db.refresh(user)
    return user


class TestUserRBAC:
    def test_manager_user_list_scoped(self, client, test_db, manager_user, auth_headers_manager):
        other_kg = _create_kindergarten(test_db, "B")
        _create_user(
            test_db,
            username="other_user",
            email="other_user@test.com",
            role=models.UserRole.SUPERVISOR,
            kindergarten_id=other_kg.id
        )

        response = client.get("/api/users", headers=auth_headers_manager)
        assert response.status_code == 200
        data = response.json()
        assert data, "Expected at least the manager in the list"
        assert all(u["kindergarten_id"] == manager_user.kindergarten_id for u in data)

    def test_manager_cannot_view_other_user(self, client, test_db, manager_user, auth_headers_manager):
        other_kg = _create_kindergarten(test_db, "C")
        other_user = _create_user(
            test_db,
            username="other_user_2",
            email="other_user_2@test.com",
            role=models.UserRole.SUPERVISOR,
            kindergarten_id=other_kg.id
        )

        response = client.get(f"/api/users/{other_user.id}", headers=auth_headers_manager)
        assert response.status_code == 403

    def test_manager_can_view_self(self, client, manager_user, auth_headers_manager):
        response = client.get(f"/api/users/{manager_user.id}", headers=auth_headers_manager)
        assert response.status_code == 200
        assert response.json()["id"] == manager_user.id


class TestAdminResetPassword:
    def test_admin_reset_requires_correct_admin_password(self, client, test_db, admin_user, auth_headers_admin):
        target_user = _create_user(
            test_db,
            username="target_user",
            email="target_user@test.com",
            role=models.UserRole.PARENT,
            password="OldPass123!"
        )

        response = client.post(
            f"/api/users/{target_user.id}/admin-reset-password",
            headers=auth_headers_admin,
            json={
                "new_password": "NewPass123!",
                "admin_password": "WrongPass123!"
            }
        )
        assert response.status_code == 401

        response = client.post(
            f"/api/users/{target_user.id}/admin-reset-password",
            headers=auth_headers_admin,
            json={
                "new_password": "NewPass123!",
                "admin_password": "Admin123!"
            }
        )
        assert response.status_code == 200

        test_db.refresh(target_user)
        assert verify_password("NewPass123!", target_user.hashed_password)


class TestAuthenticationRememberMe:
    def test_remember_me_extends_token_expiry(self, client, admin_user):
        response_default = client.post(
            "/token",
            data={
                "username": "testadmin",
                "password": "Admin123!"
            }
        )
        assert response_default.status_code == 200

        response_remember = client.post(
            "/token",
            data={
                "username": "testadmin",
                "password": "Admin123!",
                "remember_me": "true"
            }
        )
        assert response_remember.status_code == 200

        default_exp = jwt.get_unverified_claims(response_default.json()["access_token"])["exp"]
        remember_exp = jwt.get_unverified_claims(response_remember.json()["access_token"])["exp"]

        assert remember_exp - default_exp >= 24 * 60 * 60

