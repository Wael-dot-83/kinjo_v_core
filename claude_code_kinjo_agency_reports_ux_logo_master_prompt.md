# Claude Code Master Prompt — KinJo Agency Reports UX + Official Logo Implementation

## Role

You are Claude Code acting as a senior full-stack FastAPI/Jinja2/Bootstrap/Vanilla-JS engineer, Arabic RTL UI/UX specialist, government-dashboard designer, accessibility engineer, privacy/governance reviewer, QA lead, and GitHub release operator.

You must work locally, implement fully, save changes, commit, push, open/update a PR, wait for CI, and merge into `main` **only when fully green, clean, conflict-free, scope-clean, privacy-safe, and verified**.

Do not merge if anything is red, pending, conflicting, dirty, missing, privacy-risky, out of scope, or unverified.

---

## Repository

```text
Wael-dot-83/kinjo_v_core
```

GitHub URL:

```text
https://github.com/Wael-dot-83/kinjo_v_core.git
```

Local project path on this device:

```text
D:\Final Version
```

Use this local repository path as the source repository.

---

## Important Project Stack

This project is **not Laravel, React, or Vue**.

Do **not** introduce Laravel, React, Vue, SPA architecture, or unrelated frontend frameworks.

The project uses:

```text
FastAPI
Jinja2 templates
Bootstrap 5.3
Vanilla JavaScript
SQLAlchemy
Alembic
Python tests
```

---

## Current Repository State and Work Protection

Primary local repository:

```text
D:\Final Version
```

Primary branch:

```text
main
```

Important current merged work already on `main`:

```text
#21 merged
#30 merged
#31 merged
#32 merged
#33 merged
#34 merged
```

Known open/in-flight work that must not be contaminated:

```text
#29 = canonical Jordan location-filter work, still under validation.
#26 = dashboard/agency-logo redesign scope, blocked/conflicting.
#20 = draft manager overhaul.
feat/jordan-location-filters-clean-v2 = local dirty WIP; do not touch unless explicitly required.
```

Hard protection rules:

1. Do not commit directly from `D:\Final Version` if it has unrelated dirty WIP.
2. Do not overwrite, reset, delete, or clean uncommitted work in `D:\Final Version`.
3. Do not touch `D:\Final Version-loc29` or any #29 worktree.
4. Do not touch #26 or #20.
5. Do not absorb dashboard-redesign work unless directly required for shared logo/layout changes.
6. Do not run any data migration with `--apply`.
7. Do not expose personal, child, parent, national ID, phone, exact address, or sensitive data.
8. Do not use **رياض الأطفال** or **روضة** as general KinJo platform terms.
9. Use **الحضانة** for singular and **الحضانات** for plural.
10. Do not invent missing government or administrative data.
11. Do not invent a logo asset.
12. Do not merge without explicit green gates and clean GitHub mergeability.

---

## Local Worktree Setup

Start from the local repository:

```bash
cd "D:/Final Version"
git status --short
git remote -v
git branch --show-current
git fetch origin --prune
git log origin/main -10 --oneline
gh repo view Wael-dot-83/kinjo_v_core
gh pr list --state open
```

Inspect whether `D:\Final Version` is dirty.

If dirty, do not modify or clean it. Continue using a separate worktree.

Create a clean isolated implementation worktree:

```bash
cd "D:/Final Version"
git fetch origin --prune
git worktree remove --force "../Final Version-agency-reports-ux" 2>/dev/null || true
git worktree add "../Final Version-agency-reports-ux" origin/main
cd "../Final Version-agency-reports-ux"
git switch -c feat/admin-agency-reports-ux-polish
```

Expected implementation path:

```text
D:\Final Version-agency-reports-ux
```

Confirm clean state:

```bash
git status --short
git branch --show-current
git log --oneline -5
```

Expected:

```text
Branch: feat/admin-agency-reports-ux-polish
Working tree: clean
Base: latest origin/main
```

If remote branch already exists:

