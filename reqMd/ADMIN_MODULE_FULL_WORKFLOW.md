# Admin Module — Full Description, Details, and Workflow

## 1) Scope and Purpose

The Admin Module in this project is the central operational and governance control plane for the KInJo platform.  
It is implemented primarily across:

- `main.py` (router composition, middleware/security baseline, global auth/session behavior)
- `admin_endpoints.py` (admin APIs and workflows)
- `admin_security.py` (standardized admin security contract: error model, correlation ID, audit helpers, authorization helpers, CSV/pagination/bulk guardrails)

This module provides secure administration for:

- User management (CRUD, export, bulk operations)
- Security operations (password reset flows, MFA bypass/status)
- Messaging at scale (targeting, preview, send, recipient analytics)
- Admin dashboard and KPIs
- Backup lifecycle management
- Governance KPI and reminder workflows
- Incident report generation/listing/export
- Kindergarten import flows (Excel + import logs)

---

## 2) Architecture and Composition

## 2.1 Router Wiring

From `main.py`:

- Admin router is mounted via:
  - `app.include_router(admin_router, prefix="/api", tags=["Admin"])`
- This means admin endpoints are accessible under `/api/...` according to each route path in `admin_endpoints.py`.

## 2.2 Security/Middleware Context Applied to Admin Routes

Admin endpoints run inside global app middleware stack in `main.py`, including:

- Trusted host filtering
- CORS policy constraints
- Request timeout middleware
- Security headers middleware
- CSRF protections:
  - origin/referer checks for state-changing cookie-auth requests
  - strict CSRF middleware integration
- Audit middleware for state changes
- JSON response sanitization middleware
- Correlation ID middleware (`CorrelationIdMiddleware` from `admin_security.py`)
- Rate limiting handlers (SlowAPI + configured policies)

This means every admin action inherits platform-level defenses in addition to endpoint-level checks.

---

## 3) Authorization Model

## 3.1 Core Role Gatekeepers (in `admin_endpoints.py`)

- `require_admin`:
  - Allows only `UserRole.ADMIN`
  - Raises forbidden if not admin
- `require_admin_or_manager`:
  - Allows `ADMIN` or `MANAGER`

## 3.2 Object-Level Access / IDOR Protection (in `admin_security.py`)

`can_admin_access_user(actor, target)` rules:

- Admin:
  - Can access non-admin users
  - Cannot manage other admin accounts (except self checks where applicable)
- Manager:
  - Limited to same kindergarten
  - Cannot manage admins/managers (except self in limited context)
- Others:
  - Self only

`validate_bulk_targets(...)` performs batch authorization filtering into:

- `allowed`
- `forbidden`
- `not_found`

This is used by bulk endpoints to enforce per-target authorization safely.

---

## 4) Error Contract and Observability

Defined in `admin_security.py`:

- Structured error codes (`ErrorCode` enum):
  - `UNAUTHENTICATED`, `FORBIDDEN`, `VALIDATION_ERROR`, `NOT_FOUND`, `CONFLICT`, `RATE_LIMITED`, `INTERNAL_ERROR`, `BAD_REQUEST`
- API exception wrapper: `APIError`
- Unified payload shape via `create_error_response(...)`
- Global handler: `api_error_handler(...)`
- Correlation ID support:
  - Request/response propagated via `X-Correlation-ID`
  - Included in structured error payload
- Request IP tracking through context var

This ensures traceable diagnostics and consistent client behavior.

---

## 5) Audit Logging and Data Safety

## 5.1 Audit Logging Utility

`log_audit_event(...)` in `admin_security.py` records:

- actor and target
- action code
- target IDs
- metadata
- sensitivity level
- request IP and correlation ID
- optional before/after diff

## 5.2 Diff and Redaction

- `compute_diff(before, after)` captures changed/added/removed fields.
- `redact_sensitive_data(...)` masks sensitive fields (passwords, tokens, secrets, keys).
- Large audit payloads are truncated with summary protection.

This supports forensic readiness while reducing data leakage risk in logs.

---

## 6) Rate Limiting and Guardrails

Admin endpoints are throttled (`@limiter.limit(...)`) with policy-backed limits from settings or defaults:

- Admin read/write limits
- Password reset limits
- Bulk create/update/delete limits
- CSV import limits

