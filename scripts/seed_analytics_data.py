"""
Seed Analytics Data Script
Generates sample data for testing the analytics module
"""
import random
from datetime import date, datetime, timedelta
from sqlalchemy.orm import Session

from database import SessionLocal, engine
from child_age_policy import get_child_age_bounds
from models import (
    Base, User, UserRole, UserStatus, Kindergarten, KindergartenStatus,
    Child, Class, EnrollmentApplication, EnrollmentStatus, AttendanceLog,
    DailyReport, DailyReportStatus, Incident, IncidentType, SeverityLevel,
    RatioCompliance, GovernanceScore, ParentProfile, Gender, AttendanceMethod
)
from auth import get_password_hash

# Jordan governorates
GOVERNORATES = [
    "عمان", "إربد", "الزرقاء", "العقبة", "المفرق",
    "جرش", "عجلون", "الطفيلة", "الكرك", "معان", "البلقاء", "مادبا"
]

# Arabic first names
FIRST_NAMES_MALE = ["أحمد", "محمد", "عمر", "خالد", "يوسف", "علي", "حسن", "سامي", "زيد", "ياسر"]
FIRST_NAMES_FEMALE = ["فاطمة", "ريم", "سارة", "نور", "هبة", "لينا", "مريم", "رنا", "دانا", "ليلى"]
LAST_NAMES = ["الخطيب", "العمري", "الحسن", "النجار", "الصالح", "القاسم", "المصري", "الزعبي", "الطراونة", "الشمايلة"]

# Kindergarten names
KG_NAMES = [
    "روضة الأمل", "روضة النور", "روضة الزهور", "روضة الربيع", "روضة السعادة",
    "روضة الحنان", "روضة الأطفال", "روضة المستقبل", "روضة الإبداع", "روضة النجاح",
    "روضة الورود", "روضة القمر", "روضة الشمس", "روضة النجمة", "روضة الحب"
]

KG_NAMES_EN = [
    "Hope Kindergarten", "Light Kindergarten", "Flowers Kindergarten", "Spring Kindergarten", "Happiness Kindergarten",
    "Tenderness Kindergarten", "Children Kindergarten", "Future Kindergarten", "Creativity Kindergarten", "Success Kindergarten",
    "Roses Kindergarten", "Moon Kindergarten", "Sun Kindergarten", "Star Kindergarten", "Love Kindergarten"
]

# Cities and areas by governorate
CITIES = {
    "عمان": ["عمان", "الجبيهة", "القويسمة", "وادي السير", "المدينة الرياضية"],
    "إربد": ["إربد", "الحصن", "الرمثا", "الكورة", "بني كنانة"],
    "الزرقاء": ["الزرقاء", "الرصيفة", "الهاشمية", "الأزرق"],
    "العقبة": ["العقبة", "وادي رم"],
    "المفرق": ["المفرق", "الرصيفة", "البادية الشمالية"],
    "الطفيلة": ["الطفيلة", "بصيرا", "الحسا"],
    "الكرك": ["الكرك", "قصبة الكرك", "عي", "القصر"],
    "مادبا": ["مادبا", "ذيبان", "الجفر"],
    "جرش": ["جرش", "سوف", "الكفارات"],
    "عجلون": ["عجلون", "صخرة", "عنجرة"],
    "البلقاء": ["السلط", "عين الباشا", "دير علا"],
    "معان": ["معان", "الشوبك", "الطيبة", "وادي موسى"]
}

AREAS = {
    "عمان": ["وسط البلد", "الشميساني", "الدوار السابع", "المدينة الطبية", "الصويفية"],
    "إربد": ["وسط المدينة", "الحصن", "الرمثا", "الكورة"],
    "الزرقاء": ["وسط المدينة", "الرصيفة", "الهاشمية"],
    "العقبة": ["وسط المدينة", "وادي رم"],
    "المفرق": ["وسط المدينة", "الرصيفة"],
    "الطفيلة": ["وسط المدينة", "بصيرا"],
    "الكرك": ["وسط المدينة", "قصبة الكرك"],
    "مادبا": ["وسط المدينة", "ذيبان"],
    "جرش": ["وسط المدينة", "سوف"],
    "عجلون": ["وسط المدينة", "صخرة"],
    "البلقاء": ["وسط المدينة", "عين الباشا"],
    "معان": ["وسط المدينة", "الشوبك"]
}


