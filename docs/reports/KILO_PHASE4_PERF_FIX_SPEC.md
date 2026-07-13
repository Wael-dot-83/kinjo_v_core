# Phase 4 Analytics — Performance Fix Spec (for Kilo)

**Author:** Claude (read-only reviewer)
**Date:** 2026-07-13
**Target files (all currently uncommitted in Kilo's working tree):**
`analytics_service.py`, `analytics_domain.py`, `static/js/admin_analytics.js`

This spec is a hand-off. Claude did **not** edit these files (they are uncommitted
and shared with Kilo — editing live would collide). Kilo owns the tree, so Kilo
applies the fixes below. Everything here is copy-paste ready against the code as it
stands in the working tree.

Ranked: **P1 blocks the <3s load-time success metric**, **P2 is a latent N+1 landmine**,
**P3 are correctness/quality follow-ups**.

---

## P1 — 🔴 Stop the redundant `get_network_summary` storm (SHIP BLOCKER)

### Problem
`AnalyticsService.get_network_summary` (`analytics_service.py:6488`) runs ~8 heavy
aggregates and has **no cache**. Only `/dashboard-data` caches its result; the new
sibling endpoints recompute from scratch. One default dashboard load triggers **~8
uncached full recomputations**:

| Trigger | `get_network_summary` calls |
|---|---|
| `loadInsights` (Phase 1) | 1 |
| `loadActionQueue` (Phase 1) | 1 |
| `loadTargetProgress` — 3 metrics × (current + prev), `admin_analytics.js:2683` | 6 |

Plus `loadInsights`/`loadActionQueue` each also recompute `get_governorate_breakdown`,
and `target-progress`'s percentile branch adds a `get_governorate_breakdown` per metric
when a governorate is selected.

### Fix — add two cached wrappers, then swap the call sites

**Step 1.** Add `import hashlib` to the imports block (top of `analytics_service.py`).

**Step 2.** Add these helpers right after `_analytics_cache_set` (≈ line 167). They
reference `NetworkSummary`/`GovernorateMetrics`, which are defined later in the module —
that's fine because the names resolve at call time, not def time.

```python
def _kg_ids_cache_token(kg_ids: Optional[List[int]]) -> str:
    if not kg_ids:
        return "all"
    return hashlib.md5(",".join(map(str, sorted(kg_ids))).encode()).hexdigest()[:12]


def _cached_network_summary(db, period_start, period_end, kg_ids):
    """Cache-backed get_network_summary. Keyed on the explicit (Jordan) period +
    scope, so it never uses date.today()/UTC. TTL = dashboard TTL (60s)."""
    key = (
        f"analytics:netsum:{period_start.isoformat()}:{period_end.isoformat()}:"
        f"{_kg_ids_cache_token(kg_ids)}"
    )
    cached = _analytics_cache_get(key)
    if cached is not None:
        return NetworkSummary.model_validate(cached)
    summary = AnalyticsService.get_network_summary(db, period_start, period_end, kg_ids)
    _analytics_cache_set(key, summary.model_dump(mode="json"))
    return summary


def _cached_governorate_breakdown(db, period_start, period_end, governorate, allowed_kgs, extra=None):
    key = (
        f"analytics:govbrk:{period_start.isoformat()}:{period_end.isoformat()}:"
        f"{governorate or 'all'}:{_kg_ids_cache_token(allowed_kgs)}"
    )
    cached = _analytics_cache_get(key)
    if cached is not None:
        return [GovernorateMetrics.model_validate(item) for item in cached]
    breakdown = AnalyticsService.get_governorate_breakdown(
        db, period_start, period_end, governorate, allowed_kgs, extra
    )
    _analytics_cache_set(key, [b.model_dump(mode="json") for b in breakdown])
    return breakdown
```

**Step 3.** In these endpoints, replace the direct service calls:

| Endpoint | Replace | With |
|---|---|---|
| `get_insights` | `AnalyticsService.get_network_summary(...)` | `_cached_network_summary(...)` |
| `get_insights` | `AnalyticsService.get_governorate_breakdown(...)` | `_cached_governorate_breakdown(...)` |
| `get_action_queue` | both of the above | cached versions |
| `get_target_progress` | **both** `get_network_summary` calls (current + prev) | `_cached_network_summary(...)` |
| `get_target_progress` | `all_govs = ...get_governorate_breakdown(...)` | `_cached_governorate_breakdown(...)` |

**Effect:** `target-progress`'s 3 metric calls share one `(today-30…today, kg)` key →
6 recomputes collapse to 2 (current + prev). `insights` + `action-queue` share the
dashboard period → collapse to 1. Net: **~8 → ~3** distinct computations, and repeat
loads inside the 60s TTL are free.

> **Convention check (CLAUDE.md):** keys use the explicit period dates passed in, never
> `date.today()`/UTC. `target-progress` already derives its window from `_jordan_today()`,
> so the cached key is Jordan-correct. ✅

---

## P2 — 🟠 `model-performance` N+1 + non-sargable date filters

### Problem
`get_model_performance` → `_get_actual_value` runs inside a double loop (≤10 predictions
× ~30 points) and each call issues 2 `COUNT`s using `func.date(Incident.occurred_at) ==
target_date`. Wrapping the column in `func.date()` is **non-sargable** — it defeats the
index and forces a scan, up to ~1,800 scans/request.

> **Note:** `loadModelPerformance` (`admin_analytics.js:2372`) is defined but **never
> called**, so this is latent today — fix it before wiring the endpoint to a tab.

### Fix — batch the whole window in one grouped query

**Step 1.** Add `time` to the datetime import:
`from datetime import date, datetime, time, timedelta, timezone`

**Step 2.** Add this helper (replaces the per-point `_get_actual_value`):

```python
def _actual_values_for_window(db, metric, start, end):
    """One grouped query -> {date: actual_value} for the whole window.
    Filters use half-open ranges on the raw column (sargable / index-friendly);
    only the GROUP BY buckets by day."""
    result = {}
    if metric == "attendance":
        rows = (
            db.query(
                models.AttendanceLog.date,
                func.count(models.AttendanceLog.id),
                func.sum(case((models.AttendanceLog.status == models.AttendanceStatus.PRESENT, 1), else_=0)),
            )
            .filter(models.AttendanceLog.date >= start, models.AttendanceLog.date <= end)
            .group_by(models.AttendanceLog.date)
            .all()
        )
        for d, total, present in rows:
            if total:
                result[d] = round((present or 0) / total * 100, 2)
        # ⚠ Attendance semantics: mirror `_compute_network_attendance_rate` for the
        # numerator/denominator (per CLAUDE.md, EXCUSED ≠ present). If that function
        # excludes EXCUSED from the denominator or treats statuses differently, adjust
        # the case()/filter above to match — don't invent a second formula.
    elif metric in ("incidents", "enrollment"):
        col = models.Incident.occurred_at if metric == "incidents" else models.EnrollmentApplication.created_at
        model_id = models.Incident.id if metric == "incidents" else models.EnrollmentApplication.id
        rows = (
            db.query(func.date(col), func.count(model_id))
            .filter(
                col >= datetime.combine(start, time.min),
                col < datetime.combine(end + timedelta(days=1), time.min),
            )
            .group_by(func.date(col))
            .all()
        )
        for d, c in rows:
            key = d if isinstance(d, date) else date.fromisoformat(str(d)[:10])
            result[key] = float(c)
    return result
```

**Step 3.** In `get_model_performance`, fetch once before the loop and look up:

```python
actuals = _actual_values_for_window(db, metric, evaluation_start, today)
...
# inside the forecast-point loop, replace:
#   actual_value = _get_actual_value(db, metric, forecast_date, prediction.scope_type, prediction.scope_id)
# with:
actual_value = actuals.get(forecast_date)
```

You can delete `_get_actual_value` once no other caller remains.

**Step 4 (same function) — fix the trend split, which isn't time-ordered.**
`evaluations` are appended in (prediction-desc, point) order, so `evaluations[:len//2]`
is not "recent". Sort ascending by date, then take the **second** half as recent:

```python
evaluations.sort(key=lambda e: e["date"])
half = len(evaluations) // 2
older_evals = evaluations[:half] or evaluations
recent_evals = evaluations[half:] or evaluations
```

---

## P3 — 🟡 Correctness / quality follow-ups (lower priority)

### P3a — Chart annotations miss every Islamic holiday
`_get_jordan_holidays` hardcodes 4 **Gregorian** holidays and omits Eid al-Fitr,
Eid al-Adha, Islamic New Year, and the Prophet's Birthday — Jordan's *major* national
closures, which shift each year. `OperatingCalendar` is **per-kindergarten**
(`kindergarten_id`, `is_open`), so it's not a clean national-holiday source.

**Recommended:** add a small static table of Jordan Islamic-holiday **Gregorian** dates
for the years the dashboard covers (e.g. 2025–2027), merged into `_get_jordan_holidays`,
with a comment that it must be verified/extended annually against the official calendar.
(A fully automated fix would need a Hijri converter or an official feed — out of scope
for this pass.)

### P3b — Remove dead code in `validate_dashboard_data`
The `attendance_trend` / `incident_trend` chronological-order block never runs:
`NetworkSummary` has no such fields, so `if trend_key in validated` is always false.
It also would `AttributeError` on `.date` if it ever did run (post-`model_dump` items are
dicts). Delete that block; keep only the numeric clamps. The per-call
`model_dump()` + `type(network_summary)(**validated_summary)` reconstruction on the hot
path is unnecessary overhead — apply clamps in place or drop the round-trip.

---

## Acceptance criteria
- [ ] P1: `insights`, `action-queue`, `target-progress` route their summary/breakdown
      reads through the cached wrappers; a single dashboard load computes
      `get_network_summary` **≤ 3** times (verify by log/counter or query trace).
- [ ] P1: cache keys use the explicit Jordan period dates (no `date.today()`/UTC).
- [ ] P2: `model-performance` issues **one** grouped query per metric for actuals
      (no per-point queries); date filters are half-open ranges, not `func.date(col) ==`.
- [ ] P2: trend split is date-sorted; "recent" = later half.
- [ ] P3a: Islamic holidays appear in `/annotations` for the covered years.
- [ ] P3b: dead trend-validation block removed.
- [ ] `python -m pytest tests/ -k "analytics"` green; dashboard load re-timed < 3s.
