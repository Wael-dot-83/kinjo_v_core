# KinJo Design System

The visual system as it actually ships. Every value here is read from
`static/css/design-tokens.css`, and every contrast figure was measured in
Chromium against the surface the colour is used on — not calculated against
white and assumed.

Arabic is the default language and RTL the default direction. That is a
constraint on typography, not a translation layer bolted on afterwards.

---

## 01 Overview

**Mode: Operate.** These are dashboards, rosters, KPI panels and admin tools.
The visitor is completing a task — filing a daily report, checking whether a
kindergarten is compliant, finding one child in a list. Scanability,
consistency and legibility outrank expression. Brand lives in precise details:
the border colour, the focus ring, the masthead. It does not live in oversized
type or decorative motion.

The one exception is the public surface (`/`, `/login`, `/services`), which is
Persuade and may lead with the brand green and a display face.

**Two identities, deliberately separated.** Green is *identity*; blue is
*interaction*.

- `--kinjo-brand: #1F5E47` — logo lockup, login, public chrome, component borders
- `--kinjo-action: #1E40AF` — buttons, links, focus, active tabs

Green is already load-bearing as a **status** colour in this product ("جاهز" /
ready, healthy KPIs). Making primary actions green would erase that readiness
signal. This is the single most important rule in the system.

Four competing "primary" values once existed — `#2563eb`, `#1E40AF`, `#1F5E47`,
`#005ea8` — in four different stylesheets. Everything now points at
`--kinjo-action`. **Do not add a fifth.**

---

## 02 Colors

### Ground and text

| Token | Value | Notes |
|---|---|---|
| `--kinjo-color-bg-body` | `#FAF9F6` | Warm off-white. The previous `#f8fafc` was blue-tinted and fought the green chrome |
| `--kinjo-color-bg-surface` | `#ffffff` | Cards, panels |
| `--kinjo-color-bg-hover` | `#f1f5f9` | |
| `--kinjo-color-bg-active` | `#e2e8f0` | |
| `--kinjo-color-text-primary` | `#0f172a` | |
| `--kinjo-color-text-secondary` | `#475569` | |
| `--kinjo-color-text-muted` | `#64748b` | 4.52:1 on the canvas, against a 4.5 floor |

> **The canvas cannot get warmer.** `#F8F7F4` drops muted text to 4.44:1 and
> `#F7F6F2` to 4.40 — failing on every page at once. `#FAF9F6` is the warmest
> off-white the current text scale supports. Darkening it further requires
> darkening `--kinjo-color-text-muted` in the same commit.

### Fills are not foregrounds

The central lesson of this palette: **a colour tuned as a fill is not legible as
text.** Each status colour therefore has a fill value and one or more text
values, and they are not interchangeable.

| Role | Fill | As text on white | On a tint | On dark |
|---|---|---|---|---|
| Danger | `#ef4444` (3.76:1 ✗) | `#dc2626` 4.83:1 · `#b91c1c` 6.47:1 | — | `#f87171` 6.26:1 |
| Success | `#10b981` (2.54:1 ✗) | `#047857` 5.48:1 | `#036347` 5.81:1 | — |
| Warning | `#f59e0b` (2.15:1 ✗) | `#92620a` 5.28:1 | `#7d5408` 5.53:1 | — |
| Neutral | — | `#4b5563` 7.56:1 | | `#a8b6c8` 8.65:1 |

