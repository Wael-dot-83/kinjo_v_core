"""
Seed the app DB with clean kindergartens from the deduped Excel, then generate
operational data (classes, enrollments, incidents, daily reports, governance
scores) to drive the KPI indicators and heatmap.

SQLite FK enforcement is OFF so we use synthetic FK values (child_id=1,
submitted_by=5) for tables that don't need child/user resolution for heatmap
queries.

Run: python -X utf8 seed_clean_kindergartens.py
"""
import io
import os
import random
import sqlite3
import sys
import uuid
from datetime import date, datetime, timedelta, timezone
from typing import List, Tuple

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")
sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding="utf-8", errors="replace")
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import openpyxl
from sqlalchemy import func
from sqlalchemy.orm import Session

from database import SessionLocal
import models
from models import (
    Class, DailyReportStatus, EnrollmentApplication, EnrollmentStatus,
    GovernanceScore, Incident, IncidentType, Kindergarten, KindergartenStatus,
    SeverityLevel,
)

random.seed(42)

EXCEL_PATH = r"C:\Users\waelj\OneDrive - zuj.edu.jo\Desktop\Project-Kinjo-seed\DATS\Dataset_kinjo_jordan_reviewed_deduped.xlsx"
DB_PATH = r"D:\Final Version\data\kinjo.db"

GOV_MAP = {
    "عمان":    "عمان",
    "إربد":    "إربد",
    "الزرقاء": "الزرقاء",
    "البلقاء": "البلقاء",
    "عجلون":   "عجلون",
    "العقبة":  "العقبة",
    "مادبا":   "مادبا",
    "الكرك":   "الكرك",
    "الرمثا":  "إربد",
    "السلط":   "البلقاء",
    "الجبيهة": "عمان",
}

GOV_CENTERS = {
    "عمان":    (31.95, 35.95),
    "إربد":    (32.55, 35.85),
    "الزرقاء": (32.07, 36.10),
    "المفرق":  (32.34, 36.20),
    "جرش":     (32.28, 35.90),
    "عجلون":   (32.33, 35.75),
    "البلقاء": (32.04, 35.78),
    "مادبا":   (31.72, 35.79),
    "الكرك":   (31.18, 35.70),
    "الطفيلة": (30.83, 35.60),
    "معان":    (30.20, 35.73),
    "العقبة":  (29.53, 35.00),
}

SYNTHETIC_KGS = [
    ("حضانة المفرق الحديثة",  "Mafraq Modern KG",       "المفرق",  "المفرق",  "المركز",  "شارع الأردن"),
    ("حضانة الأمل - المفرق", "Al Amal Nursery Mafraq", "المفرق",  "المفرق",  "الغربي",  "شارع الوحدة"),
    ("حضانة الريحان",          "Al Raihan KG",           "المفرق",  "رحاب",    "الشمالي", "شارع الملك"),
    ("حضانة النجمة - المفرق", "Al Najma Mafraq",        "المفرق",  "المفرق",  "المركز",  "شارع القدس"),
    ("حضانة السنابل - المفرق", "Al Sanabel Mafraq",      "المفرق",  "المفرق",  "الجنوبي", "شارع الحرية"),
    ("حضانة جرش الأهلية",     "Jerash National KG",      "جرش",     "جرش",     "المدينة", "شارع الملك حسين"),
    ("حضانة الروابي - جرش",  "Al Rawabi Jerash",        "جرش",     "جرش",     "الجنوبي", "شارع الاستقلال"),
    ("حضانة الزيتون",          "Al Zaytoun KG",          "جرش",     "برما",    "الشرقي",  "شارع الوحدة"),
    ("حضانة الفرح - جرش",    "Al Farah Jerash",         "جرش",     "جرش",     "الشمالي", "شارع العلوم"),
    ("حضانة العلياء - جرش",   "Al Ulia Jerash",          "جرش",     "جرش",     "المركز",  "شارع الأردن"),
    ("حضانة الطفيلة الوطنية", "Tafileh National KG",     "الطفيلة", "الطفيلة", "المركز",  "شارع الملك حسين"),
    ("حضانة البتراء",         "Al Batra Nursery",       "الطفيلة", "الطفيلة", "الغربي",  "شارع القدس"),
    ("حضانة الحوراء",          "Al Hawraa KG",           "الطفيلة", "بصيرا",   "المدينة", "شارع الوحدة"),
    ("حضانة الأجيال - طفيلة","Al Ajyal Tafileh",        "الطفيلة", "الطفيلة", "الشمالي", "شارع الأردن"),
    ("حضانة معان الحديثة",    "Maan Modern KG",          "معان",    "معان",    "المركز",  "شارع الملك عبدالله"),
    ("حضانة الواحة - معان",  "Al Waha Maan",            "معان",    "معان",    "الغربي",  "شارع الاستقلال"),
    ("حضانة القوافل",          "Al Qawafil KG",          "معان",    "الشوبك",  "المدينة", "شارع الحسين"),
    ("حضانة النور - معان",   "Al Nour Maan",            "معان",    "معان",    "الجنوبي", "شارع التحرير"),
]

