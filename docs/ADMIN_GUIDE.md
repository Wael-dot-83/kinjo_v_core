# KinJo Admin Module Guide

## Purpose and audience

This guide is the operating and engineering handbook for the KinJo Admin module. It covers the browser interface, administrator workflows, backend composition, service boundaries, API integration, security controls, validation, and deployment operations. It is intended for administrators, support engineers, backend/frontend developers, security reviewers, and release operators.

The generated [Admin API Reference](ADMIN_API_REFERENCE.md) is the field-level companion to this guide. It inventories every registered Admin API operation directly from FastAPI's OpenAPI schema, including parameters, request models, response models, and compatibility routes.

## Module map

The Admin module is a server-rendered FastAPI/Jinja application with shared JavaScript infrastructure and JSON APIs.

| Layer | Primary files | Responsibility |
|---|---|---|
| Application composition | `main.py` | Middleware order, static mount, router registration, health and platform services |
| Core Admin API | `admin_endpoints.py` | Users, messaging, dashboard, safety, imports, governance, backups, alerts, profile, and operational endpoints |
| Security and audit helpers | `admin_security.py`, `audit_service.py`, `middleware/csrf.py`, `middleware/auth.py` | Role gates, correlation IDs, CSRF enforcement, audit redaction and export |
| Reporting API | `admin_reports_api.py`, `api/agency_reports_api.py` | Decision-support, incident, geographic, compliance, agency, and export reports |
| Analytics | `admin_advanced_analytics_endpoints.py`, `analytics_service.py` | Drilldowns, predictions, action queue, data quality, and export jobs |
| Specialist Admin APIs | `heatmap/backend/admin_router.py`, `classification_service.py`, `kpi_service.py`, `routers/admin_impersonation.py` | Heat map, classification, KPI backfill, and controlled impersonation |
| Frontend routes | `scripts/compat/frontend_orig.py`, `frontend.py`, `frontend_agency_reports.py`, `charts_api.py` | Authenticated HTML page rendering and compatibility pages |
| Templates and assets | `templates/admin*`, `static/js/admin_*`, `static/css/admin_*` | UI shell, page behavior, localization, charts, and Admin design system |

## Access and session model

1. Sign in through the platform login flow. The server accepts the configured KinJo bearer/session token mechanism.
2. Navigate to `/admin/dashboard`. Frontend Admin routes require an authenticated Admin user; a small documented subset of data-management APIs also accepts a Manager.
3. The canonical Admin shell loads `auth.js` before `kinjo-api.js` and page scripts. `auth.js` installs the authenticated fetch wrapper and applies the CSRF header to unsafe browser requests.
4. Every response receives `X-Correlation-ID`. Supply the same header when escalating an incident so browser, API, and server logs can be correlated.
5. Use the profile menu to sign out. Do not share sessions or leave an impersonation session active.

### Authorization boundaries

- Admin-only is the default for `/api/admin/**`.
- Manager access is intentionally limited to scoped user listing/creation/read/update where `require_admin_or_manager` is declared. Network-wide imports, observability, charts, and reporting remain Admin-only. Scope enforcement remains server-side; hiding a UI control is never an authorization control.
- Self-service `POST /api/admin/password-reset-request` and `POST /api/admin/password-reset-confirm` are public, rate-limited recovery operations. They return non-enumerating responses; reset tokens are returned only in the development environment.
- Legacy chart paths under `/admin/charts/**` and legacy audit-log aliases remain registered for compatibility. New integrations must use `/api/admin/**`.
- Impersonation accepts only an authenticated Admin identity, records start/end events, and must never trust a client-supplied administrator ID.

## Frontend architecture

### Shared shell

All Admin templates extend `templates/admin_base.html`. The shell provides:

- language and RTL/LTR document state;
- responsive sidebar and top navigation;
- Bootstrap, Chart.js, SweetAlert2, and Odometer from self-hosted assets;
- bearer/session handling, CSRF-aware `fetch`, and the global `api` client;
- shared Admin components and Arabic/English localization;
- a consistent content landmark, loading/error patterns, and profile controls.

`templates/admin_base_premium.html` is a compatibility wrapper around the canonical shell. New pages must extend `admin_base.html`, place page CSS in `extra_head`, page content in `content`, and deferred scripts in `extra_scripts`.

### Page catalog

