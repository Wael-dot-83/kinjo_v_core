"""
Seed database with sample data for testing
"""
from datetime import date, datetime, timedelta
import os
import secrets
from sqlalchemy.orm import Session
from database import SessionLocal, init_db
import models
from auth import get_password_hash


def _seed_password(env_key: str) -> str:
    """Return password from env var or generate a random one."""
    pw = os.environ.get(env_key)
    if pw:
        return pw
    pw = secrets.token_urlsafe(16)
    print(f"   \u26a0  No {env_key} set \u2014 generated random password: {pw}")
    return pw

def seed_database():
    """Seed database with sample kindergartens, users, and test data"""
    db = SessionLocal()

    try:
        print("Initializing database...")
        init_db()

        # Check if data already exists
        existing_kindergartens = db.query(models.Kindergarten).count()
        if existing_kindergartens > 0:
            print("Database already has data. Skipping seed.")
            return

        print("Seeding database with sample data...")

        # Create sample kindergartens
        kindergarten1 = models.Kindergarten(
            name_ar="روضة الأمل",
            name_en="Al Amal Kindergarten",
            governorate="عمان",
            city="عمان",
            area="عبدون",
            address_line="شارع 42، عمارة 5",
            contact_phone="+962791234567",
            contact_email="info@alamal.jo",
            status=models.KindergartenStatus.ACTIVE,
            operating_hours_start="07:00",
            operating_hours_end="15:00",
            license_number="KG-AMM-2024-001",
            license_valid_until=date.today() + timedelta(days=365)
        )

        kindergarten2 = models.Kindergarten(
            name_ar="روضة النور",
            name_en="Al Noor Kindergarten",
            governorate="عمان",
            city="عمان",
            area="الصويفية",
            address_line="شارع الرينبو 15",
            contact_phone="+962791234568",
            contact_email="info@alnoor.jo",
            status=models.KindergartenStatus.ACTIVE,
            operating_hours_start="07:30",
            operating_hours_end="14:30",
            license_number="KG-AMM-2024-002",
            license_valid_until=date.today() + timedelta(days=365)
        )

        db.add(kindergarten1)
        db.add(kindergarten2)
        db.flush()

        print(f"Created kindergarten: {kindergarten1.name_en} (ID: {kindergarten1.id})")
        print(f"Created kindergarten: {kindergarten2.name_en} (ID: {kindergarten2.id})")

        # Create admin user
        admin_user = models.User(
            username="admin",
            email="admin@kinjo.jo",
            hashed_password=get_password_hash(_seed_password("SEED_ADMIN_PASSWORD")),
            role=models.UserRole.ADMIN,
            status=models.UserStatus.ACTIVE
        )
        db.add(admin_user)
        db.flush()
        print(f"Created admin user: {admin_user.username}")

        # Create manager for kindergarten1
        manager1 = models.User(
            username="manager1",
            email="manager1@kinjo.jo",
            hashed_password=get_password_hash(_seed_password("SEED_MANAGER_PASSWORD")),
            role=models.UserRole.MANAGER,
            kindergarten_id=kindergarten1.id,
            status=models.UserStatus.ACTIVE
        )
        db.add(manager1)
        db.flush()
        print(f"Created manager: {manager1.username} for {kindergarten1.name_en}")

        # Create supervisor for kindergarten1
        supervisor1 = models.User(
            username="supervisor1",
            email="supervisor1@kinjo.jo",
            hashed_password=get_password_hash(_seed_password("SEED_SUPERVISOR_PASSWORD")),
            role=models.UserRole.SUPERVISOR,
            kindergarten_id=kindergarten1.id,
            status=models.UserStatus.ACTIVE
        )
        db.add(supervisor1)
        db.flush()
        print(f"Created supervisor: {supervisor1.username}")

        # Create sample parent user
        parent_user = models.User(
            username="parent1@example.com",
            email="parent1@example.com",
            hashed_password=get_password_hash(_seed_password("SEED_PARENT_PASSWORD")),
            role=models.UserRole.PARENT,
            status=models.UserStatus.ACTIVE
        )
        db.add(parent_user)
        db.flush()

        # Create parent profile
        parent_profile = models.ParentProfile(
            user_id=parent_user.id,
            first_name="Ahmad",
            last_name="Al-Rashid",
            phone_number="+962791111111",
            gender=models.Gender.MALE,
            nationality="Jordanian",
            national_id="1234567890",
            home_governorate="عمان",
            home_district="عمان",
            home_area="عبدون",
            home_address_line="شارع المنزل 123",
            correspondence_preference=True
        )
        db.add(parent_profile)
        db.flush()
        print(f"Created parent profile: {parent_profile.first_name} {parent_profile.last_name}")

        # Create classes for kindergarten1
        class1 = models.Class(
            kindergarten_id=kindergarten1.id,
            name_ar="الصف الأول",
            name_en="Class A",
            class_code="ALAMAL-A-001",
            age_group="AGE_2_4",
            capacity_total=20,
            min_age_months=24,  # 2 years
            max_age_months=48,  # 4 years
            is_active=True
        )
        db.add(class1)
        db.flush()
        print(f"Created class: {class1.name_en} with capacity {class1.capacity_total}")

        # Create sample child
        child_dob = date.today() - timedelta(days=365 * 3)  # 3 years old
        child = models.Child(
            parent_id=parent_profile.id,
            first_name="Layla",
            last_name="Al-Rashid",
            gender=models.Gender.FEMALE,
            date_of_birth=child_dob,
            father_name="Ahmad Al-Rashid",
            mother_first_name="Fatima",
            mother_last_name="Hassan",
            mother_nationality="Jordanian",
            mother_national_id="0987654321",
            media_consent=True,
            correspondence_flag=True
        )
        db.add(child)
        db.flush()
        print(f"Created child: {child.first_name} {child.last_name}")

        # Create enrollment application for the child
        enrollment = models.EnrollmentApplication(
            child_id=child.id,
            kindergarten_id=kindergarten1.id,
            class_id=class1.id,
            status=models.EnrollmentStatus.ACTIVE,
            source="WEB",
            submitted_at=datetime.now(),
            enrollment_start_date=date.today() - timedelta(days=21),
            enrollment_end_date=date.today() + timedelta(days=365),
            class_assignment_date=date.today() - timedelta(days=21)
        )
        db.add(enrollment)
        db.flush()
        print(f"Created enrollment for child in class: {class1.name_en}")

        # Assign supervisor to class
        assignment = models.SupervisorAssignment(
            class_id=class1.id,
            supervisor_id=supervisor1.id,
            is_primary=True,
            start_date=date.today()
        )
        db.add(assignment)

        # Create services for kindergartens
        services = [
            models.KindergartenService(
                kindergarten_id=kindergarten1.id,
                service_name="Extended Time",
                description="Extended care until 17:00",
                enabled_flag=True
            ),
            models.KindergartenService(
                kindergarten_id=kindergarten1.id,
                service_name="Waiting Hour",
                description="Early drop-off from 06:30",
                enabled_flag=True
            ),
            models.KindergartenService(
                kindergarten_id=kindergarten1.id,
                service_name="Transportation",
                description="Bus service for pickup and drop-off",
                enabled_flag=False
            )
        ]
        for service in services:
            db.add(service)

        print(f"Created {len(services)} services for kindergartens")

        # Create operating calendar entries
        for i in range(30):  # Next 30 days
            calendar_date = date.today() + timedelta(days=i)
            # Closed on Fridays
            is_open = calendar_date.weekday() != 4

            calendar_entry = models.OperatingCalendar(
                kindergarten_id=kindergarten1.id,
                date=calendar_date,
                is_open=is_open,
                reason="Friday" if not is_open else None
            )
            db.add(calendar_entry)

        print("Created operating calendar for next 30 days")

        # Backfill historical operating calendar for recent period (for KPI trends)
        for i in range(21, 0, -1):
            calendar_date = date.today() - timedelta(days=i)
            is_open = calendar_date.weekday() != 4
            db.add(
                models.OperatingCalendar(
                    kindergarten_id=kindergarten1.id,
                    date=calendar_date,
                    is_open=is_open,
                    reason="Friday" if not is_open else None,
                )
            )

        # Seed attendance/daily reports/incidents/checklists/staff presence for real KPI computation
        for i in range(21, 0, -1):
            day = date.today() - timedelta(days=i)
            if day.weekday() == 4:
                continue  # Friday closed by default policy

            # Attendance (mix of present/excused/absent)
            attendance_status = models.AttendanceStatus.PRESENT
            if i % 9 == 0:
                attendance_status = models.AttendanceStatus.ABSENT
            elif i % 7 == 0:
                attendance_status = models.AttendanceStatus.EXCUSED

            db.add(
                models.AttendanceLog(
                    child_id=child.id,
                    class_id=class1.id,
                    date=day,
                    status=attendance_status,
                    recorded_by=supervisor1.id,
                )
            )

            # Daily reports for attended days
            if attendance_status in (
                models.AttendanceStatus.PRESENT,
                models.AttendanceStatus.EXCUSED,
                models.AttendanceStatus.LATE,
            ):
                report_status = (
                    models.DailyReportStatus.SENT_TO_PARENT
                    if i % 5 != 0
                    else models.DailyReportStatus.SUBMITTED
                )
                db.add(
                    models.DailyReport(
                        child_id=child.id,
                        kindergarten_id=kindergarten1.id,
                        date=day,
                        status=report_status,
                        submitted_by=supervisor1.id,
                        submitted_at=datetime.combine(day, datetime.min.time()),
                        approved_by=manager1.id if report_status == models.DailyReportStatus.SENT_TO_PARENT else None,
                        approved_at=datetime.combine(day, datetime.min.time()) if report_status == models.DailyReportStatus.SENT_TO_PARENT else None,
                        sent_to_parent_at=datetime.combine(day, datetime.min.time()) if report_status == models.DailyReportStatus.SENT_TO_PARENT else None,
                        arrival_time="08:00",
                    )
                )

            # Staff presence logs
            db.add(
                models.StaffPresenceLog(
                    staff_id=supervisor1.id,
                    kindergarten_id=kindergarten1.id,
                    date=day,
                    start_at=datetime.combine(day, datetime.strptime("07:30", "%H:%M").time()),
                    end_at=datetime.combine(day, datetime.strptime("15:00", "%H:%M").time()),
                )
            )

            # Ratio compliance cache row
            db.add(
                models.RatioCompliance(
                    kindergarten_id=kindergarten1.id,
                    date=day,
                    operating_minutes=450,
                    compliant_minutes=450 if i % 6 != 0 else 390,
                    staff_count_avg=1.0,
                    child_count_avg=1.0,
                )
            )

            # Daily checklist entries (opening/safety/closing)
            for checklist_type in ("opening", "safety", "closing"):
                status = (
                    models.DailyChecklistStatus.COMPLETED
                    if not (checklist_type == "safety" and i % 8 == 0)
                    else models.DailyChecklistStatus.PENDING
                )
                db.add(
                    models.DailyChecklist(
                        kindergarten_id=kindergarten1.id,
                        checklist_date=day,
                        checklist_type=checklist_type,
                        status=status,
                        submitted_by=manager1.id,
                        submitted_at=datetime.combine(day, datetime.min.time()) if status == models.DailyChecklistStatus.COMPLETED else None,
                    )
                )

        # Sample incidents (including serious + SLA)
        incident_day = date.today() - timedelta(days=6)
        db.add(
            models.Incident(
                child_id=child.id,
                kindergarten_id=kindergarten1.id,
                type=models.IncidentType.INJURY,
                severity_level=models.SeverityLevel.MEDIUM,
                description="Minor playground injury",
                occurred_at=datetime.combine(incident_day, datetime.strptime("09:30", "%H:%M").time()),
                followup_required_flag=True,
                followup_sla_deadline=datetime.combine(incident_day + timedelta(days=1), datetime.strptime("17:00", "%H:%M").time()),
                closed_at=datetime.combine(incident_day, datetime.strptime("15:00", "%H:%M").time()),
            )
        )
        serious_day = date.today() - timedelta(days=3)
        db.add(
            models.Incident(
                child_id=child.id,
                kindergarten_id=kindergarten1.id,
                type=models.IncidentType.OTHER,
                severity_level=models.SeverityLevel.HIGH,
                description="Escalated safety incident",
                occurred_at=datetime.combine(serious_day, datetime.strptime("10:15", "%H:%M").time()),
                followup_required_flag=True,
                followup_sla_deadline=datetime.combine(serious_day + timedelta(days=1), datetime.strptime("17:00", "%H:%M").time()),
                closed_at=datetime.combine(serious_day + timedelta(days=2), datetime.strptime("10:00", "%H:%M").time()),
            )
        )

        # Mandatory training modules and completions
        module_safety = models.TrainingModule(
            name="Child Safeguarding",
            description="Mandatory safeguarding fundamentals",
            is_mandatory=True,
        )
        module_first_aid = models.TrainingModule(
            name="First Aid Basics",
            description="Mandatory basic first aid for staff",
            is_mandatory=True,
        )
        db.add_all([module_safety, module_first_aid])
        db.flush()

        db.add(
            models.StaffTrainingCompletion(
                user_id=supervisor1.id,
                training_module_id=module_safety.id,
                kindergarten_id=kindergarten1.id,
                completion_date=date.today() - timedelta(days=10),
                status=models.TrainingStatus.COMPLETED,
            )
        )
        db.add(
            models.StaffTrainingCompletion(
                user_id=manager1.id,
                training_module_id=module_first_aid.id,
                kindergarten_id=kindergarten1.id,
                completion_date=date.today() - timedelta(days=15),
                status=models.TrainingStatus.COMPLETED,
            )
        )

        # Parent satisfaction survey data
        survey = models.Survey(
            kindergarten_id=kindergarten1.id,
            title="Parent Satisfaction - Monthly Pulse",
            description="Monthly parent experience survey",
            nps_question_enabled=True,
            start_date=date.today() - timedelta(days=30),
            end_date=date.today() + timedelta(days=1),
        )
        db.add(survey)
        db.flush()
        db.add(
            models.SurveyResponse(
                survey_id=survey.id,
                parent_id=parent_user.id,
                nps_score=9,
                feedback_text="Good communication and safe environment",
            )
        )

        db.commit()
        print("\n=== Database seeded successfully! ===\n")
        print("Sample credentials (set via SEED_*_PASSWORD env vars):")
        print("  Admin:      admin")
        print("  Manager:    manager1")
        print("  Supervisor: supervisor1")
        print("  Parent:     parent1@example.com")
        print("\nTest the API at: http://localhost:8000/docs")

    except (RuntimeError, ValueError, TypeError, AttributeError, OSError) as e:
        print(f"Error seeding database: {e}")
        db.rollback()
        raise
    finally:
        db.close()


if __name__ == "__main__":
    seed_database()
