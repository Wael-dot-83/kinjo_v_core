# KinJo — Remediation Roadmap

**Source:** `docs/reports/COMPREHENSIVE_GAP_ANALYSIS.md` (2026-08-04)
**Prepared:** 2026-08-04
**Scope:** 42 classified findings (§1–§5) + 5 unclassified observations (§6) + 12 third-party services + 5 missing integrations.

---

## 0. Corrections to the source report

Verified against the codebase before planning. Three items in the source are inaccurate; do **not** open tickets for them as written.

| Ref | Report claim | Verified reality | Action |
|---|---|---|---|
| §1.11 | Heat Map ETL has "no Celery beat scheduler or cron integration" | **Resolved.** `celery_app.py:44-47` registers `regenerate-heatmap-dataset` → `heatmap_tasks.regenerate_daily_indicators`, `crontab(hour=17)` (17:00 UTC = 20:00 Jordan) | **Close as done.** Verify in staging only. |
| §5.5 | Heading: "Missing `python-json-logger` in Requirements" | **Present** at `requirements.txt:37` (`python-json-logger>=2.0,<4`). The body of the finding says so too — only the heading is wrong. The real issue is that `main.py:163-179` treats it as an optional fallback. | Re-scope to "make the structured-logging path deterministic" (OPS-05). |
| §Exec table | Role-Based Logic = **7** findings | **8** findings exist (§4.1–§4.8) | Counts below use 8. |

Also note: **§4.7 (audit trail for parent/child data access) is rated P3 in the source report.** The remediation request treats it as P1. This roadmap follows the **P1** instruction — the reasoning is sound (privacy-compliance traceability is a control, not a nicety) — but the reclassification is deliberate and flagged here so it is not mistaken for the report's own rating.

---

## 1. Prioritization Matrix

Domains: **SEC** (Security & Privacy) · **BE** (Backend/API) · **FE** (Frontend) · **DATA** (Data & Analytics) · **OPS** (DevOps/Infrastructure) · **QA** (Test & Docs)

### P1 — Blocks production

| ID | Domain | Finding | Source |
|---|---|---|---|
| **SEC-01** | SEC | Manager can infer another kindergarten's existence via 403-vs-404 divergence in predictive analytics | §4.1 |
| **SEC-02** | SEC | Admin dashboard aggregate cache is not kindergarten-scoped; a role-check bypass exposes all-kindergarten data | §4.2 |
| **SEC-03** | SEC | `google-genai==1.60.0` shipped but never imported — pure attack surface | §5.1 |
| **SEC-04** | SEC | No audit event for parent/child data access *(reclassified from P3 — see §0)* | §4.7 |
| **BE-01** | BE | `analytics_ws.py` — 6 of 12 exception handlers swallow errors silently | §1.1 |
| **BE-02** | BE | `communication_service.py` — 5 of 7 catch-alls suppress messaging failures with no audit trail | §1.2 |
| **BE-03** | BE | Fee Management / Billing module entirely absent | §2.1 |
| **FE-01** | FE | `admin_dashboard.js` has no 403 handler — permission denial surfaces as an unhandled error | §3.1 |

### P2 — Significant functional gaps

| ID | Domain | Finding | Source |
|---|---|---|---|
| **SEC-05** | SEC | Analytics explorer drilldowns accept `kindergarten_id` without verifying manager ownership | §4.4 |
| **SEC-06** | SEC | Password reset confirm path bypasses current-password verification | §4.8 |
| **BE-04** | BE | CSV import is synchronous; blocks above ~10K rows despite Celery being available | §1.6 |
| **BE-05** | BE | Notification service has no `DELIVERED` state — delivery unverifiable | §1.4 |
| **BE-06** | BE | Backup "validation" checks file shape only; never test-restores | §1.5 |
| **BE-07** | BE | Supervisor cannot progress incidents they reported (no follow-up workflow) | §4.5 |
| **BE-08** | BE | No bulk approval for daily reports — managers approve one at a time | §4.6 |
| **BE-09** | BE | Parent portal has no daily-report endpoint despite `SENT_TO_PARENT` status | §2.4, §4.3 |
| **BE-10** | BE | Staff Management module incomplete (no `Staff` model, CRUD, schedules) | §2.2 |
| **BE-11** | BE | Curriculum/lesson planning absent though `LearningDomain`/`MasteryLevel` enums exist | §2.3 |
| **BE-12** | BE | Fee payment tracking missing (`Payment` model, recording, history) | §2.5 |
| **DATA-01** | DATA | Predictive models have no persistence, versioning, or retraining pipeline | §1.3 |
| **FE-02** | FE | Plotly local fallback exists but is third in the chain and may be undeployed | §3.2 |
| **FE-03** | FE | `admin/messages/list.html` calls `GET /api/admin/messages`, which does not exist | §3.3 |
| **FE-04** | FE | Kindergarten import has no progress UI for long-running jobs | §3.4 |
| **OPS-01** | OPS | `supervisor==4.2.5` unused | §5.2 |
| **OPS-02** | OPS | `psutil==6.1.0` pinned behind security fixes | §5.3 |
| **OPS-03** | OPS | `numpy==2.4.2` strict pin risks resolver conflicts with pandas/scikit-learn | §5.4 |

