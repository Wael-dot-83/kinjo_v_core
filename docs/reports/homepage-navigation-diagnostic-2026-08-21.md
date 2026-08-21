# KinJo Homepage Navigation Diagnostic

**Issue:** A submenu does not appear when users select certain homepage navigation items.
**Audit date:** 2026-08-21
**Files inspected:** `templates/public/home.html`, `static/js/home-search.js`, `static/css/home_modern.css`, `static/css/home_public_overrides.css`, and `scripts/compat/frontend_orig.py`.

## Reproduction and expected behavior

### Expected navigation contract

The reported structure implies:

- Services (`الخدمات`) is a parent menu.
- Its submenu includes governance/partner content, represented by the gavel icon and `الحوكمة والشركاء`.
- Governorates (`المحافظات`) is a separate location menu.
- About, Contact, FAQ, Language, and Login are direct actions or links.

For both desktop and mobile, selecting a parent should reveal its submenu, update `aria-expanded`, allow keyboard focus to enter the menu, and close the menu after a child action.

### Actual implementation

- Desktop Services is a direct anchor to `/services` (`home.html:114-117`). It has no submenu button, `aria-expanded`, or menu container.
- Desktop Governance & Partners is the click-controlled dropdown (`home.html:120-177`) with `id="governance-menu-btn"` and four linked menu items.
- Desktop Governorates is a separate click-controlled dropdown (`home.html:179-253`) with 12 native buttons, but those buttons do not have `role="menuitem"`.
- Mobile Services is again a direct anchor (`home.html:300-304`).
- Mobile Governance & Partners is a static section with four links (`home.html:328-344`), not an expandable submenu and not associated with `aria-expanded`/`aria-controls`.
- About, Contact, and FAQ are direct links on desktop and mobile (`home.html:256-264`, `347-355`).
- The language control calls `toggleLanguage()` (`home.html:268-274`, `1122-1138`) and is not a submenu.
- Login is a direct link (`home.html:282-284` and `359-361`) and is not a submenu.

## Browser evidence

The production homepage was checked with Playwright at 1,440×1,000 and 390×844:

| Check | Result |
|---|---|
| Desktop Governance button click | `aria-expanded="true"`; menu visible; 4 linked menu items |
| Desktop Governorates button click | `aria-expanded="true"`; menu visible; 12 native buttons, 0 `role="menuitem"` nodes |
| Mobile menu toggle | `aria-expanded="true"`; drawer visible; 9 links and 12 governorate buttons |
| Mobile Services selection | Direct `/services` link; no submenu state |
| Console/page errors | None observed |
| Backend routes | `/services`, `/about`, `/contact`, `/faq`, `/privacy`, `/terms`, and `/login` all returned HTTP 200 |

## Root-cause assessment

### Confirmed root cause: navigation model mismatch

The click target described as “Services” is not the element that owns the submenu. The submenu is owned by a different “Governance & Partners” button. A test or user expecting Services to open the governance submenu will either navigate immediately to `/services` or see no submenu at all. This is the primary failure point.

### Confirmed secondary cause: no mobile submenu parity

The mobile drawer duplicates the navigation markup rather than sharing the desktop menu state. The desktop Governance button has a small JavaScript controller, but the mobile Governance block is static. Selecting mobile Services therefore cannot trigger a submenu because there is no mobile submenu controller attached to it.

### Confirmed semantics gap: mixed menu-item roles

The Governance menu uses links with `role="menuitem"`; the Governorates menu uses buttons without the role. This can cause keyboard and assistive-technology navigation to behave differently between the two menus. There is also no arrow-key roving focus model for the 12 governorate buttons.

### Contributing fragility: two visibility authorities

Each desktop dropdown combines Tailwind visibility classes (`hidden group-hover:block hover:block`) with JavaScript toggling of `.hidden` (`home.html:1156-1193`). Pointer hover, click, keyboard, and outside-click behavior therefore compete to control the same state. The current browser pass opens the menus, but this arrangement is fragile across touch devices, focus transitions, and CSS build changes.

### Not root causes

- The route declarations are present in `scripts/compat/frontend_orig.py:202-248` and are included through `frontend.py` and `main.py`.
- The homepage has no server redirect or missing-route problem for Services, About, Contact, FAQ, Privacy, Terms, or Login.
- `selectGovernorate()` is exposed by `home-search.js:205-215`; the governorate quick buttons can call it. It should still close the parent menu after selection.

## Recommended code fix

### 1. Choose the canonical information architecture

