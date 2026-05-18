You are Senior Automation & Localization Engineer. Execute exact commands. Fix ALL language issues. Zero assumptions.

MANDATE
Complete Parent Module to 100% production grade with FULL bilingual support (EN/AR). Follow strictly.

📋 EXECUTION CHECKLIST
Phase 1: Language Audit (5 min)
yaml
SCAN for language issues:
templates/parent/\*.html: - [ ] Hardcoded English text (must use {{ _('text') }}) - [ ] Missing RTL support (dir="{{ ui_dir }}") - [ ] Missing lang attribute (lang="{{ ui_lang }}")

api/parent.py: - [ ] Error messages in English only (must use gettext) - [ ] Status enums without AR mapping

frontend.py: - [ ] Flash messages without translation

OUTPUT: "LANG AUDIT: [X] hardcoded strings, [X] missing RTL, [X] untranslated errors"
Phase 2: Translation Completion (10 min)
python

# CREATE/FIX locale/ar/LC_MESSAGES/messages.po

MUST HAVE translations:
"Dashboard" → "لوحة التحكم"
"My Children" → "أطفالي"
"Attendance" → "الحضور"
"Reports" → "التقارير"
"Profile" → "الملف الشخصي"
"Enrollments" → "التسجيلات"
"Absence Requests" → "طلبات الغياب"
"Present" → "حاضر"
"Absent" → "غائب"
"Late" → "متأخر"
"Pending" → "قيد الانتظار"
"Approved" → "موافق"
"Rejected" → "مرفوض"
"No data found" → "لا توجد بيانات"
"Loading..." → "جاري التحميل..."
"Submit" → "إرسال"
"Cancel" → "إلغاء"
"Save Changes" → "حفظ التغييرات"
"Delete" → "حذف"
"Edit" → "تعديل"

OUTPUT: "TRANSLATIONS: Added [X] keys, [X] total"
Phase 3: Template Language Fixes (10 min)
html

<!-- FIX EVERY TEMPLATE - Example -->
<!-- BEFORE -->
<h1>Welcome Parent</h1>
<button>Submit</button>

<!-- AFTER -->
<h1>{{ _('Welcome Parent') }}</h1>
<button>{{ _('Submit') }}</button>

<!-- ADD TO EVERY HTML FILE -->
<html lang="{{ ui_lang }}" dir="{{ ui_dir }}">
<head>
    <meta charset="UTF-8">
    {% if ui_dir == 'rtl' %}
    <link rel="stylesheet" href="{{ url_for('static', path='css/rtl.css') }}">
    {% endif %}
</head>
yaml
TARGET FILES:
  - [ ] templates/dashboard/parent.html
  - [ ] templates/parent/profile.html
  - [ ] templates/parent/children.html
  - [ ] templates/parent/enrollments.html
  - [ ] templates/parent/attendance.html
  - [ ] templates/reports/parent_list.html
  - [ ] templates/attendance/absence_requests.html

OUTPUT: "TEMPLATES: Fixed [X] files, [X] strings translated"
Phase 4: API Language Fixes (8 min)
python

# api/parent.py - FIX error messages

# BEFORE

raise HTTPException(403, "Access denied")

# AFTER

from fastapi import Request
from i18n import gettext as \_

raise HTTPException(403, \_("Access denied"))

# Status enum mapping

ENROLLMENT_STATUS_AR = {
'pending': 'قيد الانتظار',
'approved': 'مقبول',
'rejected': 'مرفوض',
'waiting': 'قائمة الانتظار'
}

ATTENDANCE_STATUS_AR = {
'present': 'حاضر',
'absent': 'غائب',
'late': 'متأخر'
}

OUTPUT: "API: Fixed [X] error messages, added [X] status mappings"
Phase 5: JavaScript Language Fixes (5 min)
javascript
// static/js/parent.js - ADD i18n support

const i18n = {
en: {
confirmDelete: 'Are you sure?',
saveSuccess: 'Saved successfully',
errorOccurred: 'An error occurred'
},
ar: {
confirmDelete: 'هل أنت متأكد؟',
saveSuccess: 'تم الحفظ بنجاح',
errorOccurred: 'حدث خطأ'
}
};

function t(key) {
const lang = document.documentElement.lang || 'en';
return i18n[lang][key] || key;
}

// Use in all alerts and confirm dialogs
if (confirm(t('confirmDelete'))) { ... }

OUTPUT: "JS: Added i18n support to [X] files"
Phase 6: Date & Number Localization (5 min)
python

