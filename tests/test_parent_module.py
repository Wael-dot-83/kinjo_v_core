"""
Comprehensive tests for the Parent Module:
- GET /api/parent/profile  (API)
- GET /api/parent/children (API)
- GET /api/parent/enrollments (API)
- /parent/profile  (frontend page)
- /parent/children  (frontend page)
- /parent/enrollments  (frontend page)
- /parent/dashboard  (role gate)
- /profile  (parent redirect)
- /enrollments  (parent redirect)
- /children  (parent redirect)
- /enrollments/{id}  (parent access control)
"""
import pytest
from datetime import date, timedelta
import models
from auth import get_password_hash


# ============================================================================
# API: GET /api/parent/profile
# ============================================================================


class TestParentProfileAPI:
    """Tests for GET /api/parent/profile"""

    def test_returns_profile_for_parent(self, client, auth_headers_parent, parent_user, test_db):
        """Parent should get their own profile"""
        response = client.get("/api/parent/profile", headers=auth_headers_parent)
        assert response.status_code == 200
        data = response.json()
        assert data["first_name"] == "Ahmad"
        assert data["last_name"] == "Al-Rashid"
        assert data["phone_number"] == "+962791234567"
        assert data["home_governorate"] == "Amman"
        assert data["home_district"] == "Amman"
        assert data["email"] == "testparent@test.com"
        assert data["username"] == "testparent@test.com"
        assert data["user_id"] == parent_user.id
        assert data["nationality"] == "Jordanian"
        assert data["national_id"] == "1234567890"
        assert "id" in data

    def test_includes_optional_fields(self, client, auth_headers_parent, parent_user, test_db):
        """Response should include all optional fields even if null"""
        response = client.get("/api/parent/profile", headers=auth_headers_parent)
        data = response.json()
        # These optional fields should be present (possibly null)
        for field in ["second_name", "first_name_en", "last_name_en",
                      "passport_number", "work_address", "profile_complete",
                      "profile_completed_at", "correspondence_preference"]:
            assert field in data, f"Field {field} missing from profile response"

    def test_403_for_admin(self, client, auth_headers_admin, admin_user, test_db):
        """Admin should get 403"""
        response = client.get("/api/parent/profile", headers=auth_headers_admin)
        assert response.status_code == 403

    def test_403_for_manager(self, client, auth_headers_manager, manager_user, test_db):
        """Manager should get 403"""
        response = client.get("/api/parent/profile", headers=auth_headers_manager)
        assert response.status_code == 403

    def test_403_for_supervisor(self, client, auth_headers_supervisor, supervisor_user, test_db):
        """Supervisor should get 403"""
        response = client.get("/api/parent/profile", headers=auth_headers_supervisor)
        assert response.status_code == 403

    def test_404_when_no_profile(self, client, test_db):
        """Parent user without a ParentProfile should get 404"""
        # Create a parent user WITHOUT a profile
        user = models.User(
            username="noprofile@test.com",
            email="noprofile@test.com",
            hashed_password=get_password_hash("Parent123!"),
            role=models.UserRole.PARENT,
            status=models.UserStatus.ACTIVE,
            preferred_language="en",
        )
        test_db.add(user)
        test_db.commit()

        # Login to get token
        response = client.post("/token", data={
            "username": "noprofile@test.com",
            "password": "Parent123!"
        })
        token = response.json()["access_token"]

        response = client.get("/api/parent/profile", headers={
            "Authorization": f"Bearer {token}"
        })
        assert response.status_code == 404
        assert "profile" in response.json()["detail"].lower()

    def test_unauthenticated_returns_401(self, client, test_db):
        """Should get 401 without auth"""
        response = client.get("/api/parent/profile")
        assert response.status_code == 401


# ============================================================================
# API: GET /api/parent/children
# ============================================================================


class TestParentChildrenAPI:
    """Tests for GET /api/parent/children"""

    def test_returns_children_list(self, client, auth_headers_parent, parent_user, sample_child, test_db):
        """Parent should see their children"""
        response = client.get("/api/parent/children", headers=auth_headers_parent)
        assert response.status_code == 200
        data = response.json()
        assert data["total"] == 1
        assert len(data["children"]) == 1

        child = data["children"][0]
        assert child["first_name"] == "Layla"
        assert child["last_name"] == "Al-Rashid"
        assert child["gender"] == "FEMALE"
        assert child["date_of_birth"] is not None
        assert child["father_name"] == "Ahmad Al-Rashid"
        assert child["mother_first_name"] == "Fatima"
        assert child["mother_last_name"] == "Hassan"

    def test_children_include_enrollment_info(self, client, auth_headers_parent, parent_user,
                                               sample_child, parent_enrollment, sample_kindergarten, test_db):
        """Children response should include enrollment details"""
        response = client.get("/api/parent/children", headers=auth_headers_parent)
        data = response.json()
        child = data["children"][0]
        assert "enrollments" in child
        assert len(child["enrollments"]) == 1

        enrollment = child["enrollments"][0]
        assert enrollment["status"] == "ACCEPTED"
        assert enrollment["kindergarten_name"] == "روضة الأمل"
        assert enrollment["kindergarten_id"] == sample_kindergarten.id

    def test_empty_children_list(self, client, auth_headers_parent, parent_user, test_db):
        """Parent with no children should get empty list"""
        response = client.get("/api/parent/children", headers=auth_headers_parent)
        assert response.status_code == 200
        data = response.json()
        assert data["total"] == 0
        assert data["children"] == []

    def test_multiple_children(self, client, auth_headers_parent, parent_user, test_db):
        """Parent with multiple children should see all of them"""
        profile = parent_user.parent_profile
        for i, name in enumerate(["Omar", "Sara", "Zaid"]):
            child = models.Child(
                parent_id=profile.id,
                first_name=name,
                last_name="Al-Rashid",
                gender=models.Gender.MALE if name != "Sara" else models.Gender.FEMALE,
                date_of_birth=date.today() - timedelta(days=365 * 3 + 30 * i),
                father_name="Ahmad Al-Rashid",
                mother_first_name="Fatima",
                mother_last_name="Hassan",
                mother_nationality="Jordanian",
                mother_national_id=f"0987654{i:03d}",
            )
            test_db.add(child)
        test_db.commit()

        response = client.get("/api/parent/children", headers=auth_headers_parent)
        data = response.json()
        assert data["total"] == 3
        names = [c["first_name"] for c in data["children"]]
        assert set(names) == {"Omar", "Sara", "Zaid"}

    def test_403_for_admin(self, client, auth_headers_admin, admin_user, test_db):
        """Admin should get 403"""
        response = client.get("/api/parent/children", headers=auth_headers_admin)
        assert response.status_code == 403

    def test_403_for_manager(self, client, auth_headers_manager, manager_user, test_db):
        """Manager should get 403"""
        response = client.get("/api/parent/children", headers=auth_headers_manager)
        assert response.status_code == 403

    def test_unauthenticated_returns_401(self, client, test_db):
        """Should get 401 without auth"""
        response = client.get("/api/parent/children")
        assert response.status_code == 401


