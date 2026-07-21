# KinJo Admin — UI/UX Specification

**Version:** 1.0 · **Date:** 2026-07-21 · **Status:** Design handoff
**Live artifact:** https://claude.ai/code/artifact/7b9871b2-7d98-444f-93d2-d83ccf74c6a5

A production-ready design specification for the KinJo admin platform — bilingual
(Arabic-primary, RTL-first), role-aware, tuned so a non-technical administrator reads
the day's health in under 30 seconds. **Grounded in the system as it actually exists in
the repository, not a generic template.**

| | |
|---|---|
| **Stack** | FastAPI · Jinja2 · Vanilla JS ES6 · Bootstrap 5.3 RTL · Chart.js 4 |
| **Roles** | Admin · Manager · Supervisor · Parent (`UserRole` enum) |
| **Language** | ar (primary) / en · RTL + LTR |
| **Locale** | Amman · Jordan UTC+3 |

---

## 00 · Scope decisions & assumptions

Four branch points were resolved before writing this spec, because the brief's template
defaults (Vue/Directus, a Finance module, a Teacher role) diverged from the actual KinJo
codebase.

| Decision | Resolved as | Consequence |
|---|---|---|
| Target stack | **Actual stack** — FastAPI + Jinja2 + Vanilla JS + Bootstrap 5.3 RTL + Chart.js 4 | Component contracts and handoff map to real macros and `--kinjo-*` tokens in the repo. |
| Module set | **Real modules only** | No Finance/Payments module is specced — it does not exist. |
| Roles | **Admin · Manager · Supervisor · Parent** | Matches `UserRole`. No speculative Teacher persona; Manager is the KG-level operator. |
| Delivery | **Published artifact** + this Markdown | Browsable spec that renders its own palette, type scale, and live component mockups. |

### Confirmed with stakeholder (2026-07-21)

- **Role hierarchy is nested by scope** — Admin (platform) ⊃ Manager (one whole
  kindergarten) ⊃ Supervisor (one class within that KG) ⊃ Parent (own child). Each level
  sees strictly less than the one above.
- **Manager = one kindergarten** — sees *only their own KG* (all its classes). No
  governorate selector, no cross-KG data; server-enforced, not just hidden.
- **Supervisor = one classroom** — belongs to a single kindergarten, is responsible for
  *one assigned class of a few children*, and their core job is **filling in the daily report**
  (one per present child). Hard-scoped server-side to one `kindergarten_id` *and* one assigned
  `class_id`; not an oversight/cluster role.
- **Daily-report workflow & approval is Manager-owned** (approved *target* rule) — Supervisor
  drafts & submits → Manager reviews/edits and sends to the Parent → Parent sees it only after
  sending; the Admin monitors but never approves. *The codebase only partially enforces this
  today* — §05 splits verified behavior from the gaps (legacy Admin-permitting `/approve`, no
  mandatory approve gate, no reject/return endpoint, report events not wired to the WS channel).
- **Real-time: yes** — alerts and dashboard values are pushed live over a persistent
  transport (WebSocket, SSE fallback), not polled. The 30s cache backs the initial paint
  and cold loads; live events invalidate and repaint affected widgets.
- **Notifications: yes** — an active notification system: real-time in-app center
  (badge + toast on arrival) plus per-user delivery preferences; every notification is
  backed by an audit/alert record and deep-links to its source.
- **Governorate selector is Admin-only** — Manager and Supervisor are both hard-scoped and
  see no selector; Admin is the only role with cross-KG / cross-governorate scope.

### Still open (confirm)

- **Notification channels beyond in-app** — email / SMS / push are specced as opt-in per
  user; confirm which are wired for launch vs. roadmap.
- **Ranked pain points** are inferred from prior audits; confirm your own top-3.

---

## 01 · UX audit & problem identification

Grounded in defect classes this platform has actually produced. The recurring theme is a
**trust gap**: the interface frequently answers a *different* question than the one asked
while returning a confident `200`, and the operator can't see it.

### The dominant defect class — "silent lies"

A UI element that silently degrades instead of failing loudly:

- A filter whose value fails to parse is dropped, so the view returns **everything** rather
  than the requested subset — and looks valid.
- A "Custom" date-range button that never sends its dates, silently falling back to a default window.
- KPI cards that render a raw count with a colored good/bad status band it hasn't earned.
- Dropdowns offering phantom options that map to no real query.

> **Design mandate.** Every control must make its *current scope visible and its failure
> legible*. If a filter can't be applied, the UI says so — it never quietly widens the
> result set.

### Common pitfalls, mapped to this product

