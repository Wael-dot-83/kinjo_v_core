"""Import kindergarten records from Excel into the real kindergartens table.

The script is intentionally idempotent:
- dry-run by default
- layered duplicate matching
- no blank Excel values overwrite non-empty database values
- all writes happen in one transaction
- reports are written for both dry-run and commit runs
"""

from __future__ import annotations

import argparse
import csv
import json
import logging
import os
import re
import sys
import unicodedata
from dataclasses import dataclass, field
from datetime import date, datetime
from decimal import Decimal, InvalidOperation
from pathlib import Path
from typing import Any

import pandas as pd
from sqlalchemy import func
from sqlalchemy.orm import Session

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

import models  # noqa: E402
from config import settings  # noqa: E402
from database import SessionLocal  # noqa: E402


LOGGER = logging.getLogger("kindergarten_excel_import")

DEFAULT_FILE_CANDIDATES = [
    "Kindergarten_updated_fINAL.xlsx",
    "Kindergarten_updated_fiNAL.xlsx",
    "Kindergarten_updated_FINAL.xlsx",
    "Kindergarten_updated_fINAL.xls",
    "Kindergarten_updated_fINAL.xlxs",
]

INVISIBLE_RE = re.compile(r"[\u200b-\u200f\u202a-\u202e\u2066-\u2069\ufeff]")
DIACRITICS_RE = re.compile(r"[\u064b-\u065f\u0670]")
SPACE_RE = re.compile(r"\s+")
EMAIL_RE = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")

MISSING_DB_TEXT = "غير محدد"
MISSING_PHONE_TEXT = "غير متوفر"

GOVERNORATE_CANONICAL = {
    "amman": "عمان",
    "عمان": "عمان",
    "irbid": "إربد",
    "إربد": "إربد",
    "اربد": "إربد",
    "zarqa": "الزرقاء",
    "zarqaa": "الزرقاء",
    "الزرقاء": "الزرقاء",
    "الزرقا": "الزرقاء",
    "balqa": "البلقاء",
    "balqa governorate": "البلقاء",
    "البلقاء": "البلقاء",
    "السلط": "البلقاء",
    "madaba": "مادبا",
    "مادبا": "مادبا",
    "karak": "الكرك",
    "al karak": "الكرك",
    "الكرك": "الكرك",
    "tafilah": "الطفيلة",
    "tafila": "الطفيلة",
    "al tafilah": "الطفيلة",
    "الطفيلة": "الطفيلة",
    "معان": "معان",
    "maan": "معان",
    "ma'an": "معان",
    "aqaba": "العقبة",
    "al aqaba": "العقبة",
    "العقبة": "العقبة",
    "jerash": "جرش",
    "جرش": "جرش",
    "ajloun": "عجلون",
    "ajlun": "عجلون",
    "عجلون": "عجلون",
    "mafraq": "المفرق",
    "al mafraq": "المفرق",
    "المفرق": "المفرق",
}

LANDLINE_AREA_CODE_BY_GOV = {
    "عمان": "06",
    "الزرقاء": "05",
    "البلقاء": "05",
    "مادبا": "05",
    "إربد": "02",
    "جرش": "02",
    "عجلون": "02",
    "المفرق": "02",
    "الكرك": "03",
    "الطفيلة": "03",
    "معان": "03",
    "العقبة": "03",
}

COLUMN_ALIASES = {
    "id": "id",
    "kindergarten_id": "id",
    "kg_id": "id",
    "رقم": "id",
    "المعرف": "id",
    "name_ar": "name_ar",
    "arabic_name": "name_ar",
    "kindergarten_name_ar": "name_ar",
    "اسم الروضة": "name_ar",
    "اسم الروضة عربي": "name_ar",
    "اسم الروضة (عربي)": "name_ar",
    "اسم الروضة باللغة العربية": "name_ar",
    "name_en": "name_en",
    "english_name": "name_en",
    "kindergarten_name_en": "name_en",
    "اسم الروضة انجليزي": "name_en",
    "اسم الروضة (إنجليزي)": "name_en",
    "اسم الروضة باللغة الإنجليزية": "name_en",
    "governorate": "governorate",
    "المحافظة": "governorate",
    "city": "city",
    "المدينة": "city",
    "district": "area",
    "area": "area",
    "المنطقة": "area",
    "الحي": "area",
    "address": "address_line",
    "address_line": "address_line",
    "detailed_address": "address_line",
    "العنوان": "address_line",
    "العنوان التفصيلي": "address_line",
    "phone": "contact_phone",
    "contact_phone": "contact_phone",
    "mobile": "contact_phone",
    "telephone": "contact_phone",
    "رقم الهاتف": "contact_phone",
    "الهاتف": "contact_phone",
    "email": "contact_email",
    "contact_email": "contact_email",
    "البريد الإلكتروني": "contact_email",
    "license": "license_number",
    "license_number": "license_number",
    "registration_number": "license_number",
    "رقم الترخيص": "license_number",
    "رقم التسجيل": "license_number",
    "license_valid_until": "license_valid_until",
    "license_expiry": "license_valid_until",
    "تاريخ انتهاء الترخيص": "license_valid_until",
    "status": "status",
    "الحالة": "status",
    "operating_hours_start": "operating_hours_start",
    "وقت بدء الدوام": "operating_hours_start",
    "operating_hours_end": "operating_hours_end",
    "وقت انتهاء الدوام": "operating_hours_end",
    "latitude": "latitude",
    "lat": "latitude",
    "خط العرض": "latitude",
    "longitude": "longitude",
    "lng": "longitude",
    "long": "longitude",
    "خط الطول": "longitude",
    "manager": "manager_name",
    "manager_name": "manager_name",
    "اسم المدير": "manager_name",
}

