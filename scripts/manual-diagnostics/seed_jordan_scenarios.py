#!/usr/bin/env python
"""Seed a large, Jordan-scoped scenario dataset for exercising the admin UI.

Every row this creates is tagged so it can be found and removed again:

  * users        -- username starts with SEED_PREFIX, email @SEED_DOMAIN
  * classes      -- class_code starts with SEED_PREFIX
  * children     -- educational_notes contains SEED_TAG
  * everything else hangs off those rows by foreign key

It deliberately does NOT invent kindergartens. Production already holds the real
NCFA registry, so synthetic operational data is attached to existing
kindergartens instead of polluting the registry itself.

Usage:
    python seed_jordan_scenarios.py --scale small --dry-run
    python seed_jordan_scenarios.py --scale full
    python seed_jordan_scenarios.py --teardown        # remove everything tagged
"""

from __future__ import annotations

import argparse
import json
import random
import sys
from datetime import date, datetime, time, timedelta, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

# Arabic names go to stdout; a Windows console defaults to cp1252 and would
# raise UnicodeEncodeError on the first governorate printed.
for _stream in (sys.stdout, sys.stderr):
    try:
        _stream.reconfigure(encoding="utf-8", errors="replace")
    except (AttributeError, ValueError):  # pragma: no cover - non-reconfigurable stream
        pass

import models  # noqa: E402
from database import SessionLocal  # noqa: E402

# Jordan is UTC+3; operational dates must never come from date.today()/UTC.
_JORDAN_TZ = timezone(timedelta(hours=3))

SEED_TAG = "[SEED:JORDAN-SCENARIOS]"
SEED_PREFIX = "seed_"
SEED_DOMAIN = "seed.kinjo.test"
MANIFEST = Path(__file__).with_name("seed_manifest.json")

# A fixed seed keeps reruns and the teardown reproducible.
RNG = random.Random(20260812)

# Jordan's weekend is Friday/Saturday; weekday() gives Fri=4, Sat=5.
WEEKEND = {4, 5}

SCALES = {
    "smoke": dict(kindergartens=3, classes_per_kg=1, children_per_class=4, days=10),
    "small": dict(kindergartens=15, classes_per_kg=2, children_per_class=8, days=30),
    "full": dict(kindergartens=100, classes_per_kg=3, children_per_class=12, days=45),
}

AR_FIRST = ["أحمد", "محمد", "عمر", "يوسف", "خالد", "ليان", "سارة", "رغد", "جنى", "مريم",
            "زيد", "لؤي", "تالا", "سلمى", "نور", "هاشم", "بشار", "دانا", "رهف", "كرم"]
AR_LAST = ["العبداللات", "المجالي", "الزعبي", "الخصاونة", "النسور", "الطراونة", "العدوان",
           "الحياري", "أبو غزالة", "الشوابكة", "بني هاني", "الرواشدة", "السعودي", "التلهوني"]
# Postgres enforces these through age_group_enum; SQLite stores the column as
# free text, so a wrong label only shows up against the real database.
# (code, min_age_months, max_age_months)
AGE_GROUPS = [("AGE_0_1", 0, 11), ("AGE_1_2", 12, 23), ("AGE_2_4", 24, 47)]
MOODS = ["HAPPY", "CALM", "TIRED", "UPSET", "ENERGETIC"]

# Scenario mix -- each band gets a deliberately different behaviour profile so
# the classification page shows GREEN/AMBER/RED rather than one flat cohort.
PROFILES = [
    # name,      report_rate, approve_rate, on_time_rate, attendance_rate, weight
    ("excellent", 0.98, 0.98, 0.97, 0.97, 20),
    ("good", 0.90, 0.92, 0.88, 0.93, 30),
    ("average", 0.75, 0.80, 0.70, 0.88, 25),
    ("weak", 0.55, 0.60, 0.45, 0.80, 15),
    ("critical", 0.30, 0.35, 0.25, 0.68, 10),
]


def jordan_today() -> date:
    return datetime.now(_JORDAN_TZ).date()


def pick_profile():
    return RNG.choices(PROFILES, weights=[p[5] for p in PROFILES])[0]


def phone() -> str:
    return f"07{RNG.choice('789')}{RNG.randint(1000000, 9999999)}"


def national_id() -> str:
    return str(RNG.randint(9000000000, 9999999999))


def get_or_create_user(db, username: str, **fields):
    """Idempotent user creation so a rerun after a partial failure resumes
    instead of colliding on users.username."""
    existing = db.query(models.User).filter(models.User.username == username).first()
    if existing is not None:
        return existing, False
    user = models.User(username=username, **fields)
    db.add(user)
    db.flush()
    return user, True


