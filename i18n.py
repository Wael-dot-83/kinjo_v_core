"""Small gettext-style helpers for KinJo UI and API localization."""

from __future__ import annotations

import ast
from functools import lru_cache
from pathlib import Path
from typing import Any

from fastapi import Request


SUPPORTED_LANGUAGES = {"ar", "en"}
DEFAULT_LANGUAGE = "ar"
ROOT_DIR = Path(__file__).resolve().parent
LOCALE_DIR = ROOT_DIR / "locale"

ENROLLMENT_STATUS_AR = {
    "DRAFT": "مسودة",
    "SUBMITTED": "مقدّم",
    "PENDING_REVIEW": "قيد المراجعة",
    "PENDING": "قيد الانتظار",
    "APPROVED": "موافق عليه",
    "ACCEPTED": "مقبول",
    "REJECTED": "مرفوض",
    "WITHDRAWN": "منسحب",
    "WAITING": "قائمة الانتظار",
    "WAITLISTED": "قائمة الانتظار",
    "ACTIVE": "نشط",
}

ATTENDANCE_STATUS_AR = {
    "PRESENT": "حاضر",
    "ABSENT": "غائب",
    "LATE": "متأخر",
    "EXCUSED": "غياب بعذر",
    "SICK": "مريض",
}


def normalize_language(value: Any, default: str = DEFAULT_LANGUAGE) -> str:
    lang = str(value or "").strip().lower()
    return lang if lang in SUPPORTED_LANGUAGES else default


def _decode_po_string(line: str) -> str:
    try:
        return ast.literal_eval(line.strip())
    except (SyntaxError, ValueError):
        return ""


@lru_cache(maxsize=8)
def _load_catalog(language: str) -> dict[str, str]:
    language = normalize_language(language)
    if language == "en":
        return {}

    path = LOCALE_DIR / language / "LC_MESSAGES" / "messages.po"
    if not path.exists():
        return {}

    catalog: dict[str, str] = {}
    msgid_parts: list[str] = []
    msgstr_parts: list[str] = []
    state: str | None = None

    def flush() -> None:
        if not msgid_parts:
            return
        msgid = "".join(msgid_parts)
        msgstr = "".join(msgstr_parts)
        if msgid:
            catalog[msgid] = msgstr or msgid

    for raw_line in path.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#"):
            continue
        if line.startswith("msgid "):
            flush()
            msgid_parts = [_decode_po_string(line[6:])]
            msgstr_parts = []
            state = "msgid"
            continue
        if line.startswith("msgstr "):
            msgstr_parts = [_decode_po_string(line[7:])]
            state = "msgstr"
            continue
        if line.startswith('"'):
            if state == "msgid":
                msgid_parts.append(_decode_po_string(line))
            elif state == "msgstr":
                msgstr_parts.append(_decode_po_string(line))

    flush()
    return catalog


def gettext(message: Any, lang: str = "en", **kwargs: Any) -> str:
    text = str(message or "")
    language = normalize_language(lang, default="en")
    translated = _load_catalog(language).get(text, text) if language != "en" else text
    if kwargs:
        try:
            return translated.format(**kwargs)
        except (KeyError, IndexError, ValueError):
            return translated
    return translated


def make_gettext(language: str):
    safe_language = normalize_language(language)

    def translate(message: Any, **kwargs: Any) -> str:
        return gettext(message, lang=safe_language, **kwargs)

    return translate


def request_language(request: Request | None, default: str = "en") -> str:
    """Resolve explicit request language for API responses.

    API defaults to English unless the caller explicitly sends a UI language
    cookie, query parameter, or Accept-Language header.
    """
    if request is None:
        return normalize_language(default, default=default)

    explicit = request.query_params.get("lang") or request.headers.get("X-UI-Language")
    if explicit:
        return normalize_language(explicit, default=default)

    accept_language = request.headers.get("Accept-Language", "")
    if accept_language.lower().startswith("ar"):
        return "ar"
    if accept_language.lower().startswith("en"):
        return "en"
    return normalize_language(default, default=default)


def status_label(status: Any, lang: str = "en", category: str = "enrollment") -> str:
    value = getattr(status, "value", status)
    key = str(value or "").upper()
    if normalize_language(lang, default="en") != "ar":
        return key
    if category == "attendance":
        return ATTENDANCE_STATUS_AR.get(key, key)
    return ENROLLMENT_STATUS_AR.get(key, key)


def _seed_messages_for_babel() -> None:
    """Keep required UI/API strings discoverable by pybabel extraction."""
    _ = gettext
    _("Dashboard")
    _("My Children")
    _("Attendance")
    _("Reports")
    _("Profile")
    _("Enrollments")
    _("Absence Requests")
    _("Present")
    _("Absent")
    _("Late")
    _("Pending")
    _("Approved")
    _("Rejected")
    _("No data found")
    _("Loading...")
    _("Submit")
    _("Cancel")
    _("Save Changes")
    _("Delete")
    _("Edit")
    _("Parent access only")
    _("Parent profile not found")
    _("Not authorized to view this child's attendance")
    _("Supported languages: ar, en")
    _("Are you sure?")
    _("Saved successfully")
    _("An error occurred")