MODEL_FIELDS = {
    "name_ar",
    "name_en",
    "governorate",
    "city",
    "area",
    "address_line",
    "contact_phone",
    "contact_email",
    "status",
    "operating_hours_start",
    "operating_hours_end",
    "license_number",
    "license_valid_until",
}


@dataclass
class PreparedRow:
    excel_row: int
    raw: dict[str, Any]
    payload: dict[str, Any]
    match: dict[str, str]
    extra: dict[str, Any] = field(default_factory=dict)


@dataclass
class Candidate:
    key: str
    kind: str
    id: int | None
    excel_row: int | None
    payload: dict[str, Any]
    match: dict[str, str]


@dataclass
class ImportPlan:
    mode: str
    file_path: str
    sheet_name: str
    sheet_names: list[str]
    raw_columns: list[str]
    normalized_columns: dict[str, str]
    total_rows: int
    empty_rows: int
    total_before: int
    created: list[dict[str, Any]] = field(default_factory=list)
    updated: list[dict[str, Any]] = field(default_factory=list)
    skipped: list[dict[str, Any]] = field(default_factory=list)
    ambiguous: list[dict[str, Any]] = field(default_factory=list)
    invalid: list[dict[str, Any]] = field(default_factory=list)
    duplicate_checks: dict[str, Any] = field(default_factory=dict)
    unmapped_source_columns: list[str] = field(default_factory=list)
    report_dir: str | None = None
    total_after: int | None = None

    @property
    def valid_rows(self) -> int:
        return len(self.created) + len(self.updated) + len(self.skipped)


def _json_default(value: Any) -> str | None:
    if isinstance(value, (date, datetime)):
        return value.isoformat()
    if isinstance(value, Decimal):
        return str(value)
    if pd.isna(value):
        return None
    return str(value)


def clean_display_text(value: Any) -> str:
    if value is None or pd.isna(value):
        return ""
    text = str(value)
    if text.endswith(".0") and re.fullmatch(r"\d+\.0", text):
        text = text[:-2]
    text = unicodedata.normalize("NFKC", text)
    text = INVISIBLE_RE.sub("", text)
    text = text.replace("\u0640", "")
    text = SPACE_RE.sub(" ", text).strip()
    text = re.sub(r"\s+([،؛:,.])", r"\1", text)
    text = re.sub(r"([،؛:,.])(?=\S)", r"\1 ", text)
    return text.strip()


def normalize_arabic_for_match(value: Any) -> str:
    text = clean_display_text(value)
    text = DIACRITICS_RE.sub("", text)
    text = text.replace("أ", "ا").replace("إ", "ا").replace("آ", "ا").replace("ٱ", "ا")
    text = text.replace("ى", "ي").replace("ئ", "ي")
    text = text.replace("ة", "ه")
    text = text.lower()
    text = re.sub(r"[^\w\s\u0600-\u06ff]", " ", text)
    return SPACE_RE.sub(" ", text).strip()


def normalize_generic_for_match(value: Any) -> str:
    text = normalize_arabic_for_match(value)
    return unicodedata.normalize("NFKC", text).casefold()


def normalize_column_name(value: Any) -> str:
    text = clean_display_text(value).replace("_", " ").replace("-", " ")
    text = text.replace("أ", "ا").replace("إ", "ا").replace("آ", "ا").replace("ٱ", "ا")
    text = text.replace("ى", "ي")
    text = re.sub(r"[()\/\\]+", " ", text)
    return SPACE_RE.sub(" ", text).strip().casefold()


def normalize_digits(value: Any) -> str:
    text = clean_display_text(value)
    digit_map = str.maketrans("٠١٢٣٤٥٦٧٨٩۰۱۲۳۴۵۶۷۸۹", "01234567890123456789")
    return text.translate(digit_map)


