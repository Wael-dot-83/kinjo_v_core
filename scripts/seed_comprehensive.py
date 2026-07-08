"""
Comprehensive seed data for KInJo – bilingual Jordanian kindergarten management system.
Creates realistic data across ALL major models with Arabic/English content.

Usage:
    python scripts/seed_comprehensive.py                # skip if data exists
    python scripts/seed_comprehensive.py --force        # wipe and re-seed
    python scripts/seed_comprehensive.py --force --keep-users  # wipe data but keep user accounts
"""

import os
import sys
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

# ──────────────────────────────────────────────
#  Configuration
# ──────────────────────────────────────────────
DEFAULT_PASSWORD = "Test@1234"  # overridden by SEED_*_PASSWORD env vars

GOVERNORATES = [
    "عمان", "إربد", "الزرقاء", "المفرق", "عجلون",
    "جرش", "مادبا", "البلقاء", "الكرك", "الطفيلة", "معان", "العقبة",
]


def _pw(env_key: str) -> str:
    return get_password_hash(os.environ.get(env_key, DEFAULT_PASSWORD))


# ──────────────────────────────────────────────
#  Helpers
# ──────────────────────────────────────────────
TODAY = date.today()
NOW = datetime.now(timezone.utc)


def dt(d: date, hour: int = 8, minute: int = 0):
    """date → datetime helper"""
    return datetime(d.year, d.month, d.day, hour, minute, tzinfo=timezone.utc)


def past(days: int) -> date:
    return TODAY - timedelta(days=days)


def future(days: int) -> date:
    return TODAY + timedelta(days=days)


def is_workday(d: date) -> bool:
    return d.weekday() not in (4, 5)  # Friday/Saturday off in Jordan