# ============================================================================
# API: GET /api/parent/enrollments
# ============================================================================


class TestParentEnrollmentsAPI:
    """Tests for GET /api/parent/enrollments"""

    def test_returns_enrollments(self, client, auth_headers_parent, parent_user,
                                  sample_child, parent_enrollment, sample_kindergarten, test_db):
        """Parent should see their enrollments"""
        response = client.get("/api/parent/enrollments", headers=auth_headers_parent)
        assert response.status_code == 200
        data = response.json()
        assert data["total"] == 1
        assert len(data["enrollments"]) == 1

        enrollment = data["enrollments"][0]
        assert enrollment["child_name"] == "Layla Al-Rashid"
        assert enrollment["kindergarten_name"] == "روضة الأمل"
        assert enrollment["status"] == "ACCEPTED"
        assert enrollment["status_ar"] == "مقبول"
        assert enrollment["child_id"] == sample_child.id
        assert enrollment["kindergarten_id"] == sample_kindergarten.id

    def test_empty_enrollments_no_children(self, client, auth_headers_parent, parent_user, test_db):
        """Parent with no children should get empty enrollments"""
        response = client.get("/api/parent/enrollments", headers=auth_headers_parent)
        assert response.status_code == 200
        data = response.json()
        assert data["total"] == 0
        assert data["enrollments"] == []

    def test_empty_enrollments_with_children(self, client, auth_headers_parent, parent_user,
                                              sample_child, test_db):
        """Parent with children but no enrollments should get empty list"""
        response = client.get("/api/parent/enrollments", headers=auth_headers_parent)
        assert response.status_code == 200
        data = response.json()
        assert data["total"] == 0

    def test_multiple_enrollments_for_multiple_children(self, client, auth_headers_parent,
                                                         parent_user, test_db):
        """Parent with multiple children and enrollments"""
        profile = parent_user.parent_profile

        # Create 2 children
        child1 = models.Child(
            parent_id=profile.id, first_name="Omar", last_name="Al-Rashid",
            gender=models.Gender.MALE, date_of_birth=date.today() - timedelta(days=365 * 4),
            father_name="Ahmad", mother_first_name="Fatima", mother_last_name="H",
            mother_nationality="Jordanian", mother_national_id="111"
        )
        child2 = models.Child(
            parent_id=profile.id, first_name="Sara", last_name="Al-Rashid",
            gender=models.Gender.FEMALE, date_of_birth=date.today() - timedelta(days=365 * 3),
            father_name="Ahmad", mother_first_name="Fatima", mother_last_name="H",
            mother_nationality="Jordanian", mother_national_id="222"
        )
        test_db.add_all([child1, child2])
        test_db.commit()
        test_db.refresh(child1)
        test_db.refresh(child2)

        # Create 2 kindergartens
        kg1 = models.Kindergarten(
            name_ar="روضة الأمل", name_en="Hope KG",
            governorate="Amman", district="Amman", area="A",
            address_line="St 1", contact_phone="+962790000001",
            status=models.KindergartenStatus.ACTIVE
        )
        kg2 = models.Kindergarten(
            name_ar="روضة النور", name_en="Light KG",
            governorate="Amman", district="Amman", area="B",
            address_line="St 2", contact_phone="+962790000002",
            status=models.KindergartenStatus.ACTIVE
        )
        test_db.add_all([kg1, kg2])
        test_db.commit()
        test_db.refresh(kg1)
        test_db.refresh(kg2)

        # Create enrollments
        e1 = models.EnrollmentApplication(
            child_id=child1.id, kindergarten_id=kg1.id,
            status=models.EnrollmentStatus.ACCEPTED
        )
        e2 = models.EnrollmentApplication(
            child_id=child2.id, kindergarten_id=kg2.id,
            status=models.EnrollmentStatus.PENDING_REVIEW
        )
        test_db.add_all([e1, e2])
        test_db.commit()

        response = client.get("/api/parent/enrollments", headers=auth_headers_parent)
        data = response.json()
        assert data["total"] == 2
        child_names = {e["child_name"] for e in data["enrollments"]}
        assert "Omar Al-Rashid" in child_names
        assert "Sara Al-Rashid" in child_names

    def test_status_ar_mapping(self, client, auth_headers_parent, parent_user, test_db):
        """Arabic status labels should be correctly mapped"""
        profile = parent_user.parent_profile
        child = models.Child(
            parent_id=profile.id, first_name="T", last_name="T",
            gender=models.Gender.MALE, date_of_birth=date.today() - timedelta(days=365 * 3),
            father_name="A", mother_first_name="F", mother_last_name="H",
            mother_nationality="Jordanian", mother_national_id="333"
        )
        test_db.add(child)
        test_db.commit()
        test_db.refresh(child)

        kg = models.Kindergarten(
            name_ar="روضة", name_en="KG",
            governorate="Amman", district="Amman", area="A",
            address_line="St", contact_phone="+962790000099",
            status=models.KindergartenStatus.ACTIVE
        )
        test_db.add(kg)
        test_db.commit()
        test_db.refresh(kg)

        # Test different statuses
        status_map = {
            "DRAFT": "مسودة",
            "SUBMITTED": "مقدّم",
            "PENDING_REVIEW": "قيد المراجعة",
            "ACCEPTED": "مقبول",
            "REJECTED": "مرفوض",
        }
        for eng_status, arabic_label in status_map.items():
            enrollment = models.EnrollmentApplication(
                child_id=child.id, kindergarten_id=kg.id,
                status=models.EnrollmentStatus[eng_status]
            )
            test_db.add(enrollment)
            test_db.commit()

            response = client.get("/api/parent/enrollments", headers=auth_headers_parent)
            data = response.json()
            # Find the enrollment we just created
            found = [e for e in data["enrollments"] if e["status"] == eng_status]
            assert len(found) >= 1, f"Enrollment with status {eng_status} not found"
            assert found[0]["status_ar"] == arabic_label, f"Arabic label for {eng_status} should be {arabic_label}"

            # Clean up for next iteration
            test_db.delete(enrollment)
            test_db.commit()

    def test_403_for_admin(self, client, auth_headers_admin, admin_user, test_db):
        """Admin should get 403"""
        response = client.get("/api/parent/enrollments", headers=auth_headers_admin)
        assert response.status_code == 403

    def test_403_for_supervisor(self, client, auth_headers_supervisor, supervisor_user, test_db):
        """Supervisor should get 403"""
        response = client.get("/api/parent/enrollments", headers=auth_headers_supervisor)
        assert response.status_code == 403

    def test_unauthenticated_returns_401(self, client, test_db):
        """Should get 401 without auth"""
        response = client.get("/api/parent/enrollments")
        assert response.status_code == 401

    def test_isolation_parents_cannot_see_other_parents_enrollments(self, client, test_db):
        """Parent A should NOT see Parent B's enrollments"""
        # Create parent A
        user_a = models.User(
            username="parenta@test.com", email="parenta@test.com",
            hashed_password=get_password_hash("Parent123!"),
            role=models.UserRole.PARENT, status=models.UserStatus.ACTIVE
        )
        test_db.add(user_a)
        test_db.commit()
        test_db.refresh(user_a)
        profile_a = models.ParentProfile(
            user_id=user_a.id, first_name="A", last_name="A",
            phone_number="+962790000010", gender=models.Gender.MALE,
            nationality="Jordanian", national_id="AAAA",
            home_governorate="Amman", home_district="Amman",
            home_area="Abdoun", home_address_line="St 1"
        )
        test_db.add(profile_a)
        test_db.commit()
        test_db.refresh(profile_a)

        # Create parent B with child and enrollment
        user_b = models.User(
            username="parentb@test.com", email="parentb@test.com",
            hashed_password=get_password_hash("Parent123!"),
            role=models.UserRole.PARENT, status=models.UserStatus.ACTIVE
        )
        test_db.add(user_b)
        test_db.commit()
        test_db.refresh(user_b)
        profile_b = models.ParentProfile(
            user_id=user_b.id, first_name="B", last_name="B",
            phone_number="+962790000011", gender=models.Gender.FEMALE,
            nationality="Jordanian", national_id="BBBB",
            home_governorate="Amman", home_district="Amman",
            home_area="Abdoun", home_address_line="St 2"
        )
        test_db.add(profile_b)
        test_db.commit()
        test_db.refresh(profile_b)

        child_b = models.Child(
            parent_id=profile_b.id, first_name="ChildB", last_name="B",
            gender=models.Gender.MALE, date_of_birth=date.today() - timedelta(days=365 * 3),
            father_name="B", mother_first_name="B", mother_last_name="B",
            mother_nationality="Jordanian", mother_national_id="MMMM"
        )
        test_db.add(child_b)
        test_db.commit()
        test_db.refresh(child_b)

        kg = models.Kindergarten(
            name_ar="روضة خاصة", name_en="Private KG",
            governorate="Amman", district="Amman", area="X",
            address_line="St", contact_phone="+962790000012",
            status=models.KindergartenStatus.ACTIVE
        )
        test_db.add(kg)
        test_db.commit()
        test_db.refresh(kg)

        enroll_b = models.EnrollmentApplication(
            child_id=child_b.id, kindergarten_id=kg.id,
            status=models.EnrollmentStatus.ACCEPTED
        )
        test_db.add(enroll_b)
        test_db.commit()

        # Login as parent A
        resp = client.post("/token", data={"username": "parenta@test.com", "password": "Parent123!"})
        token_a = resp.json()["access_token"]

        # Parent A should see 0 enrollments
        response = client.get("/api/parent/enrollments", headers={
            "Authorization": f"Bearer {token_a}"
        })
        assert response.status_code == 200
        assert response.json()["total"] == 0

        # Login as parent B
        resp = client.post("/token", data={"username": "parentb@test.com", "password": "Parent123!"})
        token_b = resp.json()["access_token"]

        # Parent B should see 1 enrollment
        response = client.get("/api/parent/enrollments", headers={
            "Authorization": f"Bearer {token_b}"
        })
        assert response.status_code == 200
        assert response.json()["total"] == 1
        assert response.json()["enrollments"][0]["child_name"] == "ChildB B"