def normalize_phone(value: Any, governorate: str | None = None) -> tuple[str | None, str | None]:
    original = clean_display_text(value)
    if not original:
        return None, None

    text = normalize_digits(original)
    text = re.sub(r"(?:ext|extension|تحويلة).*", "", text, flags=re.IGNORECASE).strip()
    text = re.sub(r"[\s\-().]", "", text)
    text = text.replace("٠", "0")

    if text.endswith(".0") and text[:-2].isdigit():
        text = text[:-2]

    if text.startswith("+962"):
        text = "0" + text[4:]
    elif text.startswith("00962"):
        text = "0" + text[5:]
    elif text.startswith("962"):
        text = "0" + text[3:]

    if text.startswith("7") and len(text) == 9:
        text = "0" + text

    canonical_gov = normalize_governorate(governorate) if governorate else None
    if text.isdigit() and len(text) == 7 and canonical_gov in LANDLINE_AREA_CODE_BY_GOV:
        text = LANDLINE_AREA_CODE_BY_GOV[canonical_gov] + text
    elif text.isdigit() and len(text) == 8 and text[0] in {"2", "3", "5", "6"}:
        text = "0" + text

    if re.fullmatch(r"07\d{8}", text) or re.fullmatch(r"0[2356]\d{7}", text):
        return text, None

    return None, f"invalid phone format: {original}"


def normalize_governorate(value: Any) -> str | None:
    text = clean_display_text(value)
    if not text:
        return None
    key = normalize_generic_for_match(text)
    aliases = {normalize_generic_for_match(k): v for k, v in GOVERNORATE_CANONICAL.items()}
    return aliases.get(key, text)


def parse_optional_date(value: Any) -> tuple[date | None, str | None]:
    if value is None or pd.isna(value) or clean_display_text(value) == "":
        return None, None
    try:
        parsed = pd.to_datetime(value, errors="raise")
    except (ValueError, TypeError, OverflowError) as exc:
        return None, f"invalid date: {value} ({exc})"
    return parsed.date(), None


def parse_optional_coordinate(value: Any, field_name: str) -> tuple[float | None, str | None]:
    text = normalize_digits(value)
    if not text:
        return None, None
    try:
        number = float(text)
    except (ValueError, TypeError):
        return None, f"invalid {field_name}: {value}"
    if field_name == "latitude" and not -90 <= number <= 90:
        return None, f"latitude out of range: {value}"
    if field_name == "longitude" and not -180 <= number <= 180:
        return None, f"longitude out of range: {value}"
    return number, None


def normalize_status(value: Any) -> tuple[models.KindergartenStatus | None, str | None]:
    text = clean_display_text(value)
    if not text:
        return None, None
    key = normalize_generic_for_match(text)
    active = {"active", "نشط", "فعاله", "فعال", "ساري", "مفعله"}
    inactive = {"inactive", "غير نشط", "متوقف", "مغلق", "مغلقه", "غير فعاله"}
    draft = {"draft", "مسوده", "قيد الادخال"}
    if key in {normalize_generic_for_match(v) for v in active}:
        return models.KindergartenStatus.ACTIVE, None
    if key in {normalize_generic_for_match(v) for v in inactive}:
        return models.KindergartenStatus.INACTIVE, None
    if key in {normalize_generic_for_match(v) for v in draft}:
        return models.KindergartenStatus.DRAFT, None
    return None, f"invalid status: {text}"


def map_column(raw_column: Any) -> str | None:
    normalized = normalize_column_name(raw_column)
    if not normalized or normalized.startswith("unnamed"):
        return None

    alias_map = {normalize_column_name(k): v for k, v in COLUMN_ALIASES.items()}
    if normalized in alias_map:
        return alias_map[normalized]

    compact = normalized.replace(" ", "")
    for key, target in alias_map.items():
        if compact == key.replace(" ", ""):
            return target
    return None


def find_excel_file(path_value: str) -> Path:
    requested = Path(path_value)
    if requested.exists():
        if requested.suffix.lower() == ".xlxs":
            corrected = requested.with_suffix(".xlsx")
            if corrected.exists():
                raise FileNotFoundError(
                    f"Requested file uses .xlxs but .xlsx exists: {corrected}. "
                    "Please rerun with the corrected path."
                )
        return requested

    search_dir = requested.parent if requested.parent.exists() else Path.cwd()
    candidates = []
    for name in DEFAULT_FILE_CANDIDATES:
        candidate = search_dir / name
        if candidate.exists():
            candidates.append(candidate)

    if candidates:
        raise FileNotFoundError(
            "Requested Excel file was not found. Closest matching file(s): "
            + ", ".join(str(path) for path in candidates)
        )

    raise FileNotFoundError(f"Excel file not found: {requested}")


