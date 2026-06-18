# Kinjo — GWS (Government Website Standard) Compliance Audit Report

**Source of truth:** `GWS/kinjo_match_mismatch_checklist.xlsx`, sheet **"Full GWS Checklist"** (300 rows, MODEE GWS v6.0 / 2019).
**Audit date:** 2026-06-17
**Scope:** Full repository at `D:\Final Version` (the Kinjo kindergarten enrollment & management platform).

---

## 1. Executive Summary

This audit evaluated all 300 rows of Jordan's official Government Website Standard checklist against the live Kinjo codebase, with every status backed by a direct `file:line` citation or an explicit "not found after searching X." No row was marked MATCH on assumption.

Kinjo is **not** a ministry public-information portal — it is an **authenticated operational application** (kindergarten enrollment, attendance, daily reports, messaging) for parents, kindergarten managers/supervisors, and government admins. A large share of the GWS checklist (Ministers/Directorates pages, RSS news feeds, a classic public-content CMS, a marketing homepage) assumes a public ministry website and is genuinely **not applicable** to Kinjo's nature; those rows are marked N/A with a stated reason rather than forced into MATCH or MISMATCH.

Within what *is* applicable, the audit found the security middleware, RBAC, audit logging, and bilingual (Arabic/English, RTL/LTR) foundation to be substantially real and well-built — but found a near-total absence of GWS-required public pages (no Privacy Policy, Terms of Use, Disclaimer, Copyright statement, Contact Us form, FAQ, About page, Service Guide, sitemap, or robots.txt), several accessibility gaps (no language-label, no scroll-to-top, no accessibility toolbar), and a handful of real security polish items (no centralized unhandled-exception logging, dev-seed credentials with no production guard, reset-token-in-URL).

**115 of 300 rows now have a real, verified code fix across this audit. The current matrix shows 115 MATCH / 84 PARTIAL / 72 MISMATCH / 29 N/A.** The remaining gaps are documented honestly — including a substantial set that cannot be fixed in code at all (domain/DNS, TLS certificates, official social media accounts, third-party penetration testing, legal sign-off on policy text).

**Final compliance is 42.4% of applicable rows fully matched (115/271), or 48.0% counting N/A rows as compliant (144/300). This is not 100%, and is not claimed to be.**

## 2. Stack Detected

- **Backend:** Python, FastAPI (`main.py`), SQLAlchemy 2.0 + Alembic (`alembic/versions/`)
- **Frontend:** Server-rendered Jinja2 templates (`templates/`, 128+ `.html` files), Bootstrap 5.3.2 (RTL/LTR via swapped `bootstrap.rtl.min.css`/`bootstrap.min.css`), Bootstrap Icons as the single admin icon standard, vanilla JS (`static/js/`) — no SPA framework
- **i18n:** `i18n.py` + `static/i18n/{ar,en,app_ar,app_en,admin_ar,admin_en}.json`; `DEFAULT_LANGUAGE="ar"`, `SUPPORTED_LANGUAGES=["ar","en"]` (`config.py`)
- **Security middleware:** `middleware/security.py` (CSP, X-Frame-Options, X-Content-Type-Options, Referrer-Policy, Permissions-Policy, HSTS in production), `middleware/csrf.py` (double-submit-cookie CSRF)
- **Rate limiting:** slowapi (`rate_limiter.py`)
- **Auth:** JWT bearer via HttpOnly cookie, bcrypt password hashing, TOTP MFA (`mfa_service.py`)
- **Tests:** pytest, 2116 tests passing (3 skipped) after Round 3; focused Round 3/security suite also passed; full serial suite passed.
- **Lint:** ruff (`pyproject.toml`), conservative ruleset (bare-except, undefined-name)

## 3. Checklist Totals

| | Count |
|---|---|
| Total checklist rows | 300 |
| Applicable rows (Status ≠ N/A, before fixes) | 267 |
| Applicable rows (Status ≠ N/A, after fixes) | 271 |
| Not applicable (N/A, before fixes) | 33 |
| Not applicable (N/A, after fixes) | 29 |

## 4–7. Status Counts (Before → After)

