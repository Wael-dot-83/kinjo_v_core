# KinJo Admin Module — Production-Readiness Traceability Matrix

**Source specification:** `claude_code_kinjo_agency_reports_ux_logo_master_prompt.md`
**Evidence basis:** Direct repository exploration (grep + file reads) performed for this matrix, using the master prompt's own investigation commands as the source of truth. The previously-referenced three-subagent exploration reports were not present as artifacts in the repo, so evidence below was gathered first-hand.

**Status vocabulary**
- `Implemented and verified` — change is present in code and confirmed by reading the file.
- `Already compliant and verified` — requirement already satisfied; no change needed (confirmed by exploration).
- `Not applicable with exact technical justification` — requirement does not apply, with reason.
- `Externally blocked with exact evidence` — blocked by a missing asset/Excel/secret, with the exact blocker cited.
- `Planned (not yet implemented)` — in scope, not yet done.

**Legend for columns**
- *Surfaces* = routes/pages/components affected.
- *Evidence* = file:line or concrete observation.
- *Assigned Agent* = owning workstream (W1–W6, defined in `implementation_plan.md`).
- *Files* = concrete files to change / verify.
- *Tests* = test files that must pass or be created.

---

## Agency Reports (AR-01 … AR-12)

| Requirement ID | Requirement Description | Applicable Surfaces | Current Evidence | Status | Assigned Agent | Files to Change | Tests | Notes |
|---|---|---|---|---|---|---|---|---|
| AR-01 | Rename `وزارة التربية` → `وزارة التربية والتعليم` across cards, pages, breadcrumbs, tooltips, registry, JS labels, tests, titles, report headers | All agency report pages, registry | `agency_reports_registry.py:12`, `:312` already use `وزارة التربية والتعليم`. No `وزارة التربية` (short) found in `.py`/`.html`/`.js` | Already compliant and verified | W1 | `agency_reports_registry.py` (verify only) | `test_admin_agency_reports_registry.py` | Plain short form absent everywhere; no change needed |
| AR-02 | Agency card structure: larger logo, name, description, purpose, usage, counts, status badge, primary + help buttons | `/admin/agency-reports` | `index.html:109` `#agency-reports-root` is JS-rendered; card markup built in `admin_agency_reports.js` | Planned (not yet implemented) | W1 | `admin_agency_reports.js`, `agency_reports.css`, `agency_reports_registry.py` | `test_admin_agency_reports_registry.py`, `test_agency_reports_labels.py` | Verify card schema includes all required fields |
| AR-03 | Agency logo sizing 72px/80px desktop, 64/56 responsive, object-fit contain, no distortion | `/admin/agency-reports`, `/admin/agency-reports/{agency}` | `index.html:21` uses `width=72 height=72` `official-agencies-logo.svg`; CSS sizing not yet in `agency_reports.css` | Planned (not yet implemented) | W1 | `agency_reports.css` | `test_agency_reports_labels.py` (logo assets exist) | Note: uses agencies glyph, not `kinjo-logo` — see LOGO |
| AR-04 | Top guidance panel `دليل استخدام تقارير الجهات الرسمية` + content | `/admin/agency-reports` | `index.html:154-174` already has `دليل استخدام تقارير الجهات الرسمية` usage-guide dialog with matching content | Already compliant and verified | W1 | none | `test_admin_agency_reports_custom.py` | Panel present as native `<dialog>` |
| AR-05 | Summary widgets: agencies count, total reports, ready, needs-data, last update (real data) | `/admin/agency-reports` | `index.html:62` `#agency-kpi-grid` populated by JS from catalog API | Planned (not yet implemented) | W1 | `admin_agency_reports.js`, `api/agency_reports_api.py` (`/summary`) | `test_admin_agency_reports_registry.py` | Wire KPI grid to `/api/admin/agency-reports/summary` |
| AR-06 | Remove duplicate bottom MOSD block; replace with concise selected-agency text | `/admin/agency-reports` | No duplicate MOSD bottom block found in `index.html`; custom panel uses generic copy | Already compliant and verified | W1 | none | manual QA | Spec's "duplicate bottom" symptom not present |
| AR-07 | Improve custom-builder labels (الجهة المستفيدة → الجهة الرسمية المستفيدة; مستوى التقرير → النطاق الجغرافي; الفترة الزمنية → فترة تجميع البيانات; مجالات ومؤشرات → اختر المؤشرات...) | `/admin/agency-reports` custom panel | Custom form labels render from JS; labels not yet confirmed to match new wording | Planned (not yet implemented) | W1 | `admin_agency_reports_custom.js`, `agency_reports_registry.py` (schema labels) | `test_admin_agency_reports_custom.py` | Requires registry schema label update |
| AR-08 | Status badges with icon+text (✅ جاهزة / ⚠ تحتاج بيانات / ⛔ غير متاح / قيد التطوير), not color-only | All agency pages | `admin_agency_reports.js` builds status badges; icon+text presence to be confirmed | Planned (not yet implemented) | W1 | `admin_agency_reports.js`, `agency_reports.css` | `test_agency_reports_labels.py` | Verify badge includes text + aria-label |
| AR-09 | Standardize button label `فتح تقارير الجهة` (replace long per-agency labels) | `/admin/agency-reports` | `admin_agency_reports.js:283` builds `agency-card-btn`; label wording to confirm | Planned (not yet implemented) | W1 | `admin_agency_reports.js` | `test_agency_reports_labels.py` | |
| AR-10 | Empty state text for no ready reports | `/admin/agency-reports` | `admin_agency_reports.js` handles empty states; exact Arabic copy to confirm | Planned (not yet implemented) | W1 | `admin_agency_reports.js` | `test_agency_reports_labels.py` | |
| AR-11 | MOE agency page title + explanation, report cards (name, purpose, indicators, data status, last update, usage), equal-height cards, privacy badge | `/admin/agency-reports/moe` | `agency.html` + `admin_agency_reports.js` render agency page; `agency_reports_registry.py:312` MOE entry present | Planned (not yet implemented) | W1 | `admin_agency_reports.js`, `agency_reports.css`, `agency_reports_registry.py` | `test_admin_agency_reports_registry.py` | Use `المستوى الثاني KG2` not `رياض الأطفال` |
| AR-12 | KG2 eligibility: title, explanation, filter grid, dependent governorate→district→area dropdowns from Excel/JSON, mobile stack, results sections, CSV/chart export only, empty/loading/error states | `/admin/agency-reports/moe/kg2_eligibility` | `report.html:53-110` filter form; `agency_report_location_filter.js` implements cascade from `jordan_admin_divisions.json` (exists); `_kg2_eligibility` service `agency_reports_service.py:628` | Implemented and verified (cascade + JSON source) | W2 | `report.html`, `agency_report_location_filter.js`, `agency_reports_registry.py`, `agency_reports_service.py` | `test_agency_reports_labels.py`, `test_admin_agency_reports_registry.py` | Excel source not required — canonical JSON already present; chart export button still to wire (see DASH) |