| Area | Observed friction | Spec response |
|---|---|---|
| Hierarchy | KPI overload; raw counts styled as graded scores. | Tiered layout: ≤4 hero KPIs; neutral styling for raw counts, graded color only for true scores (§03). |
| Navigation | Dead/placeholder breadcrumbs on 10+ pages; IIFE-trapped controls; mixed module rows. | One live, route-derived breadcrumb (§02); no orphaned controls (§07). |
| Visual clutter | System Alerts shipped unstyled (CSS/JS class mismatch); four competing "primary" colors. | Single token source of truth; `--kinjo-brand` (identity) + `--kinjo-action` (action) (§04). |
| Feedback loops | Errors swallowed by the fetch wrapper (~55 call sites); a failed login rendered as success; feed render races. | Mandatory toast/inline error contract surfacing the server message verbatim; deterministic states per widget (§06/§07). |
| Localization | Arabic admin in calligraphic fallback face; raw i18n keys leaking; English-only `_t()` in Arabic mode. | Verified Arabic webfont loading; every string bilingual (inline fallback + JSON key); enrollment enum keys UPPERCASE (§04/§06). |
| Status legibility | Enrollment status compared in wrong case (JS lowercase vs API UPPERCASE) → renders blank. | Canonical UPPERCASE contract; status encoded in *form* (pill + icon), not color alone. |

### Predicted friction points to defend against

KPI overload · unclear status indicators (color-only) · mixed module rows · scope ambiguity
(which governorate / date range is in effect) · RTL/LTR asymmetry (icon sides, chart axes,
number alignment).

---

## 02 · Information architecture & navigation

Deliberately **shallow**: every core task is reachable in one or two clicks from the
persistent sidebar. Navigation is role-filtered at render time — a user never sees a nav
item they can't act on.

### Global chrome (every authenticated page)

| Element | Placement (LTR / RTL mirror) | Behavior |
|---|---|---|
| Governorate / KG scope selector | Top bar, leading edge | **Admin-only.** Primary scoping control; persists across pages (session). Canonical governorate names (e.g. `العاصمة`, not city `عمان`); alias-aware. Manager and Supervisor never see it — hard-scoped server-side to their KG and class respectively. |
| Date-range picker | Top bar, after scope | Presets (Today, 7d, 30d, Custom). "Custom" **must** transmit its dates. Jordan time (UTC+3). |
| Global search | Top bar, center | Typeahead across kindergartens, users, reports. Role-scoped. `⌘/Ctrl-K`. |
| Notification center | Top bar, trailing edge | **Real-time.** Live badge over the push channel; toast on arrival. Grouped by severity; each deep-links to source. Gear opens per-user delivery prefs (in-app always on; email/SMS/push opt-in). |
| User / language menu | Top bar, trailing corner | ar⇄en toggle (writes `window.KINJO_LANG` + flips `dir`), profile, sign out, impersonation banner. |
| Sidebar | Inline-start rail | Role-filtered nav grouped by domain; collapsible. Owns the dark-slate "Layer v3.0" style in `kinjo.css`. |
| Breadcrumb | Top of content | Route-derived, always live: `Home / Section / Entity`. Never a static placeholder. |

### Primary navigation model (Admin — the superset)

| Group | Items | Lands on |
|---|---|---|
| Overview | Dashboard · Analytics · Alerts | KPI control room / drill-down explorer / triage queue |
| Institutions | Kindergartens · Classes · Import kindergartens | KG list & detail, class roster, bulk import |
| People | Users/Staff · Children · Enrollments · Import users | Directory, child records, enrollment pipeline |
| Operations | Attendance · Daily reports · Incidents & Safety | Attendance review, report organization, incident log |
| Communication | Messages · Announcements · Events · Surveys | Communication center tabs |
| Governance | Governance reports · Agency reports · Contact messages · Import logs | Official reporting, agency exports, inbox, import audit |
| Settings | Profile · Preferences · (Admin) system settings | Account & platform configuration |

> **IA change baked in.** Agency reports now live under **Governance** (moved from a
> duplicated top-level entry). The nav must not surface the old duplicate.

### Breadcrumb + depth contract

- Level 0 → Level 1 (group landing) → Level 2 (entity/task). Deeper → modal or detail
  drawer, not a new nav level.
- Breadcrumb items are links except the last; the last is the entity's real name
  (bilingual), never a slug or ID.
- Drill-downs (Analytics → governorate → KG) push breadcrumb segments and are back-navigable.

---

## 03 · Dashboard layout & data visualization

The dashboard is a **scan surface**, not a document. Reads top-to-bottom as: *how is the
system right now* (KPIs) → *what needs me* (alerts) → *the shape of the day* (charts) →
*what happened* (feed) → *what can I do* (quick actions). The backend contract exposes seven
KPIs and seven dashboard sections; the layout tiers them rather than presenting flat.

