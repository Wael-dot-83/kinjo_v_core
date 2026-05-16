# Classification & Benchmarking Spec

## Scope
This module provides production APIs and pages for:
- Kindergarten vs kindergarten comparison
- Manager vs manager comparison
- Supervisor vs supervisor comparison
- Manager-safe anonymized benchmarking
- Supervisor self-only performance view

## Data Sources (Real Tables)
- `kindergartens`
- `classes`
- `enrollment_applications`
- `attendance_logs`
- `daily_reports`
- `operating_calendar`
- `users`
- `supervisor_assignments`
- KPI composite inputs from `kpi_service.py` bundle logic (attendance, incidents, ratio compliance, checklist/training/satisfaction, etc.)

## KPIs and Formulas

## Kindergarten Final Score
- Source: `KPIService.compute_kpi_bundle(...).governance_score`
- Coverage: average of KPI quality coverage fields from bundle quality metadata.
- Sample threshold: expected child-days (`_count_expected_child_days`) must be >= `min_sample_days`.
- Insufficient data rules:
  - expected child-days below threshold
  - coverage below 40%

## Manager Final Score
- Weighted blend:
  - 60% kindergarten final score
  - 20% manager approval timeliness rate (approved within 24 hours)
  - 20% review quality rate (inverse of rejected/returned ratio)
- Additional sufficiency rules:
  - expected reviewed report volume >= `min_sample_days`
  - manager process coverage >= 40%

## Supervisor Final Score
- Weighted blend:
  - 40% attendance marking completeness (attendance logs / expected class child-days)
  - 40% report submission completeness (submitted reports / expected class child-days)
  - 20% report timeliness (submitted on or before report date)
- Sufficiency rules:
  - expected class child-days >= `min_sample_days`
  - operational coverage >= 40%

## Peer Group Fairness Rules
- Ranking is done per `peer_group_key`.
- `peer_group_key` combines:
  - selected geography level (network/country/governorate/city/area/kindergarten)
  - selected size mode (`CAPACITY`, `ENROLLMENT`, `CLASS_COUNT`)
  - computed size band (`SMALL`, `MEDIUM`, `LARGE`)
- Ranking exclusions:
  - entities with insufficient data
  - entities with null final score

## Bands and Thresholds
- Green: `80-100`
- Amber: `60-79.99`
- Red: `0-59.99`

## Trend
- Delta is current score minus previous period score with same duration.
- Direction:
  - `صاعد` if delta >= +1
  - `هابط` if delta <= -1
  - `مستقر` otherwise

## Country Segmentation
- Current schema does not guarantee a persisted `country` column.
- Implemented minimal safe support:
  - if DB has `country`, filters use it directly
  - otherwise fallback country is `الأردن`
  - non-fallback country filters return empty scope

## Privacy and RBAC
- Admin endpoints expose full identities:
  - `/api/admin/classification/kindergartens`
  - `/api/admin/classification/managers`
  - `/api/admin/classification/supervisors`
  - `/api/admin/classification/detail`
- Manager endpoint is anonymized:
  - `/api/manager/benchmarking/summary`
  - peers returned as `peer_code` with no real names
- Supervisor endpoint is self-only:
  - `/api/supervisor/performance/summary`
- Parent endpoint (optional quality label):
  - `/api/parent/kindergarten/quality-band`

## Cache Strategy
- KPI bundles used by classification are cached via `dashboard_cache`.
- Cache key pattern:
  - `classification:bundle:{kindergarten_id}:{period_start}:{period_end}`
- Admin cache utilities:
  - `POST /api/admin/classification/cache/warm`
  - `POST /api/admin/classification/cache/invalidate`

## API Contracts (New)
- `GET /api/admin/classification/filters`
- `GET /api/admin/classification/kindergartens`
- `GET /api/admin/classification/managers`
- `GET /api/admin/classification/supervisors`
- `GET /api/admin/classification/detail`
- `POST /api/admin/classification/cache/warm`
- `POST /api/admin/classification/cache/invalidate`
- `GET /api/manager/benchmarking/summary`
- `GET /api/supervisor/performance/summary`
- `GET /api/parent/kindergarten/quality-band`

## Notes
- No placeholder/fake KPI values were added.
- Missing/low-quality data is explicitly surfaced as insufficient data in responses and UI.
