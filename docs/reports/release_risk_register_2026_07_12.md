# Release Risk Register — 2026-07-12

**Release verdict:** CONDITIONAL GO / PUBLIC-LAUNCH NO-GO
**Baseline:** `origin/main` frozen at `bd17d84` (release changes isolated in unmerged branches/PRs).
**Local evidence:** full suite 3046 passed / 0 failed / 1 xfailed; axe-core 0 violations (WCAG 2 A/AA, 4 pages); pip-audit 0 high/critical app deps; Alembic empty→head + downgrade→re-upgrade pass on SQLite and PostgreSQL 16.

## Accepted residual risks

| ID | Finding | Severity | Status | Rationale | Owner | Review-by |
|----|---------|----------|--------|-----------|-------|-----------|
| R-1 | `ecdsa 0.19.2` — PYSEC-2026-1325 (timing side-channel) | Medium | **Accepted** | Transitive (via `python-jose`); **no published fix**; code path **not exercised** — JWTs are signed with **HS256/HMAC** (`config.ALGORITHM="HS256"`), which never invokes ECDSA. Re-evaluate if signing alg changes or a fix ships. | _TBD_ | Next dep review |
| R-2 | bandit B608 (SQL built with string formatting) ×5 | Medium | **Accepted / monitor** | Occurrences are in Alembic migrations + `database.py` health/pool queries and heatmap ETL — parameters are not user-controlled. Prefer parameterized/`text()` binds where feasible. | _TBD_ | Next security pass |
| R-3 | bandit B108 (hardcoded temp dir) — `export_tasks.py` | Low | **Accepted / monitor** | Server-controlled export path; confirm perms + cleanup in production container. | _TBD_ | Pre-launch |

## Resolved this cycle (evidence in PR #47)

| Finding | Resolution | Commit |
|---|---|---|
| Pillow 11.3 — 7 CVEs | Upgrade to 12.3 (`Pillow>=12.2,<13`) | PR #47 |
| bleach 6.1 — 2 CVEs | Upgrade to 6.4.0 | PR #47 |
| pip 25.2 — 6 CVEs | Upgrade venv pip to 26.1.2 (installer only, not shipped) | n/a (env) |
| WCAG color-contrast (load-timer badge, ~2.93:1) | Solid `#146c43` (~5.4:1) | PR #47 |
| WCAG scrollable-region-focusable (`#activity-feed`) | `tabindex=0` + `aria-label` | PR #47 |
| PG migration reversibility (enum not dropped) | `DROP TYPE immunizationageunit` on downgrade | `33264c0` (in `bd17d84`) |
| Duplicate `GET /api/admin/kindergartens/stats` | Removed shadowed handler | `bd17d84` |

## Launch-blocking, NOT yet verified (require staging — see staging checklist)
Celery/scheduled tasks · SMTP · MFA (enroll/login/recovery/lockout/backup-codes) · Google-Maps prod key · Admin/Manager/Supervisor/Parent journeys · Docker-Compose cold start/restart/recovery · TLS/trusted-hosts/CORS/secret isolation · health & readiness probes · DB backup + restore · monitoring/alerting delivery.

**Promotion to FULL GO requires** every staging gate to have a named owner, timestamp, exact command/test, expected vs actual result, supporting evidence, and no unresolved critical/high finding.
