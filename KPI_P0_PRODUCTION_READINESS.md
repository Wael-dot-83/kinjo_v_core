# KPI P0 Production Readiness — magenta-manchego

## Scope

This document covers the six P0 KPI fixes implemented in `kpi_service.py` on the
`magenta-manchego` branch, plus all production-hardening work done as part of this
readiness review.

---

## 1. P0 Fix Implementation Status

### P0.1 — Jordan Timezone Compliance

**Status: PASS**

All KPI business-date logic uses Jordan UTC+3 via the `_today_jordan()` helper.

```python
# kpi_service.py — module level
_JORDAN_TZ = timezone(timedelta(hours=3))

def _today_jordan() -> date:
    """Current date in Jordan UTC+3. Use everywhere instead of date.today()."""
    return datetime.now(_JORDAN_TZ).date()
```

No bare `date.today()` calls remain in runtime code paths. The docstring reference
inside `_today_jordan` is the only permitted occurrence.

**Production Note:** The current implementation uses a fixed `timedelta(hours=3)` offset.
Jordan has been permanently UTC+3 since 2022 (DST discontinued). If the government ever
reverts DST, upgrade to `ZoneInfo("Asia/Amman")` from the `zoneinfo` standard library.
This is a non-breaking change — the public `_today_jordan()` interface remains identical.

**UTC midnight boundary:** Between 21:00–23:59 UTC, the Jordan date is one day ahead of
UTC. Any cron job, cache key, or API client that passes today's UTC date as a query
parameter will request the wrong period. All date construction must go through `_today_jordan()`.

---

### P0.2 — `get_kpi_target()` Default Argument Bug

**Status: PASS**

```python
# Before (evaluated once at module import, never changes):
def get_kpi_target(..., target_date: date = date.today()): ...

# After (evaluated at call time):
def get_kpi_target(..., target_date: Optional[date] = None):
    if target_date is None:
        target_date = _today_jordan()
```

The fix ensures KPI targets are resolved against the correct business date on every call,
not the date the server process started.

---

### P0.3 — Incident Rate Unit Normalisation

**Status: PASS**

All incident rate computations now use **per 1,000 attended child-days**.

| Location | Before | After |
|---|---|---|
| `KPIService.compute_incident_rate()` | `× 100` | `× 1000` |
| `KPIService.compute_serious_incident_rate()` | `× 100` | `× 1000` |
| `compute_kpi_bundle()` | `× 100` | `× 1000` |
| `_build_base_bundles_bulk()` | `× 100` | `× 1000` |

The per-100 formula produced values < 0.05 for normal operations (e.g., 1 incident /
2000 child-days = 0.05 per 100) — always below the GREEN threshold of 2.0 per 1,000,
making incident KPIs permanently GREEN regardless of actual safety performance.

**Backward compatibility:** `incident_rate_per_100` and `serious_incident_rate_per_100`
keys are preserved in the bundle for any consumers that haven't migrated. These will
be removed in a future release after downstream consumers are updated.

---

### P0.4 — `incident_followup_sla` Consistency

**Status: PASS**

**Before:**
- Standalone `compute_incident_followup_sla_compliance()` returned `100.0` when no
  follow-up-required incidents existed — a misleading "perfect SLA".
- Bundle returned `0.0` for the same condition.

**After:**
- Standalone returns `0.0` when `followup_required == 0`.
- Bundle sets `quality.incident_followup_sla.has_data = False` with reason:
  `"No follow-up-required incidents in selected period"`.
- Callers must check `has_data` before rendering the value.

**Frontend obligation:** The dashboard must display `INSUFFICIENT DATA` (not `100%` or
`0%`) when `quality.incident_followup_sla.has_data == false`.

---

### P0.5 — Hard Override Rules

**Status: PASS**

All five rules defined in `kpi_standards.py` are now enforced in `compute_kpi_bundle()`.

**Override priority (deterministic):**

| Priority | Rule | Band | Supersedes INSUFFICIENT? |
|---|---|---|---|
| 1 | `INSUFFICIENT_DATA_COVERAGE` | `INSUFFICIENT` | — |
| 2 | `LICENSE_MISSING` | `RED` | Yes |
| 3 | `LICENSE_EXPIRED` | `RED` | Yes |
| 4 | `OVERCAPACITY` | `RED` | Yes |
| 5 | `RATIO_BELOW_MINIMUM` | `RED` | No |
| 6 | `UNRESOLVED_CRITICAL_INCIDENT` | `AMBER` (minimum) | No |

