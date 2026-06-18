# KinJo Admin Module — Developer Guide

## Overview

The admin module lives in `admin_endpoints.py` and is mounted at `/api` in `main.py`
(registered **before** `api_router` so admin routes take precedence on any path overlap).
All routes use the `/admin/` prefix: `GET /api/admin/users`, `POST /api/admin/backup/create`, etc.

Frontend admin templates extend `admin_base.html` (not `base.html`).
Admin UI pages are served by route handlers in `frontend.py`.

---

## How to Add a New Admin Endpoint

### 1. Define the route in `admin_endpoints.py`

```python
@router.get("/admin/my-feature")
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
    db=db,
    user_id=current_user.id,
    action=AuditAction.ADMIN_UPDATE_USER,
    resource_type="User",
    resource_id=user.id,
    details={"before": before_dict, "after": after_dict},
    request=request,
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

The template engine has `settings` registered as a global, so templates can use
`{{ settings.SESSION_TIMEOUT_MINUTES }}` without it being passed in the context.

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
