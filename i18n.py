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


PARENT_TRANSLATIONS_AR: dict[str, str] = {
    "Parent Dashboard": "لوحة ولي الأمر",
    "Welcome back,": "أهلاً بك،",
    "Parent": "ولي الأمر",
    "Follow your children's daily activities, attendance status, and kindergarten reports in real-time.": "تابع أنشطة أطفالك اليومية، وحالة الحضور والغياب، وتقارير الروضة أولاً بأول.",
    "Children": "الأطفال",
    "Present Today": "حاضرون اليوم",
    "Reports": "التقارير",
    "My Children": "أطفالي",
    "Manage Children": "إدارة الأطفال",
    "Quick Services": "الخدمات السريعة",
    "Register Child": "تسجيل طفل",
    "New Enrollment Application": "تقديم طلب جديد",
    "Daily Reports": "التقارير اليومية",
    "View Daily Logs & Notes": "متابعة السجلات والأنشطة",
    "Messages": "الرسائل والطلب",
    "Contact Teachers & KG": "التواصل مع الروضة والمعلمات",
    "Attendance Log": "سجل الحضور",
    "Track Check-in Records": "متابعة الدخول والخروج",
    "Applications": "طلبات التسجيل",
    "Status & History": "حالة وقائمة الطلبات",
    "My Profile": "ملفي الشخصي",
    "Account & Parent Info": "بيانات الحساب وولي الأمر",
    "Latest Daily Reports": "أحدث التقارير اليومية",
    "View All": "عرض الكل",
    "Upcoming Events & Activities": "الفعاليات والأنشطة القادمة",
    "No upcoming events scheduled": "لا توجد فعاليات قادمة حالياً",
    "Need Assistance?": "هل تحتاج إلى مساعدة؟",
    "Have questions about your child or kindergarten services? Our support team is here to help.": "هل لديك استفسارات حول طفلك أو خدمات الروضة؟ فريق الدعم متاح لمساعدتك.",
    "Contact Support": "تواصل مع الدعم",
    "Daily Report Details": "تفاصيل التقرير اليومي",
    "Close": "إغلاق",
    "Attendance Record": "سجل الحضور والغياب",
    "Attendance": "الحضور",
    "Total Records": "إجمالي السجلات",
    "Present Days": "أيام الحضور",
    "Absent Days": "أيام الغياب",
    "Late Days": "أيام التأخير",
    "Select Child:": "اختيار الطفل:",
    "Child Select:": "اختيار الطفل:",
    "All Children": "جميع الأطفال",
    "Filter by Date:": "تاريخ الحضور:",
    "Date Filter:": "تاريخ الحضور:",
    "Filter": "تصفية",
    "Reset filters": "إعادة ضبط الفلاتر",
    "Attendance Logs": "سجلات الحضور",
    "Child": "الطفل",
    "Date": "التاريخ",
    "Status": "الحالة",
    "Check-in Time": "وقت الدخول",
    "Check-out Time": "وقت الخروج",
    "Notes": "ملاحظات",
    "Enrollment Applications": "طلبات التسجيل",
    "Enrollments": "التسجيلات",
    "New Application": "تقديم طلب جديد",
    "Register New Child": "تسجيل طفل جديد",
    "Total Applications": "إجمالي الطلبات",
    "Active / Accepted": "مقبولة / نشطة",
    "Under Review": "قيد المراجعة",
    "Applications List": "قائمة الطلبات",
    "Child Name": "اسم الطفل",
    "Kindergarten": "الروضة",
    "Submitted Date": "تاريخ التقديم",
    "Dashboard": "لوحة التحكم",
    "Breadcrumb": "مسار التنقل",
    "Loading...": "جارٍ تحميل البيانات، يرجى الانتظار.",
    "Personal Information": "المعلومات الشخصية",
    "Enrollment Requests": "طلبات التسجيل",
    "Returned": "مُرجَع",
    "My Children's Reports": "تقارير أطفالي",
    "KinJo — Home": "KinJo — الرئيسية",
}


def gettext(message: Any, lang: str = DEFAULT_LANGUAGE, **kwargs: Any) -> str:
    text = str(message or "")
    language = normalize_language(lang)
    if language == "ar":
        translated = PARENT_TRANSLATIONS_AR.get(text) or _load_catalog("ar").get(text, text)
    elif language != "en":
        translated = _load_catalog(language).get(text, text)
    else:
        translated = text

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


def request_language(request: Request | None, default: str = DEFAULT_LANGUAGE) -> str:
    """Resolve explicit request language for API responses.

    Arabic is the site-wide default. Callers can explicitly select a language
    with a query parameter, UI-language header, or Accept-Language header.
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


def status_label(status: Any, lang: str = DEFAULT_LANGUAGE, category: str = "enrollment") -> str:
    value = getattr(status, "value", status)
    key = str(value or "").upper()
    if normalize_language(lang) != "ar":
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