# ──────────────────────────────────────────────
#  SEED FUNCTION
# ──────────────────────────────────────────────
def seed(db: Session):
    print("\n[SEED] Seeding comprehensive data ...\n")

    # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
    #  TIER 0 – Kindergartens
    # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
    kg_data = [
        dict(name_ar="حضانة الأمل", name_en="Al Amal Kindergarten",
             governorate="عمان", city="عمان", area="عبدون",
             address_line="شارع 42، عمارة 5",
             contact_phone="+962791234567", contact_email="info@alamal.jo",
             license_number="KG-AMM-2024-001"),
        dict(name_ar="حضانة النور", name_en="Al Noor Kindergarten",
             governorate="عمان", city="عمان", area="الصويفية",
             address_line="شارع الرينبو 15",
             contact_phone="+962791234568", contact_email="info@alnoor.jo",
             license_number="KG-AMM-2024-002"),
        dict(name_ar="حضانة الإبداع", name_en="Al Ibdaa Kindergarten",
             governorate="إربد", city="إربد", area="الحصن",
             address_line="شارع الملك حسين 22",
             contact_phone="+962791234569", contact_email="info@alibdaa.jo",
             license_number="KG-IRB-2024-003"),
        dict(name_ar="حضانة الزهور", name_en="Al Zuhoor Kindergarten",
             governorate="الزرقاء", city="الزرقاء", area="الرصيفة",
             address_line="شارع الاستقلال 8",
             contact_phone="+962791234570", contact_email="info@alzuhoor.jo",
             license_number="KG-ZAR-2024-004"),
        dict(name_ar="حضانة البراعم", name_en="Al Baraem Kindergarten",
             governorate="العقبة", city="العقبة", area="الشامية",
             address_line="شارع الحرية 3",
             contact_phone="+962791234571", contact_email="info@albaraem.jo",
             license_number="KG-AQB-2024-005"),
    ]

    kgs = []
    for kd in kg_data:
        kg = models.Kindergarten(
            **kd,
            status=models.KindergartenStatus.ACTIVE,
            working_hours_start="07:00",
            working_hours_end="15:00",
            license_valid_until=future(365),
        )
        db.add(kg)
        kgs.append(kg)
    db.flush()
    print(f"  [OK] {len(kgs)} kindergartens")

    # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
    #  TIER 0 – Training modules
    # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
    training_modules = [
        models.TrainingModule(name="Child Safeguarding", description="حماية الطفل", is_mandatory=True),
        models.TrainingModule(name="First Aid Basics", description="الإسعافات الأولية", is_mandatory=True),
        models.TrainingModule(name="Fire Safety", description="السلامة من الحرائق", is_mandatory=True),
        models.TrainingModule(name="Inclusive Education", description="التعليم الشامل", is_mandatory=False),
    ]
    db.add_all(training_modules)
    db.flush()
    print(f"  [OK] {len(training_modules)} training modules")

    # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
    #  TIER 1 – Users
    # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
    admin = models.User(
        username="admin", email="admin@kinjo.jo",
        hashed_password=_pw("SEED_ADMIN_PASSWORD"),
        role=models.UserRole.ADMIN, status=models.UserStatus.ACTIVE,
        full_name="مدير النظام",
    )
    db.add(admin)
    db.flush()

    # One manager per KG
    manager_names = [
        ("manager1", "خالد العبادي", "khalid@kinjo.jo"),
        ("manager2", "سارة المحاسنة", "sara@kinjo.jo"),
        ("manager3", "عمر القضاة", "omar@kinjo.jo"),
        ("manager4", "نور الحياري", "nour@kinjo.jo"),
        ("manager5", "يزن البطاينة", "yazan@kinjo.jo"),
    ]
    managers = []
    for i, (uname, fname, email) in enumerate(manager_names):
        m = models.User(
            username=uname, email=email,
            hashed_password=_pw("SEED_MANAGER_PASSWORD"),
            role=models.UserRole.MANAGER,
            kindergarten_id=kgs[i].id,
            status=models.UserStatus.ACTIVE,
            full_name=fname,
        )
        db.add(m)
        managers.append(m)
    db.flush()

    # 2 supervisors per KG (10 total)
    sup_names = [
        ("sup1", "ريم الشمايلة"), ("sup2", "هالة العمري"),
        ("sup3", "دانا الخطيب"), ("sup4", "لمى الصمادي"),
        ("sup5", "فرح الطراونة"), ("sup6", "نادية الكيلاني"),
        ("sup7", "ميساء الحوراني"), ("sup8", "رزان الجراح"),
        ("sup9", "سلمى المعايطة"), ("sup10", "جمانة العساف"),
    ]
    supervisors = []
    for idx, (uname, fname) in enumerate(sup_names):
        kg_idx = idx // 2
        s = models.User(
            username=uname, email=f"{uname}@kinjo.jo",
            hashed_password=_pw("SEED_SUPERVISOR_PASSWORD"),
            role=models.UserRole.SUPERVISOR,
            kindergarten_id=kgs[kg_idx].id,
            status=models.UserStatus.ACTIVE,
            full_name=fname,
        )
        db.add(s)
        supervisors.append(s)
    db.flush()

    # 8 parents
    parent_data = [
        ("parent1@example.com", "أحمد", "الرشيد", "Ahmad", "Al-Rashid",
         models.Gender.MALE, "أردني", "1234567890", "عمان", "عمان", "عبدون",
         "+962791111111", "شارع المنزل 123"),
        ("parent2@example.com", "فاطمة", "النابلسي", "Fatima", "Al-Nabulsi",
         models.Gender.FEMALE, "أردنية", "2345678901", "عمان", "عمان", "الجبيهة",
         "+962791111112", "شارع الجامعة 45"),
        ("parent3@example.com", "محمد", "العزام", "Mohammad", "Al-Azzam",
         models.Gender.MALE, "أردني", "3456789012", "إربد", "إربد", "الحصن",
         "+962791111113", "شارع بغداد 10"),
        ("parent4@example.com", "ليلى", "الحوراني", "Laila", "Al-Hourani",
         models.Gender.FEMALE, "أردنية", "4567890123", "إربد", "إربد", "الرمثا",
         "+962791111114", "شارع فلسطين 7"),
        ("parent5@example.com", "عبدالله", "المعاني", "Abdullah", "Al-Maani",
         models.Gender.MALE, "أردني", "5678901234", "الزرقاء", "الزرقاء", "الرصيفة",
         "+962791111115", "شارع الحسين 33"),
        ("parent6@example.com", "رنا", "الشريف", "Rana", "Al-Sharif",
         models.Gender.FEMALE, "أردنية", "6789012345", "الزرقاء", "الزرقاء", "جبل الأمير حسن",
         "+962791111116", "شارع المدينة 12"),
        ("parent7@example.com", "طارق", "الخصاونة", "Tareq", "Al-Khasawneh",
         models.Gender.MALE, "أردني", "7890123456", "العقبة", "العقبة", "الشامية",
         "+962791111117", "شارع الملك عبدالله 5"),
        ("parent8@example.com", "هديل", "الزعبي", "Hadeel", "Al-Zoubi",
         models.Gender.FEMALE, "أردنية", "8901234567", "العقبة", "العقبة", "المنارة",
         "+962791111118", "شارع النخيل 18"),
    ]

    parent_users = []
    parent_profiles = []
    for (email, fn_ar, ln_ar, fn_en, ln_en, gender, nationality, nid,
         gov, city, area, phone, addr) in parent_data:
        pu = models.User(
            username=email, email=email,
            hashed_password=_pw("SEED_PARENT_PASSWORD"),
            role=models.UserRole.PARENT,
            status=models.UserStatus.ACTIVE,
            full_name=f"{fn_ar} {ln_ar}",
        )
        db.add(pu)
        db.flush()

        pp = models.ParentProfile(
            user_id=pu.id,
            first_name=fn_ar, last_name=ln_ar,
            first_name_en=fn_en, last_name_en=ln_en,
            phone_number=phone, gender=gender,
            nationality=nationality, national_id=nid,
            home_governorate=gov, home_district=city,
            home_area=area, home_address_line=addr,
            correspondence_preference=True,
            profile_complete=True,
            profile_completed_at=NOW,
            relationship_to_child="أب" if gender == models.Gender.MALE else "أم",
            emergency_contact_name=f"طوارئ {fn_ar}",
            emergency_contact_phone=phone.replace("1111", "2222"),
            emergency_contact_relationship="أخ/أخت",
        )
        db.add(pp)
        parent_users.append(pu)
        parent_profiles.append(pp)
    db.flush()
    print(f"  [OK] 1 admin, {len(managers)} managers, {len(supervisors)} supervisors, {len(parent_users)} parents")

    # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
    #  TIER 2 – Supervisor profiles
    # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
    for s in supervisors:
        db.add(models.SupervisorProfile(
            user_id=s.id, kindergarten_id=s.kindergarten_id
        ))
    db.flush()
    print(f"  [OK] {len(supervisors)} supervisor profiles")

    # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
    #  TIER 2 – KG Services
    # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
    svc_templates = [
        ("Extended Time", "رعاية ممتدة حتى الساعة 17:00"),
        ("Waiting Hour", "استقبال مبكر من الساعة 06:30"),
        ("Transportation", "خدمة النقل"),
    ]
    for kg in kgs:
        for sname, sdesc in svc_templates:
            db.add(models.KindergartenService(
                kindergarten_id=kg.id,
                service_name=sname, description=sdesc,
                enabled_flag=(sname != "Transportation"),
            ))
    db.flush()

    # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
    #  TIER 2 – Operating calendars (50-day window)
    # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
    cal_count = 0
    for kg in kgs:
        for offset in range(-30, 31):
            d = TODAY + timedelta(days=offset)
            is_open = is_workday(d)
            reason = None
            if d.weekday() == 4:
                reason = "الجمعة"
            elif d.weekday() == 5:
                reason = "السبت"
            db.add(models.OperatingCalendar(
                kindergarten_id=kg.id, date=d, is_open=is_open, reason=reason
            ))
            cal_count += 1
    db.flush()
    print(f"  [OK] {cal_count} calendar entries")

    # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
    #  TIER 3 – Classes (2 per KG = 10 total)
    # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
    class_templates = [
        ("الصف أ", "Class A", "AGE_2_4", 20, 24, 48),
        ("الصف ب", "Class B", "AGE_1_2", 15, 12, 24),
    ]
    classes = []
    class_supervisor = {}  # class -> primary supervisor (D1/B5: no legacy column)
    for kg_idx, kg in enumerate(kgs):
        sups_for_kg = [s for s in supervisors if s.kindergarten_id == kg.id]
        for cls_idx, (ar, en, ag, cap, mn, mx) in enumerate(class_templates):
            sup_for_class = sups_for_kg[cls_idx] if cls_idx < len(sups_for_kg) else None
            c = models.Class(
                kindergarten_id=kg.id,
                name_ar=ar, name_en=en,
                class_code=f"CLS-{kg_idx+1}-{cls_idx+1}",
                age_group=ag,
                capacity_total=cap,
                min_age_months=mn, max_age_months=mx,
                is_active=True,
            )
            db.add(c)
            classes.append(c)
            if sup_for_class:
                class_supervisor[c] = sup_for_class
    db.flush()
    print(f"  [OK] {len(classes)} classes")

    # Supervisor assignments (the source of truth for the primary supervisor).
    for c, sup in class_supervisor.items():
        db.add(models.SupervisorAssignment(
            class_id=c.id, supervisor_id=sup.id,
            is_primary=True, start_date=past(60),
        ))
    db.flush()

    # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
    #  TIER 3 – Children (20 children)
    # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
    child_specs = [
        # (parent_idx, first, last, gender, age_years, father, m_first, m_last, m_nat)
        (0, "ليلى", "الرشيد", "F", 3, "أحمد الرشيد", "فاطمة", "حسن", "أردنية"),
        (0, "عمر", "الرشيد", "M", 2, "أحمد الرشيد", "فاطمة", "حسن", "أردنية"),
        (1, "نور", "النابلسي", "F", 3, "سامي النابلسي", "فاطمة", "النابلسي", "أردنية"),
        (1, "ياسين", "النابلسي", "M", 2, "سامي النابلسي", "فاطمة", "النابلسي", "أردنية"),
        (1, "جنى", "النابلسي", "F", 1, "سامي النابلسي", "فاطمة", "النابلسي", "أردنية"),
        (2, "زيد", "العزام", "M", 3, "محمد العزام", "هالة", "القاضي", "أردنية"),
        (2, "رهف", "العزام", "F", 2, "محمد العزام", "هالة", "القاضي", "أردنية"),
        (3, "آدم", "الحوراني", "M", 3, "كريم الحوراني", "ليلى", "الحوراني", "أردنية"),
        (3, "سلمى", "الحوراني", "F", 2, "كريم الحوراني", "ليلى", "الحوراني", "أردنية"),
        (4, "ريان", "المعاني", "M", 3, "عبدالله المعاني", "رنا", "المعاني", "أردنية"),
        (4, "تالا", "المعاني", "F", 2, "عبدالله المعاني", "رنا", "المعاني", "أردنية"),
        (5, "كريم", "الشريف", "M", 3, "وليد الشريف", "رنا", "الشريف", "أردنية"),
        (5, "لين", "الشريف", "F", 1, "وليد الشريف", "رنا", "الشريف", "أردنية"),
        (6, "يوسف", "الخصاونة", "M", 3, "طارق الخصاونة", "مها", "العبادي", "أردنية"),
        (6, "جود", "الخصاونة", "F", 2, "طارق الخصاونة", "مها", "العبادي", "أردنية"),
        (6, "قيس", "الخصاونة", "M", 1, "طارق الخصاونة", "مها", "العبادي", "أردنية"),
        (7, "مريم", "الزعبي", "F", 3, "حسام الزعبي", "هديل", "الزعبي", "أردنية"),
        (7, "حمزة", "الزعبي", "M", 2, "حسام الزعبي", "هديل", "الزعبي", "أردنية"),
        (7, "ألين", "الزعبي", "F", 3, "حسام الزعبي", "هديل", "الزعبي", "أردنية"),
        (7, "سيف", "الزعبي", "M", 1, "حسام الزعبي", "هديل", "الزعبي", "أردنية"),
    ]

    children = []
    for (pidx, fn, ln, g, age, father, mfn, mln, mnat) in child_specs:
        dob = TODAY - timedelta(days=365 * age + random.randint(10, 300))
        ch = models.Child(
            parent_id=parent_profiles[pidx].id,
            first_name=fn, last_name=ln,
            gender=models.Gender.MALE if g == "M" else models.Gender.FEMALE,
            date_of_birth=dob,
            father_name=father,
            mother_first_name=mfn, mother_last_name=mln,
            mother_nationality=mnat,
            media_consent=True,
            correspondence_flag=True,
            profile_complete=True,
            profile_completed_at=NOW,
        )
        db.add(ch)
        children.append(ch)
    db.flush()
    print(f"  [OK] {len(children)} children")

    # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
    #  TIER 4 – Enrollments
    #  Distribute children across KGs/classes
    # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
    #  KG assignment: parents 0-1 → KG1, 2-3 → KG3, 4-5 → KG4, 6-7 → KG5
    #  KG2 gets waitlisted / pending applications
    parent_kg_map = {0: 0, 1: 0, 2: 2, 3: 2, 4: 3, 5: 3, 6: 4, 7: 4}

    enrollments = []
    for ch_idx, ch in enumerate(children):
        pidx = child_specs[ch_idx][0]
        kg_idx = parent_kg_map[pidx]
        kg = kgs[kg_idx]

        # Pick appropriate class based on child age
        kg_classes = [c for c in classes if c.kindergarten_id == kg.id]
        child_age_months = (TODAY - ch.date_of_birth).days * 12 // 365
        best_class = None
        for c in kg_classes:
            if c.min_age_months <= child_age_months <= c.max_age_months:
                best_class = c
                break
        if not best_class:
            best_class = kg_classes[0]

        # Most are ACTIVE, a few SUBMITTED / WAITLISTED for variety
        if ch_idx == 4:  # 5th child: pending
            status = models.EnrollmentStatus.SUBMITTED
        elif ch_idx == 12:  # 13th child: waitlisted
            status = models.EnrollmentStatus.WAITLISTED
        else:
            status = models.EnrollmentStatus.ACTIVE

        enr = models.EnrollmentApplication(
            child_id=ch.id,
            kindergarten_id=kg.id,
            class_id=best_class.id if status == models.EnrollmentStatus.ACTIVE else None,
            status=status,
            source="WEB",
            submitted_at=dt(past(60)),
            enrollment_start_date=past(30) if status == models.EnrollmentStatus.ACTIVE else None,
            enrollment_end_date=future(300) if status == models.EnrollmentStatus.ACTIVE else None,
            class_assignment_date=past(30) if status == models.EnrollmentStatus.ACTIVE else None,
        )
        db.add(enr)
        enrollments.append(enr)
    db.flush()

    # Update enrolled_children_count per class
    for c in classes:
        count = sum(1 for e in enrollments
                    if e.class_id == c.id and e.status == models.EnrollmentStatus.ACTIVE)
        c.enrolled_children_count = count
    db.flush()

    # Waitlist entry for the waitlisted enrollment
    waitlisted_enr = [e for e in enrollments if e.status == models.EnrollmentStatus.WAITLISTED]
    for we in waitlisted_enr:
        db.add(models.WaitlistEntry(
            enrollment_id=we.id,
            status=models.WaitlistStatus.WAITLISTED,
            priority_score=75.0,
        ))
    db.flush()
    print(f"  [OK] {len(enrollments)} enrollments ({len(waitlisted_enr)} waitlisted)")

    # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
    #  TIER 4 – Attendance (last 30 workdays)
    # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
    active_enrollments = [e for e in enrollments if e.status == models.EnrollmentStatus.ACTIVE]
    att_count = 0
    statuses_pool = (
        [models.AttendanceStatus.PRESENT] * 15
        + [models.AttendanceStatus.ABSENT] * 2
        + [models.AttendanceStatus.LATE] * 2
        + [models.AttendanceStatus.EXCUSED] * 1
    )

    for day_offset in range(30, 0, -1):
        d = past(day_offset)
        if not is_workday(d):
            continue
        for enr in active_enrollments:
            st = random.choice(statuses_pool)
            check_in = dt(d, 7, random.randint(30, 59)) if st != models.AttendanceStatus.ABSENT else None
            check_out = dt(d, 14, random.randint(0, 30)) if check_in else None
            if st == models.AttendanceStatus.LATE and check_in:
                check_in = dt(d, 8, random.randint(15, 45))

            # Find the supervisor who recorded
            kg_sups = [s for s in supervisors if s.kindergarten_id == enr.kindergarten_id]
            recorder = kg_sups[0] if kg_sups else managers[0]

            db.add(models.AttendanceLog(
                child_id=enr.child_id,
                class_id=enr.class_id,
                date=d,
                status=st,
                check_in_at=check_in,
                check_out_at=check_out,
                recorded_by=recorder.id,
                notes="تأخر بسبب الازدحام" if st == models.AttendanceStatus.LATE else None,
            ))
            att_count += 1
    db.flush()
    print(f"  [OK] {att_count} attendance records")

    # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
    #  TIER 4 – Daily reports (last 21 workdays)
    # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
    moods = ["سعيد 😊", "هادئ 😌", "نشيط 🤸", "حزين 😢", "عادي 😐"]
    activities_pool = [
        "رسم وتلوين", "لعب حر في الساحة", "قصة وقراءة", "أنشطة حركية",
        "تعلم الأرقام", "تعلم الحروف العربية", "موسيقى وغناء",
        "أشغال يدوية", "لعب تعاوني", "تجارب علمية بسيطة",
    ]
    dr_count = 0
    for day_offset in range(21, 0, -1):
        d = past(day_offset)
        if not is_workday(d):
            continue
        for enr in active_enrollments:
            kg_sups = [s for s in supervisors if s.kindergarten_id == enr.kindergarten_id]
            submitter = kg_sups[0] if kg_sups else managers[0]
            kg_mgr = [m for m in managers if m.kindergarten_id == enr.kindergarten_id]
            approver = kg_mgr[0] if kg_mgr else managers[0]

            report_status = random.choice([
                models.DailyReportStatus.SENT_TO_PARENT,
                models.DailyReportStatus.SENT_TO_PARENT,
                models.DailyReportStatus.SENT_TO_PARENT,
                models.DailyReportStatus.APPROVED,
                models.DailyReportStatus.SUBMITTED,
            ])

            dr = models.DailyReport(
                child_id=enr.child_id,
                kindergarten_id=enr.kindergarten_id,
                date=d,
                status=report_status,
                submitted_by=submitter.id,
                submitted_at=dt(d, 14, 0),
                approved_by=approver.id if report_status in (
                    models.DailyReportStatus.SENT_TO_PARENT,
                    models.DailyReportStatus.APPROVED) else None,
                approved_at=dt(d, 14, 30) if report_status in (
                    models.DailyReportStatus.SENT_TO_PARENT,
                    models.DailyReportStatus.APPROVED) else None,
                sent_to_parent_at=dt(d, 15, 0) if report_status == models.DailyReportStatus.SENT_TO_PARENT else None,
                arrival_time="07:45",
                leave_time="14:15",
                mood=random.choice(moods),
                health_notes=random.choice(["بصحة جيدة", "سعال خفيف", "حساسية موسمية", None, None]),
                breakfast=random.choice([True, True, False]),
                snack=True,
                lunch=random.choice([True, True, False]),
                milk=random.choice([True, False]),
                nap_start="12:00",
                nap_end="13:00",
                nap_duration_minutes=60,
                bathroom_count=random.randint(1, 4),
                activities=", ".join(random.sample(activities_pool, 3)),
                notes=random.choice(["يوم جميل", "تفاعل ممتاز مع الأصدقاء", "يحتاج تشجيع أكثر", None]),
            )
            db.add(dr)
            dr_count += 1
    db.flush()
    print(f"  [OK] {dr_count} daily reports")

    # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
    #  TIER 4 – Incidents
    # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
    incident_data = [
        (0, 0, models.IncidentType.INJURY, models.SeverityLevel.LOW, "خدش بسيط أثناء اللعب", 6),
        (1, 0, models.IncidentType.BEHAVIOR, models.SeverityLevel.MEDIUM, "مشاجرة بسيطة مع زميل", 4),
        (5, 2, models.IncidentType.ILLNESS, models.SeverityLevel.MEDIUM, "ارتفاع بسيط في الحرارة", 10),
        (9, 3, models.IncidentType.INJURY, models.SeverityLevel.HIGH, "سقوط من أرجوحة - كدمة", 3),
        (14, 4, models.IncidentType.OTHER, models.SeverityLevel.LOW, "فقدان حقيبة مؤقتاً", 8),
        (16, 4, models.IncidentType.ILLNESS, models.SeverityLevel.CRITICAL, "حساسية غذائية حادة", 2),
    ]
    for (ch_idx, kg_idx, itype, severity, desc, days_ago) in incident_data:
        occurred = dt(past(days_ago), 10, 15)
        db.add(models.Incident(
            child_id=children[ch_idx].id,
            kindergarten_id=kgs[kg_idx].id,
            type=itype,
            severity_level=severity,
            description=desc,
            occurred_at=occurred,
            followup_required_flag=severity in (models.SeverityLevel.HIGH, models.SeverityLevel.CRITICAL),
            followup_sla_deadline=occurred + timedelta(hours=24) if severity in (
                models.SeverityLevel.HIGH, models.SeverityLevel.CRITICAL) else None,
            closed_at=occurred + timedelta(hours=6) if severity != models.SeverityLevel.CRITICAL else None,
        ))
    db.flush()
    print(f"  [OK] {len(incident_data)} incidents")

    # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
    #  Staff presence logs (last 21 workdays)
    # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
    sp_count = 0
    for day_offset in range(21, 0, -1):
        d = past(day_offset)
        if not is_workday(d):
            continue
        for s in supervisors:
            db.add(models.StaffPresenceLog(
                staff_id=s.id, kindergarten_id=s.kindergarten_id,
                date=d,
                start_at=dt(d, 7, 15),
                end_at=dt(d, 15, 0),
            ))
            sp_count += 1
    db.flush()
    print(f"  [OK] {sp_count} staff presence logs")

    # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
    #  Ratio compliance (last 21 workdays per KG)
    # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
    rc_count = 0
    for day_offset in range(21, 0, -1):
        d = past(day_offset)
        if not is_workday(d):
            continue
        for kg in kgs:
            compliant = 450 if random.random() > 0.15 else random.randint(350, 430)
            db.add(models.RatioCompliance(
                kindergarten_id=kg.id, date=d,
                operating_minutes=450,
                compliant_minutes=compliant,
                staff_count_avg=2.0,
                child_count_avg=random.uniform(6, 14),
            ))
            rc_count += 1
    db.flush()
    print(f"  [OK] {rc_count} ratio compliance records")

    # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
    #  Daily checklists (last 21 workdays per KG)
    # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
    cl_count = 0
    for day_offset in range(21, 0, -1):
        d = past(day_offset)
        if not is_workday(d):
            continue
        for kg_idx, kg in enumerate(kgs):
            mgr = managers[kg_idx]
            for ctype in ("opening", "safety", "closing"):
                completed = random.random() > 0.1
                db.add(models.DailyChecklist(
                    kindergarten_id=kg.id,
                    checklist_date=d,
                    checklist_type=ctype,
                    status=models.DailyChecklistStatus.COMPLETED if completed else models.DailyChecklistStatus.PENDING,
                    submitted_by=mgr.id if completed else None,
                    submitted_at=dt(d, 8, 0) if completed else None,
                ))
                cl_count += 1
    db.flush()
    print(f"  [OK] {cl_count} daily checklists")

    # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
    #  Staff training completions
    # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
    tc_count = 0
    for s in supervisors:
        for tm in training_modules:
            completed = random.random() > 0.2
            db.add(models.StaffTrainingCompletion(
                user_id=s.id,
                training_module_id=tm.id,
                kindergarten_id=s.kindergarten_id,
                completion_date=past(random.randint(5, 60)) if completed else None,
                status=models.TrainingStatus.COMPLETED if completed else models.TrainingStatus.PENDING,
            ))
            tc_count += 1
    # Manager training
    for m in managers:
        for tm in training_modules[:2]:  # mandatory only
            db.add(models.StaffTrainingCompletion(
                user_id=m.id,
                training_module_id=tm.id,
                kindergarten_id=m.kindergarten_id,
                completion_date=past(random.randint(10, 90)),
                status=models.TrainingStatus.COMPLETED,
            ))
            tc_count += 1
    db.flush()
    print(f"  [OK] {tc_count} training completions")

    # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
    #  Surveys & responses
    # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
    surveys = []
    for kg in kgs:
        sv = models.Survey(
            kindergarten_id=kg.id,
            title="استطلاع رضا أولياء الأمور الشهري",
            description="Monthly parent satisfaction pulse survey",
            nps_question_enabled=True,
            start_date=past(30), end_date=future(1),
        )
        db.add(sv)
        surveys.append(sv)
    db.flush()

    sr_count = 0
    for sv in surveys:
        # Parents whose children are enrolled in this KG
        kg_parents = set()
        for enr in active_enrollments:
            if enr.kindergarten_id == sv.kindergarten_id:
                ch = next(c for c in children if c.id == enr.child_id)
                pp = next(p for p in parent_profiles if p.id == ch.parent_id)
                pu = next(u for u in parent_users if u.id == pp.user_id)
                kg_parents.add(pu.id)
        for pu_id in kg_parents:
            db.add(models.SurveyResponse(
                survey_id=sv.id,
                parent_id=pu_id,
                nps_score=random.choice([7, 8, 8, 9, 9, 9, 10, 10]),
                feedback_text=random.choice([
                    "بيئة آمنة ومحفزة",
                    "تواصل ممتاز مع أولياء الأمور",
                    "نتمنى تحسين وجبات الطعام",
                    "راضون جداً عن مستوى الرعاية",
                    "الأنشطة متنوعة وجميلة",
                    None,
                ]),
            ))
            sr_count += 1
    db.flush()
    print(f"  [OK] {len(surveys)} surveys, {sr_count} responses")

    # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
    #  Events
    # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
    event_templates = [
        ("يوم الأم", "Mother's Day celebration", models.EventType.CELEBRATION, 5),
        ("اجتماع أولياء الأمور", "Parent-teacher meeting", models.EventType.MEETING, 10),
        ("رحلة إلى المتحف", "Museum field trip", models.EventType.TRIP, 15),
        ("عيد الاستقلال", "Independence Day holiday", models.EventType.HOLIDAY, -3),
    ]
    ev_count = 0
    for kg in kgs:
        for (title, desc, etype, offset) in event_templates:
            d = future(offset) if offset > 0 else past(-offset)
            db.add(models.Event(
                kindergarten_id=kg.id,
                title=title, description=desc,
                type=etype,
                start_at=dt(d, 9, 0),
                end_at=dt(d, 12, 0),
                requires_consent_flag=(etype == models.EventType.TRIP),
            ))
            ev_count += 1
    db.flush()
    print(f"  [OK] {ev_count} events")

    # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
    #  Tasks
    # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
    task_templates = [
        ("تحديث سجلات الأطفال", models.TaskPriority.HIGH, models.TaskStatus.COMPLETED),
        ("تنظيم رحلة ميدانية", models.TaskPriority.MEDIUM, models.TaskStatus.IN_PROGRESS),
        ("صيانة ألعاب الساحة", models.TaskPriority.URGENT, models.TaskStatus.PENDING),
        ("مراجعة خطط الطوارئ", models.TaskPriority.HIGH, models.TaskStatus.PENDING),
        ("إعداد تقرير نهاية الشهر", models.TaskPriority.MEDIUM, models.TaskStatus.COMPLETED),
    ]
    tk_count = 0
    for kg_idx, kg in enumerate(kgs):
        mgr = managers[kg_idx]
        kg_sups = [s for s in supervisors if s.kindergarten_id == kg.id]
        for (title, priority, status) in task_templates:
            assignee = random.choice(kg_sups) if kg_sups else mgr
            db.add(models.Task(
                kindergarten_id=kg.id,
                title=title,
                description=f"مهمة: {title}",
                status=status, priority=priority,
                assigned_to=assignee.id,
                created_by=mgr.id,
                due_date=future(random.randint(1, 14)),
                completed_at=dt(past(1)) if status == models.TaskStatus.COMPLETED else None,
            ))
            tk_count += 1
    db.flush()
    print(f"  [OK] {tk_count} tasks")

    # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
    #  Absence requests
    # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
    abs_data = [
        # (pidx, ch_idx, kg_idx, reason, status, start_ago, end_ago)
        # start_ago >= end_ago so that start_date <= end_date
        (0, 0, 0, "زيارة طبيب أسنان", models.AbsenceRequestStatus.APPROVED, 5, 5),
        (1, 1, 0, "سفر عائلي", models.AbsenceRequestStatus.APPROVED, 12, 10),
        (2, 5, 2, "مرض - إنفلونزا", models.AbsenceRequestStatus.APPROVED, 4, 3),
        (3, 9, 3, "مناسبة عائلية", models.AbsenceRequestStatus.SUBMITTED, 2, 2),
        (4, 14, 4, "موعد طبي", models.AbsenceRequestStatus.REJECTED, 7, 7),
    ]
    for (pidx, ch_idx, kg_idx, reason, status, start_ago, end_ago) in abs_data:
        enr_match = [e for e in enrollments if e.child_id == children[ch_idx].id]
        cls_id = enr_match[0].class_id if enr_match else None
        mgr = managers[kg_idx]
        db.add(models.AbsenceRequest(
            parent_id=parent_profiles[pidx].id,
            child_id=children[ch_idx].id,
            kindergarten_id=kgs[kg_idx].id,
            class_id=cls_id,
            start_date=past(start_ago),
            end_date=past(end_ago),
            reason=reason,
            status=status,
            manager_id=mgr.id if status != models.AbsenceRequestStatus.SUBMITTED else None,
            decision_note="تمت الموافقة" if status == models.AbsenceRequestStatus.APPROVED else (
                "غير مبرر" if status == models.AbsenceRequestStatus.REJECTED else None),
            decided_at=dt(past(start_ago)) if status != models.AbsenceRequestStatus.SUBMITTED else None,
        ))
    db.flush()
    print(f"  [OK] {len(abs_data)} absence requests")

    # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
    #  Observations & portfolios
    # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
    domains = list(models.LearningDomain)
    mastery_levels = list(models.MasteryLevel)
    obs_texts = [
        "يظهر تطوراً ملحوظاً في التفاعل الاجتماعي",
        "يتقن العد حتى 20 بثقة",
        "يحتاج دعماً إضافياً في المهارات الحركية الدقيقة",
        "يتميز في الأنشطة الفنية والإبداعية",
        "يظهر قدرة ممتازة على حل المشكلات",
        "يتفاعل بشكل إيجابي مع أقرانه",
        "يحتاج تشجيعاً في التعبير اللفظي",
        "يظهر فضولاً علمياً ملفتاً",
    ]
    obs_count = 0
    port_count = 0
    for ch_idx, ch in enumerate(children[:12]):  # first 12 children
        enr_match = [e for e in active_enrollments if e.child_id == ch.id]
        if not enr_match:
            continue
        kg_sups = [s for s in supervisors if s.kindergarten_id == enr_match[0].kindergarten_id]
        observer = kg_sups[0] if kg_sups else supervisors[0]

        for _ in range(random.randint(2, 4)):
            db.add(models.Observation(
                child_id=ch.id,
                observed_by=observer.id,
                domain=random.choice(domains),
                observation_text=random.choice(obs_texts),
                mastery_level=random.choice(mastery_levels),
                observed_at=dt(past(random.randint(1, 20))),
            ))
            obs_count += 1

        # Portfolio
        db.add(models.Portfolio(
            child_id=ch.id,
            title=f"ملف إنجازات {ch.first_name}",
            description=f"Portfolio for {ch.first_name} – Term 1",
            status=random.choice([models.PortfolioStatus.DRAFT, models.PortfolioStatus.PUBLISHED]),
            published_at=dt(past(5)) if random.random() > 0.5 else None,
        ))
        port_count += 1
    db.flush()
    print(f"  [OK] {obs_count} observations, {port_count} portfolios")

    # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
    #  Messages (announcements + direct)
    # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
    msg_count = 0
    for kg_idx, kg in enumerate(kgs):
        mgr = managers[kg_idx]
        # Announcement
        ann = models.Message(
            thread_type=models.MessageThreadType.ANNOUNCEMENT,
            sender_id=mgr.id,
            kindergarten_id=kg.id,
            subject="إعلان هام - تحديث مواعيد الدوام",
            message_body="نود إعلامكم بأن مواعيد الدوام ستتغير اعتباراً من الأسبوع القادم. الرجاء مراجعة الجدول المحدث.",
            allow_replies=False,
        )
        db.add(ann)
        msg_count += 1

    # Direct messages between manager and parents (KG1)
    for pu in parent_users[:2]:
        direct = models.Message(
            thread_type=models.MessageThreadType.DIRECT,
            sender_id=managers[0].id,
            recipient_id=pu.id,
            kindergarten_id=kgs[0].id,
            subject="متابعة حالة طفلكم",
            message_body="نود الاطمئنان على حالة طفلكم بعد الحادثة الأخيرة. هل تودون مناقشة أي شيء؟",
            allow_replies=True,
        )
        db.add(direct)
        msg_count += 1
    db.flush()
    print(f"  [OK] {msg_count} messages")

    # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
    #  KPI Snapshots
    # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
    kpi_names = [
        "attendance_rate", "report_completion_rate", "ratio_compliance_rate",
        "incident_rate_per_100", "training_compliance_rate", "nps_score",
    ]
    kpi_count = 0
    for kg in kgs:
        for kpi in kpi_names:
            for month_offset in range(3):
                ps = past(30 * (month_offset + 1))
                pe = past(30 * month_offset)
                val = {
                    "attendance_rate": random.uniform(85, 98),
                    "report_completion_rate": random.uniform(75, 100),
                    "ratio_compliance_rate": random.uniform(80, 100),
                    "incident_rate_per_100": random.uniform(0.5, 5.0),
                    "training_compliance_rate": random.uniform(70, 100),
                    "nps_score": random.uniform(7.0, 10.0),
                }.get(kpi, random.uniform(50, 100))
                db.add(models.KPISnapshot(
                    kindergarten_id=kg.id,
                    kpi_name=kpi,
                    kpi_value=round(val, 2),
                    period_start=ps, period_end=pe,
                ))
                kpi_count += 1
    db.flush()
    print(f"  [OK] {kpi_count} KPI snapshots")

    # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
    #  Governance scores
    # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
    for kg in kgs:
        gqi = round(random.uniform(70, 95), 2)
        cei = round(random.uniform(65, 95), 2)
        fgs = round((gqi * 0.6 + cei * 0.4), 2)
        band = "A" if fgs >= 85 else ("B" if fgs >= 70 else "C")
        db.add(models.GovernanceScore(
            kindergarten_id=kg.id,
            period_start=past(30), period_end=TODAY,
            governance_quality_index=gqi,
            child_experience_index=cei,
            final_governance_score=fgs,
            band=band,
        ))
    db.flush()
    print(f"  [OK] {len(kgs)} governance scores")

    # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
    #  KPI Targets
    # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
    targets = [
        ("attendance_rate", 90.0),
        ("report_completion_rate", 85.0),
        ("ratio_compliance_rate", 95.0),
        ("incident_rate_per_100", 3.0),
        ("training_compliance_rate", 100.0),
        ("nps_score", 8.0),
    ]
    for kpi, val in targets:
        db.add(models.KPITarget(
            kpi_name=kpi, target_value=val,
            effective_date=past(90),
            kindergarten_id=None,  # network-wide
        ))
    db.flush()
    print(f"  [OK] {len(targets)} KPI targets")

    # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
    #  Notifications (sample)
    # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
    notif_count = 0
    for pu in parent_users:
        db.add(models.Notification(
            user_id=pu.id,
            notification_type=models.NotificationType.DAILY_REPORT_SENT,
            channel=models.NotificationChannel.IN_APP,
            status=models.NotificationStatus.SENT,
            payload={"message": "تم إرسال التقرير اليومي لطفلكم"},
            sent_at=dt(past(1)),
        ))
        notif_count += 1
    db.flush()
    print(f"  [OK] {notif_count} notifications")

    # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
    #  Health alerts
    # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
    for ch in children[:4]:
        db.add(models.HealthAlert(
            child_id=ch.id,
            alert_type="allergy",
            description="حساسية من الفول السوداني" if random.random() > 0.5 else "حساسية من الغبار",
            severity="MEDIUM",
        ))
    db.flush()
    print(f"  [OK] 4 health alerts")

    # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
    #  Audit logs (sample activity)
    # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
    audit_actions = [
        (admin.id, "LOGIN", "User", None),
        (managers[0].id, "VIEW_DASHBOARD", "Dashboard", None),
        (managers[0].id, "APPROVE_REPORT", "DailyReport", 1),
        (supervisors[0].id, "SUBMIT_ATTENDANCE", "AttendanceLog", 1),
        (parent_users[0].id, "VIEW_REPORT", "DailyReport", 1),
    ]
    for (uid, action, etype, eid) in audit_actions:
        db.add(models.AuditLog(
            user_id=uid, action=action,
            entity_type=etype, entity_id=eid,
            details=f"Seed audit: {action}",
            ip_address="127.0.0.1",
        ))
    db.flush()
    print(f"  [OK] {len(audit_actions)} audit logs")

    # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
    #  COMMIT
    # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
    db.commit()

    print("\n" + "=" * 55)
    print("  [DONE]  Comprehensive seed complete!")
    print("=" * 55)
    print(f"""
  Kindergartens : {len(kgs)}
  Users         : 1 admin + {len(managers)} managers + {len(supervisors)} supervisors + {len(parent_users)} parents = {1 + len(managers) + len(supervisors) + len(parent_users)}
  Children      : {len(children)}
  Classes       : {len(classes)}
  Enrollments   : {len(enrollments)} (active: {len(active_enrollments)}, waitlisted: {len(waitlisted_enr)})
  Attendance    : {att_count}
  Daily Reports : {dr_count}
  Incidents     : {len(incident_data)}

  Credentials (override with SEED_*_PASSWORD env vars):
    admin              : {os.environ.get('SEED_ADMIN_PASSWORD', DEFAULT_PASSWORD)}
    manager1-5         : {os.environ.get('SEED_MANAGER_PASSWORD', DEFAULT_PASSWORD)}
    sup1-10            : {os.environ.get('SEED_SUPERVISOR_PASSWORD', DEFAULT_PASSWORD)}
    parent1-8@example  : {os.environ.get('SEED_PARENT_PASSWORD', DEFAULT_PASSWORD)}

  API docs: http://localhost:8000/docs
""")