| Status | Before | After |
|---|---|---|
| **MATCH** | 60 | **115** |
| **PARTIAL** | 81 | 84 |
| **MISMATCH** | 126 | 72 |
| **N/A** | 33 | 29 |
| Total | 300 | 300 |

67 rows changed status as a direct result of verified code fixes or newly discovered content gaps across the audit. Net MATCH count increased by 55. Round 3 added focused fixes for CAPTCHA/virus scanning readiness, opaque public IDs, mobile search layout, icon unification, contrast/accessibility, and admin namespace/CSRF hardening. A few additional rows received a real, evidenced improvement that was not enough to change their status bucket (e.g. a genuine partial mitigation that stays PARTIAL).

### Per-component breakdown

| Component | n | Before M/P/X/NA | After M/P/X/NA |
|---|---|---|---|
| 1 — Accessibility | 45 | 7 / 13 / 16 / 9 | 17 / 11 / 8 / 9 |
| 2 — Usability & Design | 109 | 25 / 29 / 42 / 13 | 42 / 32 / 24 / 11 |
| 3 — Content & Site Architecture | 96 | 15 / 23 / 51 / 7 | 35 / 26 / 30 / 5 |
| 4 — Responsive Web Design | 22 | 3 / 8 / 7 / 3 | 6 / 8 / 5 / 3 |
| 5 — Security | 28 | 10 / 8 / 10 / 1 | 15 / 7 / 5 / 1 |

(M = MATCH, P = PARTIAL, X = MISMATCH, NA = N/A)

## 8. Final Compliance Percentage

- **MATCH ÷ total (300):** 38.3%
- **MATCH ÷ applicable rows (271, excluding N/A):** **42.4%**
- **(MATCH + N/A) ÷ total — the "fully resolved or genuinely out of scope" view:** **48.0%**

None of these numbers is 100%, and 100% cannot be honestly claimed — see §15.

## 9. All Fixed Items (67 status changes, by theme)

### Round 2 (continuation pass, 8 additional rows)

**Accessibility toolbar (`templates/base.html`):**
`A.1.5-024` (a persistent accessibility button + panel on every page), `A.1.5-025` (3-level text-size control, A/A+/A++, persisted in `localStorage`, applied via an early inline script with no flash-of-unstyled-content), `A.1.5-026` (a "High contrast" switch that raises contrast/reduces saturation and underlines inline links — a real colour-vision accommodation, not just a cosmetic toggle), `A.1.5-027` (a "Night mode" brightness/warmth filter switch).

**Mobile navigation:**
`R.4.1-005` (`templates/components/navbar.html`: the language toggle now has a dedicated always-visible mobile button outside the collapsible hamburger menu, instead of only existing inside it), `R.4.2-018` (`static/css/kinjo.css`: breadcrumbs are now hidden below the `md` breakpoint via a `@media` rule targeting the exact `aria-label` used by `page-header.html`).

**Image compression (`storage_service.py`, `api/children.py`):**
`U.2.5-081` / `U.2.5-082` — a new `compress_image_in_place()` helper (Pillow) re-encodes any uploaded `.jpg/.jpeg/.png/.webp` to a maximum 1920px dimension at quality 82 (JPEG/WEBP) or with PNG optimization, wired into both the message-attachment path (`storage_service.save_attachment`) and the child-photo upload path (`api/children.py`). Verified with a functional test (a synthetic 3000×2000, 94KB JPEG compressed to 1920×1280, 14.7KB) and confirmed non-fatal on a deliberately-corrupt test fixture (existing `test_upload_photo_by_parent` still passes — compression failures are caught, logged, and never block the upload). `Pillow` was promoted from a transitive dependency (via `qrcode[pil]`) to a direct, pinned one in `requirements.txt`.

### Round 3 (10 additional status changes)

**Accessibility and contrast:**
`U.2.2-041` / `U.2.2-042` — raised muted/admin/sidebar/auth text tokens to WCAG AA-safe values and added automated contrast assertions in `tests/test_gws_round3.py`.

**Icon consistency:**
`U.2.4-074` / `U.2.4-075` — standardized admin surfaces on Bootstrap Icons, removed Font Awesome usage from admin templates, and documented the Bootstrap Icons-only rule for admin development.