### Top tier — KPI cards

Only the four operational metrics earn hero prominence; two directory counts and the one
true score sit in a secondary strip. **Honesty rule:** raw counts get a neutral delta chip
(movement, not judgement); only `data_quality_score` — a genuine 0–100 score — earns a graded
good/average/low band.

| KPI key | Label (en / ar) | Tier | Value type | Delta / band | Quick action → |
|---|---|---|---|---|---|
| `active_kindergartens` | Active Kindergartens / الحضانات النشطة | Hero | Count | Neutral delta | `/admin/kg-overview` |
| `pending_submissions` | Pending Review / بانتظار المراجعة | Hero | Count | Neutral delta (down = good) | `/reports/analytics` |
| `total_submissions` | Total Reports / إجمالي التقارير | Hero | Count | Neutral delta | `/reports/analytics` |
| `data_quality_score` | Data Quality / جودة البيانات | Hero | **Score 0–100** | **Graded** Good/Average/Low | `/admin/daily-reports-organization` |
| `total_kindergartens` | Kindergartens / الحضانات | Secondary | Count | Neutral delta | `/admin/kg-overview` |
| `total_users` | Total Users / إجمالي المستخدمين | Secondary | Count | Neutral delta | `/admin/users` |
| `active_users` | Active Users / المستخدمون النشطون | Secondary | Count | Neutral delta | `/admin/users` |

> **Definition · `data_quality_score`.** Share of **active kindergartens that filed a report
> in the last 7 days** — *not* an attendance rate. The only true graded score, so the only
> KPI allowed a good/average/low color band. Tooltip surfaces the definition verbatim, bilingual.

### Middle / bottom tier — operational panels

- **System Alerts** (LIVE) — severity-striped rows (critical → resolved), each deep-linking
  to source; live-pushed.
- **Attendance today** — stacked bar per KG/class (present / excused / absent), single y-axis,
  legend + hover labels.
- **Enrollment status** — doughnut (ACTIVE / PENDING_REVIEW / WITHDRAWN) with center total and
  labeled + % legend.
- **Recent activity** — typed feed with severity affordances (incident, report, user event).
- **Quick actions** (الإجراءات السريعة) — Approve pending reports · Add kindergarten ·
  Generate agency report · Broadcast announcement.

### Visualization strategy — chart type ↔ data question

| Data question | Form | Encoding rules |
|---|---|---|
| Single headline number now? | Stat/KPI card + sparkline | Tabular-nums value; sparkline for direction only; neutral delta chip. |
| Compare classes/KGs on attendance? | Stacked bar | Single y-axis; 2px surface gap between segments; status colors + legend; direct label on hover. |
| Metric trending over range? | Line / area | 2px line; faint grid; emphasized endpoint; crosshair + tooltip. |
| Enrollment composition? | Doughnut (≤4 slices) else bar | Center total; legend labels + %; never color-only. |
| Individual records? | Data table | Sticky header; status pills; end-aligned numerics; per-row overflow menu. |
| What needs attention? | Alert list (severity-striped) | Severity stripe + badge + icon; grouped critical→resolved. |

> **Data-viz non-negotiables.** One y-axis per chart (never dual-axis). Color follows the
> entity, never its rank — a filter that drops a series must not repaint survivors. Status
> colors (good/warning/critical) are reserved and always ship with icon + label, never color
> alone. Charts inherit theme tokens so they re-color in dark mode.

---

## 04 · Design system specification

The system already ships a token layer (`--kinjo-*` in `components.css` /
`admin_design_system.css`). This formalizes it rather than replacing it.
**Load-bearing rule: green is identity ("جاهز/ready"), blue is action. Do not repaint admin green.**

### Color

| Role | Token | Hex | Use |
|---|---|---|---|
| Brand / identity | `--kinjo-brand` | `#0F7A52` | "ready / جاهز"; identity actions, active nav |
| Action | `--kinjo-action` | `#1E40AF` | Primary interactive |
| Success | — | `#15803D` | Semantic (reserved) |
| Warning | — | `#B45309` | Semantic (reserved) |
| Danger | — | `#C2321F` | Semantic (reserved) |
| Info | — | `#0369A1` | Semantic (reserved) |
| Ink / Ink-2 / Ink-3 | — | `#10201A` / `#45564F` / `#6B7A73` | Text (green-biased neutrals) |
| Line / Ground | — | `#DBE3DF` / `#F6F8F7` | Borders / page ground |

Semantic colors are **reserved** — never reused as a chart series hue.

> **Debt to close.** ~90 blue literals and Arabic calligraphic-font fallbacks were found
> untokenised. New work references tokens; migration retires the four legacy "primary" colors
> to `--kinjo-brand` + `--kinjo-action`.