def seed(db, scale: str, dry_run: bool) -> dict:
    cfg = SCALES[scale]
    today = jordan_today()
    # The window ends yesterday so nothing lands in the future.
    period_end = today - timedelta(days=1)
    period_start = period_end - timedelta(days=cfg["days"] - 1)
    all_days = [period_start + timedelta(days=i) for i in range((period_end - period_start).days + 1)]
    open_days = [d for d in all_days if d.weekday() not in WEEKEND]

    kgs = (
        db.query(models.Kindergarten)
        .filter(models.Kindergarten.status == models.KindergartenStatus.ACTIVE.value)
        .order_by(models.Kindergarten.id)
        .all()
    )
    if not kgs:
        kgs = db.query(models.Kindergarten).order_by(models.Kindergarten.id).all()
    if not kgs:
        raise SystemExit("No kindergartens in the database to attach scenarios to.")

    # Spread across governorates so every Jordanian region is represented.
    by_gov: dict[str, list] = {}
    for kg in kgs:
        by_gov.setdefault(kg.governorate or "غير محدد", []).append(kg)
    chosen: list = []
    while len(chosen) < min(cfg["kindergartens"], len(kgs)):
        progressed = False
        for gov_kgs in by_gov.values():
            if len(chosen) >= cfg["kindergartens"]:
                break
            for kg in gov_kgs:
                if kg not in chosen:
                    chosen.append(kg)
                    progressed = True
                    break
        if not progressed:
            break

    stats = {
        "period_start": str(period_start),
        "period_end": str(period_end),
        "open_days": len(open_days),
        "kindergartens": len(chosen),
        "users": 0, "classes": 0, "children": 0, "daily_reports": 0,
        "attendance_logs": 0, "incidents": 0, "enrollments": 0, "calendar_days": 0,
    }
    if dry_run:
        stats["dry_run"] = True
        est = len(chosen) * cfg["classes_per_kg"] * cfg["children_per_class"]
        stats["projected_children"] = est
        stats["projected_daily_reports"] = est * len(open_days)
        return stats

    from auth import get_password_hash
    pw = get_password_hash("SeedPassw0rd!2026")

    for kg_index, kg in enumerate(chosen):
        # Resume support: a kindergarten that already carries seeded classes was
        # completed on an earlier run. Re-seeding it would collide on
        # classes.class_code and uq_daily_report_kindergarten_child_date.
        already = (
            db.query(models.Class)
            .filter(models.Class.class_code.like(f"{SEED_PREFIX}{kg.id}\\_%", escape="\\"))
            .first()
        )
        if already is not None:
            stats["skipped_already_seeded"] = stats.get("skipped_already_seeded", 0) + 1
            continue

        profile_name, report_rate, approve_rate, on_time_rate, attend_rate, _ = pick_profile()

        # uq_users_active_manager_per_kindergarten allows exactly one active
        # manager per kindergarten, so reuse the real one where it exists rather
        # than colliding with it.
        manager = (
            db.query(models.User)
            .filter(
                models.User.kindergarten_id == kg.id,
                models.User.role == models.UserRole.MANAGER.value,
                models.User.status == models.UserStatus.ACTIVE.value,
                models.User.deleted_at.is_(None),
            )
            .first()
        )
        if manager is None:
            manager = models.User(
                username=f"{SEED_PREFIX}mgr_{kg.id}",
                email=f"{SEED_PREFIX}mgr_{kg.id}@{SEED_DOMAIN}",
                hashed_password=pw,
                role=models.UserRole.MANAGER.value,
                status=models.UserStatus.ACTIVE.value,
                kindergarten_id=kg.id,
                full_name=f"{RNG.choice(AR_FIRST)} {RNG.choice(AR_LAST)}",
                phone_number=phone(),
                preferred_language="ar",
            )
            db.add(manager)
            db.flush()
            stats["users"] += 1
        else:
            stats["reused_managers"] = stats.get("reused_managers", 0) + 1

        # Operating calendar: open on Sun-Thu, closed on the Jordanian weekend.
        existing_cal = {
            row[0] for row in db.query(models.OperatingCalendar.date)
            .filter(models.OperatingCalendar.kindergarten_id == kg.id,
                    models.OperatingCalendar.date >= period_start,
                    models.OperatingCalendar.date <= period_end).all()
        }
        for day in all_days:
            if day in existing_cal:
                continue
            db.add(models.OperatingCalendar(
                kindergarten_id=kg.id, date=day,
                is_open=day.weekday() not in WEEKEND,
                reason=None if day.weekday() not in WEEKEND else "عطلة نهاية الأسبوع",
            ))
            stats["calendar_days"] += 1

        for class_index in range(cfg["classes_per_kg"]):
            age_group, min_months, max_months = AGE_GROUPS[class_index % len(AGE_GROUPS)]
            supervisor, created = get_or_create_user(
                db,
                f"{SEED_PREFIX}sup_{kg.id}_{class_index}",
                email=f"{SEED_PREFIX}sup_{kg.id}_{class_index}@{SEED_DOMAIN}",
                hashed_password=pw,
                role=models.UserRole.SUPERVISOR.value,
                status=models.UserStatus.ACTIVE.value,
                kindergarten_id=kg.id,
                full_name=f"{RNG.choice(AR_FIRST)} {RNG.choice(AR_LAST)}",
                phone_number=phone(),
                preferred_language="ar",
            )
            stats["users"] += int(created)

            # classes.supervisor_id points at supervisor_profiles.user_id, not
            # users.id, so the profile row has to exist before the class does.
            # Get-or-create keeps a rerun after a partial failure safe.
            existing_profile = (
                db.query(models.SupervisorProfile)
                .filter(models.SupervisorProfile.user_id == supervisor.id)
                .first()
            )
            if existing_profile is None:
                db.add(models.SupervisorProfile(
                    user_id=supervisor.id, kindergarten_id=kg.id,
                ))
                db.flush()

            klass = models.Class(
                kindergarten_id=kg.id,
                name_ar=f"شعبة {age_group} - {class_index + 1}",
                name_en=f"{age_group} Section {class_index + 1}",
                class_code=f"{SEED_PREFIX}{kg.id}_{class_index}",
                age_group=age_group,
                capacity_total=cfg["children_per_class"] + 5,
                min_age_months=min_months,
                max_age_months=max_months,
                supervisor_id=supervisor.id,
                is_active=True,
            )
            db.add(klass)
            db.flush()
            stats["classes"] += 1

            db.add(models.SupervisorAssignment(
                class_id=klass.id, supervisor_id=supervisor.id,
                is_primary=True, full_time_dedication=True, start_date=period_start,
            ))

            children = []
            for child_index in range(cfg["children_per_class"]):
                parent_user, created = get_or_create_user(
                    db,
                    f"{SEED_PREFIX}par_{kg.id}_{class_index}_{child_index}",
                    email=f"{SEED_PREFIX}par_{kg.id}_{class_index}_{child_index}@{SEED_DOMAIN}",
                    hashed_password=pw,
                    role=models.UserRole.PARENT.value,
                    status=models.UserStatus.ACTIVE.value,
                    full_name=f"{RNG.choice(AR_FIRST)} {RNG.choice(AR_LAST)}",
                    phone_number=phone(),
                    preferred_language="ar",
                )
                stats["users"] += int(created)

                last = RNG.choice(AR_LAST)
                existing_parent = (
                    db.query(models.ParentProfile)
                    .filter(models.ParentProfile.user_id == parent_user.id)
                    .first()
                )
                profile = existing_parent or models.ParentProfile(
                    user_id=parent_user.id,
                    first_name=RNG.choice(AR_FIRST), last_name=last,
                    phone_number=phone(),
                    gender=RNG.choice(["MALE", "FEMALE"]),
                    nationality="أردني",
                    national_id=national_id(),
                    home_governorate=kg.governorate or "العاصمة",
                    home_district=kg.district or "قصبة عمان",
                    home_area=kg.area or "تلاع العلي",
                    home_address_line="عنوان تجريبي",
                    profile_complete=True,
                )
                db.add(profile)
                db.flush()

                # Keep each child inside its class's declared age band.
                months_old = RNG.randint(max(1, min_months), max_months)
                child = models.Child(
                    parent_id=profile.id,
                    first_name=RNG.choice(AR_FIRST), last_name=last,
                    gender=RNG.choice(["MALE", "FEMALE"]),
                    date_of_birth=period_end - timedelta(days=months_old * 30),
                    father_name=f"{RNG.choice(AR_FIRST)} {last}",
                    mother_first_name=RNG.choice(AR_FIRST), mother_last_name=RNG.choice(AR_LAST),
                    mother_nationality="أردنية",
                    # The removable marker for this dataset.
                    educational_notes=SEED_TAG,
                    has_special_needs=RNG.random() < 0.06,
                    has_medical_condition=RNG.random() < 0.08,
                    vaccination_up_to_date=RNG.random() < 0.92,
                    profile_complete=True,
                )
                db.add(child)
                db.flush()
                stats["children"] += 1
                children.append(child)

                # Enrollment applications spanning the whole status lifecycle.
                status = RNG.choices(
                    [models.EnrollmentStatus.ACTIVE.value,
                     models.EnrollmentStatus.ACCEPTED.value,
                     models.EnrollmentStatus.PENDING_REVIEW.value,
                     models.EnrollmentStatus.WAITLISTED.value,
                     models.EnrollmentStatus.REJECTED.value,
                     models.EnrollmentStatus.WITHDRAWN.value],
                    weights=[60, 15, 10, 6, 5, 4],
                )[0]
                db.add(models.EnrollmentApplication(
                    child_id=child.id, kindergarten_id=kg.id, class_id=klass.id,
                    status=status, is_active=status == models.EnrollmentStatus.ACTIVE.value,
                    source="SEED",
                    submitted_at=datetime.combine(period_start, time(9, 0)),
                    enrollment_start_date=period_start,
                ))
                stats["enrollments"] += 1

            klass.enrolled_children_count = len(children)

            # Daily operational history across the open days.
            for day in open_days:
                for child in children:
                    present = RNG.random() < attend_rate
                    att_status = (
                        models.AttendanceStatus.PRESENT.value if present
                        else RNG.choices(
                            [models.AttendanceStatus.ABSENT.value,
                             models.AttendanceStatus.LATE.value,
                             models.AttendanceStatus.EXCUSED.value],
                            weights=[60, 25, 15])[0]
                    )
                    db.add(models.AttendanceLog(
                        child_id=child.id, class_id=klass.id, date=day,
                        status=att_status, recorded_by=supervisor.id,
                        check_in_at=datetime.combine(day, time(7, RNG.randint(30, 59))),
                        check_out_at=datetime.combine(day, time(14, RNG.randint(0, 30))),
                    ))
                    stats["attendance_logs"] += 1

                    if att_status == models.AttendanceStatus.ABSENT.value:
                        continue
                    if RNG.random() > report_rate:
                        continue  # missing report -- drives the completion metric

                    if RNG.random() < approve_rate:
                        rep_status = (
                            models.DailyReportStatus.SENT_TO_PARENT.value
                            if RNG.random() < 0.7
                            else models.DailyReportStatus.APPROVED.value
                        )
                    else:
                        rep_status = RNG.choice([
                            models.DailyReportStatus.SUBMITTED.value,
                            models.DailyReportStatus.DRAFT.value,
                            models.DailyReportStatus.REJECTED.value,
                        ])

                    submitted_at = datetime.combine(day, time(13, RNG.randint(0, 59)))
                    approved_at = None
                    if rep_status in (models.DailyReportStatus.APPROVED.value,
                                      models.DailyReportStatus.SENT_TO_PARENT.value):
                        # On-time approvals land the same day; late ones slip.
                        delay = 2 if RNG.random() < on_time_rate else RNG.randint(20, 40)
                        approved_at = submitted_at + timedelta(hours=delay)

                    db.add(models.DailyReport(
                        child_id=child.id, kindergarten_id=kg.id, class_id=klass.id,
                        date=day, status=rep_status,
                        submitted_by=supervisor.id, submitted_at=submitted_at,
                        approved_by=manager.id if approved_at else None,
                        approved_at=approved_at,
                        sent_to_parent_at=(
                            approved_at if rep_status == models.DailyReportStatus.SENT_TO_PARENT.value else None
                        ),
                        arrival_time=f"07:{RNG.randint(30, 59)}",
                        leave_time=f"14:{RNG.randint(10, 59):02d}",
                        mood=RNG.choice(MOODS),
                        breakfast=RNG.random() < 0.9, snack=RNG.random() < 0.85,
                        milk=RNG.random() < 0.7, lunch=RNG.random() < 0.8,
                        nap_duration_minutes=RNG.choice([0, 30, 45, 60, 90]),
                        bathroom_count=RNG.randint(1, 5),
                        activities="أنشطة تعليمية وحركية",
                        notes=SEED_TAG,
                    ))
                    stats["daily_reports"] += 1

            # Incidents across every type and severity, open and closed.
            for _ in range(RNG.randint(0, 3)):
                child = RNG.choice(children)
                occurred = datetime.combine(RNG.choice(open_days), time(RNG.randint(8, 13), 0))
                severity = RNG.choices(
                    [models.SeverityLevel.LOW.value, models.SeverityLevel.MEDIUM.value,
                     models.SeverityLevel.HIGH.value, models.SeverityLevel.CRITICAL.value],
                    weights=[50, 30, 15, 5])[0]
                closed = RNG.random() < 0.6
                db.add(models.Incident(
                    child_id=child.id, kindergarten_id=kg.id, class_id=klass.id,
                    type=RNG.choice([models.IncidentType.INJURY.value,
                                     models.IncidentType.ILLNESS.value,
                                     models.IncidentType.BEHAVIOR.value,
                                     models.IncidentType.ACCIDENT.value,
                                     models.IncidentType.OTHER.value]),
                    severity_level=severity,
                    description=f"حادثة تجريبية {SEED_TAG}",
                    occurred_at=occurred,
                    reported_by=supervisor.id,
                    supervisor_id=supervisor.id,
                    parent_informed=RNG.random() < 0.85,
                    followup_required_flag=severity in ("HIGH", "CRITICAL"),
                    closed_at=occurred + timedelta(days=RNG.randint(1, 5)) if closed else None,
                    closed_by=manager.id if closed else None,
                    # incidentstatus stores the enum *name* (CLOSED), not the
                    # Python value ("Closed"), so .name is what Postgres accepts.
                    status=(models.IncidentStatus.CLOSED.name if closed
                            else models.IncidentStatus.OPEN.name),
                ))
                stats["incidents"] += 1

        # Commit per kindergarten to keep transactions bounded on a 4GB box.
        db.commit()
        print(f"  [{kg_index + 1}/{len(chosen)}] {kg.governorate} / kg#{kg.id} "
              f"profile={profile_name} children={stats['children']} reports={stats['daily_reports']}",
              flush=True)

    return stats