def create_admin_user(db: Session) -> User:
    """Create admin user if not exists"""
    admin = db.query(User).filter(User.username == "admin").first()
    if not admin:
        admin = User(
            username="admin",
            email="admin@kinjo.jo",
            hashed_password=get_password_hash("admin123"),
            role=UserRole.ADMIN,
            status=UserStatus.ACTIVE
        )
        db.add(admin)
        db.commit()
        db.refresh(admin)
        print(f"Created admin user: admin / admin123")
    return admin


def create_kindergartens(db: Session, count: int = 15) -> list:
    """Create sample kindergartens"""
    kindergartens = []

    for i in range(count):
        governorate = random.choice(GOVERNORATES)
        name_ar = f"{random.choice(KG_NAMES)} - {governorate}"
        name_en = f"{random.choice(KG_NAMES_EN)} - {governorate}"

        kg = Kindergarten(
            name_ar=name_ar,
            name_en=name_en,
            governorate=governorate,
            city=random.choice(CITIES.get(governorate, ["عمان"])),
            area=random.choice(AREAS.get(governorate, ["وسط البلد"])),
            address_line=f"شارع {random.randint(1, 100)}، {governorate}",
            contact_phone=f"07{random.randint(70000000, 99999999)}",
            contact_email=f"kg{i+1}@kinjo.jo",
            status=KindergartenStatus.ACTIVE,
            license_number=f"MOE-{2024}-{random.randint(1000, 9999)}",
            license_valid_until=date.today() + timedelta(days=random.randint(180, 730))
        )
        db.add(kg)
        kindergartens.append(kg)

    db.commit()
    print(f"Created {len(kindergartens)} kindergartens")
    return kindergartens


def create_staff(db: Session, kindergartens: list) -> list:
    """Create staff (managers and supervisors) for kindergartens"""
    staff = []

    for kg in kindergartens:
        # Create manager
        manager = User(
            username=f"manager_kg{kg.id}",
            email=f"manager{kg.id}@kinjo.jo",
            hashed_password=get_password_hash("manager123"),
            role=UserRole.MANAGER,
            status=UserStatus.ACTIVE,
            kindergarten_id=kg.id
        )
        db.add(manager)
        staff.append(manager)

        # Create 2-4 supervisors
        for j in range(random.randint(2, 4)):
            supervisor = User(
                username=f"supervisor_kg{kg.id}_{j+1}",
                email=f"supervisor{kg.id}_{j+1}@kinjo.jo",
                hashed_password=get_password_hash("supervisor123"),
                role=UserRole.SUPERVISOR,
                status=UserStatus.ACTIVE,
                kindergarten_id=kg.id
            )
            db.add(supervisor)
            staff.append(supervisor)

    db.commit()
    print(f"Created {len(staff)} staff members")
    return staff


def create_classes(db: Session, kindergartens: list) -> list:
    """Create classes for each kindergarten"""
    classes = []
    # Age groups with min/max age in months
    age_groups = [
        {"name_ar": "3-4 سنوات", "name_en": "3-4 years", "min_age": 36, "max_age": 48},
        {"name_ar": "4-5 سنوات", "name_en": "4-5 years", "min_age": 48, "max_age": 60},
        {"name_ar": "5-6 سنوات", "name_en": "5-6 years", "min_age": 60, "max_age": 72},
    ]

    for kg in kindergartens:
        for i, age_group in enumerate(age_groups):
            for section in ["أ", "ب"]:
                cls = Class(
                    kindergarten_id=kg.id,
                    name_ar=f"الصف {i+1}{section} - {age_group['name_ar']}",
                    name_en=f"Class {i+1}{section} - {age_group['name_en']}",
                    min_age_months=age_group['min_age'],
                    max_age_months=age_group['max_age'],
                    capacity_total=random.randint(15, 25)
                )
                db.add(cls)
                classes.append(cls)

    db.commit()
    print(f"Created {len(classes)} classes")
    return classes