### Typography

Product Arabic face is **Noto Sans Arabic** (the only Arabic webfont actually loaded);
Cairo/Tajawal are aspirational and must be genuinely fetched before use — `document.fonts.check()`
lies, so verify with the platform-font API. Latin on a system sans stack. Numerals use
`tabular-nums` in all data contexts.

| Role | Size / weight |
|---|---|
| Display / H1 | 40 / 800 / -2.5% tracking |
| H2 · Section | 26 / 750 / -2% |
| H3 · Panel | 18 / 700 |
| Body | 16 / 400 / 1.6 line-height |
| Small / label | 13 / 500 |
| Caption / mono | 12 / mono |

### Spacing & radius

4px base grid; tokens `--kinjo-spacing-1…8`. Radius: `sm 8 · md 12 · lg 18 · full 999`.
Common: spacing-2 (8, icon↔label), spacing-3 (12, grid gap), spacing-4 (16, card padding),
spacing-6 (24, section rhythm).

### Component library

Each maps to an existing macro/class; states are mandatory.

| Component | Macro / class | Required states |
|---|---|---|
| KPI card | `components/kpi-card.html` · `.k-kpi-card` | loading (spinner) · loaded · delta+/− · score band · error |
| Data table | `components/data-table.html` | loading skeleton · rows · empty · error · sorted · paginated |
| Filter bar / row | `filter-bar.html` · `filter-row.html` · `date-range-filter.html` | default · active (visible applied summary) · invalid (no silent drop) |
| Modal | `components/modal.html` · `confirm-modal.html` | open · loading · error · confirm/destructive |
| Toast | `components/toast.html` | success · error · warning · with-undo |
| Alert banner | `components/alert_banner.html` | info · warning · critical · dismissible |
| Inputs / form controls | `components/form-controls.html` | default · focus (2px ring) · invalid+message · disabled · RTL |
| Page header + breadcrumb | `components/page-header.html` | title · live breadcrumb · action slot |

Buttons: brand (identity) · action (primary) · ghost · danger, each with hover/disabled/loading.
Status pills encode state in **form** (icon + label), not color alone.

---

## 05 · Role-based experience map

Four real roles from `UserRole`. Every view is the same component set, filtered — never a
separate app. The rule is *subtractive*: start from the Admin superset and hide what a role
can't act on.