# ============================================================================
# Frontend pages: /parent/profile, /parent/children, /parent/enrollments
# ============================================================================


class TestParentFrontendPages:
    """Tests for parent-specific frontend pages"""

    def test_parent_profile_page_renders(self, client, parent_token, parent_user, test_db):
        """Parent should see their profile page"""
        client.cookies.set("kinjo_token", parent_token)
        response = client.get("/parent/profile")
        assert response.status_code == 200
        html = response.text
        assert "ملفي الشخصي" in html or "profile" in html.lower()

    def test_parent_children_page_renders(self, client, parent_token, parent_user, test_db):
        """Parent should see children list page"""
        client.cookies.set("kinjo_token", parent_token)
        response = client.get("/parent/children")
        assert response.status_code == 200
        html = response.text
        assert "أطفالي" in html or "children" in html.lower()

    def test_parent_enrollments_page_renders(self, client, parent_token, parent_user, test_db):
        """Parent should see enrollments page"""
        client.cookies.set("kinjo_token", parent_token)
        response = client.get("/parent/enrollments")
        assert response.status_code == 200
        html = response.text
        assert "طلبات التسجيل" in html or "enrollment" in html.lower()

    def test_parent_dashboard_renders_for_parent(self, client, parent_token, parent_user, test_db):
        """Parent dashboard should render for parent"""
        client.cookies.set("kinjo_token", parent_token)
        response = client.get("/parent/dashboard")
        assert response.status_code == 200

    def test_parent_profile_page_has_edit_form(self, client, parent_token, parent_user, test_db):
        """Profile page should have edit functionality"""
        client.cookies.set("kinjo_token", parent_token)
        response = client.get("/parent/profile")
        html = response.text
        # Check for edit-related elements
        assert "editBtn" in html or "تعديل" in html

    def test_parent_children_page_has_enroll_cta(self, client, parent_token, parent_user, test_db):
        """Children page should have enroll CTA"""
        client.cookies.set("kinjo_token", parent_token)
        response = client.get("/parent/children")
        html = response.text
        assert "/enroll" in html or "تسجيل طفل" in html

    def test_parent_enrollments_page_has_status_cards(self, client, parent_token, parent_user, test_db):
        """Enrollments page should have status summary"""
        client.cookies.set("kinjo_token", parent_token)
        response = client.get("/parent/enrollments")
        html = response.text
        assert "totalCount" in html or "إجمالي" in html


