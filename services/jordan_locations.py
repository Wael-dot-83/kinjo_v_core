"""Canonical Jordan location data source.

Single source of truth for governorates and areas/cities, independent of kindergarten records.
"""

from __future__ import annotations

from typing import Any, Dict, List, Optional


GOVERNORATES: List[Dict[str, Any]] = [
    {
        "key": "amman",
        "name_ar": "عمان",
        "name_en": "Amman",
        "aliases": [
            "amman", "عمان", "العاصمة", "عاصمة", "Amman", "AMMAN",
        ],
    },
    {
        "key": "irbid",
        "name_ar": "إربد",
        "name_en": "Irbid",
        "aliases": [
            "irbid", "إربد", "Irbid", "IRBID",
        ],
    },
    {
        "key": "zarqa",
        "name_ar": "الزرقاء",
        "name_en": "Zarqa",
        "aliases": [
            "zarqa", "الزرقاء", "zarqaa", "Zarqa", "ZARQA",
        ],
    },
    {
        "key": "mafraq",
        "name_ar": "المفرق",
        "name_en": "Mafraq",
        "aliases": [
            "mafraq", "المفرق", "Mafraq", "MAFRAQ",
        ],
    },
    {
        "key": "jerash",
        "name_ar": "جرش",
        "name_en": "Jerash",
        "aliases": [
            "jerash", "جرش", "Jerash", "JERASH",
        ],
    },
    {
        "key": "ajloun",
        "name_ar": "عجلون",
        "name_en": "Ajloun",
        "aliases": [
            "ajloun", "عجلون", "Ajloun", "AJLOUN",
        ],
    },
    {
        "key": "karak",
        "name_ar": "الكرك",
        "name_en": "Karak",
        "aliases": [
            "karak", "الكرك", "Karak", "KARAK",
        ],
    },
    {
        "key": "tafilah",
        "name_ar": "الطفيلة",
        "name_en": "Tafilah",
        "aliases": [
            "tafilah", "الطفيلة", "tafila", "Tafilah", "TAFILAH",
        ],
    },
    {
        "key": "maan",
        "name_ar": "معان",
        "name_en": "Ma'an",
        "aliases": [
            "maan", "معان", "ma'an", "Ma'an", "MAAN",
        ],
    },
    {
        "key": "aqaba",
        "name_ar": "العقبة",
        "name_en": "Aqaba",
        "aliases": [
            "aqaba", "العقبة", "Aqaba", "AQABA",
        ],
    },
    {
        "key": "madaba",
        "name_ar": "مادبا",
        "name_en": "Madaba",
        "aliases": [
            "madaba", "مادبا", "Madaba", "MADABA",
        ],
    },
    {
        "key": "balqa",
        "name_ar": "البلقاء",
        "name_en": "Balqa",
        "aliases": [
            "balqa", "البلقاء", "salt", "السلط", "Balqa", "BALQA",
        ],
    },
]

