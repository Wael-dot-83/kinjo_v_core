# Admin Analytics — PostgreSQL Verification (Evidence)

**Date:** 2026-07-12
**Branch:** `admin-analytics-prod-readiness`
**Engine:** PostgreSQL **16.13** (Docker `postgres:16-alpine`)

This closes the Master Implementation Prompt's §22 Postgres acceptance criteria for
the admin analytics work. The dev database is SQLite; these results were produced
against a **real Postgres** instance, executed locally (not only in CI).

> Nothing here is projected. Each result is the tail of an actual command run.

---

## 1. Analytics test suite on Postgres — PASS

Run with the opt-in test engine (`conftest.py` honours `TEST_DATABASE_URL`):

```
TEST_DATABASE_URL=postgresql://…@localhost:5432/… \
  pytest tests/test_metric_registry.py tests/test_data_state_handling.py \
         tests/test_analytics_child_detail_rbac.py tests/test_analytics_service.py \
         tests/test_analytics_gap.py tests/test_analytics_rbac.py \
         tests/test_drilldown_page_frontend_contract.py \
         tests/api/test_p0_analytics_kpi.py tests/api/test_p1_analytics_summary.py \
         tests/api/test_p1_analytics_export.py

=> 171 passed, 1 warning in 326.24s
```

Covers: metric registry, data-state handling, child_detail RBAC, drill-down
(Country→Governorate→City→Nursery→Class→Child incl. the new City level and CHILD
leaf), gap metrics (all 33), analytics RBAC, and the analytics API layer — all
executing real queries (grouped counts, joins, `func.distinct`) on Postgres.

## 2. Alembic migrations on Postgres — PASS (empty → head, reversible)

Fresh empty database:

```
alembic upgrade head       # empty -> head, all revisions applied, ends at f7a1c2e9b3d0
alembic downgrade -1       # reversibility of the latest revision
alembic upgrade head       # back to head
alembic current            # => f7a1c2e9b3d0 (head)
```

No new migrations were introduced by this effort — the "Area = City" decision
surfaces the existing `Kindergarten.area` field as the City drill-down level, so
there is no schema change to migrate.

## 3. CI coverage

- `ci.yml` `migrations` job: runs the Alembic upgrade→downgrade→upgrade on
  `postgres:15` on every push.
- `ci.yml` `analytics-postgres` job: runs the analytics suite above against a
  `postgres:15` service via `TEST_DATABASE_URL`.

## 4. Portability note

All SQL added by this effort is standard SQLAlchemy Core/ORM with no SQLite-only
idioms (no `strftime`, `julianday`, `glob`, etc.). The default SQLite test path is
unchanged and remains green (3072 tests).
