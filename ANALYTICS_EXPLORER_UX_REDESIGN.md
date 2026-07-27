# Guided Analytics — UX Redesign for Non-Technical Administrators

**Delivered at** `/admin/analytics/explorer` **Branch** `feat/analytics-explorer-redesign`
**Status** implemented, wired into `main.py`, 26 tests passing

---

## 1. The core problem

The existing page asks the operator to *assemble a database query* out of five technical
controls:

| Control | What it means | What a ministry administrator hears |
|---|---|---|
| Data Source | which SQL table | "which table?" |
| Chart Type | line / bar / pie / box / treemap / funnel / heatmap / histogram / scatter | "pick a rendering strategy" |
| Granularity | `day` / `week` / `month` | — |
| Group By | a column name | — |
| Top N | `LIMIT` | — |

Nine chart types, five sources, three granularities and a free-text `group_by` is a space of
several hundred combinations, most of which are meaningless (`box` plot of `kindergartens`
grouped by `mood`). The interface offers no guidance on which are worth asking, and the
"Auto" default hands the decision to a statistical advisor whose reasoning is shown only as
an English tooltip.

Then the result is presented with no interpretation at all. The "Metric Insight" panel says:

> **الحوادث**
> الوحدة: count
> المستوى: national

That is a restatement of the request, not an explanation of the answer. An administrator
who wants to know *whether things are getting worse* is left to work it out from the bars.

**The redesign inverts the model: the operator picks a question in plain language; the
system chooses the aggregation, the chart, and the wording, and explains itself.**

---

## 2. Requirement 1 — Simplified workflows

### 2.1 Questions replace query-building

The five technical controls collapse into one list of eight plain-language questions:

| Question (AR) | Question (EN) |
|---|---|
| ما أنواع الحوادث التي وقعت؟ | What types of incidents happened? |
| ما مدى خطورة الحوادث؟ | How serious were the incidents? |
| هل تتزايد الحوادث عبر الوقت؟ | Are incidents increasing over time? |
| في أي محافظة تتركز الحوادث؟ | Which governorate has the most incidents? |
| ما نسبة حضور الأطفال؟ | What is the children's attendance rate? |
| ما وضع طلبات التسجيل؟ | Where do enrolment applications stand? |
| كيف كانت حالة الأطفال؟ | How were the children doing? |
| هل لدينا مقاعد شاغرة؟ | Do we have free seats? |

Each question owns its aggregation *and* its chart type on the server
(`analytics_explorer.py`, `QUESTIONS`). The operator never selects a chart type, a
granularity, a `group_by`, or a `top_n` — because there is no combination they can choose
that produces a meaningless chart.

### 2.2 A three-step spine

The rail is numbered, so the workflow is legible without instructions:

```
┌─ 1 Choose a question ─┐   ┌──────────── The answer ────────────┐
│ ● What types of…      │   │  6 incidents recorded — most       │
│ ○ How serious…        │   │  common was "Illness" at 33%       │
│ ○ Are incidents…      │   │  ▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬     │
├─ 2 Narrow it down ────┤   ├─ How to read this ─────────────────┤
│ [7d][30d][3m][1y]     │   │ 👁  What this shows                │
│ From ▤  To ▤          │   │ 🧮  How it is calculated           │
│ Governorate ▾         │   │ 🗄  Where the data comes from       │
├───────────────────────┤   │ ⚠  What is left out                │
│  ▶ Show the answer    │   ├─ Good next questions ──────────────┤
└───────────────────────┘   │ ( How serious were they? )         │
                            └────────────────────────────────────┘
```

Clicking a question runs it immediately — the "Show the answer" button exists for
re-running after a filter change, not as a required step.

### 2.3 Jargon eliminated

| Removed | Replaced by |
|---|---|
| Data Source | (folded into the question) |
| Chart Type × 9 | (chosen by the server) |
| Granularity, Group By, Top N | (chosen by the server) |
| "Auto" + confidence percentages | (gone — the system simply picks well) |
| "Metric Insight / Unit: count / Level: national" | a sentence: *"6 incidents recorded — most common was Illness at 33%"* |
| "records" meaning bar count | **"6 records counted"** and **"4 groups shown"**, side by side |

---

## 3. Requirement 2 — Contextual data education