Additional derived values: `--kinjo-color-danger-action: #c81e1e` (5.74:1 with
white) for destructive buttons, and `--kinjo-color-link-accessible: #0a58ca`
(6.12:1 on the canvas — Bootstrap's `#0d6efd` is 4.27:1 and fails).

### Borders carry the brand

| Token | Value | Use |
|---|---|---|
| `--kinjo-color-border` | `#064E32` | The **outline** of a component — card, panel, input, table, dropdown |
| `--kinjo-color-border-subtle` | `#DCEAE3` | An **internal hairline** — table row separators |
| `--kinjo-color-ring` | `rgba(37,99,235,.3)` | Focus |

The two weights are load-bearing, not decorative. A component outline in the
brand green makes the product read as one material rather than green chrome
bolted onto grey components.

---

## 03 Typography

| | Family | Rasterized proof |
|---|---|---|
| Arabic (default) | `--kinjo-font-family-ar` → **Noto Sans Arabic** | CDP `CSS.getPlatformFontsForNode` |
| English | `--kinjo-font-family-en` → **Inter** | CDP, same method |

`--kinjo-font-family` resolves from the document language, so a component
inherits the right face without knowing which language it is in. Never name a
face directly in a component — that is how map labels ended up in `system-ui`
while every other string on the page was Noto.

**Scale** — `xs .75rem · sm .875rem · base 1rem · lg 1.125rem · xl 1.25rem ·
2xl 1.5rem · 3xl 1.875rem`. Weights 300/400/500/600/700.

Hierarchy is carried by size **and weight together**. On the login page: title
28px/800, body 17px/400, section heading 15px/700, label 14px/600 — identical
in both languages, a 1.65× title-to-body step.

### Arabic is not Latin with different glyphs

Three rules that do not apply to Latin type:

1. **12px is a hard floor.** Arabic loses its dots and diacritics before Latin
   loses anything. Use `rem`, never `em`, for anything near the floor —
   Bootstrap's `.badge { font-size: .75em }` compounded to **10.5px** inside a
   14px block.
2. **Don't declare `letter-spacing` on Arabic.** The common claim is that it
   breaks cursive joins. Measured in Chromium at 32px, it does not: `4px`
   tracking adds **+0.00px** to `الحضانة`, to `دار` (which contains
   non-joiners), and to `٢٠٢٦`. Chromium suppresses letter-spacing inside
   cursive runs, as CSS Text directs. Where it *does* land is word gaps
   (`+8px` across two spaces) and Latin embedded in Arabic (`+16px` on the
   `KPI` in `KPI لوحة`).

   So the rule is enforced not because joins were visibly breaking in Chromium
   — they were not — but because the declaration is inert where it looks
   meaningful, produces uneven word gaps and tracked Latin fragments where it
   is not, and depends on engine behaviour this project has verified only in
   Chromium. `[dir="rtl"]` text is pinned to `letter-spacing: normal`, with
   `lang="en"` and `.allow-tracking` as the documented escapes.
   Enforced by `tests/test_arabic_typography.py`.
3. **`text-transform: uppercase` is inert.** Arabic has no letter case, so it
   silently does nothing while changing the Latin around it.

---

## 04 Elevation

| Token | Value |
|---|---|
| `--kinjo-shadow-sm` | `0 1px 2px 0 rgba(0,0,0,.05)` |
| `--kinjo-shadow-md` | `0 4px 6px -1px rgba(0,0,0,.1), 0 2px 4px -1px rgba(0,0,0,.06)` |
| `--kinjo-shadow-lg` | `0 10px 15px -3px rgba(0,0,0,.1), 0 4px 6px -2px rgba(0,0,0,.05)` |
| `--kinjo-shadow-inner` | `inset 0 2px 4px 0 rgba(0,0,0,.06)` |

Radii: `sm .125rem · md .375rem · lg .5rem · xl .75rem · full 9999px`.
Motion: `fast 150ms` / `normal 250ms`, both `cubic-bezier(.4,0,.2,1)`.

**One boundary per surface.** A flat surface gets a border *or* a shadow, never
both — that pairing is the "ghost card" tell.

**Shadow means elevation, not decoration.** A shadow is correct when the
element genuinely floats: `.roster-bar` is `position: sticky; bottom: 0;
z-index: 5` and overlays scrolling content, so its upward shadow encodes
something true. A shadow on a surface that sits flat in the flow does not.

**No glassmorphism.** `backdrop-filter` is zero across every surface, verified
in-browser.

**Never animate layout properties.** Transition `transform` and `opacity`;
never `width`, `height`, or `top`.

---

## 05 Components

**Cards delegate their inset.** `.admin-card` / `.az-card` carry no padding;
`__header`, `__body`, `__footer` carry `var(--kinjo-spacing-4)`. A static
analyzer reads the wrapper as "children flush against the border" — measure the
children before believing it. The exception is a card wrapping a
`.table-responsive`, which takes `p-0` so the table meets the card edge and
supplies its own cell padding.

**A background and its foreground are one decision.** Setting only half is how
`.pagination .page-item.active .page-link` ended up painting a dark green
background while inheriting secondary grey text — 1.6:1.

**Bootstrap's tint pairs are decorative, not legible.** `.text-warning` on
`.bg-warning-subtle` measures 1.47:1. Override the foreground with the matching
`*-on-tint` token. These overrides live in `kinjo.css` because all three shells
(`base`, `admin_base`, `manager_base`) load it, whereas
`admin_design_system.css` never reaches `/kpi/dashboard`.

**Prefer `--bs-btn-*` custom properties** when restyling a Bootstrap button, so
hover and active states derive from the same colour instead of fighting it.

**Focus is never removed.** Focus rings use `--kinjo-color-ring`; the `0 0 0 3px`
shadows in the auth templates are focus rings, not decorative glows.

---

## 06 Do's & Don'ts

### Do

- Put every colour in `design-tokens.css` as a **semantic** token and reference
  it with `var()`. The colour-literal ratchet enforces this and budgets may only
  ever decrease.
- Name the *role*, not the value: `--kinjo-color-warning-text-on-tint`, not
  `--kinjo-amber-dark`.
- Measure contrast against the surface the colour actually sits on, compositing
  translucent ancestors.
- Re-key `?v=` to the sha256 prefix of the **committed** bytes whenever an asset
  changes. Assets are served `immutable` for a year.
- Prove a route's identity before trusting a measurement taken on it.

### Don't

- **Don't use green for primary actions.** It is the readiness signal.
- **Don't reach for a fill colour as text**, or a light-ground colour on a dark
  surface. Use the derived token.
- **Don't apply `letter-spacing` to Arabic**, and don't use
  `text-transform: uppercase` expecting it to do anything.
- **Don't size anything near the 12px floor in `em`** — it compounds.
- **Don't put a border and a shadow on the same flat surface.**
- **Don't add Subresource Integrity to first-party same-origin assets.** The
  digest is checkout-dependent; editing the file makes Chromium refuse to
  execute it. Vendor SRI stays.
- **Don't reference an undefined custom property.** CSS resolves custom
  properties at computed-value time, so an undefined token drops the whole
  declaration *silently* — this is why several "applied" fixes did nothing.

### Known open work

**Engine coverage.** The Arabic tracking behaviour above is measured in
Chromium only — WebKit and Firefox are not installed in this environment. If
either applies letter-spacing inside cursive runs, the guard is doing more work
there than it is here. Worth measuring before assuming either way.

**Detector blind spot, restated accurately.** `wide-tracking` and
`extreme-negative-tracking` read clean on this repository because they are
calibrated for Latin, and the values here (0.01–0.09em) sit below their
thresholds. That was how 142 Arabic nodes carrying tracking went unreported.
The lesson is not that the scan was hiding broken glyphs — it was not — but
that a clean scan is scoped to the rules someone wrote, and Arabic-specific
questions need Arabic-specific gates.
