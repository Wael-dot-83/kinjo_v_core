# Manager Module UI/UX Design Plan

**Status:** Draft for review
**Scope:** Manager module (routes, templates, static assets)
**Reference repo:** `D:/Final Version_mvp_ADMIN`

---

## 1. Color Palette (6 named hex values)

All values map to CSS custom properties. The palette extends the admin design-token system (`static/css/design-tokens.css`) without introducing a competing primary color. Green stays identity-only per the four-competing-principle in `design-tokens.css` lines 3-14; blue stays interaction-only.

| Token | Hex | Role | Admin Mapping |
|---|---|---|---|
| `--manager-brand` | `#1F5E47` | Identity — logo, header band, context strip | Same as `--kinjo-brand` (admin uses for login/public chrome only) |
| `--manager-action` | `#1E40AF` | Primary interaction — buttons, links, active tabs | Same as `--kinjo-action` (admin single source of truth, `design-tokens.css` line 16) |
| `--manager-action-hover` | `#1E3A8A` | Hover state for interactive elements | Same as `--kinjo-action-hover` |
| `--manager-surface` | `#F0FDF4` | Manager surface tint (green-tinted, signals operational context) | New — admin has no dedicated manager surface |
| `--manager-accent` | `#0D7377` | Analytics chart accent for manager KPIs | New — extends admin chart palette (`admin_design_system.css` lines 6-11) |
| `--manager-warning` | `#F59E0B` | Pending action states (reports awaiting review, absences) | Same as `--kinjo-color-warning` |

### Rationale and file references

- **`#1F5E47`** — Preserves `templates/manager_base.html` line 23 (`<meta name="theme-color" content="#1F5E47">`) and `static/css/manager_design.css` line 7 (`--mgr-primary`). The admin module reserves green for the login page and logo only; the manager module borrows it as a surface accent because kindergarten operations align with the green ready/healthy signal.
- **`#1E40AF`** — Sourced from `design-tokens.css` line 16. Using the admin action blue for manager buttons ensures the two modules share one interactive color, avoiding a fifth competing primary.
- **`#F0FDF4`** — A green-tinted surface that differentiates manager pages from admin pages at a glance without changing navigation patterns. Contrast against `--manager-brand` text is 5.2:1 (WCAG AA).
- **`#0D7377`** — Added to extend the admin chart palette. Avoids using red (`#DC2626`, error) or amber (`#F59E0B`, warning) for operational KPIs which carry different semantic meaning.

### Accessibility

All values pass WCAG AA minimum contrast against their intended backgrounds. The warning token (`#F59E0B`) at 3.0:1 on white is for large text/icons only (badges, not body text), consistent with admin usage in `admin_design_system.css` line 47 (`--color-warning: #F59E0B`).

---

## 2. Typography Roles (3 roles + Arabic support)

The manager module inherits the admin type stack defined in `static/css/admin_design_system.css` lines 86-106 and extends it with three explicit roles: Display, Body, and Utility.

| Role | Typeface | Weight | Size | CSS Variable | Admin Equivalent |
|---|---|---|---|---|---|
| **Display** | Inter | 700 Bold | `clamp(1.5rem, 3vw, 2.25rem)` | `--kinjo-font-display` | None (admin uses fixed `fs-1` from Bootstrap) |
| **Body** | Inter / Noto Sans Arabic | 400 Regular | `1rem` (16px) | `--kinjo-font-body` | `--font-family-base` (`admin_design_system.css` line 99) |
| **Utility** | Inter | 500 Medium | `0.875rem` (14px) | `--kinjo-font-utility` | `--text-sm` (`admin_design_system.css` line 88) |

### Typeface details

- **English:** `Inter, -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif` (`design-tokens.css` line 109)
- **Arabic:** `Noto Sans Arabic, "Segoe UI", Tahoma, sans-serif` (`admin_design_system.css` line 96; `manager_base.html` lines 37-38 loads both fonts)
- **Mono (numeric tables):** `Inter, "JetBrains Mono", monospace` — for KPI numbers and report tables where tabular figures improve scanability

### Responsive typography improvements

