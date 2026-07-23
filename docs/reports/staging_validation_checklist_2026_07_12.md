# Staging Validation Checklist — Release Candidate

**Purpose:** capture the evidence required to promote from **CONDITIONAL GO** → **FULL GO**.
**Rule:** each gate passes only with a named **owner**, **timestamp**, exact **command/test case**, **expected** and **actual** result, supporting **evidence** (logs/screenshots/exports), and **no unresolved critical/high finding**.

**Release candidate:** `<commit SHA of merged main after PR #47 + #42>`
**Staging env:** `<url / compose ref>`  ·  **Signed off by:** `<name>`  ·  **Date:** `<yyyy-mm-dd>`

> Pre-req (steps 1–2): PR #47 merged, PR #42 marked ready + merged, complete suite + `pip-audit` re-run against the merged RC (attach results below).

| # | Gate | Command / test case | Expected | Actual | Owner | Timestamp | Evidence | Result |
|---|------|---------------------|----------|--------|-------|-----------|----------|--------|
| RC-0 | Full suite on RC | `python -m pytest -q` | 0 failed | | | | log | ☐ |
| RC-0b | pip-audit on RC | `pip-audit` | 0 high/critical (ecdsa accepted) | | | | export | ☐ |
| S-1 | Celery worker + scheduled tasks | start worker+beat; enqueue a task; force a failure | task runs; retry/backoff; failure handled, not lost | | | | worker log | ☐ |
| S-2 | SMTP delivery + failure | trigger a real email; then point to a bad host | delivered on success; graceful handling + audit on failure | | | | inbox + log | ☐ |
| S-3 | MFA lifecycle | enroll → login → recovery → lockout → backup codes | each step works; lockout enforced; codes single-use | | | | screenshots | ☐ |
| S-4 | Google-Maps heatmap | load heatmap with production-restricted key | tiles render; key restricted to prod origin | | | | screenshot | ☐ |
| S-5 | Role journeys | Admin, Manager, Supervisor, Parent end-to-end | each role's core flow works; no cross-tenant leakage | | | | screenshots | ☐ |
| S-6 | Docker Compose | `docker compose up` cold; `restart`; kill+recover | clean start; healthy after restart; recovers | | | | compose log | ☐ |
| S-7 | TLS / hosts / CORS / secrets | inspect cert chain; trusted-hosts; CORS; secret isolation | valid chain; only allowed hosts/origins; no secret in image/logs | | | | scan output | ☐ |
| S-8 | Health / readiness probes | hit `/api/health` (+ readiness) under load | correct status; used by orchestrator | | | | curl output | ☐ |
| S-9 | Backup + restore | take backup; restore to a fresh DB; verify integrity | restore succeeds; row counts + spot checks match | | | | dump + verify log | ☐ |
| S-10 | Monitoring / alerting | trigger an alert condition | alert fires; notification delivered to on-call | | | | alert + notification | ☐ |

## Sign-off
- [ ] All gates ☑ with complete evidence
- [ ] Risk register (`release_risk_register_2026_07_12.md`) reviewed; residuals accepted with owners
- [ ] Final RC commit SHA recorded: `__________`
- [ ] **Immutable release tag created:** `v__________`
- [ ] Promotion decision: **FULL GO** / hold
