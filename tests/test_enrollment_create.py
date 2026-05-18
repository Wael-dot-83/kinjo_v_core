"""
Tests for the enrollment creation flow:
- Cities endpoint (GET /api/governorates/{gov}/cities)
- Kindergarten filtering with city param
- Parent access to kindergarten details
- Duplicate enrollment prevention
- Frontend page rendering
"""
import pytest
from datetime import date, timedelta
import models
from auth import get_password_hash
from sqlalchemy.orm import sessionmaker
from sqlalchemy.exc import IntegrityError


class TestCitiesEndpoint:
    """Test GET /api/governorates/{gov}/cities"""

    def test_cities_by_governorate_returns_cities(self, client, admin_token, test_db, sample_kindergarten):
        """Should return cities for a given governorate"""
        headers = {"Authorization": f"Bearer {admin_token}"}
        # The sample_kindergarten has governorate="Amman" and city="Amman"
        response = client.get("/api/governorates/Amman/cities", headers=headers)
        assert response.status_code == 200
        data = response.json()
        assert "cities" in data
        assert isinstance(data["cities"], list)

    def test_cities_by_arabic_governorate(self, client, admin_token, test_db):
        """Should work with Arabic governorate names"""
        headers = {"Authorization": f"Bearer {admin_token}"}
        # Create a KG in عمان
        kg = models.Kindergarten(
            name_ar="روضة اختبار", name_en="Test KG",
            governorate="عمان", city="الجبيهة", area="منطقة",
            address_line="عنوان", contact_phone="+962791110001",
            status=models.KindergartenStatus.ACTIVE
        )
        test_db.add(kg)
        test_db.commit()

        response = client.get("/api/governorates/عمان/cities", headers=headers)
        assert response.status_code == 200
        data = response.json()
        assert "الجبيهة" in data["cities"]

    def test_cities_parent_access(self, client, parent_token, test_db, sample_kindergarten):
        """Parents should be able to access cities endpoint"""
        headers = {"Authorization": f"Bearer {parent_token}"}
        response = client.get("/api/governorates/Amman/cities", headers=headers)
        assert response.status_code == 200

    def test_cities_unknown_governorate(self, client, admin_token, test_db):
        """Should return empty list for unknown governorate"""
        headers = {"Authorization": f"Bearer {admin_token}"}
        response = client.get("/api/governorates/UnknownGov/cities", headers=headers)
        assert response.status_code == 200
        data = response.json()
        assert isinstance(data["cities"], list)


class TestKindergartenFilteringWithCity:
    """Test filtering kindergartens by city"""

    def test_filter_by_city(self, client, admin_token, test_db):
        """Should filter kindergartens by city"""
        headers = {"Authorization": f"Bearer {admin_token}"}
        # Create KGs in different cities
        for i, city in enumerate(["عمان", "الجبيهة", "القويسمة"]):
            kg = models.Kindergarten(
                name_ar=f"روضة {city}", name_en=f"KG {city}",
                governorate="عمان", city=city, area="test",
                address_line="test", contact_phone=f"+96279111000{i}",
                status=models.KindergartenStatus.ACTIVE
            )
            test_db.add(kg)
        test_db.commit()

        # Filter by city
        response = client.get("/api/kindergartens?city=الجبيهة&status=ACTIVE", headers=headers)
        assert response.status_code == 200
        data = response.json()
        assert data["total"] >= 1
        for kg in data["kindergartens"]:
            assert "الجبيهة" in kg["city"]

    def test_filter_by_gov_and_city(self, client, admin_token, test_db):
        """Should filter by both governorate and city"""
        headers = {"Authorization": f"Bearer {admin_token}"}
        kg = models.Kindergarten(
            name_ar="روضة إربد", name_en="Irbid KG",
            governorate="إربد", city="الحصن", area="test",
            address_line="test", contact_phone="+962791112222",
            status=models.KindergartenStatus.ACTIVE
        )
        test_db.add(kg)
        test_db.commit()

        response = client.get("/api/kindergartens?governorate=إربد&city=الحصن&status=ACTIVE", headers=headers)
        assert response.status_code == 200
        data = response.json()
        assert data["total"] >= 1

    def test_parent_filter_by_city(self, client, parent_token, test_db):
        """Parents should be able to filter by city"""
        headers = {"Authorization": f"Bearer {parent_token}"}
        kg = models.Kindergarten(
            name_ar="روضة الزرقاء", name_en="Zarqa KG",
            governorate="الزرقاء", city="الزرقاء", area="test",
            address_line="test", contact_phone="+962791113333",
            status=models.KindergartenStatus.ACTIVE
        )
        test_db.add(kg)
        test_db.commit()

        response = client.get("/api/kindergartens?city=الزرقاء&status=ACTIVE", headers=headers)
        assert response.status_code == 200