AREAS: Dict[str, List[Dict[str, Any]]] = {
    "amman": [
        {"key": "amman", "name_ar": "عمان", "name_en": "Amman", "aliases": ["amman", "عمان", "Amman"]},
        {"key": "jubeiha", "name_ar": "الجبيهة", "name_en": "Jubeiha", "aliases": ["jubeiha", "الجبيهة"]},
        {"key": "quwaysimah", "name_ar": "القويسمة", "name_en": "Quwaysimah", "aliases": ["quwaysimah", "القويسمة"]},
        {"key": "wadi_alsir", "name_ar": "وادي السير", "name_en": "Wadi Al-Sir", "aliases": ["wadi_alsir", "وادي السير", "وادي السير"]},
        {"key": "swailih", "name_ar": "صويلح", "name_en": "Swailih", "aliases": ["swailih", "صويلح"]},
        {"key": "marka", "name_ar": "ماركا", "name_en": "Marka", "aliases": ["marka", "ماركا"]},
        {"key": "abu_nusayr", "name_ar": "أبو نصير", "name_en": "Abu Nusayr", "aliases": ["abu_nusayr", "أبو نصير"]},
        {"key": "tabarbur", "name_ar": "طبربور", "name_en": "Tabarbur", "aliases": ["tabarbur", "طبربور"]},
    ],
    "irbid": [
        {"key": "irbid", "name_ar": "إربد", "name_en": "Irbid", "aliases": ["irbid", "إربد"]},
        {"key": "al_husn", "name_ar": "الحصن", "name_en": "Al-Husn", "aliases": ["al_husn", "الحصن"]},
        {"key": "ramtha", "name_ar": "الرمثا", "name_en": "Ramtha", "aliases": ["ramtha", "الرمثا"]},
        {"key": "al_kura", "name_ar": "الكورة", "name_en": "Al-Kura", "aliases": ["al_kura", "الكورة"]},
        {"key": "bani_kananah", "name_ar": "بني كنانة", "name_en": "Bani Kananah", "aliases": ["bani_kananah", "بني كنانة"]},
        {"key": "al_aghwar_ash_shamaliyah", "name_ar": "الأغوار الشمالية", "name_en": "Northern Jordan Valley", "aliases": ["al_aghwar_ash_shamaliyah", "الأغوار الشمالية"]},
    ],
    "zarqa": [
        {"key": "zarqa", "name_ar": "الزرقاء", "name_en": "Zarqa", "aliases": ["zarqa", "الزرقاء"]},
        {"key": "al_rasifah", "name_ar": "الرصيفة", "name_en": "Al-Rasifah", "aliases": ["al_rasifah", "الرصيفة"]},
        {"key": "al_hashimiyah", "name_ar": "الهاشمية", "name_en": "Al-Hashimiyah", "aliases": ["al_hashimiyah", "الهاشمية"]},
        {"key": "al_azraq", "name_ar": "الأزرق", "name_en": "Al-Azraq", "aliases": ["al_azraq", "الأزرق"]},
    ],
    "aqaba": [
        {"key": "aqaba", "name_ar": "العقبة", "name_en": "Aqaba", "aliases": ["aqaba", "العقبة"]},
        {"key": "wadi_ram", "name_ar": "وادي رم", "name_en": "Wadi Rum", "aliases": ["wadi_ram", "وادي رم"]},
        {"key": "al_quwayrah", "name_ar": "القويرة", "name_en": "Al-Quwayrah", "aliases": ["al_quwayrah", "القويرة"]},
    ],
    "mafraq": [
        {"key": "mafraq", "name_ar": "المفرق", "name_en": "Mafraq", "aliases": ["mafraq", "المفرق"]},
        {"key": "al_badiyah_ash_shamaliyah", "name_ar": "البادية الشمالية", "name_en": "Northern Badia", "aliases": ["al_badiyah_ash_shamaliyah", "البادية الشمالية"]},
        {"key": "al_ruwayshid", "name_ar": "الروحاء", "name_en": "Al-Ruwayshid", "aliases": ["al_ruwayshid", "الروحاء"]},
    ],
    "jerash": [
        {"key": "jerash", "name_ar": "جرش", "name_en": "Jerash", "aliases": ["jerash", "جرش"]},
        {"key": "sawf", "name_ar": "سوف", "name_en": "Sawf", "aliases": ["sawf", "سوف"]},
        {"key": "al_kafarat", "name_ar": "الكفارات", "name_en": "Al-Kafarat", "aliases": ["al_kafarat", "الكفارات"]},
        {"key": "al_mustabah", "name_ar": "المصطبة", "name_en": "Al-Mustabah", "aliases": ["al_mustabah", "المصطبة"]},
    ],
    "ajloun": [
        {"key": "ajloun", "name_ar": "عجلون", "name_en": "Ajloun", "aliases": ["ajloun", "عجلون"]},
        {"key": "sakhrah", "name_ar": "صخرة", "name_en": "Sakhrah", "aliases": ["sakhrah", "صخرة"]},
        {"key": "anjarah", "name_ar": "عنجرة", "name_en": "Anjarah", "aliases": ["anjarah", "عنجرة"]},
        {"key": "kufranjah", "name_ar": "كفرنجة", "name_en": "Kufranjah", "aliases": ["kufranjah", "كفرنجة"]},
    ],
    "tafilah": [
        {"key": "tafilah", "name_ar": "الطفيلة", "name_en": "Tafilah", "aliases": ["tafilah", "الطفيلة"]},
        {"key": "basyirah", "name_ar": "بصيرا", "name_en": "Basyirah", "aliases": ["basyirah", "بصيرا"]},
        {"key": "al_hasa", "name_ar": "الحسا", "name_en": "Al-Hasa", "aliases": ["al_hasa", "الحسا"]},
    ],
    "karak": [
        {"key": "karak", "name_ar": "الكرك", "name_en": "Karak", "aliases": ["karak", "الكرك"]},
        {"key": "al_mazar_ash_shamali", "name_ar": "المزار الجنوبي", "name_en": "Al-Mazar Al-Janubi", "aliases": ["al_mazar_ash_shamali", "المزار الجنوبي"]},
        {"key": "ayy", "name_ar": "عي", "name_en": "Ayy", "aliases": ["ayy", "عي"]},
        {"key": "al_qasr", "name_ar": "القصر", "name_en": "Al-Qasr", "aliases": ["al_qasr", "القصر"]},
        {"key": "al_aghwar_ash_sharqiyah", "name_ar": "الأغوار الجنوبية", "name_en": "Southern Jordan Valley", "aliases": ["al_aghwar_ash_sharqiyah", "الأغوار الجنوبية"]},
    ],
    "maan": [
        {"key": "maan", "name_ar": "معان", "name_en": "Ma'an", "aliases": ["maan", "معان"]},
        {"key": "ash_shubak", "name_ar": "الشوبك", "name_en": "Ash-Shubak", "aliases": ["ash_shubak", "الشوبك"]},
        {"key": "al_tayyibah", "name_ar": "الطيبة", "name_en": "Al-Tayyibah", "aliases": ["al_tayyibah", "الطيبة"]},
        {"key": "wadi_musa", "name_ar": "وادي موسى", "name_en": "Wadi Musa", "aliases": ["wadi_musa", "وادي موسى"]},
    ],
    "balqa": [
        {"key": "salt", "name_ar": "السلط", "name_en": "Salt", "aliases": ["salt", "السلط"]},
        {"key": "ayn_al_basha", "name_ar": "عين الباشا", "name_en": "Ayn Al-Basha", "aliases": ["ayn_al_basha", "عين الباشا"]},
        {"key": "dayr_alla", "name_ar": "دير علا", "name_en": "Dayr Alla", "aliases": ["dayr_alla", "دير علا"]},
        {"key": "ash_shunah_ash_janubiyah", "name_ar": "الشونة الجنوبية", "name_en": "Ash-Shunah Ash-Janubiyah", "aliases": ["ash_shunah_ash_janubiyah", "الشونة الجنوبية"]},
    ],
    "madaba": [
        {"key": "madaba", "name_ar": "مادبا", "name_en": "Madaba", "aliases": ["madaba", "مادبا"]},
        {"key": "dhiban", "name_ar": "ذيبان", "name_en": "Dhiban", "aliases": ["dhiban", "ذيبان"]},
    ],
}

