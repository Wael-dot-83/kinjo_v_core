# KinJo Homepage Content, Visual, and Navigation Audit

**Audit date:** 2026-08-21
**Surface:** `/` / `templates/public/home.html`
**Scope:** Content accuracy and completeness, public header/footer consistency, responsive behavior, map-link presentation, and the reported navigation submenu behavior. Existing homepage image assets were not evaluated for replacement and are intentionally excluded from change recommendations.

## Executive summary

The homepage has a strong public-search premise and a coherent bilingual structure, but its marketing copy currently makes several claims that are either hard-coded, not source-attributed, or contradicted by the live public registry. The most concrete content error is the repeated claim of coverage across all 12 governorates: on the audit date, the public API returned 0 active public records for Aqaba while returning 1,375 records overall. The page should not present static national-coverage numbers unless they are generated from the same registry query or accompanied by a dated source.

The visual layer is not fully aligned with the documented design system. `DESIGN.md` identifies green (`#1F5E47`) as the public brand identity, while the later homepage override applies a blue/navy gradient over the existing header background image. The footer resolves to the green brand color, so header and footer do not currently read as one exact chrome treatment. This audit does not recommend changing any image; the flag treatment below is a CSS overlay/base-color treatment.

The navigation issue is reproducible as an information-architecture mismatch. “Services” is an anchor to `/services` (`home.html:114-117` and `302-304`), while the click-controlled desktop dropdown belongs to the separate “Governance & Partners” button (`home.html:120-177`). The mobile drawer has no equivalent toggle for that submenu. The actual backend routes exist and respond successfully, so the failure is in the menu contract and interaction model rather than route registration.

## Evidence collected

- Production homepage, public API, and public linked pages were reachable with HTTP 200 on the audit date.
- Live public registry total: **1,375** active, license-eligible records.
- Live public registry by governorate using the homepage’s Arabic filter values:

  | Governorate | Public active records |
  |---|---:|
  | Amman | 738 |
  | Irbid | 191 |
  | Zarqa | 136 |
  | Balqa | 76 |
  | Aqaba | 0 |
  | Karak | 36 |
  | Mafraq | 22 |
  | Jerash | 8 |
  | Ajloun | 32 |
  | Madaba | 35 |
  | Tafilah | 44 |
  | Ma'an | 57 |

- Playwright browser pass at 1,440×1,000 and 390×844: no horizontal overflow, no console/page errors, and the desktop Governance and Governorates controls open visibly on click.
- The desktop Governorates menu contains 12 native buttons but 0 elements with `role="menuitem"`; the Governance menu contains 4 links with `role="menuitem"`.
- Mobile menu opened successfully, but its Services entry is a direct link and its Governance section is a static list; neither is an expandable submenu.
- Axe-core returned no violations in the initial closed-menu state. That does not cover the menu semantics and keyboard behavior identified below.
- The bundled Impeccable detector reported one cramped-padding warning, repeated nested-card findings, and advisory image-hover-transform findings. These are quality signals, not reasons to modify any existing images.

## Audit health score

| Dimension | Score | Key finding |
|---|---:|---|
| Accessibility | 2/4 | Menu semantics are incomplete for the Governorates buttons, and quick-filter pills measure about 36px high on mobile, below the 44px touch-target recommendation. |
| Performance | 3/4 | Lazy loading is used for the lower-page showcase image and the page is stable in browser checks; remote Tailwind runtime, multiple CSS layers, backdrop blur, and large shadows remain avoidable cost. |
| Theming | 2/4 | Public design tokens define green as brand identity, but the header visually receives a navy/image override and many homepage rules use direct color literals. |
| Responsive design | 3/4 | Desktop and mobile fit without horizontal overflow, but mobile navigation parity and small quick-filter targets need work. |
| Implementation integrity | 2/4 | The main search flow is coherent, but hard-coded claims, a stale login prompt, and two competing menu models weaken trust and predictability. |
| **Total** | **12/20** | **Acceptable — significant content and interaction work is needed before calling the homepage fully consistent.** |