Bulk safeguards include:

- max operation sizes (`MAX_BULK_*`)
- confirmation token workflow for dangerous large ops
- dry-run preview support

---

## 7) Full API & Endpoint Description (Admin Module)

This section expands each endpoint with method, path, access, request model, behavior, and response intent.

### 7.0 Router Composition and Effective Prefixes

From `main.py`, admin-related route composition includes:

- `admin_endpoints.py` router mounted as: `app.include_router(admin_router, prefix="/api", tags=["Admin"])`
- `audit_service.py` router mounted as: `app.include_router(audit_service.router, prefix="/api", tags=["Audit"])`
- `dashboard_api.py` router already has internal prefix `/api/dashboard` and is mounted directly: `app.include_router(dashboard_router)`

So effective paths are:

- `admin_endpoints.py`: `/api/...`
- `audit_service.py`: `/api/audit-logs...`
- `dashboard_api.py`: `/api/dashboard/...`

### 7.1 User Management Endpoints

#### 7.1.1 List Users

- **Method/Path:** `GET /api/admin/users`
- **Access:** Admin or Manager (`require_admin_or_manager`)
- **Query Params:** `page`, `page_size`, `role`, `status`, `kindergarten_id`, `search`
- **Behavior:**
  - Enforced pagination bounds
  - Admin sees non-admin users (optionally by kindergarten)
  - Manager is restricted to own kindergarten
  - Optional role/status/search filtering
- **Response:**
  - `data[]` user summaries
  - `pagination` block
  - `correlation_id`

#### 7.1.2 Create User

- **Method/Path:** `POST /api/admin/users`
- **Access:** Admin or Manager
- **Body:** `UserCreateSchema`
- **Behavior:**
  - Manager cannot create Admin/Manager accounts
  - Manager cannot create outside own kindergarten
  - Admin cannot create Admin via this endpoint
  - Supervisor requires kindergarten
  - Manager assignment rules enforced
  - Username/email uniqueness checks
  - Optional parent-child creation flow
  - Optional profile fields + identity validation
  - Audit events: `USER_CREATED` (+ child creation audit if relevant)
- **Response:** created user profile fields + `correlation_id`

#### 7.1.3 Get User by ID

- **Method/Path:** `GET /api/admin/users/{user_id}`
- **Access:** Admin or Manager
- **Behavior:**
  - Not-found handling
  - IDOR protection via `can_admin_access_user`
  - Audit on denied access
- **Response:** full user details + `correlation_id`

#### 7.1.4 Update User

- **Method/Path:** `PUT /api/admin/users/{user_id}`
- **Access:** Admin or Manager
- **Body:** `UserUpdateSchema`
- **Behavior:**
  - IDOR protection
  - Manager assignment validation for target final state
  - Email uniqueness validation
  - Password/profile updates
  - Only Admin can alter role/status/kindergarten_id
  - Extra supervisor deactivation guard
  - Audit with before/after diff (`USER_UPDATED`)
- **Response:** updated user fields + `correlation_id`

#### 7.1.5 Delete User

- **Method/Path:** `DELETE /api/admin/users/{user_id}`
- **Access:** Admin only
- **Behavior:**
  - Not-found handling
  - Prevent self-delete
  - Prevent deleting admin accounts
  - Audit with before-state (`USER_DELETED`)
- **Response:** `204 No Content`

#### 7.1.6 Export Users

- **Method/Path:** `GET /api/admin/users/export`
- **Access:** Admin only
- **Query Params:** `format=csv|json`, `role`, `status`, `kindergarten_id`
- **Behavior:**
  - Exports filtered non-admin users
  - Audit action: `USER_EXPORT`
- **Response:** file download (`csv` or `json`)

### 7.2 Password Reset and MFA Endpoints

#### 7.2.1 Admin Reset User Password

- **Method/Path:** `POST /api/admin/users/{user_id}/admin-reset-password`
- **Access:** Admin only
- **Body:** `AdminPasswordResetSchema`
- **Behavior:**
  - Rejects admin-target resets
  - Verifies current admin password before reset
  - Audit success/failure actions
- **Response:** success message + target `user_id` + `correlation_id`

#### 7.2.2 Self-Service Reset Request

