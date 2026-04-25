"""
Script to check existing data and populate test data for KPI dashboard
"""
from database import get_db
from sqlalchemy.orm import Session
from models import User, Child, EnrollmentApplication, Kindergarten, AttendanceLog, Incident, ParentProfile, UserRole
from auth import create_user
from datetime import date, datetime, timedelta, time
import random

def check_existing_data():
    """Check what data already exists"""
    db: Session = next(get_db())
    try:
        print("=== CHECKING EXISTING DATA ===")

        kg = db.query(Kindergarten).filter(Kindergarten.id == 8).first()
        print(f'Kindergarten 8: {kg.name_ar if kg else "Not found"}')

        supervisors = db.query(User).filter(User.kindergarten_id == 8, User.role == 'SUPERVISOR').count()
        print(f'Supervisors: {supervisors}')

        children = db.query(EnrollmentApplication).filter(EnrollmentApplication.kindergarten_id == 8, EnrollmentApplication.status == 'ACTIVE').count()
        print(f'Active enrollments: {children}')

        attendance = db.query(AttendanceLog).join(Child).join(EnrollmentApplication, EnrollmentApplication.child_id == Child.id).filter(EnrollmentApplication.kindergarten_id == 8).count()
        print(f'Attendance records: {attendance}')

        incidents = db.query(Incident).filter(Incident.kindergarten_id == 8).count()
        print(f'Incidents: {incidents}')

        return kg is not None

    except (RuntimeError, ValueError, TypeError, AttributeError, OSError) as e:
        print(f'Error checking data: {e}')
        return False
    finally:
        db.close()

def create_supervisors(db: Session):
    """Create supervisor users"""
    print("\n=== CREATING SUPERVISORS ===")

    supervisors_data = [
        {
            "username": "supervisor1",
            "email": "supervisor1@kindergarten8.com",
            "password": "password123",
            "first_name": "Ø£Ø­Ù…Ø¯",
            "last_name": "Ù…Ø­Ù…Ø¯"
        },
        {
            "username": "supervisor2",
            "email": "supervisor2@kindergarten8.com",
            "password": "password123",
            "first_name": "ÙØ§Ø·Ù…Ø©",
            "last_name": "Ø¹Ù„ÙŠ"
        },
        {
            "username": "supervisor3",
            "email": "supervisor3@kindergarten8.com",
            "password": "password123",
            "first_name": "Ù…Ø±ÙŠÙ…",
            "last_name": "Ø£Ø­Ù…Ø¯"
        }
    ]

    supervisors = []
    for data in supervisors_data:
        # Check if user already exists
        existing = db.query(User).filter(User.username == data["username"]).first()
        if existing:
            supervisors.append(existing)
            print(f"Using existing supervisor: {existing.username}")
        else:
            try:
                user = create_user(
                    db=db,
                    username=data["username"],
                    email=data["email"],
                    password=data["password"],
                    role=UserRole.SUPERVISOR,
                    kindergarten_id=8
                )
                supervisors.append(user)
                print(f"Created supervisor: {user.username}")
            except (RuntimeError, ValueError, TypeError, AttributeError, OSError) as e:
                print(f"Error creating supervisor {data['username']}: {e}")

    return supervisors

