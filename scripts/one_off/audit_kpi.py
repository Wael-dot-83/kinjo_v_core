
import sys
import os
from datetime import date, datetime, timedelta
from fastapi import HTTPException
from sqlalchemy import create_engine, func
from sqlalchemy.orm import sessionmaker
import models
import validators
from kpi_service import KPIService, get_kpi_summary
# Mock Pydantic models - not needed if we call service methods directly or mock the request

# -----------------------------------------------------------------------------
# SETUP
# -----------------------------------------------------------------------------
engine = create_engine('sqlite:///:memory:')
models.Base.metadata.create_all(engine)
SessionLocal = sessionmaker(bind=engine)
db = SessionLocal()

def log(test, result, details):
    print(f"TEST: {test}")
    print(f"RESULT: {result}")
    print(f"DETAILS: {details}")
    print("-" * 50)

# -----------------------------------------------------------------------------
# SEED DATA
# -----------------------------------------------------------------------------
try:
    # 1. Kindergarten
    kg = models.Kindergarten(
        name_ar="KG1", name_en="KG1", governorate="Amman", city="Amman", 
        area="Area", address_line="St", contact_phone="079", contact_email="kg@test.com",
        status=models.KindergartenStatus.ACTIVE
    )
    db.add(kg)
    db.commit()

    # 2. Users
    mgr = models.User(username="mgr", email="mgr@test.com", role=models.UserRole.MANAGER, kindergarten_id=kg.id, hashed_password="x")
    supervisor = models.User(username="sup", email="sup@test.com", role=models.UserRole.SUPERVISOR, kindergarten_id=kg.id, hashed_password="x")
    db.add_all([mgr, supervisor])
    db.commit()

    # 3. Class (Capacity 10)
    cls = models.Class(
        kindergarten_id=kg.id, name_ar="A", capacity_total=10, 
        min_age_months=0, max_age_months=60, is_active=True
    )
    db.add(cls)
    db.commit()

    # 4. Children (5 Active)
    # Child 1-5
    children = []
    parent_user = models.User(username="p", email="p@t.com", role=models.UserRole.PARENT, hashed_password="x")
    db.add(parent_user)
    db.commit()
    
    pp = models.ParentProfile(user_id=parent_user.id, first_name="P", last_name="T", phone_number="0", gender=models.Gender.MALE, nationality="J", home_governorate="A", home_city="A", home_area="A", home_address_line="A")
    db.add(pp)
    db.commit() # Commit to get ID
    
    for i in range(5):
        c = models.Child(
            parent_id=pp.id, first_name=f"C{i}", last_name="T", 
            date_of_birth=date.today() - timedelta(days=365 * 3), gender=models.Gender.MALE,
            father_name="F", mother_first_name="M", mother_last_name="L", mother_nationality="J"
        )
        children.append(c)
    db.add_all(children)
    db.commit()

    # 5. Active Enrollments
    for c in children:
        enr = models.EnrollmentApplication(
            child_id=c.id, kindergarten_id=kg.id, class_id=cls.id, 
            status=models.EnrollmentStatus.ACTIVE
        )
        db.add(enr)
    db.commit()

    # 6. Attendance Logs (For KPIs)
    # Scenario: 5-day week. 5 students. Total expected child-days = 25.
    # Day 1: 5 Present
    # Day 2: 4 Present
    # Day 3: 3 Present
    # Day 4: 5 Present
    # Day 5: 0 Present (Holiday?)
    # Total Present = 17.
    # Rate = 17 / 25 = 68%

    start_date = date.today() - timedelta(days=4) # 5 days ago including today
    end_date = date.today()

    # Create logs
    # Day 1 (Index 0): All 5
    for c in children:
        db.add(models.AttendanceLog(child_id=c.id, date=start_date, check_in_at=datetime.now(), method=models.AttendanceMethod.PIN))
    
    # Day 2 (Index 1): 4 children
    for c in children[:4]:
        db.add(models.AttendanceLog(child_id=c.id, date=start_date + timedelta(days=1), check_in_at=datetime.now(), method=models.AttendanceMethod.PIN))

    # Day 3 (Index 2): 3 children
    for c in children[:3]:
        db.add(models.AttendanceLog(child_id=c.id, date=start_date + timedelta(days=2), check_in_at=datetime.now(), method=models.AttendanceMethod.PIN))

    # Day 4 (Index 3): 5 children
    for c in children:
        db.add(models.AttendanceLog(child_id=c.id, date=start_date + timedelta(days=3), check_in_at=datetime.now(), method=models.AttendanceMethod.PIN))

    # Day 5 (Index 4): 0 children

    db.commit()

    print("SEEDING COMPLETE")
    print("-" * 50)

except Exception as e:
    print(f"SEEDING FAILED: {e}")
    sys.exit(1)

# -----------------------------------------------------------------------------
# TEST 1: KPI CALCULATION ACCURACY
# -----------------------------------------------------------------------------

try:
    rate = KPIService.compute_attendance_rate(db, kg.id, start_date, end_date)
    expected = (17 / 25) * 100 # 68.0
    
    if abs(rate - expected) < 0.1:
        log("1. Attendance Rate Calculation", "PASS", f"Got {rate}%, Expected {expected}%")
    else:
        log("1. Attendance Rate Calculation", "FAIL", f"Got {rate}%, Expected {expected}%")

except Exception as e:
    log("1. Attendance Rate Calculation", "ERROR", str(e))


# -----------------------------------------------------------------------------
# TEST 2: PERMISSION CHECK (GET SUMMARY)
# -----------------------------------------------------------------------------

# Case 2.1: Manager Access (Should Pass)
try:
    res = get_kpi_summary(start_date=start_date, end_date=end_date, current_user=mgr, db=db)
    log("2.1 Manager Access", "PASS", f"Retrieved summary: Attendance={res.attendance_rate}")
except Exception as e:
    log("2.1 Manager Access", "FAIL", str(e))

# Case 2.2: Supervisor Access (Should Fail currently, per code)
try:
    res = get_kpi_summary(start_date=start_date, end_date=end_date, current_user=supervisor, db=db)
    log("2.2 Supervisor Access", "FAIL", "Supervisor accessed manager-only KPI")
except HTTPException as e:
    if e.status_code == 403:
        log("2.2 Supervisor Access", "PASS", "Blocked Supervisor access (Manager Only)")
    else:
        log("2.2 Supervisor Access", "FAIL", f"Wrong error: {e.status_code}")
except Exception as e:
    log("2.2 Supervisor Access", "ERROR", str(e))