class TestParentKindergartenDetails:
    """Test parent access to GET /api/kindergartens/{id}"""

    def test_parent_can_view_active_kg(self, client, parent_token, test_db, sample_kindergarten):
        """Parent should be able to view details of an ACTIVE kindergarten"""
        headers = {"Authorization": f"Bearer {parent_token}"}
        response = client.get(f"/api/kindergartens/{sample_kindergarten.id}", headers=headers)
        assert response.status_code == 200
        data = response.json()
        assert data["name_ar"] == sample_kindergarten.name_ar

    def test_parent_cannot_view_inactive_kg(self, client, parent_token, test_db):
        """Parent should NOT be able to view INACTIVE kindergartens"""
        headers = {"Authorization": f"Bearer {parent_token}"}
        kg = models.Kindergarten(
            name_ar="روضة غير نشطة", name_en="Inactive KG",
            governorate="عمان", city="عمان", area="test",
            address_line="test", contact_phone="+962791114444",
            status=models.KindergartenStatus.INACTIVE
        )
        test_db.add(kg)
        test_db.commit()

        response = client.get(f"/api/kindergartens/{kg.id}", headers=headers)
        assert response.status_code == 404

    def test_parent_cannot_view_draft_kg(self, client, parent_token, test_db):
        """Parent should NOT be able to view DRAFT kindergartens"""
        headers = {"Authorization": f"Bearer {parent_token}"}
        kg = models.Kindergarten(
            name_ar="روضة مسودة", name_en="Draft KG",
            governorate="عمان", city="عمان", area="test",
            address_line="test", contact_phone="+962791115555",
            status=models.KindergartenStatus.DRAFT
        )
        test_db.add(kg)
        test_db.commit()

        response = client.get(f"/api/kindergartens/{kg.id}", headers=headers)
        assert response.status_code == 404

    def test_supervisor_still_blocked(self, client, supervisor_token, test_db, sample_kindergarten):
        """Supervisor should still be blocked from viewing KG details"""
        headers = {"Authorization": f"Bearer {supervisor_token}"}
        response = client.get(f"/api/kindergartens/{sample_kindergarten.id}", headers=headers)
        assert response.status_code == 403


