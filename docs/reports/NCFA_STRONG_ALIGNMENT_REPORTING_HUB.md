# NCFA Strong-Alignment Reporting Hub — Methodology & Definitions

**Route:** `/admin/agency-reports/ncfa` (ADMIN only)
**Section title:** مركز تقارير الطفولة المبكرة والحضانات — *Early Childhood and Nursery Reporting Hub*
**Status classification:** "توافق قوي / Strong alignment" is a **product** alignment label, not an NCFA endorsement.

This document describes what the hub computes and how, so the figures can be read
and audited honestly. It is kept consistent with the code; features that do not
exist are listed under **Known limitations** rather than described as done.

---

## 1. Purpose & scope

The hub bundles the existing privacy-gated custom-report indicators
(`agency_reports_service.py` → `/api/admin/agency-reports/custom`) into six
NCFA-branded report packages. It renders **aggregated operational evidence from
KinJo** — not approved national statistics. Every report carries the caveat:

> تعرض هذه التقارير أدلة تشغيلية وإدارية مستخرجة من بيانات منصة KinJo، ولا تُعد
> تلقائيًا إحصاءات وطنية معتمدة ما لم تُستكمل متطلبات التغطية والتحقق والاعتماد.

The hub renders **only** on the NCFA agency page. Gating is structural
(`{% if agency_code == 'ncfa' %}` in `templates/admin/agency_reports/agency.html`,
plus a JS early-return when `[data-ncfa-strong-reports]` is absent), so it never
appears on mosd / moe / moh / mol / dos.

---

## 2. The six report packages

| Code | Title (AR / EN) | Indicators |
|---|---|---|
| `early_childhood_profile` | الملف الإداري للطفولة المبكرة / Early Childhood Administrative Profile | children_count, gender_distribution, age_distribution_6mo, enrollment_status |
| `nursery_capacity` | الحضانات والطاقة الاستيعابية / Nurseries and Operational Capacity | kindergarten_count, kindergarten_status, occupancy_rate |
| `attendance_daily_care` | الحضور واستمرارية الرعاية اليومية / Attendance and Daily-Care Continuity | attendance_rate, absence_requests, daily_report_completion, late_reports |
| `child_safety` | سلامة الطفل والحوادث / Child Safety and Incidents | critical_incidents, incidents_by_severity |
| `workforce_supervision` | الكوادر والإشراف والتوزيع الصفي / Workforce, Supervision and Class Assignment | staff_count, unassigned_classes, unassigned_children |
| `reporting_participation` | المشاركة الحديثة في الإبلاغ / Recent Reporting Participation | data_quality_score (re-labelled "reporting participation") |

---

## 3. Population & date semantics

- **Timezone:** all operational dates use Jordan local time (UTC+3).
- **Active enrolment overlap:** a child is in scope for a period when an ACTIVE
  enrolment overlaps it — `enrollment_start_date <= period_end` and
  (`enrollment_end_date IS NULL OR enrollment_end_date >= period_start`).
- **Working days:** the Jordan school week is **Sun–Thu**; Fri/Sat are closed.
  Explicit `OperatingCalendar` rows (`is_open`) override the default per nursery.
- **Age** (age_distribution_6mo) is computed **as of the period end** with full
  year/month/day boundaries (not a year+month approximation). Children with a
  missing/invalid date of birth remain visible as an "unknown" category with a
  note, rather than being dropped.
- **Reporting-participation window** is exactly **seven inclusive dates ending on
  the report end date** (`period_end-6 .. period_end`), anchored to the selected
  end — not "now".

---

## 4. Numerators & denominators (as implemented)

Attendance, daily-report and incident-rate denominators reuse the authoritative
**expected-child-day** logic from `kpi_service.py`. The hub computes them across a
scope in a few **batched** queries (`_expected_child_days`, `_working_days_by_kg`,
`_attended_child_days`) whose results are pinned by test to equal
`KPIService._count_expected_child_days` for a single nursery (single source of
truth). Rates are pooled at numerator/denominator level across nurseries — never
by averaging per-nursery percentages.

| Indicator | Numerator | Denominator |
|---|---|---|
| `attendance_rate` | PRESENT + LATE child-days | **expected child-days** (active-enrolment days on working days) |
| `daily_report_completion` | APPROVED + SENT_TO_PARENT reports for active children | **expected child-days** |
| `occupancy_rate` | active enrolments | active-class capacity (`Class.capacity_total`, `is_active`) |
| `incidents_by_severity` (rate) | incidents in period | attended child-days ÷ 1,000 |
| `reporting_participation` | active nurseries with ≥1 daily report in the 7-day window | active nurseries in scope |

