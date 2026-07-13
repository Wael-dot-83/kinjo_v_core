# KinJo Admin Module — Developer Guide

> This quick-reference is subordinate to the comprehensive [Admin Module Guide](ADMIN_GUIDE.md) and generated [Admin API Reference](ADMIN_API_REFERENCE.md). If they differ, the comprehensive guide and registered OpenAPI schema are authoritative.

## Overview

The core router lives in `admin_endpoints.py` and is mounted at `/api/admin` in `main.py`.
Its route decorators use paths relative to that prefix. Specialist Admin routers and
frontend page routes are catalogued in `docs/ADMIN_GUIDE.md`.

Frontend admin templates extend `admin_base.html` (not `base.html`).
Most Admin UI handlers live in `scripts/compat/frontend_orig.py` and are registered
through the lightweight `frontend.py` compatibility loader.

---

## How to Add a New Admin Endpoint

### 1. Define the route in `admin_endpoints.py`

```python
@router.get("/my-feature")
@limiter.limit(settings.RATE_LIMIT_ADMIN_READ)   # always add a rate limit
def my_feature(
    request: Request,                             # required by slowapi
    current_user: models.User = Depends(require_admin),  # always require admin
    db: Session = Depends(get_db),
):
    ...
    return {"data": ...}
```

Rules:
- **Always** use `Depends(require_admin)` — never inline role checks.
- **Always** add `request: Request` as the first parameter (slowapi requires it).
- **Always** add `@limiter.limit(...)` — use `RATE_LIMIT_ADMIN_READ` for reads, `RATE_LIMIT_ADMIN_WRITE` for writes.
- State-changing endpoints (POST/PUT/PATCH/DELETE) must log an audit event:

```python
log_audit_event(
    db,
    AuditAction.USER_UPDATED,
    current_user,
    "User",
    target_ids=user.id,
    before_state=before_dict,
    after_state=after_dict,
    metadata={"source": "admin_api"},
)
```

### 2. Add a Pydantic request body (for POST/PUT/PATCH)

```python
class _MyFeatureBody(BaseModel):
    model_config = ConfigDict(str_strip_whitespace=True)
    name: str = Field(..., min_length=1, max_length=100)
```

Use `model_config = ConfigDict(str_strip_whitespace=True)` to strip whitespace automatically.

### 3. Add pagination for list endpoints

```python
page: int = Query(1, ge=1),
page_size: int = Query(settings.DEFAULT_PAGE_SIZE, ge=1, le=settings.MAX_PAGE_SIZE),
```

### 4. Write tests

Create `tests/test_admin_<feature>.py`. Cover at minimum:
- Unauthenticated → 401
- Manager/non-admin → 403
- Valid admin request → 200 with expected shape
- Invalid input → 400/422

---

## How to Add a New Alembic Migration

```bash
# Auto-generate from model changes (review carefully before committing)
alembic revision --autogenerate -m "describe_the_change"

# Or write manually (preferred for complex changes)
alembic revision -m "add_my_new_index"
```

Edit the generated file in `alembic/versions/`. Rules:
- Guard PostgreSQL-specific DDL with `if _is_postgresql():` (see `g1h2i3j4k5l6_performance_indexes.py` for the pattern).
- Use `CREATE INDEX CONCURRENTLY IF NOT EXISTS` for production-safe index creation.
- Always implement a `downgrade()` that is the exact inverse of `upgrade()`.
- Test both directions: `alembic upgrade head && alembic downgrade -1 && alembic upgrade head`.

Apply:
```bash
alembic upgrade head
```

---

## How to Seed Data for a New Feature

Add seed data to `seed_local.py` (development) and document the production seed steps in `RUNBOOK.md`.

Do not hardcode passwords — use `SEED_*_PASSWORD` environment variables.

---

## Template Conventions

Admin pages extend `admin_base.html`. Template blocks:

| Block | Purpose |
|---|---|
| `title` | `<title>` tag |
| `extra_head` | `<style>` blocks and extra `<meta>` tags |
| `breadcrumb` | Breadcrumb navigation (Dashboard → Page Name) |
| `content` | Main page content |
| `extra_scripts` | Page-specific `<script>` blocks |

The template engine exposes only approved non-sensitive globals. For example,
templates use `{{ session_timeout_minutes }}`; the complete settings object is
intentionally not exposed.

---

## Architecture Decisions

### Why `require_admin` as a dependency instead of inline role checks?

Inline checks (`if current_user.role != ADMIN: raise 403`) were silently missing
on several endpoints — the dependency pattern (`Depends(require_admin)`) makes the
authorization check non-optional and visible in the function signature.

### Why is `missing_endpoints.py` not split into domain files?

It contains 26 user-facing routes that were audited (2026-06-14) and confirmed safe —
no conflicts with admin routes. Migration to domain-specific router files is planned
as a separate refactor; doing it alongside security fixes would have expanded blast radius.

### Why double-submit confirmation token for bulk/destructive operations?

Bulk delete and backup restore are irreversible. A two-step flow (first call returns
a short-lived token; second call submits it) prevents accidental data loss from UI bugs,
copy-paste errors, or replay attacks. See `generate_confirmation_token` /
`verify_confirmation_token` in `admin_security.py`.

---

## Icon Usage Rule

The app uses **Bootstrap Icons** (`bi bi-*`) exclusively — loaded once in `admin_base.html`
and `base.html`. Font Awesome was removed in Round 3 of the GWS audit (`GWS/unify_icons.py`
has the full fa-\* -> bi-\* mapping used). Do not add Font Awesome (`fas fa-*`, `far fa-*`,
`fab fa-*`) classes or a new Font Awesome `<link>` to any template — find the closest
Bootstrap Icons glyph at https://icons.getbootstrap.com instead. For a spinning icon, use
`bi bi-arrow-repeat bi-spin` (the `.bi-spin` utility lives in `static/css/kinjo.css`).

---

## Security Checklist for New Admin Endpoints

- [ ] Uses `Depends(require_admin)` — not inline role check
- [ ] Has `@limiter.limit(...)` decorator
- [ ] All string inputs are validated (Pydantic Field with min/max_length)
- [ ] No raw SQL string interpolation (use SQLAlchemy ORM or `text()` with bound params)
- [ ] No `hashed_password` or secret fields in response bodies
- [ ] State-changing operations emit an audit log event
- [ ] Destructive bulk operations require confirmation token
- [ ] Tests cover 401, 403, 200/201, and invalid input (400/422)