### P3 — Consistency & optimisation

| ID | Domain | Finding | Source |
|---|---|---|---|
| **BE-13** | BE | Email service is a stub — no transactional send path | §1.7 |
| **BE-14** | BE | Health/medical records stored as free text, unmanageable | §2.6 |
| **BE-15** | BE | Staff scheduling absent | §2.7 |
| **BE-16** | BE | Export coverage thin (no daily reports, attendance, enrolments, messages) | §2.8, §1.12 |
| **BE-17** | BE | Error-response contract inconsistent between `admin_security.py` and `api/` | §6.3 |
| **BE-18** | BE | No rate limiting on parent-facing endpoints | §6.5 |
| **FE-05** | FE | CesiumJS CDN without SRI or local fallback | §3.5 |
| **FE-06** | FE | Governance reports page has no export action | §3.6 |
| **FE-07** | FE | Agency reports navigation inconsistent; location filter not wired everywhere | §3.7 |
| **FE-08** | FE | Observability dashboard shows no data-freshness indicator | §3.8 |
| **FE-09** | FE | Import-logs filters do not persist across navigation | §3.9 |
| **OPS-04** | OPS | Rate-limit storage is `memory://` — bypassable behind a load balancer | §1.10 |
| **OPS-05** | OPS | Structured JSON logging is best-effort, silently degrades to text | §5.5 |
| **OPS-06** | OPS | `/api/health` omits Redis, Celery broker, storage, external APIs | §6.4 |
| **QA-01** | QA | i18n extraction incomplete for admin strings | §1.8 |
| **QA-02** | QA | RTL verification is manual only | §1.9 |
| **QA-03** | QA | No exhaustive RBAC matrix test (4 roles × all endpoints, IDOR, escalation) | §6.1 |
| **QA-04** | QA | Parent API undocumented | §6.2 |

### Distribution

| Domain | P1 | P2 | P3 | Total |
|---|---|---|---|---|
| SEC | 4 | 2 | 0 | 6 |
| BE | 3 | 9 | 6 | 18 |
| FE | 1 | 3 | 5 | 9 |
| DATA | 0 | 1 | 0 | 1 |
| OPS | 0 | 3 | 3 | 6 |
| QA | 0 | 0 | 4 | 4 |
| **Total** | **8** | **18** | **18** | **44** |

---

## 2. Actionable Task List

Each task carries a Definition of Done that closes the gap rather than describing it.

### P1

---
**SEC-01 — Make cross-tenant denial indistinguishable in predictive analytics**

> As a platform operator, I need cross-tenant access attempts to return an identical response regardless of whether the target exists, so a manager cannot enumerate other kindergartens.

**Context (verified):** `main.py:1731+` raises `403 "Access denied to this kindergarten"`. `rbac.py:103-110` documents the canonical rule: *"a cross-tenant target returns 404 (not 403) so we never reveal that another kindergarten's resource exists."* The four `/api/analytics/predict/*` endpoints violate it.

**DoD**
- All four predict endpoints (`attendance`, `incidents`, `capacity`, `enrollment`) delegate to `rbac.assert_manager_owns_kindergarten()` / `ManagerScope.assert_kindergarten_access()`.
- A manager requesting a kindergarten that **exists but is not theirs** and one that **does not exist** receive byte-identical status, body, and headers.
- Response timing difference between the two cases is not statistically distinguishable over 100 paired requests.
- Test added to `tests/test_admin_authz_sweep.py` (or a new IDOR suite) asserting both cases return 404.
- No remaining `403` for cross-tenant kindergarten targets: `grep -rn "Access denied to this kindergarten"` returns zero hits.

