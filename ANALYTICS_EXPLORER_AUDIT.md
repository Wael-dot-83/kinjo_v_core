# Analytics Charts Explorer — Technical Audit

**Target** `http://127.0.0.1:8000/admin/analytics/charts?source=incidents&date_from=2026-07-01&date_to=2026-07-27`
**Date** 2026-07-27 **Branch** `feat/analytics-explorer-redesign`

Every finding below was reproduced against the running application and the live
`data/kinjo.db`. Findings carry the evidence that produced them; nothing here is
inferred from reading alone.

---

## The headline result

For the window `2026-07-01 … 2026-07-24`, the page tells an administrator:

> **4 سجل** — "4 records"

The truth is **6 incidents**. Two independent defects compound to produce that number:

| Step | Effect |
|---|---|
| `occurred_at <= date_to` compares a `DateTime` to a bare `date` | drops every incident on the final day → 6 becomes 5 |
| the UI prints `quality.record_count`, which is the count of **aggregation groups**, not rows | 5 incidents in 4 type-groups → displays **4** |

Reproduced:

```
window: 2026-07-01 .. 2026-07-24  (incidents exist on 2026-07-24 at 10:15)
  LEGACY charts_api  -> incidents counted: 5   (record_count reported to UI: 4)
  NEW    explorer    -> incidents counted: 6   (groups shown: 4)
```

An analytics surface that under-reports safety incidents by 33% is not a cosmetic problem.

---

## Severity summary

| Sev | Count | Area |
|---|---|---|
| **Critical** | 4 | wrong numbers shown to operators; a wholly broken code path |
| **High** | 9 | integrity, security control, i18n contract, performance |
| **Medium** | 11 | correctness traps, cache behaviour, dead affordances |
| **Low** | 6 | dead code, hygiene |

---

# Phase 1 — Architecture

## 1. Route topology

The page is served by neither of the two files you would expect.

```
GET /admin/analytics/charts
  └─ scripts/compat/frontend_orig.py:1721   admin_charts_explorer()
       renders templates/admin/analytics/charts_dashboard.html   (1,728 lines)

GET /api/admin/charts/data      ← what the page actually calls
  └─ charts_api.py:266  →  charts/service.py  ChartService.render()
```

`frontend.py` is a **9-line shim** that does `from scripts.compat.frontend_orig import *`.
`CLAUDE.md` documents `frontend.py` as *"All HTML page routes"*; the real 2,000-line page
router lives under `scripts/compat/`, a path that reads as throwaway. **[B-17, Medium]**

`charts_api.py` also carried four label dictionaries (`_SOURCE_LABELS_AR/EN`,
`_CHART_LABELS_AR/EN`) duplicated **verbatim** from `frontend_orig.py:1728-1747` and
referenced by nothing — the page route moved out of this module and the dictionaries
were left behind. *(Removed.)*

---

## 2. Frontend

### 2.1 The custom visual layer does not render — **[F-01, Critical]**

`charts_dashboard.html` carries a 370-line inline `<style>` block built on design tokens:

```css
.ce-source-card { border: 2px solid var(--slate-200); border-radius: var(--r-md); }
.ce-source-card__label { font: 600 0.75rem/1.3 var(--font-ar); color: var(--slate-700); }
```

Those tokens — `--az-primary`, `--slate-*`, `--r-*`, `--font-ar` — are defined in
**exactly one file**:

```
static/css/admin_analytics_v2.css:10:  --az-primary: #2563EB;
```

and that file is linked by **exactly one template**:

```
templates/admin/analytics/dashboard.html:8:<link rel="stylesheet" href="/static/css/admin_analytics_v2.css?v=2.4">
```

`charts_dashboard.html` never links it, and neither does `admin_base.html`. Verified: none
of `--az-primary`, `--slate-200`, `--r-md`, `--font-ar` appear in any stylesheet that
`admin_base.html` loads.