```bash
cd "D:/Final Version"
git fetch origin --prune
git worktree remove --force "../Final Version-agency-reports-ux" 2>/dev/null || true
git worktree add "../Final Version-agency-reports-ux" origin/feat/admin-agency-reports-ux-polish
cd "../Final Version-agency-reports-ux"
git switch -B feat/admin-agency-reports-ux-polish origin/feat/admin-agency-reports-ux-polish
```

---

# Main Task Scope

Enhance the KinJo Admin Agency Reports module and official KinJo logo usage.

Primary pages to improve:

```text
/admin/agency-reports
/admin/agency-reports/moe
/admin/agency-reports/moe/kg2_eligibility
/admin/agency-reports/moh/vaccination_due_children
/admin/agency-reports/moh/health_absence_summary
/admin/agency-reports/dos/children_statistical_profile
/admin/agency-reports/ncfa/child_family_profile
/admin/agency-reports/ncfa/family_communication_counts
/admin/agency-reports/mol/workforce_summary
/admin/agency-reports/mol/training_compliance
/admin/agency-reports/mosd/kindergarten_registry
/admin/agency-reports/mosd/child_safety_protection
/admin/agency-reports/mopic/service_access_gaps
/login
/admin/dashboard
shared admin layout/sidebar/header/mobile nav where logo appears
```

Global objectives:

1. Improve Arabic RTL layout and spacing.
2. Improve admin usability and guidance.
3. Improve cards, labels, buttons, badges, exports, charts, and tables.
4. Make all agency report pages professional and usable by non-technical admins.
5. Preserve privacy and aggregation.
6. Replace temporary KinJo logo usages with the official `kinjo-logo` asset.
7. Keep scope clean and avoid mixing #29/#26 work.

---

# Initial Investigation

Run these searches before editing:

```bash
grep -RIn "/admin/agency-reports" .
grep -RIn "agency_reports" .
grep -RIn "وزارة التربية\|وزارة التربية والتعليم\|وزارة التنمية الاجتماعية" .
grep -RIn "رياض الأطفال\|روضة\|الحضانة\|الحضانات" templates static api services tests --include="*.html" --include="*.js" --include="*.css" --include="*.py" || true
grep -RIn "Kj\|KJ\|كينجو\|KinJo\|logo\|brand\|app-logo\|navbar-brand\|sidebar-logo" templates static api services --include="*.html" --include="*.js" --include="*.css" --include="*.py" || true
find . -iname "*kinjo*logo*" -o -iname "*logo*"
```

Likely files to inspect:

```text
templates/admin/agency_reports/index.html
templates/admin/agency_reports/agency.html
templates/admin/agency_reports/report.html
static/css/agency_reports.css
static/js/admin_agency_reports.js
static/js/admin_agency_reports_custom.js
static/js/admin_agency_reports_dashboard_summary.js
agency_reports_registry.py
agency_reports_service.py
api/agency_reports_api.py
templates/admin_base.html
templates/admin_dashboard.html
templates/auth/*.html
static/css/*.css
static/js/*.js
```

Do not assume filenames. Search and verify.

---

# 1. Agency Reports Main Page Improvements

Route:

```text
/admin/agency-reports
```

Required changes:

Rename agency everywhere user-facing:

```text
وزارة التربية
```

to:

```text
وزارة التربية والتعليم
```

Apply this to:

```text
agency cards
agency pages
breadcrumbs
tooltips
registry labels
JS labels
test expectations
page titles
report headers
```

Do not use the old shortened label in UI.

## Agency Card Structure

Each agency card must include:

```text
larger visible logo
agency name
short description
الغرض من التقرير
كيفية الاستخدام
عدد التقارير
التقارير الجاهزة
التقارير التي تحتاج بيانات
status badge
primary button: فتح تقارير الجهة
secondary help tooltip: ما هذه التقارير؟
```

Recommended visual structure:

```text
[Logo]

وزارة التربية والتعليم

الغرض من التقرير
...

كيفية الاستخدام
...

التقارير المتوفرة: N
الحالة: ✅ جاهزة

[فتح تقارير الجهة]
```

Logo size inside agency cards:

Desktop:

```css
width: 72px;
height: 72px;
```

