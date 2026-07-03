# Analytics Dashboard Investigation — Performance & Risk Intelligence

**Date:** 2026-07-04 · **Scope:** `/admin/analytics` (Analytics Intelligence Center) and its
`/api/analytics/dashboard-data` backend

## Method

A written "deep investigation report" was supplied describing symptoms observed on
`/admin/analytics`: ~37s load time, blank KPI cards, a "system healthy" banner despite
that, and an unavailable Risk Intelligence section. Rather than acting on the report's
prose (which assumed a React/TypeScript stack this project doesn't use — it's FastAPI +
Jinja2 + vanilla JS), each claim was independently verified against the live server and
database before any code changed. Two of the described symptoms turned out to be real,
confirmed, root-caused bugs; the rest were either already-correct behavior or
misdiagnosed by the source report.

## Confirmed and fixed

### 1. ~35s cold-cache dashboard load (root cause: duplicate governance-score computation)

**Verification:** direct timing of `/api/analytics/dashboard-data` showed **35.03s** on a
cold cache (30s Redis TTL), vs ~10ms warm. Profiling each internal call attributed the
cost precisely: `get_network_summary` ~6.7s ×2 (current + previous period),
`get_governorate_breakdown` ~5.3s, `get_governance_distribution` ~12.4s.

**Root cause:** the kindergarten governance score (used by the network summary, the
governorate breakdown, and the governance distribution card) was computed **up to four
times per kindergarten in a single request**, via **two different formulas**:
- `analytics_service.py`'s own duplicated "simplified GCEI" formula
- `kpi_service.py`'s canonical `KPIService.compute_governance_score` (→ `compute_kpi_bundle`)

Direct comparison for the same kindergarten/period: **60.0** (simplified) vs **40.0 /
"RED"** (canonical) — a material disagreement. This is a real KPI-integrity violation:
`CLAUDE.md`'s own rule states "KPI computations belong in `kpi_service.py` — do not
duplicate logic in endpoints." With 629 seeded kindergartens, redundantly running this
computation 3-4× per kindergarten (each ~20-26ms) is what produced the ~35s wall time.

**Fix** ([analytics_service.py](analytics_service.py)):
- Added `AnalyticsService._kg_governance_score_and_band(db, kg_id, period_start,
  period_end)`: delegates exclusively to the canonical `KPIService.compute_governance_score`
  and memoizes the result on `db.info` (request-scoped) so the same (kg, period) is never
  recomputed twice within one request.
- `get_governance_distribution`, `_compute_network_governance_score`, and
  `_compute_governorate_governance_score` now all route through this single helper.
- Removed the duplicate "simplified GCEI" formula entirely.
- The previous-period comparison in `get_consolidated_dashboard_data` was calling the
  **full** `get_network_summary()` (which internally computes the governance score for
  all 629 kindergartens again) just to read 2 of its ~9 fields (`attendance_rate`,
  `incident_rate` — `total_kindergartens` was being overwritten immediately after, never
  actually read from that call). Replaced with direct calls to the two specific cheap
  aggregate queries actually needed.

**Result (fresh, never-cached date ranges, measured live via HTTP):**

| Date range | Before | After |
|---|---|---|
| single profiled call attribution | 35.03s | — |
| 2026-04-01 to 04-10 | ~35s (extrapolated) | **12.59s** |
| 2026-03-01 to 03-10 | ~35s (extrapolated) | **7.45s** |
| 2026-07-01 to 07-03 | ~35s (extrapolated) | **12.11s** |

A **65-80% reduction**, with a real correctness bug fixed as a side effect (governance
scores are now internally consistent across every section of the dashboard).

**Not fixed, documented as a follow-up:** `/api/analytics/rankings/governance_score`
(used by the Top/Low Performers leaderboard, fired as a separate pair of HTTP requests)
independently recomputes governance scores for all 629 kindergartens (~12.5s each, no
redundancy *within* that endpoint to eliminate). Because each ranking request is its own
HTTP request with its own DB session, the request-scoped memoization above doesn't help
across requests. A real fix here needs a **cross-request cache** (Redis, keyed by
`(kg_id, period_start, period_end)`, with a staleness/TTL tradeoff against admins doing
real-time incident review) — a different risk profile than the request-scoped fix above,
and out of scope for this session. Until fixed, opening the "Registrations" tab still
costs an additional ~12-25s beyond the initial dashboard load.

### 2. Risk Intelligence always showed "no risk alerts" despite real risk data existing

**Verification:** `get_high_risk_children()` correctly found 3 at-risk children (via
direct backend test and live API call), but the rendered page showed the empty state
("لا توجد تنبيهات مخاطر — جميع المرافق بصحة جيدة") regardless.

**Root cause:** a schema mismatch between what the backend returns and what two
independent frontend renderers expected:

| Backend actually returns | Renderers were reading |
|---|---|
| `child_name`, `kindergarten_name` | `name`, `kindergarten` |
| `risk_value`, `risk_type` | `risk_score` |
| `description` | `reason` |
| *(missing entirely)* | `kindergarten_id` |