To match the reported structure, make Services the parent button and put the governance link inside its submenu. Keep Governorates as its own parent. Do not retain a second, separate Governance top-level dropdown unless product explicitly wants both.

Example desktop shape:

```html
<div class="relative" data-menu="services">
  <button id="services-menu-btn"
          type="button"
          aria-expanded="false"
          aria-controls="services-menu"
          aria-haspopup="true">
    <span class="material-symbols-outlined" aria-hidden="true">dashboard_customize</span>
    <span>Services</span>
    <span class="material-symbols-outlined" aria-hidden="true">expand_more</span>
  </button>
  <div id="services-menu" role="menu" hidden>
    <a href="/services" role="menuitem">Service guide</a>
    <a href="#trusted-partners" role="menuitem">
      <span class="material-symbols-outlined" aria-hidden="true">gavel</span>
      Governance and partners
    </a>
  </div>
</div>
```

If product instead intends Governance to remain top-level, change the acceptance criteria and labels so the button is explicitly named Governance & Partners. Do not call it a Services submenu.

### 2. Use one state mechanism, not hover plus hidden-class competition

Use the native `hidden` attribute as the single source of truth:

```js
document.querySelectorAll('[data-menu]').forEach((container) => {
  const button = container.querySelector('[aria-haspopup="true"]');
  const menu = container.querySelector('[role="menu"]');
  if (!button || !menu) return;

  const setOpen = (open) => {
    menu.hidden = !open;
    button.setAttribute('aria-expanded', String(open));
  };

  button.addEventListener('click', () => {
    setOpen(menu.hidden);
  });

  button.addEventListener('keydown', (event) => {
    if (event.key === 'ArrowDown' || event.key === 'Enter' || event.key === ' ') {
      event.preventDefault();
      setOpen(true);
      menu.querySelector('[role="menuitem"]')?.focus();
    }
    if (event.key === 'Escape') {
      setOpen(false);
      button.focus();
    }
  });

  menu.addEventListener('click', (event) => {
    if (event.target.closest('[role="menuitem"]')) setOpen(false);
  });

  container.addEventListener('focusout', (event) => {
    if (!container.contains(event.relatedTarget)) setOpen(false);
  });

  document.addEventListener('click', (event) => {
    if (!container.contains(event.target)) setOpen(false);
  });
});
```

Remove `group-hover:block hover:block` from these menus. Hover can be added as a progressive enhancement only after click, focus, keyboard, and touch behavior are correct.

### 3. Make mobile use the same menu contract

Either render the same `data-menu` structure inside the drawer or give the mobile parent its own button:

```html
<button type="button"
        data-mobile-menu-trigger="services"
        aria-expanded="false"
        aria-controls="mobile-services-menu">
  <span>Services</span>
  <span class="material-symbols-outlined" aria-hidden="true">expand_more</span>
</button>
<div id="mobile-services-menu" hidden>
  <a href="/services">Service guide</a>
  <a href="#trusted-partners">
    <span class="material-symbols-outlined" aria-hidden="true">gavel</span>
    Governance and partners
  </a>
</div>
```

When a governorate button is used, close the Governorates menu and move focus or scroll to the result panel. Add `role="menuitem"` to every button in a `role="menu"`, or remove the menu role and use a normal grouped navigation list.

### 4. Correct the map control while touching navigation-adjacent UI

The public detail modal currently uses the `map` Material Symbol. Change it to `location_on`, add an accessible label, and generate the Google Maps URL through `URLSearchParams`. Keep the visible control clean and keep it hidden when coordinates are unavailable. See the implementation block in the visual audit.

## Regression tests to add

1. Desktop: click Services; assert its submenu is visible and `aria-expanded="true"`.
2. Desktop: press Enter and ArrowDown on Services; assert first child receives focus.
3. Desktop: click a Services child; assert submenu closes and target route/hash is correct.
4. Desktop: click Governorates; assert all 12 options are keyboard reachable and selecting one closes the menu.
5. Mobile: open drawer, expand Services, assert the same children and `aria-expanded` state are present.
6. Mobile: expand and close Governance/Governorates independently; assert no stale open menu remains.
7. Language toggle and Login remain direct actions and are not intercepted by the menu controller.
8. Run the route-link check for `/services`, `/about`, `/contact`, `/faq`, `/privacy`, `/terms`, and `/login`.

## Diagnostic verdict

**The backend navigation routes are healthy. The reported submenu failure is caused by a front-end menu-contract mismatch and missing mobile submenu implementation.** Establishing one parent/submenu structure, using one visibility state mechanism, and testing both desktop and mobile will resolve the failure class and prevent regressions.
