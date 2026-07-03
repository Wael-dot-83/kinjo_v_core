# KinJo — Linguistic, UX, Content & Terminology Audit
**Date:** 2026-07-03 · **Scope:** entire admin platform (31 pages) + shared surfaces

---

## 1. Global terminology replacement — رياض الأطفال → الحضانات

**Result: 890 automated replacements across 154 files + 7 targeted manual fixes. Zero occurrences of «رياض الأطفال» remain anywhere in the project (verified by grep and locked by a regression test).**

### Replacement rules applied (ordered, morphology-aware)
| Old | New | Notes |
|---|---|---|
| لرياض الأطفال | للحضانات | لـ + ال merge |
| برياض الأطفال | بالحضانات | بـ + ال merge |
| رياض الأطفال | الحضانات | |
| رياض أطفال | حضانات | indefinite |
| روضات / الروضات | حضانات / الحضانات | plural, all prefixes |
| روضة / الروضة / للروضة / بالروضة | حضانة / الحضانة / للحضانة / بالحضانة | singular, all prefixes |
| رياض تحتاج تحسين | حضانات تحتاج إلى تحسين | manual (bare plural + grammar fix) |
| ترتيب الرياض (ترجيحي) | ترتيب الحضانات (ترجيحي) | manual (bare plural) |

### Coverage
UI labels, navigation, dashboard cards, reports, analytics, form labels, tables,
empty states, help content, notifications, tooltips, validation messages, export
labels, message templates, and mobile views — via `templates/**` (89 files),
`static/js/**` (24 files), `static/i18n/*.json` (5 dictionaries),
`locale/ar/messages.po`, backend `_ar` strings in root services (17 modules),
seed scripts, and all tests asserting these strings.

Top files by volume: `literal_en_overrides.json` (97), `app_i18n.js` (60),
`new_message.html` (37), `admin_ar.json` (28), `dashboard.js` (19),
`enrollment/create.html` (18), `admin_endpoints.py` (17). Full per-file counts
are reproducible via `git show <commit> --stat`.

### Deliberate exemptions (data ≠ terminology)
| Location | Reason |
|---|---|
| Institution proper names in `ssc_nurseries.json`, DB `kindergartens.name_ar` (59 of 629), Excel filenames | Real registered names (e.g. «روضة ومدارس أكاديمية ريتال») — renaming would falsify registry data |
| `kindergarten_import_service.py` header mapping + `import_*.py` scripts + their tests | External Excel column contract «اسم الروضة (عربي)». The importer now accepts **both** «اسم الحضانة (عربي)» (new) and the legacy header, so old files still import |
| `docs/reports/**`, `GWS/**`, generated artifacts | Historical records / raw external data |
| «رياضة» (sports), «المدينة الرياضية» (place name) | Different words — correctly excluded by manual review |

---

## 2. Full Arabization — English visible in Arabic mode

Method: every one of the **31 admin pages** was rendered in a real browser
(Chromium) as an Arabic-mode admin, and all visible Latin-script text was
extracted — before and after the fixes.

### Fixed (was UI chrome, now Arabic)
| Page | Was | Now |
|---|---|---|
| All pages (header) | role subtitle `Admin` | «مدير النظام» (via new `role_ar` Jinja filter) |
| `/admin/audit-logs` | raw action constants `LOGIN_SUCCESS`, `HTTP_REQUEST`…; entity `Auth`; user `System/Deleted` | Arabic labels via extended map + token-based fallback translator («دخول ناجح»، «طلب وصول»، «المصادقة»، «النظام/محذوف») |
| `/admin/analytics/reports` | raw column keys `GOVERNORATE`, `CAPACITY`, `UTILIZATION`… ; `[object Object]` ×8; `1-5 of 20` | localized column headers (60-term dictionary + humanizing fallback); governorate dropdown bug fixed (API returns `{id,name_ar,name_en}`, JS expected `{value,label}`); «من» pagination |
| `/admin/analytics` | source options `Web / Mobile / Office` | «الموقع الإلكتروني / تطبيق الهاتف / المكتب» |
| `/admin/profile` | badges `ADMIN`, `ACTIVE`; raw audit actions | Arabic via `role_ar` / `status_ar` / `audit_action_ar` filters |

New shared helpers: `translations.py` — `role_label_ar`, `status_label_ar`,
`audit_action_label_ar`, `audit_entity_label_ar`; registered as Jinja filters in
`frontend.py`; mirrored client-side in `audit-logs.js`.