def create_children_and_enrollments(db: Session, kindergartens: list, classes: list) -> tuple:
    """Create children and their enrollments"""
    children = []
    enrollments = []

    # Group classes by kindergarten
    kg_classes = {}
    for cls in classes:
        if cls.kindergarten_id not in kg_classes:
            kg_classes[cls.kindergarten_id] = []
        kg_classes[cls.kindergarten_id].append(cls)

    # Create parent users and profiles first
    parent_profiles = []
    for i in range(100):
        is_male = random.random() < 0.5
        first_name = random.choice(FIRST_NAMES_MALE if is_male else FIRST_NAMES_FEMALE)
        last_name = random.choice(LAST_NAMES)
        governorate = random.choice(GOVERNORATES)

        # Create user
        user = User(
            username=f"parent_{i+1}",
            email=f"parent{i+1}@example.com",
            hashed_password=get_password_hash("parent123"),
            role=UserRole.PARENT,
            status=UserStatus.ACTIVE
        )
        db.add(user)
        db.flush()  # Get the user ID

        # Create parent profile
        profile = ParentProfile(
            user_id=user.id,
            first_name=first_name,
            last_name=last_name,
            phone_number=f"+96279{random.randint(1000000, 9999999)}",
            gender=Gender.MALE if is_male else Gender.FEMALE,
            nationality="Jordanian",
            national_id=f"{random.randint(1000000000, 9999999999)}",
            home_governorate=governorate,
            home_district=random.choice(CITIES.get(governorate, ["عمان"])),
            home_area=random.choice(AREAS.get(governorate, ["وسط المدينة"])),
            home_address_line=f"شارع {random.randint(1, 100)}"
        )
        db.add(profile)
        parent_profiles.append(profile)
    db.commit()

    # Refresh to get IDs
    for profile in parent_profiles:
        db.refresh(profile)

    # Create children for each kindergarten
    child_id = 0
    for kg in kindergartens:
        kg_cls_list = kg_classes.get(kg.id, [])
        if not kg_cls_list:
            continue

        # Create 30-80 children per kindergarten
        # Calculate capacity from classes
        kg_capacity = sum(cls.capacity_total for cls in kg_cls_list) if kg_cls_list else 60
        num_children = random.randint(30, min(80, kg_capacity))

        for i in range(num_children):
            is_male = random.random() < 0.5
            first_name = random.choice(FIRST_NAMES_MALE if is_male else FIRST_NAMES_FEMALE)
            last_name = random.choice(LAST_NAMES)
            father_name = f"{random.choice(FIRST_NAMES_MALE)} {random.choice(LAST_NAMES)}"
            mother_first = random.choice(FIRST_NAMES_FEMALE)
            mother_last = random.choice(LAST_NAMES)

            bounds = get_child_age_bounds(date.today())
            delta_days = (bounds.max_date - bounds.min_date).days
            random_offset = random.randint(0, max(delta_days, 0))
            birth_date = bounds.min_date + timedelta(days=random_offset)

            parent_profile = random.choice(parent_profiles)

            child = Child(
                parent_id=parent_profile.id,
                first_name=first_name,
                last_name=last_name,
                gender=Gender.MALE if is_male else Gender.FEMALE,
                date_of_birth=birth_date,
                father_name=father_name,
                mother_first_name=mother_first,
                mother_last_name=mother_last,
                mother_nationality="Jordanian",
                mother_national_id=f"{random.randint(1000000000, 9999999999)}",
                media_consent=random.choice([True, False]),
                correspondence_flag=True
            )
            db.add(child)
            children.append(child)
            child_id += 1

    db.commit()

    # Create enrollments
    for child in children:
        # Find a random kindergarten and class
        kg = random.choice(kindergartens)
        kg_cls_list = kg_classes.get(kg.id, [])
        if not kg_cls_list:
            continue

        cls = random.choice(kg_cls_list)

        # Determine status (mostly active)
        status_weights = [
            (EnrollmentStatus.ACTIVE, 0.7),
            (EnrollmentStatus.SUBMITTED, 0.1),
            (EnrollmentStatus.ACCEPTED, 0.1),
            (EnrollmentStatus.WITHDRAWN, 0.05),
            (EnrollmentStatus.REJECTED, 0.05)
        ]
        status = random.choices(
            [s for s, _ in status_weights],
            weights=[w for _, w in status_weights]
        )[0]

        submitted_date = datetime.now() - timedelta(days=random.randint(30, 365))
        enrollment = EnrollmentApplication(
            child_id=child.id,
            kindergarten_id=kg.id,
            class_id=cls.id,
            status=status,
            submitted_at=submitted_date
        )
        db.add(enrollment)
        enrollments.append(enrollment)

    db.commit()
    print(f"Created {len(children)} children and {len(enrollments)} enrollments")
    return children, enrollments


