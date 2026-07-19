# KinJo Admin Module — Implementation Plan

**Scope source:** `claude_code_kinjo_agency_reports_ux_logo_master_prompt.md`
**Companion artifact:** `traceability_matrix.md` (requirement-by-requirement evidence)

This plan organizes the remaining `Planned` work into isolated, non-overlapping workstreams. All `Implemented/Already-compliant` items in the matrix require **verification only** (no code change) and are therefore owned by the workstream that touches the same surface, but marked "verify, do not change" unless a delta is called out.

> **Hard protection rules (from master prompt) remain in force:** do not touch `D:\Final Version` dirty WIP, `D:\Final Version-loc29` (#29), or #26/#20 work; do not run migrations with `--apply`; do not expose PII; do not invent a logo (asset `static/img/kinjo-logo.png` already exists); keep scope clean of unrelated files (`.claude`, `.kilo`, DB, screenshots, logs).

---

## 1. Workstreams (isolated, non-overlapping)

| WS | Name | Owns | Touches (read-only verify) |
|---|---|---|---|
| **W1** | Agency Index & Cards UX | `/admin/agency-reports` index page: card structure, logo sizing, summary widgets, custom-builder labels, status/button/empty states, tabs/a11y | `agency_reports_registry.py` (labels), `api/agency_reports_api.py` (`/summary`) |
| **W2** | Report Pages & KG2 | All `/admin/agency-reports/{agency}/{report}` pages, KG2 eligibility filters/cascade/results/exports, chart export, report perf | `agency_reports_service.py`, `agency_report_location_filter.js`, `api/agency_reports_api.py` |
| **W3** | RTL / Terminology / A11y Foundations | Global Arabic RTL, terminology governance, focus/contrast/tabbing, responsive base | `static/css/rtl.css`, `static/css/design-tokens.css`, `templates/admin_base.html` |
| **W4** | Official Logo Unification | `kinjo_logo.html` sizing, agency/dashboard logo decision, favicon/PWA icons, image perf | `templates/components/*`, `static/img/*`, `templates/base.html` |
| **W5** | Privacy / Security / Exports | Sensitive-field denylist, CSRF on state-changing calls, aggregated-only guarantees, data-quality label | `agency_reports_service.py`, `agency_reports_export.py`, `api/agency_reports_api.py` |
| **W6** | Verification, Tests, CI Gates, Merge | Static checks, missing test creation, full suite, browser QA, scope/PR/merge gates | `tests/`, CI config, git/gh commands |

Workstreams are **non-overlapping by file**: W1=index template+JS+CSS cards; W2=report template+KG2 JS+service; W3=global CSS/tokens; W4=logo component+assets; W5=service/export/security; W6=cross-cutting verification only.

---

## 2. Files owned by each workstream

**W1**
- `templates/admin/agency_reports/index.html` (verify; minor label/structure tweaks)
- `static/js/admin_agency_reports.js` (card schema, KPI grid, status/button/empty, custom labels)
- `static/css/agency_reports.css` (logo sizing, card equal-height, responsive)
- `agency_reports_registry.py` (verify labels only)

**W2**
- `templates/admin/agency_reports/report.html` (verify structure; chart-export button slot)
- `templates/admin/agency_reports/agency.html` (verify MOE cards)
- `static/js/admin_agency_reports.js` (chart-export wiring, DASH-09)
- `static/js/agency_report_location_filter.js` (verify cascade)
- `agency_reports_service.py` (`_kg2_eligibility`, optional caching)
- `static/data/jordan_admin_divisions.json` (verify source-of-truth)

**W3**
- `static/css/rtl.css`
- `static/css/design-tokens.css`
- `templates/admin_base.html` (dir/lang switching — verify only)

**W4**
- `templates/components/kinjo_logo.html` (size reconciliation LOGO-04)
- `templates/admin/agency_reports/index.html` (LOGO-06 decision)
- `templates/admin_dashboard.html` (LOGO-06 decision)
- `static/img/kinjo-logo.png` (exists; verify)
- `templates/base.html`, `static/manifest*` (LOGO-07, if in scope)

**W5**
- `agency_reports_service.py` (`SENSITIVE_FIELD_DENYLIST` enforcement, SEC-03/04/08)
- `agency_reports_export.py` (CSV aggregated-only, filename pattern DASH-08)
- `api/agency_reports_api.py` (CSRF/auth on POST, SEC-01/02/09)

**W6**
- `tests/test_admin_agency_logos.py` (**create** — TEST-06)
- `tests/test_admin_dashboard_redesign.py` (**create** — TEST-07)
- `tests/test_agency_reports_labels.py` (extend for new labels)
- CI workflow file (verify ruff/pytest gates)

---

## 3. Implementation sequence

1. **W6 — scaffold missing tests first** (TEST-06, TEST-07) so they exist before features change; extend `test_agency_reports_labels.py`.
2. **W3 — foundations** (RTL/tokens/a11y) since everything else layers on top; mostly verify, minor CSS only.
3. **W5 — security/privacy guardrails** before UX, so new UI cannot leak PII; verify denylist + CSRF.
4. **W1 — index/cards** UX polish (cards, widgets, labels, responsive logo sizing).
5. **W2 — report pages & KG2** (chart-export wiring, verify cascade/results, optional perf).
6. **W4 — logo unification** (sizing, agency-page decision, favicon) — independent, can run parallel to W1/W2.
7. **W6 — final verification**: ruff, py_compile, targeted + full pytest, browser QA, scope check, PR, CI watch, merge.

W4 may proceed in parallel with W1–W3 (no shared files). W5 must land before W1/W2 UI changes to avoid PII regression. W6 gates everything.

---

## 4. Dependencies between workstreams

```
W6 (tests) ──▶ W1, W2, W4 (features must satisfy new tests)
W3 (RTL/tokens) ──▶ W1, W2, W4 (CSS variables consumed downstream)
W5 (security) ──▶ W1, W2 (UI must not bypass denylist/CSRF)
W1, W2, W4 ──▶ W6 (verification depends on features done)
W4 ──┐
W1 ──┼── (parallel; no file overlap)
W3 ──┘
```

- **Hard dependency:** W5 before any W1/W2 template change (privacy-first).
- **Soft dependency:** W3 foundational CSS before W1/W2 responsive CSS additions.
- **No circular deps.** W6 is terminal.

---

## 5. Required tests per workstream

| WS | Tests (existing → run; new → create) |
|---|---|
| W1 | `test_admin_agency_reports_registry.py`, `test_admin_agency_reports_custom.py`, `test_agency_reports_labels.py` (extend), `test_admin_data_integrity.py` |
| W2 | `test_admin_agency_reports_contract.py`, `test_admin_agency_reports_registry.py`, `test_jordan_locations.py`, `test_agency_reports_labels.py`, `test_analytics_dashboard_perf_fixes.py` (extend for report perf) |
| W3 | `tests/accessibility_audit.js`, `test_help_center.py` (terminology), manual RTL/contrast QA |
| W4 | **`tests/test_admin_agency_logos.py` (CREATE)**, **`tests/test_admin_dashboard_redesign.py` (CREATE)**, manual logo QA |
| W5 | `test_admin_agency_reports_registry.py` (denylist), `test_ncfa_report_formulas.py` (CSV), `test_admin_agency_reports_custom.py` (CSRF/auth), `test_admin_contract.py` |
| W6 | All of the above + full suite `pytest tests/ --timeout=180` |

> Note: `test_admin_agency_logos.py` and `test_admin_dashboard_redesign.py` are **required by master prompt §10** but **do not currently exist on disk** — they must be created in W6/W4 before merge.

---

## 6. Verification commands

Run from a **clean worktree** (`feat/admin-agency-reports-ux-polish`), never from dirty `D:\Final Version`.

```bash
# --- Static checks (W6) ---
python -m ruff check .
python -m py_compile agency_reports_registry.py agency_reports_service.py api/agency_reports_api.py

# --- Targeted tests (W1/W2/W4/W5) ---
python -m pytest tests/test_admin_agency_reports_registry.py -q --tb=short
python -m pytest tests/test_admin_agency_reports_custom.py -q --tb=short
python -m pytest tests/test_admin_agency_reports_contract.py -q --tb=short
python -m pytest tests/test_admin_agency_logos.py -q --tb=short          # CREATE if missing
python -m pytest tests/test_admin_dashboard_redesign.py -q --tb=short  # CREATE if missing
python -m pytest tests/test_admin_dashboard_redesign.py -q --tb=short
python -m pytest tests/test_jordan_locations.py -q --tb=short
python -m pytest tests/test_agency_reports_labels.py -q --tb=short
python -m pytest tests/test_ncfa_report_formulas.py -q --tb=short

# --- Full suite (W6) ---
python -m pytest tests/ --timeout=180 -q

# --- Terminology gate (W3, pre-commit) ---
grep -RIn "رياض الأطفال\|روضة" templates static agency_reports_registry.py agency_reports_service.py api \
  --include="*.html" --include="*.js" --include="*.css" --include="*.py" || true
# Expected: 0 user-facing admin UI matches (test fixtures/data excluded by exception)

# --- Browser QA (W6) : start isolated server ---
TESTING=true ENVIRONMENT=development \
  SECRET_KEY="local-run-signing-key-please-rotate-abcdef1234" \
  DATABASE_URL="sqlite:///./kinjo_local_run.db" \
  python -m uvicorn main:app --host 127.0.0.1 --port 8099
# Walk all /admin/agency-reports* + /login + /admin/dashboard; save screenshots to .local-qa/agency-reports-ux/ (do NOT commit)

# --- Scope check before commit (W6) ---
git status --short
git diff --stat
git diff --name-only

# --- PR + CI (W6) ---
gh pr create --base main --head feat/admin-agency-reports-ux-polish --title "feat(admin): polish agency reports UX and logo usage" --body "$(cat pr_body.md)"
gh pr checks --watch
gh pr merge --squash --delete-branch   # ONLY when all gates green + mergeable CLEAN
```

**Merge gates (all must be true):** PR OPEN · base `main` · `mergeable=MERGEABLE` · all CI green · full pytest 0 failed · browser QA complete · scope clean (no #29/#26/#20 files, no DB/screenshots/logs) · no `KJ`/`Kj` visual brand marks · no `رياض الأطفال`/`روضة` in admin UI · logo asset present · no PII path · no migration `--apply`.

**Cleanup after merge:** `git worktree remove --force "../Final Version-agency-reports-ux" && git worktree prune`. Do NOT remove `D:\Final Version`, `D:\Final Version-loc29`, or any active concurrent-agent worktree.