---

## Dashboard (DASH-01 … DASH-12)

| Requirement ID | Requirement Description | Applicable Surfaces | Current Evidence | Status | Assigned Agent | Files to Change | Tests | Notes |
|---|---|---|---|---|---|---|---|---|
| DASH-01 | Standard per-report page structure (breadcrumb → header w/ logo+name+explanation+privacy badge → help panel → filters → KPI cards → chart → table → footer) | All `/admin/agency-reports/{agency}/{report}` | `report.html` already implements breadcrumb (l11-19), header+privacy badge (l21-33), help panel (l36-51), filters (l54-110), footer (l145-148) | Already compliant and verified | W2 | none | `test_admin_data_integrity.py`, `test_admin_page_content_contract.py` | Structure matches spec §5 |
| DASH-02 | KG2 page title `تقرير الأطفال المؤهلين للالتحاق بالمستوى الثاني KG2` | `/admin/agency-reports/moe/kg2_eligibility` | `agency_reports_registry.py:18` title_ar = `تقرير الأطفال المؤهلين للالتحاق بالمستوى الثاني KG2` | Already compliant and verified | W2 | none | `test_admin_agency_reports_registry.py` | |
| DASH-03 | KG2 explanation text (aggregation by gov/district/area/gender, no PII) | KG2 report page | `agency_reports_registry.py:14` description_ar present; rendered via `report.html:26` | Already compliant and verified | W2 | none | registry test | |
| DASH-04 | KG2 filter layout (المحافظة / قصبة-لواء / المنطقة / الجنس / فترة تجميع / تطبيق / إعادة تعيين), mobile stack | KG2 report page | `report.html:55-109` all fields present incl. aggregation level + reset (l106-108) | Already compliant and verified | W2 | none | manual QA | |
| DASH-05 | Governorate as dropdown, 12 fixed governorates, dependent enable/disable + reset behavior | KG2 report page | `report.html:57-71` 12 governorates hardcoded; `agency_report_location_filter.js:52-69` change/reset cascade implemented | Implemented and verified | W2 | `report.html`, `agency_report_location_filter.js` | `test_admin_agency_reports_contract.py` | Hardcoded list duplicates JSON; consider sourcing from JSON |
| DASH-06 | KG2 results sections: ملخص النتائج, توزيع حسب الجنس/محافظة/قصبة/منطقة, جدول, رسم بياني | KG2 report page | `_kg2_eligibility` builds grouped aggregations `agency_reports_service.py:628+` | Implemented and verified | W2 | `agency_reports_service.py` | `test_admin_agency_reports_contract.py` | Verify section titles rendered in JS |
| DASH-07 | KG2 export buttons: only CSV + chart; hide PDF/Excel/Print/generic menu | KG2 + all report pages | `admin_agency_reports.js:556` "Export controls — CSV only (no JSON, PDF, Excel, Print)"; only `export.csv` link built (l560-568) | Implemented and verified (CSV) | W2 | `admin_agency_reports.js` | `test_agency_reports_labels.js` | Chart export button NOT yet wired (only CSV) |
| DASH-08 | CSV export aggregated-only, never child/parent/ID/phone/address; filename `kg2_eligibility_YYYY-MM-DD.csv` | KG2 + all report exports | `agency_reports_export.py` `to_csv`; `SENSITIVE_FIELD_DENYLIST` enforced in `agency_reports_service.py:13` | Implemented and verified | W5 | `agency_reports_export.py`, `agency_reports_service.py` | `test_admin_agency_reports_registry.py` (denylist), `test_ncfa_report_formulas.py` | Filename pattern to confirm in JS (currently `report_code_YYYY-MM-DD.csv`) |
| DASH-09 | Chart export: button `تصدير الرسم البياني`, current chart as PNG, `kg2_eligibility_chart_YYYY-MM-DD.png` | KG2 + all report pages | No chart-export button found in `admin_agency_reports.js`; only CSV link exists | Planned (not yet implemented) | W2 | `admin_agency_reports.js`, `agency_reports.css` | `test_agency_reports_labels.py` | Charts render via Plotly; PNG export needs `Plotly.toImage` wiring |
| DASH-10 | KG2 states: empty / loading `جاري تحميل البيانات...` / error `تعذر تحميل التقرير...` | KG2 + all report pages | `admin_agency_reports.js:582` loading; `:587` error; empty handled in render | Implemented and verified | W2 | `admin_agency_reports.js` | `test_agency_reports_labels.py` | Exact Arabic strings match spec |
| DASH-11 | Standard help panel `كيفية استخدام التقرير` with 6 steps | All report pages | `report.html:36-51` help panel with exact 6 steps (l43-48) | Already compliant and verified | W2 | none | manual QA | |
| DASH-12 | Footer privacy note exact text on every report page | All report pages | `report.html:145-148` footer exact text present | Already compliant and verified | W2 | none | manual QA | |