- **Method/Path:** `POST /api/admin/password-reset-request`
- **Access:** public-like (not admin restricted)
- **Body:** `PasswordResetRequestSchema`
- **Behavior:**
  - Enumeration-safe generic response
  - If user exists: issue token + send email + audit event
  - Dev mode may return token in response
- **Response:** generic success + `correlation_id`

#### 7.2.3 Confirm Password Reset

- **Method/Path:** `POST /api/admin/password-reset-confirm`
- **Access:** token-based flow
- **Body:** `PasswordResetConfirmSchema`
- **Behavior:**
  - Validates token
  - Resets password and marks token used
  - Audit action `PASSWORD_RESET_COMPLETED`
- **Response:** success + `correlation_id`

#### 7.2.4 Emergency MFA Bypass

- **Method/Path:** `POST /api/admin/users/{user_id}/mfa-bypass`
- **Access:** Admin only
- **Body:** `MFABypassSchema`
- **Behavior:**
  - Admin password re-verification
  - Clears user MFA secret/state forcing re-enrollment
  - High-sensitivity audit action
- **Response:** success message + `user_id` + `correlation_id`

#### 7.2.5 User MFA Status

- **Method/Path:** `GET /api/admin/users/{user_id}/mfa-status`
- **Access:** Admin only
- **Behavior:** return MFA flags and timestamps
- **Response:** MFA status payload + `correlation_id`

### 7.3 Bulk User Operations

#### 7.3.1 Bulk Status Update

- **Method/Path:** `POST /api/admin/users/bulk-status-update`
- **Access:** Admin only
- **Body:** `BulkStatusUpdateSchema`
- **Behavior:**
  - Empty/max-size validation
  - Confirmation token required for large batches
  - Dry-run mode supported
  - Per-target authorization using `validate_bulk_targets`
  - Manager activation rule conflict checks
  - Commit + audit (`BULK_STATUS_UPDATE`)
- **Response:** success/fail IDs, errors, forbidden/not-found IDs, `correlation_id`

#### 7.3.2 Bulk Delete

- **Method/Path:** `POST /api/admin/users/bulk-delete`
- **Access:** Admin only
- **Body:** `BulkDeleteSchema`
- **Behavior:**
  - Empty/max-size validation
  - Reject if any admin accounts in target set
  - Confirmation token always required for non-dry-run
  - Dry-run support
  - Authorized batch delete + audit (`BULK_USER_DELETE`)
- **Response:** deleted IDs, forbidden/not-found IDs, `correlation_id`

#### 7.3.3 Bulk Create

- **Method/Path:** `POST /api/admin/users/bulk-create`
- **Access:** Admin only
- **Body:** `BulkCreateSchema`
- **Behavior:**
  - Batch size limits
  - Manager assignment validation across batch
  - Duplicate username/email pre-checks
  - No admin role creation allowed
  - Dry-run support
  - Commit + audit (`BULK_USER_CREATE`)
- **Response:** per-row success/errors + counts + `correlation_id`

### 7.4 CSV User Import Endpoints

#### 7.4.1 Import Users CSV

- **Method/Path:** `POST /api/admin/users/import-csv`
- **Access:** Admin only
- **Input:** CSV file + optional `dry_run` query
- **Behavior:**
  - `.csv` extension check
  - UTF-8/BOM-safe decode
  - Header requirement checks
  - Per-row sanitization and validation
  - Role/duplicate/manager rules
  - Dry-run support
  - Commit + audit (`CSV_IMPORT`)
- **Response:** `total_rows`, `succeeded`, `failed`, `errors[]`, `created_ids`, `correlation_id`

#### 7.4.2 Download Import Error Report

- **Method/Path:** `GET /api/admin/users/import-csv/error-report`
- **Access:** Admin only
- **Query:** JSON-encoded `errors`
- **Behavior:** renders error rows into downloadable CSV
- **Response:** CSV stream

### 7.5 Admin Messaging Endpoints

#### 7.5.1 Recipient Discovery

- **Method/Path:** `GET /api/admin/message-recipients`
- **Access:** Admin only
- **Query:** roles, governorates, kindergarten_ids, search, page, page_size
- **Behavior:** resolves target IDs and returns paginated summaries
- **Response:** `items[]` + pagination meta

#### 7.5.2 Recipient Preview (GET)

