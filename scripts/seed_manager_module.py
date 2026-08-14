"""
Manager Module – Comprehensive Seed Data
========================================
Creates a full, self-contained dataset that covers every manager test case:
cross-tenant isolation, daily-report workflow, analytics drill-downs, absence
scope, supervisor assignment cascade, IDOR guards, and dashboard counts.

Usage
-----
    python scripts/seed_manager_module.py              # skip if data exists
    python scripts/seed_manager_module.py --force      # wipe and re-seed
    python scripts/seed_manager_module.py --keep-users # wipe data, keep accounts

The script is idempotent by default and prints a summary of what was inserted.
"""

from __future__ import annotations

import os
import sys
import random
from datetime import date, datetime, timedelta, timezone
from pathlib import Path

ROOT = str(Path(__file__).resolve().parent.parent)
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

from sqlalchemy.orm import Session
from sqlalchemy import text
from database import SessionLocal, init_db
import models
from auth import get_password_hash
from utils.time_utils import get_amman_tz, today_amman

# ──────────────────────────────────────────────────────────────
#  Configuration
# ──────────────────────────────────────────────────────────────
DEFAULT_PASSWORD = "Test@1234"
TODAY = today_amman()
NOW = datetime.now(timezone.utc)
AMMAN = get_amman_tz()


def _pw(env_key: str) -> str:
    return get_password_hash(os.environ.get(env_key, DEFAULT_PASSWORD))


def dt(d: date, hour: int = 8, minute: int = 0) -> datetime:
    return datetime(d.year, d.month, d.day, hour, minute, tzinfo=AMMAN)


def past(days: int) -> date:
    return TODAY - timedelta(days=days)


def future(days: int) -> date:
    return TODAY + timedelta(days=days)


def is_workday(d: date) -> bool:
    return d.weekday() not in (4, 5)