| Role | Primary daily goal | Essential sections | Signature KPIs / lists | Hidden / deemphasized |
|---|---|---|---|---|
| **Admin** | Govern the whole platform; catch systemic gaps. | Dashboard · Analytics · Alerts · Institutions · People · Governance | All 7 KPIs; missed-reporting alerts; agency-report queue; user/audit activity. | Operational entry (can't create incidents/attendance/reports — by design). |
| **Manager** | Run *my* kindergarten; **review & approve** the daily reports my supervisors submit. | KG dashboard · Attendance (all classes) · Daily reports (approve) · Children · Incidents · Communication | My-KG attendance %, pending-report approval queue, today's incidents; class & child roster. | **Everything outside their own KG** — no governorate selector, no cross-KG data; hard-scoped server-side to a single `kindergarten_id`. Also platform analytics, user admin. |
| **Supervisor** | Run *my class* today; take attendance and **draft + submit** one daily report per present child. | My-class dashboard · Attendance (take) · Daily report (draft/submit) · My children · Class messages | Today's class attendance, my children's status, per-report draft/submitted/returned state, unread class messages. | **Everything outside their one class** — no governorate/KG selector, no other classes or children; hard-scoped server-side to one `kindergarten_id` + one `class_id`. Cannot approve or send reports; no analytics/admin. |
| **Parent** | Check my child's day; read the report once the Manager sends it. | Child(ren) · Attendance · Enrollments · Messages/announcements · Sent daily reports | Child attendance streak, enrollment status, unread messages, reports in `SENT_TO_PARENT` only. | Everything operational/administrative; no KPIs, no other families' data. Scoped server-side to their own children only. |

### Daily-report workflow — implemented vs. target

The core operational loop. Because the codebase mixes the *approved target* with what is
*actually shipped*, every element is tagged with an exact `file:line` source. Tags:
**IMPLEMENTED** (verified in code), **TARGET** (approved, not yet enforced), **GAP** (current
behavior violates the target), **WORK** (backend/schema/event change needed).

#### Server-side scope enforcement

| Role | Enforced scope | Report states visible | Status · source |
|---|---|---|---|
| Admin | Platform-wide oversight (no KG binding) | All (read); *also* currently `/approve` | **GAP** can approve — see C1 |
| Manager | One `kindergarten_id`; cross-KG → 404 | `SUBMITTED` → send | **IMPLEMENTED** `dependencies.py:376`, `manager.py:62-79` |
| Supervisor | Assigned class only (child-ownership) | own-class `DRAFT`/`SUBMITTED` | **IMPLEMENTED** `rbac.py:79-86`, `supervisor.py:131` |
| Parent | Own children only | `SENT_TO_PARENT` only | **IMPLEMENTED** `api/daily_reports_routes.py:247, 264-265` |

#### Workflow steps

| # | Actor | Action | Status after | Impl · source |
|---|---|---|---|---|
| 1 | Supervisor | Attendance + one report per present child (own class) | `DRAFT` | **IMPLEMENTED** `supervisor.py:807-842` |
| 2 | Supervisor | Submit to Manager (only `DRAFT` submittable) | `SUBMITTED` | **IMPLEMENTED** `supervisor.py:967-990` |
| 3 | Manager | Review; may edit (`SUBMITTED` only) | `SUBMITTED` | **IMPLEMENTED** `manager.py:515-545` |
| 4 | Manager | Optional internal approve | `APPROVED` | **GAP** legacy, Admin-permitted `api/daily_reports_routes.py:192-214` |
| 5 | Manager | Send to Parent (accepts `SUBMITTED` *or* `APPROVED` — no mandatory approve) | `SENT_TO_PARENT` | **IMPLEMENTED** manager-only `manager.py:548-608` |
| 6 | Parent | Views report — visible only now | `SENT_TO_PARENT` | **IMPLEMENTED** `api/daily_reports_routes.py:264-265` |
| — | Manager | Reject / return to Supervisor to fix | `REJECTED` | **TARGET / WORK** no endpoint/audit/notification/test |

**Status enum** (`models.py:131-137`): `DRAFT · SUBMITTED · APPROVED · SENT_TO_PARENT ·
REJECTED · RETURNED`. `RETURNED` is a backward-compat alias treated as equivalent to `REJECTED`
in analytics and edit-guards (`daily_report_analytics.py:249`, `models.py:875, 883`); no endpoint
currently sets either value.

#### A · Current implemented & verified behavior

- Supervisor authoring is creator/assigned-class-scoped: `assert_supervisor_owns_child` raises
  403 for a child outside the supervisor's classes (`rbac.py:79-86`, called at
  `supervisor.py:814, 977`); the role gate is supervisor-only (`supervisor.py:131-134`).
- Supervisor may only save `DRAFT`/`SUBMITTED`; submit transitions `DRAFT → SUBMITTED` and
  writes a `DAILY_REPORT_SUBMITTED` audit row (`supervisor.py:839-842, 967-990`).
- Manager edit is limited to `SUBMITTED` reports (`manager.py:525`); the review list defaults
  to `SUBMITTED` (`manager.py:432`).
- Manager send is **manager-only** (`require_manager`, `dependencies.py:376-392`) and
  cross-KG-safe (404, `manager.py:62-79`); it atomically sets `SENT_TO_PARENT`, stamps
  `approved_by`/`approved_at`/`sent_to_parent_at`, and writes a parent `Message` + two audit
  rows in one transaction (`manager.py:548-608`).
- Parent visibility is gated to `SENT_TO_PARENT` only (`api/daily_reports_routes.py:264-265`),
  behind a parent-ownership check (`:247`).
- Real-time infra exists: per-user Redis-pub/sub WS at `/ws/notify` (`main.py:1385`), plus
  `/ws/dashboard` & `/ws/heatmap` (`main.py:1271, 1320`) and `/ws/analytics/dashboard`
  (`analytics_ws.py:68`); publisher `realtime_service.publish_notification` (`realtime_service.py:229`).

#### B · Approved target behavior (not yet enforced)

- **Admin never performs operational approval/send** — Admin is monitoring / governance /
  audit / analytics only.
- **Explicit reject/return path** — Manager can return a `SUBMITTED` report to the authoring
  Supervisor with a reason; the Supervisor revises and resubmits.
- **Lifecycle emits real-time events** to the scoped recipient (submit → Manager; send →
  Parent; return → Supervisor) over the existing WS channel.
- *Decision required:* whether `APPROVED` becomes a mandatory gate before send or stays an
  optional internal state.

#### C · Identified implementation gaps

- **C1 — Admin can approve.** Legacy `POST /api/daily-reports/{id}/approve` calls
  `validate_manager_role`, which permits `ADMIN` and `MANAGER` (`api/daily_reports_routes.py:192-199`,
  `validators.py:374-380`), and explicitly skips KG-scoping for admin (`:212-214`). Violates
  "Admin never approves"; exercised as-is by `tests/test_integration_comprehensive.py:524`.