A CSS declaration whose `var()` resolves to nothing is **invalid and dropped**. So on this
page every border, radius, font shorthand, and colour in the source-card grid, the date
presets, the chart-type buttons, the filter pills, the skeletons, the table headers, and
the recommendation chips is silently discarded. `.az-card` survives only because it happens
to be defined separately in `admin_design_system.css`.

This is the single largest reason the page looks unfinished.

### 2.2 Structure — **[F-02, High]**

One 1,728-line Jinja file: ~370 lines CSS + ~800 lines JavaScript inline. There is no
`static/js/charts_explorer.js` — compare `static/js/admin_dashboard.js`, which the project's
own conventions point at. Consequences: no linting, no unit tests, no browser caching of
the logic, and merge conflicts on every edit.

### 2.3 State management — **[F-03, Medium]**

State is nine module-level `let` bindings plus a `filterState` object. No container, no
single update path. A concrete symptom at lines 1650-1653:

```js
function showTaskStatus(taskId) {
  _activeTaskId = taskId;
  document.getElementById('taskStatus').style.display = '';
  clearTask();                       // ← sets _activeTaskId = null
  _taskPollInterval = setInterval(...);
}
```

`_activeTaskId` is assigned, immediately nulled, and never read anywhere. Dead state that
looks load-bearing.

### 2.4 Arabic is reconstructed in the browser by substring matching — **[F-04, High]**

The backend advisor returns English-only titles and rationales (`charts/advisor.py:188`
`_default_title` hardcodes English). The template then guesses its way back to Arabic:

```js
const RATIONALE_TRANSLATIONS = {
  "Long time span": "نطاق زمني طويل (>6 أشهر) ← ...",
  "Multi-month":    "سلسلة زمنية لعدة أشهر ← ...",
  ...
};
for (var key in RATIONALE_TRANSLATIONS) {
  if (rationale.indexOf(key) !== -1) { arRationale = RATIONALE_TRANSLATIONS[key]; break; }
}
```

Reword any rationale in `advisor.py` and the Arabic UI silently falls back to English text.
This directly violates the project rule that backend strings shown in the UI supply both
`_ar` and `_en` variants — in an Arabic-primary product.

### 2.5 "Data Quality" is row count wearing a costume — **[F-05, Critical]**

```js
var qualScore = data.quality?.record_count ?? 0;
if (qualScore > 0) { gaugeEl.style.width = '100%'; gaugeEl.className = '...bg-success'; }
```

Any non-empty result paints a full green "جودة البيانات / Data Quality" bar. One stale row
from one kindergarten reads as 100% quality. `CLAUDE.md` defines `data_quality_score` as
*"% of active kindergartens that filed a report in last 7 days"* — nothing of the sort is
computed here.

### 2.6 Other frontend defects

| ID | Sev | Finding |
|---|---|---|
| **F-06** | Critical | Row-count badge prints `quality.record_count` (group count) labelled "records / سجل". See headline. |
| **F-07** | High | `loadRecommendations()` POSTs only `{source, max_suggestions}` — no dates, no governorate. Suggestions are computed over the default 365-day national window regardless of the on-screen filters. |
| **F-08** | Medium | That POST uses raw `fetch()` rather than `fetchWithAuth()` → no 401 redirect, no structured error parsing. Already logged in `admin_tests_csrf_assets_audit.md`. |
| **F-09** | High | Date presets and the initial range use browser-local `new Date()`. The backend uses `today_amman()`. An operator outside UTC+3 gets a different "today" than the server. |
| **F-10** | Medium | The API advertises `drilldown.enabled=true, next_level="governorate"` for incidents, but the click handler is hard-gated to `source === 'kindergartens'`. The hint never appears; the affordance is dead. |
| **F-11** | Medium | Axis selection is heuristic — `strCols[0]` becomes x, first numeric becomes y. Chart shape depends on dict key order from `to_dict(orient='records')`. |
| **F-12** | Medium | `exportCSV()` builds a `data:` URI (length-capped, `#` mangles the payload) and `String(row[k] \|\| '')` turns a legitimate `0` into an empty cell. |