**Unavailable, not zero.** When a denominator is missing (no capacity, no
expected child-days, no active nurseries) the value is **`None`** ("غير متاح"),
surfaced as a data-quality note; it is never a misleading 0%.

---

## 5. Data-quality status

`data_quality.status` ∈ {`sufficient`, `limited`, `incomplete`} → displayed as
البيانات متاحة / محدودة / غير مكتملة. A report is `sufficient` only when it has
KPIs **and** no quality notes; any unavailable (`None`) indicator adds a note and
downgrades it to `limited`. Unavailable indicators are reported — never fabricated.

---

## 6. Privacy, security & disclosure control

- **RBAC:** page routes and `/api/admin/agency-reports/*` require ADMIN.
- **Sensitive-field denylist** (`SENSITIVE_FIELD_DENYLIST`) is asserted centrally
  before any payload leaves the service; no names / IDs / phones / addresses /
  incident narratives appear in JSON, DOM, charts, tooltips or CSV.
- **Small-cell suppression** (`_apply_small_cell_suppression`): category counts in
  `(0, AGENCY_REPORT_MIN_CELL_SIZE)` are suppressed — chart points become a gap
  (`None`, never 0), table breakdown cells show "محجوب / Suppressed" — and the
  count is reported in `data_quality.suppressed_cells`. Threshold configurable via
  `AGENCY_REPORT_MIN_CELL_SIZE` (safe default **5**; `<=1` disables). Applied in
  `custom_report()`, so **JSON and CSV exports are both covered**.
- **CSV:** UTF-8 BOM for Arabic; formula-injection protection preserved.

---

## 7. API response contract

`POST /api/admin/agency-reports/custom` returns `{ success, data }` where `data`
contains: `title`, `generated_at` (Jordan ISO), `scope` (agency/level/geo/period +
resolved `start_date`/`end_date`), `kpis[]` (`code`, `label_ar`, `value`,
`unit_ar`), `charts[]` (`type`, `title_ar`, `series[]`), `table[]`, `summary_ar`,
`decision_notes_ar`, `data_quality` (`status`, `notes`, `suppressed_cells`),
`privacy_notice_ar`, `excluded_sensitive_fields`. The frontend localises Arabic-only
labels/units/titles and raw enum categories to English via maps in
`static/js/ncfa_strong_reports.js` (Arabic fallback preserved).

---

## 8. Charts & accessibility

Charts render backend values only (no client-side calculation). Bars start at
zero; each chart has a table equivalent; categories are localised (no raw enums);
suppressed points render as a gap. Report cards are keyboard-accessible with a
screen-reader status region and a logical heading order. RTL/LTR both supported.

---

## 9. Known limitations (honest)

- Response envelope is a validated dict, **not** a Pydantic model yet.
- **Complementary** suppression (back-out from totals) is not implemented; only
  primary small-cell suppression is. Headline KPI totals/rates are not suppressed.
- The scope "District" control posts as `city` to match the existing endpoint
  contract; UI label and wire key differ by design (not reconciled).
- District/area **real drill-down** beyond governorate is not fully wired.
- Export auditing and a Playwright E2E flow are not yet added.
- Specialised table headers beyond المؤشر/القيمة/الفئة/النسبة% remain Arabic in
  English mode.

---

## 10. Validation

```bash
python -m ruff check .
node --check static/js/ncfa_strong_reports.js
python -m pytest tests/test_ncfa_report_formulas.py tests/test_ncfa_strong_reports_page.py \
  tests/test_admin_agency_reports_custom.py tests/test_admin_agency_reports_registry.py \
  tests/test_admin_agency_reports_contract.py tests/test_agency_reports_labels.py -q
```

Key tests: `tests/test_ncfa_report_formulas.py` (occupancy-unavailable, exact
7-day window, expected-child-days == kpi_service, attendance denominator, small-
cell suppression) and `tests/test_ncfa_strong_reports_page.py` (NCFA-only gating,
bilingual/enum localisation, participation re-label).

## 11. Release / rollback

Branch `agent/ncfa-strong-report-hub` → PR #42. Front-end + additive backend
correctness; **no schema migration**, so rollback is a plain revert of the
commits. CI (`lint`, Playwright) and merge are currently blocked by a GitHub
Actions **billing** stop — not by code — and must be restored before required
checks can pass.