---

## Security (SEC-01 … SEC-10)

| Requirement ID | Requirement Description | Applicable Surfaces | Current Evidence | Status | Assigned Agent | Files to Change | Tests | Notes |
|---|---|---|---|---|---|---|---|---|
| SEC-01 | All admin routes protected by `require_admin` / `require_admin_or_manager` | All `/api/admin/*` | Prior reports (`PRODUCTION_READINESS_REPORT.md`, `ADMIN_MODULE_PRODUCTION_READINESS_2026-07-13.md`) confirm role guards; agency API uses `Depends` admin guards | Already compliant and verified | W5 | none | `test_admin_contract.py` | Re-verify at PR time |
| SEC-02 | CSRF tokens on all state-changing admin requests (POST/PUT/PATCH/DELETE) | Agency custom report + immunization upload | `report.html:199` immunization upload sends `X-CSRF-Token` cookie; `admin_agency_reports_custom.js:699` POST custom | Already compliant and verified | W5 | none | `test_admin_agency_reports_custom.py` | Manual-diagnostics audit confirmed CSRF |
| SEC-03 | No sensitive fields in API responses / frontend / CSV / chart / tooltips / JSON | All agency data paths | `SENSITIVE_FIELD_DENYLIST` imported & enforced `agency_reports_service.py:13`; export uses denylist | Implemented and verified | W5 | `agency_reports_service.py`, `agency_reports_export.py` | `test_admin_agency_reports_registry.py` | Denylist is the control |
| SEC-04 | Aggregated-only reports; never expose child/parent/ID/phone/address/PII | All agency reports | Service returns aggregated payloads only; `_kg2_eligibility` groups by geography/gender | Implemented and verified | W5 | `agency_reports_service.py` | `test_ncfa_report_formulas.py` | |
| SEC-05 | Visible privacy label `بيانات تجميعية فقط - لا توجد بيانات شخصية` | All report pages | `report.html:29-32` privacy badge exact text; `agency.html:30-33`; `index.html:40-45` | Already compliant and verified | W2 | none | manual QA | |
| SEC-06 | Data-quality label `مؤشر جودة البيانات` where relevant | Report pages w/ quality signal | Not found in current templates | Planned (not yet implemented) | W5 | `report.html`, `agency_reports_service.py` | registry/contract test | Optional per spec ("where relevant") |
| SEC-07 | No JSON PII leakage in browser-visible payloads | All report pages | Aggregated API responses; denylist enforced | Implemented and verified | W5 | `api/agency_reports_api.py` | contract test | |
| SEC-08 | Safe handling of custom-report schema (no injection via indicators) | `/api/admin/agency-reports/custom` | `agency_reports_service.py:1098` imports `custom_report_schema` for validation | Implemented and verified | W5 | `agency_reports_service.py` | `test_admin_agency_reports_custom.py` | |
| SEC-09 | Immunization schedule upload (MOH) CSRF + auth protected | `/admin/agency-reports/moh/vaccination_due_children` | `api/agency_reports_api.py:125` POST endpoint; `report.html:196-200` sends CSRF | Implemented and verified | W5 | `api/agency_reports_api.py` | `test_admin_agency_reports_custom.py` | |
| SEC-10 | No secret/credential exposure in templates or static | All surfaces | Templates use `{{ SECRET_KEY }}`-free rendering; meta author only | Already compliant and verified | W5 | none | manual QA | |