def create_attendance_logs(db: Session, enrollments: list, days: int = 60) -> list:
    """Create attendance logs for the past N days"""
    logs = []
    today = date.today()

    active_enrollments = [e for e in enrollments if e.status == EnrollmentStatus.ACTIVE]

    for day_offset in range(days):
        log_date = today - timedelta(days=day_offset)

        # Skip weekends (Friday/Saturday in Jordan)
        if log_date.weekday() in [4, 5]:
            continue

        for enrollment in active_enrollments:
            # 85% attendance rate on average
            if random.random() < 0.85:
                check_in_at = datetime.combine(log_date, datetime.min.time()) + timedelta(hours=7, minutes=random.randint(30, 90))
                check_out_at = datetime.combine(log_date, datetime.min.time()) + timedelta(hours=13, minutes=random.randint(0, 60))

                log = AttendanceLog(
                    child_id=enrollment.child_id,
                    date=log_date,
                    check_in_at=check_in_at,
                    check_out_at=check_out_at,
                    method=random.choice([AttendanceMethod.PIN, AttendanceMethod.QR, AttendanceMethod.KIOSK, AttendanceMethod.MANUAL])
                )
                db.add(log)
                logs.append(log)

        # Commit in batches to avoid memory issues
        if day_offset % 10 == 0:
            db.commit()

    db.commit()
    print(f"Created {len(logs)} attendance logs")
    return logs


def create_daily_reports(db: Session, enrollments: list, staff: list, days: int = 30) -> list:
    """Create daily reports for active children"""
    reports = []
    today = date.today()

    active_enrollments = [e for e in enrollments if e.status == EnrollmentStatus.ACTIVE]
    supervisor_ids = [s.id for s in staff if s.role in [UserRole.SUPERVISOR, UserRole.MANAGER]]
    if not supervisor_ids:
        print("No supervisors found for daily reports")
        return reports

    activities_list = ["لعب حر", "قراءة قصة", "رسم", "موسيقى", "رياضة", "ألعاب تعليمية"]

    for day_offset in range(days):
        report_date = today - timedelta(days=day_offset)

        if report_date.weekday() in [4, 5]:
            continue

        for enrollment in random.sample(active_enrollments, int(len(active_enrollments) * 0.8)):
            status = random.choice([DailyReportStatus.SUBMITTED, DailyReportStatus.DRAFT, DailyReportStatus.APPROVED, DailyReportStatus.RETURNED])
            arrival_hour = random.randint(7, 8)
            arrival_min = random.randint(0, 59)
            leave_hour = random.randint(12, 14)
            leave_min = random.randint(0, 59)
            nap_start_h = random.randint(11, 12)
            nap_end_h = nap_start_h + 1

            report = DailyReport(
                child_id=enrollment.child_id,
                date=report_date,
                status=status,
                submitted_by=random.choice(supervisor_ids),
                arrival_time=f"{arrival_hour:02d}:{arrival_min:02d}",
                leave_time=f"{leave_hour:02d}:{leave_min:02d}",
                breakfast=random.choice([True, False]),
                snack=random.choice([True, False]),
                milk=random.choice([True, False]),
                lunch=random.choice([True, False]),
                nap_start=f"{nap_start_h:02d}:00",
                nap_end=f"{nap_end_h:02d}:00",
                nap_duration_minutes=60,
                activities=", ".join(random.sample(activities_list, random.randint(2, 4))),
                notes="لا توجد ملاحظات خاصة" if random.random() > 0.2 else "يحتاج متابعة"
            )
            db.add(report)
            reports.append(report)

        if day_offset % 10 == 0:
            db.commit()

    db.commit()
    print(f"Created {len(reports)} daily reports")
    return reports


def create_incidents(db: Session, kindergartens: list, enrollments: list, days: int = 90) -> list:
    """Create incident reports"""
    incidents = []
    today = date.today()

    active_enrollments = [e for e in enrollments if e.status == EnrollmentStatus.ACTIVE]

    for day_offset in range(days):
        incident_date = today - timedelta(days=day_offset)

        # Average 0.5 incidents per kindergarten per day
        for kg in kindergartens:
            if random.random() < 0.5:
                kg_enrollments = [e for e in active_enrollments if e.kindergarten_id == kg.id]
                if not kg_enrollments:
                    continue

                enrollment = random.choice(kg_enrollments)

                severity_weights = [
                    (SeverityLevel.LOW, 0.5),
                    (SeverityLevel.MEDIUM, 0.35),
                    (SeverityLevel.HIGH, 0.12),
                    (SeverityLevel.CRITICAL, 0.03)
                ]
                severity = random.choices(
                    [s for s, _ in severity_weights],
                    weights=[w for _, w in severity_weights]
                )[0]

                incident_type = random.choice(list(IncidentType))

                occurred_at = datetime.combine(incident_date, datetime.min.time()) + timedelta(hours=random.randint(8, 12))

                incident = Incident(
                    child_id=enrollment.child_id,
                    kindergarten_id=kg.id,
                    type=incident_type,
                    severity_level=severity,
                    description=f"حادث من نوع {incident_type.value}",
                    occurred_at=occurred_at,
                    followup_required_flag=severity in [SeverityLevel.HIGH, SeverityLevel.CRITICAL],
                    closed_at=occurred_at + timedelta(hours=random.randint(1, 48)) if random.random() > 0.2 else None
                )
                db.add(incident)
                incidents.append(incident)

    db.commit()
    print(f"Created {len(incidents)} incidents")
    return incidents