class TestDuplicateEnrollmentPrevention:
    """Test that duplicate enrollments are prevented"""

    def test_duplicate_enrollment_blocked(self, client, parent_token, test_db, sample_kindergarten, parent_user):
        """Should block duplicate enrollment for same child + same KG"""
        headers = {"Authorization": f"Bearer {parent_token}"}
        dob = (date.today() - timedelta(days=365 * 3)).isoformat()

        enrollment_data = {
            "first_name": "Layla",
            "last_name": parent_user.parent_profile.last_name,
            "gender": "FEMALE",
            "date_of_birth": dob,
            "father_name": "Ahmad Al-Rashid",
            "mother_first_name": "Fatima",
            "mother_last_name": "Hassan",
            "mother_nationality": "Jordanian",
            "mother_national_id": "9999888877",
            "national_id": "1122334455",
            "kindergarten_id": sample_kindergarten.id
        }

        # First enrollment should succeed
        response1 = client.post("/api/enrollment/apply", json=enrollment_data, headers=headers)
        assert response1.status_code == 201, f"First enrollment failed: {response1.json()}"

        # Second enrollment with same child data + same KG should fail
        response2 = client.post("/api/enrollment/apply", json=enrollment_data, headers=headers)
        assert response2.status_code == 400
        detail = response2.json()["detail"]
        assert (
            "duplicate" in detail.lower()
            or "enrollment" in detail.lower()
            or "تسجيل" in detail  # Arabic: "يوجد طلب تسجيل..."
        )

    def test_same_child_different_kg_allowed(self, client, parent_token, test_db, sample_kindergarten, parent_user):
        """Same child should be allowed to enroll in a different KG"""
        headers = {"Authorization": f"Bearer {parent_token}"}
        dob = (date.today() - timedelta(days=365 * 3)).isoformat()

        # Create second kindergarten
        kg2 = models.Kindergarten(
            name_ar="روضة ثانية", name_en="Second KG",
            governorate="عمان", city="عمان", area="test",
            address_line="test", contact_phone="+962791116666",
            status=models.KindergartenStatus.ACTIVE
        )
        test_db.add(kg2)
        test_db.commit()

        enrollment_data = {
            "first_name": "Layla",
            "last_name": parent_user.parent_profile.last_name,
            "gender": "FEMALE",
            "date_of_birth": dob,
            "father_name": "Ahmad Al-Rashid",
            "mother_first_name": "Fatima",
            "mother_last_name": "Hassan",
            "mother_nationality": "Jordanian",
            "mother_national_id": "7777666655",
            "national_id": "2233445566",
            "kindergarten_id": sample_kindergarten.id
        }

        # First enrollment
        response1 = client.post("/api/enrollment/apply", json=enrollment_data, headers=headers)
        assert response1.status_code == 201, f"First enrollment failed: {response1.json()}"

        # Different KG should succeed
        enrollment_data2 = {**enrollment_data, "kindergarten_id": kg2.id, "mother_national_id": "7777666656"}
        response2 = client.post("/api/enrollment/apply", json=enrollment_data2, headers=headers)
        assert response2.status_code == 201

    def test_active_enrollment_other_kg_blocked(self, client, parent_token, test_db, sample_kindergarten, parent_user):
        """Child with active enrollment in another KG should be blocked"""
        headers = {"Authorization": f"Bearer {parent_token}"}
        dob = (date.today() - timedelta(days=365 * 3)).isoformat()

        # Create child + active enrollment in KG1
        child = models.Child(
            parent_id=parent_user.parent_profile.id,
            first_name="Maya",
            last_name="Al-Rashid",
            gender=models.Gender.FEMALE,
            date_of_birth=date.fromisoformat(dob),
            father_name="Ahmad Al-Rashid",
            mother_first_name="Fatima",
            mother_last_name="Hassan",
            mother_nationality="Jordanian",
            mother_national_id="5555444433",
        )
        test_db.add(child)
        test_db.commit()
        test_db.refresh(child)

        enrollment_active = models.EnrollmentApplication(
            child_id=child.id,
            kindergarten_id=sample_kindergarten.id,
            status=models.EnrollmentStatus.ACTIVE
        )
        test_db.add(enrollment_active)
        test_db.commit()

        # Create second KG
        kg2 = models.Kindergarten(
            name_ar="روضة ثانية", name_en="Second KG",
            governorate="Amman", city="Amman", area="test",
            address_line="test", contact_phone="+962791116777",
            status=models.KindergartenStatus.ACTIVE
        )
        test_db.add(kg2)
        test_db.commit()

        enrollment_data = {
            "first_name": "Maya",
            "last_name": "Al-Rashid",
            "gender": "FEMALE",
            "date_of_birth": dob,
            "father_name": "Ahmad Al-Rashid",
            "mother_first_name": "Fatima",
            "mother_last_name": "Hassan",
            "mother_nationality": "Jordanian",
            "mother_national_id": "5555444433",
            "kindergarten_id": kg2.id
        }

        response = client.post("/api/enrollment/apply", json=enrollment_data, headers=headers)
        assert response.status_code == 400
        detail = response.json()["detail"]
        assert "child" in detail.lower() or "طفل" in detail  # Arabic: "هذا الطفل مسجل..."

    def test_submit_blocked_when_active_elsewhere(self, client, parent_token, test_db, sample_kindergarten, parent_user):
        """Submitting draft should fail if child has active enrollment elsewhere"""
        headers = {"Authorization": f"Bearer {parent_token}"}
        dob = (date.today() - timedelta(days=365 * 3)).isoformat()

        child = models.Child(
            parent_id=parent_user.parent_profile.id,
            first_name="Ola",
            last_name="Al-Rashid",
            gender=models.Gender.FEMALE,
            date_of_birth=date.fromisoformat(dob),
            father_name="Ahmad Al-Rashid",
            mother_first_name="Fatima",
            mother_last_name="Hassan",
            mother_nationality="Jordanian",
            mother_national_id="6666555544",
        )
        test_db.add(child)
        test_db.commit()
        test_db.refresh(child)

        enrollment_active = models.EnrollmentApplication(
            child_id=child.id,
            kindergarten_id=sample_kindergarten.id,
            status=models.EnrollmentStatus.ACTIVE
        )
        test_db.add(enrollment_active)
        test_db.commit()

        kg2 = models.Kindergarten(
            name_ar="روضة ثالثة", name_en="Third KG",
            governorate="Amman", city="Amman", area="test",
            address_line="test", contact_phone="+962791116888",
            status=models.KindergartenStatus.ACTIVE
        )
        test_db.add(kg2)
        test_db.commit()

        enrollment_draft = models.EnrollmentApplication(
            child_id=child.id,
            kindergarten_id=kg2.id,
            status=models.EnrollmentStatus.DRAFT
        )
        test_db.add(enrollment_draft)
        test_db.commit()
        test_db.refresh(enrollment_draft)

        response = client.post(f"/api/enrollment/{enrollment_draft.id}/submit", headers=headers)
        assert response.status_code == 400
        detail = response.json()["detail"]
        assert "child" in detail.lower() or "طفل" in detail  # Arabic: "هذا الطفل مسجل..."