AGE_GROUPS = [
    ("KG1",     "KG1",     "AGE_2_4", 24,  48),
    ("KG2",     "KG2",     "AGE_2_4", 36,  60),
    ("Nursery", "حضانة",   "AGE_1_2", 12,  24),
]

GOVERNANCE_BANDS = ["A", "A", "B", "B", "B", "C"]


def log(msg):
    print(f"[{datetime.now().strftime('%H:%M:%S')}] {msg}")


def _jitter(lat, lng, r=0.04):
    return lat + random.uniform(-r, r), lng + random.uniform(-r, r)


def _working_days(start: date, end: date) -> List[date]:
    days, d = [], start
    while d <= end:
        if d.weekday() not in (4, 5):  # skip Fri/Sat
            days.append(d)
        d += timedelta(days=1)
    return days


# ── Step 1: Kindergartens ─────────────────────────────────────────────────────
def seed_kindergartens(db: Session) -> List[Kindergarten]:
    log("Loading Excel …")
    wb = openpyxl.load_workbook(EXCEL_PATH, read_only=True)
    ws = wb["Merged"]
    rows = list(ws.iter_rows(values_only=True))
    headers = list(rows[0])
    col = {h: i for i, h in enumerate(headers)}

    existing = {(kg.name_ar, kg.governorate) for kg in db.query(Kindergarten).all()}
    inserted = 0

    for row in rows[1:]:
        name_ar = (str(row[col["اسم الحضانة (عربي)"]]).strip() if row[col["اسم الحضانة (عربي)"]] else "")
        gov_raw = (str(row[col["المحافظة"]]).strip() if row[col["المحافظة"]] else "")
        gov = GOV_MAP.get(gov_raw, gov_raw)
        if not name_ar or not gov:
            continue
        if (name_ar, gov) in existing:
            continue
        name_en = (str(row[col["اسم الحضانة (إنجليزي)"]]).strip() if row[col["اسم الحضانة (إنجليزي)"]] else name_ar)
        city   = (str(row[col["المدينة"]]).strip()            if row[col["المدينة"]]            else gov)
        area   = (str(row[col["المنطقة"]]).strip()            if row[col["المنطقة"]]            else city)
        addr   = (str(row[col["العنوان التفصيلي"]]).strip()   if row[col["العنوان التفصيلي"]]   else gov)
        center = GOV_CENTERS.get(gov)
        lat, lng = (_jitter(*center) if center else (None, None))
        db.add(Kindergarten(
            name_ar=name_ar, name_en=name_en,
            governorate=gov, district=city, area=area, address_line=addr,
            contact_phone="N/A", latitude=lat, longitude=lng,
            status=KindergartenStatus.ACTIVE,
        ))
        existing.add((name_ar, gov))
        inserted += 1
        if inserted % 200 == 0:
            db.commit()

    for name_ar, name_en, gov, city, area, addr in SYNTHETIC_KGS:
        if (name_ar, gov) in existing:
            continue
        center = GOV_CENTERS.get(gov)
        lat, lng = (_jitter(*center) if center else (None, None))
        db.add(Kindergarten(
            name_ar=name_ar, name_en=name_en,
            governorate=gov, district=city, area=area, address_line=addr,
            contact_phone="N/A", latitude=lat, longitude=lng,
            status=KindergartenStatus.ACTIVE,
        ))
        existing.add((name_ar, gov))
        inserted += 1

    db.commit()
    total = db.query(Kindergarten).count()
    log(f"✓ Kindergartens: +{inserted} inserted, total={total}")
    return db.query(Kindergarten).filter(Kindergarten.id > 3).all()


