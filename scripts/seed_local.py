# seed_local.py - Development seed script with enhanced auto-auth support
# Run this before starting the server to prepare the testing environment.

import sys, os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.stdout.reconfigure(encoding="utf-8", errors="replace")

from datetime import date, datetime, timedelta
from database import SessionLocal, init_db
from models import (
    User, UserRole, UserStatus,
    Kindergarten, KindergartenStatus,
    Class,
    SupervisorAssignment,
    Child, Gender,
    EnrollmentApplication, EnrollmentStatus,
    AttendanceLog, AttendanceStatus,
    DailyReport, DailyReportStatus,
    Incident, IncidentType, SeverityLevel,
    ParentProfile, AuditLog
)
from auth import get_password_hash, create_user
from config import settings

if settings.ENVIRONMENT.lower() == "production" and not settings.TESTING:
    raise RuntimeError(
        "seed_local.py is a development/test fixture script (creates known, "
        "non-expiring passwords) and must not be run against a production "
        "environment. Refusing to continue."
    )

# Credentials for easy reference (used by launcher scripts)
CREDENTIALS = {
    "admin":       {"password": "Admin@1234",   "role": "ADMIN"},
    "manager1":    {"password": "Manager@1234", "role": "MANAGER"},
    "manager2":    {"password": "Manager@1234", "role": "MANAGER"},
    "supervisor1": {"password": "Super@1234",   "role": "SUPERVISOR"},
    "supervisor2": {"password": "Super@1234",   "role": "SUPERVISOR"},
    "parent1":     {"password": "Parent@1234",  "role": "PARENT"},
    "parent2":     {"password": "Parent@1234",  "role": "PARENT"},
}