| Area | Pages | Main interaction |
|---|---|---|
| Home and operations | `/admin/dashboard`, `/api/admin/health` API, `/admin/observability`, `/admin/alerts` | KPIs, recent activity, critical cases, service health, alert acknowledgement |
| Users and identity | `/admin/users`, `/admin/users/create`, `/admin/users/{id}/edit`, `/admin/users/import` | Search/filter, create/edit/delete, bulk status/delete/create, CSV import/export, password reset, MFA status/bypass |
| Kindergartens | `/admin/kindergartens`, `/admin/kindergartens/new`, `/admin/kindergartens/{id}`, `/admin/kindergartens/{id}/edit`, `/admin/kg-overview` | CRUD, manager assignment, freeze/activate, overview and audit history |
| Data imports | `/admin/import-kindergartens`, `/admin/imported-kindergartens`, `/admin/import-logs` | Upload, validate, review duplicates/errors, inspect import history |
| Messaging | `/admin/messages`, `/admin/messages/compose`, `/admin/contact-messages` | Audience preview, compose/send, list messages, resolve contact requests |
| Analytics | `/admin/analytics`, `/admin/analytics/dashboard`, `/admin/analytics/reports`, `/admin/analytics/charts`, `/admin/analytics/drilldown/{type}/{id}`, `/admin/analytics/daily-reports`, `/admin/daily-reports-organization` | Filtering, drilldown, chart rendering, report building, daily-report oversight |
| Reports | `/admin/reports/incidents`, `/admin/reports/incidents/generate`, `/admin/reports/incidents/{id}`, `/admin/agency-reports/**` | Generate, view, export, and investigate operational/agency reports |
| Governance and safety | `/admin/governance-reports`, `/admin/governance/reminders`, `/admin/kpi`, `/admin/classification`, `/admin/safety-analytics`, `/admin/heatmap` | KPI trends, reminders, classifications, safeguarding analytics, geographic intelligence |
| Security and support | `/admin/audit-logs`, `/admin/impersonate`, `/admin/profile`, `/admin/settings`, `/admin/help` | Audit/export, controlled impersonation, account maintenance, preferences, help |

### Interaction conventions

- Filters update explicit query parameters and reset pagination to page 1.
- List views display bounded pages and server-provided totals; they must not infer a total from the current page length.
- Destructive actions require an explicit confirmation and use the shared API helper.
- UI text and API-derived strings inserted into HTML must be escaped. Prefer DOM `textContent` for untrusted values.
- Empty, loading, error, and partial-data states must remain meaningful in both Arabic and English.
- A navigation target must map to a registered frontend route. A page API target must map to a registered backend route.

## Administrator workflows

### Manage a user

1. Open **Users**, search or filter the server-side list, then open the target record.
2. Review the user's role and organizational scope before editing. Manager operations are restricted to their permitted scope.
3. Save changes through `PUT /api/admin/users/{user_id}`. Validation conflicts return 4xx responses and do not partially update the record.
4. Use the dedicated password-reset or MFA-bypass operation only after verifying the support case. MFA bypass requires an administrative password/reason and creates a sensitive audit event.
5. For bulk actions, preview the selected IDs, confirm the action, and review the per-row error list returned by the API.

### Import users or kindergartens

1. Download/use the documented column format from the import page.
2. Upload CSV/Excel through the page; browser writes flow through the CSRF-aware request layer.
3. Review created, skipped-duplicate, and rejected rows. Download the error report when present.
4. Open **Import Logs** to verify the persisted outcome. Correct source data before retrying; do not edit database rows manually.

### Operate a kindergarten

1. Locate the record in **Kindergartens** or **KG Overview**.
2. Create/update names, geography, capacity, and manager assignments using the dedicated form.
3. Freeze instead of deleting when the organization must remain historically referential. Supply a reason.
4. Activate only after the underlying issue is resolved. Confirm the audit history on the detail page.

### Send an administrative message

1. Open **Compose Message** and select the audience filters.
2. Run recipient preview and verify the returned count/sample.
3. Enter localized subject/body content, then send. The server recalculates recipients and records the result; the preview is not an authorization grant.
4. Confirm delivery state in the message list and investigate failures with the correlation ID/logs.

### Generate and export a report

1. Select the reporting scope and geography. Child-level and kindergarten-level drilldowns require the corresponding identifiers.
2. Review data-quality/compliance context before interpreting risk ranks or classifications.
3. Generate an incident or custom report. Long-running exports return a job identifier; poll status through the documented endpoint.
4. Download CSV/JSON/PDF as offered. CSV exports neutralize spreadsheet formulas; do not remove this protection.
5. Failed jobs link to the registered Audit Logs page for operational investigation.