def select_sheet(excel: pd.ExcelFile, requested_sheet: str | None = None) -> tuple[str, int]:
    if requested_sheet:
        if requested_sheet not in excel.sheet_names:
            raise ValueError(f"Sheet '{requested_sheet}' not found. Available sheets: {excel.sheet_names}")
        return requested_sheet, 0

    best_sheet = excel.sheet_names[0]
    best_header = 0
    best_score = -1
    best_rows = -1
    for sheet_name in excel.sheet_names:
        preview = pd.read_excel(excel, sheet_name=sheet_name, header=None, nrows=12)
        for idx, row in preview.iterrows():
            mapped = [map_column(value) for value in row.tolist()]
            score = len([field_name for field_name in mapped if field_name])
            rows = len(pd.read_excel(excel, sheet_name=sheet_name, header=idx).dropna(how="all"))
            if score > best_score or (score == best_score and rows > best_rows):
                best_sheet = sheet_name
                best_header = int(idx)
                best_score = score
                best_rows = rows
    return best_sheet, best_header


def read_excel_rows(file_path: Path, sheet_name: str | None = None) -> tuple[pd.DataFrame, dict[str, Any]]:
    excel = pd.ExcelFile(file_path)
    selected_sheet, header_row = select_sheet(excel, sheet_name)
    df = pd.read_excel(excel, sheet_name=selected_sheet, header=header_row)
    raw_columns = [clean_display_text(column) for column in df.columns]

    mapped_columns: dict[str, str] = {}
    renamed: dict[Any, str] = {}
    seen: set[str] = set()
    unmapped: list[str] = []
    for column in df.columns:
        raw = clean_display_text(column)
        mapped = map_column(raw)
        if mapped and mapped not in seen:
            renamed[column] = mapped
            mapped_columns[raw] = mapped
            seen.add(mapped)
        else:
            safe_raw = raw or "unnamed"
            extra_name = f"extra_{normalize_column_name(safe_raw).replace(' ', '_') or len(unmapped)}"
            renamed[column] = extra_name
            if raw:
                unmapped.append(raw)

    df = df.rename(columns=renamed)
    metadata = {
        "sheet_names": excel.sheet_names,
        "selected_sheet": selected_sheet,
        "header_row": header_row + 1,
        "raw_columns": raw_columns,
        "mapped_columns": mapped_columns,
        "unmapped_columns": unmapped,
    }
    return df, metadata


def prepare_row(row: pd.Series, excel_row: int) -> tuple[PreparedRow | None, dict[str, Any] | None]:
    raw = {str(key): _json_default(value) for key, value in row.to_dict().items()}
    if all(clean_display_text(value) == "" for value in row.to_dict().values()):
        return None, None

    errors: list[str] = []
    warnings: list[str] = []
    payload: dict[str, Any] = {}
    extra: dict[str, Any] = {}
    match_phone = ""

    for text_field in ("name_ar", "name_en", "city", "area", "address_line", "license_number"):
        value = clean_display_text(row.get(text_field))
        if value:
            payload[text_field] = value

    governorate = normalize_governorate(row.get("governorate"))
    if governorate:
        payload["governorate"] = governorate

    phone, phone_error = normalize_phone(row.get("contact_phone"), governorate)
    if phone:
        payload["contact_phone"] = phone
        match_phone = phone
    elif phone_error:
        raw_phone = clean_display_text(row.get("contact_phone"))
        warnings.append(phone_error)
        if raw_phone:
            extra["contact_phone_original"] = raw_phone

    email = clean_display_text(row.get("contact_email")).lower()
    if email:
        if EMAIL_RE.fullmatch(email):
            payload["contact_email"] = email
        else:
            errors.append(f"invalid email: {email}")

    for time_field in ("operating_hours_start", "operating_hours_end"):
        value = clean_display_text(row.get(time_field))
        if value:
            payload[time_field] = value

    license_date, date_error = parse_optional_date(row.get("license_valid_until"))
    if license_date:
        payload["license_valid_until"] = license_date
    elif date_error:
        errors.append(date_error)

    status_value, status_error = normalize_status(row.get("status"))
    if status_value:
        payload["status"] = status_value
    elif status_error:
        errors.append(status_error)

    for coord_field in ("latitude", "longitude"):
        coordinate, coordinate_error = parse_optional_coordinate(row.get(coord_field), coord_field)
        if coordinate is not None:
            extra[coord_field] = coordinate
        elif coordinate_error:
            errors.append(coordinate_error)

    manager_name = clean_display_text(row.get("manager_name"))
    if manager_name:
        extra["manager_name"] = manager_name

    if warnings:
        extra["warnings"] = warnings

    if not payload.get("name_ar") and not payload.get("name_en"):
        errors.append("missing Arabic or English kindergarten name")

    if not payload.get("governorate") and not payload.get("address_line"):
        errors.append("missing governorate and address; not enough location data")

    if errors:
        return None, {"excel_row": excel_row, "errors": errors, "raw": raw}

    match = {
        "id": clean_display_text(row.get("id")),
        "license_number": normalize_generic_for_match(payload.get("license_number")),
        "name_ar": normalize_arabic_for_match(payload.get("name_ar")),
        "name_en": normalize_generic_for_match(payload.get("name_en")),
        "governorate": normalize_generic_for_match(payload.get("governorate")),
        "city": normalize_generic_for_match(payload.get("city")),
        "area": normalize_generic_for_match(payload.get("area")),
        "address_line": normalize_generic_for_match(payload.get("address_line")),
        "contact_phone": match_phone,
    }
    return PreparedRow(excel_row=excel_row, raw=raw, payload=payload, match=match, extra=extra), None


