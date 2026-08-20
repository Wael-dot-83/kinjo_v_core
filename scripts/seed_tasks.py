"""
Seed data for Task Management feature testing
Creates users, kindergartens, and sample tasks
"""
from datetime import datetime, timedelta
import os
import secrets
from sqlalchemy.orm import Session
from database import SessionLocal, init_db
import models
from dependencies import has_role
from auth import create_user, get_password_hash


def _seed_password(env_key: str) -> str:
    """Return password from env var or generate a random one."""
    pw = os.environ.get(env_key)
    if pw:
        return pw
    pw = secrets.token_urlsafe(16)
    print(f"   ⚠  No {env_key} set — generated random password: {pw}")
    return pw

def seed_tasks():
    """Create comprehensive seed data for testing tasks"""
    db = SessionLocal()

    try:
        print("[SEED] Starting seed process...")

        # ============================================================================
        # 1. Create Kindergartens
        # ============================================================================
        print("\n📍 Creating kindergartens...")

        kg1 = models.Kindergarten(
            name_ar="حضانة الأمل",
            name_en="Al Amal Kindergarten",
            governorate="Amman",
            city="Amman",
            area="Abdoun",
            address_line="Street 1, Building 5",
            contact_phone="+962791111111",
            contact_email="alamal@example.com",
            status=models.KindergartenStatus.DRAFT,
            operating_hours_start="07:00",
            operating_hours_end="16:00"
        )
        db.add(kg1)

        kg2 = models.Kindergarten(
            name_ar="حضانة النور",
            name_en="Al Noor Kindergarten",
            governorate="Amman",
            city="Amman",
            area="Sweifieh",
            address_line="Street 10, Building 3",
            contact_phone="+962792222222",
            contact_email="alnoor@example.com",
            status=models.KindergartenStatus.DRAFT,
            operating_hours_start="07:30",
            operating_hours_end="15:30"
        )
        db.add(kg2)

        db.commit()
        db.refresh(kg1)
        db.refresh(kg2)
        print(f"   ✅ Created {kg1.name_en} (ID: {kg1.id})")
        print(f"   ✅ Created {kg2.name_en} (ID: {kg2.id})")

        # ============================================================================
        # 2. Create Users
        # ============================================================================
        print("\n👥 Creating users...")

        # Check if users already exist
        admin = db.query(models.User).filter(models.User.username == "admin").first()
        if not admin:
            admin = create_user(
                db=db,
                username="admin",
                email="admin@kinjo.com",
                password=_seed_password("SEED_ADMIN_PASSWORD"),
                role=models.UserRole.ADMIN
            )
            print(f"   [+] Admin: admin")
        else:
            print(f"   [*] Admin user already exists")

        manager1 = db.query(models.User).filter(models.User.username == "manager1").first()
        if not manager1:
            manager1 = create_user(
                db=db,
                username="manager1",
                email="manager1@kinjo.com",
                password=_seed_password("SEED_MANAGER_PASSWORD"),
                role=models.UserRole.MANAGER,
                kindergarten_id=kg1.id
            )
            print(f"   [+] Manager (Al Amal): manager1")
        else:
            print(f"   [*] manager1 already exists")

        manager2 = db.query(models.User).filter(models.User.username == "manager2").first()
        if not manager2:
            manager2 = create_user(
                db=db,
                username="manager2",
                email="manager2@kinjo.com",
                password=_seed_password("SEED_MANAGER_PASSWORD"),
                role=models.UserRole.MANAGER,
                kindergarten_id=kg2.id
            )
            print(f"   [+] Manager (Al Noor): manager2")
        else:
            print(f"   [*] manager2 already exists")

        for expected_manager, expected_kg, username in (
            (manager1, kg1, "manager1"),
            (manager2, kg2, "manager2"),
        ):
            if (
                not has_role(expected_manager, models.UserRole.MANAGER)
                or expected_manager.status != models.UserStatus.ACTIVE
                or expected_manager.kindergarten_id != expected_kg.id
                or expected_manager.deleted_at is not None
            ):
                raise RuntimeError(
                    f"Refusing to activate seeded kindergarten: {username} is not its active manager"
                )

        kg1.status = models.KindergartenStatus.ACTIVE
        kg2.status = models.KindergartenStatus.ACTIVE
        db.commit()

        supervisor1 = db.query(models.User).filter(models.User.username == "supervisor1").first()
        if not supervisor1:
            supervisor1 = create_user(
                db=db,
                username="supervisor1",
                email="supervisor1@kinjo.com",
                password=_seed_password("SEED_SUPERVISOR_PASSWORD"),
                role=models.UserRole.SUPERVISOR,
                kindergarten_id=kg1.id
            )
            print(f"   [+] Supervisor (Al Amal): supervisor1")
        else:
            print(f"   [*] supervisor1 already exists")

        supervisor2 = db.query(models.User).filter(models.User.username == "supervisor2").first()
        if not supervisor2:
            supervisor2 = create_user(
                db=db,
                username="supervisor2",
                email="supervisor2@kinjo.com",
                password=_seed_password("SEED_SUPERVISOR_PASSWORD"),
                role=models.UserRole.SUPERVISOR,
                kindergarten_id=kg2.id
            )
            print(f"   [+] Supervisor (Al Noor): supervisor2")
        else:
            print(f"   [*] supervisor2 already exists")

        parent = db.query(models.User).filter(models.User.username == "parent1@example.com").first()
        if not parent:
            parent = create_user(
                db=db,
                username="parent1@example.com",
                email="parent1@example.com",
                password=_seed_password("SEED_PARENT_PASSWORD"),
                role=models.UserRole.PARENT
            )

            # Create parent profile
            parent_profile = models.ParentProfile(
                user_id=parent.id,
                first_name="Ahmad",
                last_name="Al-Rashid",
                phone_number="+962791234567",
                gender=models.Gender.MALE,
                nationality="Jordanian",
                national_id="1234567890",
                home_governorate="Amman",
                home_district="Amman",
                home_area="Abdoun",
                home_address_line="Street 123"
            )
            db.add(parent_profile)
            print(f"   [+] Parent: parent1@example.com")
        else:
            print(f"   [*] parent1@example.com already exists")

        db.commit()

        # ============================================================================
        # 3. Create Sample Tasks
        # ============================================================================
        print("\n📝 Creating sample tasks...")

        tasks_data = [
            # Admin tasks
            {
                "title": "Review monthly KPI reports",
                "description": "Analyze attendance rates, incident reports, and governance scores for all kindergartens",
                "status": models.TaskStatus.PENDING,
                "priority": models.TaskPriority.HIGH,
                "created_by_id": admin.id,
                "assigned_to_id": admin.id,
                "due_date": datetime.now() + timedelta(days=2)
            },
            {
                "title": "Update system documentation",
                "description": "Review and update API documentation and user guides",
                "status": models.TaskStatus.IN_PROGRESS,
                "priority": models.TaskPriority.MEDIUM,
                "created_by_id": admin.id,
                "assigned_to_id": admin.id,
                "due_date": datetime.now() + timedelta(days=7)
            },
            {
                "title": "Complete security audit",
                "description": "Conducted comprehensive security review of all modules",
                "status": models.TaskStatus.COMPLETED,
                "priority": models.TaskPriority.URGENT,
                "created_by_id": admin.id,
                "assigned_to_id": admin.id,
                "completed_at": datetime.now() - timedelta(days=1)
            },

            # Manager 1 tasks (Al Amal)
            {
                "title": "Review pending enrollment applications",
                "description": "Process 5 pending enrollment applications for next semester",
                "status": models.TaskStatus.PENDING,
                "priority": models.TaskPriority.URGENT,
                "created_by_id": manager1.id,
                "assigned_to_id": manager1.id,
                "kindergarten_id": kg1.id,
                "due_date": datetime.now() + timedelta(days=1)
            },
            {
                "title": "Schedule parent-teacher meetings",
                "description": "Coordinate with supervisors to schedule monthly parent-teacher meetings",
                "status": models.TaskStatus.IN_PROGRESS,
                "priority": models.TaskPriority.MEDIUM,
                "created_by_id": manager1.id,
                "assigned_to_id": supervisor1.id,
                "kindergarten_id": kg1.id,
                "due_date": datetime.now() + timedelta(days=5)
            },
            {
                "title": "Approve daily reports for last week",
                "description": "Review and approve all pending daily reports",
                "status": models.TaskStatus.COMPLETED,
                "priority": models.TaskPriority.HIGH,
                "created_by_id": manager1.id,
                "assigned_to_id": manager1.id,
                "kindergarten_id": kg1.id,
                "completed_at": datetime.now() - timedelta(hours=12)
            },

            # Manager 2 tasks (Al Noor)
            {
                "title": "Prepare for licensing renewal",
                "description": "Gather all required documentation for kindergarten license renewal",
                "status": models.TaskStatus.PENDING,
                "priority": models.TaskPriority.URGENT,
                "created_by_id": manager2.id,
                "assigned_to_id": manager2.id,
                "kindergarten_id": kg2.id,
                "due_date": datetime.now() + timedelta(days=3)
            },
            {
                "title": "Review incident reports",
                "description": "Analyze incident trends and implement preventive measures",
                "status": models.TaskStatus.IN_PROGRESS,
                "priority": models.TaskPriority.HIGH,
                "created_by_id": manager2.id,
                "assigned_to_id": manager2.id,
                "kindergarten_id": kg2.id,
                "due_date": datetime.now() + timedelta(days=4)
            },

            # Supervisor 1 tasks (Al Amal)
            {
                "title": "Complete observation records for Class A",
                "description": "Document developmental observations for all children in Class A",
                "status": models.TaskStatus.PENDING,
                "priority": models.TaskPriority.MEDIUM,
                "created_by_id": supervisor1.id,
                "assigned_to_id": supervisor1.id,
                "kindergarten_id": kg1.id,
                "due_date": datetime.now() + timedelta(days=3)
            },
            {
                "title": "Prepare weekly activity plan",
                "description": "Plan educational activities for next week",
                "status": models.TaskStatus.IN_PROGRESS,
                "priority": models.TaskPriority.MEDIUM,
                "created_by_id": supervisor1.id,
                "assigned_to_id": supervisor1.id,
                "kindergarten_id": kg1.id,
                "due_date": datetime.now() + timedelta(days=2)
            },
            {
                "title": "Update health alerts for children with allergies",
                "description": "Review and update allergy information for all children",
                "status": models.TaskStatus.COMPLETED,
                "priority": models.TaskPriority.HIGH,
                "created_by_id": supervisor1.id,
                "assigned_to_id": supervisor1.id,
                "kindergarten_id": kg1.id,
                "completed_at": datetime.now() - timedelta(days=2)
            },

            # Supervisor 2 tasks (Al Noor)
            {
                "title": "Organize field trip to science museum",
                "description": "Coordinate transportation, permissions, and supervision for field trip",
                "status": models.TaskStatus.PENDING,
                "priority": models.TaskPriority.LOW,
                "created_by_id": supervisor2.id,
                "assigned_to_id": supervisor2.id,
                "kindergarten_id": kg2.id,
                "due_date": datetime.now() + timedelta(days=14)
            },
            {
                "title": "Create daily reports for this week",
                "description": "Complete and submit all daily reports for supervisor review",
                "status": models.TaskStatus.IN_PROGRESS,
                "priority": models.TaskPriority.HIGH,
                "created_by_id": supervisor2.id,
                "assigned_to_id": supervisor2.id,
                "kindergarten_id": kg2.id,
                "due_date": datetime.now() + timedelta(days=1)
            },

            # Parent tasks
            {
                "title": "Submit medical documents",
                "description": "Upload vaccination records and health certificate for enrollment",
                "status": models.TaskStatus.PENDING,
                "priority": models.TaskPriority.URGENT,
                "created_by_id": parent.id,
                "assigned_to_id": parent.id,
                "due_date": datetime.now() + timedelta(days=5)
            },
            {
                "title": "Review and sign consent forms",
                "description": "Sign media consent and field trip permission forms",
                "status": models.TaskStatus.PENDING,
                "priority": models.TaskPriority.MEDIUM,
                "created_by_id": parent.id,
                "assigned_to_id": parent.id,
                "due_date": datetime.now() + timedelta(days=7)
            },

            # Cross-assigned tasks
            {
                "title": "Prepare monthly newsletter",
                "description": "Create newsletter with updates, events, and announcements",
                "status": models.TaskStatus.PENDING,
                "priority": models.TaskPriority.LOW,
                "created_by_id": manager1.id,
                "assigned_to_id": supervisor1.id,
                "kindergarten_id": kg1.id,
                "due_date": datetime.now() + timedelta(days=10)
            },
            {
                "title": "Inventory check for educational materials",
                "description": "Count and report on all educational materials and supplies",
                "status": models.TaskStatus.PENDING,
                "priority": models.TaskPriority.MEDIUM,
                "created_by_id": manager2.id,
                "assigned_to_id": supervisor2.id,
                "kindergarten_id": kg2.id,
                "due_date": datetime.now() + timedelta(days=6)
            },

            # Overdue tasks
            {
                "title": "OVERDUE: Update emergency contact information",
                "description": "Verify and update emergency contacts for all enrolled children",
                "status": models.TaskStatus.PENDING,
                "priority": models.TaskPriority.URGENT,
                "created_by_id": manager1.id,
                "assigned_to_id": manager1.id,
                "kindergarten_id": kg1.id,
                "due_date": datetime.now() - timedelta(days=2)  # Overdue
            },
        ]

        for task_data in tasks_data:
            task = models.Task(**task_data)
            db.add(task)

        db.commit()
        print(f"   ✅ Created {len(tasks_data)} sample tasks")

        # ============================================================================
        # Summary
        # ============================================================================
        print("\n" + "="*60)
        print("✅ SEED DATA CREATED SUCCESSFULLY!")
        print("="*60)

        print("\n📊 Summary:")
        print(f"   • Kindergartens: 2")
        print(f"   • Users: 6 (1 admin, 2 managers, 2 supervisors, 1 parent)")
        print(f"   • Tasks: {len(tasks_data)}")

        print("\n👤 Test Credentials (passwords set via SEED_*_PASSWORD env vars):")
        print("   ┌─────────────┬─────────────────────┐")
        print("   │ Role        │ Username            │")
        print("   ├─────────────┼─────────────────────┤")
        print("   │ Admin       │ admin               │")
        print("   │ Manager     │ manager1            │")
        print("   │ Manager     │ manager2            │")
        print("   │ Supervisor  │ supervisor1         │")
        print("   │ Supervisor  │ supervisor2         │")
        print("   │ Parent      │ parent1@example.com │")
        print("   └─────────────┴─────────────────────┘")

        print("\n🎯 Task Statistics by Status:")
        pending = sum(1 for t in tasks_data if t["status"] == models.TaskStatus.PENDING)
        in_progress = sum(1 for t in tasks_data if t["status"] == models.TaskStatus.IN_PROGRESS)
        completed = sum(1 for t in tasks_data if t["status"] == models.TaskStatus.COMPLETED)
        print(f"   • Pending: {pending}")
        print(f"   • In Progress: {in_progress}")
        print(f"   • Completed: {completed}")

        print("\n🔥 Task Statistics by Priority:")
        urgent = sum(1 for t in tasks_data if t["priority"] == models.TaskPriority.URGENT)
        high = sum(1 for t in tasks_data if t["priority"] == models.TaskPriority.HIGH)
        medium = sum(1 for t in tasks_data if t["priority"] == models.TaskPriority.MEDIUM)
        low = sum(1 for t in tasks_data if t["priority"] == models.TaskPriority.LOW)
        print(f"   • Urgent: {urgent}")
        print(f"   • High: {high}")
        print(f"   • Medium: {medium}")
        print(f"   • Low: {low}")

        print("\n🌐 Access the application:")
        print("   → http://127.0.0.1:8000")
        print("   → API Docs: http://127.0.0.1:8000/docs")
        print("   → Tasks Page: http://127.0.0.1:8000/tasks")

        print("\n" + "="*60)

    except (RuntimeError, ValueError, TypeError, AttributeError, OSError) as e:
        print(f"\n❌ Error: {e}")
        db.rollback()
        raise
    finally:
        db.close()


if __name__ == "__main__":
    # Initialize database first
    print("[*] Initializing database...")
    init_db()

    # Seed data
    seed_tasks()