---
**SEC-02 — Scope the admin dashboard cache by tenant**

> As a security engineer, I need aggregate dashboard data to be unreachable by non-admin roles even if a route guard is misconfigured, so a single middleware error is not a full data breach.

**Context:** `admin_endpoints.py:89` builds a cache key from `day + period` with no tenant component (§4.2).

**DoD**
- Cache key includes role and kindergarten scope; an admin-scope entry can never be served to a manager/supervisor request.
- Defence in depth: the handler re-asserts role **inside** the function, not only via the dependency.
- Regression test: a SUPERVISOR token against `/api/admin/dashboard` returns 403 **and** the response contains no aggregate figures, with the admin cache pre-warmed.
- Cache poisoning check: warming the cache as admin then requesting as supervisor yields no admin data.

---
**SEC-03 — Remove the unused `google-genai` dependency**

> As a security engineer, I need to eliminate shipped-but-unused packages, so we are not exposed to CVEs in code we never call.

**Context (verified):** `requirements.txt:26` pins `google-genai==1.60.0`. A repo-wide search finds **zero** imports — the only mention is a documentation generator string. `GOOGLE_API_KEY` exists in `config.py:79` but nothing reads it for this SDK.

**DoD**
- `google-genai` removed from `requirements.txt`.
- `GOOGLE_API_KEY` removed from `config.py` and all `.env*` templates **or** documented as reserved with an explicit "unused today" comment.
- `pip install -r requirements.txt` in a clean venv succeeds; full suite green.
- `pip-audit` re-run; the dependency count drops and no new advisory appears.
- ADR or changelog entry records why it was removed, so it is not reinstated by habit.

---
**SEC-04 — Audit trail for parent/child data access** *(reclassified P3→P1)*

> As a data protection officer, I need every read of parent or child personal data attributed to an actor and timestamp, so we can answer "who saw this child's record?".

**DoD**
- New `AuditAction` constants (e.g. `PARENT_DATA_VIEWED`, `CHILD_DATA_ACCESSED`) in `audit_actions.py` — no raw strings, per `CLAUDE.md`.
- Every read path returning parent/child PII emits `log_audit_event()` with actor, target ids, and correlation id.
- Read auditing does **not** log PII values themselves — ids and counts only.
- Volume assessed: high-traffic list endpoints log one event per request, not per row.
- Test asserts an event row exists after a manager opens a child record, and that the payload contains no free-text PII.
- Retention/rotation for the increased audit volume documented in `RUNBOOK.md`.

---
**BE-01 — Harden `analytics_ws.py` exception paths**

**DoD**
- All 12 handlers either act on the error or carry a comment stating why swallowing is correct; none is silent.
- Every caught exception logs with correlation id at an appropriate level.
- Client receives a typed error frame on failure rather than a silently dead socket.
- Test simulates a downstream failure and asserts both a log record and a client-visible error frame.

---
**BE-02 — Harden `communication_service.py` exception paths**

**DoD**
- All 7 catch-alls refined; send/compose/deliver failures raise or return a typed error.
- Failed admin message delivery writes an audit event.
- Test: forced delivery failure produces a non-2xx to the caller **and** an audit row.

---
**BE-03 — Fee Management / Billing module**

> As a kindergarten manager, I need to record and track fee payments, so outstanding balances are visible without a spreadsheet.

**DoD**
- `Fee`/`Invoice`/`Payment` models with Alembic migration (single head maintained).
- CRUD API under `/api/admin/fees/*` and `/api/manager/fees/*`, all behind `require_admin` / manager scope.
- Balance calculation covered by unit tests including partial and overpayment.
- Every state change emits an audit event using `AuditAction` constants.
- Money stored as integer minor units or `Numeric` — **not** float. *(Note: `Kindergarten.registration_fees`/`monthly_fees` are currently `Float`; migrating them is in scope.)*
- Bilingual UI per the `ui_lang` guard; no mixed-language rendering.

---
**FE-01 — Handle 403 in the admin dashboard client**

**DoD**
- `static/js/admin_dashboard.js` handles 401 (redirect), 403 (permission-denied panel), and 5xx (retry affordance) distinctly.
- Denial message is bilingual and contains no internal detail.
- Test/manual check: a non-admin session renders the permission panel, not a console error.

### P2 — abbreviated (full DoD pattern as above)

