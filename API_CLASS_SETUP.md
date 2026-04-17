# Class Setup + Staffing Validation + DailyReport Workflow API

## Endpoints

### Create/Update Class

- `POST /api/classes`
- Payload: `{ name_ar, name_en, class_code, age_group, enrolled_children_count, capacity_total, min_age_months, max_age_months }`
- Validations: unique code, children count, age group, etc.

### Get Required Supervisors

- `GET /api/classes/{class_id}/required-supervisors`
- Returns: `{ required_supervisors: int }`

### Assign Supervisor

- `POST /api/supervisor/assign`
- Payload: `{ supervisor_id, class_id, start_date, is_primary, full_time_dedication }`
- Validations: age >= 20, dedication, count >= required

### Generate DailyReport Workflow

- `POST /api/classes/{class_id}/generate-dailyreport-workflow`
- Idempotent, logs audit

## Validation Errors

- Standard format: `{ detail: "message" }`

## Developer Notes

- Supervisor requirement logic: `validators.calculate_required_supervisors`
- All business rules enforced server-side
- Extendable via config or policy module