Every answer ships with four explanations, authored per question, in both languages. This
is not tooltip text; it is a first-class panel titled **"How to read this / كيف تقرأ هذا الرسم"**.

For *What types of incidents happened?*:

> **👁 What this shows**
> This chart shows how many incidents were recorded in the selected period, broken down by
> the type of incident.
>
> **🧮 How it is calculated**
> 1) We take every incident whose date falls inside the selected period. 2) We exclude
> deleted incidents. 3) We group incidents of the same type together and count them.
> Each bar is a count of incidents of one type — not a percentage.
>
> **🗄 Where the data comes from**
> The incident log filled in by kindergartens, using the "incident occurred" date.
>
> **⚠ What is left out**
> The system automatically excludes any record belonging to a child outside the approved
> kindergarten age range, and excludes deleted records. The figure shown here can therefore
> be lower than the raw database count.

That last panel is the direct answer to audit finding **D-03** — the global child-age filter
that silently shrinks historical results. It was invisible in the old UI; now it is stated
on every affected question.

The explanations also pre-empt the specific misreadings each chart invites:

* **Governorate counts** — *"a raw count does not mean a governorate performs worse — larger
  governorates have more kindergartens and more children, and therefore naturally more
  incidents."*
* **Severity** — *"Severity is chosen by the reporting staff member — it is not computed
  automatically."*
* **Attendance** — *"the unit is 'one child on one day', not a number of children."*
* **Enrolment status** — *"status reflects the position now, not at submission time."*
* **Mood** — *"a subjective indicator entered by the teacher — read it as a general signal,
  not a diagnosis."*
* **Capacity** — *"this question reflects the present state, so it is not affected by the
  date period above."*

### The headline sentence

Every answer opens with a computed sentence, not a number:

```
سُجِّلت 6 حادثة، أكثرها «مرض» بنسبة 33%
6 incidents recorded — most common was "Illness" at 33%

2 من أصل 6 حادثة صُنِّفت مرتفعة أو حرجة (33%)
2 of 6 incidents were rated high or critical (33%)

سُجِّلت 6 حادثة، والاتجاه العام متزايد في النصف الثاني من الفترة
6 incidents recorded — the trend is rising in the second half of the period
```

The trend claim is defined in the explanation panel rather than left to interpretation:
*"The trend statement compares the total of the first half of the period against the second
half."*

---

## 4. Requirement 3 — Guided interactivity

### 4.1 Next steps are data, not decoration

Each answer returns a server-defined `next_steps` list — the follow-up questions that
actually make sense from where the operator is standing:

```
What types of incidents happened?
   → How serious were these incidents?
   → Are incidents increasing over time?
   → Which governorate has the most incidents?
```

Clicking one loads that question with the **current period and scope preserved**, then
scrolls the answer into view. A test asserts every `next_steps` target resolves to a real
question, so the graph cannot rot.

This replaces the old "Recommended" chips, which suggested a *chart type* for the same data
— restyling rather than progressing — and computed those suggestions over a different date
window than the one on screen (**F-07**).

### 4.2 Filters re-run immediately

Changing the governorate or a period chip re-runs the current question at once. No
"remember to press Analyze again" trap.

### 4.3 Shareable state

The URL is rewritten on every answer (`?question=…&date_from=…&date_to=…&governorate=…`) and
restored on load, so a link reproduces exactly what the sender saw.

### 4.4 Drill-down honesty

