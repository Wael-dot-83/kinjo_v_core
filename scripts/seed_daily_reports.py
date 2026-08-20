"""
Seed realistic DailyReport data for kindergarten_id=1, dates 2026-02-01 to 2026-02-09.
Usage:  python -m scripts.seed_daily_reports
  -- or from repo root: python scripts/seed_daily_reports.py
"""
import sys, os, random
from datetime import date, datetime, timedelta

# Allow running from repo root
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from database import SessionLocal, engine, Base
from config import settings
import models
from dependencies import has_role

random.seed(42)

# ── helpers ─────────────────────────────────────────────────────
MOODS = ["happy", "normal", "sad", "tired", "sick"]
MOOD_WEIGHTS = [0.40, 0.30, 0.10, 0.10, 0.10]
STATUSES = list(models.DailyReportStatus)
STATUS_WEIGHTS = [0.10, 0.10, 0.40, 0.30, 0.05, 0.05]  # DRAFT,SUBMIT,APPROVED,SENT,REJECT,RETURNED

HEALTH_NOTES_POOL = [
    None, None, None,  # 60% blank
    None, None,
    "حرارة خفيفة", "سعال بسيط", "احتقان", "mild fever",
    "runny nose", "slight cough", "stomach ache", "ألم في البطن",
    "تعب عام", "بكاء متكرر",
]
REJECTION_REASONS = [
    "بيانات غير مكتملة", "وقت الوصول غير صحيح", "ملاحظات ناقصة",
    "تكرار تقرير", "خطأ في اسم الطفل",
]
ACTIVITY_POOL = [
    "لعب حر في الساحة", "نشاط فني - رسم", "قراءة قصة",
    "أنشطة حركية", "تلوين", "أغاني وأناشيد", "مكعبات بناء",
    "لعب بالرمل", "زراعة نبتة", "نشاط علمي",
]


def _rand_time(h_min: int, h_max: int) -> str:
    h = random.randint(h_min, h_max)
    m = random.choice([0, 5, 10, 15, 20, 25, 30, 35, 40, 45, 50, 55])
    return f"{h:02d}:{m:02d}"


def _hhmm_to_minutes(t: str) -> int:
    h, m = t.split(":")
    return int(h) * 60 + int(m)