class TestEnrollmentUniquenessConcurrency:
    """Simulate concurrent duplicate creates using separate sessions"""

    def test_unique_constraint_blocks_second_create(self, test_db, sample_kindergarten, parent_user):
        child = models.Child(
            parent_id=parent_user.parent_profile.id,
            first_name="Zain",
            last_name="Al-Rashid",
            gender=models.Gender.MALE,
            date_of_birth=date.today() - timedelta(days=365 * 3),
            father_name="Ahmad Al-Rashid",
            mother_first_name="Fatima",
            mother_last_name="Hassan",
            mother_nationality="Jordanian",
            mother_national_id="7777666611",
        )
        test_db.add(child)
        test_db.commit()
        test_db.refresh(child)

        SessionLocal = sessionmaker(bind=test_db.get_bind())
        s1 = SessionLocal()
        s2 = SessionLocal()
        try:
            e1 = models.EnrollmentApplication(
                child_id=child.id,
                kindergarten_id=sample_kindergarten.id,
                status=models.EnrollmentStatus.DRAFT
            )
            s1.add(e1)
            s1.commit()

            e2 = models.EnrollmentApplication(
                child_id=child.id,
                kindergarten_id=sample_kindergarten.id,
                status=models.EnrollmentStatus.DRAFT
            )
            s2.add(e2)
            with pytest.raises(IntegrityError):
                s2.commit()
        finally:
            s1.close()
            s2.close()


class TestEnrollmentCreatePage:
    """Test enrollment create page rendering"""

    def test_parent_sees_enrollment_form(self, client, parent_token, test_db, sample_kindergarten):
        """Parent should see enrollment form with KG selector"""
        client.cookies.set("kinjo_token", parent_token)
        response = client.get("/enrollments/create")
        assert response.status_code == 200
        html = response.text
        assert "govFilter" in html
        assert "cityFilter" in html
        assert "kgSearchInput" in html
        assert "kgResultsList" in html
        assert "kgSearchPanel" in html
        assert "kgDetailModal" in html

    def test_parent_sees_governorate_options(self, client, parent_token, test_db, sample_kindergarten):
        """Parent should see governorate dropdown options"""
        client.cookies.set("kinjo_token", parent_token)
        response = client.get("/enrollments/create")
        assert response.status_code == 200
        html = response.text
        assert "عمان" in html
        assert "إربد" in html

    def test_admin_sees_enrollment_form(self, client, admin_token, test_db, sample_kindergarten):
        """Admin should see enrollment form with same KG selector"""
        client.cookies.set("kinjo_token", admin_token)
        response = client.get("/enrollments/create")
        assert response.status_code == 200
        html = response.text
        assert "govFilter" in html
        assert "cityFilter" in html
        assert "kgDetailModal" in html

    def test_supervisor_gets_403(self, client, supervisor_token, test_db, sample_kindergarten):
        """Supervisor should get 403 on enrollment create"""
        client.cookies.set("kinjo_token", supervisor_token)
        response = client.get("/enrollments/create")
        assert response.status_code == 403

    def test_manager_skips_kg_selector(self, client, manager_token, test_db, sample_kindergarten):
        """Manager should skip KG selector (auto-assigned)"""
        client.cookies.set("kinjo_token", manager_token)
        response = client.get("/enrollments/create")
        assert response.status_code == 200
        html = response.text
        # Manager shouldn't see the search panel div (id="kgSearchPanel") in the HTML
        assert 'id="kgSearchPanel"' not in html

    def test_page_has_detail_modal(self, client, parent_token, test_db, sample_kindergarten):
        """Page should include the KG detail modal"""
        client.cookies.set("kinjo_token", parent_token)
        response = client.get("/enrollments/create")
        html = response.text
        assert "kgDetailModal" in html
        assert "تفاصيل الروضة" in html
        assert "تأكيد اختيار الروضة" in html

    def test_page_has_clear_filters(self, client, parent_token, test_db, sample_kindergarten):
        """Page should include clear filters button"""
        client.cookies.set("kinjo_token", parent_token)
        response = client.get("/enrollments/create")
        html = response.text
        assert "clearFiltersBtn" in html
        assert "مسح عوامل التصفية" in html

    def test_page_has_loading_skeleton(self, client, parent_token, test_db, sample_kindergarten):
        """Page should include loading skeleton"""
        client.cookies.set("kinjo_token", parent_token)
        response = client.get("/enrollments/create")
        html = response.text
        assert "kgLoadingSkeleton" in html
        assert "skeleton-line" in html