# ── Step 2: Classes ───────────────────────────────────────────────────────────
def seed_classes(db: Session, kindergartens: List[Kindergarten]) -> None:
    log("Seeding classes …")
    inserted = 0
    for kg in kindergartens:
        n = random.randint(1, 3)
        for i in range(n):
            name_en, name_ar, age_grp, mn, mx = AGE_GROUPS[i]
            code = f"C-{kg.id}-{i+1}"
            db.add(Class(
                kindergarten_id=kg.id,
                name_ar=name_ar,
                name_en=name_en,
                class_code=code,
                age_group=age_grp,
                capacity_total=random.randint(15, 25),
                min_age_months=mn,
                max_age_months=mx,
                is_active=True,
            ))
            inserted += 1
        if inserted % 500 == 0:
            db.commit()
    db.commit()
    log(f"✓ Classes: {inserted}")


# ── Step 3: Enrollments (children proxy) ─────────────────────────────────────
def seed_enrollments(db: Session, kindergartens: List[Kindergarten]) -> None:
    """
    Each kindergarten gets 10-25 ACTIVE enrollment rows.
    child_id cycles 1-4; FK not enforced in SQLite.
    """
    log("Seeding enrollment applications …")
    inserted = 0
    FAKE_CHILD_IDS = [1, 2, 3, 4]

    # Resolve class_id per kindergarten from already-seeded classes
    kg_class = {
        row[0]: row[1]
        for row in db.query(Class.kindergarten_id, Class.id).all()
    }

    conn = sqlite3.connect(DB_PATH)
    cur = conn.cursor()
    batch = []
    for kg in kindergartens:
        cls_id = kg_class.get(kg.id)
        n = random.randint(10, 25)
        for j in range(n):
            child_id = FAKE_CHILD_IDS[j % len(FAKE_CHILD_IDS)]
            batch.append((str(uuid.uuid4()), child_id, kg.id, cls_id, "ACTIVE", 1, "WEB"))
            inserted += 1
        if len(batch) >= 2000:
            cur.executemany(
                "INSERT OR IGNORE INTO enrollment_applications "
                "(public_id,child_id,kindergarten_id,class_id,status,is_active,source) "
                "VALUES (?,?,?,?,?,?,?)",
                batch,
            )
            conn.commit()
            batch = []
    if batch:
        cur.executemany(
            "INSERT OR IGNORE INTO enrollment_applications "
            "(public_id,child_id,kindergarten_id,class_id,status,is_active,source) "
            "VALUES (?,?,?,?,?,?,?)",
            batch,
        )
        conn.commit()
    conn.close()
    log(f"✓ Enrollments: {inserted}")


# ── Step 4: Daily reports (last 45 working days) ──────────────────────────────
def seed_daily_reports(db: Session, kindergartens: List[Kindergarten]) -> None:
    """
    1 report per working day per kindergarten (submission rate ~87%).
    child_id=1 and submitted_by=5 (admin) — FK not enforced.
    """
    log("Seeding daily reports (45 working days) …")
    today = date.today()
    wdays = _working_days(today - timedelta(days=63), today)  # ~45 work days
    inserted = 0

    conn = sqlite3.connect(DB_PATH)
    cur = conn.cursor()
    batch = []
    for kg in kindergartens:
        for d in wdays:
            if random.random() > 0.13:  # 87% submit rate
                batch.append((
                    1,           # child_id (fake)
                    d.isoformat(),
                    "SUBMITTED",
                    5,           # submitted_by (admin)
                    datetime.now(timezone.utc).isoformat(),
                    "08:00",     # arrival_time
                    "14:00",     # leave_time (NOT NULL)
                    kg.id,       # kindergarten_id
                ))
                inserted += 1
        if len(batch) >= 2000:
            cur.executemany(
                "INSERT INTO daily_reports "
                "(child_id, date, status, submitted_by, submitted_at, arrival_time, leave_time, kindergarten_id) "
                "VALUES (?,?,?,?,?,?,?,?)",
                batch,
            )
            conn.commit()
            batch = []

    if batch:
        cur.executemany(
            "INSERT INTO daily_reports "
            "(child_id, date, status, submitted_by, submitted_at, arrival_time, leave_time, kindergarten_id) "
            "VALUES (?,?,?,?,?,?,?,?)",
            batch,
        )
        conn.commit()
    conn.close()
    log(f"✓ Daily reports: {inserted}")


