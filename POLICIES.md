# KinJo Platform — Coding Standards and Operational Policies

This document defines the rules every contributor must follow when working on KinJo. It covers module organization, validation, localization, performance, reusability, exports, error handling, security, naming conventions, and the commit workflow.

---

## Table of Contents

1. [Clarity — Module and File Organization](#1-clarity--module-and-file-organization)
2. [Relevance — Dead Code Policy](#2-relevance--dead-code-policy)
3. [Validation — Forms and API Payloads](#3-validation--forms-and-api-payloads)
4. [Localization — Arabic and English](#4-localization--arabic-and-english)
5. [Performance — Async Data and Loading States](#5-performance--async-data-and-loading-states)
6. [Reusability — Shared Components](#6-reusability--shared-components)
7. [Exports — CSV and PNG Conventions](#7-exports--csv-and-png-conventions)
8. [Error Handling — Templates and Exceptions](#8-error-handling--templates-and-exceptions)
9. [Security — RBAC and Authentication](#9-security--rbac-and-authentication)
10. [Naming Conventions](#10-naming-conventions)
11. [Commit and Branch Strategy](#11-commit-and-branch-strategy)
12. [Architecture Invariants](#12-architecture-invariants)

---

## 1. Clarity — Module and File Organization

### Backend structure

Every feature domain lives in its own file under `api/`. Business logic that is reused across multiple endpoints belongs in a `*_service.py` file at the project root.

| Layer | Location | Example |
|-------|----------|---------|
| REST endpoints | `api/{domain}.py` | `api/enrollment.py`, `api/parent.py` |
| Role-scoped endpoint groups | `routers/{role}.py` | `routers/supervisor.py`, `routers/manager.py` |
| Business / domain logic | `{domain}_service.py` | `kpi_service.py`, `report_service.py` |
| ORM models | `models.py` (single file) | All SQLAlchemy classes |
| Shared utilities | `validators.py`, `i18n.py`, `auth.py` | Audit logging, translation, password hashing |

**Do not** put business logic in `main.py` or `frontend.py`. Route handler functions should be thin: validate → call service → return response.

### Frontend structure

Templates are organized by role. Shared UI components live exclusively in `templates/components/`.

```
templates/
├── base.html               ← master layout (all pages extend this)
├── admin_base.html         ← admin-specific layout
├── components/             ← reusable partials (ONLY place for shared markup)
├── admin/                  ← admin role pages
├── manager/                ← manager role pages
├── supervisor/             ← supervisor role pages
├── parent/                 ← parent role pages
├── enrollment/             ← enrollment workflow
├── attendance/             ← attendance tracking
├── communication/          ← messages, events, surveys
├── auth/                   ← login, register, MFA, password reset
└── error pages (403.html, 404.html, 500.html)
```

### Function naming

Name every function after the action it performs. Use one of these prefixes:

| Prefix | Action |
|--------|--------|
| `get_` | Read a single record |
| `list_` | Read a collection |
| `create_` | Insert a new record |
| `update_` | Modify an existing record |
| `delete_` | Remove a record |
| `submit_`, `approve_`, `reject_` | State transitions |

One function = one responsibility. If a function needs an inline comment to explain what it does, it should be split.

---

## 2. Relevance — Dead Code Policy

- **No placeholder routes.** Every registered route must serve a real, tested purpose.
- **No stub functions.** Functions must be fully implemented before being merged to `main`.
- **No commented-out code blocks.** Use git history to recover removed code.
- **`missing_endpoints.py` is the last-resort router** registered last in `main.py`. New endpoints must go in their domain module (`api/{domain}.py`). Adding endpoints to `missing_endpoints.py` is not permitted.
- **Duplicate route registrations are a test failure.** The test `test_no_duplicate_route_method_registrations` in `tests/test_route_registration.py` asserts zero duplicates. A PR that introduces a duplicate route will fail CI.

---

## 3. Validation — Forms and API Payloads

### Backend — Pydantic models (required)

Every `POST`, `PUT`, and `PATCH` endpoint must accept a typed Pydantic `BaseModel` as its request body. Raw `dict` or `Any` bodies are not permitted.

```python
from pydantic import BaseModel, Field, field_validator
from datetime import date

class EnrollmentApplicationRequest(BaseModel):
    first_name: str = Field(..., min_length=1, max_length=100)
    last_name: str = Field(..., min_length=1, max_length=100)
    date_of_birth: date           # Pydantic validates ISO format → auto-422 on bad input
    kindergarten_id: int = Field(..., gt=0)
    gender: str

    @field_validator("gender")
    @classmethod
    def validate_gender(cls, v: str) -> str:
        if v.upper() not in ("MALE", "FEMALE"):
            raise ValueError("gender must be MALE or FEMALE")
        return v.upper()
```

**HTTP status code conventions:**

| Situation | Status Code | When to use |
|-----------|-------------|-------------|
| Schema / type error | 422 | Pydantic returns this automatically |
| Business rule violation | 400 | Custom logic (e.g., child too old for enrollment) |
| Not authorized | 403 | Wrong role or scope |
| Resource not found | 404 | Record does not exist |
| Duplicate / conflict | 409 | Unique constraint violation |

### Frontend — JavaScript validation

Validate all required fields **before** calling `fetch()`. Do not rely solely on HTML5 `required` attributes.

```javascript
async function submitEnrollment(formData) {
    // Client-side gate
    if (!formData.get('first_name') || !formData.get('kindergarten_id')) {
        Swal.fire({
            icon: 'warning',
            title: ui_lang === 'en' ? 'Required fields missing' : 'حقول مطلوبة غير مكتملة',
            text: ui_lang === 'en' ? 'Please fill in all required fields.' : 'يرجى تعبئة جميع الحقول المطلوبة.'
        });
        return;
    }

    const resp = await fetch('/api/enrollment/apply', {
        method: 'POST',
        headers: {'Content-Type': 'application/json', 'X-CSRF-Token': getCsrfToken()},
        body: JSON.stringify(Object.fromEntries(formData))
    });

    if (!resp.ok) {
        const err = await resp.json();
        Swal.fire({ icon: 'error', title: 'Error', text: err.detail });
        return;
    }
    // success path
}
```

**Rules:**
- Use **SweetAlert2** (`Swal.fire`) for all error/confirmation dialogs. SweetAlert2 is pre-loaded in `base.html`.
- Show inline field errors next to the specific `<input>` that failed, in addition to the modal.
- Never swallow errors silently — always surface them to the user.

---

## 4. Localization — Arabic and English

KinJo is a bilingual platform. Arabic is the primary language; English is the secondary. Every user-facing string must support both.

### Templates — `ui_lang` blocks

`ui_lang` is injected by the language context processor in `frontend.py` and is available in every template automatically.

```jinja2
{# Correct — both languages covered #}
{% if ui_lang == 'en' %}Add Child{% else %}إضافة طفل{% endif %}

{# Correct — button label #}
<button type="submit">
    {% if ui_lang == 'en' %}Save Changes{% else %}حفظ التغييرات{% endif %}
</button>

{# Wrong — hardcoded string #}
<button type="submit">Save Changes</button>
```

RTL layout for Arabic is handled automatically by `rtl.css`, which is included when `ui_lang == 'ar'`. Do not add manual `dir="rtl"` attributes to individual elements — the stylesheet applies them globally.

### JavaScript strings — i18n JSON files

Dynamic strings rendered by JavaScript must come from the i18n JSON files, not be hardcoded.

**Files:**
- `static/i18n/ar.json` and `static/i18n/en.json` — core app strings
- `static/i18n/admin_ar.json` and `static/i18n/admin_en.json` — admin interface
- `static/i18n/app_ar.json` and `static/i18n/app_en.json` — application UI strings

**Usage:**

```javascript
// appText() is defined in static/js/admin_i18n.js
// It reads from the loaded i18n JSON for the current ui_lang
const label = appText('enrollment.status.pending');

// For inline ternary in JS files that pre-load ui_lang from a template variable:
const title = ui_lang === 'en' ? 'Enrollment Submitted' : 'تم تقديم الطلب';
```

### Backend API error messages

Use the `i18n.gettext` helper from `i18n.py` to return localized error messages in API responses:

```python
from i18n import gettext as _api

def _ulang(user) -> str:
    return getattr(user, "preferred_language", None) or "ar"

# In an endpoint:
raise HTTPException(
    status_code=403,
    detail=_api("Parent access only", _ulang(current_user))
)
```

---

## 5. Performance — Async Data and Loading States

### Fetch API for dynamic data

Dashboard statistics, list views, and analytics data must be loaded asynchronously. Do not render large datasets directly in Jinja2 template context — this blocks the page and makes filtering impossible without a reload.

```javascript
async function loadDashboardStats() {
    const spinner = document.getElementById('statsSpinner');
    const content = document.getElementById('statsContent');

    spinner.classList.remove('d-none');
    content.classList.add('d-none');

    try {
        const resp = await fetch('/api/manager/dashboard');
        if (!resp.ok) throw new Error('Failed to load stats');
        const data = await resp.json();
        renderStats(data);
        content.classList.remove('d-none');
    } catch (err) {
        content.innerHTML = `<p class="text-danger">${ui_lang === 'en' ? 'Failed to load data.' : 'فشل تحميل البيانات.'}</p>`;
        content.classList.remove('d-none');
    } finally {
        spinner.classList.add('d-none');
    }
}
```

### Spinner convention

Every async section must show a loading spinner while data is in flight:

```html
<div id="statsSpinner" class="text-center py-4">
    <div class="spinner-border text-primary" role="status">
        <span class="visually-hidden">
            {% if ui_lang == 'en' %}Loading...{% else %}جاري التحميل...{% endif %}
        </span>
    </div>
</div>
<div id="statsContent" class="d-none">
    <!-- populated by JS -->
</div>
```

**Rules:**
- The `visually-hidden` span inside every `spinner-border` is **required** for accessibility (screen readers).
- Do not use `display:none` inline styles — use Bootstrap's `d-none` class.
- Do not reload the entire page to refresh a data table; update only the affected DOM nodes.

### Redis caching for heavy queries

Analytics aggregations and KPI calculations that touch large datasets must be cached:

```python
# In a service function
from cache_service import get_cache, set_cache

cache_key = f"kpi:kg:{kindergarten_id}:{date.today()}"
cached = get_cache(cache_key)
if cached:
    return cached
result = compute_expensive_kpi(db, kindergarten_id)
set_cache(cache_key, result, ttl=300)   # 5 minute TTL
return result
```

---

## 6. Reusability — Shared Components

### Templates — always `{% include %}`, never copy markup

The shared components in `templates/components/` must be included via Jinja2's `{% include %}` directive. Duplicating their markup into page templates is prohibited.

```jinja2
{# Required inclusions in every page template #}
{% include 'components/navbar.html' %}
{% include 'components/sidebar.html' %}

{# Use when the page has filter controls #}
{% include 'components/filter-row.html' %}

{# Use for delete/archive confirmation prompts #}
{% include 'components/confirm-modal.html' %}

{# Use when the page has export functionality #}
{% include 'components/export-modal.html' %}

{# Use for data tables with sort/pagination #}
{% include 'components/data-table.html' %}
```

**Available components:**

| Component | Purpose |
|-----------|---------|
| `navbar.html` | Top navigation bar with user menu, notifications, language switcher |
| `sidebar.html` | Role-specific side navigation |
| `filter-row.html` | Standardized filter bar (search, date range, status) |
| `confirm-modal.html` | Bootstrap modal for delete/archive confirmations |
| `export-modal.html` | Export options dialog (CSV, PDF, PNG) |
| `data-table.html` | Sortable, paginated data table wrapper |
| `alert_banner.html` | Flash message display |
| `impersonation_banner.html` | Admin impersonation warning bar |
| `chart_container.html` | Chart.js canvas wrapper with resize handling |
| `kpi_card.html` | KPI metric card with icon, value, trend |

### CSS — utility classes, never inline styles

All styling must use `kinjo.css` utility classes. Inline `style=` attributes on HTML elements are prohibited except in edge cases explicitly documented with a comment.

**Status badges:**
```html
{# Correct #}
<span class="badge badge-soft badge-soft-success rounded-pill">Active</span>
<span class="badge badge-soft badge-soft-warning rounded-pill">Pending</span>
<span class="badge badge-soft badge-soft-danger rounded-pill">Rejected</span>

{# Wrong — raw Bootstrap color class #}
<span class="badge bg-success">Active</span>
```

**KPI / stat icon circles:**
```html
{# Correct — use semantic color modifiers #}
<div class="stat-icon-wrap stat-icon-success"><i class="bi bi-check-circle"></i></div>
<div class="stat-icon-wrap stat-icon-danger"><i class="bi bi-exclamation-circle"></i></div>
<div class="stat-icon-wrap stat-icon-warning"><i class="bi bi-clock"></i></div>
<div class="stat-icon-wrap stat-icon-info"><i class="bi bi-info-circle"></i></div>
<div class="stat-icon-wrap stat-icon-primary"><i class="bi bi-people"></i></div>

{# Wrong — inline style #}
<div class="stat-icon-wrap" style="background:rgba(16,185,129,0.12);color:#10b981;">...</div>
```

**Other utilities:**
```html
<!-- Breadcrumb sizing -->
<ol class="breadcrumb breadcrumb-sm">...</ol>

<!-- Character counter for textareas -->
<small class="form-counter" id="charCount">0 / 500</small>

<!-- Message list items (inbox views) -->
<div class="msg-item unread">
    <div class="msg-avatar">AB</div>
    <div class="flex-grow-1">
        <div class="msg-preview">Message preview text...</div>
        <span class="msg-time">10:30 AM</span>
    </div>
</div>
```

### JavaScript — shared API helper

Centralize API calls in a reusable fetch wrapper rather than repeating `fetch()` boilerplate in every template's `<script>` block:

```javascript
// Defined once in a shared JS file (e.g., static/js/api_helpers.js)
async function apiFetch(url, options = {}) {
    const defaults = {
        headers: {
            'Content-Type': 'application/json',
            'X-CSRF-Token': document.cookie.match(/kinjo_csrf=([^;]+)/)?.[1] || ''
        }
    };
    const resp = await fetch(url, { ...defaults, ...options });
    if (!resp.ok) {
        const err = await resp.json().catch(() => ({ detail: 'Unknown error' }));
        throw new Error(err.detail || `HTTP ${resp.status}`);
    }
    return resp.json();
}
```

---

## 7. Exports — CSV and PNG Conventions

### Export toolbar pattern

Every page with export functionality must use the standardized toolbar button layout:

```html
<div class="d-flex gap-2 ms-auto">
    <button class="btn btn-outline-secondary btn-sm" id="exportCsvBtn">
        <i class="bi bi-download me-1"></i>
        {% if ui_lang == 'en' %}Export CSV{% else %}تصدير CSV{% endif %}
    </button>
    <button class="btn btn-outline-secondary btn-sm" id="exportPngBtn">
        <i class="bi bi-image me-1"></i>
        {% if ui_lang == 'en' %}Export PNG{% else %}تصدير PNG{% endif %}
    </button>
</div>
```

### CSV export — server-side

The export button triggers a GET request to a server endpoint that returns the file:

```javascript
document.getElementById('exportCsvBtn').addEventListener('click', async () => {
    const url = `/api/admin/export?format=csv&scope=${currentScope}&from=${fromDate}&to=${toDate}`;
    const resp = await fetch(url);
    if (!resp.ok) return;
    const blob = await resp.blob();
    const a = document.createElement('a');
    a.href = URL.createObjectURL(blob);
    a.download = `kinjo-export-${new Date().toISOString().slice(0,10)}.csv`;
    a.click();
});
```

The server endpoint must set the correct response headers:

```python
from fastapi.responses import StreamingResponse
import csv, io

@router.get("/admin/export")
def export_data(format: str = "csv", ...):
    output = io.StringIO()
    writer = csv.writer(output)
    # ... write rows
    output.seek(0)
    return StreamingResponse(
        iter([output.getvalue()]),
        media_type="text/csv",
        headers={"Content-Disposition": f"attachment; filename=kinjo-export.csv"}
    )
```

### PNG export — client-side Chart.js

Chart PNG exports are generated client-side using Chart.js's built-in method:

```javascript
document.getElementById('exportPngBtn').addEventListener('click', () => {
    const chart = Chart.getChart('attendanceChart');  // canvas element id
    const url = chart.toBase64Image('image/png', 1.0);
    const a = document.createElement('a');
    a.href = url;
    a.download = `kinjo-chart-${new Date().toISOString().slice(0,10)}.png`;
    a.click();
});
```

### Export status tracking

For long-running exports (large date ranges, full network exports), use the `ExportStatus` lifecycle managed by `export_service.py`:

```
PENDING → PROCESSING → COMPLETED | FAILED
```

Poll the export status endpoint and show a progress indicator while the export is being generated.

---

## 8. Error Handling — Templates and Exceptions

### Custom error pages

KinJo serves custom error templates for all standard HTTP errors. These templates are configured in `main.py`:

| Template | HTTP Status | Trigger |
|----------|-------------|---------|
| `templates/403.html` | 403 Forbidden | `HTTPException(status_code=403)` |
| `templates/404.html` | 404 Not Found | `HTTPException(status_code=404)` |
| `templates/500.html` | 500 Server Error | Unhandled exceptions in middleware |

**Never expose raw exception messages, stack traces, or database errors to end users.** The `security.py` middleware catches `SQLAlchemyError` and all unhandled exceptions, returning a structured 500 response.

### Backend exception pattern

```python
from fastapi import HTTPException
from i18n import gettext as _api

def _ulang(user) -> str:
    return getattr(user, "preferred_language", None) or "ar"

# Authorization failure
raise HTTPException(
    status_code=403,
    detail=_api("You do not have permission to perform this action", _ulang(current_user))
)

# Resource not found
raise HTTPException(
    status_code=404,
    detail=_api("Record not found", _ulang(current_user))
)

# Business rule violation
raise HTTPException(
    status_code=400,
    detail=_api("Child is already enrolled in another kindergarten", _ulang(current_user))
)
```

### Frontend error display pattern

```javascript
try {
    const data = await apiFetch('/api/enrollment/apply', { method: 'POST', body: JSON.stringify(payload) });
    Swal.fire({ icon: 'success', title: ui_lang === 'en' ? 'Submitted' : 'تم التقديم', timer: 2000 });
} catch (err) {
    Swal.fire({
        icon: 'error',
        title: ui_lang === 'en' ? 'Error' : 'خطأ',
        text: err.message
    });
}
```

---

## 9. Security — RBAC and Authentication

### Authentication requirement

Every endpoint must call `get_current_user` from `dependencies.py`. The only **explicitly anonymous** endpoints are:

- `POST /token` — login
- `POST /register/parent` — parent self-registration
- `GET /health` — health check
- Static assets (`/static/*`)

```python
from dependencies import get_current_user

@router.get("/parent/children")
def get_children(
    current_user: models.User = Depends(get_current_user),  # required
    db: Session = Depends(get_db),
):
    ...
```

### Role-based access control

Check `current_user.role` at the top of every endpoint that is role-specific:

```python
if current_user.role != models.UserRole.PARENT:
    raise HTTPException(status_code=403, detail=_api("Parent access only", _ulang(current_user)))
```

For admin-or-manager access:
```python
if current_user.role not in {models.UserRole.ADMIN, models.UserRole.MANAGER}:
    raise HTTPException(status_code=403, detail="Admin or Manager access required")
```

### Kindergarten scoping

Managers and Supervisors can only access data within their assigned kindergarten. Enforce this on every query:

```python
# For manager/supervisor endpoints — always filter by kindergarten_id
query = db.query(models.Child).join(models.EnrollmentApplication).filter(
    models.EnrollmentApplication.kindergarten_id == current_user.kindergarten_id
)
```

Admins are the only role that may access cross-kindergarten data.

### Password policy (enforced by `config.py`)

| Rule | Value |
|------|-------|
| Minimum length | 8 characters |
| Requires uppercase | Yes |
| Requires lowercase | Yes |
| Requires digit | Yes |
| Requires special character | Yes |
| Maximum password age | 90 days |
| Account lockout threshold | 5 failed attempts |
| Lockout duration | 30 minutes |

Use `auth.PasswordValidator.validate(password)` to check any new password against these rules.

### CSRF protection

All HTML forms that perform state-changing operations (`POST`, `PUT`, `DELETE`) must include the CSRF token:

```jinja2
<form method="POST" action="/api/enrollment/apply">
    <input type="hidden" name="csrf_token" value="{{ csrf_token() }}">
    <!-- form fields -->
</form>
```

For JavaScript `fetch()` calls, include the token in the `X-CSRF-Token` header (see the `apiFetch` helper in Section 6).

### JWT tokens

- Algorithm: `HS256`
- Expiry: `ACCESS_TOKEN_EXPIRE_MINUTES` (default: 30 minutes)
- Stored in: HttpOnly cookie (`kinjo_session`) — never in `localStorage`

---

## 10. Naming Conventions

| Entity | Convention | Example |
|--------|-----------|---------|
| Python module files | `snake_case.py` | `daily_report_analytics.py` |
| API URL paths | `kebab-case` segments | `/api/daily-reports/{report_id}` |
| Pydantic model classes | `PascalCase` | `EnrollmentApplicationRequest` |
| SQLAlchemy model classes | `PascalCase` | `EnrollmentApplication`, `DailyReport` |
| Database columns | `snake_case` | `submitted_at`, `kindergarten_id`, `deleted_at` |
| Database tables | `snake_case` (plural) | `enrollment_applications`, `daily_reports` |
| Python functions | `snake_case` | `get_parent_children()`, `submit_enrollment()` |
| Python variables | `snake_case` | `parent_profile`, `enrollment_id` |
| Jinja2 template files | `snake_case.html` | `daily_reports.html`, `class_form.html` |
| JavaScript functions | `camelCase` | `fetchDashboardData()`, `renderKpiCards()` |
| JavaScript variables | `camelCase` | `currentPage`, `selectedKgId` |
| CSS utility classes | `kebab-case` | `.stat-icon-wrap`, `.breadcrumb-sm`, `.msg-item` |
| CSS color modifiers | `kebab-case` | `.stat-icon-success`, `.badge-soft-danger` |
| Test files | `test_{module}.py` | `test_enrollment_rules.py` |
| Test functions | `test_{action}_{context}` | `test_parent_sees_sent_reports()` |
| Git branches | `{type}/{description}` | `feature/absence-requests`, `fix/enrollment-rbac` |

### Enum naming

All SQLAlchemy / Pydantic enums use `UPPER_SNAKE_CASE` values:

```python
class EnrollmentStatus(str, enum.Enum):
    DRAFT = "DRAFT"
    SUBMITTED = "SUBMITTED"
    PENDING_REVIEW = "PENDING_REVIEW"
    ACCEPTED = "ACCEPTED"
    REJECTED = "REJECTED"
    ACTIVE = "ACTIVE"
```

---

## 11. Commit and Branch Strategy

### Branch naming

```
feature/{short-description}    # New functionality
fix/{short-description}        # Bug fix
ux/{short-description}         # UI/UX improvement
security/{short-description}   # Security change
infra/{short-description}      # Infrastructure / CI / Docker
docs/{short-description}       # Documentation only
```

### Commit message format

```
{type}: {imperative description}

{optional body — what and why, not how}
```

**Types:** `feat`, `fix`, `ux`, `security`, `infra`, `docs`, `refactor`, `test`

**Examples:**
```
fix: enforce RBAC on enrollment submission endpoint
feat: add absence request cancellation for parents
security: rate-limit password reset endpoint by IP
ux: replace inline styles with kinjo.css utility classes
infra: add dedicated docker-compose.prod.yml
```

### Pre-push gate

Before every push, run:

```bash
make check
```

This runs: `lint` + `lint-py-strict` + `test-p0`. All three must pass.

The following test must **always** pass:

```bash
pytest tests/test_route_registration.py
# Expected: 1 passed — 0 duplicate route registrations
```

### Pull request checklist

Before opening a PR:

- [ ] `make check` passes locally
- [ ] New endpoints have tests in `tests/test_{module}.py`
- [ ] New templates use `{% include 'components/navbar.html' %}` and `{% include 'components/sidebar.html' %}`
- [ ] All user-facing strings are wrapped in `{% if ui_lang == 'en' %}...{% else %}...{% endif %}`
- [ ] Spinners have `<span class="visually-hidden">Loading...</span>`
- [ ] No inline `style=` attributes on HTML elements (use utility classes)
- [ ] Alembic migration generated and committed for any `models.py` changes
- [ ] `test_no_duplicate_route_method_registrations` passes

---

## 12. Architecture Invariants

These constraints must never be violated:

1. **Single source of ORM truth.** All SQLAlchemy models live in `models.py`. Do not define models in other files.

2. **Router registration order.** Domain-specific routers (`api/enrollment.py`, etc.) are always registered before `missing_endpoints.py`. The catch-all router is always last.

3. **Test isolation.** Tests use in-memory SQLite (`StaticPool`). Tests must not depend on an external PostgreSQL or Redis instance. The `TESTING=true` environment variable is set by `conftest.py` before any app import.

4. **No production SQLite.** `database.py` enforces this: if `ENVIRONMENT=production` and `DATABASE_URL` contains `sqlite`, the app raises a `ValueError` at startup.

5. **No raw secrets in code.** All credentials, API keys, and tokens must come from environment variables via `config.py`. Never hardcode a secret in a Python file, template, or JavaScript file.

6. **Soft deletes for users and children.** Records with a `deleted_at` column must always be filtered with `.filter(Model.deleted_at.is_(None))` in list views. Hard deletion is reserved for compliance-mandated purges only.

7. **Audit logging for state changes.** Any endpoint that changes the status of an enrollment, daily report, or user account must call `validators.log_audit_action(...)`. This feeds the admin audit log UI and the government reporting API.

8. **Celery for long-running tasks.** Background jobs (report dispatch, email delivery, export generation) must run in Celery workers, not in synchronous endpoint handlers. Use `celery_app.py` task definitions.