| ID | Story | Key DoD |
|---|---|---|
| SEC-05 | Enforce manager ownership on analytics drilldowns | Every `kindergarten_id` parameter in `analytics_explorer.py` routed through `ManagerScope`; cross-tenant → 404; test per drilldown |
| SEC-06 | Require current password on all self-service changes | `password-reset-confirm` either consumes a single-use emailed token **or** verifies current password; session-only change impossible; test both |
| BE-04 | Move CSV import to Celery | >10K-row file returns a job id immediately; status endpoint; no request timeout; failure leaves no partial import |
| BE-05 | Delivery confirmation | `DELIVERED` added to `NotificationStatus` + migration; per-channel callback; admin can see delivery state |
| BE-06 | Real backup restore verification | Scheduled job restores to a throwaway database and asserts row counts/checksums; failure alerts; result visible to admins |
| BE-07 | Supervisor incident follow-up | Supervisor can move OPEN→UNDER_INVESTIGATION, add notes, and close **only** incidents they reported; audited; cross-tenant → 404 |
| BE-08 | Bulk daily-report approval | `POST /api/admin/daily-reports/bulk-approve`; partial-failure report; one audit event per report; idempotent |
| BE-09 | Parent daily-report access | `GET /api/parent/daily-reports` scoped to own children, `SENT_TO_PARENT` only; parent-facing page; IDOR test |
| BE-10 | Staff management | `Staff` model + CRUD + employment records; separated from auth users; audited |
| BE-11 | Curriculum module | Lesson plans + activity tracking keyed to existing `LearningDomain`/`MasteryLevel`; progress reporting |
| BE-12 | Fee payment tracking | Depends on BE-03; payment recording, history, outstanding balance |
| DATA-01 | Model persistence & versioning | Models serialised with version + metrics; `GET /models`, `POST /models/{id}/retrain`, `GET /models/{id}/performance`; rollback possible |
| FE-02 | Deterministic chart assets | Local vendored Plotly is the **primary** source; CDN optional; build fails if the asset is absent |
| FE-03 | Fix messages-list API mismatch | Either implement `GET /api/admin/messages` or repoint the client; contract test binds template to route |
| FE-04 | Import progress UI | Progress reflects real server-side state (pairs with BE-04); cancel or safe-abandon; no frozen-looking screen |
| OPS-01 | Drop `supervisor` package | Removed; clean install; deployment docs updated if it was assumed |
| OPS-02 | Upgrade `psutil` | Moved to a supported patched release; `performance_monitor.py`/`monitoring_service.py` verified; suite green |
| OPS-03 | Relax the `numpy` pin | Compatible range instead of `==`; resolves cleanly with `pandas`/`scikit-learn`; lockfile regenerated |

### P3 — grouped

- **Backend:** BE-13 email transport · BE-14 structured health records · BE-15 staff scheduling · BE-16 export coverage (+PDF) · BE-17 unify error contract · BE-18 parent-endpoint rate limits
- **Frontend:** FE-05 Cesium SRI + fallback · FE-06 governance export · FE-07 agency navigation · FE-08 freshness indicators · FE-09 filter persistence
- **Infrastructure:** OPS-04 Redis rate-limit backend · OPS-05 deterministic JSON logging · OPS-06 full health check
- **Quality:** QA-01 i18n extraction · QA-02 automated RTL checks · QA-03 RBAC matrix suite · QA-04 parent API docs

> **QA-01 partially addressed:** 19 untranslated Latin msgids and 27 English screen-reader labels were localised on 2026-08-04; the Arabic catalogue now holds 259 entries. Remaining scope is the admin-module string extraction described in §1.8.

---

## 3. Dependency & Infrastructure Plan

### 3.1 The 12 third-party services (§9)

