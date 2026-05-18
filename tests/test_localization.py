from pathlib import Path

from i18n import gettext
from utils.localization import format_date_ar, format_date_en, format_number_ar


ROOT = Path(__file__).resolve().parents[1]
PARENT_TEMPLATES = [
    ROOT / "templates" / "dashboard" / "parent.html",
    ROOT / "templates" / "parent" / "profile.html",
    ROOT / "templates" / "parent" / "children.html",
    ROOT / "templates" / "parent" / "enrollments.html",
    ROOT / "templates" / "parent" / "attendance.html",
    ROOT / "templates" / "reports" / "parent_list.html",
    ROOT / "templates" / "attendance" / "absence_requests.html",
]


def _auth_headers(token: str) -> dict:
    return {"Authorization": f"Bearer {token}"}


def test_parent_templates_use_gettext_for_static_language_branches():
    for path in PARENT_TEMPLATES:
        html = path.read_text(encoding="utf-8")
        assert "ui_lang == 'en'" not in html
        assert "{{ _(" in html


def test_required_arabic_translations_are_present():
    required = {
        "Dashboard": "لوحة التحكم",
        "My Children": "أطفالي",
        "Attendance": "الحضور",
        "Reports": "التقارير",
        "Profile": "الملف الشخصي",
        "Enrollments": "التسجيلات",
        "Absence Requests": "طلبات الغياب",
        "Present": "حاضر",
        "Absent": "غائب",
        "Late": "متأخر",
        "Pending": "قيد الانتظار",
        "Approved": "موافق",
        "Rejected": "مرفوض",
        "No data found": "لا توجد بيانات",
        "Loading...": "جاري التحميل...",
        "Submit": "إرسال",
        "Cancel": "إلغاء",
        "Save Changes": "حفظ التغييرات",
        "Delete": "حذف",
        "Edit": "تعديل",
    }
    for msgid, expected in required.items():
        assert gettext(msgid, lang="ar") == expected


def test_parent_api_errors_translate_when_arabic_requested(client, admin_token):
    headers = _auth_headers(admin_token)
    headers["Accept-Language"] = "ar"
    response = client.get("/api/parent/profile", headers=headers)
    assert response.status_code == 403
    assert response.json()["detail"] == "الوصول للوالدين فقط"


def test_date_and_number_localization_helpers():
    assert format_date_en("2026-04-26") == "04/26/2026"
    assert format_date_ar("2026-04-26") == "٢٦/٠٤/٢٠٢٦"
    assert format_number_ar(12345) == "١٢٣٤٥"
