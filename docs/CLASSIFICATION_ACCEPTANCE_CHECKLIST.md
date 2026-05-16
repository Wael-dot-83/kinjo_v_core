# Classification Acceptance Checklist

## 1) API Responses (Examples)

### Admin leaderboard
`GET /api/admin/classification/kindergartens`

Example shape:
- `{"period_start":"2026-01-01","period_end":"2026-01-31","rows":[{"entity_type":"KINDERGARTEN","entity_id":1,"display_name":"...","rank":1,"percentile":100.0,"final_score":78.5,"band_label":"كهرماني","coverage_pct":82.4,"insufficient_data":false}]}`

Expected keys:
- `period_start`
- `period_end`
- `rows[]` with:
  - `entity_type`
  - `entity_id`
  - `display_name`
  - `rank`
  - `percentile`
  - `final_score`
  - `band_label`
  - `coverage_pct`
  - `insufficient_data`

### Manager summary
`GET /api/manager/benchmarking/summary`

Example shape:
- `{"manager_id":2,"kindergarten_id":1,"final_score":74.2,"percentile":66.7,"band_label":"كهرماني","peer_group_size":6,"anonymized_peers":[{"peer_code":"ندّ 1","rank":1,"percentile":100.0,"band_label":"أخضر","final_score":88.3}]}`

Expected keys:
- `manager_id`
- `kindergarten_id`
- `final_score`
- `percentile`
- `band_label`
- `peer_group_size`
- `anonymized_peers[]`

### Supervisor self summary
`GET /api/supervisor/performance/summary`

Example shape:
- `{"supervisor_id":3,"final_score":70.0,"band_label":"كهرماني","coverage_pct":75.0,"sample_size":120,"aspects":{"اكتمال_الحضور":78.0,"اكتمال_التقارير":69.0,"الالتزام_بالوقت":62.0}}`

Expected keys:
- `supervisor_id`
- `final_score`
- `band_label`
- `coverage_pct`
- `sample_size`
- `aspects`

## 2) Key UI DOM IDs
- Admin page:
  - `classificationRoot`
  - `classificationTabs`
  - `classificationTableBody`
  - `classificationDetailModal`
  - `classificationTrendChart`
- Manager page:
  - `managerBenchmarkRoot`
  - `managerFinalScore`
  - `managerPeersTableBody`
- Supervisor page:
  - `supervisorPerformanceRoot`
  - `supervisorFinalScore`
  - `supervisorAspectsList`

## 3) RBAC Verification
- Admin endpoints reject non-admin.
- Manager summary rejects non-manager.
- Supervisor summary rejects non-supervisor.
- Parent quality endpoint rejects non-parent.

## 4) Data Quality / Insufficient Data
- Responses include:
  - `insufficient_data`
  - `insufficient_reason`
  - `coverage_pct`
- UI renders these states and explanatory text.

## 5) Arabic-Only UI (New Screens)
- New templates and status messages were written in Arabic text.
- Added gate test for Latin characters in newly added classification/benchmarking UI-facing strings.

## 6) Test Execution Evidence
- See test files:
  - `tests/test_classification_api.py`
  - `tests/test_arabic_ui_gate_classification.py`
- Executed command:
  - `python -m pytest -q tests/test_classification_api.py tests/test_arabic_ui_gate_classification.py`
- Result:
  - `9 passed`