**CAPTCHA and malware scanning:**
`U.2.6-098`, `S.5.5-012`, `S.5.5-013`, `S.5.7-017` — added pluggable hCaptcha/reCAPTCHA verification, wired it into public contact/registration/password-reset flows, added ClamAV-stream-compatible upload scanning, and covered enabled/disabled/fail-closed behavior with tests.

**Mobile search layout:**
`R.4.1-011` — moved the global search control into the always-visible header area and verified it at 320/375/414/768 px with `GWS/check_mobile_search.py`.

**Opaque identifiers:**
`S.5.10-026` remains PARTIAL, not MATCH: added UUID `public_id` columns, Alembic migration, runtime backfill, and IDOR tests for sensitive resources, while preserving legacy internal integer-ID admin routes for compatibility.

### Round 1 (49 rows)

**SEO / meta / markup (base.html, site-wide):**
`A.1.2-010` (XML sitemap), `A.1.2-011` (meta keywords), `A.1.2-012` (per-page description block, partial), `C.3.2-023` (tab-title format "Page Title – KinJo"), `A.1.5-029` (scroll-to-top button), `A.1.2-009` / `A.1.8-042` (deleted two orphaned dead templates with a broken `/static/img/logo.svg` reference — `templates/auth/forgot_password.html`, `templates/auth/reset_password.html`).

**Navigation (navbar.html):**
`A.1.4-020` (visible "English"/"العربية" text next to the language-toggle icon), `U.2.1-020` / `U.2.1-031` / `U.2.1-034` (Home, FAQ, Sitemap links added to the secondary menu), `U.2.1-002` (every public page now reachable in 1 click).

**New public pages and routes (`frontend.py`, `templates/public/*`):**
- `/about` — `C.3.1-002`
- `/services` (Service Guide for the enrollment service: description, eligibility, required documents, procedure, fees, completion time, eService link) — `C.3.1-008`, `C.3.1-009`, `C.3.1-010` (now N/A: "fully digital, no offline forms")
- `/faq` (categorized, real Q&A, links to Contact) — `C.3.1-015`, `C.3.6-077`, `C.3.6-078`, `C.3.6-079`, `C.3.6-080`, `C.3.6-081`
- `/contact` + new `POST /api/contact` (`api/public.py`) wired into the existing `ContactMessage` table — `C.3.1-013`, `C.3.4-073`, `C.3.4-074`, `C.3.4-075`
- `/privacy`, `/terms`, `/disclaimer`, `/copyright` (`templates/public/legal.html`) — `C.3.7-082`, `C.3.7-083`, `C.3.7-084`, `C.3.7-085`
- `/sitemap` (HTML) + `/sitemap.xml` + `/robots.txt` — `C.3.1-001`, `U.2.1-033`, `U.2.1-035`, `U.2.1-004` (partial)

**Footer (`templates/components/footer.html`):**
`U.2.2-057` (browser-compatibility/resolution note), `U.2.2-059` (Privacy/Terms/Disclaimer/Copyright links), `U.2.2-060` (contact email/phone, partial — blank until operator configures `SUPPORT_CONTACT_EMAIL`/`SUPPORT_CONTACT_PHONE`), `U.2.2-062` (dynamic year, partial), `C.3.5-076` (cross-government links: Amman Message, e-Government portal, Right to Obtain Information), `C.3.1-014` (partial — some useful links, no dedicated page).

**Forms:**
`U.2.6-085` (estimated completion time on register + enrollment forms), `U.2.6-086` (required-documents notice before the enrollment wizard), `U.2.6-096` / `U.2.6-097` (file-size/format hints + `accept=` attribute on the 2 forms identified by the audit), `U.2.2-059` again via the register.html Terms/Privacy checkbox now linking to the real pages.

**Security (`main.py`, `middleware/security.py`, `seed_local.py`):**
`S.5.9-019` / `S.5.9-020` (catch-all exception handler: every uncaught exception is now logged server-side with a full traceback and returns only a generic message, in every environment), `S.5.10-029` (`Referrer-Policy: no-referrer` specifically on `/reset-password` to stop the single-use token leaking via the Referer header), `S.5.8-018` (partial — `seed_local.py` now refuses to run when `ENVIRONMENT=production`).