- **C2 — No mandatory approve gate.** Send accepts `SUBMITTED` *or* `APPROVED` and jumps
  straight to `SENT_TO_PARENT` (`manager.py:559-566`); the 400 message says "must be in
  SUBMITTED state" while the code also accepts `APPROVED` — copy/logic mismatch.
- **C3 — Reject/return not implemented.** `REJECTED`/`RETURNED` exist as enum values only;
  there is no manager reject endpoint, no `DAILY_REPORT_REJECTED` *AuditAction*
  (`audit_actions.py:100-105` defines none), and no notification or test.
- **C4 — Lifecycle not wired to real-time.** The send flow writes a `Message` row but does
  *not* call `publish_notification`; that publisher is only invoked by the Celery task
  `notification_tasks._push_to_ws` (`notification_tasks.py:22-36`). No `report.*` event reaches
  the parent's WS channel today.

#### D · Required backend / schema / event work

- **D1** — Restrict operational approval/send to `MANAGER`: change the legacy `/approve` guard
  from `validate_manager_role` to a manager-only dependency (or deprecate the endpoint).
  Separate, explicitly-scoped task with its own tests.
- **D2** — Decide and enforce the approve gate (mandatory vs optional); align the send-endpoint
  validation and its 400 message with the decision.
- **D3** — Add a manager reject/return endpoint (e.g. `PUT /api/manager/daily-reports/{id}/reject`)
  with a reason field, a new `DAILY_REPORT_REJECTED` AuditAction, a supervisor notification, and
  a decision on `REJECTED` vs `RETURNED` (recommend consolidating on `REJECTED`, keeping
  `RETURNED` read-only for legacy rows).
- **D4** — Emit lifecycle events by publishing a typed `models.Notification` (which already
  flows to `/ws/notify`) on submit/send/return, scoped to the recipient; define the payloads as
  an explicit contract (§07).

#### Required test coverage

Specified here for a follow-up, explicitly-scoped test task — no test files were created in this
documentation change.