# ============================================================================
# Role gates: non-parents redirected from /parent/* pages
# ============================================================================


class TestParentRouteRoleGates:
    """Non-parent roles should be redirected away from parent-specific routes"""

    def test_admin_redirected_from_parent_profile(self, client, admin_token, admin_user, test_db):
        """Admin accessing /parent/profile should redirect to /profile"""
        client.cookies.set("kinjo_token", admin_token)
        response = client.get("/parent/profile", follow_redirects=False)
        assert response.status_code == 307
        assert "/profile" in response.headers["location"]

    def test_manager_redirected_from_parent_profile(self, client, manager_token, manager_user, test_db):
        """Manager accessing /parent/profile should redirect to /profile"""
        client.cookies.set("kinjo_token", manager_token)
        response = client.get("/parent/profile", follow_redirects=False)
        assert response.status_code == 307
        assert "/profile" in response.headers["location"]

    def test_admin_redirected_from_parent_children(self, client, admin_token, admin_user, test_db):
        """Admin accessing /parent/children should redirect to /dashboard"""
        client.cookies.set("kinjo_token", admin_token)
        response = client.get("/parent/children", follow_redirects=False)
        assert response.status_code == 307
        assert "/dashboard" in response.headers["location"]

    def test_manager_redirected_from_parent_enrollments(self, client, manager_token, manager_user, test_db):
        """Manager accessing /parent/enrollments should redirect to /enrollments"""
        client.cookies.set("kinjo_token", manager_token)
        response = client.get("/parent/enrollments", follow_redirects=False)
        assert response.status_code == 307
        assert "/enrollments" in response.headers["location"]

    def test_admin_redirected_from_parent_dashboard(self, client, admin_token, admin_user, test_db):
        """Admin accessing /parent/dashboard should redirect to /dashboard"""
        client.cookies.set("kinjo_token", admin_token)
        response = client.get("/parent/dashboard", follow_redirects=False)
        assert response.status_code == 307
        assert "/dashboard" in response.headers["location"]


# ============================================================================
# Redirects: generic routes redirect parents to parent-specific pages
# ============================================================================


class TestParentRedirects:
    """Generic routes should redirect parents to parent-specific pages"""

    def test_profile_redirects_parent(self, client, parent_token, parent_user, test_db):
        """GET /profile should redirect parent to /parent/profile"""
        client.cookies.set("kinjo_token", parent_token)
        response = client.get("/profile", follow_redirects=False)
        assert response.status_code == 307
        assert "/parent/profile" in response.headers["location"]

    def test_enrollments_redirects_parent(self, client, parent_token, parent_user, test_db):
        """GET /enrollments should redirect parent to /parent/enrollments"""
        client.cookies.set("kinjo_token", parent_token)
        response = client.get("/enrollments", follow_redirects=False)
        assert response.status_code == 307
        assert "/parent/enrollments" in response.headers["location"]

    def test_children_redirects_parent(self, client, parent_token, parent_user, test_db):
        """GET /children should redirect parent to /parent/children"""
        client.cookies.set("kinjo_token", parent_token)
        response = client.get("/children", follow_redirects=False)
        assert response.status_code == 307
        assert "/parent/children" in response.headers["location"]

    def test_profile_redirects_admin_to_admin_profile(self, client, admin_token, admin_user, test_db):
        """GET /profile should redirect admin to their dedicated /admin/profile page"""
        client.cookies.set("kinjo_token", admin_token)
        response = client.get("/profile", follow_redirects=False)
        # Admin gets redirected to dedicated admin profile page (not the generic user settings page)
        assert response.status_code == 307
        assert "/admin/profile" in response.headers.get("location", "")

    def test_enrollments_does_not_redirect_manager(self, client, manager_token, manager_user, test_db):
        """GET /enrollments should NOT redirect manager"""
        client.cookies.set("kinjo_token", manager_token)
        response = client.get("/enrollments", follow_redirects=False)
        assert response.status_code == 200