def create_children_and_enrollments(db: Session):
    """Create children and their enrollments"""
    print("\n=== CREATING CHILDREN AND ENROLLMENTS ===")

    # First create parent profiles and users
    parents_data = [
        {
            "username": "parent_mohammed_ali_2",
            "email": "mohammed.ali2@example.com",
            "password": "password123",
            "first_name": "Ù…Ø­Ù…Ø¯",
            "last_name": "Ø§Ù„Ø¹Ù„ÙŠ",
            "phone": "0501234567"
        },
        {
            "username": "parent_sara_ahmed_2",
            "email": "sara.ahmed2@example.com",
            "password": "password123",
            "first_name": "Ø³Ø§Ø±Ø©",
            "last_name": "Ø£Ø­Ù…Ø¯",
            "phone": "0502345678"
        }
    ]

    valid_dob = date.today() - timedelta(days=365 * 3)
    children_data = [
        {
            "first_name": "Ø¹Ù„ÙŠ",
            "last_name": "Ù…Ø­Ù…Ø¯",
            "gender": "MALE",
            "date_of_birth": valid_dob - timedelta(days=30),
            "father_name": "Ù…Ø­Ù…Ø¯ Ø§Ù„Ø¹Ù„ÙŠ",
            "mother_first_name": "ÙØ§Ø·Ù…Ø©",
            "mother_last_name": "Ø§Ù„Ø¹Ù„ÙŠ",
            "mother_nationality": "Ø§Ù„Ø³Ø¹ÙˆØ¯ÙŠØ©",
            "parent_index": 0
        },
        {
            "first_name": "Ù„ÙŠÙ†Ø§",
            "last_name": "Ø£Ø­Ù…Ø¯",
            "gender": "FEMALE",
            "date_of_birth": valid_dob - timedelta(days=60),
            "father_name": "Ø£Ø­Ù…Ø¯ Ø³Ø§Ø±Ø©",
            "mother_first_name": "Ø³Ø§Ø±Ø©",
            "mother_last_name": "Ø£Ø­Ù…Ø¯",
            "mother_nationality": "Ø§Ù„Ø³Ø¹ÙˆØ¯ÙŠØ©",
            "parent_index": 1
        },
        {
            "first_name": "ÙŠÙˆØ³Ù",
            "last_name": "Ù…Ø­Ù…Ø¯",
            "gender": "MALE",
            "date_of_birth": valid_dob - timedelta(days=90),
            "father_name": "Ù…Ø­Ù…Ø¯ Ø§Ù„Ø¹Ù„ÙŠ",
            "mother_first_name": "ÙØ§Ø·Ù…Ø©",
            "mother_last_name": "Ø§Ù„Ø¹Ù„ÙŠ",
            "mother_nationality": "Ø§Ù„Ø³Ø¹ÙˆØ¯ÙŠØ©",
            "parent_index": 0
        },
        {
            "first_name": "Ù†ÙˆØ±",
            "last_name": "Ø£Ø­Ù…Ø¯",
            "gender": "FEMALE",
            "date_of_birth": valid_dob - timedelta(days=120),
            "father_name": "Ø£Ø­Ù…Ø¯ Ø³Ø§Ø±Ø©",
            "mother_first_name": "Ø³Ø§Ø±Ø©",
            "mother_last_name": "Ø£Ø­Ù…Ø¯",
            "mother_nationality": "Ø§Ù„Ø³Ø¹ÙˆØ¯ÙŠØ©",
            "parent_index": 1
        },
        {
            "first_name": "Ø¹Ù…Ø±",
            "last_name": "Ù…Ø­Ù…Ø¯",
            "gender": "MALE",
            "date_of_birth": valid_dob - timedelta(days=150),
            "father_name": "Ù…Ø­Ù…Ø¯ Ø§Ù„Ø¹Ù„ÙŠ",
            "mother_first_name": "ÙØ§Ø·Ù…Ø©",
            "mother_last_name": "Ø§Ù„Ø¹Ù„ÙŠ",
            "mother_nationality": "Ø§Ù„Ø³Ø¹ÙˆØ¯ÙŠØ©",
            "parent_index": 0
        }
    ]

    # Create parents first
    parents = []
    for parent_data in parents_data:
        # Check if parent already exists
        existing_parent = db.query(ParentProfile).join(User).filter(User.username == parent_data["username"]).first()
        if existing_parent:
            parents.append(existing_parent)
            print(f"Using existing parent: {parent_data['username']}")
        else:
            try:
                # Create user
                user = create_user(
                    db=db,
                    username=parent_data["username"],
                    email=parent_data["email"],
                    password=parent_data["password"],
                    role=UserRole.PARENT,
                    kindergarten_id=None
                )

                # Create parent profile
                parent_profile = ParentProfile(
                    user_id=user.id,
                    first_name=parent_data["first_name"],
                    last_name=parent_data["last_name"],
                    phone_number=parent_data["phone"],
                    gender="MALE" if parent_data["first_name"] in ["Ù…Ø­Ù…Ø¯", "Ø£Ø­Ù…Ø¯"] else "FEMALE",
                    nationality="Ø§Ù„Ø³Ø¹ÙˆØ¯ÙŠØ©",
                    home_governorate="Ø§Ù„Ø±ÙŠØ§Ø¶",
                    home_city="Ø§Ù„Ø±ÙŠØ§Ø¶",
                    home_area="Ø§Ù„Ù…Ù„Ø²",
                    home_address_line="Ø´Ø§Ø±Ø¹ Ø§Ù„Ù…Ù„Ùƒ Ø¹Ø¨Ø¯Ø§Ù„Ø¹Ø²ÙŠØ²",
                    correspondence_preference=True
                )
                db.add(parent_profile)
                db.commit()
                db.refresh(parent_profile)
                parents.append(parent_profile)
                print(f"Created parent: {user.username}")
            except (RuntimeError, ValueError, TypeError, AttributeError, OSError) as e:
                print(f"Error creating parent {parent_data['username']}: {e}")

    # Create children and enrollments
    enrollments = []
    for child_data in children_data:
        try:
            parent = parents[child_data["parent_index"]]

            # Create child
            child = Child(
                parent_id=parent.id,
                first_name=child_data["first_name"],
                last_name=child_data["last_name"],
                gender=child_data["gender"],
                date_of_birth=child_data["date_of_birth"],
                father_name=child_data["father_name"],
                mother_first_name=child_data["mother_first_name"],
                mother_last_name=child_data["mother_last_name"],
                mother_nationality=child_data["mother_nationality"],
                media_consent=True,
                correspondence_flag=True
            )
            db.add(child)
            db.commit()
            db.refresh(child)

            # Create enrollment
            enrollment = EnrollmentApplication(
                child_id=child.id,
                kindergarten_id=8,
                status="ACTIVE",
                submitted_at=datetime.now(),
                decision_at=datetime.now()
            )
            db.add(enrollment)
            db.commit()
            db.refresh(enrollment)

            enrollments.append(enrollment)
            print(f"Created child and enrollment: {child.first_name} {child.last_name}")

        except (RuntimeError, ValueError, TypeError, AttributeError, OSError) as e:
            print(f"Error creating child {child_data['first_name']}: {e}")

    return enrollments

