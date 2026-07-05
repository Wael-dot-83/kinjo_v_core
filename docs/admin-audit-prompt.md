# Elite Admin Audit Prompt

Reusable task spec for a full security/QA audit of admin-facing routes in
the KinJo Admin System (or a similarly structured Flask/FastAPI admin
panel). Copy this into a fresh session to kick off another full-panel
audit pass.

## Scope

All routes in `frontend.py` that start with `/admin/`.

Explicitly excluded (do not touch without checking first): any page
noted as currently under active work by another agent — check
`git status --short` for untracked/modified files outside your own
edits before starting, and treat those pages as off-limits.

## Audit checklist (per page)

### 1. Functionality & data correctness
- Verify every table, list, and detail view displays correct data from the database.
- Check pagination wiring: `page`, `page_size`/`per_page`, and filter params are passed and handled correctly end-to-end (frontend → endpoint → response).
- Validate batch operations (e.g., governorate resolution, reminders, status updates) for correctness and performance — no N+1 queries; batch with `.in_()` or `GROUP BY` + `func.count()`.
- Confirm computed fields (e.g., missing-reports counts) are accurate and update on relevant actions.

### 2. UI/UX consistency
- Table `<caption>` and `scope="col"` present for accessibility (WCAG 2.1 AA).
- Column headers correctly labeled — verify against what the row-rendering code actually populates, not just what the header text claims.
- Breadcrumbs present, functional, not duplicated; confirm the template block name is one the base layout actually declares (a mismatched block name renders nothing, silently).
- Modals, buttons, and forms have proper ARIA labels and keyboard navigation.

### 3. Security & session management
- **Critical**: review any impersonation endpoints. Confirm session tokens/state are properly scoped and invalidated when impersonation ends, and that permission checks are enforced on every impersonated action.
- If a critical session-security gap is found, **document it and escalate to the stakeholder before fixing** — this class of change can have a large blast radius and deserves an explicit go/no-go, not a unilateral fix.
- Scan for endpoints leaking sensitive data in URLs, query strings, or error messages.

### 4. Error handling & feedback
- Audit every call site of the shared authenticated-fetch helper for proper error handling — confirm it surfaces the real backend error body (structured error envelope, `detail` string, or Pydantic validation array) rather than a generic status-text fallback.
- If a fix here touches many call sites, treat it as its own escalation: confirm scope (fix everywhere vs. fix locally vs. document only) with the stakeholder before proceeding.
- Forms display validation errors and success messages clearly.

### 5. Testing & coverage
- Write new unit/integration tests for every modified page/endpoint.
- Run the full suite and confirm zero regressions before each commit.
- Cover edge cases: empty states, malformed input, permission denied.

## Working method

- Verify claims directly (don't trust a sub-agent's report at face value) before fixing.
- Live-verify fixes in a running dev server, not just via unit tests.
- Self-verify each fix: revert it, confirm the new regression test fails for the *right* reason, restore it, confirm the test passes again.
- Commit per page (or per logical group of pages), with a descriptive message explaining the *why*, not just the *what*.
- Escalate via an explicit question (not a unilateral decision) when a finding is either a core security/session gap or has a blast radius spanning many files/call sites.
- Keep a running index memory/doc of recurring bug classes found — they tend to repeat across pages and speed up later audits.

## Deliverables

- A per-page account of what was found and how it was resolved (fixed, or documented-only with the reason).
- Incremental, logically-scoped commits.
- Tests covering every fix.
- A final summary: pages audited, commits made, critical findings and their disposition, and anything explicitly left out of scope.

## Reference: prior completed run (2026-07-06)

- **Coverage**: 48 admin pages (18-page series + 30-page extended series), all `/admin/...` routes in `frontend.py` except `/admin/heatmap` and `/admin/daily-reports-organization` (left for a concurrent agent).
- **Last commit**: `eb0cb3d` — Governance Reminders page: pagination wiring, batched governorate resolution (kindergarten + supervisor-via-kindergarten), computed missing-reports count, relabeled a mislabeled column, removed a dead breadcrumb block, added table caption/scope.
- **Escalations**:
  - Impersonate page — critical session-security gap, documented only per stakeholder decision (no `SessionMiddleware` anywhere; the feature logs a fake-success audit event while doing nothing).
  - `fetchWithAuth` — site-wide bug discarding backend error bodies across ~55 call sites in 13 files; fixed full-scope per stakeholder approval.
- **Tests**: full suite grew from ~2660 to 2815 tests over the series, always green before each commit.