# ============================================================================
# Enrollment view access control
# ============================================================================


class TestParentEnrollmentViewAccess:
    """Parent should only see their own children's enrollment details"""

    def test_parent_can_view_own_enrollment(self, client, parent_token, parent_user,
                                             sample_child, parent_enrollment, test_db):
        """Parent should see their own child's enrollment detail"""
        client.cookies.set("kinjo_token", parent_token)
        response = client.get(f"/enrollments/{parent_enrollment.id}")
        assert response.status_code == 200

    def test_parent_cannot_view_other_enrollment(self, client, parent_token, parent_user, test_db):
        """Parent should NOT see another parent's enrollment"""
        # Create another parent with child and enrollment
        user2 = models.User(
            username="other@test.com", email="other@test.com",
            hashed_password=get_password_hash("Parent123!"),
            role=models.UserRole.PARENT, status=models.UserStatus.ACTIVE
        )
        test_db.add(user2)
        test_db.commit()
        test_db.refresh(user2)

        profile2 = models.ParentProfile(
            user_id=user2.id, first_name="Other", last_name="Parent",
            phone_number="+962790009999", gender=models.Gender.FEMALE,
            nationality="Jordanian", national_id="XXXX",
            home_governorate="Amman", home_district="Amman",
            home_area="Abdoun", home_address_line="St 1"
        )
        test_db.add(profile2)
        test_db.commit()
        test_db.refresh(profile2)

        child2 = models.Child(
            parent_id=profile2.id, first_name="OtherChild", last_name="P",
            gender=models.Gender.MALE, date_of_birth=date.today() - timedelta(days=365 * 3),
            father_name="O", mother_first_name="M", mother_last_name="P",
            mother_nationality="Jordanian", mother_national_id="YYYY"
        )
        test_db.add(child2)
        test_db.commit()
        test_db.refresh(child2)

        kg = models.Kindergarten(
            name_ar="روضة أخرى", name_en="Other KG",
            governorate="Amman", district="Amman", area="Z",
            address_line="St", contact_phone="+962790009998",
            status=models.KindergartenStatus.ACTIVE
        )
        test_db.add(kg)
        test_db.commit()
        test_db.refresh(kg)

        other_enrollment = models.EnrollmentApplication(
            child_id=child2.id, kindergarten_id=kg.id,
            status=models.EnrollmentStatus.ACCEPTED
        )
        test_db.add(other_enrollment)
        test_db.commit()
        test_db.refresh(other_enrollment)

        # Parent 1 tries to view Parent 2's enrollment
        client.cookies.set("kinjo_token", parent_token)
        response = client.get(f"/enrollments/{other_enrollment.id}")
        assert response.status_code == 403


# ============================================================================
# Children isolation
# ============================================================================


class TestParentChildrenIsolation:
    """Parent should only see their own children, not other parents' children"""

    def test_parent_cannot_see_other_children(self, client, test_db):
        """Parent A children list should NOT include Parent B's children"""
        # Create Parent A
        user_a = models.User(
            username="pa@test.com", email="pa@test.com",
            hashed_password=get_password_hash("Parent123!"),
            role=models.UserRole.PARENT, status=models.UserStatus.ACTIVE
        )
        test_db.add(user_a)
        test_db.commit()
        test_db.refresh(user_a)
        profile_a = models.ParentProfile(
            user_id=user_a.id, first_name="PA", last_name="A",
            phone_number="+962791111111", gender=models.Gender.MALE,
            nationality="Jordanian", national_id="PA1",
            home_governorate="Amman", home_district="Amman",
            home_area="Abdoun", home_address_line="St 1"
        )
        test_db.add(profile_a)
        test_db.commit()
        test_db.refresh(profile_a)

        child_a = models.Child(
            parent_id=profile_a.id, first_name="ChildA", last_name="A",
            gender=models.Gender.MALE, date_of_birth=date.today() - timedelta(days=365 * 3),
            father_name="PA", mother_first_name="MA", mother_last_name="A",
            mother_nationality="Jordanian", mother_national_id="MA1"
        )
        test_db.add(child_a)
        test_db.commit()

        # Create Parent B
        user_b = models.User(
            username="pb@test.com", email="pb@test.com",
            hashed_password=get_password_hash("Parent123!"),
            role=models.UserRole.PARENT, status=models.UserStatus.ACTIVE
        )
        test_db.add(user_b)
        test_db.commit()
        test_db.refresh(user_b)
        profile_b = models.ParentProfile(
            user_id=user_b.id, first_name="PB", last_name="B",
            phone_number="+962792222222", gender=models.Gender.FEMALE,
            nationality="Jordanian", national_id="PB1",
            home_governorate="Amman", home_district="Amman",
            home_area="Khalda", home_address_line="St 2"
        )
        test_db.add(profile_b)
        test_db.commit()
        test_db.refresh(profile_b)

        child_b = models.Child(
            parent_id=profile_b.id, first_name="ChildB", last_name="B",
            gender=models.Gender.FEMALE, date_of_birth=date.today() - timedelta(days=365 * 4),
            father_name="PB", mother_first_name="MB", mother_last_name="B",
            mother_nationality="Jordanian", mother_national_id="MB1"
        )
        test_db.add(child_b)
        test_db.commit()

        # Login as Parent A
        resp = client.post("/token", data={"username": "pa@test.com", "password": "Parent123!"})
        token_a = resp.json()["access_token"]

        response = client.get("/api/parent/children", headers={
            "Authorization": f"Bearer {token_a}"
        })
        data = response.json()
        assert data["total"] == 1
        assert data["children"][0]["first_name"] == "ChildA"

        # Login as Parent B
        resp = client.post("/token", data={"username": "pb@test.com", "password": "Parent123!"})
        token_b = resp.json()["access_token"]

        response = client.get("/api/parent/children", headers={
            "Authorization": f"Bearer {token_b}"
        })
        data = response.json()
        assert data["total"] == 1
        assert data["children"][0]["first_name"] == "ChildB"