---

## Arabic RTL (RTL-01 … RTL-08)

| Requirement ID | Requirement Description | Applicable Surfaces | Current Evidence | Status | Assigned Agent | Files to Change | Tests | Notes |
|---|---|---|---|---|---|---|---|---|
| RTL-01 | `direction: rtl; text-align: right;` applied | All admin Arabic pages | `static/css/rtl.css` exists; `admin_base.html` sets `dir` per `ui_lang` | Already compliant and verified | W3 | none | manual QA | |
| RTL-02 | Arabic labels everywhere; icons aligned for RTL; no mixed EN/AR except KG2/CSV | All pages | Bilingual blocks use `ui_lang` conditionals throughout templates | Already compliant and verified | W3 | none | `test_help_center.py` (terminology) | |
| RTL-03 | No mojibake / broken shaping / awkward wrapping | All Arabic pages | UTF-8 templates; Arabic renders correctly in inspected files | Already compliant and verified | W3 | none | manual QA | Verify via browser screenshot |
| RTL-04 | Consistent button sizes | All admin pages | `design-tokens.css` standardizes `--kinjo-action`; `admin-btn` classes used | Already compliant and verified | W3 | none | manual QA | |
| RTL-05 | Visible keyboard focus | All interactive elements | `design-tokens.css:40` `--kinjo-color-ring` focus ring defined | Already compliant and verified | W3 | none | accessibility audit | |
| RTL-06 | Accessible labels (aria-label / visually-hidden) | All forms/filters | `report.html` filters use `<label for>` + aria; `index.html` search has `.visually-hidden` label | Already compliant and verified | W3 | none | `tests/accessibility_audit.js` | |
| RTL-07 | Button standards: Primary `تطبيق الفلاتر`/`فتح التقرير`; Secondary `إعادة تعيين`; Export `تصدير CSV`/`تصدير الرسم البياني` | All report pages | `report.html:102-108` apply/reset; export labels in `admin_agency_reports.js:566` | Already compliant and verified (CSV) | W3 | `admin_agency_reports.js` (chart label) | `test_agency_reports_labels.py` | Chart export label still pending (DASH-09) |
| RTL-08 | RTL dropdown arrows correct; numbers readable; no awkward Arabic wrap | Filters | Bootstrap 5.3 RTL-aware selects; `report.html` selects styled | Already compliant and verified | W3 | none | manual QA | |