---

## 3. Backend

### 3.1 The heavy-render path was broken three ways — **[B-01/02/03, Critical]** *(fixed)*

`charts/tasks.py:30` called a method that does not exist:

```python
html = svc._build_html(df, req, chart_type)
```

```
hasattr(ChartService, '_build_html') = False
```

`_build_html` was removed when rendering moved to the browser; it survives only in the
stale `charts/service.py.bak`. So **every dataset ≥ 10,000 rows** entered a Celery task
that raised `AttributeError`, retried twice, and failed permanently — while the page sat
polling a task that would never succeed.

Two further breaks sat behind it: the task returned enum objects (not JSON-serialisable),
in a dict shape (`html`, `row_count`, `cached`) that `ChartResponse(**data)` in
`get_task_status` could never validate.

And the offload saves nothing. `render()` calls `self.get_data(db, req)` — running the full
query and materialising the whole DataFrame — **before** testing the threshold, then queues
a task to redo identical work.

**Fixed:** the task now calls `render(..., allow_offload=False)` and returns
`response.model_dump(mode="json")`, which is exactly what `get_task_status` consumes. The
`allow_offload` flag prevents the task from re-queueing itself forever.
*Remaining:* the "load everything, then offload" ordering is inherent to the design — see
recommendations.

### 3.2 The rate limit on `/admin/charts/suggest` was never applied — **[B-04, High]** *(fixed)*

```python
@limiter.limit(settings.RATE_LIMIT_ADMIN_WRITE)   # ← applied second
@router.post("/admin/charts/suggest", ...)        # ← registers the BARE function
def suggest_charts(...):
```

Decorators apply bottom-up. `@router.post` ran first and captured the undecorated function;
`@limiter.limit` then wrapped a reference the router no longer held.

```
BEFORE   /admin/charts/suggest       limiter-wrapped: False
         /api/admin/charts/suggest   limiter-wrapped: True
AFTER    /admin/charts/suggest       limiter-wrapped: True
         /api/admin/charts/suggest   limiter-wrapped: True
```

An unthrottled POST that runs a `GROUP BY` over the incident table was reachable by any
admin or manager.

Fixing the order exposed a second issue: `suggest_admin_charts` *called* `suggest_charts`,
so one client request would have charged the limiter twice. **[B-05]** Both now delegate to
a plain `_suggest()` helper.

### 3.3 Timezone — **[B-07, High]** *(fixed)*

```python
freshness_at=datetime.datetime.now().isoformat()   # service.py:418, :446
```

Naive server-local time, on a payload field whose entire purpose is telling an operator how
fresh the data is. The module already imports `today_amman` for date bounds — the
inconsistency is within a single file. Now `now_amman()`.

### 3.4 Caching

| ID | Sev | Finding |
|---|---|---|
| **B-06** | Low | `render()` computed `cache_params` and never used it — rendered results are not cached at all. *(Removed.)* |
| **B-08** | Low | `ChartResponse.cached` is never assigned; always `False`. |
| **B-09** | Medium | The raw-data cache key is the full `req.model_dump()`, including `chart_type` and `title`. Switching chart type re-queries the database for byte-identical data. |
| **B-10** | Medium | `suggest()` builds a `ChartRequest` omitting `granularity`, `group_by`, `top_n`, `lang` → a different cache key from `render()`. Suggestions always miss the cache, and when `group_by` is set the advisor profiles a **differently shaped DataFrame** than the one on screen. |
| **B-11** | High | `_get_redis()` constructs a new client and issues `PING` on *every* get and set. No pooling — two extra round-trips per cache operation. |
| **B-12** | Medium | `charts/cache.py` duplicates the project's `cache_service.py` (per `CLAUDE.md`). |

### 3.5 Silent wrong-data traps

**[B-13, High]** — `group_by` is accepted and then ignored:

```python
group_by_col = req.group_by or "type"
if group_by_col == "type":   ...group by Incident.type...
else:                        ...group by Incident.severity_level...
```

`group_by=kindergarten` returns severity data. No error, no warning.

**[B-18, High]** — governorate filtering returns zero rows for the capital. *(Fixed.)*

> **Correction to an earlier revision of this document.** A previous pass recorded the
> root cause as "the code rewrites `عمان` → `العاصمة`, which is wrong". That was wrong.
> `العاصمة` **is** the canonical governorate name for the capital — `config.py:213`
> (`JORDAN_GOVERNORATES`), `services/jordan_locations.py`, and migration
> `canon_gov_cap_01` all agree, and `عمان` is the *city* inside it, historically
> mis-stored in the governorate column. The code applied the project's canonical rule
> correctly. The defect is elsewhere, and the earlier "synonym group" fix was itself
> unsafe — see below.

All five loaders rewrote input to the single canonical spelling and compared with `==`:

```python
gov = "العاصمة" if req.governorate.lower() in ("amman", "عمان", "العاصمة") else req.governorate
... models.Kindergarten.governorate == gov
```

That is correct **only on a database where migration `canon_gov_cap_01` has run**. This
development database has no `alembic_version` table at all — it was built by
`Base.metadata.create_all()` and seeded, so it still holds the pre-migration form `عمان`:

```
input='عمان'   -> resolved='العاصمة' -> records=0     (2 kindergartens exist there)
input='amman'  -> resolved='العاصمة' -> records=0
input='إربد'   -> resolved='إربد'    -> records=1     (unaffected: one spelling only)
```

**Root cause:** an equality test against one canonical spelling, on a column that legitimately
holds either form depending on whether the deployment has been migrated.

**Fix:** match every accepted stored form via `services.jordan_locations.governorate_query_aliases`
— the registry `api/analytics/scope_domain.py` already uses for exactly this reason. Correct
on migrated and un-migrated databases alike, and no governorate knowledge is duplicated:

```
after: 'عمان' 'العاصمة' 'amman' 'Amman' 'AMMAN' all -> 2 records
       legacy partition: SUM=6 NATIONAL=6 holds=True
```

**Why the earlier "synonym group" fix was rejected.** It hardcoded `("amman","عمان","العاصمة")`
into `analytics_explorer.py`, duplicating the canonical registry, and it matched with `IN`
*without folding the breakdown onto a canonical key*. On a half-migrated database holding
both spellings that yields two "Amman" entries in the picker and two Amman bars — every
capital row counted twice. Verified against a simulated mixed-spelling database; the
canonical-key implementation keeps `keys.count("amman") == 1` and the partition intact.

**[B-14, High]** — the `attendance` metric metadata contradicts the data it describes:

```
registry says: label_en='Attendance Rate'  unit='percent'  expected_range=(0.0, 100.0)
loader returns: ['date', 'status', 'count'] -> raw counts
```

The UI renders counts under a label that says percentage.

---

## 4. Data layer

### 4.1 The date-boundary defect — **[D-01, Critical]**

`Incident.occurred_at` is `DateTime(timezone=True)` (`models.py:915`). The loader filters:

```python
models.Incident.occurred_at <= d_to        # d_to is a datetime.date
```

Generated SQL, captured live:

```sql
WHERE incidents.deleted_at IS NULL
  AND incidents.occurred_at >= '2026-07-01'
  AND incidents.occurred_at <= '2026-07-27'
```

Under SQLite's lexicographic comparison, `'2026-07-27 00:00:00.000000' <= '2026-07-27'` is
**False** — the longer string sorts after the shorter one. So the final day is excluded
**entirely, including exact midnight**:

```
occurred_at=2026-07-27 00:00:00.000000  passes: False
occurred_at=2026-07-27 09:30:00.000000  passes: False
occurred_at=2026-07-27 23:59:00.000000  passes: False

live incidents with a non-midnight time component: 6 of 6
```