Large cards may use:

```css
width: 80px;
height: 80px;
```

Style:

```css
object-fit: contain;
background: #f8fafc;
border: 1px solid #e5e7eb;
border-radius: 16px;
padding: 10px;
```

Responsive:

```text
tablet: 64px
mobile: 56px
```

Do not crop, stretch, blur, or distort logos.

## Top Guidance Panel

Add top guidance panel.

Title:

```text
دليل استخدام تقارير الجهات الرسمية
```

Content:

```text
اختر الجهة الرسمية لعرض التقارير التجميعية المتاحة. جميع التقارير تعرض بيانات إحصائية وتجميعية فقط، ولا تعرض أي بيانات شخصية أو حساسة. استخدم الفلاتر لتحديد الفترة الزمنية والنطاق الجغرافي، ثم صدّر النتائج بصيغة CSV أو الرسم البياني عند الحاجة.
```

## Summary Widgets

Add summary widgets:

```text
عدد الجهات الرسمية
إجمالي التقارير
التقارير الجاهزة
التقارير التي تحتاج بيانات منظمة
آخر تحديث للبيانات
```

Use real registry/service data. Do not invent fake values.

## Remove Duplicate Bottom Content

Remove duplicate bottom/custom-builder content:

```text
وزارة التنمية الاجتماعية
تقارير الرعاية والحماية وجودة الحضانات والوصول للخدمة.
```

Replace with concise selected-agency text:

```text
الجهة الرسمية المختارة
```

Example:

```text
الجهة الرسمية المختارة: وزارة التنمية الاجتماعية
```

## Improve Custom Builder Labels

Replace:

```text
الجهة المستفيدة
```

with:

```text
الجهة الرسمية المستفيدة من التقرير
```

Replace:

```text
مستوى التقرير
```

with:

```text
النطاق الجغرافي للتقرير
```

Replace:

```text
الفترة الزمنية
```

with:

```text
فترة تجميع البيانات
```

Replace:

```text
مجالات ومؤشرات التقرير
```

with:

```text
اختر المؤشرات المطلوب تضمينها في التقرير
```

## Status Badges

Use icon + text:

```text
✅ جاهزة
⚠ تحتاج بيانات
⛔ غير متاح
قيد التطوير
```

Do not rely on color only.

## Button Labels

Replace agency-specific long labels such as:

```text
عرض تقارير وزارة التربية
```

with:

```text
فتح تقارير الجهة
```

## Empty State

```text
لا توجد تقارير جاهزة حالياً.
يرجى استكمال البيانات المطلوبة أو مراجعة إعدادات التكامل.
```

---

# 2. MOE Agency Page Improvements

Route:

```text
/admin/agency-reports/moe
```

Page title:

```text
وزارة التربية والتعليم
```

Page explanation:

```text
تعرض هذه الصفحة التقارير التجميعية الخاصة بوزارة التربية والتعليم، مثل تقدير الأطفال المؤهلين للالتحاق بالمستوى الثاني KG2 حسب المحافظة واللواء والمنطقة والجنس. البيانات المعروضة إحصائية فقط ولا تحتوي على أي بيانات شخصية.
```

Do not use **رياض الأطفال** here as platform language. Use **المستوى الثاني KG2**.

Each report card must show:

```text
اسم التقرير
الغرض من التقرير
المؤشرات المتاحة
حالة البيانات
آخر تحديث
كيفية الاستخدام
```

Button labels:

```text
فتح التقرير
عرض التفاصيل
تصدير CSV
تصدير الرسم البياني
```

Cards must have:

```text
equal height
clean RTL alignment
consistent button placement
clear status labels
privacy badge
```

---

# 3. KG2 Eligibility Report Critical Fix

Route:

```text
/admin/agency-reports/moe/kg2_eligibility
```

Page title:

```text
تقرير الأطفال المؤهلين للالتحاق بالمستوى الثاني KG2
```

Explanation:

```text
يساعد هذا التقرير وزارة التربية والتعليم على تقدير عدد الأطفال المؤهلين للالتحاق بالمستوى الثاني KG2 حسب المحافظة واللواء/القصبة والمنطقة والجنس. استخدم الفلاتر لتحديد النطاق الجغرافي ثم راجع الأرقام التجميعية والرسم البياني. البيانات المعروضة إحصائية وتجميعية فقط ولا تحتوي على أي بيانات شخصية.
```

Filter layout desktop grid:

```text
المحافظة
قصبة / لواء
المنطقة
الجنس
فترة تجميع البيانات
تطبيق الفلاتر
إعادة تعيين
```

Mobile:

```text
Stack vertically with full width.
```

Governorate field:

Must be a dropdown, not free text.

Allowed governorates only:

```text
العاصمة
إربد
الزرقاء
البلقاء
مادبا
الكرك
الطفيلة
معان
العقبة
جرش
عجلون
المفرق
```

Dependent dropdown behavior:

On page load:

```text
المحافظة enabled
قصبة / لواء disabled
المنطقة disabled
```

After selecting المحافظة:

```text
قصبة / لواء enabled
المنطقة disabled
```

After selecting قصبة / لواء:

```text
المنطقة enabled
```

If المحافظة changes:

```text
reset قصبة / لواء
reset المنطقة
```

If قصبة / لواء changes:

```text
reset المنطقة
```

Administrative divisions source:

Use this Excel file if available:

```text
C:\Users\waelj\OneDrive - zuj.edu.jo\Desktop excelsheet التقسيمات_الإدارية_الأردنية_من_النظام
```

Required behavior:

```text
Import or convert the Excel sheet into a structured seed, JSON file, or lookup table.
Map: المحافظة -> قصبة / لواء -> المنطقة.
Keep Arabic names exactly as source.
Trim spaces.
Remove duplicates.
Preserve RTL names.
Validate invalid combinations.
```

Critical blocker rule:

If the Excel file is unavailable, stop and report the blocker. Do not fabricate administrative divisions. Use existing project canonical location data only if it already provides the required hierarchy.

Alignment requirements:

```text
Labels above inputs.
Consistent input widths.
Buttons aligned with fields.
RTL dropdown arrows correct.
Numbers readable.
Arabic text does not wrap awkwardly.
Cards/tables/charts have consistent spacing.
```

Results sections:

```text
ملخص النتائج
التوزيع حسب الجنس
التوزيع حسب المحافظة
التوزيع حسب قصبة / لواء
التوزيع حسب المنطقة
جدول البيانات التجميعية
الرسم البياني
```

Export buttons on KG2:

Only show:

```text
تصدير CSV
تصدير الرسم البياني
```

Remove/hide:

```text
PDF
Excel
Print
Generic export menu
```

CSV export:

Must include aggregated data only.

Never export:

```text
child name
parent name
national ID
phone number
exact address
personal identifier
```

CSV filename:

```text
kg2_eligibility_YYYY-MM-DD.csv
```

Chart export:

Button label:

```text
تصدير الرسم البياني
```

Export currently visible chart only as PNG.

Filename:

```text
kg2_eligibility_chart_YYYY-MM-DD.png
```

States:

Empty:

```text
لا توجد بيانات مطابقة للفلاتر المحددة. يرجى تعديل المحافظة أو اللواء أو المنطقة أو الفترة الزمنية.
```

Loading:

```text
جاري تحميل البيانات...
```

Error:

```text
تعذر تحميل التقرير. يرجى المحاولة مرة أخرى أو التواصل مع مسؤول النظام.
```

---

# 4. Export Consistency Across Report Pages

For every official agency report page, show only:

```text
تصدير CSV
تصدير الرسم البياني
```

Affected report routes:

```text
/admin/agency-reports/moe/kg2_eligibility
/admin/agency-reports/moh/vaccination_due_children
/admin/agency-reports/moh/health_absence_summary
/admin/agency-reports/dos/children_statistical_profile
/admin/agency-reports/ncfa/child_family_profile
/admin/agency-reports/ncfa/family_communication_counts
/admin/agency-reports/mol/workforce_summary
/admin/agency-reports/mol/training_compliance
/admin/agency-reports/mosd/kindergarten_registry
/admin/agency-reports/mosd/child_safety_protection
/admin/agency-reports/mopic/service_access_gaps
```