def create_attendance_records(db: Session, enrollments):
    """Create attendance records for the last 30 days"""
    print("\n=== CREATING ATTENDANCE RECORDS ===")

    # Get child IDs from enrollments
    child_ids = [e.child_id for e in enrollments]

    attendance_count = 0
    today = date.today()

    for days_back in range(30):
        attendance_date = today - timedelta(days=days_back)

        # Skip weekends (assuming kindergarten doesn't operate on weekends)
        if attendance_date.weekday() >= 5:  # Saturday = 5, Sunday = 6
            continue

        for child_id in child_ids:
            # 90% attendance rate (some absences)
            if random.random() < 0.9:
                # Create attendance record
                check_in_time = datetime.combine(attendance_date, time(8, 0))  # 8:00 AM
                check_out_time = datetime.combine(attendance_date, time(14, 0))  # 2:00 PM

                attendance = AttendanceLog(
                    child_id=child_id,
                    date=attendance_date,
                    check_in_at=check_in_time,
                    check_out_at=check_out_time,
                    method="MANUAL",
                    dropped_by_name="Ø§Ù„ÙˆØ§Ù„Ø¯",
                    picked_by_name="Ø§Ù„ÙˆØ§Ù„Ø¯"
                )
                db.add(attendance)
                attendance_count += 1

    db.commit()
    print(f"Created {attendance_count} attendance records")