def candidate_from_kindergarten(kg: models.Kindergarten) -> Candidate:
    payload = {
        "name_ar": kg.name_ar,
        "name_en": kg.name_en,
        "governorate": kg.governorate,
        "city": kg.city,
        "area": kg.area,
        "address_line": kg.address_line,
        "contact_phone": kg.contact_phone,
        "contact_email": kg.contact_email,
        "status": kg.status,
        "operating_hours_start": kg.operating_hours_start,
        "operating_hours_end": kg.operating_hours_end,
        "license_number": kg.license_number,
        "license_valid_until": kg.license_valid_until,
    }
    match = {
        "id": str(kg.id),
        "license_number": normalize_generic_for_match(kg.license_number),
        "name_ar": normalize_arabic_for_match(kg.name_ar),
        "name_en": normalize_generic_for_match(kg.name_en),
        "governorate": normalize_generic_for_match(kg.governorate),
        "city": normalize_generic_for_match(kg.city),
        "area": normalize_generic_for_match(kg.area),
        "address_line": normalize_generic_for_match(kg.address_line),
        "contact_phone": normalize_phone(kg.contact_phone, kg.governorate)[0] or "",
    }
    return Candidate(key=f"db:{kg.id}", kind="db", id=kg.id, excel_row=None, payload=payload, match=match)


def make_candidate_from_prepared(row: PreparedRow) -> Candidate:
    return Candidate(
        key=f"excel:{row.excel_row}",
        kind="planned_create",
        id=None,
        excel_row=row.excel_row,
        payload=row.payload.copy(),
        match=row.match.copy(),
    )


def build_indexes(candidates: list[Candidate]) -> dict[str, dict[Any, list[Candidate]]]:
    indexes: dict[str, dict[Any, list[Candidate]]] = {
        "id": {},
        "license_number": {},
        "name_ar_governorate": {},
        "name_ar_city_area": {},
        "name_ar_address": {},
        "contact_phone": {},
        "name_en_governorate": {},
    }

    def add(index_name: str, key: Any, candidate: Candidate) -> None:
        if key is None or key == "" or key == ("", "") or key == ("", "", ""):
            return
        indexes[index_name].setdefault(key, []).append(candidate)

    for candidate in candidates:
        add("id", candidate.match.get("id"), candidate)
        add("license_number", candidate.match.get("license_number"), candidate)
        add("name_ar_governorate", (candidate.match.get("name_ar"), candidate.match.get("governorate")), candidate)
        add(
            "name_ar_city_area",
            (candidate.match.get("name_ar"), candidate.match.get("city"), candidate.match.get("area")),
            candidate,
        )
        add("name_ar_address", (candidate.match.get("name_ar"), candidate.match.get("address_line")), candidate)
        add("contact_phone", candidate.match.get("contact_phone"), candidate)
        add("name_en_governorate", (candidate.match.get("name_en"), candidate.match.get("governorate")), candidate)
    return indexes


def find_match(row: PreparedRow, indexes: dict[str, dict[Any, list[Candidate]]]) -> tuple[str, list[Candidate]]:
    rules: list[tuple[str, Any]] = [
        ("id", row.match.get("id")),
        ("license_number", row.match.get("license_number")),
        ("name_ar_governorate", (row.match.get("name_ar"), row.match.get("governorate"))),
        ("name_ar_city_area", (row.match.get("name_ar"), row.match.get("city"), row.match.get("area"))),
        ("name_ar_address", (row.match.get("name_ar"), row.match.get("address_line"))),
        ("contact_phone", row.match.get("contact_phone")),
        ("name_en_governorate", (row.match.get("name_en"), row.match.get("governorate"))),
    ]
    for rule_name, key in rules:
        if key is None or key == "" or key == ("", "") or key == ("", "", ""):
            continue
        candidates = indexes[rule_name].get(key, [])
        if candidates:
            return rule_name, candidates
    return "no_match", []