# ============================================================================
# Profile isolation
# ============================================================================


class TestParentProfileIsolation:
    """Each parent should only see their own profile"""

    def test_parent_gets_own_profile_not_others(self, client, test_db):
        """Two parents should each see only their own profile"""
        # Create Parent A
        user_a = models.User(
            username="profilea@test.com", email="profilea@test.com",
            hashed_password=get_password_hash("Parent123!"),
            role=models.UserRole.PARENT, status=models.UserStatus.ACTIVE
        )
        test_db.add(user_a)
        test_db.commit()
        test_db.refresh(user_a)
        profile_a = models.ParentProfile(
            user_id=user_a.id, first_name="Khalid", last_name="Mansour",
            phone_number="+962793333333", gender=models.Gender.MALE,
            nationality="Jordanian", national_id="KM01",
            home_governorate="Amman", home_district="Amman",
            home_area="Abdoun", home_address_line="St 1"
        )
        test_db.add(profile_a)
        test_db.commit()

        # Create Parent B
        user_b = models.User(
            username="profileb@test.com", email="profileb@test.com",
            hashed_password=get_password_hash("Parent123!"),
            role=models.UserRole.PARENT, status=models.UserStatus.ACTIVE
        )
        test_db.add(user_b)
        test_db.commit()
        test_db.refresh(user_b)
        profile_b = models.ParentProfile(
            user_id=user_b.id, first_name="Nour", last_name="Haddad",
            phone_number="+962794444444", gender=models.Gender.FEMALE,
            nationality="Jordanian", national_id="NH01",
            home_governorate="Amman", home_district="Amman",
            home_area="Shmeisani", home_address_line="St 2"
        )
        test_db.add(profile_b)
        test_db.commit()

        # Login as Parent A
        resp = client.post("/token", data={"username": "profilea@test.com", "password": "Parent123!"})
        token_a = resp.json()["access_token"]
        response = client.get("/api/parent/profile", headers={
            "Authorization": f"Bearer {token_a}"
        })
        assert response.status_code == 200
        assert response.json()["first_name"] == "Khalid"
        assert response.json()["last_name"] == "Mansour"

        # Login as Parent B
        resp = client.post("/token", data={"username": "profileb@test.com", "password": "Parent123!"})
        token_b = resp.json()["access_token"]
        response = client.get("/api/parent/profile", headers={
            "Authorization": f"Bearer {token_b}"
        })
        assert response.status_code == 200
        assert response.json()["first_name"] == "Nour"
        assert response.json()["last_name"] == "Haddad"


# ============================================================================
# Sidebar
# ============================================================================


class TestParentSidebar:
    """Parent sidebar should have all parent navigation links"""

    def test_sidebar_has_parent_links(self, client, parent_token, parent_user, test_db):
        """Dashboard should include all parent navigation links in sidebar"""
        client.cookies.set("kinjo_token", parent_token)
        response = client.get("/parent/dashboard")
        assert response.status_code == 200
        html = response.text
        assert "/parent/profile" in html
        assert "/parent/children" in html
        assert "/parent/enrollments" in html
        assert "/my-reports" in html
        assert "/enroll" in html

    def test_sidebar_links_have_arabic_labels(self, client, parent_token, parent_user, test_db):
        """Sidebar links should have Arabic labels"""
        client.cookies.set("kinjo_token", parent_token)
        response = client.get("/parent/dashboard")
        html = response.text
        assert "ملفي الشخصي" in html
        assert "أطفالي" in html
        assert "طلبات التسجيل" in html


# ============================================================================
# Dashboard quick actions
# ============================================================================


class TestParentDashboardQuickActions:
    """Parent dashboard should have correct quick action links"""

    def test_dashboard_links_to_parent_profile(self, client, parent_token, parent_user, test_db):
        """Dashboard should link to /parent/profile, not /profile"""
        client.cookies.set("kinjo_token", parent_token)
        response = client.get("/parent/dashboard")
        html = response.text
        # Should have parent profile link, not generic settings
        assert "/parent/profile" in html
        assert "ملفي الشخصي" in html

# ============================================================================
# Parent reports page and API visibility
# ============================================================================