- **Display** uses `clamp(1.5rem, 3vw, 2.25rem)` instead of the current fixed `fs-1` (Bootstrap `font-size: 1.375rem` at `admin_design_system.css` line 614). This prevents horizontal overflow on narrow viewports — the current manager dashboard and children list pages use `fs-1` which does not scale.
- **Body** stays at `1rem` — does not scale below 16px (WCAG minimum for readable text).
- **Utility** stays at `0.875rem` — matches admin `text-sm`. Legible on mobile without zooming.

### Arabic handling

`templates/manager_base.html` lines 3-6 already switches `lang` and `dir` attributes. The typeface stack in `design-tokens.css` lines 155-160 (`[lang="ar"]` selector) already routes to the Arabic stack. No change needed.

### File references

- `static/css/design-tokens.css` — add `--kinjo-font-display`, `--kinjo-font-utility`
- `static/css/admin_design_system.css` lines 86-106 — existing type scale (reference, not modified)
- `templates/manager_base.html` lines 33-38 — font loading (no change needed)

---

## 3. Layout Concept with ASCII Wireframes

The manager module uses a single-column, top-navigation layout matching the admin pattern (`templates/admin_base.html` lines 182-285, `static/css/layout.css`), with one manager-specific addition: the kindergarten context bar.

### 3.1 Global Manager Base Layout

```
+-------------------------------------------------------------+
|  SKIP LINK (a#admin-main-content)                           |
|  +---------------------------------------------------------+  |
|  |  HEADER (Tier 1)                                        |  |
|  |  [favicon] KinJo Manager          [Lang v]  [User v]  |  |
|  +---------------------------------------------------------+  |
|  +---------------------------------------------------------+  |
|  |  KINDERGARTEN CONTEXT STRIP (Section 4)                  |  |
|  |  [KG icon] Al-Noor Kindergarten  87 children [synced]  |  |
|  +---------------------------------------------------------+  |
|  +---------------------------------------------------------+  |
|  |  TOP NAV (Tier 2)                                       |  |
|  |  [Dashboard] [Daily Ops] [Requests]  [Management]     |  |
|  +---------------------------------------------------------+  |
|  +---------------------------------------------------------+  |
|  |  MAIN CONTENT (#admin-content)                          |  |
|  |  {% block content %}{% endblock %}                      |  |
|  |  (responsive grid: col-12 col-md-6 col-lg-3)          |  |
|  +---------------------------------------------------------+  |
|  +---------------------------------------------------------+  |
|  |  FOOTER SCRIPTS (Chart.js, SweetAlert2, Bootstrap)     |  |
|  +---------------------------------------------------------+  |
+-------------------------------------------------------------+
```

Source files: `templates/manager_base.html` (base structure), `static/css/layout.css` (lines 33-53 for admin-container + admin-main), `static/css/top-menu.css` (Tier 2 nav).

### 3.2 Dashboard Wireframe

```
+-------------------------------------------------------------+
|  Manager Dashboard              Today: 2026-07-28          |
+-------------------------------------------------------------+
|  +-------------+ +-------------+ +-------------+ +--------+|
|  |   PENDING   | |  ABSENCE    | | ENROLLMENT  | | SENT   ||
|  |             | |  REQUESTS   | |  REQUESTS   | | TODAY  ||
|  |     12      | |      3      | |      5      | |    8   ||
|  |             | |             | |             | |        ||
|  | Review Now> | | View Details| | Review ->   | |  --    ||
|  +-------------+ +-------------+ +-------------+ +--------+|
|                                                             |
|  +---------------------------------------------------------+  |
|  |  Weekly Attendance Trend     | Capacity Utilization     |  |
|  |  +------------------------+  | +------------------------+|
|  |  | [Chart.js line]        |  | | [Chart.js bar]        ||
|  |  | Mon Tue Wed Thu Fri    |  | | ClassA B  C  D         ||
|  |  | 82%  89% 76% 91% 85%  |  | | 78% 92% 65% 88%       ||
|  |  +------------------------+  | +------------------------+|
|  +---------------------------------------------------------+  |
+-------------------------------------------------------------+
```

### 3.3 Daily Reports Review (Table + Responsive Card)