def non_empty_update_payload(prepared: PreparedRow, existing: models.Kindergarten | Candidate) -> dict[str, Any]:
    existing_payload = existing.payload if isinstance(existing, Candidate) else candidate_from_kindergarten(existing).payload
    changes: dict[str, Any] = {}
    for field_name, value in prepared.payload.items():
        if field_name not in MODEL_FIELDS:
            continue
        if value is None or value == "":
            continue
        old_value = existing_payload.get(field_name)
        if hasattr(old_value, "value"):
            old_value = old_value.value
        compare_value = value.value if hasattr(value, "value") else value
        if isinstance(old_value, date):
            old_value = old_value.isoformat()
        if isinstance(compare_value, date):
            compare_value = compare_value.isoformat()
        if old_value != compare_value:
            changes[field_name] = value
    return changes


def create_payload(prepared: PreparedRow) -> dict[str, Any]:
    payload = prepared.payload.copy()
    payload.setdefault("governorate", MISSING_DB_TEXT)
    payload.setdefault("city", payload.get("governorate") or MISSING_DB_TEXT)
    payload.setdefault("area", MISSING_DB_TEXT)
    payload.setdefault("address_line", MISSING_DB_TEXT)
    payload.setdefault("contact_phone", prepared.extra.get("contact_phone_original") or MISSING_PHONE_TEXT)
    payload.setdefault("status", models.KindergartenStatus.ACTIVE)
    if not payload.get("name_ar"):
        payload["name_ar"] = payload.get("name_en")
    return {key: value for key, value in payload.items() if key in MODEL_FIELDS}


def build_import_plan(
    db: Session,
    file_path: Path,
    *,
    mode: str,
    sheet_name: str | None = None,
) -> ImportPlan:
    df, metadata = read_excel_rows(file_path, sheet_name)
    total_before = db.query(func.count(models.Kindergarten.id)).scalar() or 0
    plan = ImportPlan(
        mode=mode,
        file_path=str(file_path),
        sheet_name=metadata["selected_sheet"],
        sheet_names=metadata["sheet_names"],
        raw_columns=metadata["raw_columns"],
        normalized_columns=metadata["mapped_columns"],
        total_rows=len(df),
        empty_rows=0,
        total_before=total_before,
        unmapped_source_columns=metadata["unmapped_columns"],
    )

    existing_candidates = [candidate_from_kindergarten(kg) for kg in db.query(models.Kindergarten).all()]
    candidates = existing_candidates.copy()
    matched_existing_rows: dict[int, int] = {}

    for dataframe_index, row in df.iterrows():
        excel_row = int(dataframe_index) + int(metadata["header_row"]) + 1
        prepared, invalid = prepare_row(row, excel_row)
        if prepared is None and invalid is None:
            plan.empty_rows += 1
            plan.skipped.append({"excel_row": excel_row, "reason": "empty_row"})
            continue
        if invalid:
            plan.invalid.append(invalid)
            continue

        assert prepared is not None
        indexes = build_indexes(candidates)
        rule_name, matches = find_match(prepared, indexes)
        unique_matches = list({match.key: match for match in matches}.values())

        if len(unique_matches) > 1:
            plan.ambiguous.append(
                {
                    "excel_row": excel_row,
                    "reason": f"ambiguous {rule_name}",
                    "source": prepared.payload,
                    "possible_matches": [
                        {
                            "candidate": match.key,
                            "id": match.id,
                            "excel_row": match.excel_row,
                            "name_ar": match.payload.get("name_ar"),
                            "governorate": match.payload.get("governorate"),
                            "city": match.payload.get("city"),
                            "phone": match.payload.get("contact_phone"),
                            "license_number": match.payload.get("license_number"),
                        }
                        for match in unique_matches
                    ],
                }
            )
            continue

        if len(unique_matches) == 1:
            match = unique_matches[0]
            if match.kind == "planned_create":
                plan.skipped.append(
                    {
                        "excel_row": excel_row,
                        "reason": f"duplicate_of_excel_row_{match.excel_row}",
                        "matched_by": rule_name,
                        "source": prepared.payload,
                    }
                )
                continue

            if match.id in matched_existing_rows:
                plan.skipped.append(
                    {
                        "excel_row": excel_row,
                        "reason": f"duplicate_of_excel_row_{matched_existing_rows[match.id]}",
                        "matched_by": rule_name,
                        "matched_id": match.id,
                        "source": prepared.payload,
                    }
                )
                continue

            changes = non_empty_update_payload(prepared, match)
            if changes:
                plan.updated.append(
                    {
                        "excel_row": excel_row,
                        "id": match.id,
                        "matched_by": rule_name,
                        "name_ar": match.payload.get("name_ar"),
                        "changes": changes,
                        "source": prepared.payload,
                        "extra": prepared.extra,
                    }
                )
                matched_existing_rows[match.id] = excel_row
            else:
                plan.skipped.append(
                    {
                        "excel_row": excel_row,
                        "reason": "no_changes",
                        "matched_by": rule_name,
                        "matched_id": match.id,
                        "source": prepared.payload,
                    }
                )
                matched_existing_rows[match.id] = excel_row
            continue

        new_payload = create_payload(prepared)
        plan.created.append(
            {
                "excel_row": excel_row,
                "payload": new_payload,
                "source": prepared.payload,
                "extra": prepared.extra,
            }
        )
        candidates.append(make_candidate_from_prepared(PreparedRow(excel_row, prepared.raw, new_payload, prepared.match, prepared.extra)))

    plan.duplicate_checks = duplicate_check_summary(db)
    return plan


