"""A3 — manager KPI enrollment rate = active enrollments / total capacity (%),
computed once, division-by-zero guarded."""
import models
from main import app
from dependencies import get_current_user


def _seed_class(test_db, kg_id, code, capacity, active=True):
    cls = models.Class(
        kindergarten_id=kg_id, name_ar=code, name_en=code, class_code=code,
        age_group="AGE_1_2", capacity_total=capacity, min_age_months=24,
        max_age_months=48, is_active=active,
    )
    test_db.add(cls)
    test_db.commit()
    test_db.refresh(cls)
    return cls


def _seed_active_enrollment(test_db, kg_id, cls, n):
    """n active enrollments (each needs a parent->child chain)."""
    from datetime import date
    parent = models.User(username=f"p_{kg_id}_{cls.id}", email=f"p{kg_id}{cls.id}@t.com",
                         hashed_password="x", role=models.UserRole.PARENT,
                         status=models.UserStatus.ACTIVE)
    test_db.add(parent); test_db.commit(); test_db.refresh(parent)
    prof = models.ParentProfile(user_id=parent.id, first_name="P", last_name="P",
                                phone_number="+962790000000", gender=models.Gender.MALE,
                                nationality="Jordanian", national_id=f"N{kg_id}{cls.id}",
                                home_governorate="Amman", home_district="Amman",
                                home_area="A", home_address_line="A")
    test_db.add(prof); test_db.commit(); test_db.refresh(prof)
    for i in range(n):
        child = models.Child(parent_id=prof.id, first_name=f"C{i}", last_name="X",
                             gender=models.Gender.MALE, date_of_birth=date(2024, 1, 1),
                             father_name="F", mother_first_name="M", mother_last_name="X",
                             mother_nationality="Jordanian", mother_national_id=f"M{kg_id}{cls.id}{i}")
        test_db.add(child); test_db.commit(); test_db.refresh(child)
        test_db.add(models.EnrollmentApplication(child_id=child.id, kindergarten_id=kg_id,
                                                 class_id=cls.id, status=models.EnrollmentStatus.ACTIVE))
    test_db.commit()


def test_enrollment_rate_is_active_over_capacity(client, test_db, manager_user):
    kg = manager_user.kindergarten_id
    cls = _seed_class(test_db, kg, "CAP20", 20)
    _seed_active_enrollment(test_db, kg, cls, 5)  # 5 active / 20 capacity = 25%

    app.dependency_overrides[get_current_user] = lambda: manager_user
    try:
        resp = client.get("/api/manager/analytics/kpis")
        assert resp.status_code == 200, resp.text
        m = resp.json()["metrics"]
        assert m["active_enrollments"] == 5
        assert m["capacity"] == 20
        assert m["enrollment_rate"] == 25.0
        assert 0.0 <= m["enrollment_rate"] <= 100.0
    finally:
        app.dependency_overrides.pop(get_current_user, None)


def test_enrollment_rate_guards_zero_capacity(client, test_db, manager_user):
    kg = manager_user.kindergarten_id  # no classes -> capacity 0
    app.dependency_overrides[get_current_user] = lambda: manager_user
    try:
        resp = client.get("/api/manager/analytics/kpis")
        assert resp.status_code == 200, resp.text
        m = resp.json()["metrics"]
        assert m["capacity"] == 0
        assert m["enrollment_rate"] == 0.0  # no ZeroDivisionError
    finally:
        app.dependency_overrides.pop(get_current_user, None)