_GOVERNORATE_BY_KEY: Dict[str, Dict[str, Any]] = {g["key"]: g for g in GOVERNORATES}
_GOVERNORATE_BY_NAME_AR: Dict[str, Dict[str, Any]] = {g["name_ar"]: g for g in GOVERNORATES}
_GOVERNORATE_BY_NAME_EN: Dict[str, Dict[str, Any]] = {g["name_en"]: g for g in GOVERNORATES}

_AREA_MAP: Dict[str, Dict[str, List[Dict[str, Any]]]] = {}
for gov_key, areas in AREAS.items():
    area_by_key = {a["key"]: a for a in areas}
    area_by_name_ar = {a["name_ar"]: a for a in areas}
    area_by_name_en = {a["name_en"]: a for a in areas}
    _AREA_MAP[gov_key] = {
        "by_key": area_by_key,
        "by_name_ar": area_by_name_ar,
        "by_name_en": area_by_name_en,
    }


def get_all_governorates() -> List[Dict[str, Any]]:
    """Return all canonical governorates."""
    return list(GOVERNORATES)


def get_governorate_by_key(key: str) -> Optional[Dict[str, Any]]:
    """Return a governorate by canonical key."""
    return _GOVERNORATE_BY_KEY.get(key.lower())


def get_governorate_by_name(name: str, locale: str = "ar") -> Optional[Dict[str, Any]]:
    """Return a governorate by Arabic or English name."""
    if locale == "en":
        return _GOVERNORATE_BY_NAME_EN.get(name)
    return _GOVERNORATE_BY_NAME_AR.get(name)


