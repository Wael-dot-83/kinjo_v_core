"""
Seed the app database (data/kinjo.db) from scripts/final_kindergartens_indexed.csv.
Skips duplicates (same name_ar + governorate).
Run once to populate kindergartens from the indexed pipeline output.
"""
import csv
import io
import os
import sys

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")
sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding="utf-8", errors="replace")

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from database import SessionLocal
from models import Kindergarten, KindergartenStatus

CSV_PATH = os.path.join(os.path.dirname(__file__), "scripts", "final_kindergartens_indexed.csv")

# Governorate centre coordinates for records without lat/lng
GOV_CENTERS = {
    "عمان":   (31.95, 35.95),
    "إربد":   (32.55, 35.85),
    "الزرقاء": (32.07, 36.10),
    "المفرق": (32.34, 36.20),
    "جرش":    (32.28, 35.90),
    "عجلون":  (32.33, 35.75),
    "البلقاء": (32.04, 35.78),
    "مادبا":  (31.72, 35.79),
    "الكرك":  (31.18, 35.70),
    "الطفيلة": (30.83, 35.60),
    "معان":   (30.20, 35.73),
    "العقبة": (29.53, 35.00),
}

# Column map: CSV_TO_DB (after Arabic→English mapping in CSV)
# The pipeline stored the kindergarten_index in the last column
COL = {
    "name_ar":           "name_ar",
    "name_en":           "name_en",
    "governorate":       "governorate",
    "city":              "city",
    "area":              "area",
    "address_line":      "address_line",
    "kindergarten_index": "kindergarten_index",
}

ARABIC_TO_DB = {
    "اسم الروضة (عربي)":   "name_ar",
    "اسم الروضة (إنجليزي)": "name_en",
    "المحافظة":             "governorate",
    "المدينة":              "city",
    "المنطقة":              "area",
    "العنوان التفصيلي":     "address_line",
    "رقم الهاتف":           "kindergarten_index",
}


def main():
    if not os.path.exists(CSV_PATH):
        print(f"ERROR: CSV not found at {CSV_PATH}")
        sys.exit(1)

    print(f"Reading {CSV_PATH} ...")
    with open(CSV_PATH, newline="", encoding="utf-8-sig") as f:
        reader = csv.DictReader(f)
        raw_rows = list(reader)

    # Translate Arabic headers to DB column names
    rows = [
        {ARABIC_TO_DB.get(k, k): v for k, v in row.items()}
        for row in raw_rows
    ]
    print(f"  {len(rows)} rows read")

    db = SessionLocal()
    try:
        # Build existing set for dedup (name_ar + governorate)
        existing = set(
            db.query(Kindergarten.name_ar, Kindergarten.governorate).all()
        )
        print(f"  {len(existing)} kindergartens already in DB")

        inserted = 0
        skipped_dup = 0
        skipped_empty = 0

        for row in rows:
            name_ar = (row.get("name_ar") or "").strip()
            governorate = (row.get("governorate") or "").strip()

            if not name_ar or not governorate:
                skipped_empty += 1
                continue

            if (name_ar, governorate) in existing:
                skipped_dup += 1
                continue

            name_en = (row.get("name_en") or "").strip() or None
            city = (row.get("city") or "").strip() or governorate
            area = (row.get("area") or "").strip() or city
            address_line = (row.get("address_line") or "").strip() or governorate
            kg_index = (row.get("kindergarten_index") or "").strip() or None

            lat, lng = GOV_CENTERS.get(governorate, (None, None))

            kg = Kindergarten(
                name_ar=name_ar,
                name_en=name_en,
                governorate=governorate,
                district=city,
                area=area,
                address_line=address_line,
                contact_phone="N/A",
                latitude=lat,
                longitude=lng,
                status=KindergartenStatus.ACTIVE,
                license_number=kg_index,  # store index as license for uniqueness
            )
            db.add(kg)
            existing.add((name_ar, governorate))
            inserted += 1

            if inserted % 500 == 0:
                db.commit()
                print(f"  ... {inserted} inserted so far")

        db.commit()

        total = db.query(Kindergarten).count()
        print()
        print("=" * 60)
        print("  SEED SUMMARY")
        print("=" * 60)
        print(f"  Inserted:       {inserted}")
        print(f"  Skipped (dup):  {skipped_dup}")
        print(f"  Skipped (empty):{skipped_empty}")
        print(f"  Total in DB:    {total}")
        print("=" * 60)

    except Exception as e:
        db.rollback()
        print(f"ERROR: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)
    finally:
        db.close()


if __name__ == "__main__":
    main()