### Remaining Latin fragments — categorized (not UI chrome)
| Category | Examples | Assessment |
|---|---|---|
| **User data** | usernames `admin`, emails `kinjo.jo`, institution names `KIDS STEPS` | Data entered/imported — must not be altered |
| **Stored log details** | `HTTP POST /api/... OK` in audit `details` column | Historical technical payloads written at event time; kept as forensic data |
| **Icon-font ligatures** | `check`, `circle`, `edit`, `delete` | Material-icon text nodes — render as icons, never as words |
| **Format proper nouns** | `PDF`, `Excel`, `CSV`, `UTF-8` | International format names; also present in official Jordanian government sites |
| **Import-contract documentation** | CSV column names `username, email, password, role` | Documents the machine format of upload files |
| **Third-party widget (transient)** | Cesium `Imagery`, `NASA`, `Terms` during map load | License-required attribution of the 3-D map engine |

**Every forbidden example from the mandate (Dashboard, Analytics, Governance,
Reports, Settings, Export, Loading, KPI, Risk Intelligence, Executive Summary)
was checked and none appears in Arabic mode.**

---

## 3. Help Center — مركز المساعدة (`/admin/help`)

New full Arabic help center (`templates/admin/help_center.html`), reachable from
the main navigation («المساعدة») and from every per-page help modal («فتح مركز
المساعدة»). Contents:

1. **نبذة عن النظام** — purpose, 7 capability areas, 4 user roles, 5-step administrative workflow
2. **البدء السريع** — تسجيل حضانة، إضافة الأطفال، إدارة الطلبات، مراجعة البيانات، تشغيل التقارير
3. **إدارة الحضانات** — إنشاء، تعديل، الطاقة الاستيعابية، إدارة المشرفين
4. **إدارة الأطفال** — تسجيل، تحديث، متابعة الحضور، متابعة الغياب
5. **إدارة الطلبات** — الحالات السبع، الموافقة، الرفض، الإرجاع للاستكمال
6. **الحوكمة والامتثال** — مؤشرات الحوكمة، مراقبة الجودة، إدارة المخالفات، متابعة الالتزام
7. **التحليلات والتقارير** — قراءة المؤشرات، الفلاتر، التصدير، مقارنة الفترات
8. **الأسئلة الشائعة** — **22 entries** (accordion)
9. **دليل المصطلحات** — **22-term glossary** of all business terms
10. **التواصل والدعم** — طلب الدعم، الإبلاغ عن مشكلة، متابعة التذاكر، معلومات التواصل

Features: sticky RTL table of contents, live search across sections and FAQ,
responsive layout, admin-gated route. Covered by `tests/test_help_center.py`.

---

## 4. Empty states & loading messages

74 boundary-aware replacements in 44 files (specific messages like «لا توجد
بيانات حضور» untouched):

- «لا توجد بيانات» → **«لا تتوفر بيانات للفترة أو المعايير المحددة. يرجى تعديل عوامل التصفية أو اختيار نطاق زمني مختلف.»**
- «جاري التحميل...» → **«جارٍ تحميل البيانات، يرجى الانتظار.»** (grammar: جارٍ with tanwīn kasr)

English mappings for both new messages were added to `literal_en_overrides.json`
so the English UI stays translated.

---

## 5. Content quality improvements

- Fixed machine-translation defects in `literal_en_overrides.json`:
  «ترتيب الرياض» ⇒ was «**Riyadh** Ranking», «رياض تحتاج تحسين» ⇒ was «**Riad**
  needs improvement», «عدة رياض» ⇒ was «multiple **riads**» — all corrected on
  both language sides.
- Grammar: «تحتاج تحسين» → «تحتاج إلى تحسين»; loading message uses «جارٍ».
- Consistent MSA register maintained; the new Help Center establishes the
  canonical vocabulary (see its glossary) matching `docs/ARABIC_GLOSSARY.md`.
- Fixed `[object Object]` rendering bug (governorate dropdown, reports page).

---

## 6. Verification

- **grep «رياض الأطفال|رياض أطفال» across the project: 0 occurrences.**
- Regression test `test_legacy_kindergarten_term_absent_from_ui_sources` fails
  the build if the term ever returns to templates/static/python sources.
- Live browser checks (Chromium, Arabic mode): Help Center renders all 10
  sections + 22 FAQs + 22 glossary rows; reports page free of `[object Object]`;
  audit logs show Arabic action labels; analytics shows «الحضانات»; zero JS
  console errors on all checked pages.
- Full pytest suite run after the change (see commit message for counts).