def get_areas_for_governorate(governorate_key: str) -> List[Dict[str, Any]]:
    """Return all areas/cities for a governorate by canonical key."""
    return list(AREAS.get(governorate_key.lower(), []))


def get_area_by_key(governorate_key: str, area_key: str) -> Optional[Dict[str, Any]]:
    """Return an area by governorate key and area key."""
    areas = _AREA_MAP.get(governorate_key.lower(), {}).get("by_key", {})
    return areas.get(area_key.lower())


def get_area_by_name(governorate_key: str, area_name: str, locale: str = "ar") -> Optional[Dict[str, Any]]:
    """Return an area by governorate key and area name."""
    if locale == "en":
        areas = _AREA_MAP.get(governorate_key.lower(), {}).get("by_name_en", {})
    else:
        areas = _AREA_MAP.get(governorate_key.lower(), {}).get("by_name_ar", {})
    return areas.get(area_name)


def normalize_governorate(value: Optional[str]) -> Optional[str]:
    """Normalize a governorate value to its canonical Arabic name."""
    if not value:
        return None
    v = str(value).strip()
    if not v:
        return None
    v_lower = v.lower()
    for gov in GOVERNORATES:
        if v_lower in (alias.lower() for alias in gov["aliases"]):
            return gov["name_ar"]
    return v


def normalize_area(governorate_key: str, value: Optional[str]) -> Optional[str]:
    """Normalize an area value to its canonical Arabic name within a governorate."""
    if not value:
        return None
    v = str(value).strip()
    if not v:
        return None
    areas = AREAS.get(governorate_key.lower(), [])
    for area in areas:
        if v.lower() in (alias.lower() for alias in area["aliases"]):
            return area["name_ar"]
    return v


def is_valid_governorate(value: Optional[str]) -> bool:
    """Check if a value is a known governorate (canonical or alias)."""
    if not value:
        return False
    v = str(value).strip().lower()
    for gov in GOVERNORATES:
        if v in (alias.lower() for alias in gov["aliases"]):
            return True
    return False


def is_valid_area_for_governorate(governorate_key: str, value: Optional[str]) -> bool:
    """Check if a value is a known area for a specific governorate."""
    if not value:
        return False
    v = str(value).strip().lower()
    areas = AREAS.get(governorate_key.lower(), [])
    for area in areas:
        if v in (alias.lower() for alias in area["aliases"]):
            return True
    return False


def validate_governorate(value: Optional[str]) -> str:
    """Validate and return canonical Arabic governorate name, raise ValueError if invalid."""
    normalized = normalize_governorate(value)
    if not normalized or not is_valid_governorate(normalized):
        raise ValueError(f"Invalid governorate: {value}")
    return normalized


def validate_area_for_governorate(governorate_key: str, value: Optional[str]) -> str:
    """Validate and return canonical Arabic area name, raise ValueError if invalid."""
    if not value:
        return ""
    normalized = normalize_area(governorate_key, value)
    if not is_valid_area_for_governorate(governorate_key, normalized):
        raise ValueError(f"Invalid area for governorate {governorate_key}: {value}")
    return normalized


def validate_governorate_area_pair(governorate_value: Optional[str], area_value: Optional[str]) -> tuple[str, str]:
    """Validate a governorate+area pair and return canonical Arabic names."""
    gov_obj = None
    if governorate_value:
        v = str(governorate_value).strip().lower()
        for gov in GOVERNORATES:
            if v in (alias.lower() for alias in gov["aliases"]):
                gov_obj = gov
                break
    if not gov_obj:
        raise ValueError(f"Invalid governorate: {governorate_value}")
    area = validate_area_for_governorate(gov_obj["key"], area_value) if area_value else ""
    return gov_obj["name_ar"], area