- **Method/Path:** `GET /api/admin/message-recipients/preview`
- **Access:** Admin only
- **Query:** `mode` + optional filters
- **Behavior:**
  - Validates targeting mode semantics
  - Returns total_count, sample recipients, role/governorate/kindergarten breakdowns
  - Audit action `ADMIN_MESSAGE_PREVIEW`
- **Response:** `AdminRecipientPreviewResponse`

#### 7.5.3 Recipient Preview (POST)

- **Method/Path:** `POST /api/admin/messages/preview`
- **Access:** Admin only
- **Body:** `AdminMessagePreviewRequest`
- **Behavior:** payload-based preview equivalent with pagination
- **Response:** `AdminRecipientListResponse`

#### 7.5.4 Send Admin Message

- **Method/Path:** `POST /api/admin/messages`
- **Access:** Admin only
- **Body:** `AdminMessageCreate`
- **Behavior:**
  - CSRF double-submit validation
  - subject/body required + sanitized
  - target resolution and recipient cap enforcement
  - chunked `MessageRecipient` inserts
  - audit `ADMIN_MESSAGE_SENT`
  - notification queue attempt + warning path
- **Response:** `AdminMessageResponse` (id, timestamps, recipient_count, warnings)

#### 7.5.5 Governorate Options

- **Method/Path:** `GET /api/admin/options/governorates`
- **Access:** Admin only
- **Behavior:** returns active governorate list with Arabic/English labels
- **Response:** `GovernorateOptionsResponse`

#### 7.5.6 Kindergarten Options

- **Method/Path:** `GET /api/admin/options/kindergartens`
- **Access:** Admin only
- **Query:** governorate, status, search, page, page_size
- **Behavior:** filterable list for targeting UI
- **Response:** kindergarten list + pagination

### 7.6 Admin Dashboard Endpoint

#### 7.6.1 Admin Dashboard Aggregate

- **Method/Path:** `GET /api/admin/dashboard`
- **Access:** Admin only
- **Query:** `period_days` (1..90)
- **Behavior:**
  - cache lookup by day + period
  - optimized batch metric computation
  - alert synthesis (applications/incidents/license expiry)
  - audit action `ADMIN_DASHBOARD_VIEWED`
  - cache set on miss
- **Response:** `AdminDashboardResponse`

### 7.7 Performance Monitoring Endpoints

- `GET /api/performance/metrics`
- `GET /api/performance/requests`
- `GET /api/performance/database`
- `GET /api/performance/system`

**Access:** Admin only  
**Behavior:** pulls performance monitor reports/series, with guarded error handling.

### 7.8 Backup Management Endpoints

- `POST /api/backup/create`
- `GET /api/backup/list`
- `POST /api/backup/restore/{backup_name}`
- `DELETE /api/backup/{backup_name}`
- `GET /api/backup/info/{backup_name}`
- `POST /api/backup/cleanup`
- `POST /api/backup/validate/{backup_name}`

**Access:** Admin only  
**Key Behavior:**

- backup name sanitization against path traversal
- controlled restore behavior (API-safe restrictions)
- audit logging around create/restore/delete/cleanup

### 7.9 Governance Endpoints

- `GET /api/admin/governance/kpis`
- `GET /api/admin/governance/leaderboard`
- `POST /api/admin/governance/reminders`
- `GET /api/admin/governance/reminders`

**Access:** Admin only  
**Key Behavior:**

- date-range validation
- KPI funnel/timeliness/quality/consistency analytics
- low-performer extraction
- reminder cooldown enforcement + audited send path

### 7.10 Incident Reporting Endpoints

- `POST /api/admin/reports/incidents/generate`
- `GET /api/admin/reports/incidents`
- `GET /api/admin/reports/incidents/{report_id}`
- `GET /api/admin/reports/incidents/{report_id}/export`
- `GET /api/admin/reports/scopes`

**Access:** Admin only  
**Key Behavior:**

- scope/period validation
- report persistence and list/detail retrieval
- CSV export and export audit trails

### 7.11 Kindergarten Import Endpoints

- `POST /api/kindergartens/import-excel`
- `POST /api/admin/kindergartens/import`
- `GET /api/admin/kindergartens/imported`
- `GET /api/admin/imports/logs`

**Access:** primarily Admin (listing imported items also allows Manager by implementation on one route)  
**Behavior:** file validation, structured import summaries, logging/audit, pagination filters for views.