| Test | Assertion | Anchors on |
|---|---|---|
| Supervisor assigned-class enforcement | 403 when a supervisor acts on a child outside their classes | `rbac.py:79` |
| Creator-only submission | Only the authoring supervisor (own class) can submit a `DRAFT` | `supervisor.py:967-979` |
| Manager-only send | Non-manager (incl. Admin) → 403 on send-to-parents | `dependencies.py:376` |
| Cross-kindergarten 404 | Manager acting on another KG's report → 404 (not 403) | `manager.py:62-79` |
| Parent visibility | Parent sees a report only after `SENT_TO_PARENT` | `api/daily_reports_routes.py:264` |
| Admin blocked from approval (final rule) | Admin → 403 on `/approve` once D1 lands (today it's 200 — a test asserting the gap) | C1 / D1 |
| Reject/return transition | Manager return sets `REJECTED`, notifies supervisor, audits — once D3 lands | D3 |
| Valid/invalid status transitions | Reject illegal jumps (e.g. `DRAFT → SENT_TO_PARENT`); allow legal ones | state machine |

> **Security invariant.** Role filtering is a UI convenience, never the enforcement boundary.
> Every admin endpoint keeps `require_admin`; ownership checks must not short-circuit when a
> profile is `None` (a known IDOR shape). Scoping is enforced in the query layer per the tables
> above, and a report becomes Parent-visible **only** once a Manager moves it to
> `SENT_TO_PARENT`. Note the open gap C1 — the legacy `/approve` route still admits `ADMIN` —
> until D1 lands. The nav hiding an item does not authorize the API.

---

## 06 · Interaction & microcopy guidelines

### Feedback patterns

| Event | Pattern | Rule |
|---|---|---|
| Success | Toast (auto-dismiss 4s) + optimistic UI | Verb→result symmetry: "Approve" → "Approved". Name the entity. |
| Destructive | Confirm modal → toast **with Undo** (where reversible) | Confirm names the exact target and consequence. Undo window ≥ 5s. |
| Error | Inline (field) + toast (action); **surface server message verbatim** | Never swallow the error body (fixes the ~55-callsite `fetchWithAuth` bug). No generic "something went wrong" when the server said more. |
| Loading | Skeletons for content; spinner only for in-place values | Every async widget has explicit loading/empty/error — no blank panels. |
| Empty | Illustration + one-line reason + primary action | Explain *why* empty and the next step, bilingual. |

### Accessibility standards

- **Contrast** — body ≥ 4.5:1, large/UI ≥ 3:1, both themes. Status never color-only.
- **Touch targets** — ≥ 44×44px.
- **Focus** — visible 2px ring; logical tab order; no keyboard traps.
- **RTL/LTR parity** — logical properties (`inset-inline`, `margin-inline`); icons and chart
  axes mirror; numerals stay LTR inside RTL.
- **Live regions** — KPI values and toasts use `aria-live="polite"`.
- **Motion** — honor `prefers-reduced-motion`; no essential info via animation alone.
- **Responsive** — ≥1200 (full grid), 768–1199 (2-col, collapsible sidebar), <768 (single
  column, sidebar → drawer, tables scroll in-container).
- **Language** — correct `html lang` + `dir` per session.

### Bilingual microcopy

Arabic is primary. Every UI string ships both variants (backend returns `_ar` + `_en`;
templates guard with `{% if ui_lang == 'en' %}`). i18n keys use dot-notation; enrollment enum
keys UPPERCASE to match JS. Tone: plain, active, operational.

| Context | English | العربية | i18n key |
|---|---|---|---|
| KPI section | KPI cards | بطاقات المؤشرات | `dashboard.kpi_cards` |
| Alerts panel | System alerts | تنبيهات النظام | `dashboard.system_alerts` |
| Quick actions | Quick actions | الإجراءات السريعة | `dashboard.quick_actions` |
| Enrollment state | Active | نشط | `enrollment.ACTIVE` |
| Enrollment state | Pending review | بانتظار المراجعة | `enrollment.PENDING_REVIEW` |
| Data quality | Share of active kindergartens that reported in the last 7 days. | نسبة الحضانات النشطة التي قدّمت تقريراً خلال آخر 7 أيام. | `dashboard.dq_help` |
| Success toast | Report approved | تمت الموافقة على التقرير | `reports.approved_toast` |
| Empty state | No reports in this range yet. | لا توجد تقارير في هذه الفترة بعد. | `reports.empty` |

> **Copy rules.** Name things as people recognize them (a "report", not a "submission record").
> Errors say what happened and how to fix it — no apologies. Never hardcode Arabic-only strings
> in API fields the UI renders. Never leak a raw i18n key: every key has an inline fallback *and*
> a JSON entry.

---

## 07 · Engineering implementation spec

### Sitemap / navigation tree

```
/admin
├── dashboard            — KPI control room (7 cards, 7 sections)
├── analytics            — drill-down explorer → governorate → KG
├── alerts               — triage queue
├── institutions/
│   ├── kg-overview      — list + stats
│   ├── kindergartens/:id
│   ├── classes
│   └── import-kindergartens
├── people/
│   ├── users            — directory (require_admin)
│   ├── children/:id
│   ├── enrollments
│   └── import-users
├── operations/
│   ├── attendance
│   ├── daily-reports-organization
│   └── incidents/:id    — safety log
├── communication/
│   ├── messages
│   ├── announcements
│   ├── events
│   └── surveys
├── governance/
│   ├── governance-reports
│   ├── agency-reports   — moved here from top level
│   ├── contact-messages
│   └── import-logs
└── settings
```

### Component inventory — props & states

| Component | Props | States | Events |
|---|---|---|---|
| `KpiCard` | key, label{ar,en}, value, format(number\|percentage), icon, color, delta, band?, drilldownHref, helpText{ar,en} | loading · value · error | onDrilldown |
| `AlertList` | items[], groupBy(severity), maxRows | loading · items · empty · error | onTriage(id) |
| `AttendanceChart` | series[{kg,present,excused,absent}], scope | loading · rendered · empty | onBarHover, onBarClick |
| `DataTable` | columns[], rows[], sort, page, rowActions[] | skeleton · rows · empty · error | onSort, onPage, onRowAction |
| `FilterBar` | scope, dateRange, appliedSummary | default · active · invalid | onApply (never silent-drops) |
| `ScopeSelector` | governorates[], selected, locked(role) | open · selected · locked | onChange (persists session) |

### Real-time transport & notifications

**What exists today (IMPLEMENTED)** — a per-user notification WebSocket at `/ws/notify` backed
by Redis pub/sub (`main.py:1385`), fed by `realtime_service.publish_notification(user_id, payload)`
(`realtime_service.py:229`), currently called only by the Celery task
`notification_tasks._push_to_ws` for `models.Notification` rows (`notification_tasks.py:22-36`).
Dashboard/analytics sockets also exist (`main.py:1271, 1320`; `analytics_ws.py:68`).

**Target contract (TARGET)** — the daily-report lifecycle should publish scoped events over that
channel, with the client subscribing by role (Manager → `kindergarten_id`, Supervisor →
`class_id`, Parent → own children). These report events are *not* emitted yet (§05 gap C4); the
send flow only writes a `Message` row. The table below is the proposed contract, to be wired per
§05 D4 with tests.

| Channel / event | Payload | Client effect | Status |
|---|---|---|---|
| `notification.new` | Notification | Live badge + toast; enters notification center. | IMPLEMENTED |
| `alert.created` | Alert | Prepend to alerts panel; bump badge; toast if severity ≥ warning. | TARGET |
| `kpi.updated` | { key, value, delta, band? } | Repaint the one KPI card (`aria-live` announces new value). | TARGET |
| `report.submitted` | { report_id, class_id, child_id } | **→ Manager**: +1 approval queue; toast; feed row. | TARGET / WORK |
| `report.sent` | { report_id, child_id } | **→ Parent**: report now visible; badge + toast. | TARGET / WORK |
| `report.returned` | { report_id, reason } | **→ Supervisor**: report back to `REJECTED`; toast to fix. | TARGET / WORK |

### Example data models (widget contracts)

```python
# AdminDashboardResponse — the dashboard payload (Pydantic v2)
class KpiValue(BaseModel):
    key: str            # e.g. "data_quality_score"
    value: float
    format: Literal["number", "percentage"]
    delta: float | None
    band: Literal["good", "average", "low"] | None  # score KPIs only

class AdminDashboardResponse(BaseModel):
    kpis: dict[str, KpiValue]        # EXACTLY 7 keys — must match KPI_CONFIG
    alerts: list[Alert]
    attendance: list[AttendanceBar]
    enrollment: dict[str, int]       # UPPERCASE enum keys: ACTIVE, PENDING_REVIEW…
    activity: list[ActivityItem]
    generated_at: datetime           # Jordan tz (UTC+3), not UTC
```

```jsonc
// Alert — severity-striped row
{
  "id": "a_8842",
  "severity": "critical",          // good | warning | critical
  "title":  { "ar": "3 حضانات لم تُرسل تقاريرها", "en": "3 kindergartens missed reporting" },
  "detail": { "ar": "…", "en": "Al-Basma, Nour · 8+ days" },
  "href": "/admin/daily-reports-organization?filter=missing",
  "created_at": "2026-07-21T09:12:00+03:00"
}
```

```python
# Notification — one per user; in-app always, other channels opt-in
class Notification(BaseModel):
    id: str
    user_id: str
    kind: Literal["alert", "report", "message", "system"]
    severity: Literal["info", "warning", "critical"]
    title: dict[str, str]    # { "ar": …, "en": … }
    href: str                # deep-link to source
    read: bool = False
    channels: list[Literal["in_app", "email", "sms", "push"]]  # resolved from user prefs
    created_at: datetime     # Jordan tz (+03:00)
```

```python
# DailyReport — one per present child per day; status drives visibility
class DailyReportStatus(str, Enum):
    DRAFT = "DRAFT"                    # supervisor authoring, not yet submitted
    SUBMITTED = "SUBMITTED"            # sent to manager, awaiting review
    APPROVED = "APPROVED"              # optional internal state — NOT a mandatory gate (gap C2)
    SENT_TO_PARENT = "SENT_TO_PARENT"  # parent-visible ONLY in this state (verified)
    REJECTED = "REJECTED"             # target reject state — no endpoint sets it yet (gap C3)
    RETURNED = "RETURNED"             # backward-compat alias, == REJECTED in analytics; legacy rows only

class DailyReport(BaseModel):
    id: str
    child_id: str
    class_id: str
    kindergarten_id: str
    status: DailyReportStatus
    authored_by: str          # supervisor user_id
    approved_by: str | None   # manager user_id (stamped on send, manager.py:567)
    report_date: date         # Jordan date (UTC+3)
    # VERIFIED: send-to-parents is manager-only (dependencies.py:376) and the Parent
    # query filters status == SENT_TO_PARENT (api/daily_reports_routes.py:264).
    # GAP: legacy /approve still admits ADMIN (api/daily_reports_routes.py:199) — see C1/D1.
```

> **Build guardrails.** Jordan time (UTC+3) for every operational date and cache key — never
> `date.today()` or UTC. KPI math lives in `kpi_service.py`, never inlined in endpoints. Batch
> aggregates (no N+1). Every state change calls `log_audit_event()` with an `AuditAction`
> constant. The `kpis` dict has exactly 7 keys matching `KPI_CONFIG` — drift breaks the contract.

### Definition of done (per screen)

- Renders correctly in ar (RTL) and en (LTR).
- Loading, empty, and error states implemented.
- No raw i18n keys; fallback + JSON present.
- Server errors surfaced, not swallowed.
- Keyboard-navigable; focus visible; ≥44px targets.
- Dark + light both pass contrast.
- No dual-axis charts; status never color-only.
- Audit event on every state change.

---

*Grounded in the live codebase. Tokens reference `--kinjo-*` in `components.css` /
`admin_design_system.css`. Arabic-primary · Jordan UTC+3.*