| # | Service | Tier | Status today | Gate to close |
|---|---|---|---|---|
| 1 | **SMTP / email provider** | Required | **Stub** — no send path | Provider chosen, credentials in secrets, password-reset delivered end-to-end, bounce handling |
| 2 | **Redis** | Required | Configured, **not enforced** | Production instance with persistence + auth; app fails fast if absent in prod; used for cache, rate limit, pub/sub |
| 3 | **PostgreSQL** | Required | Configured, **not enforced** | Managed instance, backups + PITR, migrations applied, SQLite refused when `ENVIRONMENT=production` |
| 4 | **CDN assets** (Bootstrap, USWDS, Plotly, Cesium, Chart.js, SweetAlert2) | Required | Mixed: SRI on SweetAlert2, local fallback only for Plotly | All vendored locally as primary; CDN optional; SRI on any remaining CDN tag; CSP updated |
| 5 | Google AI API | Optional | **Unused** | Covered by SEC-03 — remove now, reintroduce with a real use case |
| 6 | S3 / object storage | Optional→Required for multi-instance | Not used | Needed before horizontal scaling; local disk does not survive redeploy |
| 7 | Monitoring / Grafana + alerting | Optional | Prometheus metrics exist, no dashboards or alerts | Dashboards for the golden signals; alert routes; on-call runbook |
| 8 | **SMS gateway** | Missing integration | None | Provider + template catalogue + opt-out + delivery receipts |
| 9 | **Push notifications** (FCM/APNs) | Missing integration | `PUSH` enum value with no provider | Provider wired; device-token lifecycle; pairs with BE-05 |
| 10 | **PDF generation** | Missing integration | None | Library selected; Arabic **RTL shaping verified** — most engines need explicit font embedding for Arabic |
| 11 | **Virus scanning** | Missing integration | `virus_scan_service.py` is a stub | Real engine wired; infected upload rejected + audited; failure mode is *fail-closed* |
| 12 | **CAPTCHA provider** | Missing integration | `captcha_service.py` needs config | Keys configured; enabled on login/registration/forgot-password/contact; accessible fallback |

The **5 missing integrations** are #8–#12.

### 3.2 Dependency-risk sub-tasks

- [ ] **DEP-01** Remove `google-genai` (SEC-03) — unused, P1 attack surface.
- [ ] **DEP-02** Remove `supervisor==4.2.5` (OPS-01) — unused; confirm no deploy script assumes it.
- [ ] **DEP-03** Upgrade `psutil` off 6.1.0 (OPS-02); re-run `pip-audit`.
- [ ] **DEP-04** Replace `numpy==2.4.2` with a compatible range (OPS-03); verify resolution against `pandas==3.0.0` and `scikit-learn>=1.5,<2`.
- [ ] **DEP-05** Make structured logging deterministic (OPS-05) — `python-json-logger` **is** present at `requirements.txt:37`; either make the import hard or log a startup warning when falling back, so the format is never silently text in production.
- [ ] **DEP-06** Introduce a lockfile (`uv.lock` exists — adopt or replace with `pip-compile`) so environments are reproducible.
- [ ] **DEP-07** Add `pip-audit` to CI as a gate. *(Baseline 2026-08-03: only `ecdsa` — unreachable under HS256 + `python-jose[cryptography]` — and build-time `pip` advisories.)*
- [ ] **DEP-08** Audit the JavaScript dependency tree — never assessed.

---

## 4. Security Remediation (P1 detail)

### 4.1 SEC-01 — Information leakage via error codes

**Verified, not assumed.** `rbac.py:103-110` states the rule in its own docstring; the predict endpoints break it.

The subtle part: **changing the status code is necessary but not sufficient.** Enumeration also leaks through response timing and body shape. A "does not exist" path that short-circuits early is measurably faster than one that loads a record and then denies. The DoD therefore requires identical bodies *and* indistinguishable timing.

**Order:** fix `enrollment` first (it takes the widest parameters), then the other three; add the IDOR test before the fix so it fails first.

### 4.2 SEC-02 — Admin dashboard scope

Treat the role guard as fallible by design. The finding's own phrasing — "if a supervisor *somehow* bypasses the role check" — is exactly the assumption worth removing: put the tenant in the cache key so a bypass yields nothing useful.

### 4.3 SEC-03 — `google-genai` attack surface

Confirmed unused by repo-wide search. This is the cheapest P1 on the list: delete the line, reinstall, run the suite. Do it first — it is the only P1 with no design decisions attached.

Two follow-ons: remove `GOOGLE_API_KEY` so no operator provisions a secret for nothing, and record the decision so the package is not reinstated.

### 4.4 SEC-04 — Audit trails

Two failure modes to avoid:

1. **Auditing the payload.** Log ids and counts, never the PII itself, or the audit log becomes a second copy of the data it protects.
2. **Volume collapse.** A per-row event on a list endpoint will flood the table. One event per request, with a count.

Pairs naturally with BE-02, which needs an audit trail for failed message delivery.

### 4.5 Sequencing note