**Design decision:** `OVERCAPACITY` supersedes `INSUFFICIENT_DATA_COVERAGE` because it is
a hard physical fact (children in a room designed for fewer) verifiable without KPI data.
`RATIO_BELOW_MINIMUM` and `UNRESOLVED_CRITICAL_INCIDENT` are rate-derived and must not
override INSUFFICIENT (the raw values are unreliable when data is absent). Both rules are
still recorded in `override_rules_triggered` for observability.

**`INSUFFICIENT` vs `RED`:** These are distinct states. `RED` means measured poor
performance. `INSUFFICIENT` means the system cannot measure performance. A dashboard that
shows `INSUFFICIENT` as `RED` misleads operators into investigating a reporting failure as
if it were a safety failure.

---

### P0.6 — Training Completion Denominator

**Status: PASS** (plus one additional bug found and fixed during this review)

**Original fix:** Changed from in-period filter to cumulative coverage as of `period_end`:
```python
# Counts valid completions from any prior period, not just the selected month
StaffTrainingCompletion.completion_date <= period_end
```

**Additional bug fixed in this review:** The numerator was not filtering for mandatory
modules. Non-mandatory completions were inflating the numerator against a denominator
that only counted mandatory modules × active staff. Fix adds a JOIN to `training_modules`
with `is_mandatory == True` in all three computation locations:
- `KPIService.compute_training_completion_rate()`
- `compute_kpi_bundle()`
- `_build_base_bundles_bulk()`

**Correct semantics:**
- Denominator = active staff count × mandatory training module count
- Numerator = distinct (staff, mandatory-module) pairs completed as of `period_end`
- Rate = capped at 100% (distinct pairs cannot exceed denominator)

---

## 2. Additional Bugs Found and Fixed During This Review

These were found by the regression test suite, not in the original P0 analysis:

| # | Bug | Location | Fix |
|---|---|---|---|
| B1 | Standalone `compute_incident_rate()` still used `× 100` | `KPIService.compute_incident_rate()` | Changed to `× 1000` |
| B2 | Standalone `compute_serious_incident_rate()` still used `× 100` | `KPIService.compute_serious_incident_rate()` | Changed to `× 1000` |
| B3 | `INSUFFICIENT_DATA_COVERAGE` set `governance_band = "RED"` | `compute_kpi_bundle()` | Changed to `"INSUFFICIENT"` |
| B4 | `OVERCAPACITY` only demoted GREEN → AMBER | `compute_kpi_bundle()` | Changed to always set `"RED"` |
| B5 | Rate-based overrides fired on unreliable data | `compute_kpi_bundle()` | Rate rules skip when `insufficient_data = True` |
| B6 | Training numerator counted non-mandatory completions | 3 locations | Added JOIN with `TrainingModule.is_mandatory == True` |

---

## 3. Test Coverage

### Existing suite
- 105 tests pass with no failures and no SQLAlchemy warnings.

### New P0 regression suite: `tests/test_kpi_p0_regression.py`
- 40 tests, 40 pass.
- Covers all six P0 fixes plus all additional bugs found during this review.

### Total after merge
- 145 tests pass, 0 failures.

---

## 4. API Contract

### Bundle response shape

The `compute_kpi_bundle()` return dict is the source of truth for all KPI endpoints.
Required keys:

```
attendance_rate, excused_absence_rate, incident_rate, incident_rate_per_100,
serious_incident_rate, serious_incident_rate_per_100, incident_followup_sla,
ratio_compliance, training_completion_rate, report_submission_rate,
chronic_absence_rate, checklist_compliance, regulatory_status, parent_satisfaction,
parent_response_rate, gqi_score, cei_score, governance_score, governance_band,
capacity_utilization_rate, active_enrollments, new_enrollments,
override_rules_triggered, numerators, denominators, quality
```

### `governance_band` valid values

```
"GREEN" | "AMBER" | "RED" | "INSUFFICIENT"
```

`"INSUFFICIENT"` is not a band color — it is a distinct state meaning "cannot be
rated due to missing source data." Frontend must render it differently from the three
band colors.

### Quality metadata shape

```json
{
  "has_data": true,
  "coverage_pct": 100.0,
  "reason": null
}
```

When `has_data == false`, `reason` contains a human-readable explanation. The frontend
must display `INSUFFICIENT DATA` (not 0% or any band color) for any KPI where
`quality[kpi_key].has_data == false`.

### Breaking changes in this branch

| Change | Impact |
|---|---|
| `incident_rate` now per-1,000 (was per-100) | Any frontend chart threshold that assumed per-100 will show wrong bands. Update display labels and threshold expectations. |
| `governance_band` can now be `"INSUFFICIENT"` | Frontend code doing `if band === "RED"` must also handle `"INSUFFICIENT"`. |
| `incident_followup_sla` is `0.0` (not `100.0`) when no data | Clients that cached or cached the old "100.0 perfect" value will see a change. |

