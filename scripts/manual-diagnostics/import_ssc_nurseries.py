"""Import official SSC approved nurseries into the local app database.

The source page is the Social Security Corporation list of approved nurseries
for care requests. This script is intentionally idempotent: records are matched
by their SSC source row license number first, then by normalized Arabic name.
"""

from __future__ import annotations

import argparse
import json
import re
import sys
import time
import unicodedata
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import requests
from bs4 import BeautifulSoup

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

import models
from database import SessionLocal


SSC_URL = (
    "https://www.ssc.gov.jo/"
    "%D8%A7%D9%84%D8%AD%D8%B6%D8%A7%D9%86%D8%A7%D8%AA-"
    "%D8%A7%D9%84%D9%85%D8%B9%D8%AA%D9%85%D8%AF%D8%A9-"
    "%D9%84%D8%B7%D9%84%D8%A8%D8%A7%D8%AA-"
    "%D8%A7%D9%84%D8%B1%D8%B9%D8%A7%D9%8A%D8%A9/"
)

UA = "KinJo local nursery importer/1.0 (admin data maintenance)"
CACHE_PATH = ROOT / ".tmp" / "ssc_nursery_geocode_cache.json"

GOV_CENTERS = {
    "عمان": (31.9539, 35.9106),
    "إربد": (32.5556, 35.8500),
    "الزرقاء": (32.0833, 36.1000),
    "البلقاء": (32.0333, 35.7333),
    "مادبا": (31.7167, 35.8000),
    "الكرك": (31.1853, 35.7047),
    "الطفيلة": (30.8333, 35.6000),
    "معان": (30.1962, 35.7341),
    "العقبة": (29.5320, 35.0063),
    "جرش": (32.2808, 35.8993),
    "عجلون": (32.3333, 35.7528),
    "المفرق": (32.3429, 36.2080),
}

BRANCH_TO_LOCATION = {
    "عمان": ("عمان", "عمان"),
    "اليوبيل": ("عمان", "عمان"),
    "اربد": ("إربد", "إربد"),
    "إربد": ("إربد", "إربد"),
    "عجلون": ("عجلون", "عجلون"),
    "السلط": ("البلقاء", "السلط"),
    "الزرقاء": ("الزرقاء", "الزرقاء"),
    "مادبا": ("مادبا", "مادبا"),
    "الكرك": ("الكرك", "الكرك"),
    "الطفيلة": ("الطفيلة", "الطفيلة"),
    "معان": ("معان", "معان"),
    "العقبة": ("العقبة", "العقبة"),
    "جرش": ("جرش", "جرش"),
    "المفرق": ("المفرق", "المفرق"),
}

PLACEHOLDER_NAME_RE = re.compile(
    r"^حضانة (عمان|إربد|اربد|الزرقاء|البلقاء|السلط|مادبا|الكرك|الطفيلة|معان|العقبة|جرش|عجلون|المفرق) \d+$"
)
SAMPLE_RECORDS = {
    ("حضانة الأمل", "0791234567"),
    ("حضانة النجوم", "0798765432"),
}


@dataclass
class NurseryRow:
    source_row: int
    name: str
    address: str
    phone: str
    branch: str
    governorate: str
    district: str
    area: str


def clean_text(value: str | None) -> str:
    if not value:
        return ""
    text = unicodedata.normalize("NFKC", value)
    text = re.sub(r"[\u200b-\u200f\u202a-\u202e\u2066-\u2069\ufeff]", "", text)
    return " ".join(text.split()).strip()


def normalize_for_match(value: str | None) -> str:
    text = clean_text(value)
    text = re.sub(r"[\u064b-\u065f\u0670ـ]", "", text)
    text = text.replace("أ", "ا").replace("إ", "ا").replace("آ", "ا")
    text = text.replace("ى", "ي").replace("ة", "ه")
    text = re.sub(r"[^\w\s\u0600-\u06ff]", " ", text)
    return " ".join(text.split()).lower()


def infer_location(branch: str, address: str) -> tuple[str, str]:
    text = f"{branch} {address}"
    for token, location in BRANCH_TO_LOCATION.items():
        if token in text:
            return location
    return "عمان", "عمان"


def infer_area(address: str, district: str) -> str:
    address = clean_text(address)
    if not address:
        return district
    first = re.split(r"[/،,\-–_]", address, maxsplit=1)[0]
    first = clean_text(first)
    return first[:100] if first else district


def normalize_phone(raw: str, governorate: str, row_num: int) -> str:
    raw = clean_text(raw)
    if not raw or raw.upper() == "NULL":
        return f"غير متوفر-{row_num:03d}"
    digits = re.sub(r"\D", "", raw)
    if not digits:
        return f"غير متوفر-{row_num:03d}"
    if digits.startswith("962"):
        return "+" + digits
    if len(digits) == 9 and digits.startswith("7"):
        return "0" + digits
    if len(digits) == 7:
        area_code = "02" if governorate in {"إربد", "عجلون", "جرش", "المفرق"} else "06"
        return area_code + digits
    return digits[:20]