### Acknowledge an alert or send a governance reminder

1. Filter to the relevant entity and severity/period.
2. Inspect the supporting data before acknowledgement.
3. Acknowledge or send the reminder through the unsafe-method API; the action is CSRF-protected and audited.
4. Refresh the list and confirm the persisted state rather than relying only on a toast message.

### Impersonate a user

1. Use impersonation only for an approved support/debugging case and record a specific reason.
2. Select the target account; the server rejects Admin targets and unauthorized callers.
3. Perform only the approved diagnostic workflow. The UI must clearly indicate impersonation state.
4. Exit impersonation immediately. Confirm both start and end events in the audit log.

### Backup operations

Backup create/list/info/validate/restore/delete/cleanup endpoints are restricted to Admins. Validate a backup before restore, use an approved maintenance window, and retain an external backup. Restore and delete are production-impacting actions; follow the deployment runbook and database change controls rather than treating them as routine UI actions.

## Backend request lifecycle

1. `main.py` receives the request through security, authentication, correlation, observability, and CSRF middleware.
2. The mounted router resolves the canonical route. FastAPI/Pydantic validates path, query, form, file, and JSON input.
3. A dependency loads the current user and enforces Admin or the explicitly scoped Admin/Manager policy.
4. The endpoint delegates domain work to a service or a focused query helper and uses the request-scoped database session.
5. State-changing operations commit atomically. Operations covered by the audit policy emit a redacted event; during impersonation every new audit row is attributed to both the target identity and originating Admin.
6. Exceptions are translated into an appropriate 4xx/5xx response with a correlation ID; secrets and raw stack traces are not returned to the browser.

### Service boundaries

- `admin_endpoints.py` is the orchestration boundary, not a place to duplicate domain algorithms.
- `analytics_service.py`, `governance_*`, `classification_service.py`, `backup_manager.py`, `export_service.py`, and import services own their corresponding business behavior.
- `audit_service.py` owns audit querying/export; `admin_security.py` owns audit emission, redaction, standard API errors, and role helpers.
- `dashboard_api.py` manages user dashboard customization outside the `/api/admin` namespace; the Admin dashboard summary itself is served by `admin_endpoints.py`.
- Background jobs use the configured task queue and expose status rather than blocking an HTTP worker.

## API integration

Use the generated [Admin API Reference](ADMIN_API_REFERENCE.md) for the complete operation inventory and exact OpenAPI model names.

### Request example

```http
PATCH /api/admin/alerts/123/acknowledge HTTP/1.1
Authorization: Bearer <token>
Cookie: kinjo_csrf_token=<csrf-token>
X-CSRF-Token: <csrf-token>
X-Correlation-ID: <client-generated-uuid>
Content-Type: application/json
```

### Response and error handling

- Treat only documented 2xx codes as success.
- `400` indicates invalid business input or CSRF validation; `401` missing/expired authentication; `403` insufficient role/scope; `404` absent resource; `409` state/uniqueness conflict; `422` structural validation; `429` rate limit; `5xx` an operational fault.
- Display a safe localized message to users and retain `X-Correlation-ID` for support.
- Never retry unsafe operations blindly. Retry only when the operation is documented as idempotent or after reading back the persisted state.

### Compatibility policy

- New calls use `/api/admin/**`.
- `/admin/charts/**` remains a documented legacy surface; `/api/admin/charts/**` is canonical.
- `/api/audit-logs` and `/api/admin/audit-logs` share the same implementation for compatibility. Admin authorization is enforced inside that implementation.
- `/api/kpi/admin/backfill-governance` is a legacy alias; `/api/admin/kpi/backfill-governance` is canonical.
- Compatibility aliases should be hidden from OpenAPI where appropriate, delegate to one canonical implementation, and have regression tests.

## Security controls

### CSRF

All browser `POST`, `PUT`, `PATCH`, and `DELETE` calls must use `api.*`, `fetchWithAuth`, or the globally wrapped `fetch` loaded by `admin_base.html`. The CSRF cookie/header values must match. Do not add an unsafe native form submission or capture the unwrapped browser fetch function.

### IDOR and scope protection

Every endpoint that accepts a user, kindergarten, child, report, alert, backup, or job identifier must authorize the current caller against that object. Frontend filtering and opaque identifiers are defense in depth, not authorization. Return 404 when revealing existence would disclose out-of-scope data.