Remove or hide from UI:

```text
PDF export
Excel export
Print export
Generic export menu
```

Do not remove backend functions unless safe and tested. Prefer hiding unsupported UI actions.

---

# 5. Standard Report Page Structure

Every report page must follow this structure:

Breadcrumb:

```text
لوحة التحكم / تقارير الجهات الرسمية / اسم الجهة / اسم التقرير
```

Header:

```text
report title
agency logo
agency name
short explanation
privacy badge: بيانات تجميعية فقط
```

Help panel title:

```text
كيفية استخدام التقرير
```

Help panel content:

```text
اختر فترة تجميع البيانات.
حدد المحافظة عند الحاجة.
اختر قصبة / لواء ثم المنطقة إذا كانت متاحة.
اضغط تطبيق الفلاتر.
راجع الملخص والرسم البياني.
استخدم تصدير CSV أو تصدير الرسم البياني عند الحاجة.
```

Filters card:

```text
clear labels
required indicators where needed
tooltips/help text
apply/reset buttons
```

KPI cards:

```text
Arabic title
number
short explanation
status indicator where applicable
```

Chart section:

```text
Arabic chart title
chart description
Arabic legend
export chart button
```

Aggregated table:

```text
Arabic column names
sorting where useful
pagination
empty state
CSV export button
```

Footer privacy note:

```text
تعرض هذه الصفحة بيانات إحصائية وتجميعية فقط لدعم القرار، ولا تعرض أي بيانات شخصية أو حساسة.
```

---

# 6. Arabic RTL Rules

Apply:

```css
direction: rtl;
text-align: right;
```

Rules:

```text
Arabic labels everywhere.
Icons aligned correctly for RTL.
Avoid mixed English/Arabic unless needed for KG2 or CSV.
No mojibake.
No broken Arabic shaping.
No awkward wrapping.
Consistent button sizes.
Visible keyboard focus.
Accessible labels.
```

Button standards:

```text
Primary: تطبيق الفلاتر / فتح التقرير
Secondary: إعادة تعيين
Export: تصدير CSV / تصدير الرسم البياني
```

---

# 7. Privacy and Governance

All reports must be aggregated only.

Never expose:

```text
child names
parent names
national IDs
phone numbers
exact addresses
sensitive child/family data
personal identifiers
```

Protect:

```text
API responses
frontend tables
CSV export
chart data
tooltips
browser-visible JSON
```

Visible privacy label:

```text
بيانات تجميعية فقط - لا توجد بيانات شخصية
```

Data quality label where relevant:

```text
مؤشر جودة البيانات
```

---

# 8. Official KinJo Logo Replacement

Replace temporary logo/icon/brand-mark usage.

Current temporary usages:

```text
Kj
KJ
text-logo كينجو
```

Required official asset name:

```text
kinjo-logo
```

Important:

Only replace visual logo/brand-mark usage. Do not replace normal text references where “كينجو” appears in readable content, page titles, descriptions, or normal sentences.

Scope:

```text
main layout
sidebar header
top navigation
mobile navigation
collapsed sidebar logo
expanded sidebar logo
admin layout header
login page
forgot/reset/verification screens
admin dashboard
agency reports pages
report pages
error pages where applicable
favicon/apple-touch-icon/manifest/PWA icons if asset supports it
```

Implementation approach:

Create or update one reusable Jinja partial/component if compatible, for example:

```text
templates/components/kinjo_logo.html
```

Suggested interface:

```text
size: small | medium | large
variant: full | icon
class/className
showText: true | false
```

Image rules:

```text
Use official kinjo-logo asset.
Prefer SVG, then PNG, then WebP.
Do not use external URLs.
Do not use generated icons.
Do not use temporary KJ/Kj fallback as final result.
Do not stretch.
Do not crop.
object-fit: contain.
alt text: شعار كينجو
```

Suggested sizes:

```text
sidebar expanded: width 140px, height auto
sidebar collapsed: 40px x 40px
top navbar: 120px width
login page: 160px to 200px
```