def fetch_ssc_rows() -> list[NurseryRow]:
    response = requests.get(SSC_URL, timeout=30, headers={"User-Agent": UA})
    response.raise_for_status()
    soup = BeautifulSoup(response.text, "html.parser")

    rows: list[NurseryRow] = []
    source_row = 1
    for tr in soup.find_all("tr"):
        cells = [clean_text(c.get_text(" ", strip=True)) for c in tr.find_all(["td", "th"])]
        if len(cells) < 4 or cells[0] == "اسم الحضانه":
            continue
        source_row += 1
        name, address, phone, branch = cells[:4]
        if not name:
            continue
        governorate, district = infer_location(branch, address)
        rows.append(
            NurseryRow(
                source_row=source_row,
                name=name,
                address=address,
                phone=normalize_phone(phone, governorate, source_row),
                branch=branch,
                governorate=governorate,
                district=district,
                area=infer_area(address, district),
            )
        )
    return rows


def load_cache() -> dict[str, Any]:
    if CACHE_PATH.exists():
        return json.loads(CACHE_PATH.read_text(encoding="utf-8"))
    return {}


def save_cache(cache: dict[str, Any]) -> None:
    CACHE_PATH.parent.mkdir(parents=True, exist_ok=True)
    CACHE_PATH.write_text(json.dumps(cache, ensure_ascii=False, indent=2), encoding="utf-8")


def geocode_row(row: NurseryRow, cache: dict[str, Any], delay: float) -> tuple[float, float, str]:
    query = f"{row.name}, {row.address}, {row.district}, {row.governorate}, Jordan"
    cache_key = normalize_for_match(query)
    cached = cache.get(cache_key)
    if cached:
        return cached["lat"], cached["lon"], cached["source"]

    try:
        response = requests.get(
            "https://nominatim.openstreetmap.org/search",
            params={"q": query, "format": "json", "limit": 1, "countrycodes": "jo"},
            headers={"User-Agent": UA},
            timeout=20,
        )
        response.raise_for_status()
        results = response.json()
        if results:
            lat = float(results[0]["lat"])
            lon = float(results[0]["lon"])
            cache[cache_key] = {"lat": lat, "lon": lon, "source": "nominatim"}
            time.sleep(delay)
            return lat, lon, "nominatim"
    except requests.RequestException:
        pass

    lat, lon = GOV_CENTERS[row.governorate]
    cache[cache_key] = {"lat": lat, "lon": lon, "source": "governorate_fallback"}
    time.sleep(delay)
    return lat, lon, "governorate_fallback"


def is_generated_placeholder(kg: models.Kindergarten) -> bool:
    name = kg.name_ar or ""
    phone = kg.contact_phone or ""
    if PLACEHOLDER_NAME_RE.match(name):
        return True
    return (name, phone) in SAMPLE_RECORDS


def import_rows(rows: list[NurseryRow], commit: bool, geocode: bool, replace_generated: bool) -> dict[str, int]:
    cache = load_cache()
    db = SessionLocal()
    created = updated = skipped = soft_deleted = geocoded = fallback = 0
    try:
        if replace_generated:
            for kg in db.query(models.Kindergarten).all():
                if kg.status != models.KindergartenStatus.DELETED and is_generated_placeholder(kg):
                    kg.status = models.KindergartenStatus.DELETED
                    soft_deleted += 1

        existing_by_license = {
            kg.license_number: kg
            for kg in db.query(models.Kindergarten).filter(models.Kindergarten.license_number.like("SSC-%")).all()
            if kg.license_number
        }
        existing_by_name = {
            normalize_for_match(kg.name_ar): kg
            for kg in db.query(models.Kindergarten).filter(models.Kindergarten.status != models.KindergartenStatus.DELETED).all()
        }

        for row in rows:
            license_number = f"SSC-{row.source_row:04d}"
            kg = existing_by_license.get(license_number) or existing_by_name.get(normalize_for_match(row.name))
            if geocode:
                lat, lon, coord_source = geocode_row(row, cache, delay=1.0)
                if coord_source == "nominatim":
                    geocoded += 1
                else:
                    fallback += 1
            else:
                lat, lon = GOV_CENTERS[row.governorate]
                coord_source = "governorate_fallback"
                fallback += 1

            notes = f"Source: SSC approved nurseries page ({SSC_URL}); branch: {row.branch}; coordinates: {coord_source}"
            payload = {
                "name_ar": row.name,
                "name_en": None,
                "governorate": row.governorate,
                "district": row.district,
                "area": row.area,
                "address_line": row.address or row.district,
                "contact_phone": row.phone,
                "latitude": lat,
                "longitude": lon,
                "license_number": license_number,
                "license_status": "approved_ssc",
                "administrative_notes": notes,
                "status": models.KindergartenStatus.DRAFT,
            }
            if kg:
                changed = False
                for key, value in payload.items():
                    if getattr(kg, key) != value:
                        setattr(kg, key, value)
                        changed = True
                updated += 1 if changed else 0
                skipped += 0 if changed else 1
            else:
                db.add(models.Kindergarten(**payload))
                created += 1

        if commit:
            db.commit()
            save_cache(cache)
        else:
            db.rollback()
        return {
            "source_rows": len(rows),
            "created": created,
            "updated": updated,
            "skipped": skipped,
            "soft_deleted_generated": soft_deleted,
            "geocoded": geocoded,
            "coordinate_fallback": fallback,
        }
    except Exception:
        db.rollback()
        raise
    finally:
        db.close()


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--commit", action="store_true", help="Write changes to the database")
    parser.add_argument("--geocode", action="store_true", help="Resolve coordinates through Nominatim")
    parser.add_argument("--replace-generated", action="store_true", help="Soft-delete generated placeholder records")
    args = parser.parse_args()

    rows = fetch_ssc_rows()
    result = import_rows(rows, commit=args.commit, geocode=args.geocode, replace_generated=args.replace_generated)
    print(json.dumps({"commit": args.commit, **result}, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