def teardown(db) -> dict:
    """Remove everything the seeder created, in FK-safe order."""
    removed = {}
    seed_users = db.query(models.User.id).filter(
        models.User.username.like(f"{SEED_PREFIX}%")).subquery()
    seed_profiles = db.query(models.ParentProfile.id).filter(
        models.ParentProfile.user_id.in_(db.query(seed_users.c.id))).subquery()
    seed_children = db.query(models.Child.id).filter(
        models.Child.parent_id.in_(db.query(seed_profiles.c.id))).subquery()
    seed_classes = db.query(models.Class.id).filter(
        models.Class.class_code.like(f"{SEED_PREFIX}%")).subquery()

    child_ids = [r[0] for r in db.query(seed_children.c.id).all()]
    class_ids = [r[0] for r in db.query(seed_classes.c.id).all()]
    user_ids = [r[0] for r in db.query(seed_users.c.id).all()]
    profile_ids = [r[0] for r in db.query(seed_profiles.c.id).all()]

    def purge(model, column, ids):
        if not ids:
            return 0
        total = 0
        for i in range(0, len(ids), 500):
            chunk = ids[i:i + 500]
            total += db.query(model).filter(column.in_(chunk)).delete(synchronize_session=False)
        db.commit()
        return total

    removed["daily_reports"] = purge(models.DailyReport, models.DailyReport.child_id, child_ids)
    removed["attendance_logs"] = purge(models.AttendanceLog, models.AttendanceLog.child_id, child_ids)
    removed["incidents"] = purge(models.Incident, models.Incident.child_id, child_ids)
    removed["enrollments"] = purge(models.EnrollmentApplication,
                                   models.EnrollmentApplication.child_id, child_ids)
    removed["supervisor_assignments"] = purge(models.SupervisorAssignment,
                                              models.SupervisorAssignment.class_id, class_ids)
    removed["children"] = purge(models.Child, models.Child.id, child_ids)
    removed["parent_profiles"] = purge(models.ParentProfile, models.ParentProfile.id, profile_ids)
    removed["classes"] = purge(models.Class, models.Class.id, class_ids)
    removed["supervisor_profiles"] = purge(
        models.SupervisorProfile, models.SupervisorProfile.user_id, user_ids)
    removed["users"] = purge(models.User, models.User.id, user_ids)
    return removed


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--scale", choices=sorted(SCALES), default="small")
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--teardown", action="store_true")
    args = parser.parse_args()

    db = SessionLocal()
    try:
        if args.teardown:
            result = teardown(db)
            print("Removed:", json.dumps(result, indent=2))
            return
        result = seed(db, args.scale, args.dry_run)
        print(json.dumps(result, indent=2, ensure_ascii=False))
        if not args.dry_run:
            MANIFEST.write_text(json.dumps(result, indent=2, ensure_ascii=False), encoding="utf-8")
    finally:
        db.close()


if __name__ == "__main__":
    main()