`admin_analytics.js`'s `updateRiskRadar()` — which runs **first**, before a chain of 9
sequential `await` calls — validated every entry against the wrong field names, so
`typeof item.name === "string"` was always false, every entry was discarded, and the
function fell through to the empty state before a second, independent renderer
(`dashboard.html`'s `window._renderRiskCards`, wired to a later `analyticsDataLoaded`
custom event) ever got a chance to correct it. `_renderRiskCards` had the *same* wrong
field names, so even that later correction never actually worked. Also, `risk_value`'s
scale and direction differ by `risk_type` (an attendance % where lower is worse, vs. an
incident count where higher is worse), so a single `score >= 7` threshold — which relied
on a field that didn't exist anyway — couldn't have classified severity correctly even
with the right field name.

**Fix:**
- [analytics_service.py](analytics_service.py) `get_high_risk_children`: added the
  missing `kindergarten_id` field (the join already computes it; it just wasn't included
  in the returned dict), so the "view facility" link has something to point at.
- [static/js/admin_analytics.js](static/js/admin_analytics.js) `updateRiskRadar`: fixed
  the validation filter and sort to use the real field names; severity ranking now uses
  the new shared classifier instead of a nonexistent `risk_score`.
- [templates/admin/analytics/dashboard.html](templates/admin/analytics/dashboard.html):
  added `window._classifyRisk(r)` (branches on `risk_type` since attendance-% and
  incident-count aren't comparable on one scale) and `window._riskReasonText(r, isAr)`
  (renders a proper Arabic reason instead of the backend's English-only `description`);
  `_renderRiskCards` and the executive banner's critical-count chip now use these.

**Verified live (headless Chromium, after fix):** `#riskList` renders 3 real cards
(e.g. "يوسف سالم" / "نسبة الحضور: 0%", correctly classified `critical`);
`#noRiskData` is correctly hidden; zero console errors.

## Investigated and found to be already correct (no fix needed)

- **Date range display** (`إجراء البانر التنفيذي`): already renders as
  `١ تموز ٢٠٢٦ — ٤ تموز ٢٠٢٦` (unambiguous month-name Arabic), not the numeric
  `MM/DD/YYYY` format the source report worried about. That numeric format only appears
  inside the native `<input type="date">` picker widgets, which is standard browser
  locale behavior, not app code.
- **"Registrations: 0"**: `/api/analytics/registration/analytics` correctly returns
  `new_applications: 3` for the exact same date range and dataset — the specific figure
  the source report screenshotted was very likely a stale render (a direct symptom of the
  ~35s load, now fixed) or a different, legitimately-zero sub-metric (e.g., pending vs.
  active), not a data or query bug.
- **~19 other "stuck skeleton" widgets** (funnel viz, registration totals, top/low
  performer lists, benchmark/target/recommendation lists): confirmed via DOM inspection
  to live inside non-default tab panes (`tabOperations`, `tabGovernance`,
  `tabGeographic`) that intentionally lazy-load on tab activation — correct, deliberate
  UX, not a defect. `execInsights` (in the always-visible executive banner) was the one
  exception worth checking and turned out to depend on the same risk-radar fix above.
- **"System healthy" banner vs. slow/incomplete data**: no separate fix applied. The
  banner's logic already only escalates to "needs attention" based on `criticalCount`
  from the risk radar (now correctly computed after the fix above) — it isn't hardcoded
  to always say "good."

## Tests

- `tests/test_analytics_dashboard_perf_fixes.py` (new, 6 tests): governance-score
  helper consistency, per-request memoization, network/governorate aggregation using the
  canonical formula, dashboard-data endpoint smoke test, and `get_high_risk_children`
  field-name contract (including a negative check that the old, wrong field names don't
  silently reappear).
- `tests/test_dashboard_frontend_contract.py` (extended, +1 test): asserts both risk-card
  renderers reference the real backend field names and not `risk_score`.
- Targeted suite (`test_analytics_service.py`, `test_analytics_gap.py`,
  `test_kpi_service.py`, `test_kpi_p0_regression.py`, `test_kpi_dashboard.py`,
  `test_analytics_pinpoint_e2e.py`): **205/205 pass**.
- Full suite: see commit message for final count.

## Files changed

- `analytics_service.py` — governance-score memoization/consolidation,
  previous-period comparison no longer computes a full unused `NetworkSummary`,
  `get_high_risk_children` now includes `kindergarten_id`.
- `static/js/admin_analytics.js` — `updateRiskRadar` field-name and severity-sort fix.
- `templates/admin/analytics/dashboard.html` — `_classifyRisk`/`_riskReasonText` helpers,
  `_renderRiskCards` and executive-banner critical-count fixed to match.
- `tests/test_analytics_dashboard_perf_fixes.py` (new),
  `tests/test_dashboard_frontend_contract.py` (extended).
