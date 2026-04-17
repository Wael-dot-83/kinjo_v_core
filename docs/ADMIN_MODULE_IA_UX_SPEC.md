# Admin Module IA + UX Spec

## Baseline UX Inventory (Step 0)
- Date of baseline: 2026-02-11 (local environment).
- Current page `/kpi/dashboard` already loads with role-aware redirects.
- Existing admin analytics pages:
  - `/admin/analytics`
  - `/admin/governance-reports`
- Missing before this implementation:
  - `/admin/classification` (not found)
  - manager benchmarking page
  - supervisor self-performance page
- Existing API behavior (validated in runtime checks):
  - Admin: KPI and governance leaderboard APIs accessible.
  - Manager: admin governance APIs blocked (`403`), manager KPI APIs accessible.
  - Supervisor/Parent: KPI admin endpoints blocked by role.

## Baseline Feature Inventory (Step 1)
- KPI service exists in `kpi_service.py` with real DB-driven formulas and data quality metadata.
- Governance leaderboard exists in `governance_kpi_service.py` but no full classification module pages.
- Attendance history supports governorate and name filtering (`/api/attendance/history-summary` and `/attendance/history`).
- Sidebar had no dedicated classification navigation for admin/manager/supervisor.

## Role-Based IA (Implemented)
### Admin
- Dashboard: `/dashboard`
- KPI dashboard: `/kpi/dashboard`
- Classification & benchmarking: `/admin/classification`
- Governance reports: `/admin/governance-reports`
- Analytics drilldowns and other admin operations remain unchanged

### Manager
- Dashboard: `/dashboard`
- KPI dashboard: `/kpi/dashboard`
- Benchmarking summary (anonymized peers): `/manager/benchmarking`

### Supervisor
- Dashboard: `/dashboard` or `/supervisor/dashboard`
- Self-performance summary: `/supervisor/performance`

### Parent
- Existing parent pages unchanged
- Optional quality band API added (no leaderboard exposure)

## UX System Decisions
- Arabic-first UI labels for all newly added pages.
- Shared interaction pattern:
  - Period filter (start/end)
  - Entity tab selection (admin classification)
  - KPI explanation block (colors/trend/coverage meaning)
  - Data states: loading, no data, error
- Detail modal includes:
  - indicator values
  - trend chart
  - action guidance

## Navigation Updates
- Sidebar additions:
  - Admin: `التصنيف والمقارنات` -> `/admin/classification`
  - Manager: `المقارنة المعيارية` -> `/manager/benchmarking`
  - Supervisor: `أدائي المهني` -> `/supervisor/performance`
- KPI dashboard admin shortcut button to `/admin/classification`.

## Files Added/Updated for IA/UX
- `templates/admin/classification.html`
- `templates/manager/benchmarking.html`
- `templates/supervisor/performance.html`
- `templates/components/sidebar.html`
- `templates/kpi/dashboard.html`
- `frontend.py`