# ── Step 5: Incidents ─────────────────────────────────────────────────────────
def seed_incidents(db: Session, kindergartens: List[Kindergarten]) -> None:
    log("Seeding incidents …")
    today = datetime.now(timezone.utc)
    inc_types  = ["HEALTH", "BEHAVIORAL", "ACCIDENT"]
    severities = ["LOW", "LOW", "LOW", "MEDIUM", "MEDIUM", "HIGH"]
    inserted = 0

    conn = sqlite3.connect(DB_PATH)
    cur = conn.cursor()
    batch = []
    for kg in kindergartens:
        n = random.choices([0, 1, 2, 3], weights=[0.40, 0.35, 0.18, 0.07])[0]
        for _ in range(n):
            occ = today - timedelta(days=random.randint(0, 89))
            sev = random.choice(severities)
            batch.append((
                1,                          # child_id (fake)
                kg.id,
                random.choice(inc_types),
                sev,
                "حادثة موثقة",
                occ.isoformat(),
                0 if sev == "LOW" else 1,  # followup_required_flag
            ))
            inserted += 1
    cur.executemany(
        "INSERT OR IGNORE INTO incidents "
        "(child_id, kindergarten_id, type, severity_level, description, occurred_at, followup_required_flag) "
        "VALUES (?,?,?,?,?,?,?)",
        batch,
    )
    conn.commit()
    conn.close()
    log(f"✓ Incidents: {inserted}")


# ── Step 6: Governance scores ─────────────────────────────────────────────────
def seed_governance(db: Session, kindergartens: List[Kindergarten]) -> None:
    log("Seeding governance scores …")
    inserted = 0
    p_start = date(2026, 1, 1)
    p_end   = date(2026, 6, 30)
    for kg in kindergartens:
        gqi   = round(random.uniform(50, 95), 1)
        cxi   = round(random.uniform(50, 90), 1)
        final = round((gqi * 0.6 + cxi * 0.4), 1)
        band  = random.choice(GOVERNANCE_BANDS)
        db.add(GovernanceScore(
            kindergarten_id=kg.id,
            period_start=p_start,
            period_end=p_end,
            governance_quality_index=gqi,
            child_experience_index=cxi,
            final_governance_score=final,
            band=band,
        ))
        inserted += 1
        if inserted % 200 == 0:
            db.commit()
    db.commit()
    log(f"✓ Governance scores: {inserted}")


# ── Main ──────────────────────────────────────────────────────────────────────
def main():
    log("=" * 60)
    log("COMPREHENSIVE SEED")
    log("=" * 60)
    db = SessionLocal()
    try:
        kgs = seed_kindergartens(db)
        seed_classes(db, kgs)
        seed_enrollments(db, kgs)
        seed_daily_reports(db, kgs)
        seed_incidents(db, kgs)
        seed_governance(db, kgs)

        log("")
        log("=" * 60)
        log("FINAL COUNTS")
        log("=" * 60)
        conn = sqlite3.connect(DB_PATH)
        cur = conn.cursor()
        for tbl in ["kindergartens", "classes", "enrollment_applications",
                    "daily_reports", "incidents", "governance_scores"]:
            cur.execute(f"SELECT COUNT(*) FROM {tbl}")
            log(f"  {tbl}: {cur.fetchone()[0]}")
        conn.close()
        log("=" * 60)
    finally:
        db.close()


if __name__ == "__main__":
    main()