class TestParentMyReportsPage:
    """Validate /my-reports data quality and access controls."""

    def test_parent_reports_shows_only_visible_own_reports(
        self,
        client,
        parent_token,
        parent_user,
        sample_child,
        sample_kindergarten,
        supervisor_user,
        test_db,
    ):
        report_date = date.today()

        child_visible = models.Child(
            parent_id=parent_user.parent_profile.id,
            first_name="Sami",
            last_name="Visible",
            gender=models.Gender.MALE,
            date_of_birth=date.today() - timedelta(days=365 * 3),
            father_name="Ahmad Al-Rashid",
            mother_first_name="Fatima",
            mother_last_name="Hassan",
            mother_nationality="Jordanian",
            mother_national_id="1000000002",
        )
        child_hidden = models.Child(
            parent_id=parent_user.parent_profile.id,
            first_name="Dina",
            last_name="Hidden",
            gender=models.Gender.FEMALE,
            date_of_birth=date.today() - timedelta(days=365 * 3),
            father_name="Ahmad Al-Rashid",
            mother_first_name="Fatima",
            mother_last_name="Hassan",
            mother_nationality="Jordanian",
            mother_national_id="1000000003",
        )
        test_db.add_all([child_visible, child_hidden])
        test_db.commit()
        test_db.refresh(child_visible)
        test_db.refresh(child_hidden)

        other_parent_user = models.User(
            username="other.parent.reports@test.com",
            email="other.parent.reports@test.com",
            hashed_password=get_password_hash("Parent123!"),
            role=models.UserRole.PARENT,
            status=models.UserStatus.ACTIVE,
        )
        test_db.add(other_parent_user)
        test_db.commit()
        test_db.refresh(other_parent_user)

        other_profile = models.ParentProfile(
            user_id=other_parent_user.id,
            first_name="Other",
            last_name="Parent",
            phone_number="+962790006666",
            gender=models.Gender.FEMALE,
            nationality="Jordanian",
            national_id="2000000001",
            home_governorate="Amman",
            home_district="Amman",
            home_area="Abdoun",
            home_address_line="Street 9",
        )
        test_db.add(other_profile)
        test_db.commit()
        test_db.refresh(other_profile)

        other_child = models.Child(
            parent_id=other_profile.id,
            first_name="Nora",
            last_name="Other",
            gender=models.Gender.FEMALE,
            date_of_birth=date.today() - timedelta(days=365 * 3),
            father_name="Other Father",
            mother_first_name="Other Mother",
            mother_last_name="Other Last",
            mother_nationality="Jordanian",
            mother_national_id="2000000002",
        )
        test_db.add(other_child)
        test_db.commit()
        test_db.refresh(other_child)

        test_db.add_all(
            [
                models.DailyReport(
                    child_id=sample_child.id,
                    kindergarten_id=sample_kindergarten.id,
                    date=report_date,
                    status=models.DailyReportStatus.APPROVED,
                    submitted_by=supervisor_user.id,
                    arrival_time="08:00",
                    leave_time="14:00",
                    notes="VISIBLE_APPROVED_NOTE",
                ),
                models.DailyReport(
                    child_id=child_visible.id,
                    kindergarten_id=sample_kindergarten.id,
                    date=report_date,
                    status=models.DailyReportStatus.SENT_TO_PARENT,
                    submitted_by=supervisor_user.id,
                    arrival_time="08:10",
                    leave_time="14:10",
                    notes="VISIBLE_SENT_NOTE",
                ),
                models.DailyReport(
                    child_id=child_hidden.id,
                    kindergarten_id=sample_kindergarten.id,
                    date=report_date,
                    status=models.DailyReportStatus.DRAFT,
                    submitted_by=supervisor_user.id,
                    arrival_time="08:20",
                    leave_time="14:20",
                    notes="HIDDEN_DRAFT_NOTE",
                ),
                models.DailyReport(
                    child_id=other_child.id,
                    kindergarten_id=sample_kindergarten.id,
                    date=report_date,
                    status=models.DailyReportStatus.APPROVED,
                    submitted_by=supervisor_user.id,
                    arrival_time="08:30",
                    leave_time="14:30",
                    notes="HIDDEN_OTHER_PARENT_NOTE",
                ),
            ]
        )
        test_db.commit()

        client.cookies.set("kinjo_token", parent_token)
        response = client.get(f"/my-reports?date={report_date.isoformat()}")
        assert response.status_code == 200

        html = response.text
        assert "VISIBLE_APPROVED_NOTE" in html
        assert "VISIBLE_SENT_NOTE" in html
        assert "HIDDEN_DRAFT_NOTE" not in html
        assert "HIDDEN_OTHER_PARENT_NOTE" not in html

    def test_parent_reports_filters_by_child(
        self,
        client,
        parent_token,
        parent_user,
        sample_child,
        sample_kindergarten,
        supervisor_user,
        test_db,
    ):
        report_date = date.today()
        another_child = models.Child(
            parent_id=parent_user.parent_profile.id,
            first_name="Ali",
            last_name="Filter",
            gender=models.Gender.MALE,
            date_of_birth=date.today() - timedelta(days=365 * 3),
            father_name="Ahmad Al-Rashid",
            mother_first_name="Fatima",
            mother_last_name="Hassan",
            mother_nationality="Jordanian",
            mother_national_id="1000000004",
        )
        test_db.add(another_child)
        test_db.commit()
        test_db.refresh(another_child)

        test_db.add_all(
            [
                models.DailyReport(
                    child_id=sample_child.id,
                    kindergarten_id=sample_kindergarten.id,
                    date=report_date,
                    status=models.DailyReportStatus.APPROVED,
                    submitted_by=supervisor_user.id,
                    arrival_time="08:00",
                    leave_time="14:00",
                    notes="FILTER_IN_NOTE",
                ),
                models.DailyReport(
                    child_id=another_child.id,
                    kindergarten_id=sample_kindergarten.id,
                    date=report_date,
                    status=models.DailyReportStatus.SENT_TO_PARENT,
                    submitted_by=supervisor_user.id,
                    arrival_time="08:05",
                    leave_time="14:05",
                    notes="FILTER_OUT_NOTE",
                ),
            ]
        )
        test_db.commit()

        client.cookies.set("kinjo_token", parent_token)
        response = client.get(f"/my-reports?date={report_date.isoformat()}&child_id={sample_child.id}")
        assert response.status_code == 200
        html = response.text
        assert "FILTER_IN_NOTE" in html
        assert "FILTER_OUT_NOTE" not in html

    def test_non_parent_redirected_from_my_reports(self, client, admin_token, admin_user, test_db):
        client.cookies.set("kinjo_token", admin_token)
        response = client.get("/my-reports", follow_redirects=False)
        assert response.status_code == 307
        assert "/dashboard" in response.headers["location"]

    def test_parent_reports_rejects_other_child_filter(
        self,
        client,
        parent_token,
        test_db,
    ):
        other_parent = models.User(
            username="forbidden.child.filter@test.com",
            email="forbidden.child.filter@test.com",
            hashed_password=get_password_hash("Parent123!"),
            role=models.UserRole.PARENT,
            status=models.UserStatus.ACTIVE,
        )
        test_db.add(other_parent)
        test_db.commit()
        test_db.refresh(other_parent)

        other_profile = models.ParentProfile(
            user_id=other_parent.id,
            first_name="Other",
            last_name="Parent",
            phone_number="+962790001111",
            gender=models.Gender.FEMALE,
            nationality="Jordanian",
            national_id="3000000001",
            home_governorate="Amman",
            home_district="Amman",
            home_area="Abdoun",
            home_address_line="Street 99",
        )
        test_db.add(other_profile)
        test_db.commit()
        test_db.refresh(other_profile)

        other_child = models.Child(
            parent_id=other_profile.id,
            first_name="Child",
            last_name="Foreign",
            gender=models.Gender.FEMALE,
            date_of_birth=date.today() - timedelta(days=365 * 3),
            father_name="Foreign Father",
            mother_first_name="Foreign Mother",
            mother_last_name="Foreign Last",
            mother_nationality="Jordanian",
            mother_national_id="3000000002",
        )
        test_db.add(other_child)
        test_db.commit()

        client.cookies.set("kinjo_token", parent_token)
        response = client.get(f"/my-reports?child_id={other_child.id}")
        assert response.status_code == 403


