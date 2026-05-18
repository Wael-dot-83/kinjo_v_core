# KinJo UI Design System

Design system date: 2026-04-28
Implementation files: `static/css/kinjo.css`, `static/css/admin_design_system.css`, `templates/base.html`, `templates/admin_base.html`

## Design Foundations

### Color System

KinJo uses a restrained operational palette anchored by professional blue and supported by semantic colors.

| Role | Token | Light | Dark |
| --- | --- | --- | --- |
| Primary action | `--kinjo-primary`, `--admin-primary` | `#2563eb` | `#60a5fa` |
| Success | `--kinjo-success`, `--admin-success` | `#10b981` | `#34d399` |
| Warning | `--kinjo-warning`, `--admin-warning` | `#f59e0b` | `#fbbf24` |
| Error | `--kinjo-danger`, `--admin-error` | `#ef4444` | `#f87171` |
| Surface | `--kinjo-surface`, `--admin-bg-white` | `#ffffff` | `#111827` |
| Body text | `--kinjo-text-primary`, `--admin-text-primary` | `#1e293b` / `#0f172a` | `#f8fafc` |

Warnings use dark foreground text through `--kinjo-text-on-warning` and `--admin-text-on-warning` to meet WCAG AA contrast where amber backgrounds are used.

### Typography System

Primary English UI font: Inter. Primary Arabic UI font: Cairo for the main app and Noto Sans Arabic for admin.

The scale is fixed rather than viewport-fluid to keep dense dashboards predictable:

`12px`, `14px`, `16px`, `18px`, `20px`, `24px`, `30px`

Line height defaults to `1.5` for English and `1.65` for Arabic/RTL reading comfort.

### Spacing System

The base unit is 4px. Core tokens:

`4px`, `8px`, `12px`, `16px`, `20px`, `24px`, `32px`, `40px`, `48px`

Touch targets use a 44px minimum through `--kinjo-touch-target` and `--admin-touch-target`.

## Component Library

### Buttons

Use Bootstrap `.btn` variants in the main app and `.admin-btn` variants in admin. Primary, success, warning, error/danger, secondary, ghost, icon, small, and large states are tokenized.

Expected states: default, hover, active, focus-visible, disabled. Focus-visible uses tokenized focus rings and must remain visible against both light and dark surfaces.

### Forms

Inputs and selects inherit surface, text, border, focus, disabled, and placeholder tokens. Labels use `14px` with medium weight. Required fields should use the existing `.required` helper.

### Cards

Cards use an 8px maximum radius, tokenized borders, and restrained shadows. Use cards for repeated items, dialogs, and framed tools; avoid nesting cards inside cards.

### Data Display

Tables use semantic header backgrounds, uppercase-free spacing, and tokenized hover states. Badges use semantic colors and must include readable foreground colors, especially warning badges.

### Feedback

Alerts, dropdowns, modals, skeletons, and empty states are tied to surface and semantic tokens. Motion is disabled or minimized when `prefers-reduced-motion` is set.

## Responsive Design

Breakpoints follow Bootstrap's mobile-first model:

| Range | Use |
| --- | --- |
| 320px-639px | Single-column mobile flows, fixed 44px touch targets |
| 640px-1023px | Tablet grid expansion and denser filters |
| 1024px-1279px | Full dashboard/sidebar workflows |
| 1280px+ | Wider data tables and multi-column admin views |

Use `.container-kinjo` for tokenized max-width content in new pages. Existing Bootstrap grids remain supported.

## Theme Strategy

Both base templates expose `data-theme="{{ ui_theme | default('light') }}"`. The CSS includes an opt-in `[data-theme="dark"]` token set for the main app and admin.

Theme implementation rule: toggle `data-theme` at the `html` element and do not hard-code page colors in templates unless there is a product requirement.

## Accessibility Standards

Minimum target: WCAG AA.

- Normal text contrast: 4.5:1 minimum.
- Large text and UI component boundaries: 3:1 minimum.
- Touch targets: 44px minimum for primary interactive controls.
- Keyboard support: all custom buttons, links, controls, dropdown triggers, and form controls require visible `:focus-visible`.
- Motion: animations and transitions respect `prefers-reduced-motion`.
- Bilingual layout: LTR and RTL flows rely on logical properties where practical.

## Developer Handoff

For new interface work:

1. Start with tokens in `kinjo.css` or `admin_design_system.css`.
2. Reuse `.btn`, `.form-control`, `.card`, `.table`, `.admin-btn`, `.admin-form-control`, `.admin-card`, and `.admin-table`.
3. Avoid inline colors and pixel-only one-off styles in templates.
4. Verify light theme, dark theme hook, keyboard focus, mobile width, and RTL layout before release.