# ──────────────────────────────────────────────
#  CLI entry point
# ──────────────────────────────────────────────
def main():
    force = "--force" in sys.argv

    init_db()
    db = SessionLocal()

    try:
        existing = db.query(models.Kindergarten).count()
        if existing > 0 and not force:
            print(f"Database already has {existing} kindergarten(s). Use --force to wipe and re-seed.")
            return

        if existing > 0 and force:
            print("[WIPE]  Wiping existing data ...")
            # Delete in reverse dependency order
            for model_cls in [
                models.Notification, models.DailyReportView, models.WaitlistEntry,
                models.AbsenceRequest, models.SafeguardingCase, models.ChildDocument,
                models.HealthAlert, models.Portfolio, models.Observation,
                models.DailyReport, models.Incident, models.AttendanceLog,
                models.SupervisorAssignment, models.EnrollmentApplication,
                models.ActionPlan, models.ActiveAlert,
                models.MessageAttachment, models.MessageUserState, models.MessageRecipient,
                models.Message,
                models.StaffTrainingCompletion, models.GovernanceReminder,
                models.Report, models.DailyChecklist, models.Recommendation, models.Task,
                models.PerformanceTarget, models.AlertThreshold, models.DrilldownPath,
                models.AnomalyAlert, models.PredictiveModel, models.ExportJob,
                models.SurveyResponse, models.StaffPresenceLog, models.AuditLog,
                models.UserDeviceToken, models.PasswordResetToken,
                models.Child,
                models.ParentProfile, models.SupervisorProfile,
                models.UserDashboardPreference, models.UserFilterPreference,
                models.GovernanceScore, models.KPITarget, models.KPISnapshot,
                models.RatioCompliance, models.Survey, models.Event,
                models.OperatingCalendar, models.KindergartenService,
                models.Class,
                models.User,
                models.TrainingModule, models.Kindergarten,
                models.BenchmarkData, models.PredictionCache,
                models.AnalyticsDimensionCache, models.AdvancedAnalyticsCache,
                models.DataQualityMetric, models.ImportLog, models.ImportedKindergarten,
            ]:
                try:
                    db.query(model_cls).delete()
                except (RuntimeError, ValueError, TypeError, AttributeError):
                    pass
            db.commit()
            print("  Done.\n")

        seed(db)

    except (RuntimeError, ValueError, TypeError, AttributeError, OSError) as e:
        db.rollback()
        print(f"\n[ERROR] {e}")
        raise
    finally:
        db.close()


if __name__ == "__main__":
    main()
