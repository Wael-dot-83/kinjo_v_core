# Manager Module Hardening — Audit & Decisions

Branch: `fix/manager-scope-analytics`
Scope: manager-facing class, daily-report, dashboard and analytics endpoints.

This document records every fix implemented, the evidence/verification, and the
production decisions taken where the requirement was ambiguous.

## Security / data-scope (IDOR)

| # | Endpoint / area | Fix | Verified by |
|---|---|---|---|
| 1 | `GET /api/classes/{id}/capacity-status` | Role + kindergarten scope via `get_class_for_user_or_404`; cross-tenant/soft-deleted → 404; wrong role → 403 | `TestClassCapacityStatusIDOR` |
| 2 | `GET /api/classes/{id}/required-supervisors` | Same scoped helper; previously had **no** auth at all | `TestRequiredSupervisorsIDOR` |
| 3 | `create_class` / `update_class` supervisor | Supervisor must be **ACTIVE, non-deleted, role SUPERVISOR, same kindergarten** | `TestCreateClassSupervisorValidation`, updated `test_manager_scope_requirements` |
| 4 | `list/get/update/deactivate/assign-child` classes | Shared `get_class_or_404(include_deleted=False)` / `get_class_for_user_or_404`; soft-deleted classes hidden everywhere | `TestSoftDeletedClassHidden` |
| 6 | Daily report edit/send/delete | `_get_daily_report_for_manager_or_404` scopes to the report's own `kindergarten_id`; cross-tenant → 404 | `TestDailyReportScope` |
| 14 | ManagerScope policy | Resource cross-tenant → **404** (no existence leak); wrong role → **403**; unassigned manager → account-scope error. Applied to class + daily-report + list-class-filter paths | covered across IDOR/scope tests |
| 16 | `get_eligible_supervisors` | Ignore soft-deleted `SupervisorAssignment` rows (`deleted_at IS NULL`) | `TestEligibleSupervisorsSoftDeleted` |

Shared helpers live in `dependencies.py`:
- `get_class_or_404(db, class_id, include_deleted=False)`
- `get_class_for_user_or_404(db, class_id, user, include_deleted=False)` — delegates
  scope to `ManagerScope.assert_kindergarten_access` (ADMIN any; MANAGER/SUPERVISOR
  own KG else 404; other role 403; no-KG 400).

## Business rules

| # | Fix | Verified by |
|---|---|---|
| 15 | Class capacity constrained to `[settings.CLASS_MIN_CAPACITY, settings.CLASS_MAX_CAPACITY]` (default **3–10**) on create **and** update | `TestClassCapacityRange` (1,2→400; 3,10→201; 11→400) |

## Daily-report workflow

| # | Fix | Verified by |
|---|---|---|
| 7 | `send_report_to_parents` is **atomic** — status change, `approved_by/at`, parent `Message`, and both audit rows commit in one transaction; any error rolls the whole thing back (no report left `SENT_TO_PARENT` without its parent message) | `TestSendReportAtomic` |
| 8 | List endpoint uses **typed** `from_date`/`to_date: date` params → malformed date returns **422**, not 500 | `TestDailyReportQueryValidation` |
| 9 | Unknown `report_status` returns **400** with the allowed values, instead of being silently ignored | `TestDailyReportQueryValidation` |

## Analytics correctness

| # | Fix | Verified by |
|---|---|---|
| 5 | Dashboard counts hardened. Report counts (`pending_daily_reports`, `reports_sent_today`) now filter `DailyReport.kindergarten_id` directly instead of joining `Child→EnrollmentApplication`; attendance counts filter `PRESENT/LATE`, scope to ACTIVE enrollment, and use `func.count(DISTINCT …)` | `TestDashboardCountsAnchoring` |
| 10 | `compute_enrollment_trend` implements **weekly** (ISO week start, `YYYY-MM-DD`) and **monthly** (`YYYY-MM`) aggregation (previously returned `[]`) | `TestEnrollmentTrendGrouping` |
| 11 | `compute_absenteeism_rate` denominator uses `_count_operating_days` (Jordan Sun–Thu + `OperatingCalendar`), not raw calendar days | `TestAbsenteeismOperatingDays` |
| 12 | `get_drilldown_by_class` counts only `_ATTENDED_STATUSES` (PRESENT/LATE) and divides by operating days | `TestClassDrilldownAttendance` |
| 13 | Incident date filters use `func.date(occurred_at)` (inclusive of the whole end date), so an incident on `end_date` at 23:00 is counted | `TestManagerAnalyticsIncidentBoundary` |

## Production decisions (ambiguous requirements)

1. **Daily-report scope anchored to `report.kindergarten_id`.**
   The `DailyReport` model stores its own `kindergarten_id`, which is the
   authoritative context for the kindergarten a report was filed in. We scope
   edit/send/delete by `report.kindergarten_id == manager.kindergarten_id`
   rather than the child's *current* active enrollment. This is more robust
   (a report cannot be silently re-scoped when a child transfers), fully blocks
   cross-tenant access (→ 404), and matches the task's "unless the model stores
   report context" exception.

2. **A MANAGER cannot be a class supervisor.**
   Per task #3 and FRD C5 (MANAGER and SUPERVISOR are mutually exclusive for a
   single user), `create_class`/`update_class` require the supervisor to have
   role `SUPERVISOR`. A manager — even one holding a self `SupervisorProfile` —
   is rejected. The one existing test asserting the old lax behaviour
   (`test_manager_can_create_class_as_own_supervisor`) was updated to assert
   rejection and renamed accordingly.

3. **#5 "duplicate counts" — root-caused, not assumed.**
   Same-kindergarten enrollment fan-out is *structurally impossible* because of
   the `uq_enrollment_child_kindergarten` unique constraint (one enrollment per
   child per kindergarten). The genuine defect was that the join-based report
   counts *undercounted* a report whose child had no enrollment row; anchoring
   the counts to `DailyReport.kindergarten_id` fixes that and decouples the
   metric from enrollment state. The regression test proves this exact behaviour.

## Known limitations / out of scope

- `POST /api/supervisor/assign` (a different endpoint, not in this change set)
  still permits assigning a MANAGER via that path; only `create_class`/
  `update_class` were hardened here. Aligning that endpoint with FRD C5 is a
  follow-up.
- The pre-existing Alembic-on-Postgres migration debt is tracked separately in
  issue #19 and is unrelated to this branch.

## HTTP semantics used

- 401 unauthenticated · 403 wrong role · 404 not found / outside manager scope
  (no existence leak) · 400/422 invalid input · 409 business conflict.
