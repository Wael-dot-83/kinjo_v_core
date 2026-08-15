# Parent Module — Production-Readiness Report

- **Date:** 2026-08-15
- **Branch:** `fix/parent-module-production-readiness`
- **Worktree:** `.claude/worktrees/parent-prod-readiness`
- **Agent-Run-ID:** `kilo-parent-prod-20260815`
- **Plan:** `.kilo/plans/1786685448607-parent-module-production-readiness.md`

## Verdict: PRODUCTION READY

All four passes agree: implementation, broad-sweep findings (the plan), an
independent adversarial review (fresh subagent, no prior context), and the
test/static-analysis automation.

## Scope delivered

### P1 — Correctness (both fixed)
1. **Dashboard multi-enrollment collapse** — `parent_service.build_dashboard_payload`
   now groups every in-flight enrollment per child (`group_enrollments_by_child`),
   returns the full `enrollments` list additively, and keeps the legacy
   single-enrollment `enrollment` key via `pick_primary_enrollment`
   (ACTIVE > PENDING_REVIEW > WAITLISTED, newest id first). Mobile/web shapes unchanged.
2. **`parent_login_frequency` stub** — now computes `total_parents`, `active_parents`
   (from `User.last_login_at`), `total_logins` (from `AuditLog` `LOGIN_SUCCESS`),
   `avg_logins_per_parent`, `active_rate`, and a real `high/moderate/low/no_data`
   classification. Kindergarten scoping uses the correct
   ParentProfile → Child → EnrollmentApplication join. The fabricated
   `"unknown"` metric surfaced by `/api/observability/parent-engagement` is gone.

### P2 — Performance
3. **Pagination** — `/api/parent/enrollments`, `/api/parent/attendance`,
   `/api/parent/daily-reports` accept opt-in `page`/`page_size` (max 100). With no
   params the full list is returned unchanged, preserving the mobile contract;
   `pagination` metadata is additive and only present when `page` is supplied.
4. **Caching** — parent dashboard cached 60s per user (invalidated on profile save);
   engagement metrics cached 300s keyed by `(kindergarten_id, days)`. Both skip the
   cache under `settings.TESTING` so tests stay deterministic.
5. **Imports** — all mid-function imports moved to module top in `api/parent.py`.

### P2 — Architecture
6/13. **`get_current_parent` dependency** (`dependencies.py`) enforces the PARENT role
   and resolves the profile in one place, returning a `ParentIdentity`; all 8 parent
   endpoints now use it and no inline role guard remains.
9. **`parent_service` layer** — dashboard assembly, enrollment grouping and
   primary-enrollment selection moved out of the route handler.
8. **`async def` conversion — deliberately NOT done.** Every handler in `api/`
   (172 of 172) is a sync `def`; converting sync SQLAlchemy handlers to `async def`
   would block the event loop. This deviation is documented in the commit.
7. **Pydantic `response_model` — deferred (documented).** Response shapes are a hard
   mobile-compat contract; attaching schemas adds a `ResponseValidationError` surface
   without fixing a defect. Tracked as follow-up.

### P2/P3 — Security
14. **Phone validation** consolidated into `_normalize_phone_or_raise` (primary +
   emergency paths share one validator).
15. **Rate limiting** on `PUT /api/parent/profile` via the shared slowapi limiter with
   new `RATE_LIMIT_PARENT_WRITE` (10/minute); the limiter is disabled under TESTING.
- **Latent CSRF bug fixed:** the inline `getHeaders()` in all parent templates fell
  back to a regex for a nonexistent `kinjo_csrf` cookie, so cookie-auth state-changing
  requests could not supply the double-submit header. `parent-common.js` now resolves
  the token from the `kinjo_csrf_token` cookie / `csrf-token` meta, matching
  `middleware/csrf.py`.

### P2 — Frontend UX
10. **Inline CSS extracted** — the ~310-line `<style>` block in
   `templates/parent/profile.html` moved to `static/css/parent-profile.css`
   (`?v=1.0` cache-bust). The Jinja RTL/LTR gradient branch became a
   `--profile-hero-pos` custom property overridden by `[dir="rtl"]`, preserving behavior.
11. **Shared JS** — `static/js/parent-common.js` provides the single `IS_EN`, `T()`,
   `escHtml()`, `getHeaders()` implementation; the duplicated inline copies were removed
   from `parent/children`, `attendance`, `enrollments`, `profile` and `dashboard/parent`.
12. **Status labels single-sourced** — backend returns additive `status_en` alongside
   `status_ar`; the children/enrollments pages prefer the API labels with the local
   `STATUS_LABEL` map kept only as a fallback.

### P3 — Maintainability
16/17. **Return type hints** added to all parent handlers and service methods;
   regression tests added for the multi-enrollment dashboard, login-frequency
   (empty/populated/scoped/observability), pagination boundaries and backward
   compatibility, bilingual status labels, shared-asset serving, and helper dedup.

## Validation evidence (commands run in the worktree)

| Check | Result |
|---|---|
| `python -m py_compile` (api/parent.py, parent_service.py, parent_engagement_service.py, dependencies.py, config.py) | PASS |
| `ruff check` (all changed Python files) | All checks passed |
| `pytest tests/test_parent_module.py tests/test_parent_module_regressions.py tests/test_parent_module_comprehensive_audit.py` | **83 passed** |
| `pytest tests/test_frontend.py tests/test_language_zero_mix_routes.py` | **332 passed** |
| `pytest tests/test_route_registration.py tests/test_csrf_double_submit_contract.py tests/test_frontend_api_paths_resolve.py` | **26 passed** (incl. no duplicate `(method,path)` routes) |
| `pytest tests/test_wave3_observability.py tests/test_kpi_service.py` | **36 passed** |
| `pytest tests/test_analytics_gap.py tests/test_government_apis.py tests/test_reports_preview_engine.py` | **109 passed** |

Total parent-module and collateral suites: **586 tests passing**, 0 failures.

## Independent adversarial review
A fresh subagent (no implementation context) re-read the code and returned
**PRODUCTION READY** with **no BLOCKING or MAJOR findings**. Its two MINOR findings:
- Wizard step cookie regex (fixed in commit `fix(parent): wizard CSRF cookie fallback…`).
- Inline phone validation in non-parent modules (out of scope; item 14 targeted the
  duplicated pair inside `api/parent.py` only).

## Backward compatibility
No existing response key was removed or renamed. Additive keys only:
`enrollments[]` (dashboard child), `status_en` (children/enrollments/dashboard),
`total_logins`/`active_rate` (engagement), `pagination` (list endpoints, only when
`page` is supplied). Mobile (`mobile/lib/core/api/api_endpoints.dart` consumes
`dashboard` and `children`) is unaffected.

## Follow-ups (deferred, documented)
- Attach Pydantic `response_model` schemas to parent endpoints (item 7).
- Real-time updates (WebSocket/SSE) — feature, not a defect (plan).
- Consolidate phone validation across non-parent modules.
- Retire `scripts/compat/frontend_orig.py` legacy parent page routes.
