"""
Comprehensive Admin Module Seed Data Generator
==============================================
Generates deterministic, realistic, and complete test data covering ALL admin
module features, metrics, filters, and edge cases across the Jordanian
kindergarten network.

Covers:
  - 12 Jordanian Governorates (Amman, Irbid, Zarqa, Balqa, Madaba, Mafraq, Jerash, Ajloun, Karak, Tafilah, Ma'an, Aqaba)
  - Kindergarten statuses: ACTIVE, DRAFT, FROZEN, INACTIVE
  - Quality tiers, capacity levels, and license expiry edge cases
  - User roles & credentials: Admin, Managers, Supervisors (with active assignments), Parents, Staff
  - Classrooms across age groups (Infants, Toddlers, KG1, KG2 eligibility)
  - Enrollment applications across ALL 7 funnel statuses (DRAFT, SUBMITTED, PENDING_REVIEW, ACCEPTED, REJECTED, ACTIVE, WITHDRAWN, WAITLISTED) and sources (WEB, MOBILE, OFFICE)
  - 90-day time-series attendance records (PRESENT, ABSENT, EXCUSED, LATE) with realistic baselines and injected anomalies
  - Daily reports with all canonical moods (HAPPY, CALM, ENERGETIC, TIRED, FUSSY, SAD) and statuses
  - Safety incidents across all severities (LOW, MEDIUM, HIGH, CRITICAL) and types
  - Ratio compliance snapshots & Governance scores (Bands A, B, C)
  - Scheduled chart exports (DAILY, WEEKLY, MONTHLY)
  - Audit logs across varied admin and user actions

Usage:
  python scripts/seed_admin_module.py           # Seed without wiping existing data
  python scripts/seed_admin_module.py --force   # Clean wipe and fresh re-seed
"""

from __future__ import annotations

import os
import sys
import uuid
import random
from datetime import date, datetime, timedelta, timezone
from pathlib import Path

# Ensure project root is on sys.path
ROOT = str(Path(__file__).resolve().parent.parent)
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

from sqlalchemy.orm import Session
from database import SessionLocal, engine, init_db
import models
from auth import get_password_hash
from child_age_policy import get_child_age_bounds

# ─────────────────────────────────────────────────────────────────────────────
# Configuration & Credentials
# ─────────────────────────────────────────────────────────────────────────────
DEFAULT_PASSWORD = "Test@1234"
ADMIN_PASSWORD = os.environ.get("SEED_ADMIN_PASSWORD", "Admin@1234")
MANAGER_PASSWORD = os.environ.get("SEED_MANAGER_PASSWORD", "Manager@1234")
SUPERVISOR_PASSWORD = os.environ.get("SEED_SUPERVISOR_PASSWORD", "Super@1234")
PARENT_PASSWORD = os.environ.get("SEED_PARENT_PASSWORD", "Parent@1234")

GOVERNORATES = [
    "عمان", "إربد", "الزرقاء", "البلقاء", "مادبا", "المفرق",
    "جرش", "عجلون", "الكرك", "الطفيلة", "معان", "العقبة"
]

TODAY = date.today()
NOW = datetime.now(timezone.utc)


def dt(d: date, hour: int = 8, minute: int = 0) -> datetime:
    return datetime(d.year, d.month, d.day, hour, minute, tzinfo=timezone.utc)


def past(days: int) -> date:
    return TODAY - timedelta(days=days)


def future(days: int) -> date:
    return TODAY + timedelta(days=days)


def is_workday(d: date) -> bool:
    return d.weekday() not in (4, 5)  # Friday (4) and Saturday (5) are weekend in Jordan