### 7.12 Audit Log Endpoints (`audit_service.py`)

#### 7.12.1 List Audit Logs

- **Method/Path:** `GET /api/audit-logs`
- **Access:** Admin only
- **Query:** `page`, `limit`, `action`, `entity_type`, `user`, `date`
- **Behavior:**
  - optional filters with date parsing
  - username join for display enrichment
  - sorted by newest first
- **Response:** paginated audit log entries

#### 7.12.2 Export Audit Logs

- **Method/Path:** `GET /api/audit-logs/export`
- **Access:** Admin only
- **Query:** `format=csv|json`, `period`, `action`, `entity_type`, `user`
- **Behavior:**
  - optional time-window filtering
  - export cap (`limit 5000`)
  - audit action `AUDIT_LOG_EXPORT`
- **Response:** downloadable CSV/JSON

### 7.13 Dashboard Customization Endpoints (`dashboard_api.py`)

Base prefix in module: `/api/dashboard`

#### 7.13.1 Get User Widgets

- **Method/Path:** `GET /api/dashboard/widgets`
- **Access:** Authenticated user
- **Behavior:** returns role-aware user widget configuration
- **Response:** `{ "widgets": [...] }`

#### 7.13.2 Update User Widgets

- **Method/Path:** `PUT /api/dashboard/widgets`
- **Access:** Authenticated user
- **Body:** `List[Dict]` widgets
- **Behavior:** validates and persists widget config
- **Response:** success message

#### 7.13.3 Reset Widgets

- **Method/Path:** `POST /api/dashboard/widgets/reset`
- **Access:** Authenticated user
- **Behavior:** resets to role defaults
- **Response:** success message

#### 7.13.4 Toggle Widget

- **Method/Path:** `PATCH /api/dashboard/widgets/{widget_id}/toggle?enabled=true|false`
- **Access:** Authenticated user
- **Behavior:** enable/disable single widget by id
- **Response:** success message

#### 7.13.5 Reorder Widgets

- **Method/Path:** `PUT /api/dashboard/widgets/reorder`
- **Access:** Authenticated user
- **Body:** `List[str]` widget order ids
- **Behavior:** updates widget order
- **Response:** success message

#### 7.13.6 List Available Widgets

- **Method/Path:** `GET /api/dashboard/widgets/available`
- **Access:** Authenticated user
- **Behavior:** returns role-available widgets catalog
- **Response:** `{ "widgets": [...] }`

---

## 8) Detailed Workflow (End-to-End)

## 8.1 Admin User Lifecycle Workflow

1. Admin authenticates through main auth pipeline (cookie+CSRF/JWT constraints).
2. Calls `POST /api/admin/users`.
3. Endpoint validates:
   - role constraints
   - manager assignment rules
   - identity/nationality rules (for manager/supervisor where relevant)
   - uniqueness of username/email
4. Data inserted and committed.
5. Audit event `USER_CREATED` logged.
6. Future changes go through `PUT /api/admin/users/{id}` with before/after diff.
7. Optional deactivation or delete (with role/self protections).

## 8.2 Bulk Status Update Workflow

1. Admin submits list + target status.
2. If count exceeds threshold and no token:
   - API returns `requires_confirmation` + token.
3. Admin re-submits with token.
4. API validates per-target authorization and manager consistency constraints.
5. Dry-run returns projected effect; normal run commits.
6. Audit event `BULK_STATUS_UPDATE` stored.

## 8.3 Bulk Delete Workflow

1. Admin submits IDs.
2. API checks max size + disallows admin accounts.
3. Confirmation token required for destructive execution.
4. Dry-run available.
5. Authorized targets are deleted; others reported.
6. Audit event `BULK_USER_DELETE` stored.

## 8.4 CSV Import Workflow

1. Admin uploads `.csv`.
2. System parses UTF-8 BOM-safe.
3. Validates headers and each row:
   - schema validation
   - uniqueness checks
   - role restrictions
   - manager assignment consistency
4. In dry-run: no writes, full report returned.
5. In commit mode: inserts rows, returns created IDs and row errors.
6. Optional error report downloadable as CSV.

## 8.5 Admin Messaging Workflow

1. Admin prepares target:
   - mode (all, by role, governorate, kindergartens)
   - optional search