# utils/localization.py - CREATE if missing

from babel.dates import format_date
from babel.numbers import format_number
import locale

def format_date_ar(date):
return format_date(date, locale='ar_EG')

def format_date_en(date):
return format_date(date, locale='en_US')

def format_number_ar(number): # Arabic-Indic digits ٠١٢٣٤٥٦٧٨٩
arabic_digits = str(number).translate(str.maketrans('0123456789', '٠١٢٣٤٥٦٧٨٩'))
return arabic_digits

# Apply to ALL dates in templates

{{ format_date_ar(child.dob) if ui_lang == 'ar' else child.dob }}

OUTPUT: "LOCALE: Added date/number formatting for AR"
Phase 7: RTL CSS Fixes (5 min)
css
/_ static/css/rtl.css - CREATE if missing _/

[dir="rtl"] {
text-align: right;
direction: rtl;
}

[dir="rtl"] .navbar-nav {
padding-right: 0;
padding-left: auto;
}

[dir="rtl"] .dropdown-menu {
text-align: right;
}

[dir="rtl"] .form-control {
text-align: right;
}

[dir="rtl"] .alert {
border-right: 4px solid;
border-left: none;
}

/_ Fix icons for RTL _/
[dir="rtl"] .fa-arrow-left:before {
content: "\f061"; /_ arrow-right _/
}

[dir="rtl"] .ml-auto {
margin-right: auto !important;
margin-left: 0 !important;
}

OUTPUT: "CSS: Created RTL styles with [X] rules"
Phase 8: Database Language Fields (5 min)
sql
-- CHECK for language preference in User/ParentProfile
ALTER TABLE users ADD COLUMN IF NOT EXISTS preferred_language VARCHAR(2) DEFAULT 'en';
ALTER TABLE parent_profiles ADD COLUMN IF NOT EXISTS notification_language VARCHAR(2) DEFAULT 'en';

-- UPDATE existing users
UPDATE users SET preferred_language = 'en' WHERE preferred_language IS NULL;
python

# ADD to profile update endpoint

@router.put("/parent/profile")
async def update_profile(
language: Optional[str] = None,
current_user: User = Depends(get_current_user)
):
if language and language in ['en', 'ar']:
current_user.preferred_language = language
db.commit() # ... rest of update

OUTPUT: "DB: Added language fields to [X] tables"
🔧 COMPLETE FIX COMMANDS
bash

# RUN SEQUENCE

step 1: grep -r ">[A-Za-z]" templates/parent/ | grep -v "\_(" | grep -v "{%" # Find hardcoded text
step 2: pybabel extract -F babel.cfg -o messages.pot .
step 3: pybabel update -i messages.pot -d locale
step 4: # Manually edit locale/ar/LC_MESSAGES/messages.po
step 5: pybabel compile -d locale
step 6: pytest tests/test_localization.py -v
✅ SUCCESS CRITERIA
STOP ONLY WHEN:

✅ 0 hardcoded English strings in templates (all use {{ _() }})

✅ RTL layout works correctly (navbar, forms, alerts, icons)

✅ All 7 templates have lang + dir attributes

✅ API error messages in both EN/AR

✅ Dates display correctly (EN: MM/DD/YYYY, AR: DD/MM/YYYY)

✅ Numbers display Arabic-Indic digits in AR mode

✅ Language preference persists in database

✅ User can switch language without logout

📤 FINAL REPORT FORMAT
text
=== LANGUAGE COMPLETION REPORT ===
HARDCODED STRINGS: X fixed / X total
RTL SUPPORT: [YES/NO]
TEMPLATES UPDATED: X/7
API MESSAGES: X endpoints translated
DATE FORMATS: EN/AR working
NUMBER FORMATS: AR digits working
DB LANGUAGE FIELD: [YES/NO]
CSS RTL FILE: [YES/NO]

# LANGUAGE STATUS: [FULLY BILINGUAL / PARTIAL / FAILED]

🎯 COMBINED FINAL REPORT
text
=== PARENT MODULE + LANGUAGE COMPLETION ===
MODULE STATUS: [100% / XX%]
AUDIT: PASS/FAIL
DB INTEGRITY: orphans: X
SECURITY: X/7 endpoints
URLS: X/20 responsive
LANGUAGE: X/7 templates bilingual
RTL: [WORKING/NOT WORKING]
TRANSLATIONS: X keys complete

# FINAL STATUS: [READY FOR PRODUCTION]

🚀 INITIATE
Run all 8 phases. Fix all language issues. Report final status only.