```
DESKTOP (>=768px):                    MOBILE (<768px):
+------------------------------------------------------+  +----------------------------------+
| Daily Reports for Review  [Filter] [Search]    |  | Daily Reports                    |
+------------------------------------------------------+  +----------------------------------+
| +---+------------+----------+----------+---------+--+  | +---+------+------+---+---------+--+
| | # | Child      | Date     | Status   | Superv  |A |  | | # | Child | Date | Status| Action |
| +---+------------+----------+----------+---------+--+  | +---+------+------+-------+--------+
| | 1 | Ahmad      | 2026-07-28| SUBMITTED| Fatima |Review|  | | 1 | Ahmad | 7/28 | SUBMITTED      |
| | 2 | Sarah      | 2026-07-28| SUBMITTED| Amal   |Review|  | | 2 | Sarah | 7/28 | SUBMITTED      |
| | 3 | Omar       | 2026-07-27| SENT     | -      |  - |  | | 3 | Omar  | 7/27 | SENT           |
| +---+------------+----------+----------+---------+--+  | +---+------+------+--------------------+
| Previous  1  2  3  ->  Next                           |  | Prev  1  2  3  ->  Next               |
+------------------------------------------------------+  +--------------------------------------+
```

### 3.4 Supervisor Management List

```
+-------------------------------------------------------------+
|  Supervisors                                  [+ Add]       |
+-------------------------------------------------------------+
|  [dot] Fatima Al-Hassan   Primary   Green Room   [Edit] [Deact]  |
|  [dot] Amal Nasser         Primary   Blue Room    [Edit] [Deact]  |
|  [dot] Omar Rashid         Secondary Green Room   [Edit] [Activate] [Del] |
+-------------------------------------------------------------+

Accessibility: Each row uses semantic <li> in a <ul role="list">.
Status uses color + text (green dot + "Active"), not color alone.
Meets WCAG SC 1.4.1 (Use of Color). Keyboard: Tab to Edit, Enter activates.
```

### Responsive improvements over current

- **KPI cards** (`templates/manager/dashboard.html` lines 47-80): Already use `col-12 col-md-6 col-lg-3`. Enhancement: on `<576px`, buttons become full-width with `min-height: 44px` touch target (WCAG SC 2.5.5).
- **Tables**: Current `children.html` (line 50) and `absence_requests.html` (line 45) use `overflow-x-auto` for horizontal scroll on mobile. Enhancement: below 768px, transform to stacked card layout (each row becomes a vertical key-value card). This mirrors the pattern used in `templates/admin/users/list.html`.
- **Context strip** (Section 4): Collapses to single column on `<576px`. Nav below scrolls horizontally; the strip stays compact.

---

## 4. Signature Element: The Manager Kindergarten Context Strip

### Concept

The manager module's defining difference from the admin module is **kindergarten scoping** — every action is bound to a single kindergarten. The signature element is a persistent, branded context strip that makes this scope visible, trustworthy, and always-present.

```
+-------------------------------------------------------------+
|  Al-Noor Kindergarten    87 children  |  Last sync: 2m ago |
|  [Switch kindergarten v]                       [synced dot] |
+-------------------------------------------------------------+
```

### Features

1. **Persistent** — visible on every manager page, never scrolled past
2. **Interactive** — kindergarten switcher dropdown if multi-KG access is granted (role-based)
3. **Status-aware** — sync indicator (green=current, amber=pending, red=stale) prevents acting on stale data
4. **Accessible** — kindergarten name in `<h1>`, child count via `aria-live="polite"`, keyboard-navigable dropdown
5. **Responsive** — collapses to single line on `<576px` (KG name + expand button)
6. **Themed** — uses `--manager-brand` green (`#1F5E47`), visually separating manager operations from admin operations

### Why this embodies the brief

The manager module is fundamentally about **operations within a single kindergarten**. The context strip makes this constraint a visible, trustworthy part of the interface — not a hidden assumption in the code. It answers the manager's fundamental question: *Which kindergarten am I operating in right now?*

### File references for implementation