class TestParentDailyReportsVisibility:
    """Ensure parent-facing report endpoints include sent reports."""

    def test_daily_reports_child_endpoint_includes_sent_to_parent(
        self,
        client,
        auth_headers_parent,
        sample_child,
        sample_kindergarten,
        supervisor_user,
        test_db,
    ):
        test_db.add(
            models.DailyReport(
                child_id=sample_child.id,
                kindergarten_id=sample_kindergarten.id,
                date=date.today(),
                status=models.DailyReportStatus.SENT_TO_PARENT,
                submitted_by=supervisor_user.id,
                arrival_time="08:00",
                leave_time="14:00",
                notes="SENT_TO_PARENT_VISIBLE",
            )
        )
        test_db.commit()

        response = client.get(f"/api/daily-reports/child/{sample_child.id}", headers=auth_headers_parent)
        assert response.status_code == 200
        statuses = [row["status"] for row in response.json()["reports"]]
        assert "SENT_TO_PARENT" in statuses

    def test_parent_dashboard_latest_report_accepts_sent_to_parent(
        self,
        client,
        auth_headers_parent,
        sample_child,
        sample_kindergarten,
        supervisor_user,
        test_db,
    ):
        today = date.today()
        test_db.add(
            models.DailyReport(
                child_id=sample_child.id,
                kindergarten_id=sample_kindergarten.id,
                date=today,
                status=models.DailyReportStatus.SENT_TO_PARENT,
                submitted_by=supervisor_user.id,
                arrival_time="08:00",
                leave_time="14:00",
                notes="DASHBOARD_LATEST_SENT",
            )
        )
        test_db.commit()

        response = client.get("/api/parent/dashboard", headers=auth_headers_parent)
        assert response.status_code == 200
        data = response.json()

        child_row = next((child for child in data["children"] if child["id"] == sample_child.id), None)
        assert child_row is not None
        assert child_row["latest_report_date"] == today.isoformat()

    def test_parent_dashboard_handles_absent_attendance_without_checkin(
        self,
        client,
        auth_headers_parent,
        sample_child,
        sample_class,
        supervisor_user,
        test_db,
    ):
        test_db.add(
            models.AttendanceLog(
                child_id=sample_child.id,
                class_id=sample_class.id,
                date=date.today(),
                status=models.AttendanceStatus.ABSENT,
                recorded_by=supervisor_user.id,
                check_in_at=None,
                check_out_at=None,
            )
        )
        test_db.commit()

        response = client.get("/api/parent/dashboard", headers=auth_headers_parent)
        assert response.status_code == 200
        data = response.json()
        child_row = next((child for child in data["children"] if child["id"] == sample_child.id), None)
        assert child_row is not None
        assert child_row["attendance_today"] is not None
        assert child_row["attendance_today"]["checked_in"] is None

class TestParentDashboardDateContext:
    """Parent dashboard should use server-side date for daily badges."""

    def test_parent_dashboard_injects_server_today(self, client, parent_token, parent_user, test_db):
        client.cookies.set("kinjo_token", parent_token)
        response = client.get("/parent/dashboard")
        assert response.status_code == 200
        html = response.text
        assert "const SERVER_TODAY" in html
        assert date.today().isoformat() in html

    def test_parent_dashboard_uses_partial_report_fetch_strategy(self, client, parent_token, parent_user, test_db):
        client.cookies.set("kinjo_token", parent_token)
        response = client.get("/parent/dashboard")
        assert response.status_code == 200
        html = response.text
        assert "Promise.allSettled" in html