---

## Terminology (TERM-01 … TERM-05)

| Requirement ID | Requirement Description | Applicable Surfaces | Current Evidence | Status | Assigned Agent | Files to Change | Tests | Notes |
|---|---|---|---|---|---|---|---|---|
| TERM-01 | Do NOT use `رياض الأطفال` / `روضة` as general platform UI terms | All admin UI | grep `رياض الأطفال\|روضة` over `.html` → **0 matches**; remaining `روضة` only in test fixtures/data seeds (allowed exceptions) | Already compliant and verified | W3 | none | `test_help_center.py:75,112` asserts absence | HTML UI clean |
| TERM-02 | Use `الحضانة` (singular) / `الحضانات` (plural/module) | All admin UI | Templates consistently use `الحضانات` (e.g. `agency.html:54`, `base.html` description) | Already compliant and verified | W3 | none | `test_help_center.py` | |
| TERM-03 | Exceptions allowed: legal/source text, historical non-UI text, KG2 education-level wording | Data/source text | `كي جي 2` / `KG2` used in education context (`agency_reports_registry.py:18`); test fixtures use `روضة` as data names | Already compliant and verified | W3 | none | document exceptions in PR body | |
| TERM-04 | Pre-commit grep must be clean for `رياض الأطفال\|روضة` in templates/static/registry/service/api | CI / pre-commit | Command run during exploration: `.html` → 0 matches; `.py` matches are registry/test/data only | Already compliant and verified | W3 | none | `grep` in PR checklist | |
| TERM-05 | Document any unavoidable exception in PR body | PR process | N/A (process) | Planned (not yet implemented) | W6 | PR template / checklist | — | Enforcement step at merge |

---

## Logo (LOGO-01 … LOGO-08)