The old page advertised `drilldown.enabled: true` for incidents while the click handler was
hard-gated to `kindergartens` (**F-10**) — an affordance that never fired. The redesign
exposes geography as an explicit **question** (*"Which governorate has the most
incidents?"*) plus a governorate filter. Nothing is advertised that does not work.

---

## 5. Requirement 4 — Visual design

### 5.1 Self-contained tokens

Audit finding **F-01** was that the old page's entire custom visual layer silently vanished
because it referenced tokens from a stylesheet it never linked. The redesign defines its
own tokens under a page-scoped `.gx` root:

```css
.gx {
  --gx-ink: #0F172A;  --gx-ink-soft: #475569;  --gx-line: #E2E8F0;
  --gx-accent: #1D4ED8;  --gx-accent-wash: #EFF6FF;
  --gx-radius: 14px;
  --gx-shadow: 0 1px 2px rgba(15,23,42,.04), 0 8px 24px -12px rgba(15,23,42,.18);
}
```

It cannot break when a global stylesheet is reordered, renamed, or dropped.

### 5.2 Charts without a chart library

Bars are CSS; the trend line is inline SVG. No Plotly on this page.

This removes a 3.5 MB dependency and the SRI/CDN-fallback machinery around it, but the
reason is legibility, not weight. A horizontal bar with the label and the value on the same
line reads correctly in RTL with no tick-rotation, no truncated Arabic axis labels, and no
canvas that a screen reader cannot enter:

```
مرض                                    2  33%
▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓
إصابة                                  2  33%
▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓
سلوك                                   1  17%
▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓
```

Each bar carries its absolute value *and* its share of the total, so "is this a lot?" is
answered without arithmetic. The time-series view adds a stated peak in words — *"Highest
day: 2026-07-16 — 2 recorded"* — because that is the fact an administrator acts on.

### 5.3 Cognitive load

* One accent colour. Colour marks the selected question and the bars; it never encodes a
  category, so nothing depends on distinguishing ten hues.
* Numerals are tabular (`font-feature-settings: "tnum"`) so figures align down the column.
* Three panels in a fixed order — Answer, How to read this, Next questions — so the page
  shape never changes between questions.
* Loading is a skeleton in the shape of the eventual content, not a spinner.

### 5.4 Accessibility

* Questions are `aria-pressed` toggle buttons; period chips likewise.
* The chart container carries a generated `aria-label` enumerating every category and value,
  so the data is readable without seeing the bars.
* Visible `:focus-visible` rings; full keyboard operation.
* `prefers-reduced-motion` disables all transitions and the loading pulse.
* Body text at 13px/1.75 with ≥4.5:1 contrast on every text token.
* RTL is native — logical properties throughout, and the SVG line reverses its x-axis when
  `dir="rtl"`.

---

## 6. What the backend guarantees

`analytics_explorer.py` fixes, by construction, four defects the audit found in the legacy path:

| Guarantee | Legacy behaviour | Test |
|---|---|---|
| Window is half-open `[start, next_day)` | `occurred_at <= date_to` dropped the whole final day | `test_window_end_is_exclusive_midnight_of_the_next_day` |
| `records` and `groups` reported separately | bar count displayed as "records" | `test_records_and_groups_are_distinct_measures` |
| `as_of` is Jordan time | naive `datetime.now()` | `test_as_of_is_reported_in_jordan_time` |
| Every visible string carries `ar` + `en` | English from the server, Arabic guessed in the browser by substring match | `test_answer_payload_is_fully_bilingual` |

Plus: days with zero incidents are emitted as zero rather than dropped, so a gap in the
timeline means "no incidents", not "no data"
(`test_daily_series_has_no_gaps`).

### API

```
GET /api/admin/analytics/explorer/questions
GET /api/admin/analytics/explorer/answer?question=&date_from=&date_to=&governorate=&kindergarten_id=
GET /admin/analytics/explorer                     ← the page
```

Response shape:

```json
{
  "headline":  { "ar": "سُجِّلت 6 حادثة، أكثرها «مرض» بنسبة 33%",
                 "en": "6 incidents recorded — most common was “Illness” at 33%" },
  "chart":     { "type": "bar", "categories": [ { "label": {"ar":…,"en":…}, "value": 2 } ],
                 "value_axis": {…}, "category_axis": {…} },
  "explanation": { "what": {…}, "how": {…}, "origin": {…}, "excluded": {…} },
  "coverage":  { "records": 6, "groups": 4,
                 "period": {…}, "scope": {…}, "scope_level": "national",
                 "as_of": "2026-07-27T10:18:07+03:00" },
  "next_steps": [ { "label": {…}, "question": "incidents_by_severity" } ]
}
```

The browser picks `ar` or `en`. It never translates, never pattern-matches, never falls back.

---

## 7. Files

| File | Role |
|---|---|
| `analytics_explorer.py` | **new** — question catalogue, builders, bilingual text, API |
| `templates/admin/analytics/explorer.html` | **new** — the page |
| `test_analytics_explorer.py` | **new** — 26 tests |
| `main.py` | +3 lines — router registration |
| `charts_api.py`, `charts/service.py`, `charts/tasks.py`, `charts/cache.py`, `charts/advisor.py` | audit fixes + dead-code removal |
| `charts/builders/`, `charts/colors.py`, `charts/service.py.bak` | **deleted** — dead |

**On file placement.** Python modules, tests and reports are at the repository root, matching
both the instruction and this repo's existing layout (`analytics_service.py`, `charts_api.py`,
`kpi_service.py` all sit at root). The template must stay under `templates/` because
`Jinja2Templates(directory="templates")` in `scripts/compat/frontend_orig.py:79` resolves
names against that root — a template at the repository root is unreachable by the loader.
Same for `static/`. Placing them elsewhere would not work, so I kept them where the framework
requires and flagged it here rather than silently diverging.