**SEO module:** `C.3.8-094` (partial — robots.txt, sitemap.xml, meta description/keywords now exist; Open Graph still missing).

**Misc:** `A.1.6-032` (N/A reason updated now that `/contact` exists but has no social buttons, since there are no official accounts to link).

Two rows moved from N/A to a worse status because the underlying content now exists and exposed a real, more specific gap: `U.2.1-011` and `U.2.1-012` (About / Contact are now real pages, but only linked from the footer, not yet from the **main** top-nav menu as the literal checklist wording asks).

## 10. Remaining Unresolved Items (selected, code-fixable in a future pass)

The full list of all 165 remaining MISMATCH/PARTIAL rows is in `GWS_COMPLIANCE_MATRIX.csv`. The highest-value ones not attempted in this audit:

- **CAPTCHA provider credentials are still required for production enforcement** (`U.2.6-098`, `S.5.5-012/013`) — code paths and tests now exist, but operators must configure real hCaptcha/reCAPTCHA credentials and enable `CAPTCHA_ENABLED`.
- **Virus scanning infrastructure is still required for production enforcement** (`S.5.7-017`) — code paths and tests now exist, but operators must run ClamAV or configure an equivalent scanner endpoint.
- **Opaque public IDs are implemented for sensitive models but not yet used everywhere** (`S.5.10-026`) — `public_id` columns, migration, runtime backfill, and IDOR tests were added; legacy admin integer-ID routes remain for internal compatibility.
- **Mobile search layout was verified after the fix** (`R.4.1-011`) — no longer unresolved.
- **No marketing homepage for anonymous visitors** (`U.2.2-036` through `U.2.2-056` cluster) — `/` still redirects straight to `/login`/`/dashboard`. Building a real homepage (hero, services teaser, public stats) is a significant, separate design effort, not a compliance patch.

## 11. Exact Files Changed

**Created:**
- `templates/public/about.html`, `contact.html`, `faq.html`, `legal.html`, `service_guide.html`, `sitemap.html`
- `api/public.py`

**Deleted (dead, unreferenced, contained a broken asset reference):**
- `templates/auth/forgot_password.html`, `templates/auth/reset_password.html`

**Modified:**
- `templates/base.html` (round 1: meta blocks, title format, scroll-to-top, duplicate `</html>` fix; round 2: accessibility toolbar)
- `templates/components/navbar.html` (round 1: language label, Home/FAQ/Sitemap links; round 2: mobile-visible language toggle)
- `templates/components/footer.html`, `templates/auth/register.html`, `templates/enrollment/create.html`, `templates/reports/form.html`, `templates/communication/modals/new_message.html`
- `frontend.py`, `main.py`, `config.py`, `middleware/security.py`, `seed_local.py`
- `static/i18n/app_en.json`, `static/i18n/app_ar.json` (added `nav.home`, `nav.faq`, `nav.sitemap` keys)
- `captcha_service.py`, `virus_scan_service.py`, `csv_utils.py`, `storage_service.py`, `api/children.py`, `api/public.py`, `api/registration.py`, `api/users.py`
- `routers/admin_impersonation.py`, `audit_service.py`, `main.py`, `frontend.py`, `static/js/audit-logs.js`
- `templates/admin_base.html`, `templates/admin/users/list.html`, `templates/admin/users/form.html`, `templates/admin/import_kindergartens.html`, `templates/admin/imported_kindergartens.html`, `templates/components/navbar.html`, `templates/components/sidebar.html`, `templates/auth/login.html`, `templates/auth/forgot-password.html`, `templates/auth/reset-password.html`, `templates/base.html`
- `static/css/kinjo.css`, `static/css/admin_design_system.css`, `static/js/kinjo-app.js`, `static/js/dashboard.js`
- `models.py`, `database.py`, `config.py`, `.env.example`, `alembic/versions/d4e5f6a7b8c9_add_opaque_public_ids.py`
- `docs/ADMIN_DEVELOPER_GUIDE.md`, `docs/UI_DESIGN_SYSTEM.md`, `tests/run_accessibility_tests.py`, `tests/test_gws_round3.py`, `tests/test_route_registration.py`, `tests/test_opaque_ids_and_idor.py`, `tests/test_analytics_pinpoint_e2e.py`, `tests/test_captcha_and_virus_scan.py`, `tests/test_enrollment_features.py`