### Deprecated keys (remove in next release)

- `incident_rate_per_100` — backward compat only; equals old `incident_rate`
- `serious_incident_rate_per_100` — same

---

## 5. Frontend Requirements

### Incident rate display

```
Label: "X.XXX per 1,000 child-days"
Tooltip: "Number of incidents per 1,000 attended child-days during the selected period.
          A value of 0.0 means no incidents occurred."
```

Band thresholds shown to users (from kpi_standards.py):
- GREEN: ≤ 2.0 per 1,000 child-days
- AMBER: 2.001 – 5.0
- RED: > 5.0

### `INSUFFICIENT` band display

```
Badge text: "INSUFFICIENT DATA"
Background: grey (not red)
Tooltip: "This KPI cannot be reliably calculated because required source data
          is missing or incomplete. This is not a performance rating."
```

### Override badges

When `override_rules_triggered` is non-empty, show each code as a badge:

| Code | Badge text |
|---|---|
| `LICENSE_EXPIRED` | License expired |
| `LICENSE_MISSING` | No license on file |
| `OVERCAPACITY` | Overcapacity |
| `RATIO_BELOW_MINIMUM` | Below ratio minimum |
| `UNRESOLVED_CRITICAL_INCIDENT` | Unresolved critical incident |
| `INSUFFICIENT_DATA_COVERAGE` | Insufficient data |

### Follow-up SLA

When `quality.incident_followup_sla.has_data == false`:
```
Display: "INSUFFICIENT DATA"
Subtitle: "No follow-up-required incidents in selected period"
```
Do not display `0%` or `100%`.

### Training completion tooltip

```
Tooltip: "Percentage of required mandatory training completions among active staff
          as of the end of the reporting period. Prior completions remain valid."
```

### Timezone display

All date values shown to users must include Jordan timezone context:
```
"Computed using Asia/Amman timezone (UTC+3)"
```

---

## 6. Database

### Schema migrations
No schema changes are required. All six P0 fixes are pure query logic changes.

### Performance indexes
Add via `alembic/versions/001_kpi_p0_performance_indexes.py`. All indexes use
`CREATE INDEX IF NOT EXISTS` and are safe for zero-downtime deployment.

Critical indexes for P0 query patterns:
- `ix_attendance_kg_date_status` — every KPI bundle
- `ix_staff_training_kg_user_module_date` — training completion (now includes JOIN to modules)
- `ix_incidents_kg_occurred_followup` — incident rate and followup SLA
- `ix_kindergartens_license_valid_until` — hard override license check

---

## 7. Monitoring

### Metrics to instrument

```
kpi_compute_duration_ms         — per bundle computation latency
kpi_insufficient_data_count     — count of INSUFFICIENT band results per period
kpi_override_applied_count      — count of non-empty override_rules_triggered
kpi_override_by_rule_{code}     — per-rule override count
kpi_expired_license_count       — count of LICENSE_EXPIRED overrides
kpi_overcapacity_count          — count of OVERCAPACITY overrides
kpi_fallback_ratio_used_count   — count of ratio estimation fallback usage
```

### Alert conditions

| Alert | Condition | Severity |
|---|---|---|
| Spike in INSUFFICIENT band | > 20% of bundles return INSUFFICIENT in a single run | Warning |
| License expired detected | Any LICENSE_EXPIRED override | Critical |
| Overcapacity detected | Any OVERCAPACITY override | High |
| Ratio below minimum | Any RATIO_BELOW_MINIMUM override | High |
| KPI compute error | Any exception in `compute_kpi_bundle` | Critical |
| Dashboard latency | p95 > 5s | Warning |

### Structured log fields for KPI events

```json
{
  "event": "kpi_bundle_computed",
  "kindergarten_id": 123,
  "period_start": "2026-06-01",
  "period_end": "2026-06-30",
  "timezone": "Asia/Amman (UTC+3)",
  "governance_band": "GREEN",
  "override_rules_triggered": [],
  "gqi_weight_sum": 0.85,
  "insufficient_data": false,
  "duration_ms": 42
}
```

---

## 8. QA Acceptance Checklist

### Functional QA