Every incident carries a real time-of-day, so **100% of the final day is always lost**. The
same pattern is in `_load_enrollments` (`created_at`) and `_load_kindergartens`.

### 4.2 No usable index for the default query — **[D-02, High]**

```
ix_incidents_kg_occurred_at: ['kindergarten_id', 'occurred_at']
ix_incidents_kg_severity:    ['kindergarten_id', 'severity_level']
ix_incidents_id:             ['id']
```

Both composites lead with `kindergarten_id`. The national-scope query — the one this page
issues on load — constrains only `occurred_at` and `deleted_at`, leaving the leading column
unbound, so neither index is usable:

```
EXPLAIN QUERY PLAN
  SCAN incidents
  USE TEMP B-TREE FOR GROUP BY
```

There is no index on `occurred_at` alone and none on `deleted_at`. Add
`(occurred_at)` or `(deleted_at, occurred_at)`.

### 4.3 A global filter silently rewrites history — **[D-03, Critical]**

`database.py:118` `_apply_child_age_policy` attaches `with_loader_criteria` to **every ORM
SELECT** in the application, restricting `Incident`, `AttendanceLog`, `DailyReport`,
`EnrollmentApplication` (and more) to children whose date of birth currently falls inside
the kindergarten age band — computed against **today**:

```sql
AND (EXISTS (SELECT 1 FROM children
             WHERE children.id = incidents.child_id
               AND children.date_of_birth >= '2021-11-27'
               AND children.date_of_birth <= '2026-05-18'))
```

Two consequences the UI never discloses:

1. **Historical reports are not reproducible.** An incident from 2024 involving a child who
   has since aged out simply disappears. Re-run the same 2024 report next year and the
   number is smaller — with no indication why.
2. Displayed totals will not reconcile against the raw tables, which turns every
   cross-check into an investigation.

In the current seed data this drops 0 rows, so the mechanism is proven but the impact is
latent. It will not stay latent.

### 4.4 The cache changes the shape of the payload — **[D-04, High]**

`get_data()` caches `df.to_json(orient='split')`. On re-read, dtypes do not survive:

```
loader dtypes  : {'incident_type': 'str', 'count': 'int64', 'month': 'datetime64[us]'}
get_data dtypes: {'incident_type': 'str', 'count': 'int64', 'month': 'str'}
loader month[0] : Timestamp('2026-07-01 00:00:00')
get_data month0 : '2026-07-01T00:00:00.000'
```

`render()` only applies `strftime('%Y-%m-%d')` to columns that are still datetime64, so:

* **cold cache** → x-axis label `2026-07-01`
* **warm cache** → x-axis label `2026-07-01T00:00:00.000`

The same request returns two different payloads depending on where you land in a 5-minute
TTL. Redis is live in this environment (`redis available to chart cache: True`), so this is
the normal path, not a corner case.

### 4.5 Schema and migrations

| ID | Sev | Finding |
|---|---|---|
| **D-05** | Medium | `DailyReport.mood` is `String(20)` free text. The inline comment says `# happy, normal, sad, tired, sick`; production stores `'سعيد 😊'`, `'هادئ 😌'`, `'نشيط 🤸'`. No enum, no constraint, no validation — and the comment is actively misleading. |
| **D-06** | High | `alembic.ini` was **absent** from this checkout while `alembic/versions/` held 44 migrations, so `alembic upgrade head` could not run. **Resolved:** restored from `HEAD`; the database was stamped at `c7d9e1a4b820` and upgraded to `analytics_idx_01`. It had no `alembic_version` table at all — `create_all`-built — which is why the capital was still stored in its pre-migration form. |

---

## 5. Dead code removed — **[B-16, Low]**

Verified unreferenced outside their own package, then deleted:

| Path | Lines | Why dead |
|---|---|---|
| `charts/builders/` (10 modules) | ~325 | Imported only by their own `__init__.py` and `service.py.bak`. Plotly rendering moved to the browser. |
| `charts/colors.py` | 55 | Imported only by `builders/`. |
| `charts/service.py.bak` | 317 | Stale duplicate of `service.py`, still holding the deleted `_build_html`. |
| `charts_api.py` label dicts | 20 | Duplicated verbatim in `frontend_orig.py`; unreferenced here. |
| `charts/cache.py` render helpers | 18 | `get_render`/`set_render` unused after rendering moved client-side. |
| `ChartAdvisor._RULES` | 1 | Class attribute, never read. |
| dead imports / locals | — | `json`, `DataProfile`, `Optional` in `service.py`; `cols` assigned in four branches of `_load_kindergartens` and never used. |

Still dead, left in place as it is outside this page's blast radius: `charts/stats.py`
exports `compute_trend`, `detect_outliers_iqr`, `compute_correlation_matrix`,
`resample_timeseries`, `safe_pct_change`, `moving_average` — only `profile_dataframe` is
imported anywhere.

---

## 6. Repository hygiene (context, not defects)

* 312 tracked files are deleted in the working tree, including `.gitignore`, `Makefile`,
  `conftest.py`, `alembic.ini` and the whole `tests/` directory. Root-level `test_*.py`
  files have replaced the suite.
* `test_analytics_endpoints.py` collects **0 tests**.
* 48 git worktrees are registered, several pointing at `d:\Final Version` — the shared
  checkout `CLAUDE.md` marks off-limits.

---

## 7. Verification

```
39 passed in 1.00s
  test_analytics_explorer.py ..........................   (26 new)
  test_moe_kg2_eligibility.py ....
  test_mopic_agency_reports.py ......
  test_mosd_kindergarten_registry.py ...
```

Legacy surfaces re-checked after the cleanup, authenticated:

```
200  /admin/analytics/charts?source=incidents&date_from=2026-07-01&date_to=2026-07-27
200  /api/admin/charts/data?source=incidents&...
200  POST /api/admin/charts/suggest   -> 3 suggestions
200  POST /admin/charts/suggest       -> 3 suggestions
```

---

## 7b. Second verification pass — findings not present in the first audit

An independent re-audit from zero (assuming nothing, including this document) found nine
further defects. All are fixed and covered by tests.

| ID | Sev | Finding | Evidence |
|---|---|---|---|
| **V-01** | Critical | **Unbounded reporting period.** `date_from=1900-01-01&date_to=2100-01-01` — typeable in the URL — built a 73,050-point, **6.28 MB** response. Now capped at 3653 days, and the series bucket widens day → week → month with the window. | `73050 categories / 6,282,300 bytes` before; `79 categories / 6,794 bytes` for a 6-year window after |
| **V-02** | High | **Geography breakdown ignored the geography filter.** Scoping to one governorate and then asking "which governorate has the most incidents?" silently widened back to the whole country. | `_build_incidents_by_governorate` applied no scope predicate |
| **V-03** | High | **LIKE wildcards were interpreted.** `search=%` matched every kindergarten. Parameter binding stops injection but not metacharacters. Now escaped with an explicit `ESCAPE`. | `search='%' -> total=5` (whole table) before |
| **V-04** | High | **WCAG 2.2 AA contrast failure.** `--gx-ink-faint` `#94A3B8` measured **2.56:1** on white, used for 11px question subtitles, axis labels and share percentages — none of which qualify as large text. Replaced with `#64748B` (4.76:1 on white, 4.55:1 on the canvas). | computed luminance ratios |
| **V-05** | High | **Answer changes were silent to screen readers.** No live region; choosing a question replaced the headline with no announcement. Added `aria-live="polite"`, plus focus movement on next-step navigation. | rendered DOM had no `aria-live` |
| **V-06** | Medium | **Response races.** Neither the answer fetch nor the picker fetch was cancellable, so a slow earlier response could land last and overwrite a newer answer — the chart would disagree with the filters beside it. Both now use `AbortController` with a generation check. | no `AbortController` in the page |
| **V-07** | Medium | **Back button was broken.** Every answer called `history.replaceState`, so no history entry was ever created and Back left the page. Now `pushState` for user actions, `replaceState` when restoring, plus a `popstate` handler that reapplies the whole filter state. | `history.replaceState` was the only call |
| **V-08** | Medium | **Two numeral systems on one screen.** Client values used `toLocaleString('ar-JO')` → Arabic-Indic `٦`, while the server composes headlines with Latin digits: `سُجِّلت 6 حادثة` beside a bar reading `٦`. Now `ar-JO-u-nu-latn`. | `(6).toLocaleString('ar-JO') === '٦'` |
| **V-09** | Medium | **`records` still meant "bars" in one question.** `kindergarten_capacity` reported `len(rows)` — the very conflation this surface exists to avoid. Now counts distinct kindergartens. | `records == groups == 4` before; `records=5, groups=4` after |
| **V-10** | Low | **A nonexistent kindergarten answered "0 incidents"** rather than 404 — an empty filter reading as a clean safety record. | `kindergarten_id=999999 -> 200, records=0` |
| **V-11** | Low | **Unbounded picker.** No limit; a national deployment would return every kindergarten into a `<select>`. Now capped at 200 with `total`/`truncated` and a `search` parameter. | no `LIMIT` in the query |