def apply_import_plan(db: Session, plan: ImportPlan) -> None:
    for item in plan.updated:
        kg = db.query(models.Kindergarten).filter(models.Kindergarten.id == item["id"]).one()
        for field_name, value in item["changes"].items():
            setattr(kg, field_name, value)

    for item in plan.created:
        db.add(models.Kindergarten(**item["payload"]))


def _normalized_db_rows(db: Session) -> list[dict[str, Any]]:
    rows = []
    for kg in db.query(models.Kindergarten).all():
        normalized_phone, _ = normalize_phone(kg.contact_phone, kg.governorate)
        rows.append(
            {
                "id": kg.id,
                "license_number": normalize_generic_for_match(kg.license_number),
                "phone": normalized_phone or "",
                "name_governorate": (
                    normalize_arabic_for_match(kg.name_ar),
                    normalize_generic_for_match(kg.governorate),
                ),
            }
        )
    return rows


def _find_duplicates(rows: list[dict[str, Any]], field_name: str) -> list[dict[str, Any]]:
    buckets: dict[Any, list[int]] = {}
    for row in rows:
        value = row[field_name]
        if not value or value == ("", ""):
            continue
        buckets.setdefault(value, []).append(row["id"])
    return [
        {"value": str(value), "ids": ids}
        for value, ids in sorted(buckets.items(), key=lambda item: str(item[0]))
        if len(ids) > 1
    ]


def duplicate_check_summary(db: Session) -> dict[str, Any]:
    rows = _normalized_db_rows(db)
    return {
        "duplicate_license_numbers": _find_duplicates(rows, "license_number"),
        "duplicate_normalized_phones": _find_duplicates(rows, "phone"),
        "duplicate_name_governorate": _find_duplicates(rows, "name_governorate"),
    }


def is_production_like_database() -> bool:
    url = settings.DATABASE_URL.lower()
    env = settings.ENVIRONMENT.lower()
    return env == "production" or "production" in url or re.search(r"(^|[^a-z])prod([^a-z]|$)", url) is not None


def redact_database_url(url: str) -> str:
    return re.sub(r"://([^:/@]+):([^@]+)@", r"://\1:***@", url)