def create_ratio_compliance(db: Session, kindergartens: list, days: int = 60) -> list:
    """Create ratio compliance records"""
    records = []
    today = date.today()

    for day_offset in range(days):
        record_date = today - timedelta(days=day_offset)

        if record_date.weekday() in [4, 5]:
            continue

        for kg in kindergartens:
            operating_minutes = random.randint(300, 360)  # 5-6 hours
            compliance_rate = random.uniform(0.75, 0.98)
            compliant_minutes = int(operating_minutes * compliance_rate)

            record = RatioCompliance(
                kindergarten_id=kg.id,
                date=record_date,
                operating_minutes=operating_minutes,
                compliant_minutes=compliant_minutes,
                staff_count_avg=random.uniform(3, 6),
                child_count_avg=random.uniform(20, 50)
            )
            db.add(record)
            records.append(record)

        if day_offset % 10 == 0:
            db.commit()

    db.commit()
    print(f"Created {len(records)} ratio compliance records")
    return records


def create_governance_scores(db: Session, kindergartens: list) -> list:
    """Create monthly governance scores"""
    scores = []
    today = date.today()

    for month_offset in range(6):  # Last 6 months
        period_start = (today.replace(day=1) - timedelta(days=month_offset * 30)).replace(day=1)
        if period_start.month == 12:
            period_end = date(period_start.year + 1, 1, 1) - timedelta(days=1)
        else:
            period_end = date(period_start.year, period_start.month + 1, 1) - timedelta(days=1)

        for kg in kindergartens:
            gqi = random.uniform(60, 95)
            cei = random.uniform(65, 98)
            final_score = gqi * 0.6 + cei * 0.4

            if final_score >= 80:
                band = "GREEN"
            elif final_score >= 60:
                band = "AMBER"
            else:
                band = "RED"

            score = GovernanceScore(
                kindergarten_id=kg.id,
                period_start=period_start,
                period_end=period_end,
                governance_quality_index=round(gqi, 2),
                child_experience_index=round(cei, 2),
                final_governance_score=round(final_score, 2),
                band=band
            )
            db.add(score)
            scores.append(score)

    db.commit()
    print(f"Created {len(scores)} governance scores")
    return scores


def seed_all():
    """Main function to seed all analytics data"""
    print("=" * 50)
    print("Starting Analytics Data Seeding...")
    print("=" * 50)

    # Create all tables
    Base.metadata.create_all(bind=engine)

    db = SessionLocal()

    try:
        # Check if data already exists
        existing_kg = db.query(Kindergarten).count()
        if existing_kg > 5:
            print(f"Database already has {existing_kg} kindergartens. Skipping seed.")
            return

        # Create data
        admin = create_admin_user(db)
        kindergartens = create_kindergartens(db, count=15)
        staff = create_staff(db, kindergartens)
        classes = create_classes(db, kindergartens)
        children, enrollments = create_children_and_enrollments(db, kindergartens, classes)
        attendance_logs = create_attendance_logs(db, enrollments, days=60)
        daily_reports = create_daily_reports(db, enrollments, staff, days=30)
        incidents = create_incidents(db, kindergartens, enrollments, days=90)
        ratio_compliance = create_ratio_compliance(db, kindergartens, days=60)
        governance_scores = create_governance_scores(db, kindergartens)

        print("=" * 50)
        print("Seeding Complete!")
        print("=" * 50)
        print(f"Admin login: admin / admin123")
        print(f"Manager login: manager_kg1 / manager123")
        print(f"Supervisor login: supervisor_kg1_1 / supervisor123")
        print(f"Parent login: parent_1 / parent123")

    except (RuntimeError, ValueError, TypeError, AttributeError, OSError) as e:
        print(f"Error during seeding: {e}")
        db.rollback()
        raise
    finally:
        db.close()


if __name__ == "__main__":
    seed_all()
