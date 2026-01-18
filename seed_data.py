"""
Seed database with sample data for testing
"""
from datetime import date, datetime, timedelta
from sqlalchemy.orm import Session
from database import SessionLocal, init_db
import models
from auth import get_password_hash

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
            governorate="Amman",
            city="Amman",
            area="Abdoun",
            address_line="Street 42, Building 5",
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
            governorate="Amman",
            city="Amman",
            area="Sweifieh",
            address_line="Rainbow Street 15",
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
            hashed_password=get_password_hash("Admin123!"),
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
            hashed_password=get_password_hash("Manager123!"),
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
            hashed_password=get_password_hash("Supervisor123!"),
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
            hashed_password=get_password_hash("Parent123!"),
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
            home_governorate="Amman",
            home_city="Amman",
            home_area="Abdoun",
            home_address_line="Home Street 123",
            correspondence_preference=True
        )
        db.add(parent_profile)
        db.flush()
        print(f"Created parent profile: {parent_profile.first_name} {parent_profile.last_name}")

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

        # Create classes for kindergarten1
        class1 = models.Class(
            kindergarten_id=kindergarten1.id,
            name_ar="الصف الأول",
            name_en="Class A",
            capacity_total=20,
            min_age_months=24,  # 2 years
            max_age_months=48,  # 4 years
            is_active=True
        )
        db.add(class1)
        db.flush()
        print(f"Created class: {class1.name_en} with capacity {class1.capacity_total}")

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

        db.commit()
        print("\n=== Database seeded successfully! ===\n")
        print("Sample credentials:")
        print("  Admin:      admin / Admin123!")
        print("  Manager:    manager1 / Manager123!")
        print("  Supervisor: supervisor1 / Supervisor123!")
        print("  Parent:     parent1@example.com / Parent123!")
        print("\nTest the API at: http://localhost:8000/docs")

    except Exception as e:
        print(f"Error seeding database: {e}")
        db.rollback()
        raise
    finally:
        db.close()


if __name__ == "__main__":
    seed_database()