## 1. Content audit & copywriting findings

### P1 — National coverage claim is contradicted by live data

- **Locations:** `templates/public/home.html:387`, `402-405`, `454`, `636-640`, and `196-199`.
- **Finding:** The page says “all 12 governorates” and “nationwide coverage,” while Aqaba currently has 0 active public records. The filter still lists Aqaba, so a visitor can select it and receive an empty result set after seeing a national-coverage promise.
- **Impact:** This is a factual trust issue and creates a poor empty-state experience.
- **Recommendation:** Make coverage counts data-driven. Until all 12 have active public records, use “11 governorates currently represented” or a neutral statement that the registry is expanding. Do not hard-code the number in four separate locations.

### P1 — “100% Accreditation Compliance” overstates what the page proves

- **Location:** `home.html:643-649`.
- **Finding:** The public API intentionally filters to active records with a valid/approved/active license status or a null legacy license status (`api/kindergartens.py:467-480`). That is an inclusion rule, not evidence that the entire national sector has a 100% compliance rate.
- **Impact:** The metric can be read as a measured national performance claim.
- **Recommendation:** Replace the percentage with “Active, license-eligible records” or generate a dated percentage from an auditable source. Add “verified at time of publication” only if the data pipeline supports that statement.

### P2 — “24/7” needs a defined service promise

- **Location:** `home.html:651-657`.
- **Finding:** “24/7 Digital Care & Attendance” is presented as a service capability, but the page does not state whether this means platform availability, live monitoring, or an emergency support commitment.
- **Recommendation:** Use “Access care records anytime” for a safe product statement, or define the uptime/support commitment in the FAQ and link to it.

### P2 — Partner claims need verification and attribution

- **Locations:** `home.html:671-742` and `1057-1071`.
- **Finding:** “Official Institutional Partners & Beneficiaries” and “Part of Jordan’s National Digital Transformation Strategy” read as formal endorsements or affiliations. The logos are not linked to official partner pages and the page does not identify the source, agreement, or last verification date.
- **Recommendation:** Use “Institutions represented in the governance framework” unless formal partnerships are documented. Add a short source/verification note and link only where authorization exists. Do not imply endorsement from a logo alone.

### P2 — Ministry name is incomplete in English

- **Location:** `home.html:707-710`.
- **Finding:** `MoPIC` is expanded as “Ministry of Planning,” while the Arabic copy says “وزارة التخطيط والتعاون الدولي.”
- **Replacement:** “Ministry of Planning and International Cooperation.”

### P2 — Product terminology is inconsistent

- **Locations:** Throughout `home.html`, especially `6-7`, `395-405`, `419-422`, `681-688`, `761-770`, and `834-841`.
- **Finding:** The page alternates between *kindergarten*, *nursery*, *early childhood*, *accredited*, *licensed*, *registered*, *standards*, and *compliance* without defining how those terms relate.
- **Recommendation:** Use one canonical public term: “licensed kindergarten and early-childhood facility.” Use “listed in the public registry” for the directory and reserve “accredited” for a status that is actually supplied by the official data source.

### P2 — Mobile product section has an information gap

- **Location:** `home.html:983-1047`.
- **Finding:** The section presents “KinJo Mobile,” push notifications, and a request-access CTA, but provides no platform availability, access eligibility, app-store link, rollout status, or explanation of which roles can use it.
- **Recommendation:** Add one truthful status line, such as “Mobile access is available to participating families and staff; contact support to confirm eligibility,” or replace the section with a web-platform statement until native app distribution is available.

### P2 — The public-details promise conflicts with the legacy login prompt

- **Locations:** `home.html:1295-1299` versus `1317-1359`.
- **Finding:** The details modal correctly states that public registry details require no registration, but the hidden legacy prompt says visitors must log in to view full details.
- **Impact:** Future code paths or assistive technology can expose contradictory instructions.
- **Recommendation:** Remove the legacy prompt if it is no longer reachable, or change it to explain which actions require an account (for example, submitting an enrollment request) while keeping public viewing free.

