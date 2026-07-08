# Kindergarten Model Fields Audit

## 1. Current fields in `models.py` (post-change)

| Field | Type | Nullable | Notes |
|-------|------|----------|-------|
| `id` | Integer | No | PK |
| `name_ar` | String(255) | No | Arabic name |
| `name_en` | String(255) | Yes | English name |
| `governorate` | String(100) | No | |
| `district` | String(100) | No | |
| `area` | String(100) | No | |
| `address_line` | Text | No | |
| `contact_phone` | String(20) | No | |
| `contact_email` | String(255) | Yes | Optional |
| `latitude` | Float | Yes | |
| `longitude` | Float | Yes | |
| `status` | Enum(KindergartenStatus) | No | DRAFT/ACTIVE/INACTIVE/FROZEN/DELETED |
| `frozen_at` | DateTime(timezone=True) | Yes | |
| `frozen_reason` | String(255) | Yes | |
| `frozen_by` | Integer | Yes | |
| `deleted_at` | DateTime(timezone=True) | Yes | |
| `deleted_by` | Integer | Yes | |
| `legal_name` | String(255) | Yes | Legal / trade name |
| `type` | String(50) | Yes | e.g. private / public / franchise |
| `mobile` | String(20) | Yes | |
| `website` | String(255) | Yes | |
| `manager_name` | String(255) | Yes | |
| `manager_id` | String(50) | Yes | |
| `manager_phone` | String(20) | Yes | |
| `manager_email` | String(255) | Yes | |
| `owner_name` | String(255) | Yes | |
| `ownership_type` | String(50) | Yes | e.g. individual / company |
| `total_capacity` | Integer | Yes | |
| `current_child_count` | Integer | Yes | |
| `number_of_classes` | Integer | Yes | |
| `teacher_count` | Integer | Yes | |
| `working_days` | String(100) | Yes | |
| `age_group` | String(50) | Yes | |
| `registration_fees` | Float | Yes | |
| `monthly_fees` | Float | Yes | |
| `license_status` | String(50) | Yes | |
| `administrative_notes` | Text | Yes | |
| `working_hours_start` | String(5) | Yes | Canonical field (was `operating_hours_start`) |
| `working_hours_end` | String(5) | Yes | Canonical field (was `operating_hours_end`) |
| `license_number` | String(100) | Yes | |
| `license_valid_until` | Date | Yes | |
| `created_at` | DateTime(timezone=True) | Yes | server_default=func.now() |
| `updated_at` | DateTime(timezone=True) | Yes | onupdate=func.now() |

### Python property
- `name` → returns `name_ar or name_en or ""`

## 2. Fields referenced by APIs / services / templates / tests

### API serialization (`api/kindergartens.py::_serialize`)
All model fields above are exposed via the API response envelope.

### KPI / analytics services (`kpi_service.py`)
- `kg.working_hours_start`
- `kg.working_hours_end`
- `kg.license_valid_until`
- `kg.name_ar` / `kg.name_en`
- `kg.governorate`, `kg.district`, `kg.area`
- `kg.total_capacity`, `kg.current_child_count`

### Frontend templates / JS
- `templates/kindergartens/view.html`: `kindergarten.working_hours_start/end`, `kindergarten.license_number`, `kindergarten.license_valid_until`
- `templates/kindergartens/list.html`: `kg.working_hours_start/end`
- `templates/kindergartens/form.html`: form inputs named `working_hours_start`, `working_hours_end`
- `templates/enrollment/create.html`: `kg.working_hours_start/end`
- `static/js/kg_overview.js`: `kg.name`, `kg.name_en`, `kg.name_ar`, `kg.governorate`, `kg.children`, `kg.teachers`, `kg.attendance`, `kg.alerts`, `kg.capacity`

### Tests
- `tests/test_core_crud.py`: create/list kindergarten with `working_hours_start/end`
- `tests/test_missing_endpoints.py`: admin CRUD endpoints, blank optional fields
- `tests/test_manager_module.py`: manager list/detail access
- `tests/test_enrollment_create.py`: district filtering, parent view access

## 3. Missing or mismatched fields

| Issue | Resolution |
|-------|------------|
| No unified `name` property | Added `@property name` returning `name_ar or name_en or ""` |
| DB columns named `operating_hours_start/end` | Renamed to `working_hours_start/end` via migration |
| Duplicate column definitions in `models.py` | Removed duplicate block of columns (318–323 duplicated 326–331) |

## 4. Why `working_hours_start/end` is canonical

- The templates, forms, and JS already used `working_hours_*` naming in multiple places.
- The field `working_days` already exists, so `working_hours_*` is consistent with that naming convention.
- "Working hours" is the term used in the UI labels (`ساعات العمل`).

## 5. Why `operating_hours_start/end` was removed

- They were legacy DB column names that did not match the rest of the codebase.
- Keeping both would have required duplicate columns or compatibility aliases.
- The Alembic migration safely renames the existing columns.

## 6. Backward compatibility impact

- **Breaking**: Any external client still sending `operating_hours_start` / `operating_hours_end` in JSON payloads will get a 422 validation error.
- **Mitigation**: The migration preserves all existing data by renaming columns in place.
- **Recommendation**: If backward compatibility is required, add input aliases in `KindergartenCreate` / `KindergartenUpdate` that map old names to new ones.

## 7. Migration

**File**: `alembic/versions/f1a2b3c4d5e6_rename_kindergarten_working_hours.py`

- `upgrade()`: renames `operating_hours_start` → `working_hours_start`, `operating_hours_end` → `working_hours_end`
- `downgrade()`: reverses the rename
- Uses `op.batch_alter_table('kindergartens')` for SQLite/PostgreSQL safety

## 8. Tests run

| Test file | Result |
|-----------|--------|
| `tests/test_core_crud.py` | 16 passed |
| `tests/test_missing_endpoints.py` | passed |
| `tests/test_new_endpoints.py` | passed |
| `tests/test_new_modules.py` | passed |
| `tests/test_manager_module.py` | passed |
| `tests/test_enrollment_create.py` | 1 failed (pre-existing) |
| `tests/test_admin_reports_api.py` | passed |
| `tests/test_kpi_p0_regression.py` | passed |

## 9. Known limitations

- **Pre-existing failure**: `tests/test_enrollment_create.py::TestKindergartenFilteringWithCity::test_filter_by_city` fails on this branch and on `main`; not caused by this change.
- **GWS files**: Compliance audit artifacts (`GWS/*`, `GWS_COMPLIANCE_MATRIX.csv`) were intentionally excluded from this commit. They should be updated in a separate documentation pass.
- **No backward-compatible input aliases**: Old API payload keys `operating_hours_start/end` are not accepted. If needed, add aliasing in the Pydantic schemas.