If official `kinjo-logo` asset is missing:

```text
Search assets first.
If truly missing, stop and report the blocker.
Do not invent or generate a replacement logo.
```

---

# 9. Terminology Rule

Mandatory platform terminology:

Do not use:

```text
رياض الأطفال
روضة
```

as general KinJo platform/module UI terms.

Use:

```text
الحضانة
```

for singular.

Use:

```text
الحضانات
```

for plural/module.

Acceptable exceptions:

```text
legal/source data where exact text must be preserved
historical text that is not UI copy
KG2 education-level wording when it does not refer to the KinJo nursery module
```

Before commit, run:

```bash
grep -RIn "رياض الأطفال\|روضة" templates static agency_reports_registry.py agency_reports_service.py api --include="*.html" --include="*.js" --include="*.css" --include="*.py" || true
```

Any user-facing admin UI occurrence must be changed to:

```text
الحضانة
الحضانات
```

unless a clear exception is documented in the PR body.

---

# 10. Testing

Run static checks:

```bash
python -m ruff check .
python -m py_compile agency_reports_registry.py agency_reports_service.py api/agency_reports_api.py
```

Run targeted tests that exist:

```bash
python -m pytest tests/test_admin_agency_reports_registry.py -q --tb=short
python -m pytest tests/test_admin_agency_reports_custom.py -q --tb=short
python -m pytest tests/test_admin_agency_reports_contract.py -q --tb=short
python -m pytest tests/test_admin_agency_logos.py -q --tb=short
python -m pytest tests/test_admin_dashboard_redesign.py -q --tb=short
python -m pytest tests/test_jordan_locations.py -q --tb=short
```

If a listed test file does not exist, report it and continue with closest existing tests.

Run full suite:

```bash
python -m pytest tests/ --timeout=180 -q
```

Expected:

```text
0 failed
```

If full suite fails:

```text
Investigate.
Fix only in-scope issues.
If failure is unrelated, prove it with logs and stop for approval.
```

---

# 11. Browser QA

Start local server from the clean worktree.

Suggested:

```bash
TESTING=true ENVIRONMENT=development SECRET_KEY="local-run-signing-key-please-rotate-abcdef1234" DATABASE_URL="sqlite:///./kinjo_local_run.db" python -m uvicorn main:app --host 127.0.0.1 --port 8099
```

Verify:

```text
/admin/agency-reports
/admin/agency-reports/moe
/admin/agency-reports/moe/kg2_eligibility
/admin/agency-reports/moh/vaccination_due_children
/admin/agency-reports/moh/health_absence_summary
/admin/agency-reports/dos/children_statistical_profile
/admin/agency-reports/ncfa/child_family_profile
/admin/agency-reports/ncfa/family_communication_counts
/admin/agency-reports/mol/workforce_summary
/admin/agency-reports/mol/training_compliance
/admin/agency-reports/mosd/kindergarten_registry
/admin/agency-reports/mosd/child_safety_protection
/admin/agency-reports/mopic/service_access_gaps
/login
/admin/dashboard
```

Browser QA checklist:

```text
HTTP 200 for expected routes.
No console errors.
No raw Jinja tags.
No mojibake.
Arabic RTL alignment correct.
Agency logos visible and not distorted.
وزارة التربية والتعليم appears correctly.
No duplicate MOSD bottom block.
Only CSV/chart export buttons visible on report pages.
Privacy badge visible.
Help panel visible.
KG2 filters aligned.
Governorate dropdown not free text.
Dependent dropdowns work if data source is available.
Empty/loading/error states render correctly.
Official KinJo logo appears in layout/auth/admin pages.
No KJ/Kj visual brand marks remain.
No broken image paths.
Mobile viewport works.
Keyboard focus visible.
```

Save screenshots locally only:

```text
.local-qa/agency-reports-ux/
```

Do not commit screenshots unless the repo already tracks QA screenshots by convention.

---

# 12. Git Scope Check Before Commit

Before commit:

```bash
git status --short
git diff --stat
git diff --name-only
```

