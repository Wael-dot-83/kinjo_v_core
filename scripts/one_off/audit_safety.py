
import sys
import os
from datetime import date, datetime, timedelta
from fastapi import HTTPException
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
import models
import validators
# Import endpoints to test
from missing_endpoints import create_incident_json, create_health_alert, list_incidents, get_child_health_alerts
# Mock Pydantic models
class IncidentCreateRequest:
    def __init__(self, **kwargs):
        for k, v in kwargs.items():
            setattr(self, k, v)

class HealthAlertCreateRequest:
    def __init__(self, **kwargs):
        for k, v in kwargs.items():
            setattr(self, k, v)

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
    # Organization 1
    kg1 = models.Kindergarten(
        name_ar="KG One", name_en="KG One", 
        governorate="Amman", city="Amman", area="Area1", address_line="St1", 
        contact_phone="111", contact_email="kg1@test.com", status=models.KindergartenStatus.ACTIVE
    )
    db.add(kg1)

    # Organization 2 (For Cross-Tenant Testing)
    kg2 = models.Kindergarten(
        name_ar="KG Two", name_en="KG Two", 
        governorate="Amman", city="Amman", area="Area2", address_line="St2", 
        contact_phone="222", contact_email="kg2@test.com", status=models.KindergartenStatus.ACTIVE
    )
    db.add(kg2)
    db.commit()

    # Users
    # Admin
    admin = models.User(username="admin", email="admin@test.com", role=models.UserRole.ADMIN, hashed_password="x")
    
    # KG1 Staff
    mgr1 = models.User(username="mgr1", email="mgr1@test.com", role=models.UserRole.MANAGER, kindergarten_id=kg1.id, hashed_password="x")
    auth_sup1 = models.User(username="sup1", email="sup1@test.com", role=models.UserRole.SUPERVISOR, kindergarten_id=kg1.id, hashed_password="x")
    
    # KG2 Staff
    mgr2 = models.User(username="mgr2", email="mgr2@test.com", role=models.UserRole.MANAGER, kindergarten_id=kg2.id, hashed_password="x")
    
    # Parent
    parent_user = models.User(username="parent", email="parent@test.com", role=models.UserRole.PARENT, hashed_password="x")
    
    db.add_all([admin, mgr1, auth_sup1, mgr2, parent_user])
    db.commit()

    # Parent Profile
    pp = models.ParentProfile(
        user_id=parent_user.id, first_name="P", last_name="T", phone_number="079", 
        gender=models.Gender.MALE, nationality="Jordanian", home_governorate="Amman", 
        home_city="Amman", home_area="Area", home_address_line="Street"
    )
    db.add(pp)
    db.commit()

    # Child in KG1
    child1 = models.Child(
        parent_id=pp.id, first_name="Child1", last_name="Test", 
        date_of_birth=date.today() - timedelta(days=365 * 3), gender=models.Gender.MALE,
        father_name="F", mother_first_name="M", mother_last_name="L", mother_nationality="J"
    )
    db.add(child1)
    db.commit()

    # Enrollment for Child1 in KG1
    enr1 = models.EnrollmentApplication(
        child_id=child1.id, kindergarten_id=kg1.id, status=models.EnrollmentStatus.ACTIVE
    )
    db.add(enr1)
    db.commit()

    print("SEEDING COMPLETE")
    print("-" * 50)

except (RuntimeError, ValueError, TypeError, AttributeError, OSError) as e:
    print(f"SEEDING FAILED: {e}")
    sys.exit(1)

# -----------------------------------------------------------------------------
# TEST 1: INCIDENT REPORTING (RBAC)
# -----------------------------------------------------------------------------

# Case 1.1: Supervisor Reports Incident (Should PASS, currently might FAIL)
req = IncidentCreateRequest(
    child_id=child1.id,
    type="INJURY",
    severity_level="LOW",
    description="Scraped knee",
    occurred_at=datetime.now().isoformat(),
    followup_required_flag=False,
    kindergarten_id=kg1.id # Explicitly providing KG ID
)

try:
    create_incident_json(req, current_user=auth_sup1, db=db)
    log("1.1 Supervisor Report Incident", "PASS", "Supervisor successfully created incident")
except HTTPException as e:
    log("1.1 Supervisor Report Incident", "FAIL", f"HTTP {e.status_code}: {e.detail}")
except (RuntimeError, ValueError, TypeError, AttributeError, OSError) as e:
    log("1.1 Supervisor Report Incident", "ERROR", str(e))

# Case 1.2: Cross-Tenant Incident (KG2 Manager reports on KG1 Child)
req_cross = IncidentCreateRequest(
    child_id=child1.id,
    type="BEHAVIOR",
    severity_level="LOW",
    description="Bad behavior",
    occurred_at=datetime.now().isoformat(),
    followup_required_flag=False,
    kindergarten_id=kg2.id 
)

try:
    create_incident_json(req_cross, current_user=mgr2, db=db)
    # Check if DB actually linked incident to KG2 despite child being in KG1
    # This is a conceptual data integrity failure if allowed
    log("1.2 Cross-Tenant Incident", "WARNING", "System allowed reporting incident for child in different KG")
except HTTPException as e:
    log("1.2 Cross-Tenant Incident", "PASS", f"Correctly blocked: {e.detail}")


# -----------------------------------------------------------------------------
# TEST 2: HEALTH ALERTS
# -----------------------------------------------------------------------------

# Case 2.1: Supervisor Creates Alert (Should PASS)
alert_req = HealthAlertCreateRequest(
    alert_type="Allergy",
    description="Peanuts",
    severity="High"
)

try:
    create_health_alert(child_id=child1.id, alert_data=alert_req, current_user=auth_sup1, db=db)
    log("2.1 Supervisor Create Health Alert", "PASS", "Success")
except (RuntimeError, ValueError, TypeError, AttributeError, OSError) as e:
    log("2.1 Supervisor Create Health Alert", "FAIL", str(e))

# Case 2.2: Cross-Tenant Health Alert (KG2 Manager creates for KG1 Child)
try:
    create_health_alert(child_id=child1.id, alert_data=alert_req, current_user=mgr2, db=db)
    log("2.2 Cross-Tenant Alert Creation", "FAIL", "Security Hole: KG2 Manager created alert for KG1 Child")
except HTTPException as e:
    log("2.2 Cross-Tenant Alert Creation", "PASS", f"Blocked: {e.detail}")

# Case 2.3: Parent View (Own Child)
try:
    alerts = get_child_health_alerts(child_id=child1.id, current_user=parent_user, db=db)
    if len(alerts) > 0:
        log("2.3 Parent View Own Alerts", "PASS", f"Saw {len(alerts)} alerts")
    else:
         log("2.3 Parent View Own Alerts", "FAIL", "Returned 0 alerts (should see the one created in 2.1)")
except (RuntimeError, ValueError, TypeError, AttributeError, OSError) as e:
    log("2.3 Parent View Own Alerts", "ERROR", str(e))