def create_incidents(db: Session, enrollments):
    """Create some safety incidents"""
    print("\n=== CREATING SAFETY INCIDENTS ===")

    # Get child IDs from enrollments
    child_ids = [e.child_id for e in enrollments]

    incidents_data = [
        {
            "child_id": child_ids[0],
            "type": "INJURY",
            "severity": "LOW",
            "description": "Ø³Ù‚ÙˆØ· Ø·ÙÙŠÙ Ø£Ø«Ù†Ø§Ø¡ Ø§Ù„Ù„Ø¹Ø¨",
            "occurred_at": datetime.now() - timedelta(days=5),
            "followup_required": False
        },
        {
            "child_id": child_ids[1],
            "type": "ILLNESS",
            "severity": "MEDIUM",
            "description": "Ø§Ø±ØªÙØ§Ø¹ ÙÙŠ Ø¯Ø±Ø¬Ø© Ø§Ù„Ø­Ø±Ø§Ø±Ø©",
            "occurred_at": datetime.now() - timedelta(days=10),
            "followup_required": True
        },
        {
            "child_id": child_ids[2],
            "type": "BEHAVIOR",
            "severity": "LOW",
            "description": "Ù…Ø´Ø§Ø¯Ø© Ù…Ø¹ Ø²Ù…ÙŠÙ„",
            "occurred_at": datetime.now() - timedelta(days=15),
            "followup_required": False
        }
    ]

    for incident_data in incidents_data:
        try:
            incident = Incident(
                child_id=incident_data["child_id"],
                kindergarten_id=8,
                type=incident_data["type"],
                severity_level=incident_data["severity"],
                description=incident_data["description"],
                occurred_at=incident_data["occurred_at"],
                followup_required_flag=incident_data["followup_required"]
            )
            db.add(incident)
            print(f"Created incident: {incident.description[:30]}...")
        except (RuntimeError, ValueError, TypeError, AttributeError, OSError) as e:
            print(f"Error creating incident: {e}")

    db.commit()
    print(f"Created {len(incidents_data)} incidents")

def update_ratio_compliance(db: Session):
    """Update ratio compliance data with real staff and child counts"""
    print("\n=== UPDATING RATIO COMPLIANCE DATA ===")

    from models import RatioCompliance

    # Get supervisors and children counts
    supervisors_count = db.query(User).filter(User.kindergarten_id == 8, User.role == 'SUPERVISOR', User.status == 'ACTIVE').count()
    children_count = db.query(EnrollmentApplication).filter(EnrollmentApplication.kindergarten_id == 8, EnrollmentApplication.status == 'ACTIVE').count()

    print(f"Supervisors: {supervisors_count}, Children: {children_count}")

    # Update existing ratio compliance records
    records = db.query(RatioCompliance).filter(RatioCompliance.kindergarten_id == 8).all()

    for record in records:
        record.staff_count_avg = float(supervisors_count)
        record.child_count_avg = float(children_count)

        # Calculate compliant minutes (simplified: assume compliance when staff ratio is adequate)
        # Saudi regulation: 1 staff per 8 children for ages 3-6
        required_staff = max(1, children_count // 8)
        if supervisors_count >= required_staff:
            record.compliant_minutes = record.operating_minutes
        else:
            # Partial compliance based on available staff
            compliance_ratio = supervisors_count / required_staff if required_staff > 0 else 0
            record.compliant_minutes = int(record.operating_minutes * compliance_ratio)

    db.commit()
    print(f"Updated {len(records)} ratio compliance records")

if __name__ == "__main__":
    print("Starting data population for KPI dashboard...")

    if not check_existing_data():
        print("Kindergarten 8 not found. Please ensure it exists.")
        exit(1)

    db: Session = next(get_db())
    try:
        supervisors = create_supervisors(db)
        enrollments = create_children_and_enrollments(db)
        create_attendance_records(db, enrollments)
        create_incidents(db, enrollments)
        update_ratio_compliance(db)

        print("\n=== DATA POPULATION COMPLETE ===")
        print("âœ… Supervisors created")
        print("âœ… Children and enrollments created")
        print("âœ… Attendance records created")
        print("âœ… Safety incidents created")
        print("âœ… Ratio compliance data updated")

    except (RuntimeError, ValueError, TypeError, AttributeError, OSError) as e:
        print(f"Error during data population: {e}")
        db.rollback()
    finally:
        db.close()
