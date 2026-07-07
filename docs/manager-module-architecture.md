# Manager Module — Architecture & Hardening Notes

This document records the decisions from the Manager-module production-hardening
pass. It covers the assignment source of truth, authorization scoping, audit
strategy, index additions, the two-stage legacy-column drop plan, and notes on
issue-list items that were already fixed or turned out to be inaccurate.

## 1. Supervisor assignment — single source of truth (D1/B5)

`SupervisorAssignment` is the **only** source of truth for which supervisor runs
a class. The legacy denormalised `Class.supervisor_id` column has been retired at
the code level:

- **Reads** — the current primary supervisor of a class is
  `validators.active_primary_supervisor_map(db, class_ids)`, which returns
  `{class_id: supervisor_id}` from the active (`is_primary = True`,
  `deleted_at IS NULL`) assignment rows. All former readers now use it:
  `manager_analytics.py` (supervisor-workload aggregates JOIN
  `SupervisorAssignment`; the class drill-down uses the map),
  `classification_service.py`, `api/supervisor.py`, and the change-detection in
  `api/classes.py`.
- **Writes** — nothing writes `Class.supervisor_id` any more. The pure column-sync
  helper `validators.set_class_primary_supervisor_id` was removed along with its
  call sites (`routers/manager.py` assign/unassign/swap, `api/classes.py`
  create/update) and the offboarding column-clear in
  `manager_assignment_service.py`. `validators.retire_active_primary_assignment`
  is **kept** — it soft-deletes the active primary `SupervisorAssignment` row and
  is part of the assignment lifecycle, not a column-sync helper.

### Two-stage column drop plan

1. **Code stage (done, this pass).** Stop reading and writing
   `Class.supervisor_id`. The column still exists in the schema but is inert.
2. **Migration stage (deferred, separate deploy).** After the code stage has run
   in production and been verified, ship an Alembic migration that drops
   `classes.supervisor_id` (and its UNIQUE constraint). Do **not** drop it in the
   same release that stops using it — a rollback of the code stage would need the
   column back.

## 2. Authorization scoping (S2)

One canonical implementation lives in `dependencies.py`:

- `dependencies.ManagerScope` — `validate_manager`, `get_manager_kindergarten_id`,
  `assert_kindergarten_access`.
- `dependencies.require_manager` — FastAPI dependency for manager-only routes.

Policy:

| Caller | Access |
|---|---|
| ADMIN | any kindergarten |
| MANAGER / SUPERVISOR | their own kindergarten only |
| cross-tenant target | **404** (never 403 — do not leak that the resource exists) |
| non-admin with no kindergarten | 403 |

The former duplicates delegate to the canonical version:
`manager_scope.ManagerScope` re-exports it, `rbac.assert_manager_owns_kindergarten`
calls `assert_kindergarten_access` (this is the fix that turned cross-tenant 403
into 404), and `routers/manager.py` uses `require_manager`.

Left as-is on purpose: `validators.validate_manager_role` is a plain *role* check
used by ~12 non-manager files (supervisor/parent/safety/KPI/…). It is orthogonal
to kindergarten scoping and out of scope for this consolidation.

Deviation from the issue text: null-kindergarten stays **403** (not the suggested
400) so all manager routes agree with the existing `/api/manager/dashboard` and
`/api/absence-requests` guards; moving to 400 everywhere would require touching
the app-wide `validate_manager_role` callers.

## 3. Audit strategy (M1/M2 — deferred)

Two audit writes currently fire for a state-changing call: the domain-specific
handler audit and a generic `HTTP_<METHOD>` row from
`middleware/security.audit_state_changes_middleware`. Removing the middleware
write is an **app-wide** change (it audits every mutating `/api` call, not just
manager routes) and requires verifying handler-audit coverage across the whole
app first. It was therefore **deferred** to a dedicated effort rather than done
blind. `request.state.user_id` is already cached by `get_current_user_or_redirect`,
so the `_resolve_actor_id` DB re-query optimisation can piggyback on that when the
middleware change is done.

## 4. Indexes (D2/D3)

- **D2 (added).** `supervisor_assignments` had only its PK index while active-
  assignment lookups filter on `(class_id, deleted_at)` and
  `(supervisor_id, deleted_at)`. Added both composite indexes (model +
  migration `d4a2c1b8e6f0`); `EXPLAIN QUERY PLAN` confirms they are used.
- **D3 (already satisfied).** `attendance_logs` already carries
  `(child_id, date, status)` and `(class_id, date)`; a guard test locks them in.
  The issue's suggested `check_in_time` column does not exist (it is `date`).

## 5. Other correctness/perf fixes in this pass

- **S1** — CSV export neutralises formula injection (`=+-@`/TAB/CR) via a writer
  wrapper in `manager_analytics_endpoints.py`.
- **F1** — inline `on*` handlers removed from manager templates (XSS surface);
  behaviour is delegated listeners bound to `data-*` attributes.
- **F2** — manager pages authenticate via the httpOnly `kinjo_session` cookie plus
  the `X-CSRF-Token` double-submit token; no JWT is read from localStorage and no
  Bearer header is sent.
- **B1/B2** — attendance rate counts only PRESENT/LATE and divides by operating
  days from `OperatingCalendar` (not raw calendar days).
- **A3** — `get_manager_kpis` computes the enrollment rate once as
  active ÷ capacity (guarded), instead of calling the trend twice and returning a
  count.
- **B3** — forecast/anomaly use a batched `_compute_daily_attendance_rates`
  (≤ 5 queries) instead of one `compute_attendance_rate` call per day.

## 6. Deferred (require dedicated efforts)

- **CSP** hardening (drop `'unsafe-inline'` from `script-src`) — app-wide; every
  page with an inline `<script>` must be externalised with nonces/hashes first.
- **M1/M2** middleware audit dedup — app-wide audit-coverage review needed.
- **Phase 4** package consolidation (`manager/` package) — large refactor with no
  behaviour change; must preserve every route and response shape.
- **D1/B5 column DROP migration** — see the two-stage plan above.