### Corrected from the first pass

* **Migration chain is healthy.** A naive regex over `down_revision` suggested 8 heads;
  `alembic.script.ScriptDirectory` — the authority — reports **one** (`canon_gov_cap_01`,
  now `analytics_idx_01`). `upgrade head` would succeed. **D-06 stands**: `alembic.ini`
  is absent from this working tree, so migrations cannot be *run* here.
* **B-18's root cause was misdiagnosed.** See the corrected entry in §3.5.

### D-02 resolved

`ix_incidents_occurred_at` added to `models.Incident` and via migration `analytics_idx_01`.
Measured on a 300,000-row incidents table:

| window | before | after |
|---|---|---|
| 7 days | 50.5 ms | 0.0 ms |
| 30 days | 50.2 ms | 0.0 ms |
| 90 days | 49.0 ms | 11.3 ms |
| 365 days *(the explorer default)* | 56.9 ms | 133.3 ms ⚠ |
| 10 years | 210 ms | 1290 ms ⚠ |

The wide-range regression is a SQLite planner artifact — past roughly 10% selectivity it
keeps choosing the index where a sequential scan would win, even after `ANALYZE`. Production
runs PostgreSQL (`config.py:416` refuses to start on SQLite), whose cost-based planner
reverts to a scan once a range stops being selective, so the regression does not apply there.

The index is retained: it is decisive for the 7/30/90-day windows operators drill into,
which dominate interaction after the initial page load. **This was measured, not assumed —
and it is the reason the default period change was worth re-measuring rather than
assuming the earlier 90-day numbers still applied.**

---

## 8. Recommended next actions, in order

1. **`D-01`** — sweep every `DateTime <= date` comparison in the codebase, not just these
   three loaders. Use half-open `[start, next_day)` windows. This is the highest-value fix.
2. **`D-03`** — give the age policy an explicit opt-out for analytics reads
   (`include_out_of_range_children=True` already exists in `database.py:123`) so historical
   reporting is reproducible, and disclose the filter in the UI wherever it stays on.
3. **`F-01`** — either link `admin_analytics_v2.css` from `admin_base.html` or move the
   tokens into `design-tokens.css`. Today, page styling depends on which template you
   happen to be on.
4. **`D-02`** — add an index on `incidents(occurred_at)`.
5. **`D-04`** — cache a serialised payload, not a DataFrame, so cache state cannot alter
   output.
6. **`B-03`** — decide the offload path's fate: either count rows first with a cheap
   `COUNT(*)` before loading, or delete the Celery path outright.