### P2 — Footer wording is not idiomatic Arabic

- **Location:** `home.html:1089-1096`.
- **Finding:** “Support & Legal” is translated as “الدعم والمحددات القانونية,” which means legal constraints rather than legal/support resources.
- **Replacement:** “الدعم والشؤون القانونية” or, for a more user-facing label, “الدعم والمعلومات القانونية.”

### P3 — Copy polish

- “Browse by Governorate” is clearer as “Find a kindergarten by governorate.”
- “Statutory Staff Ratios” should be “Legally required educator-to-child ratios.”
- “Official Early Childhood & Kindergarten National Portal — Jordan” is grammatically heavy; use “Jordan’s National Early Childhood and Kindergarten Portal.”
- Add a “Last updated” date or “Data refreshed” status near the registry heading so visitors understand the freshness of results.
- Add an explicit contact expectation on the Contact page link, such as response hours or target response time, if the support team has a defined SLA.

## 2. Visual and design consistency findings

### Header

- `DESIGN.md` defines `--kinjo-brand: #1F5E47` as the public brand identity and `--kinjo-action: #1E40AF` as the interaction color.
- `static/css/home_modern.css:40-44` first sets the header background to the brand color.
- `static/css/home_public_overrides.css:10-16`, loaded later, adds a navy gradient plus `/static/images/kinjo-header-background.jpg` and a navy shadow. The computed mobile header still resolves its base color from the green token, but the visible header is a composited image/navy surface rather than an exact solid brand-green background.
- **Finding:** The header does not have one unambiguous design-spec treatment. The footer resolves to `#1F5E47` (`home_modern.css:277-290`), so header and footer are not visually identical chrome.
- **Recommendation:** Choose and document one rule: either exact solid brand green, or an explicitly documented image-backed header with a green/flag veil. Keep the existing image asset unchanged.

### Footer

- The footer has a strong landmark, four-column responsive grid, visible legal links, and a clear copyright row (`home.html:1052-1114`).
- Its green background is consistent with the public brand token, but its column heading style uses `uppercase` and `tracking-wider`; this has no effect on Arabic and can create a mixed-language hierarchy.
- Add a visible support contact or “Contact support” action if the footer is intended to be the primary support entry point. The current footer links to `/contact` but does not expose the support address/phone already available in the backend template context.

### Cards, spacing, and hierarchy

- The homepage uses several bordered/shadowed card layers: search container, results panel, metric strip, partner tiles, showcase card, governance cards, role cards, and mobile mockup. The detector flagged repeated nested-card patterns. Flattening one or two layers would improve hierarchy without touching images.
- The search area is visually strong but dense: the search form, quick governorate pills, result panel, and hero background all compete in the first viewport. The new result panel is correctly separated from the form, but the quick-pill row should be treated as a secondary shortcut, not another primary control group.
- Touch target measurement on mobile found quick governorate pills around 36px high. Increase them to at least 44px without changing their text or imagery.

### Jordan flag background implementation instructions

The following CSS treats the flag as a low-opacity decorative layer. It does not edit, replace, crop, or otherwise modify any existing homepage image. The content remains above the layer and the flag is hidden from assistive technology.