def write_csv(path: Path, rows: list[dict[str, Any]], fieldnames: list[str]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8-sig", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames, extrasaction="ignore")
        writer.writeheader()
        for row in rows:
            flat = {}
            for key in fieldnames:
                value = row.get(key)
                if isinstance(value, (dict, list)):
                    value = json.dumps(value, ensure_ascii=False, default=_json_default)
                elif hasattr(value, "value"):
                    value = value.value
                elif isinstance(value, (date, datetime)):
                    value = value.isoformat()
                flat[key] = value
            writer.writerow(flat)


def write_reports(plan: ImportPlan, report_base_dir: Path) -> Path:
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    report_dir = report_base_dir / f"kindergarten_import_{timestamp}_{plan.mode}"
    report_dir.mkdir(parents=True, exist_ok=False)
    plan.report_dir = str(report_dir)

    summary = {
        "mode": plan.mode,
        "file_path": plan.file_path,
        "sheet_names": plan.sheet_names,
        "selected_sheet": plan.sheet_name,
        "raw_columns": plan.raw_columns,
        "normalized_columns": plan.normalized_columns,
        "unmapped_source_columns": plan.unmapped_source_columns,
        "database_url": redact_database_url(settings.DATABASE_URL),
        "environment": settings.ENVIRONMENT,
        "testing": settings.TESTING,
        "total_rows": plan.total_rows,
        "valid_rows": plan.valid_rows,
        "created": len(plan.created),
        "updated": len(plan.updated),
        "skipped": len(plan.skipped),
        "ambiguous": len(plan.ambiguous),
        "invalid": len(plan.invalid),
        "empty_rows": plan.empty_rows,
        "total_before": plan.total_before,
        "total_after": plan.total_after,
        "duplicate_checks": plan.duplicate_checks,
        "generated_at": datetime.now().isoformat(timespec="seconds"),
    }
    (report_dir / "import_summary.json").write_text(
        json.dumps(summary, ensure_ascii=False, indent=2, default=_json_default),
        encoding="utf-8",
    )

    write_csv(
        report_dir / "created_kindergartens.csv",
        [
            {
                "excel_row": item["excel_row"],
                **item["payload"],
                "source": item["source"],
                "extra": item.get("extra"),
            }
            for item in plan.created
        ],
        [
            "excel_row",
            "name_ar",
            "name_en",
            "governorate",
            "city",
            "area",
            "address_line",
            "contact_phone",
            "contact_email",
            "status",
            "license_number",
            "license_valid_until",
            "source",
            "extra",
        ],
    )
    write_csv(
        report_dir / "updated_kindergartens.csv",
        plan.updated,
        ["excel_row", "id", "matched_by", "name_ar", "changes", "source", "extra"],
    )
    write_csv(report_dir / "skipped_rows.csv", plan.skipped, ["excel_row", "reason", "matched_by", "matched_id", "source"])
    write_csv(
        report_dir / "ambiguous_matches.csv",
        plan.ambiguous,
        ["excel_row", "reason", "source", "possible_matches"],
    )
    write_csv(report_dir / "invalid_rows.csv", plan.invalid, ["excel_row", "errors", "raw"])
    return report_dir


def run_import(
    *,
    file_path: Path,
    mode: str,
    report_dir: Path,
    sheet_name: str | None = None,
    confirm_production: bool = False,
    db: Session | None = None,
) -> ImportPlan:
    owns_session = db is None
    session = db or SessionLocal()
    try:
        if mode == "commit" and is_production_like_database() and not confirm_production:
            raise RuntimeError(
                "Refusing commit because the database target looks production-like. "
                "Pass --confirm-production only after verifying the target."
            )

        plan = build_import_plan(session, file_path, mode=mode, sheet_name=sheet_name)
        LOGGER.info("Sheet names: %s", plan.sheet_names)
        LOGGER.info("Selected sheet: %s", plan.sheet_name)
        LOGGER.info("Columns: %s", plan.raw_columns)
        LOGGER.info(
            "Dry plan: rows=%s create=%s update=%s skip=%s ambiguous=%s invalid=%s",
            plan.total_rows,
            len(plan.created),
            len(plan.updated),
            len(plan.skipped),
            len(plan.ambiguous),
            len(plan.invalid),
        )

        if mode == "commit":
            apply_import_plan(session, plan)
            session.flush()
            plan.total_after = session.query(func.count(models.Kindergarten.id)).scalar() or 0
            plan.duplicate_checks = duplicate_check_summary(session)
            duplicate_blockers = (
                plan.duplicate_checks["duplicate_license_numbers"]
                or plan.duplicate_checks["duplicate_normalized_phones"]
                or plan.duplicate_checks["duplicate_name_governorate"]
            )
            if duplicate_blockers:
                raise RuntimeError(f"Duplicate check failed after import: {duplicate_blockers}")
            session.commit()
            LOGGER.info("Import committed.")
        else:
            session.rollback()
            plan.total_after = plan.total_before

        write_reports(plan, report_dir)
        return plan
    except Exception:
        session.rollback()
        raise
    finally:
        if owns_session:
            session.close()


def print_summary(plan: ImportPlan) -> None:
    print(json.dumps(
        {
            "mode": plan.mode,
            "file": plan.file_path,
            "sheet": plan.sheet_name,
            "total_rows": plan.total_rows,
            "valid_rows": plan.valid_rows,
            "created": len(plan.created),
            "updated": len(plan.updated),
            "skipped": len(plan.skipped),
            "ambiguous": len(plan.ambiguous),
            "invalid": len(plan.invalid),
            "total_before": plan.total_before,
            "total_after": plan.total_after,
            "report_dir": plan.report_dir,
        },
        ensure_ascii=False,
        indent=2,
        default=_json_default,
    ))


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Import kindergarten records from Excel into KinJo.")
    parser.add_argument("--file", required=True, help="Excel file path")
    parser.add_argument("--sheet", default=None, help="Optional sheet name")
    parser.add_argument("--report-dir", default="reports/imports", help="Directory for import reports")
    parser.add_argument("--dry-run", action="store_true", help="Validate and report without writing")
    parser.add_argument("--commit", action="store_true", help="Write valid creates/updates to the database")
    parser.add_argument("--confirm-production", action="store_true", help="Allow commit against production-like DB URL")
    return parser.parse_args()


def main() -> int:
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    args = parse_args()
    if args.dry_run and args.commit:
        print("Choose only one mode: --dry-run or --commit", file=sys.stderr)
        return 2
    mode = "commit" if args.commit else "dry-run"
    try:
        file_path = find_excel_file(args.file)
        plan = run_import(
            file_path=file_path,
            mode=mode,
            report_dir=Path(args.report_dir),
            sheet_name=args.sheet,
            confirm_production=args.confirm_production,
        )
        print_summary(plan)
        return 0
    except Exception as exc:
        LOGGER.exception("Kindergarten Excel import failed")
        print(f"Import failed: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