# ─────────────────────────────────────────────────────────────────────────────
# Seed Logic
# ─────────────────────────────────────────────────────────────────────────────
def seed_admin_module(db: Session, force: bool = False) -> dict:
    print("\n" + "=" * 65)
    print("  [KINJO ADMIN SEED] Starting comprehensive data generation ...")
    print("=" * 65 + "\n")

    summary = {}

    # 1. Platform Administrator
    admin = db.query(models.User).filter(models.User.username == "admin").first()
    if not admin:
        admin = models.User(
            username="admin",
            email="admin@kinjo.jo",
            hashed_password=get_password_hash(ADMIN_PASSWORD),
            role=models.UserRole.ADMIN,
            status=models.UserStatus.ACTIVE,
            public_id=str(uuid.uuid4()),
            failed_login_count=0,
            must_change_password=False,
            mfa_enabled=False,
        )
        db.add(admin)
        db.flush()
        print("  [+] Created Platform Admin: admin / " + ADMIN_PASSWORD)
    else:
        admin.hashed_password = get_password_hash(ADMIN_PASSWORD)
        admin.status = models.UserStatus.ACTIVE
        db.flush()

    # 2. Regional Supervisors (Covering North, Central, and South regions)
    supervisors_data = [
        ("supervisor_amman", "supervisor.amman@kinjo.jo", "أحمد الشريف", "عمان"),
        ("supervisor_irbid", "supervisor.irbid@kinjo.jo", "محمود عبيدات", "إربد"),
        ("supervisor_zarqa", "supervisor.zarqa@kinjo.jo", "عمر الزعبي", "الزرقاء"),
        ("supervisor_south", "supervisor.south@kinjo.jo", "خالد الطراونة", "الكرك"),
        ("supervisor_aqaba", "supervisor.aqaba@kinjo.jo", "يوسف المجالي", "العقبة"),
    ]
    supervisors = []
    for username, email, full_name, gov in supervisors_data:
        sup = db.query(models.User).filter(models.User.username == username).first()
        if not sup:
            sup = models.User(
                username=username,
                email=email,
                hashed_password=get_password_hash(SUPERVISOR_PASSWORD),
                role=models.UserRole.SUPERVISOR,
                status=models.UserStatus.ACTIVE,
                public_id=str(uuid.uuid4()),
                failed_login_count=0,
                must_change_password=False,
            )
            db.add(sup)
            db.flush()
        supervisors.append(sup)
    print(f"  [+] {len(supervisors)} Regional Supervisors verified/created")

    # 3. Kindergartens Across All 12 Governorates with All Statuses
    kg_specs = [
        # Central Governorates
        dict(name_ar="حضانة الأمل النموذجية", name_en="Al Amal Model Kindergarten",
             governorate="عمان", district="قصبة عمان", area="عبدون",
             license_number="KG-AMM-2024-001", status=models.KindergartenStatus.ACTIVE,
             capacity=120, lat=31.9539, lng=35.9106, renewal=future(180)),
        dict(name_ar="حضانة براعم الهدى", name_en="Baraem Al Huda Kindergarten",
             governorate="عمان", district="الجامعة", area="الجبيهة",
             license_number="KG-AMM-2024-002", status=models.KindergartenStatus.ACTIVE,
             capacity=85, lat=32.0250, lng=35.8650, renewal=future(300)),
        dict(name_ar="حضانة النور الساطع", name_en="Al Noor Kindergarten",
             governorate="الزرقاء", district="قصبة الزرقاء", area="الرصيفة",
             license_number="KG-ZAR-2024-003", status=models.KindergartenStatus.ACTIVE,
             capacity=90, lat=32.0608, lng=36.0942, renewal=future(90)),
        dict(name_ar="حضانة السلط الأهلية", name_en="Al Salt Kindergarten",
             governorate="البلقاء", district="قصبة السلط", area="السلط القديمة",
             license_number="KG-BAL-2024-004", status=models.KindergartenStatus.ACTIVE,
             capacity=60, lat=32.0392, lng=35.7272, renewal=future(15)),  # Expiring soon
        dict(name_ar="حضانة الفسيفساء", name_en="Mosaic Kindergarten",
             governorate="مادبا", district="قصبة مادبا", area="وسط مادبا",
             license_number="KG-MAD-2024-005", status=models.KindergartenStatus.ACTIVE,
             capacity=50, lat=31.7175, lng=35.7939, renewal=future(240)),

        # Northern Governorates
        dict(name_ar="حضانة إربد الكبرى", name_en="Greater Irbid Kindergarten",
             governorate="إربد", district="قصبة إربد", area="الحصن",
             license_number="KG-IRB-2024-006", status=models.KindergartenStatus.ACTIVE,
             capacity=110, lat=32.5568, lng=35.8469, renewal=future(150)),
        dict(name_ar="حضانة غصن الزيتون", name_en="Olive Branch Kindergarten",
             governorate="عجلون", district="قصبة عجلون", area="عنجرة",
             license_number="KG-AJL-2024-007", status=models.KindergartenStatus.ACTIVE,
             capacity=45, lat=32.3326, lng=35.7517, renewal=past(10)),  # Expired license
        dict(name_ar="حضانة أعمدة جرش", name_en="Jerash Columns Kindergarten",
             governorate="جرش", district="قصبة جرش", area="سوف",
             license_number="KG-JER-2024-008", status=models.KindergartenStatus.ACTIVE,
             capacity=55, lat=32.2747, lng=35.8961, renewal=future(210)),
        dict(name_ar="حضانة بادية المفرق", name_en="Mafraq Desert Kindergarten",
             governorate="المفرق", district="قصبة المفرق", area="البادية الشمالية",
             license_number="KG-MAF-2024-009", status=models.KindergartenStatus.ACTIVE,
             capacity=40, lat=32.3424, lng=36.2081, renewal=future(60)),

        # Southern Governorates
        dict(name_ar="حضانة قلعة الكرك", name_en="Karak Castle Kindergarten",
             governorate="الكرك", district="قصبة الكرك", area="المرج",
             license_number="KG-KAR-2024-010", status=models.KindergartenStatus.ACTIVE,
             capacity=65, lat=31.1853, lng=35.7048, renewal=future(140)),
        dict(name_ar="حضانة جبال الطفيلة", name_en="Tafilah Heights Kindergarten",
             governorate="الطفيلة", district="قصبة الطفيلة", area="بصيرا",
             license_number="KG-TAF-2024-011", status=models.KindergartenStatus.ACTIVE,
             capacity=35, lat=30.8375, lng=35.6042, renewal=future(110)),
        dict(name_ar="حضانة عروس الصحراء", name_en="Ma'an Desert Kindergarten",
             governorate="معان", district="قصبة معان", area="طريق الشوبك",
             license_number="KG-MAA-2024-012", status=models.KindergartenStatus.ACTIVE,
             capacity=40, lat=30.1927, lng=35.7360, renewal=future(95)),
        dict(name_ar="حضانة خليج العقبة", name_en="Aqaba Bay Kindergarten",
             governorate="العقبة", district="قصبة العقبة", area="الشاطئ الشمالي",
             license_number="KG-AQB-2024-013", status=models.KindergartenStatus.ACTIVE,
             capacity=95, lat=29.5320, lng=35.0063, renewal=future(330)),

        # Special Administrative Status Edge Cases
        dict(name_ar="حضانة المستقبل (قيد التأسيس)", name_en="Future Nursery (Draft)",
             governorate="عمان", district="ماركا", area="طبربور",
             license_number="KG-AMM-2024-DRAFT-014", status=models.KindergartenStatus.DRAFT,
             capacity=50, lat=31.9800, lng=35.9300, renewal=future(365)),
        dict(name_ar="حضانة زهرة الربيع (موقوفة مؤقتاً)", name_en="Spring Flower (Frozen)",
             governorate="الزرقاء", district="الزرقاء", area="الزرقاء الجديدة",
             license_number="KG-ZAR-2024-FRZ-015", status=models.KindergartenStatus.FROZEN,
             capacity=60, lat=32.0700, lng=36.1000, renewal=past(45)),
    ]

    kindergartens = []
    managers = []

    for i, spec in enumerate(kg_specs):
        kg = db.query(models.Kindergarten).filter(models.Kindergarten.license_number == spec["license_number"]).first()
        if not kg:
            kg = models.Kindergarten(
                name_ar=spec["name_ar"],
                name_en=spec["name_en"],
                governorate=spec["governorate"],
                district=spec["district"],
                area=spec["area"],
                address_line=f"شارع رقم {i+1}، مجمع {i+10}",
                contact_phone=f"+962791000{i+10:03d}",
                contact_email=f"kg_{i+1}@kinjo.jo",
                license_number=spec["license_number"],
                status=spec["status"],
                total_capacity=spec["capacity"],
                latitude=spec["lat"],
                longitude=spec["lng"],
                license_valid_until=spec["renewal"],
            )
            db.add(kg)
            db.flush()
        kindergartens.append(kg)

        # Create Manager for this kindergarten
        mgr_username = f"manager_kg_{i+1}"
        mgr = db.query(models.User).filter(models.User.username == mgr_username).first()
        if not mgr:
            mgr = models.User(
                username=mgr_username,
                email=f"manager_kg_{i+1}@kinjo.jo",
                hashed_password=get_password_hash(MANAGER_PASSWORD),
                role=models.UserRole.MANAGER,
                status=models.UserStatus.ACTIVE,
                kindergarten_id=kg.id,
                public_id=str(uuid.uuid4()),
                failed_login_count=0,
                must_change_password=False,
            )
            db.add(mgr)
            db.flush()
        managers.append(mgr)

    print(f"  [+] {len(kindergartens)} Kindergartens & Managers verified/created across 12 Governorates")

    # 4. Classrooms (Infants, Toddlers, KG1, KG2)
    class_specs = [
        ("صف الرضع (الفراشات)", "Infants Class (Butterflies)", "AGE_0_1", 0, 12, 10),
        ("صف البراعم (الأزهار)", "Toddlers Class (Blossoms)", "AGE_1_2", 12, 24, 15),
        ("صف الروضة الأولى (النجوم)", "KG1 Class (Stars)", "AGE_2_4", 24, 48, 20),
        ("المستوى الثاني KG2 (المستكشفون)", "KG2 Level 2 (Explorers)", "AGE_2_4", 48, 60, 25),
    ]

    all_classes = []
    assignments_created = 0

    for kg_idx, kg in enumerate(kindergartens):
        if kg.status == models.KindergartenStatus.DRAFT:
            continue
        for room_num, (c_name_ar, c_name_en, ag_enum, min_m, max_m, cap) in enumerate(class_specs, 1):
            cls_code = f"CLS-KG{kg.id}-R{room_num}"
            cls_obj = db.query(models.Class).filter(
                models.Class.class_code == cls_code
            ).first()
            if not cls_obj:
                cls_obj = models.Class(
                    kindergarten_id=kg.id,
                    name_ar=c_name_ar,
                    name_en=c_name_en,
                    class_code=cls_code,
                    age_group=ag_enum,
                    capacity_total=cap,
                    min_age_months=min_m,
                    max_age_months=max_m,
                )
                db.add(cls_obj)
                db.flush()
            all_classes.append(cls_obj)

            # Assign supervisor based on governorate
            assigned_sup = supervisors[0]
            for s_user in supervisors:
                if s_user.username == "supervisor_irbid" and kg.governorate in ("إربد", "عجلون", "جرش", "المفرق"):
                    assigned_sup = s_user
                elif s_user.username == "supervisor_zarqa" and kg.governorate == "الزرقاء":
                    assigned_sup = s_user
                elif s_user.username == "supervisor_south" and kg.governorate in ("الكرك", "الطفيلة", "معان"):
                    assigned_sup = s_user
                elif s_user.username == "supervisor_aqaba" and kg.governorate == "العقبة":
                    assigned_sup = s_user

            assign = db.query(models.SupervisorAssignment).filter(
                models.SupervisorAssignment.class_id == cls_obj.id,
                models.SupervisorAssignment.supervisor_id == assigned_sup.id,
                models.SupervisorAssignment.deleted_at.is_(None)
            ).first()
            if not assign:
                assign = models.SupervisorAssignment(
                    class_id=cls_obj.id,
                    supervisor_id=assigned_sup.id,
                    is_primary=True,
                    full_time_dedication=True,
                    start_date=past(180),
                    end_date=None,
                )
                db.add(assign)
                assignments_created += 1

    db.flush()
    print(f"  [+] {len(all_classes)} Classrooms & {assignments_created} Primary Supervisor Assignments created")

    # 5. Parents & Guardians
    parents_info = [
        ("parent_tariq", "tariq.khatib@gmail.com", "طارق", "الخطيب", "+962795111222", "9901001111", models.Gender.MALE),
        ("parent_reem", "reem.omari@gmail.com", "ريم", "العمري", "+962795222333", "9912002222", models.Gender.FEMALE),
        ("parent_sami", "sami.hasan@gmail.com", "سامي", "الحسن", "+962795333444", "9893003333", models.Gender.MALE),
        ("parent_mona", "mona.najjar@gmail.com", "منى", "النجار", "+962795444555", "9924004444", models.Gender.FEMALE),
        ("parent_zaid", "zaid.saleh@gmail.com", "زيد", "الصالح", "+962795555666", "9885005555", models.Gender.MALE),
        ("parent_huda", "huda.qasim@gmail.com", "هدى", "القاسم", "+962795666777", "9936006666", models.Gender.FEMALE),
        ("parent_omar", "omar.masri@gmail.com", "عمر", "المصري", "+962795777888", "9877007777", models.Gender.MALE),
        ("parent_layla", "layla.zoubi@gmail.com", "ليلى", "الزعبي", "+962795888999", "9948008888", models.Gender.FEMALE),
    ]
    parent_profiles = []
    for uname, email, fn, ln, phone, nat_id, gnd in parents_info:
        p_user = db.query(models.User).filter(models.User.username == uname).first()
        if not p_user:
            p_user = models.User(
                username=uname,
                email=email,
                hashed_password=get_password_hash(PARENT_PASSWORD),
                role=models.UserRole.PARENT,
                status=models.UserStatus.ACTIVE,
                public_id=str(uuid.uuid4()),
                failed_login_count=0,
                must_change_password=False,
            )
            db.add(p_user)
            db.flush()

        profile = db.query(models.ParentProfile).filter(models.ParentProfile.user_id == p_user.id).first()
        if not profile:
            profile = models.ParentProfile(
                user_id=p_user.id,
                first_name=fn,
                last_name=ln,
                phone_number=phone,
                gender=gnd,
                nationality="أردنية",
                national_id=nat_id,
                home_governorate="عمان",
                home_district="قصبة عمان",
                home_area="عبدون",
                home_address_line="شارع مكة، عمارة 12",
            )
            db.add(profile)
            db.flush()
        parent_profiles.append(profile)
    print(f"  [+] {len(parent_profiles)} Parent Accounts & Profiles verified/created")

    # 6. Children & Enrollment Applications Across All Funnel Stages & Sources
    child_first_names = [
        ("يوسف", models.Gender.MALE), ("كرم", models.Gender.MALE), ("آدم", models.Gender.MALE), ("زين", models.Gender.MALE), ("حمزة", models.Gender.MALE),
        ("عبدالله", models.Gender.MALE), ("إبراهيم", models.Gender.MALE), ("فيصل", models.Gender.MALE), ("سند", models.Gender.MALE), ("جاد", models.Gender.MALE),
        ("سارة", models.Gender.FEMALE), ("مريم", models.Gender.FEMALE), ("جنى", models.Gender.FEMALE), ("تالا", models.Gender.FEMALE), ("سلمى", models.Gender.FEMALE),
        ("زينة", models.Gender.FEMALE), ("يارا", models.Gender.FEMALE), ("لين", models.Gender.FEMALE), ("جود", models.Gender.FEMALE), ("نور", models.Gender.FEMALE),
        ("عمر", models.Gender.MALE), ("علي", models.Gender.MALE), ("أحمد", models.Gender.MALE), ("محمد", models.Gender.MALE), ("خالد", models.Gender.MALE),
        ("سامي", models.Gender.MALE), ("ياسر", models.Gender.MALE), ("طارق", models.Gender.MALE), ("فارس", models.Gender.MALE), ("راشد", models.Gender.MALE),
        ("ريما", models.Gender.FEMALE), ("هبة", models.Gender.FEMALE), ("دانا", models.Gender.FEMALE), ("رنا", models.Gender.FEMALE), ("مايا", models.Gender.FEMALE),
        ("ليلى", models.Gender.FEMALE), ("سما", models.Gender.FEMALE), ("سيلين", models.Gender.FEMALE), ("حلا", models.Gender.FEMALE), ("شهد", models.Gender.FEMALE),
        ("بشير", models.Gender.MALE), ("ماجد", models.Gender.MALE), ("منير", models.Gender.MALE), ("نايف", models.Gender.MALE), ("وليد", models.Gender.MALE),
        ("قيس", models.Gender.MALE), ("غيث", models.Gender.MALE), ("ليث", models.Gender.MALE), ("هاشم", models.Gender.MALE), ("عاصم", models.Gender.MALE),
        ("لمى", models.Gender.FEMALE), ("رزان", models.Gender.FEMALE), ("ديما", models.Gender.FEMALE), ("بيان", models.Gender.FEMALE), ("سحر", models.Gender.FEMALE),
        ("فرح", models.Gender.FEMALE), ("سندس", models.Gender.FEMALE), ("تسنيم", models.Gender.FEMALE), ("غيداء", models.Gender.FEMALE), ("نجود", models.Gender.FEMALE),
    ]
    family_names = ["الخطيب", "العمري", "الحسن", "النجار", "الصالح", "القاسم", "المصري", "الزعبي", "الحداد", "النبر"]

    age_bounds = get_child_age_bounds(TODAY)
    children = []
    enrollments = []

    # Status distribution for realistic analytics funnel testing
    statuses = [
        models.EnrollmentStatus.ACTIVE,
        models.EnrollmentStatus.ACTIVE,
        models.EnrollmentStatus.ACTIVE,
        models.EnrollmentStatus.SUBMITTED,
        models.EnrollmentStatus.PENDING_REVIEW,
        models.EnrollmentStatus.ACCEPTED,
        models.EnrollmentStatus.DRAFT,
        models.EnrollmentStatus.REJECTED,
        models.EnrollmentStatus.WITHDRAWN,
        models.EnrollmentStatus.WAITLISTED,
    ]
    sources = ["WEB", "MOBILE", "OFFICE"]

    active_classes = [c for c in all_classes if c.kindergarten_id]

    for idx, (fn, gender) in enumerate(child_first_names):
        ln = family_names[idx % len(family_names)]

        # Distribute birth dates across age policy range
        months_ago = 6 + (idx * 47 // len(child_first_names))
        dob = TODAY - timedelta(days=int(months_ago * 30.4))
        if dob < age_bounds.min_date:
            dob = age_bounds.min_date + timedelta(days=30)
        if dob > age_bounds.max_date:
            dob = age_bounds.max_date - timedelta(days=30)

        target_class = active_classes[idx % len(active_classes)]
        parent_profile = parent_profiles[idx % len(parent_profiles)]
        enr_status = statuses[idx % len(statuses)]
        app_source = sources[idx % len(sources)]

        ch = db.query(models.Child).filter(
            models.Child.first_name == fn,
            models.Child.last_name == ln,
            models.Child.parent_id == parent_profile.id
        ).first()

        if not ch:
            ch = models.Child(
                first_name=fn,
                last_name=ln,
                date_of_birth=dob,
                gender=gender,
                parent_id=parent_profile.id,
                father_name=f"{parent_profile.first_name} {parent_profile.last_name}",
                mother_first_name="فاطمة",
                mother_last_name="النجار",
                mother_nationality="أردنية",
                national_id=f"202{idx:02d}00{idx:04d}",
            )
            db.add(ch)
            db.flush()
        children.append(ch)

        enr = db.query(models.EnrollmentApplication).filter(
            models.EnrollmentApplication.child_id == ch.id,
            models.EnrollmentApplication.kindergarten_id == target_class.kindergarten_id
        ).first()

        if not enr:
            submitted_dt = dt(past(random.randint(10, 80)))
            decision_dt = submitted_dt + timedelta(days=2) if enr_status not in (models.EnrollmentStatus.DRAFT, models.EnrollmentStatus.SUBMITTED) else None

            enr = models.EnrollmentApplication(
                child_id=ch.id,
                kindergarten_id=target_class.kindergarten_id,
                class_id=target_class.id if enr_status == models.EnrollmentStatus.ACTIVE else None,
                status=enr_status,
                is_active=(enr_status == models.EnrollmentStatus.ACTIVE),
                source=app_source,
                submitted_at=submitted_dt,
                accepted_at=decision_dt if enr_status in (models.EnrollmentStatus.ACCEPTED, models.EnrollmentStatus.ACTIVE) else None,
                rejected_at=decision_dt if enr_status == models.EnrollmentStatus.REJECTED else None,
                decision_by=supervisors[0].id if decision_dt else None,
                decision_at=decision_dt,
                enrollment_start_date=past(60) if enr_status == models.EnrollmentStatus.ACTIVE else None,
            )
            db.add(enr)
            db.flush()
        enrollments.append(enr)

    print(f"  [+] {len(children)} Children & {len(enrollments)} Applications seeded across all 7 funnel statuses & sources")

    # 7. 90-Day Time Series Attendance Logs (With Baseline & Anomaly Spikes)
    att_logs = 0
    active_enrs = [e for e in enrollments if e.status == models.EnrollmentStatus.ACTIVE and e.class_id]

    existing_att_count = db.query(models.AttendanceLog).count()
    if existing_att_count < 100:
        for day_offset in range(90, -1, -1):
            cur_date = past(day_offset)
            if not is_workday(cur_date):
                continue

            # Inject a deliberate weather anomaly (high absence) on day -14
            is_anomaly_day = (day_offset == 14)

            for enr in active_enrs:
                # Normal 92% attendance, on anomaly day drops to 45%
                rand_val = random.random()
                if is_anomaly_day:
                    att_status = models.AttendanceStatus.ABSENT if rand_val > 0.45 else models.AttendanceStatus.PRESENT
                else:
                    if rand_val < 0.90:
                        att_status = models.AttendanceStatus.PRESENT
                    elif rand_val < 0.95:
                        att_status = models.AttendanceStatus.LATE
                    elif rand_val < 0.98:
                        att_status = models.AttendanceStatus.EXCUSED
                    else:
                        att_status = models.AttendanceStatus.ABSENT

                check_in = dt(cur_date, hour=7, minute=random.randint(45, 59)) if att_status in (models.AttendanceStatus.PRESENT, models.AttendanceStatus.LATE) else None
                check_out = dt(cur_date, hour=13, minute=random.randint(0, 30)) if att_status in (models.AttendanceStatus.PRESENT, models.AttendanceStatus.LATE) else None

                att = models.AttendanceLog(
                    child_id=enr.child_id,
                    class_id=enr.class_id,
                    date=cur_date,
                    status=att_status,
                    check_in_at=check_in,
                    check_out_at=check_out,
                    recorded_by=supervisors[0].id,
                )
                db.add(att)
                att_logs += 1

        db.flush()
        print(f"  [+] {att_logs} Daily Attendance logs generated over 90-day window (with anomaly test injection)")
    else:
        print(f"  [.] {existing_att_count} Attendance logs already present; skipping daily generation")

    # 8. Daily Reports (All Canonical Moods: HAPPY, CALM, ENERGETIC, TIRED, FUSSY, SAD)
    daily_reports_count = 0
    canonical_moods = ["HAPPY", "CALM", "ENERGETIC", "TIRED", "FUSSY", "SAD"]
    existing_dr_count = db.query(models.DailyReport).count()

    if existing_dr_count < 50:
        for day_offset in range(30, -1, -1):
            cur_date = past(day_offset)
            if not is_workday(cur_date):
                continue

            for enr in active_enrs[:15]:
                mood = canonical_moods[(day_offset + enr.child_id) % len(canonical_moods)]
                dr = models.DailyReport(
                    child_id=enr.child_id,
                    kindergarten_id=enr.kindergarten_id,
                    class_id=enr.class_id,
                    date=cur_date,
                    status=models.DailyReportStatus.APPROVED if day_offset > 0 else models.DailyReportStatus.SUBMITTED,
                    submitted_by=supervisors[0].id,
                    approved_by=managers[0].id if day_offset > 0 else None,
                    arrival_time="08:00",
                    mood=mood,
                    notes="الحالة الصحية ممتازة ومعنويات مرتفعة طوال اليوم" if mood in ("HAPPY", "CALM", "ENERGETIC") else "لوحظ بعض الخمول الخفيف بعد وجبة الغداء",
                )
                db.add(dr)
                daily_reports_count += 1
        db.flush()
        print(f"  [+] {daily_reports_count} Daily Reports created covering all 6 canonical mood states")
    else:
        print(f"  [.] {existing_dr_count} Daily Reports already present")

    # 9. Safety Incidents (All Severities: LOW, MEDIUM, HIGH, CRITICAL & Types)
    incident_specs = [
        (models.SeverityLevel.LOW, models.IncidentType.INJURY, "خدش بسيط في راحة اليد أثناء اللعب بالصلصال", "تم تطهير الخدش ووضع لاصق طبي مناسب", models.IncidentStatus.CLOSED, past(25)),
        (models.SeverityLevel.LOW, models.IncidentType.BEHAVIOR, "خلاف بسيط بين طفلين على لعبة جماعية", "تم التوجيه الإيجابي والصلح بين الطفلين", models.IncidentStatus.CLOSED, past(20)),
        (models.SeverityLevel.MEDIUM, models.IncidentType.ILLNESS, "ارتفاع طفيف في درجة الحرارة (38.1°م)", "تم عزل الطفل في غرفة الرعاية وإبلاغ ولي الأمر للحضور", models.IncidentStatus.RESOLVED, past(12)),
        (models.SeverityLevel.MEDIUM, models.IncidentType.ACCIDENT, "انزلاق خفيف في ممر الحضانة بدون كدمات", "تم فحص الطفل والتأكد من سلامة الأطراف وتجفيف الممر", models.IncidentStatus.RESOLVED, past(8)),
        (models.SeverityLevel.HIGH, models.IncidentType.HEALTH, "أعراض حساسية جلدية مفاجئة بعد تناول وجبة خفيفة", "تم إعطاء الدواء الموصوف وفق ملف الطفل والتواصل الفوري مع الأهل", models.IncidentStatus.ACTION_REQUIRED, past(3)),
        (models.SeverityLevel.CRITICAL, models.IncidentType.INJURY, "سقوط من أرجوحة الساحة الخارجية مع تورم في الكاحل", "تم تقديم الإسعاف الأولي ونقل الطفل مع المشرفة للمركز الصحي", models.IncidentStatus.UNDER_INVESTIGATION, past(1)),
    ]

    incidents_added = 0
    if db.query(models.Incident).count() < 10:
        for idx, (sev, itype, desc, action, st, occ_date) in enumerate(incident_specs):
            enr = active_enrs[idx % len(active_enrs)] if active_enrs else None
            if not enr:
                continue
            inc = models.Incident(
                child_id=enr.child_id,
                kindergarten_id=enr.kindergarten_id,
                class_id=enr.class_id,
                reported_by=supervisors[0].id,
                type=itype,
                severity_level=sev,
                status=st,
                occurred_at=dt(occ_date, hour=10, minute=30),
                description=desc,
                resolution_notes=action,
                parent_informed=True,
            )
            db.add(inc)
            incidents_added += 1
        db.flush()
        print(f"  [+] {incidents_added} Safety Incidents created across all 4 severity tiers (LOW to CRITICAL)")

    # 10. Ratio Compliance & Governance Scores
    ratio_records = 0
    for kg in kindergartens[:5]:
        for d_off in range(7, -1, -1):
            r_date = past(d_off)
            if not is_workday(r_date):
                continue
            rc = models.RatioCompliance(
                kindergarten_id=kg.id,
                date=r_date,
                operating_minutes=360,
                compliant_minutes=340 if random.random() > 0.15 else 280,
                staff_count_avg=4.0,
                child_count_avg=20.0,
            )
            db.add(rc)
            ratio_records += 1

        # Governance score
        gs = models.GovernanceScore(
            kindergarten_id=kg.id,
            period_start=past(30),
            period_end=TODAY,
            governance_quality_index=round(random.uniform(75.0, 96.0), 2),
            child_experience_index=round(random.uniform(70.0, 94.0), 2),
            final_governance_score=round(random.uniform(72.0, 95.0), 2),
            band=random.choice(["A", "A", "B", "C"]),
        )
        db.add(gs)

    db.flush()
    print(f"  [+] {ratio_records} Staff-Child Ratio Snapshots & Governance Scores seeded")

    # 11. Scheduled Chart Exports for Admin
    sched_exports = [
        ("attendance", "bar", "last_30", "CSV", "WEEKLY", 6, "admin.reports@kinjo.jo", "عمان"),
        ("incidents", "line", "last_3m", "JSON", "MONTHLY", 8, "safety.audit@kinjo.jo", None),
        ("daily_reports", "heatmap", "last_7", "CSV", "DAILY", 17, "compliance@kinjo.jo", "إربد"),
    ]
    sched_created = 0
    for src, ct, preset, fmt, freq, hour, email, gov in sched_exports:
        existing_se = db.query(models.ScheduledChartExport).filter(
            models.ScheduledChartExport.user_id == admin.id,
            models.ScheduledChartExport.source == src,
            models.ScheduledChartExport.frequency == freq
        ).first()
        if not existing_se:
            se = models.ScheduledChartExport(
                user_id=admin.id,
                source=src,
                chart_type=ct,
                date_preset=preset,
                export_format=fmt,
                frequency=freq,
                hour_utc=hour,
                recipient_email=email,
                governorate=gov,
                is_active=True,
                next_run_at=future(1),
            )
            db.add(se)
            sched_created += 1

    db.flush()
    print(f"  [+] {sched_created} Scheduled Chart Exports configured for Admin")

    # 12. Audit Logs
    audit_events = [
        (admin.id, "LOGIN", "User", admin.id, "Admin logged into Intelligence Center"),
        (admin.id, "VIEW_ANALYTICS", "Dashboard", None, "Accessed /admin/analytics dashboard"),
        (admin.id, "EXPORT_CHART_DATA", "ChartExport", None, "Exported attendance CSV report"),
        (supervisors[0].id, "INSPECT_KINDERGARTEN", "Kindergarten", kindergartens[0].id, "Completed quarterly field audit"),
        (managers[0].id, "APPROVE_DAILY_REPORT", "DailyReport", 1, "Manager approved daily reports batch"),
    ]
    for uid, act, etype, eid, details in audit_events:
        al = models.AuditLog(
            user_id=uid,
            action=act,
            entity_type=etype,
            entity_id=eid,
            details=details,
            ip_address="127.0.0.1",
        )
        db.add(al)
    db.flush()
    print(f"  [+] {len(audit_events)} System Audit Logs recorded")

    # Commit all transaction units
    db.commit()

    print("\n" + "=" * 65)
    print("  [SUCCESS] Admin Module Seed Data Generation Completed!")
    print("=" * 65 + "\n")

    summary = {
        "admin_user": "admin",
        "supervisors": len(supervisors),
        "kindergartens": len(kindergartens),
        "classes": len(all_classes),
        "parents": len(parent_profiles),
        "children": len(children),
        "enrollment_applications": len(enrollments),
        "attendance_logs": att_logs or existing_att_count,
        "daily_reports": daily_reports_count or existing_dr_count,
        "incidents": len(incident_specs),
        "governorates_covered": len(GOVERNORATES),
    }
    return summary


def main():
    force = "--force" in sys.argv
    init_db()
    db = SessionLocal()
    try:
        if force:
            print("[WIPE] Cleaning up existing data ...")
            for model_cls in [
                models.ScheduledChartExport, models.DailyReportView, models.WaitlistEntry,
                models.AbsenceRequest, models.SafeguardingCase, models.ChildDocument,
                models.HealthAlert, models.Portfolio, models.Observation,
                models.DailyReport, models.Incident, models.AttendanceLog,
                models.SupervisorAssignment, models.EnrollmentApplication,
                models.RatioCompliance, models.GovernanceScore,
                models.Child, models.ParentProfile, models.Class,
                models.Kindergarten, models.AuditLog
            ]:
                try:
                    db.query(model_cls).delete()
                except Exception:
                    pass
            db.commit()
            print("  Wipe complete.")

        summary = seed_admin_module(db, force=force)
        print("Summary:", summary)
    finally:
        db.close()


if __name__ == "__main__":
    main()