SEC-01 and SEC-05 are the same class of defect (tenant scoping on a `kindergarten_id` parameter) in two modules. Fix SEC-01 first, extract the pattern into a shared dependency, then apply it to SEC-05 — otherwise the same bug is fixed twice, differently.

---

## 5. Implementation Sequence

### Wave 0 — Immediate (days)
Cheap, isolated, no design debate.
1. **SEC-03 / DEP-01** remove `google-genai`
2. **OPS-01 / DEP-02** remove `supervisor`
3. **Close §1.11** — heat map scheduling already shipped; verify in staging
4. **DEP-07** add `pip-audit` to CI

*Exit:* dependency count down, clean install, suite green, CI gate live.

### Wave 1 — P1 security (1–2 sprints)
5. **QA-03 (partial)** write the failing IDOR/RBAC tests **first**
6. **SEC-01** cross-tenant 404 parity → extract shared scope dependency
7. **SEC-05** apply that dependency to analytics drilldowns *(promoted from P2 — same defect class, marginal extra cost here, far more expensive later)*
8. **SEC-02** tenant-scoped dashboard cache
9. **SEC-04** audit trail for parent/child access
10. **SEC-06** password-change verification

*Exit:* no cross-tenant enumeration by code, body, or timing; PII access attributable.

### Wave 2 — P1 stability (1–2 sprints)
11. **BE-01** analytics WebSocket error paths
12. **BE-02** communication service error paths + delivery audit
13. **FE-01** 403 handling in the dashboard client

*Exit:* no silent failure paths in real-time or messaging.

### Wave 3 — Infrastructure prerequisites (1 sprint, parallelisable)
14. **OPS-04** Redis rate-limit backend · **OPS-06** full health check · **OPS-05/DEP-05** deterministic logging
15. **DEP-03/04** dependency upgrades · **DEP-06** lockfile
16. **Service #1** SMTP provider — unblocks BE-13 and BE-05
17. **Service #4** vendor CDN assets locally — closes FE-02 and FE-05 together

*Why here:* several P2 items depend on these. Async import (BE-04) needs a reliable broker; delivery confirmation (BE-05) needs a real email transport.

### Wave 4 — P1 functional + P2 (2–4 sprints)
18. **BE-03 → BE-12** fee management, then payment tracking (strict order — payments depend on the fee model)
19. **BE-04** async CSV import + **FE-04** progress UI (ship together; a progress bar with no server-side job is theatre)
20. **BE-09** parent daily reports *(highest user-visible value in this wave)*
21. **BE-07** supervisor incident follow-up · **BE-08** bulk approval
22. **BE-05** delivery confirmation · **BE-06** restore verification
23. **FE-03** messages API mismatch · **DATA-01** model versioning
24. **BE-10/BE-11** staff management, curriculum

### Wave 5 — Missing integrations (parallel with Wave 4)
25. **#10 PDF generation** first — unblocks BE-16, FE-06, and §1.12 agency PDF export. **Verify Arabic RTL shaping during selection, not after.**
26. **#11 virus scanning** (fail-closed) · **#12 CAPTCHA**
27. **#8 SMS** · **#9 push** — both pair with BE-05
28. **#6 S3** — required before horizontal scaling; **#7** Grafana/alerting

### Wave 6 — P3
29. Frontend polish (FE-06…FE-09) · Backend consistency (BE-13…BE-18) · Quality (QA-01…QA-04)

### Sequencing rules
- **Tests before fixes** for every security item — a security fix without a failing test first proves nothing.
- **BE-03 before BE-12**; **BE-04 with FE-04**; **service #10 before BE-16/FE-06**; **SMTP before BE-05/BE-13**.
- **Do not** start Wave 4 functional modules before Wave 1 completes — new endpoints inherit the scoping defect the shared dependency is meant to fix.

---

## 6. Caveats

- **Effort is not estimated.** Sequencing reflects dependency order and risk, not story points; size them against your team's velocity.
- **Findings are as reported**, except the three corrected in §0 and the items verified inline (SEC-01, SEC-03, OPS-01). The remaining findings were **not** independently re-verified against the codebase — §0 shows the report already contains stale and self-contradicting entries, so **spot-check each ticket before committing to it.**
- **§6.1–§6.5 were unclassified** in the source; assigned here as QA-03, QA-04, BE-17, OPS-06, BE-18.
- **§4.7 was promoted P3→P1** on instruction, not on the report's own rating.