def seed(kg_id: int = 1, start: str = "2026-02-01", end: str = "2026-02-09"):
    if settings.ENVIRONMENT.lower() == "production":
        raise RuntimeError("Refusing to seed synthetic daily reports in production")

    # This utility is development-only; create missing local tables only after
    # the production guard has run.
    Base.metadata.create_all(bind=engine)
    db = SessionLocal()
    try:
        # Ensure base objects exist
        kg = db.query(models.Kindergarten).filter_by(id=kg_id).first()
        if not kg:
            kg = models.Kindergarten(
                id=kg_id, name_ar="حضانة النور", name_en="Al-Noor KG",
                governorate="Amman", city="Amman", area="Downtown",
                address_line="شارع الملك فهد",
                contact_phone="0551234567",
                status=models.KindergartenStatus.DRAFT,
            )
            db.add(kg)
            db.flush()

        # Ensure a supervisor user exists
        supervisor = db.query(models.User).filter_by(username="seed_supervisor").first()
        if not supervisor:
            from auth import get_password_hash
            supervisor = models.User(
                username="seed_supervisor", email="sup_seed@kinjo.test",
                hashed_password=get_password_hash("Test1234!"),
                role=models.UserRole.SUPERVISOR, kindergarten_id=kg_id,
                status=models.UserStatus.ACTIVE,
            )
            db.add(supervisor)
            db.flush()

        # Ensure a manager user exists (for approved_by)
        manager = db.query(models.User).filter_by(username="seed_manager").first()
        if not manager:
            from auth import get_password_hash
            manager = models.User(
                username="seed_manager", email="mgr_seed@kinjo.test",
                hashed_password=get_password_hash("Test1234!"),
                role=models.UserRole.MANAGER, kindergarten_id=kg_id,
                status=models.UserStatus.ACTIVE,
            )
            db.add(manager)
            db.flush()

        if (
            manager.deleted_at is not None
            or not has_role(manager, models.UserRole.MANAGER)
            or manager.status != models.UserStatus.ACTIVE
            or manager.kindergarten_id != kg_id
        ):
            raise RuntimeError(
                "seed_manager must be a non-deleted ACTIVE manager assigned to the target kindergarten"
            )

        # A kindergarten becomes operational only after its single manager is
        # known to be valid in this transaction.
        kg.status = models.KindergartenStatus.ACTIVE

        # Ensure parent users and children exist (10 children)
        children = db.query(models.Child).join(
            models.EnrollmentApplication,
            models.EnrollmentApplication.child_id == models.Child.id
        ).filter(models.EnrollmentApplication.kindergarten_id == kg_id).all()
        if len(children) < 10:
            # Ensure a class exists
            klass = db.query(models.Class).filter_by(kindergarten_id=kg_id).first()
            if not klass:
                klass = models.Class(
                    name_ar="صف الورد", kindergarten_id=kg_id,
                    capacity_total=25, min_age_months=24, max_age_months=48,
                )
                db.add(klass)
                db.flush()

            child_names = [
                ("أحمد", "محمد"), ("فاطمة", "علي"), ("نورة", "سعد"),
                ("ريم", "خالد"), ("يوسف", "عبدالله"), ("لينا", "عمر"),
                ("عمر", "حسن"), ("سارة", "إبراهيم"), ("خالد", "ناصر"),
                ("هند", "فهد"),
            ]
            from auth import get_password_hash
            for i, (first, last) in enumerate(child_names):
                if i < len(children):
                    continue
                parent_user = models.User(
                    username=f"parent_seed_{i}", email=f"parent_seed_{i}@kinjo.test",
                    hashed_password=get_password_hash("Test1234!"),
                    role=models.UserRole.PARENT,
                    status=models.UserStatus.ACTIVE,
                )
                db.add(parent_user)
                db.flush()

                parent_profile = models.ParentProfile(
                    user_id=parent_user.id,
                    first_name=f"ولي{i}",
                    last_name=last,
                    phone_number=f"+96279000{i:04d}",
                    gender=models.Gender.MALE,
                    nationality="Jordanian",
                    national_id=f"SEED{i:06d}",
                    home_governorate="Amman",
                    home_district="Amman",
                    home_area="Downtown",
                    home_address_line="شارع البذور",
                    correspondence_preference=True,
                )
                db.add(parent_profile)
                db.flush()

                child = models.Child(
                    first_name=first,
                    last_name=last,
                    date_of_birth=date(2022, random.randint(1, 12), random.randint(1, 28)),
                    parent_id=parent_profile.id,
                    gender=random.choice([models.Gender.MALE, models.Gender.FEMALE]),
                    father_name=f"أب {first}",
                    mother_first_name="أم",
                    mother_last_name=last,
                    mother_nationality="Jordanian",
                    media_consent=True,
                )
                db.add(child)
                db.flush()

                # Enrollment
                enrollment = models.EnrollmentApplication(
                    child_id=child.id, kindergarten_id=kg_id,
                    status=models.EnrollmentStatus.ACCEPTED,
                )
                db.add(enrollment)

            db.flush()
            children = db.query(models.Child).join(
                models.EnrollmentApplication,
                models.EnrollmentApplication.child_id == models.Child.id
            ).filter(models.EnrollmentApplication.kindergarten_id == kg_id).all()

        # Generate DailyReport rows
        d = date.fromisoformat(start)
        end_d = date.fromisoformat(end)
        created = 0
        while d <= end_d:
            # Skip Friday (weekend in KSA)
            if d.weekday() == 4:
                d += timedelta(days=1)
                continue
            for child in children:
                # ~10% absence
                if random.random() < 0.10:
                    d_dummy = d  # child absent this day
                    continue

                # Check if already exists
                exists = db.query(models.DailyReport).filter_by(
                    kindergarten_id=kg_id, child_id=child.id, date=d
                ).first()
                if exists:
                    continue

                status_choice = random.choices(STATUSES, STATUS_WEIGHTS)[0]
                mood = random.choices(MOODS, MOOD_WEIGHTS)[0]

                arrival = _rand_time(6, 8)
                leave = _rand_time(12, 14)

                nap_start = _rand_time(11, 12)
                nap_end_h = 12 + random.randint(0, 1)
                nap_end_m = random.choice([0, 15, 30, 45])
                nap_end = f"{nap_end_h:02d}:{nap_end_m:02d}"
                nap_dur = max(0, _hhmm_to_minutes(nap_end) - _hhmm_to_minutes(nap_start))
                # ~15% didn't nap
                if random.random() < 0.15:
                    nap_start = None
                    nap_end = None
                    nap_dur = None

                rejected_reason = None
                approved_by_id = None
                approved_at = None
                submitted_at = None
                sent_at = None

                base_dt = datetime(d.year, d.month, d.day, 14, 0, 0)

                if status_choice in (
                    models.DailyReportStatus.SUBMITTED,
                    models.DailyReportStatus.APPROVED,
                    models.DailyReportStatus.SENT_TO_PARENT,
                    models.DailyReportStatus.REJECTED,
                    models.DailyReportStatus.RETURNED,
                ):
                    submitted_at = base_dt + timedelta(minutes=random.randint(0, 60))

                if status_choice in (
                    models.DailyReportStatus.APPROVED,
                    models.DailyReportStatus.SENT_TO_PARENT,
                ):
                    approved_by_id = manager.id
                    approved_at = base_dt + timedelta(hours=random.randint(1, 4))

                if status_choice == models.DailyReportStatus.SENT_TO_PARENT:
                    sent_at = approved_at + timedelta(minutes=random.randint(5, 30)) if approved_at else None

                if status_choice in (
                    models.DailyReportStatus.REJECTED,
                    models.DailyReportStatus.RETURNED,
                ):
                    rejected_reason = random.choice(REJECTION_REASONS)
                    approved_by_id = manager.id

                report = models.DailyReport(
                    child_id=child.id,
                    kindergarten_id=kg_id,
                    date=d,
                    status=status_choice,
                    submitted_by=supervisor.id,
                    submitted_at=submitted_at,
                    approved_by=approved_by_id,
                    approved_at=approved_at,
                    sent_to_parent_at=sent_at,
                    rejected_reason=rejected_reason,
                    arrival_time=arrival,
                    leave_time=leave,
                    mood=mood,
                    health_notes=random.choice(HEALTH_NOTES_POOL),
                    breakfast=random.random() > 0.15,
                    snack=random.random() > 0.20,
                    milk=random.random() > 0.25,
                    lunch=random.random() > 0.10,
                    nap_start=nap_start,
                    nap_end=nap_end,
                    nap_duration_minutes=nap_dur,
                    bathroom_count=random.randint(0, 5),
                    diaper_wet=random.random() > 0.60,
                    diaper_soiled=random.random() > 0.75,
                    activities=random.choice(ACTIVITY_POOL),
                    notes=None if random.random() > 0.3 else "ملاحظة عامة",
                )
                db.add(report)
                created += 1

            d += timedelta(days=1)

        db.commit()
        print(f"[OK] Seeded {created} DailyReport rows for kg_id={kg_id} ({start} -> {end})")
        total = db.query(models.DailyReport).filter_by(kindergarten_id=kg_id).count()
        print(f"   Total DailyReport rows for kg_id={kg_id}: {total}")
    finally:
        db.close()


if __name__ == "__main__":
    seed()