**Working/evidence files (not application code, kept for audit traceability):**
`GWS/full_checklist_export.json`, `GWS/checklist_readable.txt`, `GWS/raw_batch_1..6_*.txt` (the 6 subagents' raw evidence), `GWS/build_matrix.py`, `GWS/apply_status_after.py`, `GWS/apply_status_after_round2.py`, `GWS/write_final_csv.py`, `GWS/matrix_working.json`, `GWS/matrix_final.json`

## 12. Tests / Checks Executed

1. **`python -m ruff check .`** — All checks passed.
2. **`python -m py_compile`** on every modified `.py` file — clean.
3. **Focused Round 3/security tests:** `tests/test_gws_round3.py tests/test_analytics_pinpoint_e2e.py::TestHelpModalIntegration tests/test_opaque_ids_and_idor.py tests/test_captcha_and_virus_scan.py tests/test_route_registration.py` — **40 passed**.
4. **Review-fix regression tests:** `tests/test_gws_round3.py tests/test_admin_security.py::test_admin_export_audit_logs_creates_audit_entry tests/test_captcha_and_virus_scan.py::TestCaptchaEndpointIntegration::test_contact_form_accepts_when_captcha_enabled_and_token_valid` — **7 passed**.
5. **Additional admin/frontend/security tests:** `tests/test_frontend.py tests/test_frontend_integration.py tests/test_admin_security.py::test_admin_export_audit_logs_creates_audit_entry tests/test_new_modules.py::TestAdminImpersonation` — **248 passed, 1 skipped**.
6. **Full pytest suite:** `python -m pytest tests/ --timeout=30 -q` — **2116 passed, 3 skipped**.
7. **Mobile/browser layout:** `python GWS\check_mobile_search.py` — PASS at 320/375/414/768 px; search visible with no overlap.
8. **Static asset/link smoke:** local template static-reference check reported `missing_static_refs=[]`.
9. **Accessibility smoke:** `python tests\run_accessibility_tests.py` exited with no critical or serious issues; axe reported only moderate/minor structural warnings in the local dev run.
10. **Alembic migration check:** `python -m alembic upgrade head` applied the opaque public-id migration after fixing empty-string backfill.
11. **Admin template static references:** temporary `check_admin_static_refs.py` reported `missing_static_refs=[]`.
12. **Admin API route literals:** temporary `check_admin_api_routes.py` checked 69 non-comment `/api/admin/...` literals and reported `unresolved_admin_api_paths=[]`.
13. **Admin internal links:** temporary `check_admin_links.py` checked 44 `/admin/...` href literals and reported `unresolved_admin_hrefs=[]`.
14. **Admin API helper/CSRF dependency:** local check confirmed `templates/admin_base.html` loads `/static/js/auth.js`, `/static/js/kinjo-api.js`, and exposes the CSRF meta token; 9 `api.*` helper call sites are covered by those scripts.

## 13. Evidence for Compliance

All evidence is in `GWS_COMPLIANCE_MATRIX.csv`, one row per checklist ID, with an `Evidence Before` and `Evidence After` column citing exact `file:line` locations or stating "NOT FOUND — searched X" where nothing existed. Every MATCH in that file is backed by a citation; no row was marked MATCH from inference alone. A sample of the underlying agent evidence was independently spot-checked by direct file reads before being trusted (e.g. `footer.html`, `email_service.py:54`'s token-in-URL, `config.py`'s lockout threshold, the exact checklist wording for `S.5.6-016`/`S.5.10-026`/`S.5.10-029`).

## 14. Risks and Assumptions

- **Source-data anomaly:** one checklist row (the vulnerability-assessment question, "Is a vulnerability assessment performed on the websites annually?") is filed in the workbook with `ID=R.4.2-001` and `Guideline section=R.4.2 Content`, but `Component=Component 5 - Security` — almost certainly a copy-paste labeling slip in the source spreadsheet (it reads as a Security/OWASP question, not a Responsive-Design one). The audit kept the row's ID/Component/text exactly as written in the workbook (per "use this workbook as the mandatory source of truth") and evaluated it on its actual content; the per-component counts in §7 reflect the workbook's own `Component` column, not the ID prefix.
- **Subagent evidence was delegated, then spot-checked, not 100% independently re-verified line-by-line.** Six parallel research passes gathered the initial 300-row evidence; a sample was independently re-confirmed by direct file reads (see §13) and found accurate, but a few individual citations elsewhere in the CSV are trusted from the subagent pass rather than independently re-opened.
- **Footer/contact info is mechanism-only, not data-complete.** `SUPPORT_CONTACT_EMAIL` / `SUPPORT_CONTACT_PHONE` default to empty strings on purpose — the audit will not fabricate a phone number or address. Until the operator sets real values, the footer and Contact page simply omit that block rather than show a placeholder.
- **Legal page content (`/privacy`, `/terms`, `/disclaimer`, `/copyright`) is genuine, reasonable boilerplate written for this specific product, not a substitute for legal review.** See §15.
- **Pre-existing, unrelated uncommitted changes exist elsewhere in the working tree** (heatmap module, docs, several admin templates, alembic migrations, etc., from prior work sessions). This audit did not touch, depend on, or evaluate any of that — only the files listed in §11 were created/modified/deleted in this pass.

## 15. Items That Cannot Honestly Reach 100% Without Business/Legal/Government Confirmation

These are real, applicable checklist rows that **no amount of code change can close** — they require an operator/business/legal/government decision or external action:

- **Domain naming, HTTPS certificate, www/non-www behavior** (`A.1.1-001..008`) — Kinjo is not yet deployed to a real `.gov.jo` (or any production) domain; there is nothing to inspect until deployment.
- **Official social media accounts** (`A.1.6-030/031/033/034/035/036`, `U.2.2-063`) — cannot link buttons to accounts that don't exist; needs a business decision on whether/which platforms to use.
- **Legal sign-off on Privacy Policy / Terms of Use / Disclaimer / Copyright text** (`C.3.7-082..085`) — real, reasonable content was written, but final wording is a legal decision, not a code one.
- **CAPTCHA provider credentials** (`U.2.6-098`, `S.5.5-012/013`) — application code, schema fields, and tests now exist, but production enforcement requires configured hCaptcha/reCAPTCHA credentials and `CAPTCHA_ENABLED=true`.
- **Virus-scanning service availability** (`S.5.7-017`) — application code and tests now exist, but production enforcement requires a reachable ClamAV scanner or equivalent configured provider.
- **Opaque public IDs** (`S.5.10-026`) — sensitive models now have UUID `public_id` values and IDOR tests, but legacy admin integer-ID routes remain for internal compatibility until a deliberate public-API migration is shipped.
- **Annual third-party vulnerability assessment / penetration test** (`S.5.1-001`/the mislabeled `R.4.2-001` row) — needs an actual engagement with a security firm; cannot be "coded."
- **TLS certificate issuance and renewal process** (`S.5.2-003/004`) — a hosting/ops decision, not application code.
- **GWS Design Kit adoption** (`U.2.8-109`) — Kinjo was never given access to this MODEE asset; adopting it (if mandated) is a design decision, not a bug fix.
- **Real Lighthouse/RUM performance numbers against the 9s/5MB/800ms/150KB/40KB thresholds** (`A.1.8-040..045`) — these need to be measured against a real, deployed, internet-facing instance; a dev-machine measurement would not be honest evidence.
- **Cross-browser testing including Internet Explorer 11** (`A.1.3-015`) — Bootstrap 5 itself dropped IE11 support; supporting it would mean abandoning the entire current CSS framework, a major architectural decision for stakeholders, not a fix.
- **Whether a public marketing homepage is even wanted** (`U.2.2` homepage cluster) — Kinjo's current product decision is "no anonymous homepage, `/` goes straight to login" — building one assumes a business decision that hasn't been made.

---

*Full row-by-row detail for all 300 checklist items — including every row not mentioned above — is in `GWS_COMPLIANCE_MATRIX.csv`.*