### Audit and sensitive data

Sensitive fields—including passwords, tokens, keys, secrets, MFA values, and administrative passwords—are redacted before audit serialization. Security-sensitive actions use explicit audit actions and sensitivity levels. CSV exports escape formula prefixes to prevent spreadsheet execution.

### Browser content safety

Keep third-party assets self-hosted or covered by the production Content Security Policy. Escape API-derived values before `innerHTML`; use `textContent` by default. Do not introduce inline secrets, debug tokens, or development-only endpoints into templates.

## Operations and deployment readiness

### Pre-deployment checklist

1. Review configuration using `DEPLOYMENT_GUIDE.md`, `RUNBOOK.md`, and the environment's secret manager. Production must not use development token-return behavior or default credentials.
2. Apply and verify Alembic migrations against a backup. Confirm only one migration head.
3. Confirm database, cache/task queue, email, file storage, and monitoring dependencies required by enabled features.
4. Build an immutable artifact and serve the checked-in static assets. Verify `/static/**` references before release.
5. Run compile, bug-class lint, Admin tests, route-duplicate, link/API/global/CSRF, and asset checks.
6. Smoke test login, dashboard, a read-only list, one approved write, audit appearance, and logout in the deployment environment.
7. Validate public `/health`, authenticated `/api/health`, and `/api/admin/health` for the detailed Admin view.
8. Confirm log ingestion, metrics, alert routing, backup retention, restore procedure, and rollback owner.

### Required verification commands

Use the active project interpreter for the target environment:

```powershell
python -m py_compile main.py admin_endpoints.py admin_security.py audit_service.py dashboard_api.py admin_reports_api.py admin_advanced_analytics_endpoints.py
python -m ruff check main.py admin_endpoints.py admin_security.py audit_service.py dashboard_api.py admin_reports_api.py admin_advanced_analytics_endpoints.py analytics_service.py tests/test_admin_contract.py
python -m pytest -q tests/test_admin_contract.py tests/test_admin_sidebar_navigation.py tests/test_admin_security.py
python scripts/manual-diagnostics/check_routes.py
python scripts/manual-diagnostics/generate_admin_api_reference.py
```

Run the complete Admin-relevant suite before release, not only the three fast contract/security files.

### Staging smoke gate

The smoke harness performs controlled writes and soft-deletes its uniquely named test user. Run it only against an approved staging environment. The rate-limit probe is disabled by default because it intentionally exhausts the login limit for the source address.

```powershell
$env:SMOKE_BASE_URL = "https://staging.example"
$env:SMOKE_ADMIN_USERNAME = "admin"
$env:SMOKE_ADMIN_PASSWORD = "<from-secret-store>"
$env:SMOKE_ALLOW_MUTATIONS = "true"
$env:SMOKE_EXPECTED_HOST = "staging.example"
python scripts/manual-diagnostics/staging_smoke_test.py --output smoke-report.json
```

Enable `SMOKE_RATELIMIT_PROBE=true` only during an isolated validation window. Impersonation is mandatory: supply `SMOKE_IMPERSONATE_USER_ID` when staging does not contain a discoverable active Manager.

## Troubleshooting

| Symptom | Checks |
|---|---|
| Page redirects or returns 401 | Token/session expiry, cookie domain/secure flags, clock skew, authentication middleware logs |
| 403 on an Admin action | Current role, Manager scope, object ownership/scope, impersonation state |
| 400 on a write | Matching CSRF cookie/header, content type, business validation message |
| 422 response | OpenAPI parameter/body schema, missing required field, enum/date/ID format |
| Dashboard card is empty | Network response, filter range, data-quality reasons, background service/cache health |
| Export stays pending | Worker/queue health, job status endpoint, storage permissions, audit logs |
| Static/JS error | Asset existence, script order in `admin_base.html`, CSP, console correlation with request logs |
| Duplicate or shadowed behavior | Registered `(method, path)` inventory and compatibility delegation tests |

## Change checklist

For every new Admin capability:

- register one canonical route and document any compatibility alias;
- declare the narrowest role/scope dependency;
- use typed validation and bounded pagination;
- add CSRF-safe frontend integration and escape output;
- create an audit event for security/data mutations;
- add success, authorization, validation, conflict, and edge-case tests;
- update this guide when workflows or architecture change;
- regenerate `docs/ADMIN_API_REFERENCE.md` when the OpenAPI surface changes;
- run the full Admin verification gate and an independent review.