# ──────────────────────────────────────────────────────────────
#  Seed
# ──────────────────────────────────────────────────────────────
def seed(db: Session) -> None:
    print("\n[SEED] Manager Module comprehensive data ...\n")

    # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
    #  TIER 0 – Kindergartens (3 KGs for richer cross-tenant tests)
    # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
    kg_defs = [
        ("حضانة أ", "KG Alpha", "عمّان", "عمّان", "الدعيس",
         "شارع الملك", "+962791234501", "kg_a@kinjo.jo"),
        ("حضانة ب", "KG Beta", "الزرقاء", "الزرقاء", "المقابلين",
         "شارع الجديدة", "+962791234502", "kg_b@kinjo.jo"),
        ("حضانة ج", "KG Gamma", "إربد", "إربد", "الحصن",
         "شارع الملك حسين", "+962791234503", "kg_g@kinjo.jo"),
    ]

    kgs = []
    for ar, en, gov, dist, area, addr, phone, email in kg_defs:
        kg = models.Kindergarten(
            name_ar=ar,
            name_en=en,
            governorate=gov,
            district=dist,
            area=area,
            address_line=addr,
            contact_phone=phone,
            contact_email=email,
            status=models.KindergartenStatus.ACTIVE,
            operating_hours_start="07:00",
            operating_hours_end="15:00",
            license_valid_until=future(365),
            total_capacity=60,
            current_child_count=0,
            number_of_classes=3,
        )
        db.add(kg)
        kgs.append(kg)
    db.flush()
    print(f"  [OK] {len(kgs)} kindergartens")

    # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
    #  TIER 1 – Users (1 admin, 1 manager per KG, 2 supervisors per KG,
    #               1 parent per KG + 1 shared parent for edge cases)
    # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
    admin = models.User(
        username="admin",
        email="admin@kinjo.jo",
        hashed_password=_pw("SEED_ADMIN_PASSWORD"),
        role=models.UserRole.ADMIN,
        status=models.UserStatus.ACTIVE,
        full_name="مدير النظام",
    )
    db.add(admin)
    db.flush()

    managers: list[models.User] = []
    for i, kg in enumerate(kgs):
        m = models.User(
            username=f"manager{i+1}",
            email=f"manager{i+1}@kinjo.jo",
            hashed_password=_pw("SEED_MANAGER_PASSWORD"),
            role=models.UserRole.MANAGER,
            kindergarten_id=kg.id,
            status=models.UserStatus.ACTIVE,
            full_name=f"مدير {kg.name_ar}",
        )
        db.add(m)
        managers.append(m)
    db.flush()

    supervisors: list[models.User] = []
    for i, kg in enumerate(kgs):
        for j in range(2):
            s = models.User(
                username=f"sup_{i+1}_{j+1}",
                email=f"sup_{i+1}_{j+1}@kinjo.jo",
                hashed_password=_pw("SEED_SUPERVISOR_PASSWORD"),
                role=models.UserRole.SUPERVISOR,
                kindergarten_id=kg.id,
                status=models.UserStatus.ACTIVE,
                full_name=f"مشرف {j+1} - {kg.name_ar}",
            )
            db.add(s)
            supervisors.append(s)
    # One extra supervisor in KG A with INACTIVE status for validation tests
    inactive_sup = models.User(
        username="sup_inactive",
        email="sup_inactive@kinjo.jo",
        hashed_password=_pw("SEED_SUPERVISOR_PASSWORD"),
        role=models.UserRole.SUPERVISOR,
        kindergarten_id=kgs[0].id,
        status=models.UserStatus.INACTIVE,
        full_name="مشرف غير نشط",
    )
    db.add(inactive_sup)
    supervisors.append(inactive_sup)
    db.flush()

    parent_users: list[models.User] = []
    parent_profiles: list[models.ParentProfile] = []
    parent_specs = [
        ("parent1@example.com", "أحمد", "الرشيد", "Ahmad", "Al-Rashid",
         models.Gender.MALE, "الأردن", "1234567890", "عمّان", "عمّان", "الدعيس",
         "+962791111111", "شارع المنزل 123"),
        ("parent2@example.com", "فاطمة", "النابلسي", "Fatima", "Al-Nabulsi",
         models.Gender.FEMALE, "أردنية", "2345678901", "عمّان", "عمّان", "الجبيهة",
         "+962791111112", "شارع الجامعة 45"),
        ("parent3@example.com", "محمد", "العزام", "Mohammad", "Al-Azzam",
         models.Gender.MALE, "أردني", "3456789012", "إربد", "إربد", "الحصن",
         "+962791111113", "شارع بغداد 10"),
    ]
    for (email, fn_ar, ln_ar, fn_en, ln_en, gender, nationality, nid,
         gov, city, area, phone, addr) in parent_specs:
        pu = models.User(
            username=email,
            email=email,
            hashed_password=_pw("SEED_PARENT_PASSWORD"),
            role=models.UserRole.PARENT,
            status=models.UserStatus.ACTIVE,
            full_name=f"{fn_ar} {ln_ar}",
        )
        db.add(pu)
        db.flush()

        pp = models.ParentProfile(
            user_id=pu.id,
            first_name=fn_ar,
            last_name=ln_ar,
            first_name_en=fn_en,
            last_name_en=ln_en,
            phone_number=phone,
            gender=gender,
            nationality=nationality,
            national_id=nid,
            home_governorate=gov,
            home_district=city,
            home_area=area,
            home_address_line=addr,
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

    # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
    #  TIER 2 – Supervisor profiles
    # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
    for s in supervisors:
        if s.status == models.UserStatus.ACTIVE and s.role == models.UserRole.SUPERVISOR:
            db.add(models.SupervisorProfile(user_id=s.id, kindergarten_id=s.kindergarten_id))
    db.flush()
    print(f"  [OK] supervisor profiles")

    # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
    #  TIER 2 – Classes (3 per KG = 9 total)
    # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
    class_defs = [
        ("الحضانة", "Nursery", "AGE_1_2", 15, 12, 24),
        ("الروم", "Toddlers", "AGE_2_4", 20, 24, 48),
        ("الرياض", "Pre-K", "AGE_2_4", 12, 24, 48),
    ]
    classes: list[models.Class] = []
    class_supervisor: dict[models.Class, models.User] = {}
    for kg_idx, kg in enumerate(kgs):
        sups = [s for s in supervisors if s.kindergarten_id == kg.id and s.status == models.UserStatus.ACTIVE]
        for cls_idx, (ar, en, ag, cap, mn, mx) in enumerate(class_defs):
            sup = sups[cls_idx % len(sups)] if sups else None
            c = models.Class(
                kindergarten_id=kg.id,
                name_ar=ar,
                name_en=en,
                class_code=f"CLS-{kg_idx+1}-{cls_idx+1}",
                age_group=ag,
                capacity_total=cap,
                min_age_months=mn,
                max_age_months=mx,
                is_active=True,
            )
            db.add(c)
            classes.append(c)
            if sup:
                class_supervisor[c] = sup
    db.flush()

    # One "full" class for move-blocking tests (capacity 0)
    full_class = models.Class(
        kindergarten_id=kgs[0].id,
        name_ar="صف ممتلئ",
        name_en="Full Class",
        class_code="FULL-01",
        age_group="AGE_2_4",
        capacity_total=0,
        min_age_months=24,
        max_age_months=72,
        supervisor_id=None,
        is_active=True,
    )
    db.add(full_class)
    classes.append(full_class)
    db.flush()
    print(f"  [OK] {len(classes)} classes")

    # Primary supervisor assignments
    for c, sup in class_supervisor.items():
        db.add(models.SupervisorAssignment(
            class_id=c.id,
            supervisor_id=sup.id,
            is_primary=True,
            start_date=past(60),
        ))
    # One soft-deleted assignment to prove eligibility survives
    first_class = next(iter(class_supervisor.keys()))
    first_sup = class_supervisor[first_class]
    db.add(models.SupervisorAssignment(
        class_id=first_class.id,
        supervisor_id=first_sup.id,
        is_primary=True,
        start_date=past(90),
        end_date=past(30),
        deleted_at=dt(past(30), 10, 0),
    ))
    db.flush()
    print(f"  [OK] supervisor assignments")

    # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
    #  TIER 3 – Children (6 per KG = 18 total)
    # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
    children: list[models.Child] = []
    child_specs = [
        # (parent_idx, first_ar, last_ar, gender, age, father, m_first, m_last, m_nat)
        (0, "ليلى", "الرشيد", "F", 3, "أحمد الرشيد", "فاطمة", "حسن", "أردنية"),
        (0, "عمر", "الرشيد", "M", 2, "أحمد الرشيد", "فاطمة", "حسن", "أردنية"),
        (1, "نور", "النابلسي", "F", 3, "سامي النابلسي", "فاطمة", "النابلسي", "أردنية"),
        (1, "ياسين", "النابلسي", "M", 2, "سامي النابلسي", "فاطمة", "النابلسي", "أردنية"),
        (2, "زيد", "العزام", "M", 3, "محمد العزام", "هالة", "القاضي", "أردنية"),
        (2, "رهف", "العزام", "F", 2, "محمد العزام", "هالة", "القاضي", "أردنية"),
        # Extra children for KG A (no enrollment, for dashboard anchoring test)
        (0, "بلا_تسجيل", "طفل", "M", 4, "أب", "أم", "لقب", "أردنية"),
        (1, "سامي", "الصغير", "M", 1, "أب", "أم", "لقب", "أردنية"),
    ]
    for (pidx, fn, ln, g, age, father, mfn, mln, mnat) in child_specs:
        ch = models.Child(
            parent_id=parent_profiles[pidx].id,
            first_name=fn,
            last_name=ln,
            gender=models.Gender.MALE if g == "M" else models.Gender.FEMALE,
            date_of_birth=TODAY - timedelta(days=365 * age + 100),
            father_name=father,
            mother_first_name=mfn,
            mother_last_name=mln,
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

    # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
    #  TIER 4 – Enrollments
    # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
    enrollments: list[models.EnrollmentApplication] = []
    # Map first 6 children (2 per KG) to their KG's classes
    age_group_map = {"AGE_1_2": 0, "AGE_2_4": 1}
    for ch_idx, ch in enumerate(children[:6]):
        kg_idx = ch_idx % len(kgs)
        kg = kgs[kg_idx]
        kg_classes = [c for c in classes if c.kindergarten_id == kg.id and c.age_group in ("AGE_1_2", "AGE_2_4")]
        best = next((c for c in kg_classes if c.capacity_total > 0), kg_classes[0] if kg_classes else None)
        enr = models.EnrollmentApplication(
            child_id=ch.id,
            kindergarten_id=kg.id,
            class_id=best.id if best else None,
            status=models.EnrollmentStatus.ACTIVE,
            source="WEB",
            submitted_at=dt(past(60)),
            enrollment_start_date=past(30),
            enrollment_end_date=future(300),
            class_assignment_date=past(30),
        )
        db.add(enr)
        enrollments.append(enr)

    # A SUBMITTED enrollment for scope tests (different child)
    pending_child_idx = 6 if len(children) > 6 else len(children) - 1
    pending_enr = models.EnrollmentApplication(
        child_id=children[pending_child_idx].id,
        kindergarten_id=kgs[2].id,
        class_id=None,
        status=models.EnrollmentStatus.SUBMITTED,
        is_active=False,
        source="WEB",
        submitted_at=dt(past(10)),
    )
    db.add(pending_enr)
    enrollments.append(pending_enr)

    # A WAITLISTED enrollment (different child)
    waitlist_child_idx = 7 if len(children) > 7 else len(children) - 1
    waitlist_enr = models.EnrollmentApplication(
        child_id=children[waitlist_child_idx].id,
        kindergarten_id=kgs[2].id,
        class_id=None,
        status=models.EnrollmentStatus.WAITLISTED,
        is_active=False,
        source="WEB",
        submitted_at=dt(past(20)),
    )
    db.add(waitlist_enr)
    enrollments.append(waitlist_enr)
    db.flush()

    # Waitlist entry
    db.add(models.WaitlistEntry(
        enrollment_id=waitlist_enr.id,
        status=models.WaitlistStatus.WAITLISTED,
        priority_score=75.0,
    ))
    db.flush()
    print(f"  [OK] {len(enrollments)} enrollments")

    # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
    #  TIER 4 – OperatingCalendar (30-day window per KG)
    # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
    cal_count = 0
    for kg in kgs:
        for offset in range(-15, 16):
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

    # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
    #  TIER 4 – Attendance (last 20 workdays per active enrollment)
    # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
    active_enrollments = [e for e in enrollments if e.status == models.EnrollmentStatus.ACTIVE]
    att_count = 0
    statuses_pool = (
        [models.AttendanceStatus.PRESENT] * 15
        + [models.AttendanceStatus.ABSENT] * 2
        + [models.AttendanceStatus.LATE] * 2
        + [models.AttendanceStatus.EXCUSED] * 1
    )
    for day_offset in range(20, 0, -1):
        d = past(day_offset)
        if not is_workday(d):
            continue
        for enr in active_enrollments:
            st = random.choice(statuses_pool)
            check_in = dt(d, 7, random.randint(30, 59)) if st != models.AttendanceStatus.ABSENT else None
            check_out = dt(d, 14, random.randint(0, 30)) if check_in else None
            if st == models.AttendanceStatus.LATE and check_in:
                check_in = dt(d, 8, random.randint(15, 45))

            kg_sups = [s for s in supervisors if s.kindergarten_id == enr.kindergarten_id and s.status == models.UserStatus.ACTIVE]
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

    # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
    #  TIER 4 – Daily reports (multiple statuses for workflow tests)
    # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
    moods = ["سعيد 😊", "هادئ 😌", "نشيط 🤸", "حزين 😢", "عادي 😐"]
    activities_pool = [
        "رسم وتلوين", "لعب حر في الساحة", "قصة وقراءة", "أنشطة حركية",
        "تعلم الأرقام", "تعلم الحروف العربية", "موسيقى وغناء",
        "أشغال يدوية", "لعب تعاوني", "تجارب علمية بسيطة",
    ]
    dr_count = 0
    # One report per status per KG (for parametrized edit tests)
    statuses_for_tests = [
        models.DailyReportStatus.DRAFT,
        models.DailyReportStatus.SUBMITTED,
        models.DailyReportStatus.APPROVED,
        models.DailyReportStatus.SENT_TO_PARENT,
        models.DailyReportStatus.REJECTED,
        models.DailyReportStatus.RETURNED,
    ]
    for kg_idx, kg in enumerate(kgs):
        kg_active = [e for e in active_enrollments if e.kindergarten_id == kg.id]
        kg_sups = [s for s in supervisors if s.kindergarten_id == kg.id and s.status == models.UserStatus.ACTIVE]
        submitter = kg_sups[0] if kg_sups else managers[kg_idx]
        kg_mgr = managers[kg_idx]

        for s_idx, status in enumerate(statuses_for_tests):
            if not kg_active:
                continue
            enr = kg_active[s_idx % len(kg_active)]
            approver = kg_mgr if status in (
                models.DailyReportStatus.SENT_TO_PARENT,
                models.DailyReportStatus.APPROVED
            ) else None
            report_date = past(kg_idx * 3 + s_idx)

            dr = models.DailyReport(
                child_id=enr.child_id,
                kindergarten_id=kg.id,
                class_id=enr.class_id,
                date=report_date,
                status=status,
                submitted_by=submitter.id,
                submitted_at=dt(report_date, 14, 0),
                approved_by=approver.id if approver else None,
                approved_at=dt(report_date, 14, 30) if approver else None,
                sent_to_parent_at=dt(report_date, 15, 0) if status == models.DailyReportStatus.SENT_TO_PARENT else None,
                arrival_time="07:45",
                leave_time="14:15",
                mood=random.choice(moods),
                health_notes=random.choice(["بصحة جيدة", "سعال خفيف", None]),
                breakfast=True,
                snack=True,
                lunch=False,
                milk=True,
                nap_start="12:00",
                nap_end="13:00",
                nap_duration_minutes=60,
                bathroom_count=random.randint(1, 3),
                activities=", ".join(random.sample(activities_pool, 3)),
                notes="تقرير اختباري",
            )
            db.add(dr)
            dr_count += 1

    # A SUBMITTED report with no enrollment (dashboard anchoring test)
    child_no_enr = children[6]  # "بلا_تسجيل"
    db.add(models.DailyReport(
        child_id=child_no_enr.id,
        kindergarten_id=kgs[0].id,
        class_id=classes[0].id,
        date=past(1),
        status=models.DailyReportStatus.SUBMITTED,
        submitted_by=supervisors[0].id,
        arrival_time="08:00",
    ))
    dr_count += 1
    db.flush()
    print(f"  [OK] {dr_count} daily reports")

    # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
    #  TIER 4 – Incidents (for drill-down & boundary tests)
    # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
    incident_data = [
        (0, 0, models.IncidentType.INJURY, models.SeverityLevel.LOW, "خدش بسيط أثناء اللعب", 6),
        (1, 0, models.IncidentType.BEHAVIOR, models.SeverityLevel.MEDIUM, "مشاجرة بسيطة مع زميل", 4),
        (2, 2, models.IncidentType.ILLNESS, models.SeverityLevel.MEDIUM, "ارتفاع بسيط في الحرارة", 10),
        (3, 1, models.IncidentType.INJURY, models.SeverityLevel.HIGH, "سقوط من أرجوحة - كدمة", 3),
    ]
    for (ch_idx, kg_idx, itype, severity, desc, days_ago) in incident_data:
        occurred = dt(past(days_ago), 10, 15)
        db.add(models.Incident(
            child_id=children[ch_idx].id,
            kindergarten_id=kgs[kg_idx].id,
            class_id=classes[kg_idx].id if kg_idx < len(classes) else None,
            type=itype,
            severity_level=severity,
            description=desc,
            occurred_at=occurred,
            followup_required_flag=severity in (models.SeverityLevel.HIGH, models.SeverityLevel.CRITICAL),
            followup_sla_deadline=occurred + timedelta(hours=24) if severity in (
                models.SeverityLevel.HIGH, models.SeverityLevel.CRITICAL
            ) else None,
            closed_at=occurred + timedelta(hours=6) if severity != models.SeverityLevel.CRITICAL else None,
        ))
    db.flush()
    print(f"  [OK] {len(incident_data)} incidents")

    # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
    #  TIER 4 – Absence requests (SUBMITTED, APPROVED, REJECTED)
    # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
    abs_data = [
        (0, 0, 0, "زيارة طبيب أسنان", models.AbsenceRequestStatus.APPROVED, 5, 5),
        (1, 1, 0, "سفر عائلي", models.AbsenceRequestStatus.APPROVED, 12, 10),
        (2, 2, 1, "مرض - إنفلونزا", models.AbsenceRequestStatus.APPROVED, 4, 3),
        (0, 0, 0, "موعد طبي", models.AbsenceRequestStatus.SUBMITTED, 2, 2),
        (1, 1, 0, "مناسبة عائلية", models.AbsenceRequestStatus.REJECTED, 7, 7),
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
                "غير مبرر" if status == models.AbsenceRequestStatus.REJECTED else None
            ),
            decided_at=dt(past(start_ago)) if status != models.AbsenceRequestStatus.SUBMITTED else None,
        ))
    db.flush()
    print(f"  [OK] {len(abs_data)} absence requests")

    # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
    #  TIER 4 – ChildDocument (for foreign-manager scope test)
    # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
    db.add(models.ChildDocument(
        child_id=children[0].id,
        document_type="other",
        file_name="private.pdf",
        file_path="private.pdf",
        content_type="application/pdf",
        file_size=1024,
        verified=False,
        uploaded_by=managers[0].id,
    ))
    db.flush()
    print("  [OK] child document")

    # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
    #  TIER 5 – KPI Snapshots & Governance Scores
    # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
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
                    period_start=ps,
                    period_end=pe,
                ))
                kpi_count += 1
    db.flush()
    print(f"  [OK] {kpi_count} KPI snapshots")

    for kg in kgs:
        gqi = round(random.uniform(70, 95), 2)
        cei = round(random.uniform(65, 95), 2)
        fgs = round((gqi * 0.6 + cei * 0.4), 2)
        band = "A" if fgs >= 85 else ("B" if fgs >= 70 else "C")
        db.add(models.GovernanceScore(
            kindergarten_id=kg.id,
            period_start=past(30),
            period_end=TODAY,
            governance_quality_index=gqi,
            child_experience_index=cei,
            final_governance_score=fgs,
            band=band,
        ))
    db.flush()
    print(f"  [OK] {len(kgs)} governance scores")

    # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
    #  TIER 5 – Audit logs (sample mutations)
    # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
    audit_actions = [
        (managers[0].id, "SUPERVISOR_ASSIGNED", "SupervisorAssignment", 1),
        (managers[0].id, "CHILD_MOVED_CLASS", "Class", 1),
        (managers[0].id, "ABSENCE_REQUEST_APPROVED", "AbsenceRequest", 1),
        (supervisors[0].id, "DAILY_REPORT_SUBMITTED", "DailyReport", 1),
    ]
    for (uid, action, etype, eid) in audit_actions:
        db.add(models.AuditLog(
            user_id=uid,
            action=action,
            entity_type=etype,
            entity_id=eid,
            details=f"Seed audit: {action}",
            ip_address="127.0.0.1",
        ))
    db.flush()
    print("  [OK] audit logs")

    # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
    #  COMMIT
    # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
    db.commit()

    print("\n" + "=" * 55)
    print("  [DONE] Manager Module seed complete!")
    print("=" * 55)
    print(f"""
  Kindergartens : {len(kgs)}
  Users         : 1 admin + {len(managers)} managers + {len(supervisors)} supervisors + {len(parent_users)} parents
  Children      : {len(children)}
  Classes       : {len(classes)} (including 1 full-class for capacity tests)
  Enrollments   : {len(enrollments)}
  Attendance    : {att_count}
  Daily Reports : {dr_count} (all workflow statuses covered)
  Incidents     : {len(incident_data)}
  Absence Reqs  : {len(abs_data)}

  Credentials (override with SEED_*_PASSWORD env vars):
    admin       : {os.environ.get('SEED_ADMIN_PASSWORD', DEFAULT_PASSWORD)}
    manager1-3  : {os.environ.get('SEED_MANAGER_PASSWORD', DEFAULT_PASSWORD)}
    sup_1_1..3_2: {os.environ.get('SEED_SUPERVISOR_PASSWORD', DEFAULT_PASSWORD)}
    parent1-3   : {os.environ.get('SEED_PARENT_PASSWORD', DEFAULT_PASSWORD)}
""")


# ──────────────────────────────────────────────────────────────
#  CLI
# ──────────────────────────────────────────────────────────────
def main() -> None:
    force = "--force" in sys.argv

    init_db()
    db = SessionLocal()

    try:
        if force:
            from database import Base
            Base.metadata.drop_all(bind=db.get_bind())
            db.commit()
            print("[WIPE] All tables dropped.")
            init_db()
            db = SessionLocal()
        else:
            existing_kgs = db.query(models.Kindergarten).count()
            if existing_kgs > 0:
                print(f"[SKIP] Database already contains {existing_kgs} kindergartens. Use --force to re-seed.")
                return

        seed(db)
    finally:
        db.close()


if __name__ == "__main__":
    main()