def run():
    init_db()
    db = SessionLocal()
    try:
        # ── Fix any kindergartens with corrupt '????' data from old seed runs ─
        from sqlalchemy import text as _text
        _corrupt = db.execute(_text(
            "SELECT id FROM kindergartens WHERE name_ar LIKE '%?%'"
        )).fetchall()
        for (_id,) in _corrupt:
            db.execute(_text(
                "UPDATE kindergartens SET "
                "name_ar='حضانة البراعم', name_en='Al Baraaem Kindergarten', "
                "governorate='عمان', district='عمان', area='الرابية', "
                "address_line='شارع الرابية، عمان', contact_phone='0799000001' "
                "WHERE id=:id"
            ), {"id": _id})
            print(f"  Fixed corrupt kindergarten id={_id}")
        if _corrupt:
            db.commit()

        # ── Kindergartens ─────────────────────────────────────────────────────
        kg1 = db.query(Kindergarten).filter(Kindergarten.name_ar == "حضانة الأمل").first()
        if not kg1:
            kg1 = Kindergarten(
                name_ar="حضانة الأمل",
                name_en="Al Amal Kindergarten",
                governorate="عمان",
                district="عمان",
                area="الجبيهة",
                address_line="شارع الجامعة الأردنية، عمان",
                contact_phone="0791234567",
                status=KindergartenStatus.DRAFT,
            )
            db.add(kg1)
        kg2 = db.query(Kindergarten).filter(Kindergarten.name_ar == "حضانة النجوم").first()
        if not kg2:
            kg2 = Kindergarten(
                name_ar="حضانة النجوم",
                name_en="Al Nujoom Kindergarten",
                governorate="إربد",
                district="إربد",
                area="وسط البلد",
                address_line="شارع الملك حسين، إربد",
                contact_phone="0798765432",
                status=KindergartenStatus.DRAFT,
            )
            db.add(kg2)
        db.commit()
        db.refresh(kg1)
        if kg2.id is None:
            db.refresh(kg2)

        print(f"Kindergartens ready: {kg1.name_en} (id={kg1.id}), {kg2.name_en} (id={kg2.id})")

        # ── Users ─────────────────────────────────────────────────────────────
        from sqlalchemy import text

        def upsert_user(username, email, password, role, kg_id=None, first="", last=""):
            u = db.query(User).filter(User.username == username).first()
            if not u:
                import uuid as _uuid
                hashed = get_password_hash(password)
                db.execute(text(
                    "INSERT INTO users (username, email, hashed_password, role, status, kindergarten_id, must_change_password, failed_login_count, mfa_enabled, public_id) "
                    "VALUES (:u, :e, :h, :r, 'ACTIVE', :kg, 0, 0, 0, :pid)"
                ), {"u": username, "e": email, "h": hashed, "r": role.value, "kg": kg_id, "pid": str(_uuid.uuid4())})
                db.commit()
                u = db.query(User).filter(User.username == username).first()
                print(f"  Created {role} : {username} / {password}")
            else:
                # Keep demo credentials deterministic in local/dev environments.
                u.email = email
                u.role = role
                u.kindergarten_id = kg_id
                u.status = UserStatus.ACTIVE
                u.hashed_password = get_password_hash(password)
                u.failed_login_count = 0
                u.locked_until = None
                u.must_change_password = False
                if hasattr(u, 'mfa_enabled'):
                    u.mfa_enabled = False
                db.commit()
                print(f"  Updated {role} : {username} / {password}")
            return u

        admin  = upsert_user("admin",       "admin@kinjo.jo",       "Admin@1234",   UserRole.ADMIN,      None,     "مدير", "النظام")
        mgr    = upsert_user("manager1",    "manager1@kinjo.jo",    "Manager@1234", UserRole.MANAGER,    kg1.id,   "محمد", "الأحمد")
        sup    = upsert_user("supervisor1", "sup1@kinjo.jo",        "Super@1234",   UserRole.SUPERVISOR, kg1.id,   "فاطمة","علي")
        parent = upsert_user("parent1",     "parent1@kinjo.jo",     "Parent@1234",  UserRole.PARENT,     None,     "سامي", "الخالد")

        # Extra users for kg2
        upsert_user("manager2",    "manager2@kinjo.jo",    "Manager@1234", UserRole.MANAGER,    kg2.id, "ليلى", "حسن")
        upsert_user("supervisor2", "sup2@kinjo.jo",        "Super@1234",   UserRole.SUPERVISOR, kg2.id, "أحمد", "ناصر")
        upsert_user("parent2",     "parent2@kinjo.jo",     "Parent@1234",  UserRole.PARENT,     None,   "هند",  "سالم")

        # ── Classes ───────────────────────────────────────────────────────────
        kg1.status = KindergartenStatus.ACTIVE
        kg2.status = KindergartenStatus.ACTIVE
        db.commit()

        def upsert_class(kg_id, name_ar, name_en, class_code):
            c = db.query(Class).filter(Class.kindergarten_id == kg_id, Class.name_en == name_en).first()
            if not c:
                c = Class(
                    kindergarten_id=kg_id,
                    name_ar=name_ar,
                    name_en=name_en,
                    class_code=class_code,
                    age_group="AGE_2_4",
                    capacity_total=20,
                    min_age_months=24,
                    max_age_months=84,
                    is_active=True,
                )
                db.add(c)
                db.commit()
                db.refresh(c)
                print(f"  Created class: {name_en} (kg_id={kg_id})")
            return c

        class_a = upsert_class(kg1.id, "الصف الأول أ",  "Class A", "KG1-A")
        class_b = upsert_class(kg1.id, "الصف الثاني ب", "Class B", "KG1-B")
        class_c = upsert_class(kg2.id, "الصف الأول ج",  "Class C", "KG2-C")

        # ── Parent Profiles ───────────────────────────────────────────────────
        def upsert_parent_profile(user_id, phone, nationality, first, last, gender_val=Gender.MALE):
            pp = db.query(ParentProfile).filter(ParentProfile.user_id == user_id).first()
            if not pp:
                db.execute(text(
                    "INSERT INTO parent_profiles "
                    "(user_id, first_name, last_name, phone_number, gender, nationality, "
                    "home_governorate, home_district, home_area, home_address_line, "
                    "correspondence_preference, profile_complete) "
                    "VALUES (:uid, :fn, :ln, :ph, :g, :nat, 'عمان', 'عمان', 'الجبيهة', 'شارع الجامعة', 1, 1)"
                ), {"uid": user_id, "fn": first, "ln": last, "ph": phone, "g": gender_val.value, "nat": nationality})
                db.commit()
                pp = db.query(ParentProfile).filter(ParentProfile.user_id == user_id).first()
            return pp

        pp1 = upsert_parent_profile(parent.id, "0791112233", "الأردن", "سامي", "الخالد", Gender.MALE)
        parent2_user = db.query(User).filter(User.username == "parent2").first()
        pp2 = None
        if parent2_user:
            pp2 = upsert_parent_profile(parent2_user.id, "0792223344", "الأردن", "هند", "سالم", Gender.FEMALE)

        # ── Children ──────────────────────────────────────────────────────────
        def upsert_child(first_ar, last_ar, dob, gender, father_name, parent_user_id):
            c = db.query(Child).filter(
                Child.first_name == first_ar,
                Child.last_name  == last_ar,
            ).first()
            if not c:
                import uuid as _uuid
                db.execute(text(
                    "INSERT INTO children (parent_id, first_name, last_name, gender, date_of_birth, "
                    "father_name, mother_first_name, mother_last_name, mother_nationality, "
                    "media_consent, correspondence_flag, profile_complete, public_id) "
                    "VALUES (:pid, :fn, :ln, :g, :dob, :dad, 'أم', :ln, 'الأردن', 0, 1, 1, :cid)"
                ), {"pid": parent_user_id, "fn": first_ar, "ln": last_ar, "g": gender.value, "dob": str(dob), "dad": father_name, "cid": str(_uuid.uuid4())})
                db.commit()
                c = db.query(Child).filter(Child.parent_id == parent_user_id, Child.first_name == first_ar).first()
            return c

        today = date.today()
        child1 = upsert_child("علي",  "الخالد", today - timedelta(days=365 * 4), Gender.MALE,   "سامي الخالد",  pp1.id)
        child2 = upsert_child("لينا", "الخالد", today - timedelta(days=365 * 3), Gender.FEMALE, "سامي الخالد",  pp1.id)
        child3 = upsert_child("يوسف","سالم",    today - timedelta(days=365 * 4 + 90), Gender.MALE,   "هند سالم",     pp2.id if pp2 else pp1.id)
        print(f"Children: {child1.first_name}, {child2.first_name}, {child3.first_name}")

        # ── Enrollments ───────────────────────────────────────────────────────
        def upsert_enrollment(child_id, kg_id, class_id, status=EnrollmentStatus.ACTIVE):
            e = db.query(EnrollmentApplication).filter(
                EnrollmentApplication.child_id == child_id,
                EnrollmentApplication.kindergarten_id == kg_id,
            ).first()
            if not e:
                e = EnrollmentApplication(
                    child_id=child_id,
                    kindergarten_id=kg_id,
                    class_id=class_id,
                    status=status,
                    source="WEB",
                )
                db.add(e)
                db.commit()
                db.refresh(e)
            return e

        enroll1 = upsert_enrollment(child1.id, kg1.id, class_a.id)
        enroll2 = upsert_enrollment(child2.id, kg1.id, class_a.id)
        enroll3 = upsert_enrollment(child3.id, kg2.id, class_c.id)
        print("Enrollments created")

        # ── Supervisor Assignments ────────────────────────────────────────────
        def upsert_supervisor_assignment(supervisor_id, class_id, is_primary=True):
            a = db.query(SupervisorAssignment).filter(
                SupervisorAssignment.supervisor_id == supervisor_id,
                SupervisorAssignment.class_id == class_id,
                SupervisorAssignment.deleted_at.is_(None),
            ).first()
            if not a:
                a = SupervisorAssignment(
                    supervisor_id=supervisor_id,
                    class_id=class_id,
                    is_primary=is_primary,
                    start_date=date.today(),
                )
                db.add(a)
                db.commit()
                db.refresh(a)
                print(f"  Assigned supervisor {supervisor_id} → class {class_id}")
            return a

        sup2_user = db.query(User).filter(User.username == "supervisor2").first()
        upsert_supervisor_assignment(sup.id,             class_a.id, is_primary=True)
        upsert_supervisor_assignment(sup.id,             class_b.id, is_primary=False)
        if sup2_user:
            upsert_supervisor_assignment(sup2_user.id,   class_c.id, is_primary=True)
        print("Supervisor assignments created")

        # ── Sample Daily Reports ──────────────────────────────────────────────
        def upsert_daily_report(child_id, kg_id, report_date, status, submitted_by_id):
            r = db.query(DailyReport).filter(
                DailyReport.child_id == child_id,
                DailyReport.kindergarten_id == kg_id,
                DailyReport.date == report_date,
            ).first()
            if not r:
                r = DailyReport(
                    child_id=child_id,
                    kindergarten_id=kg_id,
                    date=report_date,
                    status=status,
                    submitted_by=submitted_by_id,
                    submitted_at=datetime.utcnow() if status != DailyReportStatus.DRAFT else None,
                    arrival_time="08:00",
                    leave_time="14:00",
                    breakfast=True,
                    snack=True,
                    milk=True,
                    lunch=False,
                    notes="تقرير يومي تجريبي",
                )
                db.add(r)
                db.commit()
            return r

        today = date.today()
        upsert_daily_report(child1.id, kg1.id, today,                   DailyReportStatus.DRAFT,     sup.id)
        upsert_daily_report(child1.id, kg1.id, today - timedelta(days=1), DailyReportStatus.SUBMITTED, sup.id)
        upsert_daily_report(child2.id, kg1.id, today,                   DailyReportStatus.DRAFT,     sup.id)
        upsert_daily_report(child2.id, kg1.id, today - timedelta(days=1), DailyReportStatus.SENT_TO_PARENT, sup.id)
        print("Daily reports created")

        # ── Attendance ────────────────────────────────────────────────────────
        today = date.today()
        for child in [child1, child2]:
            kg_class = db.execute(text("SELECT id FROM classes WHERE kindergarten_id=:kg LIMIT 1"), {"kg": kg1.id}).fetchone()
            cls_id = kg_class[0] if kg_class else None
            for delta in range(10):
                d = today - timedelta(days=delta)
                exists = db.query(AttendanceLog).filter(
                    AttendanceLog.child_id == child.id,
                    AttendanceLog.date == d
                ).first()
                if not exists and cls_id:
                    checkin = datetime.combine(d, datetime.min.time()).replace(hour=8)
                    db.execute(text(
                        "INSERT INTO attendance_logs (child_id, class_id, date, status, check_in_at, check_out_at, recorded_by, picked_by_name) "
                        "VALUES (:cid, :clsid, :d, :status, :cin, :cout, :recorded_by, :picked_by)"
                    ), {
                        "cid": child.id,
                        "clsid": cls_id,
                        "d": str(d),
                        "status": AttendanceStatus.PRESENT.value,
                        "cin": str(checkin),
                        "cout": str(checkin.replace(hour=13)),
                        "recorded_by": sup.id,
                        "picked_by": "سامي الخالد",
                    })
        db.commit()
        print("Attendance records created")

        # ── Incidents ─────────────────────────────────────────────────────────
        severities = [SeverityLevel.LOW, SeverityLevel.MEDIUM, SeverityLevel.HIGH]
        inc_types   = [IncidentType.INJURY, IncidentType.BEHAVIOR, IncidentType.ILLNESS]
        for i, child in enumerate([child1, child2, child3]):
            kg_id = kg1.id if i < 2 else kg2.id
            exists = db.query(Incident).filter(Incident.child_id == child.id).first()
            if not exists:
                db.add(Incident(
                    child_id=child.id,
                    kindergarten_id=kg_id,
                    type=inc_types[i % 3],
                    severity_level=severities[i % 3],
                    description=f"حادثة تجريبية للطفل {child.first_name}",
                    occurred_at=datetime.utcnow() - timedelta(days=i * 3),
                ))
        db.commit()
        print("Incidents created")

        print("\n" + "="*60)
        print("SEED COMPLETE — Test credentials (use with TESTING=true):")
        print("  ADMIN      : admin       / Admin@1234")
        print("  MANAGER    : manager1    / Manager@1234   (kg1)")
        print("  SUPERVISOR : supervisor1 / Super@1234     (kg1)")
        print("  PARENT     : parent1     / Parent@1234")
        print("  MANAGER 2  : manager2    / Manager@1234   (kg2)")
        print("  SUPERVISOR2: supervisor2 / Super@1234     (kg2)")
        print("  PARENT 2   : parent2     / Parent@1234")
        print("="*60)
        print("Open: http://127.0.0.1:8000")
        print("API docs: http://127.0.0.1:8000/docs")

    except Exception as e:
        import traceback
        traceback.print_exc()
        db.rollback()
    finally:
        db.close()

if __name__ == "__main__":
    run()
