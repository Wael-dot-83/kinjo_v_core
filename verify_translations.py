"""Quick verification of corrected Arabic translations."""
from i18n import _load_catalog, ENROLLMENT_STATUS_AR

c = _load_catalog('ar')
checks = [
    ('Approved',                                  'موافق عليه'),
    ('Loading...',                                'جارٍ التحميل...'),
    ('Need Help?',                                'هل تحتاج إلى مساعدة؟'),
    ('Not arrived yet',                           'لم يُسجَّل حضوره بعد'),
    ('Latest Daily Reports',                      'أحدث التقارير اليومية'),
    ('Welcome,',                                  'مرحباً،'),
    ('My Account',                                'إعدادات الحساب'),
    ('From Date',                                 'تاريخ البداية'),
    ('To Date',                                   'تاريخ الانتهاء'),
    ('National ID',                               'رقم الهوية الوطنية'),
    ('Emergency Contact',                         'جهة الاتصال للطوارئ'),
    ('Middle Name',                               'الاسم الأوسط'),
    ('Receive correspondence',                    'تلقّي المراسلات والإشعارات'),
    ('Support team is ready to help',             'فريق الدعم الفني مستعدٌّ لمساعدتك'),
    ('Parent access only',                        'مخصص لأولياء الأمور فقط'),
    ('Parent profile not found',                  'لم يُعثَر على ملف ولي الأمر'),
    ('Not authorized to update this profile',     'لا تملك صلاحية تحديث هذا الملف الشخصي'),
    ('Not authorized to view this child\'s attendance', 'لا تملك صلاحية الاطلاع على سجل حضور هذا الطفل'),
    ('Track your children\'s news and daily reports from one place', 'تابع أخبار أطفالك وتقاريرهم اليومية من مكان واحد'),
]

print("=== Translation Catalog Checks ===")
all_ok = True
for msgid, expected in checks:
    got = c.get(msgid, 'NOT FOUND')
    status = '✓' if got == expected else '✗'
    if got != expected:
        all_ok = False
    print(f"{status} {msgid!r}")
    if got != expected:
        print(f"    Expected: {expected}")
        print(f"    Got:      {got}")

print()
print("=== ENROLLMENT_STATUS_AR ===")
approved = ENROLLMENT_STATUS_AR.get('APPROVED')
print(f"APPROVED => {approved!r}  {'✓' if approved == 'موافق عليه' else '✗'}")

print()
print("ALL OK" if all_ok and approved == 'موافق عليه' else "SOME CHECKS FAILED")