```css
/* Add after home_public_overrides.css, or fold into the canonical public layer. */
body.kinjo-public-home .kinjo-public-header {
  --kinjo-brand: #1f5e47;
  position: relative;
  isolation: isolate;
  background-color: var(--kinjo-brand) !important;
}

body.kinjo-public-home .kinjo-public-header::before {
  content: "";
  position: absolute;
  inset: 0;
  z-index: 0;
  pointer-events: none;
  opacity: .14;
  background:
    linear-gradient(to bottom,
      rgba(0, 0, 0, .85) 0 33.333%,
      rgba(255, 255, 255, .95) 33.333% 66.666%,
      rgba(31, 94, 71, .95) 66.666% 100%);
}

/* Red hoist triangle and a quiet star mark; decorative only. */
body.kinjo-public-home .kinjo-public-header::after {
  content: "✦";
  position: absolute;
  inset-block: 0;
  inset-inline-start: 0;
  z-index: 0;
  display: grid;
  place-items: center;
  width: 28%;
  color: rgba(255, 255, 255, .45);
  font-size: clamp(1rem, 2vw, 1.75rem);
  background: rgba(196, 35, 50, .45);
  clip-path: polygon(0 0, 100% 50%, 0 100%);
}

body.kinjo-public-home .kinjo-public-header > * {
  position: relative;
  z-index: 1;
}

@media (max-width: 767px) {
  body.kinjo-public-home .kinjo-public-header::before {
    /* Centered watermark: lower opacity preserves logo and menu contrast. */
    opacity: .07;
    background-position: center;
  }

  body.kinjo-public-home .kinjo-public-header::after {
    opacity: .22;
    width: 34%;
  }
}
```

For a strict exact-color requirement, use `background-color: #1F5E47` as the only header background and treat the flag as the low-opacity pseudo-element. If the existing image remains as a header background, the final rendered pixels will necessarily vary with the image; that cannot be described as one exact background color.

### Google Maps location-link audit

- No raw `googleusercontent.com` or `maps.google.com` URL is rendered as visible homepage text.
- The current details script creates a clean Google Maps URL from coordinates (`static/js/home-search.js:230-232`) and places it behind the “Open Location in Google Maps” button (`home.html:1272-1281`). This is the correct general pattern: show a friendly control, not a raw URL.
- The icon is currently `map`, not a location pin. Change the icon to `location_on`, add a specific accessible name, and build the URL with `URLSearchParams` so the display remains clean and the target is encoded safely.

```html
<a id="modal-kg-maps-btn"
   class="kg-map-link"
   target="_blank"
   rel="noopener noreferrer"
   aria-label="Open this kindergarten location in Google Maps">
  <span class="material-symbols-outlined" aria-hidden="true">location_on</span>
  <span>Open location in Google Maps</span>
</a>
```

```js
const mapsUrl = new URL('https://www.google.com/maps/search/');
mapsUrl.searchParams.set('api', '1');
mapsUrl.searchParams.set('query', `${kg.latitude},${kg.longitude}`);
modalKgMapsBtn.href = mapsUrl.toString();
```

The link should remain hidden when coordinates are absent. If a future data import includes a raw Maps URL, normalize it server-side and never place it in visible text.

## Positive findings

- The homepage has a clear search-first purpose and a useful public registry path.
- Public search and details are available without login, and the details endpoint restricts output to a safe public projection (`api/kindergartens.py:452-480`).
- The page includes bilingual direction handling, focus-visible styles, semantic `main`, `header`, `nav`, and `footer` landmarks, and image alt text was present for all 10 images observed in the browser pass.
- Search loading, empty, retry, and reset states are present and separated from the search controls.
- The main public routes and service anchors resolve successfully: `/`, `/services`, `/about`, `/contact`, `/faq`, `/privacy`, `/terms`, `/login`, and service anchors for parents, supervisors, managers, and standards.

## Prioritized action list

1. **P1 — Correct the governorate coverage and compliance claims.** Make registry counts and coverage labels data-driven; replace unsupported “100%” language.
2. **P1 — Establish one navigation contract.** Decide whether Services owns the governance submenu or Governance is a separate top-level menu, then implement the same behavior on desktop and mobile.
3. **P1 — Remove or rewrite the legacy login prompt.** It contradicts the public-details promise.
4. **P2 — Align header/footer chrome to the documented public brand token.** Add the flag as a CSS watermark layer without changing any existing image.
5. **P2 — Fix map-link semantics.** Use `location_on`, an accessible label, and a generated clean URL.
6. **P2 — Add data freshness and source language.** Show “Last updated” or “Registry refreshed” beside the public search heading.
7. **P2 — Increase quick-filter touch targets to at least 44px and add full menu keyboard semantics.**
8. **P3 — Reduce nested card depth and consolidate direct color literals after the content and navigation work is complete.**
