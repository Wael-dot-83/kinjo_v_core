"""
Local development seed script for KinJo platform.
Creates all tables and populates demo data for manual testing.

Users created:
  ADMIN    : admin / Admin@1234
  MANAGER  : manager1 / Manager@1234
  SUPERVISOR: supervisor1 / Super@1234
  PARENT   : parent1 / Parent@1234
"""
import sys, os
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
sys.stdout.reconfigure(encoding="utf-8", errors="replace")

from datetime import date, datetime, timedelta
from database import SessionLocal, init_db
from models import (
    User, UserRole, UserStatus,
    Kindergarten, KindergartenStatus,
    Child, Gender,
    EnrollmentApplication, EnrollmentStatus,
    AttendanceLog, AttendanceMethod,
    Incident, IncidentType, SeverityLevel,
    ParentProfile, AuditLog
)
from auth import get_password_hash, create_user

def run():
    init_db()
    db = SessionLocal()
    try:
        # ── Kindergartens ─────────────────────────────────────────────────────
        kg1 = db.query(Kindergarten).filter(Kindergarten.name_ar == "روضة الأمل").first()
        if not kg1:
            kg1 = Kindergarten(
                name_ar="روضة الأمل",
                name_en="Al Amal Kindergarten",
                governorate="عمان",
                city="عمان",
                area="الجبيهة",
                address_line="شارع الجامعة الأردنية، عمان",
                contact_phone="0791234567",
                status=KindergartenStatus.ACTIVE,
            )
            db.add(kg1)
        kg2 = db.query(Kindergarten).filter(Kindergarten.name_ar == "روضة النجوم").first()
        if not kg2:
            kg2 = Kindergarten(
                name_ar="روضة النجوم",
                name_en="Al Nujoom Kindergarten",
                governorate="إربد",
                city="إربد",
                area="وسط البلد",
                address_line="شارع الملك حسين، إربد",
                contact_phone="0798765432",
                status=KindergartenStatus.ACTIVE,
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
                hashed = get_password_hash(password)
                db.execute(text(
                    "INSERT INTO users (username, email, hashed_password, role, status, kindergarten_id, must_change_password, failed_login_count) "
                    "VALUES (:u, :e, :h, :r, 'ACTIVE', :kg, 0, 0)"
                ), {"u": username, "e": email, "h": hashed, "r": role.value, "kg": kg_id})
                db.commit()
                u = db.query(User).filter(User.username == username).first()
                print(f"  Created {role} : {username} / {password}")
            else:
                print(f"  Exists  {role} : {username}")
            return u

        admin  = upsert_user("admin",       "admin@kinjo.jo",       "Admin@1234",   UserRole.ADMIN,      None,     "مدير", "النظام")
        mgr    = upsert_user("manager1",    "manager1@kinjo.jo",    "Manager@1234", UserRole.MANAGER,    kg1.id,   "محمد", "الأحمد")
        sup    = upsert_user("supervisor1", "sup1@kinjo.jo",        "Super@1234",   UserRole.SUPERVISOR, kg1.id,   "فاطمة","علي")
        parent = upsert_user("parent1",     "parent1@kinjo.jo",     "Parent@1234",  UserRole.PARENT,     None,     "سامي", "الخالد")

        # Extra users for kg2
        upsert_user("manager2",    "manager2@kinjo.jo",    "Manager@1234", UserRole.MANAGER,    kg2.id, "ليلى", "حسن")
        upsert_user("supervisor2", "sup2@kinjo.jo",        "Super@1234",   UserRole.SUPERVISOR, kg2.id, "أحمد", "ناصر")
        upsert_user("parent2",     "parent2@kinjo.jo",     "Parent@1234",  UserRole.PARENT,     None,   "هند",  "سالم")

        # ── Parent Profiles ───────────────────────────────────────────────────
        def upsert_parent_profile(user_id, phone, nationality, first, last, gender_val=Gender.MALE):
            pp = db.query(ParentProfile).filter(ParentProfile.user_id == user_id).first()
            if not pp:
                db.execute(text(
                    "INSERT INTO parent_profiles "
                    "(user_id, first_name, last_name, phone_number, gender, nationality, "
                    "home_governorate, home_city, home_area, home_address_line, "
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
                db.execute(text(
                    "INSERT INTO children (parent_id, first_name, last_name, gender, date_of_birth, "
                    "father_name, mother_first_name, mother_last_name, mother_nationality, "
                    "media_consent, correspondence_flag, profile_complete) "
                    "VALUES (:pid, :fn, :ln, :g, :dob, :dad, 'أم', :ln, 'الأردن', 0, 1, 1)"
                ), {"pid": parent_user_id, "fn": first_ar, "ln": last_ar, "g": gender.value, "dob": str(dob), "dad": father_name})
                db.commit()
                c = db.query(Child).filter(Child.parent_id == parent_user_id, Child.first_name == first_ar).first()
            return c

        child1 = upsert_child("علي",  "الخالد", date(2021, 3, 10), Gender.MALE,   "سامي الخالد",  pp1.id)
        child2 = upsert_child("لينا", "الخالد", date(2021, 9, 5),  Gender.FEMALE, "سامي الخالد",  pp1.id)
        child3 = upsert_child("يوسف","سالم",    date(2020, 12, 1), Gender.MALE,   "هند سالم",     pp2.id if pp2 else pp1.id)
        print(f"Children: {child1.first_name}, {child2.first_name}, {child3.first_name}")

        # ── Enrollments ───────────────────────────────────────────────────────
        def upsert_enrollment(child_id, kg_id, status=EnrollmentStatus.ACTIVE):
            e = db.query(EnrollmentApplication).filter(
                EnrollmentApplication.child_id == child_id,
                EnrollmentApplication.kindergarten_id == kg_id,
            ).first()
            if not e:
                e = EnrollmentApplication(
                    child_id=child_id,
                    kindergarten_id=kg_id,
                    status=status,
                    source="WEB",
                )
                db.add(e)
                db.commit()
                db.refresh(e)
            return e

        enroll1 = upsert_enrollment(child1.id, kg1.id)
        enroll2 = upsert_enrollment(child2.id, kg1.id)
        enroll3 = upsert_enrollment(child3.id, kg2.id)
        print("Enrollments created")

        # ── Attendance ────────────────────────────────────────────────────────
        today = date.today()
        for child in [child1, child2]:
            # find class for this child's kg
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
                        "INSERT INTO attendance_logs (child_id, class_id, date, check_in_at, check_out_at, method, status, recorded_by, dropped_by_name) "
                        "VALUES (:cid, :clsid, :d, :cin, :cout, 'MANUAL', 'PRESENT', :rbid, :dby)"
                    ), {"cid": child.id, "clsid": cls_id, "d": str(d), "cin": str(checkin), "cout": str(checkin.replace(hour=13)), "rbid": sup.id, "dby": "سامي الخالد"})
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
        print("SEED COMPLETE — Test credentials:")
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