**Language consistency.** Backend is Python throughout. The page needs browser code, which
is necessarily JavaScript — kept to one vanilla ES5-compatible IIFE with no framework and no
build step, matching the project's existing vanilla-JS convention.

---

## 8. Verification

```
39 passed in 1.00s

authenticated, via TestClient:
  200  GET /api/admin/analytics/explorer/questions   → 8 questions
  200  GET /api/admin/analytics/explorer/answer      → records 6 / groups 4
                                                       as_of 2026-07-27T10:18:07+03:00
  200  GET /admin/analytics/explorer                 → 47,894 bytes
       8 question buttons, 4 governorate options, 0 unrendered Jinja
  401  all three, unauthenticated
```

All eight question builders were executed against the live database; every one returns a
coherent bilingual answer.

---

## 9. Governorate matching — a defect found while completing the filters

Building the kindergarten picker surfaced a bug in the legacy scoping logic that I had
initially copied. The capital is stored in this database as **`عمان`**, but the legacy
loader rewrites every alias to a single winner:

```python
gov = "العاصمة" if req.governorate.lower() in ("amman", "عمان", "العاصمة") else req.governorate
```

So filtering by the capital rewrites `عمان` → `العاصمة`, which matches no row:

```
BEFORE  input='عمان'    -> resolved='العاصمة'  records=0
        input='amman'   -> resolved='العاصمة'  records=0
AFTER   input='عمان'    -> matches ('عمان','العاصمة')  records=2
        input='amman'   -> matches ('عمان','العاصمة')  records=2
```

The fix treats the spellings as **synonyms matched with `IN`** rather than picking a winner,
so it is correct whichever spelling a deployment holds. The English alias is an input
convenience and never reaches the query. Guarded by
`test_every_amman_spelling_matches_both_stored_names` and by a partition test asserting that
the per-governorate slices sum exactly to the national total — no row lost, none
double-counted.

**The same defect is still live in `charts/service.py`**, in all four loaders
(`_load_incidents`, `_load_attendance`, `_load_daily_reports`, `_load_enrollments`,
`_load_kindergartens`). Any governorate drill-down on the legacy page returns zero rows on
this data. Logged as **[B-18]**.

---

## 10. Now complete

* **Sidebar entry** — *التحليلات الموجَّهة / Guided Analytics* under *Analytics & Reporting*,
  immediately above the legacy Charts Explorer.
* **Kindergarten picker** — a dependent dropdown fed by
  `GET /api/admin/analytics/explorer/kindergartens?governorate=`, loaded on demand rather
  than embedded so the page stays small on a national deployment. Selecting a governorate
  refilters it; both selections survive a shared link.
* **Accessibility** — the answer heading and chart region carry real text before JavaScript
  populates them, clearing two `axe-linter` errors (`empty-heading`, `role-img-alt`).

## 11. Still deliberately not done

* **The legacy page is untouched and still served** at `/admin/analytics/charts`. Replacing
  it is a migration decision, not an audit finding — the new surface runs alongside it so
  the two can be compared on real usage before anything is retired.
* **`charts/stats.py`'s six unused exports were left in place** — outside this page's blast
  radius, and removing them belongs with a broader sweep.
* **[B-18] is documented, not fixed.** Correcting governorate matching inside
  `charts/service.py` changes what the legacy page returns for every geographic filter; that
  is a behaviour change on a live surface and should be its own reviewed edit.
