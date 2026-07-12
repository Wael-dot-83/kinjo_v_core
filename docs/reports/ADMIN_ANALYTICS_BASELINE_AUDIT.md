# Admin Analytics — Baseline Audit (Evidence)

**Date:** 2026-07-12
**Auditor:** Claude Code (senior cross-functional delivery pass)
**Target route:** `http://127.0.0.1:8055/admin/analytics`
**Scope:** Verified baseline per Master Implementation Prompt §3, **before** any code change.

> This document records **only what was verified with commands**. Nothing here is
> assumed, projected, or fabricated. Items not yet verified are explicitly marked
> `NOT YET VERIFIED`.

---

## 1. Environment snapshot (verified)

| Item | Value | Evidence |
|---|---|---|
| Branch | `release-gate/dep-upgrades` | `git branch --show-current` |
| Commit SHA | `0595ee17302bca1da050a8b98f47231f7c5be3db` | `git rev-parse HEAD` |
| Python | 3.13.7 | `python --version` |
| DB engine (dev) | **SQLite** `sqlite:///./data/kinjo.db` | `.env` |
| Redis | `redis://localhost:6379/0` configured | `.env` |
| TESTING | `false` (correct — cache enabled) | `.env` |
| REQUEST_TIMEOUT_SECONDS | 60 | `.env` |
| PostgreSQL final verification | **NOT DONE** — dev DB is SQLite | — |

**Gap:** Production readiness per §22 requires Postgres empty→head migration + Postgres E2E.
The dev environment runs SQLite, so all Postgres-specific acceptance criteria are `NOT YET VERIFIED`.

---

## 2. Test baseline (verified)

Targeted analytics suite — **107 passed, 0 failed** (59.2s):

```
python -m pytest tests/test_analytics_service.py tests/test_analytics_endpoints.py \
  tests/test_kpi_service.py tests/test_analytics_rbac.py \
  tests/test_drilldown_page_frontend_contract.py -q
=> 107 passed, 1 warning in 59.21s
```

Full suite (`python -m pytest`): **NOT YET RUN this session** (memory records 3046 passing on `main` as of prior sweep; not re-verified on this branch).

Browser verification of `/admin/analytics` (console errors, network, timings, a11y, screenshots):
**NOT YET DONE** — server not confirmed running on :8055 this session.

---

## 3. Terminology state (verified) — §2

### Arabic (`حضانة`) — effectively COMPLETE

A prior Arabization audit already migrated `رياض الأطفال → الحضانات` (890 repl / 154 files).
Residual scan of user-facing files (`templates/`, `static/i18n/`, `static/js/`):

```
grep -rc -E 'روضة|رياض' templates/ static/i18n/ static/js/
```

3 of 4 hits are **FALSE POSITIVES** — `رياضة` ("sports") matched on the substring `رياض`:
- `templates/reports/form.html:235,437` → "Sports / رياضة"
- `static/i18n/literal_en_overrides.json:846` → `"رياضة": "sports"`

**Genuine facility-term residuals in Arabic: 0.** This validates the prompt's own warning
against blind string replacement.

### English (`Nursery`) — NOT STARTED

- `"Nursery"` occurrences in `static/i18n/admin_en.json`: **0**
- `"Kindergarten"` occurrences in `admin_en.json`: **26**
- `Kindergarten` hits across `templates/`: **780** (mix of user-facing English guards,
  model refs, Jinja comments — requires context-aware audit, NOT blind replace)
- Concrete bilingual defect: `static/js/admin_daily_reports_organization.js:274` renders
  English `"Displayed kindergartens"` while its Arabic side is correct (`عدد الحضانات`).

**Conclusion:** §2 Arabic work is ~done; §2 English work (Kindergarten→Nursery, user-facing
labels only, preserving `kindergarten_id`/models/URLs) is real, sizeable, and outstanding.

---

## 4. Drill-down hierarchy (verified defect) — §7

`analytics_service.py` drill-down dispatch (lines ~1854–1982) handles only:

```
GOVERNORATE → KINDERGARTEN → CLASS
```

**CITY level is absent.** The prompt's claim that the journey skips the city level is
**CONFIRMED**. The required hierarchy is Country → Governorate → **City** → Nursery → Class.

`models.AnalyticsDimensionType` is used at analytics_service.py:6154/6297/6386 — need to
confirm whether a CITY enum member exists before implementing (`NOT YET VERIFIED`).

---

## 5. Missing-data-as-zero anti-pattern (verified) — §6

Zero-coalescing (`|| 0` / `?? 0`) occurrences in analytics JS:

```
grep -rnE '\|\|\s*0\b|\?\?\s*0\b' static/js/admin_analytics*.js  =>  76 matches
```

Analytics JS surface: `admin_analytics.js`, `admin_analytics_drilldown.js`,
`advanced_analytics.js`, `analytics.js`. Each of the 76 sites needs individual triage —
some are legitimately zero (counts), many likely mask missing/insufficient data as `0%`.
This is the §6 defect class and it is real, but **each site requires business-context review**;
the count is an upper bound, not a confirmed defect count.

---

## 6. Architecture facts (verified)

- Proposed `analytics/` package (§5 registry) **does not exist** — greenfield.
- `analytics_service.py` is **312 KB** — monolithic; extracting a canonical metric registry
  is a large refactor with regression risk.
- Existing KPI single-source infra already present: `kpi_service.py` (250 KB),
  `kpi_standards.py` (58 KB), `governance_kpi_service.py`. Any registry must **reconcile with**
  these, not duplicate them.

---

## 7. Confirmed defects (evidence-backed)

| # | Defect | Section | Evidence | Status |
|---|---|---|---|---|
| D1 | English facility terminology not standardized to "Nursery" | §2 | 26 in admin_en.json, 0 "Nursery" | Confirmed |
| D2 | Drill-down skips CITY level | §7 | analytics_service.py:1854–1982 | Confirmed |
| D3 | Widespread `\|\| 0` masking of missing data in analytics JS | §6 | 76 matches | Confirmed (per-site triage needed) |
| D4 | Bilingual leak: English "kindergartens" in daily-reports JS | §2/§12 | admin_daily_reports_organization.js:274 | Confirmed |

## 8. Verified-correct / already-done

- Arabic `حضانة` terminology standardization (§2 Arabic side).
- Targeted analytics test suite green (107/107).
- Cache enabled (`TESTING=false`) — the historical 504 root cause is not present.

## 9. NOT YET VERIFIED (must not be claimed as done)

- Full test suite on this branch.
- Live browser audit (console/network/timings/a11y/screenshots) of `/admin/analytics`.
- Postgres empty→head migration + Postgres E2E.
- Per-metric formula correctness / weighted-aggregation review.
- RBAC drill-down authorization by URL manipulation.
- Export parity with active filters.
- Accessibility (axe) on analytics pages.

---

## 10. Honest scope assessment

The Master Prompt (§5–§21) describes a multi-week program: a canonical metric registry +
snapshot tables, full 5-level drill-down, a rewritten accessible chart layer, a re-architected
locale system, export parity, perf/snapshot infrastructure, and full bilingual E2E on Postgres.
Each is a substantial standalone PR. This baseline is the mandated §3 prerequisite; implementation
must proceed in reviewable, independently-verifiable slices — not a single unverifiable "done".
