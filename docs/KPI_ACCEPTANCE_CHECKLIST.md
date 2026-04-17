# KPI Acceptance Checklist

## A) KPI Plan Document
- [x] Added: `docs/KPI_ENHANCEMENT_PLAN.md`

## B) Code Deliverables
- [x] KPI formulas updated to DB-driven logic in `kpi_service.py`
- [x] Admin filters extended (`governorate/city/area`, dimension support)
- [x] Manager scope preserved and hardened
- [x] Dashboard UI updated with new filters + no-data/coverage handling
- [x] Migration added for checklist KPI source table
- [x] Seed data enriched for KPI realism
- [x] Tests added/updated

## C) API Evidence

### 1. Filters Endpoint
- Endpoint: `GET /api/kpi/filters?locale=en`
- Evidence keys:
  - `kindergartens`
  - `governorates`
  - `cities`
  - `areas`
  - `dimension_types`
- Sample excerpt:
```json
{
  "dimension_types": [
    {"id": 1, "name": "NETWORK"},
    {"id": 2, "name": "GOVERNORATE"},
    {"id": 3, "name": "CITY"}
  ],
  "cities": [{"id": 1, "name": "Amman"}]
}
```

### 2. Dashboard Endpoint
- Endpoint: `GET /api/kpi/dashboard-data`
- Added query params:
  - `city`
  - `area`
  - `dimension_type`
  - `dimension_id`
- Sample excerpt showing quality metadata:
```json
{
  "overall_gcei": {
    "value": 84.0,
    "unit": "%",
    "has_data": false,
    "data_coverage": 0.0,
    "no_data_reason": "Missing active enrollment periods or operating calendar data"
  },
  "attendance_rate": {
    "value": 0.0,
    "has_data": false,
    "data_coverage": 0.0,
    "no_data_reason": "Missing active enrollment periods or operating calendar data"
  }
}
```

### 3. Backfill Endpoint
- Endpoint: `POST /api/kpi/admin/backfill-governance`
- Role: `ADMIN` only
- Behavior:
  - Backfills ratio compliance cache for period
  - Idempotent create/update of `governance_scores`

## D) UI Evidence (Admin Page)
- Updated filter controls (DOM IDs):
  - `#governorateSelect`
  - `#citySelect`
  - `#areaSelect`
  - `#kindergartenSelect`
  - `#granularitySelect`
- Updated KPI rendering for quality/no-data:
  - Uses card metadata `has_data`, `data_coverage`, `no_data_reason`
  - Hero and metric cards show no-data labels and coverage tooltips

## E) DB/Migration Evidence
- New model: `DailyChecklist` in `models.py`
- New enum: `DailyChecklistStatus`
- Migration: `alembic/versions/20260213_daily_checklists_kpi.py`
  - table `daily_checklists`
  - indexes:
    - `ix_daily_checklists_kindergarten_date`
    - `ix_daily_checklists_status`
  - unique key:
    - `uq_daily_checklist_kindergarten_date_type`

## F) Test Evidence
- Executed:
  - `python -m pytest -q tests/test_kpi_service.py tests/test_kpi_dashboard.py tests/test_attendance_summary.py tests/test_frontend_integration.py`
- Result:
  - `46 passed`
- Added tests include:
  - Survey-driven parent satisfaction scoring
  - Checklist compliance from persisted `daily_checklists`
  - Admin city filter behavior
  - Manager city-dimension scope denial
  - Unsupported KPI `dimension_type` rejection
  - Manager long-range dashboard request (granularity fallback safety)
  - KPI quality-metadata wiring (`overall_gcei` and `capacity_utilization_rate`)

## G) Live Smoke Evidence (2026-02-12)
- Environment: `http://127.0.0.1:8000` (local server)
- Auth:
  - Admin login: `200`
  - Manager login: `200`
- KPI API checks:
  - `GET /api/kpi/dashboard-data?dimension_type=CLASS&dimension_id=1` -> `400`
    - detail: `Invalid dimension_type. Allowed: NETWORK, GOVERNORATE, CITY, AREA, KINDERGARTEN`
  - `GET /api/kpi/manager/dashboard?period_start=2025-01-01&period_end=2025-12-31` -> `200`
    - `kindergarten_id=1`
    - `attendance_trend` points: `53` (weekly fallback, no daily-limit failure)
  - `GET /api/kpi/filters?locale=en` -> `200`
    - `dimension_types`: `NETWORK, GOVERNORATE, CITY, AREA, KINDERGARTEN`
    - non-empty `cities` and `areas` lists
- Attendance history checks (original admin filter requirement):
  - `GET /api/attendance/history-summary` with `governorate`, `kindergarten_name`, and `child_name` -> `200`
  - Response `meta.scope.filters` echoes all three filters
  - `meta.scope.mode`: `filtered_kindergartens`

## H) Known Limitations
- Regulatory score currently reflects license validity only; inspection scoring is not yet modeled.