- [ ] KPI dashboard loads for admin role
- [ ] KPI dashboard loads for manager role
- [ ] Incident rate labels show "per 1,000 child-days"
- [ ] GREEN threshold for incident rate is ≤ 2.0 per 1,000 (not ≤ 0.02)
- [ ] `INSUFFICIENT DATA` badge appears when denominator is missing
- [ ] `INSUFFICIENT DATA` badge appears when GQI data coverage < 60%
- [ ] `INSUFFICIENT` band is grey (not red or amber)
- [ ] Follow-up SLA shows `INSUFFICIENT DATA` when no follow-up incidents exist
- [ ] Training completion > 0% for a kg where all staff trained last month
- [ ] License expired forces RED regardless of other KPI scores
- [ ] Overcapacity forces RED
- [ ] Unresolved critical incident prevents GREEN (minimum AMBER)
- [ ] Override codes appear in `override_rules_triggered`
- [ ] Old `incident_rate_per_100` legacy key is present for backward compat

### Data QA

- [ ] Empty kindergarten (no data) → INSUFFICIENT band
- [ ] Kindergarten with only license data → still INSUFFICIENT (0.20 < 0.60 GQI weight)
- [ ] Kindergarten with ratio + checklist + license → rated normally (0.70 ≥ 0.60)
- [ ] Training completion for kg where all training was done 6 months ago → > 0%
- [ ] Follow-up with one SLA breach out of two incidents → 50.0% (not 100%)
- [ ] Overcapacity: 3 active children in a room with capacity 2 → RED

### Regression QA

- [ ] `python -m pytest tests/test_kpi_p0_regression.py -q` → 40 passed
- [ ] `python -m pytest tests/test_kpi_dashboard.py tests/test_kpi_service.py tests/test_admin_operations.py -q` → 105 passed
- [ ] No SQLAlchemy cartesian product warnings in test output
- [ ] No `date.today()` violations flagged by `test_no_date_today_in_runtime_code`

---

## 9. Merge Readiness Report

```
Production Readiness Result: READY WITH CONDITIONS

Summary:
- All six P0 fixes are implemented and verified.
- Three additional bugs found during this review are also fixed (standalone
  incident rate methods still per-100; OVERCAPACITY severity; training numerator
  including non-mandatory modules).
- 145 tests pass, 0 failures, 0 SQLAlchemy warnings.
- One frontend breaking change requires coordinated deploy (incident_rate units).

Verified Fixes:
- P0.1 Jordan timezone:             PASS
- P0.2 get_kpi_target default arg:  PASS
- P0.3 incident rate units:         PASS (includes standalone method fixes found in review)
- P0.4 incident_followup_sla:       PASS
- P0.5 hard override rules:         PASS (includes INSUFFICIENT band + priority logic)
- P0.6 training completion:         PASS (includes mandatory-module filter added in review)

Tests:
- Existing suite:      105 passed, 0 failed
- P0 regression suite: 40 passed, 0 failed
- Total:              145 passed, 0 failed
- Warnings:           1 (httpx deprecation in FastAPI TestClient — unrelated to this branch)
- Failures:           0

API Contract:
- Stable:             All existing bundle keys preserved
- Breaking changes:   incident_rate value scale changed (per-100 → per-1,000);
                      governance_band can now return "INSUFFICIENT"
- Frontend changes:   Required (see Section 5)

Database:
- Mandatory migration: None
- Recommended indexes: alembic/versions/001_kpi_p0_performance_indexes.py

Documentation:
- KPI docs:      This file (KPI_P0_PRODUCTION_READINESS.md)
- API docs:      See Section 4 (API Contract)
- Frontend notes: See Section 5
- QA notes:      See Section 8

Remaining Risks:
- _today_jordan() uses fixed timedelta(hours=3) offset. Works correctly for Jordan
  (permanently UTC+3 since 2022) but is not DST-aware. Low risk, non-blocking.
- incident_rate_per_100 / serious_incident_rate_per_100 legacy keys should be
  removed in the next release after frontend migration is confirmed.
- No load testing of bulk dashboard endpoint under production data volume.
  Performance indexes must be applied before first production run.

Required Before Merge:
1. Update alembic down_revision in 001_kpi_p0_performance_indexes.py to the
   actual previous revision ID.
2. Frontend team must acknowledge the incident_rate unit breaking change and
   confirm dashboard threshold logic is updated.
3. QA must run the acceptance checklist in Section 8.

Required Before Deployment:
1. Apply performance indexes (alembic upgrade head) during a low-traffic window.
2. Cache warming: the 30-second TTL cache will serve stale per-100 values for up
   to 30 seconds after deploy. Flush Redis cache immediately after deployment.
3. Monitor kpi_insufficient_data_count for 24 hours post-deploy to confirm no
   unexpected data loss introduced INSUFFICIENT bands for previously-rated kgs.

Final Recommendation:
  MERGE APPROVED pending the three pre-merge items listed above.
  Deploy during a maintenance window with cache flush and index migration.
```