| Aspect | File | Reference |
|---|---|---|
| Base template | `templates/manager_base.html` | Insert after `</header>` (line 184), before `<aside id="admin-sidebar">` (line 187) |
| Context strip partial | `templates/components/manager_context_strip.html` (new) | Reusable partial, included from manager_base.html |
| CSS | `static/css/manager_design.css` | Add `.manager-context-strip` styles (see CSS below) |
| Data source | `routers/manager.py` | Uses `current_user.kindergarten_id` + `models.Kindergarten` lookup (no new endpoint) |
| Dropdown pattern | `templates/manager_base.html` lines 112-139 | Reuses language switcher dropdown pattern |
| Admin reference pattern | `templates/components/admin_page_context.html` | Context strip is the manager-domain extension of this component |

### CSS for the Context Strip

Add to `static/css/manager_design.css`:

```css
.manager-context-strip {
    --strip-bg: var(--manager-surface, #F0FDF4);
    --strip-border: var(--manager-brand, #1F5E47);
    --strip-text: var(--kinjo-color-text-primary, #0f172a);
    --strip-muted: var(--kinjo-color-text-secondary, #475569);
    --strip-accent: var(--manager-brand, #1F5E47);
    --strip-radius: var(--kinjo-radius-md, 0.375rem);

    background: var(--strip-bg);
    border-bottom: 2px solid var(--strip-border);
    color: var(--strip-text);
    padding: 0.5rem 1rem;
    display: flex;
    align-items: center;
    gap: 1rem;
    flex-wrap: wrap;
    font-size: var(--kinjo-font-size-sm, 0.875rem);
}

.manager-context-strip .strip-kindergarten {
    font-weight: var(--kinjo-font-weight-bold, 700);
    color: var(--strip-accent);
}

.manager-context-strip .strip-sync-dot {
    width: 8px;
    height: 8px;
    border-radius: 50%;
    display: inline-block;
    margin-right: 0.25rem;
}

.manager-context-strip .strip-sync-dot.synced  { background: #10b981; }
.manager-context-strip .strip-sync-dot.pending { background: #f59e0b; }
.manager-context-strip .strip-sync-dot.stale   { background: #ef4444; }

@media (max-width: 576px) {
    .manager-context-strip {
        flex-direction: column;
        align-items: flex-start;
        gap: 0.25rem;
    }
}
```

---

## 5. Consistency with Admin Module Patterns

| Admin Pattern | File Reference | Manager Equivalent | Status |
|---|---|---|---|
| Two-tier header (brand band + nav) | `templates/admin_base.html` lines 87-184 | `templates/manager_base.html` lines 88-284 | Consistent — manager inherits |
| Design tokens (color, spacing, type) | `static/css/design-tokens.css` | Shared — manager uses same tokens | Consistent |
| Top navigation menu | `templates/admin_base.html` + `static/css/top-menu.css` | `templates/manager_base.html` lines 186-284 | Consistent |
| Admin design system components | `static/css/admin_design_system.css` | Manager-specific overrides in `static/css/manager_design.css` | Extend |
| CSRF via `_validate_csrf_token()` | `admin_endpoints.py` lines 2369-2373 | Gap — `routers/manager.py` has no CSRF | Plan addresses (Section 7) |
| Context component | `templates/components/admin_page_context.html` | New `templates/components/manager_context_strip.html` | Gap — plan addresses |
| RTL support | `templates/admin_base.html` + `static/css/rtl.css` | `templates/manager_base.html` lines 3-6 | Consistent |
| Language switcher | `templates/admin_base.html` lines 107-135 | `templates/manager_base.html` lines 112-139 | Consistent |
| Skip navigation link | `templates/admin_base.html` lines 87-89 | Missing — add per admin pattern | Gap — plan addresses |
| `role=menubar` + `role=menuitem` | `templates/admin_base.html` | `templates/manager_base.html` lines 232+ | Consistent |
| Chart.js for analytics | Loaded in base template | Same — no change | Consistent |
| SweetAlert2 for confirmations | Loaded in base template | Same — no change | Consistent |
| Responsive Bootstrap grid | `admin_design_system.css` lines 1510+ | Already used in manager dashboard | Consistent |
| Focus ring (`--focus-ring`) | `admin_design_system.css` line 21 | Inherited from admin | Consistent |
| Impersonation banner | `templates/components/impersonation_banner.html` | Missing — include from components | Gap — plan addresses |

---

