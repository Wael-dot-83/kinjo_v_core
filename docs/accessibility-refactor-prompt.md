# Card/Section Accessibility Refactor Prompt

Reusable prompt for refactoring a single dashboard card or page section to
be properly laid out, keyboard/screen-reader accessible, and information-
dense in the right way. Adapted from a live run against the Risk Heatmap
card on `/admin/analytics` (commit `f781781`) — corrected in a few places
where the original draft assumed things that aren't true of this codebase.
Read [admin-audit-prompt.md](admin-audit-prompt.md) first if this is part
of a full-panel audit; this prompt is for a single targeted card/section.

## Role

Senior full-stack engineer working in **this specific codebase**: FastAPI
+ Jinja2 (bilingual `_ar`/`_en`, `{% if ui_lang == 'en' %}` guards),
**Bootstrap 5.3 RTL** (not USWDS, not Tailwind — verify with
`grep -rn "uswds\|tailwind" static/` before assuming otherwise), vanilla
JS ES6, pytest for regression tests.

## Objective

Refactor a named card/section to fix layout, accessibility, and dead-code
defects, matching the conventions already established elsewhere on the
same page.

## Task specifications (priority order)

1. **Fix the actual layout bug, if one exists.** Before assuming a grid
   is "supposed to" use a particular framework's classes, check what's
   actually loaded and what the sibling cards on the same page already
   use. In this codebase, Bootstrap's `.col-*` classes need a `.row`
   (or `d-flex flex-wrap`) ancestor to lay out side-by-side — a `.col-6
   col-md-4` div appended straight into a plain container silently
   stacks as full-width blocks instead of a grid. Confirm the bug live
   (screenshot before/after) rather than assuming from reading the JS
   alone.
2. **Make interactive cells real `<button>` elements** inside a semantic
   `<ul role="list">` / `<li>` structure, not clickable `<div>`s. A
   native button gets focus and Enter/Space activation for free — no
   extra keyboard-handler JS needed. Give each one an `aria-label` in
   the **current UI language only** (via whatever bilingual-text helper
   the page already uses, e.g. `adminAnalyticsText(ar, en)`) — don't
   concatenate both languages into one label; screen readers announce
   one language at a time, and every other page in this codebase follows
   the pick-current-language pattern.
3. **Add a legend for any color-coded status**, reusing existing CSS
   classes from the same page/design system rather than inventing new
   ones (e.g. this page already has `.gov-legend-dot--green/amber/red`
   from the Governance Distribution card — reuse it for visual
   consistency instead of a parallel set of classes).
4. **Sort by what matters, and be honest about where.** "Worst-first"
   sorting is usually a front-end concern if the same backend array
   feeds multiple widgets that need different orders (e.g. a table on
   one tab and a heatmap on another, sharing one `governorate_breakdown`
   response) — sorting server-side would require either resorting
   every consumer or duplicating the field. Only push sorting to the
   backend if this card is the sole consumer of that data.
5. **Remove dead code you find along the way** (unused placeholder divs,
   elements with zero JS references) — but grep the whole codebase for
   the id/class first to be sure nothing else targets it.
6. **Don't expand scope into data cleansing.** Garbage/placeholder
   values surfacing in live data (bad seed rows, migration artifacts)
   are a backend data-quality issue, not a front-end refactor's job —
   document them, don't filter or delete rows as a side effect of a UI
   fix.

## Testing deliverable

Write regression tests **in the same style already used for that page's
test file** — check the existing `test_<page>_page_frontend_contract.py`
file's conventions before writing new ones. In this codebase that means
fast, browser-free string assertions against rendered template/JS source
(`TEMPLATE.read_text()`, slice out the relevant function/block, assert on
literal substrings) — not Playwright computed-style assertions, which
would be slower and more brittle than this suite's established pattern.
Live Playwright verification (screenshots, a manual click-through) is a
one-time confirmation step during development, not something to encode
as a committed pytest test unless the page already has E2E coverage in
that style.

Self-verify every new test: revert the fix, confirm the test fails for
the *right* reason, restore the fix, confirm it passes again.

## Concurrent-edit blocker (if it happens)

If another agent/session has uncommitted, in-progress changes touching
files your work depends on (e.g. a shared import), and their changes
have temporarily broken something (a missing import causing the whole
test suite to fail to collect):
- Confirm the file is genuinely theirs (check `git status`/`git diff`
  against what you were told is out of scope) before touching it.
- Ask before making any fix in a file you don't own, even a one-line one.
- Before staging, diff the file against `HEAD` — if your fix and their
  in-progress edits are tangled in the same file, do **not** `git add`
  the whole file. Either isolate your exact hunk, or — if your fix
  brings the file back to exactly what's already committed at `HEAD`
  (net zero diff) — leave the file out of your commit entirely; there's
  nothing of yours to stage.
- Never stage files outside what you were asked to change, even by
  accident via `git add -A`/`git add .`.

## Final step

Do not push until asked. After tests pass, summarize what changed (with
before/after screenshots if the change is visual) and ask explicitly
whether to push now or hold.

## Reference: what actually shipped (2026-07-06, commit f781781)

- Bootstrap `.row g-2 list-unstyled` + `.col-6 col-md-4 col-lg-3` (not
  USWDS grid classes — this codebase doesn't load USWDS).
- `<button class="risk-cell">` inside `<ul role="list"><li>`, with
  `aria-label` picking the current UI language via the page's existing
  `adminAnalyticsText()` helper.
- Legend reusing `.gov-legend-dot--green/amber/red` from the sibling
  Governance Distribution card.
- Sorting done client-side in `updateRiskHeatmap()`, ascending by
  `governance_score` (highest risk first) — kept client-side because the
  same `governorate_breakdown` array also feeds the Governorate
  Breakdown table on the Governance tab, which needs its own order.
- Removed a dead `#advancedMetricsContainer` placeholder div.
- 5 new string-assertion tests in the page's existing
  `test_analytics_dashboard_page_frontend_contract.py`, self-verified.
- Two garbage governorate values ("cols", "X") observed live and left
  untouched — documented, not a front-end concern.
- Hit and resolved a concurrent-edit blocker: another agent's uncommitted
  work in `admin_reports_api.py` had dropped a `require_admin` import,
  breaking `main.py`'s import and the whole test suite's collection.
  Restored the import — it turned out to be a zero-diff match against
  `HEAD`, so the file was left out of the commit entirely.
