# Admin Staging Gate Validation

**Date:** 2026-07-14

## Outcome

The repository contains an environment-driven Admin staging smoke harness at `scripts/manual-diagnostics/staging_smoke_test.py`. The harness is intended for an approved staging environment and produces a JSON report plus a non-zero process exit when a required check fails.

## Settled-tree evidence

- Full repository suite: **3,068 passed, 1 xpassed, 0 failed** in 22 minutes 42 seconds (`EXIT=0`).
- Admin production-readiness review: **PRODUCTION READY**.
- Effective FastAPI route inventory: **709 unique method/path pairs, 0 duplicates**.
- Alembic forward migration on an empty temporary database: **34 migrations applied to the single head `f7a1c2e9b3d0`**.
- Production configuration validation: rejects development/weak secrets, non-Redis rate-limit storage, and incomplete production configuration at import/startup.

## Smoke-harness coverage

- Public and authenticated health probes.
- Unauthenticated Admin authorization boundary.
- Login, cookie session, and CSRF double-submit enforcement.
- Admin user create/read/soft-delete and deleted-user login denial.
- Dry-run malformed XLSX and CSV rejection.
- User export response contract.
- Impersonation start/end audit attribution.
- One-time restore-token replay denial using the captured Manager session.
- Logout-during-impersonation restore-token revocation and replay denial.
- Admin logout cookie clearing and post-logout browser-session denial.
- Optional rate-limit exhaustion probe.

The harness requires explicit mutation acknowledgement. Non-local targets must use HTTPS and `SMOKE_EXPECTED_HOST` must exactly match the target hostname. The rate-limit probe is disabled by default because it intentionally consumes the source address's login allowance.

## Local validation

The strengthened harness was run against a temporary localhost application instance:

- Exit code: **0**
- Required checks: **10 passed, 0 failed**
- Optional checks: **1 skipped** (rate-limit probe disabled)
- Harness safety regression tests: **5 passed**
- Temporary application listener: stopped after validation

The run soft-deleted its uniquely named test user. Soft deletion deliberately preserves database and audit history; staging data-retention procedures should purge smoke records when policy requires physical removal.

## Migration rollback note

The SQLite `head -> base` exercise reaches revision `e3f4a5b6c7d8` and then encounters `no such column: class_id` during Alembic batch-table recreation. The production PostgreSQL branch uses direct `DROP COLUMN` rather than SQLite batch recreation. This does not invalidate the PostgreSQL production path, but rollback must still be exercised against a disposable staging PostgreSQL clone before cutover.

## Remaining ownership boundary

Infrastructure provisioning, staging execution with deployment secrets, real backup restoration, live monitoring review, stakeholder acceptance, and the production change window remain operations-owned activities.