Confirm every changed file belongs only to:

```text
agency reports UI/UX
agency report labels/help/status/export controls
official KinJo logo usage
Arabic RTL/accessibility fixes
tests for these changes
administrative-division lookup only if source file exists and is required
```

Do not include:

```text
#29 unrelated rebasing files
#26 dashboard redesign files unless directly required for shared logo/header
local DB
screenshots
logs
temp files
dirty shared worktree changes
.claude
.kilo
```

---

# 13. Commit, Push, PR

Commit only intended files:

```bash
git add <only intended files>
git commit -m "feat(admin): polish agency reports UX and logo usage"
```

Push:

```bash
git push -u origin feat/admin-agency-reports-ux-polish
```

Open PR:

```bash
gh pr create \
  --base main \
  --head feat/admin-agency-reports-ux-polish \
  --title "feat(admin): polish agency reports UX and logo usage" \
  --body "<complete PR body>"
```

PR body must include:

```text
## Summary
- Improves /admin/agency-reports and official agency report pages.
- Renames وزارة التربية to وزارة التربية والتعليم.
- Enlarges and standardizes agency logos.
- Adds admin help labels, privacy badges, status badges, empty/loading/error guidance.
- Standardizes export controls to CSV and chart export.
- Improves KG2 report filter layout and RTL alignment.
- Replaces temporary KJ/Kj/text-logo brand marks with official kinjo-logo asset where used as a visual logo.

## Privacy
- Reports remain aggregated only.
- No child, parent, national ID, phone, exact address, or sensitive data is exposed.
- CSV exports contain aggregated data only.

## Terminology
- Uses الحضانة / الحضانات for platform terminology.
- Documents any unavoidable exceptions.

## Verification
- ruff:
- py_compile:
- targeted tests:
- full pytest:
- browser QA:
- accessibility/RTL QA:
- export/privacy QA:

## Scope
Changed files:
- ...

## Risks / Not Done
- Administrative Excel import status:
- Logo asset status:
- Any missing data/asset blockers:
- No migration --apply was run.
```

---

# 14. GitHub CI and Merge

After PR is open:

```bash
gh pr checks --watch
```

If checks fail:

```text
Inspect logs.
Fix only in-scope issues.
Commit and push.
Wait again.
```

Before merge, verify:

```bash
gh pr view --json state,mergeable,mergeStateStatus,headRefName,baseRefName
gh pr checks
git fetch origin --prune
git status --short
```

Merge only when all are true:

```text
PR is OPEN.
Base is main.
Mergeable is MERGEABLE.
Merge state is CLEAN or equivalent green state.
All GitHub checks are green.
No pending checks.
Full local test suite is green.
Browser QA is complete.
Scope is clean.
No unrelated files.
No conflicts.
No missing logo asset.
No privacy regression.
No forbidden platform terminology in admin UI.
```

Merge method:

```bash
gh pr merge --squash --delete-branch
```

After merge:

```bash
git fetch origin --prune
git log origin/main -10 --oneline
gh pr view --json state,mergedAt,mergeCommit
```

Cleanup only the task worktree:

```bash
cd "D:/Final Version"
git worktree remove --force "../Final Version-agency-reports-ux"
git worktree prune
```

Do not remove:

```text
D:\Final Version
D:\Final Version-loc29
D:\Final Version-main-run
D:\Final Version-parent-audit
D:\Final Version-supervisor-audit
Any active concurrent-agent worktree
```

---

# 15. Final Report

Return this final report:

```text
Branch:
PR:
Starting main SHA:
Ending main SHA:
Merge commit:
Files changed:
Summary:
Agency reports verification:
KG2 filter verification:
Privacy verification:
Terminology verification:
Logo verification:
Tests:
Browser QA:
CI:
Worktree cleanup:
Remaining risks:
Final status:
```

Final rule:

You are allowed to implement locally, commit, push, open PR, watch CI, and merge, but only after all gates pass. Do not merge if there are conflicts, red checks, pending checks, missing assets, missing Excel source, privacy risks, dirty scope, or unrelated changes.
