# KPI Enhancement Plan

## 1) Baseline (Step 0: Run & Observe)
- Date observed: February 11-12, 2026.
- Target page: `/kpi/dashboard`.
- APIs observed:
  - `GET /api/kpi/filters`
  - `GET /api/kpi/dashboard-data`
  - `GET /api/kpi/manager/dashboard`
- Baseline issues observed:
  - `dashboard-data` with governorate filters was intermittently timing out.
  - KPI pipeline had placeholder metrics (`parent_satisfaction`, `checklist_compliance`, `regulatory_status`).
  - Dashboard response had no per-metric data-quality/coverage indicators.
  - Admin filter experience lacked city/area and dimension-level controls.

## 2) KPI Pipeline Inventory (Step 1)
- Main router/service: `kpi_service.py`.
- Dashboard template and JS: `templates/kpi/dashboard.html` + `templates/components/filter_panel.html`.
- Current data sources in ORM:
  - `OperatingCalendar`, `EnrollmentApplication`, `AttendanceLog`, `Incident`, `StaffPresenceLog`, `RatioCompliance`
  - `Survey`, `SurveyResponse`
  - `TrainingModule`, `StaffTrainingCompletion`
  - `KPISnapshot`, `GovernanceScore`, `KPITarget`
- Missing source for checklist KPI:
  - Added `DailyChecklist` model + migration (`daily_checklists` table).

## 3) KPI Catalog (Definitions, Formula, Data)
| KPI | Formula | Tables | Notes |
|---|---|---|---|
| Attendance Rate | attended child-days / expected child-days * 100 | `attendance_logs`, `enrollment_applications`, `operating_calendar` | Expected child-days now respects enrollment overlap + open days. |
| Chronic Absence | children with absence >= 10% / children with expected days * 100 | same as attendance | Uses expected days per child (not raw logged days). |
| Incident Rate | incidents / attended child-days * 100 | `incidents`, `attendance_logs` | Denominator tied to attended child-days. |
| Serious Incident Rate | high/critical incidents / attended child-days * 100 | `incidents`, `attendance_logs` | `HIGH` and `CRITICAL` only. |
| Incident Follow-up SLA | closed-within-SLA / follow-up-required * 100 | `incidents` | If no follow-up-required incidents => no-data state. |
| Ratio Compliance | compliant minutes / operating minutes * 100 | `ratio_compliance` (+ fallback from `staff_presence_logs` + attendance) | Uses cache table first, fallback estimator when cache missing. |
| Regulatory Status | license validity scoring (0/60/100) | `kindergartens` | License-only for now; inspections marked as not yet tracked. |
| Checklist Compliance | completed checklists / required checklists * 100 | `daily_checklists`, `operating_calendar` | Required = open days * checklist types (`opening/safety/closing`). |
| Training Coverage | completed required training / expected completions * 100 | `training_modules`, `staff_training_completion`, `users` | No staff/modules => no-data state. |
| Parent Satisfaction | NPS transformed to 0..100 (`(NPS+100)/2`) + response rate | `surveys`, `survey_responses`, enrollments via parent-child mapping | No responses => no-data state. |
| GQI | Weighted dynamic average of ratio/checklist/regulatory/training/SLA | above | Missing components are excluded from weight normalization. |
| CEI | Weighted dynamic average of attendance/chronic inverse/serious inverse/satisfaction | above | Missing components are excluded from weight normalization. |
| Final Governance Score | weighted blend of GQI (60%) + CEI (40%), dynamic normalization | computed | Band: GREEN/AMBER/RED + expired license override to RED. |

### Exclusions and Edge Cases
- Closed days excluded through `OperatingCalendar` (or default Friday closure in non-testing mode).
- Inactive or non-overlapping enrollments excluded from expected denominators.
- If denominator missing (no expected days, no follow-up incidents, no surveys, etc.), KPI is marked no-data with reason.

## 4) Visibility Rules (Admin vs Manager)
- Admin:
  - Network overview by default.
  - Can filter by governorate/city/area/kindergarten.
  - Can use `dimension_type` + `dimension_id` (`NETWORK`, `GOVERNORATE`, `CITY`, `AREA`, `KINDERGARTEN`).
  - Sees rankings (top/bottom).
- Manager:
  - Strictly scoped to assigned kindergarten.
  - Any cross-scope dimension/filter request returns `403`.

## 5) DB Reflection & Migrations
- Added ORM model:
  - `DailyChecklist` with status enum `DailyChecklistStatus`.
- Added migration:
  - `alembic/versions/20260213_daily_checklists_kpi.py`.
  - Creates `daily_checklists` table + indexes + uniqueness constraint.
- Seed updates:
  - `scripts/seed_data.py` now seeds attendance, reports, incidents, ratio rows, checklists, training records, and surveys for KPI realism.

## 6) Performance Strategy
- Replaced repeated KPI recomputation loop with consolidated bundle computation:
  - `KPIService.compute_kpi_bundle(...)`.
- Dashboard endpoint now computes once per kindergarten for summary cards/rankings.
- Trend windows use cached bundle-per-window during request.
- Added guardrail:
  - Daily trend requests limited to 93 days.

## 7) UI Plan and Applied Changes
- Dashboard filter panel now supports:
  - Governorate, city, area, kindergarten, granularity, date range.
- Added dashboard card quality metadata handling:
  - `has_data`, `data_coverage`, `no_data_reason`.
- Admin filter API now returns:
  - `cities`, `areas`, `dimension_types` in addition to existing filters.
- Manager dashboard endpoint now delegates to consolidated endpoint for consistency.

## 8) Backfill/Refresh Plan
- Existing:
  - `POST /api/kpi/populate-ratio-compliance` (historical ratio cache fill).
- Added:
  - `POST /api/kpi/admin/backfill-governance` (admin-only, idempotent update/create of governance scores across KGs for a period).

## 9) Known Limits
- Regulatory KPI currently uses license validity only (inspection model not yet implemented).
- Checklist workflow form/pages are not yet expanded in admin UI (KPI reads from table and supports no-data state until records exist).