2. Calls preview endpoint for recipient estimate and sampling.
3. Sends `POST /api/admin/messages` with CSRF token.
4. API validates:
   - subject/body presence and sanitization
   - target validity and existence checks
   - recipient max cap
5. Creates message thread and recipients (chunked inserts).
6. Queues notifications when enabled.
7. Records audit events (`ADMIN_MESSAGE_SENT`, notification events).

## 8.6 Dashboard Workflow

1. Admin calls dashboard endpoint with period.
2. System checks short-lived cache.
3. On miss: computes all KPI/summary/charts/alerts in optimized batches.
4. Stores response in cache.
5. Logs dashboard view action.
6. Returns typed response model.

## 8.7 Backup Workflow

1. Admin creates backup (`database`, optional uploads/config).
2. System writes backup artifacts and metadata.
3. Admin can list/info/validate.
4. Restore path:
   - name sanitized
   - validated
   - limited to DB-type restore for API safety
5. All critical actions are audited.

## 8.8 Governance Reminder Workflow

1. Admin reviews KPI/leaderboard.
2. Requests reminder send to target entity.
3. Cooldown check prevents spam.
4. Reminder recorded with payload snapshot.
5. Audit event emitted for governance traceability.

## 8.9 Incident Reporting Workflow

1. Admin requests generation with scope and period.
2. Service computes metrics and persists report.
3. Reports listed with pagination/filters.
4. Detailed report view accessible.
5. CSV export available and audited.

---

## 9) Security Controls Summary

- Role-based endpoint dependency enforcement
- Object-level authorization (IDOR protection)
- Correlation ID propagation and standardized error payloads
- CSRF validation for state-changing operations (including explicit check in admin messaging)
- Rate limiting on sensitive operations
- Audit logging with sensitivity levels and field redaction
- Confirmation tokens for destructive/high-impact bulk operations
- Path traversal sanitization in backup operations
- Input sanitation and CSV formula injection defense
- Pagination caps to prevent abusive scans/data extraction

---

## 10) Data Contracts / Models (High-Level)

Key response model groups in `admin_endpoints.py`:

- Dashboard:
  - `DashboardSummary`
  - `DashboardSystemOverview`
  - `DashboardKindergarten`
  - `DashboardCharts` / `DashboardChartPoint`
  - `DashboardAlert`
  - `AdminDashboardResponse`
- Messaging:
  - `AdminMessageTarget`, `AdminMessageCreate`, `AdminMessagePreviewRequest`
  - `AdminRecipientSummary`, `AdminRecipientListResponse`
  - `AdminRecipientPreviewResponse`
- Governance:
  - `GovernanceReminderRequest`
- Import:
  - `KindergartenImportResult`

Key security/input schemas in `admin_security.py`:

- `UserCreateSchema`, `UserUpdateSchema`
- `BulkStatusUpdateSchema`, `BulkDeleteSchema`, `BulkCreateSchema`
- `PasswordResetRequestSchema`, `PasswordResetConfirmSchema`, `AdminPasswordResetSchema`
- `CSVRowError`, `CSVImportResult`

---

## 11) Operational Notes and Recommended Usage

1. Prefer dry-run first for bulk and import operations.
2. Use preview endpoints before broadcasting admin messages.
3. Always capture `X-Correlation-ID` in client logs for support/forensics.
4. Monitor audit logs for high-sensitivity actions:
   - MFA bypass
   - password resets
   - bulk delete
   - backup restore
5. Keep settings aligned with production hardening:
   - strict trusted hosts/CORS
   - secure cookies
   - non-development logging and secret policies
6. Periodically validate backup integrity and test restore procedure.
7. Track reminder cooldown behavior in governance workflows to prevent duplicate escalation noise.

---

## 12) Practical Workflow Map (Condensed)

- **Access Layer**: Authenticated admin request -> middleware security gates -> route dependency check
- **Validation Layer**: schema + business rules + role scope + IDOR checks
- **Execution Layer**: DB action (often batch optimized, optionally cached)
- **Safety Layer**: rate limits + confirmation tokens + sanitization
- **Observability Layer**: standardized errors + correlation ID + audit events
- **Response Layer**: typed payload with pagination/summary/warnings where relevant

This is the effective operating model of the Admin Module in the current codebase.
