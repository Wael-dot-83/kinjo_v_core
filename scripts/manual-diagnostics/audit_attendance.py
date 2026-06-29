
import sys
import os
from datetime import date, datetime, timedelta
from fastapi import HTTPException
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.exc import IntegrityError
import models
import validators
from missing_endpoints import check_in_child, check_out_child

# -----------------------------------------------------------------------------
# SETUP
# -----------------------------------------------------------------------------

# Use in-memory SQLite for testing
engine = create_engine('sqlite:///:memory:')
properties = models.Base.metadata.create_all(engine)
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
    # Organization
    kg = models.Kindergarten(
        name_ar="Rawdat Al-Test", # Changed from name
        name_en="Test KG",       # Added
        governorate="Amman",
        city="Amman",
        area="Shmeisani",
        address_line="123 St",
        contact_phone="0791234567",
        contact_email="test@kg.com",
        license_number="123",
        status=models.KindergartenStatus.ACTIVE
    )
    db.add(kg)
    db.commit()

    # Users
    admin = models.User(username="admin", email="admin@test.com", role=models.UserRole.ADMIN, hashed_password="hash")
    manager = models.User(username="manager", email="manager@test.com", role=models.UserRole.MANAGER, kindergarten_id=kg.id, hashed_password="hash")
    supervisor = models.User(username="supervisor", email="super@test.com", role=models.UserRole.SUPERVISOR, kindergarten_id=kg.id, hashed_password="hash")
    parent_user = models.User(username="parent", email="parent@test.com", role=models.UserRole.PARENT, hashed_password="hash")
    db.add_all([admin, manager, supervisor, parent_user])
    db.commit()

    # Parent Profile
    parent_profile = models.ParentProfile(
        user_id=parent_user.id, 
        first_name="P", 
        last_name="T", 
        phone_number="0790000000", 
        national_id="0000000000",
        gender=models.Gender.MALE,
        nationality="Jordanian",
        home_governorate="Amman",
        home_district="Amman",
        home_area="Area",
        home_address_line="Street"
    )
    db.add(parent_profile)
    db.commit()

    # Class
    cls = models.Class(
        kindergarten_id=kg.id, 
        name_ar="Class A",
        name_en="Class A",
        is_active=True, 
        min_age_months=0, 
        max_age_months=60, 
        capacity_total=10
    )
    db.add(cls)
    db.commit()

    # Supervisor Assignment
    sa = models.SupervisorAssignment(supervisor_id=supervisor.id, class_id=cls.id, start_date=date.today())
    db.add(sa)
    db.commit()

    # Child
    child = models.Child(
        parent_id=parent_profile.id, 
        first_name="Kid", 
        last_name="Uno", 
        date_of_birth=date.today() - timedelta(days=1000), 
        gender=models.Gender.MALE,
        father_name="Dad",
        mother_first_name="Mom",
        mother_last_name="MomLast",
        mother_nationality="Jordanian"
    )
    db.add(child)
    db.commit()

    # Enrollment (Active)
    enrollment = models.EnrollmentApplication(child_id=child.id, kindergarten_id=kg.id, class_id=cls.id, status=models.EnrollmentStatus.ACTIVE, submitted_at=datetime.now())
    db.add(enrollment)
    db.commit()

    print("SEEDING COMPLETE")
    print("-" * 50)

except Exception as e:
    print(f"SEEDING FAILED: {e}")
    sys.exit(1)

# -----------------------------------------------------------------------------
# TEST EXECUTION
# -----------------------------------------------------------------------------

# TEST 1: Supervisor Check-In (RBAC Bug Verification)
try:
    check_in_child(child_id=child.id, method="manual", dropped_by_name="Mom", current_user=supervisor, db=db)
    log("Supervisor Check-In", "PASS", "Supervisor successfully checked in child.")
except HTTPException as e:
    log("Supervisor Check-In", "FAIL", f"Supervisor access denied: {e.status_code} - {e.detail}")
except Exception as e:
    log("Supervisor Check-In", "ERROR", f"Unexpected error: {str(e)}")


# TEST 2: Manager Check-In (Should Work - But technically Duplicate now if Test 1 passed)
try:
    check_in_child(child_id=child.id, method="manual", dropped_by_name="Mom", current_user=manager, db=db)
    log("Manager Check-In (Duplicate Attempt)", "FAIL", "Allowed duplicate check-in!")
except HTTPException as e:
    if e.status_code == 400:
        log("Manager Check-In (Duplicate Attempt)", "PASS", f"Correctly rejected duplicate: {e.detail}")
    else:
        log("Manager Check-In (Duplicate Attempt)", "FAIL", f"Wrong error code: {e.status_code}")


# TEST 3: Duplicate Check-In (Immediate)
try:
    check_in_child(child_id=child.id, method="manual", dropped_by_name="Mom", db=db, current_user=manager)
    log("Duplicate Check-In", "FAIL", "Allowed duplicate check-in!")
except HTTPException as e:
    if e.status_code == 400 and "already checked in" in str(e.detail):
        log("Duplicate Check-In", "PASS", f"Correctly rejected: {e.detail}")
    else:
        log("Duplicate Check-In", "FAIL", f"Wrong error code: {e.status_code}")


# TEST 4: Check-Out
try:
    check_out_child(child_id=child.id, picked_by_name="Dad", current_user=manager, db=db)
    log("Manager Check-Out", "PASS", "Manager successfully checked out child.")
except Exception as e:
    log("Manager Check-Out", "FAIL", f"Error: {e}")


# TEST 5: Re-Check-In After Check-Out (Integrity Bug Verification)
try:
    check_in_child(child_id=child.id, method="manual", dropped_by_name="Return", current_user=manager, db=db)
    log("Re-Check-In Same Day", "FAIL (Integrity Issue)", "Function executed without raising HTTPException. Did DB catch it?")
except IntegrityError:
    log("Re-Check-In Same Day", "FAIL (Crash)", "Caught SQLAlchemy IntegrityError! API crashed 500 instead of 400.")
    db.rollback() # Reset for next test
except HTTPException as e:
     log("Re-Check-In Same Day", "PASS", f"Handled correctly with HTTP {e.status_code}: {e.detail}")
except Exception as e:
    log("Re-Check-In Same Day", "FAIL (Unknown)", f"Error: {type(e)} - {str(e)}")