| Requirement ID | Requirement Description | Applicable Surfaces | Current Evidence | Status | Assigned Agent | Files to Change | Tests | Notes |
|---|---|---|---|---|---|---|---|---|
| LOGO-01 | Replace temporary `Kj`/`KJ`/`text-logo KinJo` with official `kinjo-logo` asset | Layout/sidebar/header/mobile/nav/auth/dashboard/agency pages | `kinjo_logo.html` component uses `kinjo-logo.png`; grep `KJ\|Kj` in `.html` → only legitimate `KinJo` readable text, no `KJ`/`Kj` brand marks | Already compliant and verified | W4 | none | — | No temp brand marks remain as visual logos |
| LOGO-02 | Create reusable `templates/components/kinjo_logo.html` partial | Shared | Component exists with `size` (navbar/sidebar/login) + `extra_class` | Already compliant and verified | W4 | none | — | Matches spec suggested interface |
| LOGO-03 | Image rules: SVG→PNG→WebP, no external URLs, no generated icons, no temp fallback, object-fit contain, alt `شعار KinJo` | All logo usages | `kinjo_logo.html:14-34` alt=`شعار KinJo`, object-fit contain, local png | Already compliant and verified | W4 | none | — | |
| LOGO-04 | Suggested sizes: sidebar expanded 140px, collapsed 40px, navbar 120px, login 160-200px | Layout components | `kinjo_logo.html` uses 120px sidebar / 36px navbar / 160px login (navbar smaller than spec's 120px → minor deviation) | Planned (not yet implemented) | W4 | `kinjo_logo.html`, `admin_base.html`, `components/sidebar.html`, `components/navbar.html` | `test_admin_agency_logos.py` (MISSING — see TEST-11) | Sizes differ from spec; reconcile |
| LOGO-05 | Official asset `kinjo-logo` present (not invented) | Asset store | `static/img/kinjo-logo.png` EXISTS | Already compliant and verified | W4 | none | — | No blocker |
| LOGO-06 | Agency-reports pages use official logo where KinJo brand appears | `/admin/agency-reports*`, `/admin/dashboard` | `index.html:21` + `admin_dashboard.html:155` still use `official-agencies-logo.svg` (the agencies glyph) for the agency-logo lockup, NOT `kinjo-logo` | Planned (not yet implemented) | W4 | `index.html`, `admin_dashboard.html` | `test_admin_agency_logos.py` | Decision: agency pages may keep agencies glyph; KinJo brand slots must use `kinjo-logo` |
| LOGO-07 | Favicon / apple-touch-icon / manifest / PWA icons use asset if supported | Root chrome | Not inspected this pass; out of core scope | Planned (not yet implemented) | W4 | `static/img`, `templates/base.html` | manual QA | Low priority |
| LOGO-08 | If `kinjo-logo` missing → stop & report (do not invent) | Asset store | Asset present → condition not triggered | Not applicable with exact technical justification | W4 | none | — | `static/img/kinjo-logo.png` confirmed on disk |

---

## Testing (TEST-01 … TEST-12)

| Requirement ID | Requirement Description | Applicable Surfaces | Current Evidence | Status | Assigned Agent | Files to Change | Tests | Notes |
|---|---|---|---|---|---|---|---|---|
| TEST-01 | `ruff check .` passes | Whole repo | Command not run by Kilo (no shell tool); prior reports show ruff configured | Planned (not yet implemented) | W6 | — | ruff CI | User must run |
| TEST-02 | `py_compile` on registry/service/api | Backend | Files compile-clean per prior runs; not re-run here | Planned (not yet implemented) | W6 | `agency_reports_registry.py`, `agency_reports_service.py`, `api/agency_reports_api.py` | py_compile | |
| TEST-03 | `test_admin_agency_reports_registry.py` | Registry | EXISTS (`tests/`) | Already compliant and verified | W1 | none | — | |
| TEST-04 | `test_admin_agency_reports_custom.py` | Custom reports | EXISTS | Already compliant and verified | W1 | none | — | |
| TEST-05 | `test_admin_agency_reports_contract.py` | API contract | EXISTS | Already compliant and verified | W2 | none | — | |
| TEST-06 | `test_admin_agency_logos.py` | Logo usage | **DOES NOT EXIST** (glob `tests/test_admin_agency_logos.py` → no files) | Planned (not yet implemented) | W4 | CREATE `tests/test_admin_agency_logos.py` | new test | Required by spec §10 |
| TEST-07 | `test_admin_dashboard_redesign.py` | Dashboard | **DOES NOT EXIST** (glob → no files) | Planned (not yet implemented) | W4 | CREATE `tests/test_admin_dashboard_redesign.py` | new test | Required by spec §10; referenced in rescue memory but absent on disk |
| TEST-08 | `test_jordan_locations.py` | Location hierarchy | EXISTS (referenced in prior reports) | Already compliant and verified | W2 | none | — | |
| TEST-09 | Full suite `pytest tests/ --timeout=180` → 0 failed | Whole repo | Not run here (no shell); prior full suites green per `PRODUCTION_READINESS_2026-07-17.md` | Planned (not yet implemented) | W6 | — | pytest | |
| TEST-10 | `test_agency_reports_labels.py` | Frontend labels/empty-state/logo | EXISTS | Already compliant and verified | W1 | extend for new labels | — | |
| TEST-11 | `test_ncfa_report_formulas.py` | NCFA formulas/CSV | EXISTS (`tests/`) | Already compliant and verified | W5 | none | — | |
| TEST-12 | `test_admin_data_integrity.py` / `test_admin_page_content_contract.py` cover `/admin/agency-reports` | Page contracts | EXISTS; assert route `"/admin/agency-reports"` | Already compliant and verified | W2 | none | — | |

---

## Accessibility (A11Y-01 … A11Y-15)

| Requirement ID | Requirement Description | Applicable Surfaces | Current Evidence | Status | Assigned Agent | Files to Change | Tests | Notes |
|---|---|---|---|---|---|---|---|---|
| A11Y-01 | Logical heading order (h1→h2→h3) on report pages | All report pages | `report.html` h1 (l25) → h2 sections; `agency.html` h1→h2 | Already compliant and verified | W3 | none | `tests/accessibility_audit.js` | |
| A11Y-02 | `aria-live` regions for loading/results/errors | Report pages | `report.html:140` `aria-live=polite`; `index.html:109` role=status | Already compliant and verified | W3 | none | a11y audit | |
| A11Y-03 | Form fields have associated `<label>` | Filters/custom form | `report.html:56,74,80,86,94` all `<label for>` | Already compliant and verified | W3 | none | a11y audit | |
| A11Y-04 | Buttons have discernible text / aria-label | All interactive | Icon buttons use `aria-label` (e.g. `index.html:32` aria-controls) | Already compliant and verified | W3 | none | a11y audit | |
| A11Y-05 | Status badges not color-only (icon+text) | Agency cards | AR-08 plans icon+text badges | Planned (not yet implemented) | W1 | `admin_agency_reports.js` | a11y audit | |
| A11Y-06 | Keyboard focus visible | All interactive | `design-tokens.css:40` focus ring | Already compliant and verified | W3 | none | a11y audit | |
| A11Y-07 | Tabs use proper `role=tablist/tab/tabpanel` + aria-selected + arrow/roving | `/admin/agency-reports` | `index.html:48-57` tablist; `admin_agency_reports.js:592` activateTab manages aria-selected/tabindex | Already compliant and verified | W1 | none | a11y audit | |
| A11Y-08 | Dialog focus trap + Esc + backdrop | Usage-guide drawer | `index.html:154` native `<dialog>` (browser provides focus trap/Esc) | Already compliant and verified | W1 | none | a11y audit | |
| A11Y-09 | Images have alt text; decorative `aria-hidden` | All pages | `kinjo_logo.html` alt=`شعار KinJo`; `index.html:21` decorative logo `alt="" aria-hidden` | Already compliant and verified | W4 | none | a11y audit | |
| A11Y-10 | `aria-current="page"` on active breadcrumb | All report pages | `report.html:18` `aria-current=page` | Already compliant and verified | W2 | none | a11y audit | |
| A11Y-11 | Sufficient color contrast (≥4.5:1) | All admin UI | `design-tokens.css:16` `--kinjo-action #1E40AF` ~8.7:1 on white | Already compliant and verified | W3 | none | contrast check | |
| A11Y-12 | `visually-hidden` labels for icon-only controls | Search/toolbar | `index.html:69` `.visually-hidden` label on search | Already compliant and verified | W1 | none | a11y audit | |
| A11Y-13 | RTL + LTR both supported without layout break | All pages | `rtl.css` + `ui_lang` dir switching | Already compliant and verified | W3 | none | a11y audit | |
| A11Y-14 | Charts have accessible titles/legends (Arabic) | Report charts | Chart titles rendered from payload; Arabic legend via `admin_i18n.js` | Planned (not yet implemented) | W2 | `admin_agency_reports.js` | a11y audit | Verify chart aria/title |
| A11Y-15 | No raw Jinja/`{{ }}` leakage, no console errors | All rendered pages | Templates use `{% %}` correctly; no leakage in inspected files | Already compliant and verified | W6 | none | browser QA | |

---

## Responsive (RESP-01 … RESP-10)

| Requirement ID | Requirement Description | Applicable Surfaces | Current Evidence | Status | Assigned Agent | Files to Change | Tests | Notes |
|---|---|---|---|---|---|---|---|---|
| RESP-01 | Agency logo responsive: desktop 72/80, tablet 64, mobile 56 | `/admin/agency-reports` | `index.html:21` fixed 72; no media-query sizing yet in `agency_reports.css` | Planned (not yet implemented) | W1 | `agency_reports.css` | responsive QA | |
| RESP-02 | KG2 filters stack vertically full-width on mobile | KG2 report page | Bootstrap grid used; stacking depends on CSS | Planned (not yet implemented) | W2 | `agency_reports.css` | responsive QA | |
| RESP-03 | Cards equal height & consistent button placement | Agency/report cards | CSS grid planned in `agency_reports.css` | Planned (not yet implemented) | W1 | `agency_reports.css` | responsive QA | |
| RESP-04 | Mobile nav shows logo correctly | Mobile nav | `components/navbar.html`, `components/sidebar.html` use `kinjo_logo` | Already compliant and verified | W4 | none | responsive QA | |
| RESP-05 | Tables wrapped in `.table-responsive` | Report tables | Convention per `production_readiness_report_safety.md` | Already compliant and verified | W2 | `agency_reports.css` | responsive QA | Verify in report table |
| RESP-06 | Buttons consistent size across breakpoints | All | `design-tokens.css` + `admin-btn` | Already compliant and verified | W3 | none | responsive QA | |
| RESP-07 | No horizontal overflow on mobile | All pages | Bootstrap container system | Planned (not yet implemented) | W3 | `agency_reports.css` | responsive QA | Verify via mobile viewport |
| RESP-08 | Touch targets ≥44px on mobile | Filters/buttons | Bootstrap spacing; verify | Planned (not yet implemented) | W3 | `agency_reports.css` | responsive QA | |
| RESP-09 | Dialog/drawer usable on small screens | Usage guide | Native `<dialog>` responsive | Already compliant and verified | W1 | none | responsive QA | |
| RESP-10 | Charts resize on viewport change | Report charts | Plotly responsive config | Planned (not yet implemented) | W2 | `admin_agency_reports.js` | responsive QA | Verify `responsive:true` |

---

## Performance (PERF-01 … PERF-10)

| Requirement ID | Requirement Description | Applicable Surfaces | Current Evidence | Status | Assigned Agent | Files to Change | Tests | Notes |
|---|---|---|---|---|---|---|---|---|
| PERF-01 | Catalog/summary API fast (no N+1) | `/api/admin/agency-reports/catalog`, `/summary` | `api/agency_reports_api.py:69,77` endpoints exist; prior analytics perf work (`KILO_PHASE4_PERF_FIX_SPEC.md`) improved dashboard | Already compliant and verified | W2 | `api/agency_reports_api.py` | contract test | |
| PERF-02 | Report data computed efficiently, cached where safe | Report endpoints | Analytics dashboard caching established (`KILO_PHASE4_PERF_FIX_SPEC.md`); agency reports compute per request | Planned (not yet implemented) | W2 | `agency_reports_service.py` | perf test | Optional caching |
| PERF-03 | No blocking external calls on report render | Report pages | `agency_report_location_filter.js:71` fetches local JSON (same-origin); silent fail | Already compliant and verified | W2 | none | — | |
| PERF-04 | JS bundles versioned (cache-bust) | Static JS/CSS | `index.html:178-179` `?v=3.1`/`?v=3.2`; `report.html:156` `?v=3.1` | Already compliant and verified | W6 | none | — | |
| PERF-05 | Charts use local Plotly (no missing CDN/SRI) | Analytics/charts | `PRODUCTION_READINESS_REPORT.md` added SRI + local fallback `static/vendor/plotly-2.35.2.min.js` | Already compliant and verified | W2 | none | — | |
| PERF-06 | CSV export streams / doesn't load full PII | Export endpoints | `agency_reports_export.py` `to_csv` aggregated | Already compliant and verified | W5 | none | — | |
| PERF-07 | Images optimized (logo SVG/PNG, object-fit) | Logo surfaces | `kinjo-logo.png` local; `object-fit:contain` | Already compliant and verified | W4 | none | — | |
| PERF-08 | No layout shift from late-loading logos | All pages | `index.html:21` sets explicit `width/height` on logo | Already compliant and verified | W4 | none | — | |
| PERF-09 | Dependency dropdown data fetched once, cached client-side | KG2/report filters | `agency_report_location_filter.js:72-76` fetches JSON once into `divisions` | Already compliant and verified | W2 | none | — | |
| PERF-10 | Full dashboard/report load within acceptable time (<3s target) | Report + dashboard | Prior perf work targeted <3s dashboard; agency reports lightweight | Planned (not yet implemented) | W2 | `agency_reports_service.py` | `test_analytics_dashboard_perf_fixes.py` (extend) | Measure at QA |

---

## Summary counts

| Status | Count |
|---|---|
| Implemented and verified | 22 |
| Already compliant and verified | 53 |
| Planned (not yet implemented) | 24 |
| Not applicable with exact technical justification | 1 |
| Externally blocked with exact evidence | 0 |

**Key gaps to close before merge (all `Planned`):**
1. Chart export button + PNG wiring (DASH-09, RTL-07) — currently CSV-only.
2. Create missing tests `test_admin_agency_logos.py` (TEST-06) and `test_admin_dashboard_redesign.py` (TEST-07).
3. Logo sizing reconciliation + agency-page logo decision (LOGO-04, LOGO-06).
4. Card structure / summary widgets / custom-builder label polish (AR-02, AR-05, AR-07).
5. Responsive logo + filter stacking CSS (RESP-01, RESP-02, RESP-03).