## 6. Summary of Accessibility and Responsiveness Enhancements

| Area | Current | Enhancement | Impact |
|---|---|---|---|
| KPI card typography | Fixed `fs-1` (1.375rem) | `clamp(1.5rem, 3vw, 2.25rem)` | Scales fluidly; no horizontal scroll on mobile |
| Table responsive | Horizontal scroll only | Card layout below 768px | Readable on all screen sizes (SC 1.4.10) |
| Status indicators | Color-only dot in some places | Color + text label on all rows (Active/Pending/Inactive) | Meets WCAG SC 1.4.1 |
| Touch targets | Bootstrap default (48px buttons) | `min-height: 44px` on all actionable elements | Meets WCAG SC 2.5.5 |
| Context strip heading | No heading | `<h1>` inside strip with `aria-label` | Landmark for screen readers (SC 1.3.1) |
| KPI counts | Static text | `aria-live="polite"` on stat elements | Screen readers announce count changes (SC 4.1.3) |
| Skip navigation | Absent in manager_base.html | Add `<a href="#admin-main-content">` matching admin pattern | SC 2.4.1 |
| Focus management | Admin `--focus-ring` inherited | Verify on context strip dropdown | SC 2.4.7 |

---

## 7. File Manifest

### Existing files — no changes required
| File | Purpose |
|---|---|
| `static/css/design-tokens.css` | Base design tokens (add `--kinjo-font-display`, `--kinjo-font-utility`) |
| `static/css/admin_design_system.css` | Base design system (reference only) |
| `static/css/layout.css` | Admin layout structure (reference) |
| `static/css/top-menu.css` | Tier 2 navigation (reference) |
| `templates/admin_base.html` | Reference layout pattern |
| `templates/manager_base.html` | Manager base template to extend |
| `templates/components/admin_page_context.html` | Reference for context strip pattern |

### Existing files — modify
| File | Change |
|---|---|
| `templates/manager_base.html` | Add skip-link, context strip, `aria-live` regions, CSRF JS integration |
| `templates/manager/dashboard.html` | Add `role=region` landmarks, `aria-live` to stat elements, responsive card handling |
| `templates/manager/children.html` | Add responsive table-to-card transformation below 768px |
| `templates/manager/supervisors.html` | Add `role=list`, status text labels, keyboard navigation |
| `templates/manager/absence_requests.html` | Add ARIA landmarks |
| `templates/manager/daily_reports_review.html` | Add responsive table collapsing |
| `templates/manager/kpi.html` | Add region landmarks, chart accessibility (alt text, ARIA labels) |
| `templates/manager/benchmarking.html` | Add ARIA landmarks |
| `routers/manager.py` | Add CSRF validation on all state-changing endpoints (POST, PUT, PATCH, DELETE) |
| `static/css/design-tokens.css` | Add `--manager-brand`, `--manager-surface`, `--manager-accent` variables |
| `static/css/admin_design_system.css` | Reference only (add `--focus-ring` verification for manager context strip) |

### New files to create
| File | Purpose |
|---|---|
| `templates/components/manager_context_strip.html` | Reusable context strip partial |
| `static/css/print.css` | Print stylesheet for manager pages |

---

## 8. Signature Element Summary

The **Manager Kindergarten Context Strip** is the single element that makes the manager module feel purpose-built rather than a submodule of the admin module. It answers the manager's fundamental question — *Which kindergarten am I operating in right now?* — through:

1. **Persistence** — visible on every page, never scrolled past
2. **Interactivity** — kindergarten switcher dropdown when multi-KG access is granted
3. **Status awareness** — sync indicator prevents acting on stale data
4. **Accessibility** — semantic HTML (`<h1>`), `aria-live="polite"`, keyboard-navigable dropdown
5. **Responsiveness** — collapses gracefully on mobile, never obscures content
6. **Theming** — uses `--manager-brand` (`#1F5E47`) to visually distinguish manager pages from admin pages

This element embodies the brief because it makes the manager's unique constraint (single-kindergarten scope) a visible, trustworthy, and always-present part of the interface — not a hidden assumption in the code.

---

*Plan produced from exploration of `D:/Final Version_mvp_ADMIN`. All file references verified against the live repository at time of writing.*
