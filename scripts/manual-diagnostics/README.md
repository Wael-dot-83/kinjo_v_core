# scripts/manual-diagnostics/

Manually-run diagnostic, audit, and data-population scripts.

**These files are NOT part of the automated test suite.**
`pytest.ini` sets `testpaths = tests`, so pytest never collects this directory.
Files that were formerly named `test_*.py` at the project root have been renamed
to `diagnostic_*.py` here for clarity.

---

## Categories

### `diagnostic_*.py` — Stale / manual integration probes

Formerly `test_*.py` at the project root. These scripts hit the **live server**
or **production database** directly. They are NOT compatible with the automated
test fixtures (SQLite in-memory, `TestClient`).

| File | Notes |
|---|---|
| `diagnostic_api.py` | Uses wrong `/api` prefix — update before running |
| `diagnostic_integration.py` | Uses wrong `/api` prefix — update before running |
| `diagnostic_bulk_operations.py` | Hits live server via `requests` — server must be running |
| `diagnostic_cache_invalidation.py` | Hits live server via `requests` — server must be running |
| `diagnostic_services_management.py` | Hits live server via `requests` — server must be running |
| `diagnostic_staff_management.py` | Hits live server via `requests` — server must be running |
| `diagnostic_tasks_api.py` | Uses `requests` directly, no TestClient |
| `diagnostic_advanced_analytics_cache.py` | Hits production DB directly |
| `diagnostic_advanced_analytics_cache_multi.py` | Hits production DB directly |
| `diagnostic_analytics_plugins.py` | Hits production DB directly |
| `diagnostic_api_analytics_endpoints.py` | Uses placeholder token |
| `diagnostic_app.py` | Hits production DB directly |
| `diagnostic_connection.py` | Hits production DB directly |
| `diagnostic_db_schema.py` | Hits production DB directly |
| `diagnostic_simple.py` | Hits production DB directly |
| `diagnostic_api_advanced_cache.py` | Manual cache test |

### `audit_*.py` — Audit utilities

| File | Purpose |
|---|---|
| `audit_attendance.py` | Validate attendance data integrity |
| `audit_kpi.py` | Validate KPI calculations |
| `audit_safety.py` | Validate safety/incident data |
| `audit_translations.py` | Check missing i18n translation keys |

### `check_*.py` — Database / startup checks

| File | Purpose |
|---|---|
| `check_column.py` | Verify specific column exists in DB |
| `check_db.py` | Verify DB connection and schema basics |
| `check_startup.py` | Verify app startup health |

### `diag_*.py` — Diagnostics

| File | Purpose |
|---|---|
| `diag_compare.py` | Compare two data sets or responses |
| `diag_excel.py` | Inspect Excel import file structure |

### `manual_*.py` — Manual test procedures

| File | Purpose |
|---|---|
| `manual_anomaly_test.py` | Manually trigger anomaly-detection logic |
| `manual_migration.py` | Run/test a migration manually |

### Other scripts

| File | Purpose |
|---|---|
| `quick_test.py` | Ad-hoc connectivity check |
| `integration_tests.py` | Stale integration suite (predates `tests/` directory) |
| `inspect_dataset.py` | Inspect a data import file |
| `populate_kpi_data.py` | Seed KPI demo data into DB |
| `populate_test_data.py` | Seed general demo data into DB |

---

## Running a script

1. Activate the venv:
   ```powershell
   .\.venv\Scripts\Activate.ps1
   ```
2. Ensure `DATABASE_URL` is set in `.env` (or the env is loaded):
   ```powershell
   Get-Content .env | ForEach-Object { if ($_ -match '^([^#=]+)=(.*)$') { [System.Environment]::SetEnvironmentVariable($Matches[1].Trim(), $Matches[2].Trim()) } }
   ```
3. Run from the **project root** (so imports resolve correctly):
   ```powershell
   python scripts/manual-diagnostics/<script_name>.py
   ```

> **Warning**: Scripts that hit the production DB will read/write live data.
> Scripts that use `requests` require the server to be running on `localhost:8000`.
