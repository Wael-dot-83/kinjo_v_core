# -*- coding: utf-8 -*-
"""Apply Status After / Evidence After / Files Changed to matrix_working.json
based on the fixes made during Phase C of the GWS compliance audit."""
import json

with open("matrix_working.json", encoding="utf-8") as f:
    rows = json.load(f)
by_id = {r["ID"]: r for r in rows}


def upd(id_, status_after, evidence_after, files_changed):
    r = by_id[id_]
    r["Status After"] = status_after
    r["Evidence After"] = evidence_after
    r["Files Changed"] = files_changed


NAV = "templates/components/navbar.html"
FOOTER = "templates/components/footer.html"
BASE = "templates/base.html"
FRONTEND = "frontend.py"
DELETED = "templates/auth/forgot_password.html (deleted), templates/auth/reset_password.html (deleted)"

upd("A.1.2-009", "MATCH",
    "Orphaned dead templates with the broken /static/img/logo.svg <img> reference were unreferenced by any route; deleted. Live routes verified 200 via TestClient.",
    DELETED)
upd("A.1.2-010", "MATCH",
    "GET /sitemap.xml returns 200 with a valid <urlset> XML body listing all public routes (verified via TestClient).",
    FRONTEND)
upd("A.1.2-011", "MATCH",
    "base.html now renders a {% block meta_keywords %} <meta name=\"keywords\"> tag site-wide, bilingual.",
    BASE)
upd("A.1.2-012", "PARTIAL",
    "base.html now wraps the description in an overridable {% block meta_description %}; the 6 new public pages (about/contact/faq/legal/service_guide/sitemap) each set a unique description. The ~116 pre-existing templates still share the one global description block — not rolled out site-wide.",
    f"{BASE}, templates/public/about.html, templates/public/contact.html, templates/public/faq.html, templates/public/legal.html, templates/public/service_guide.html, templates/public/sitemap.html")
upd("A.1.4-020", "MATCH",
    "navbar.html language-toggle button now shows visible \"English\"/\"العربية\" text next to the translate icon (d-none d-lg-inline span), in addition to the existing icon.",
    NAV)
upd("A.1.5-029", "MATCH",
    "base.html adds a fixed #scrollToTopBtn shown after 400px of scroll, smooth-scrolling to top on click, included on every page.",
    BASE)
upd("A.1.8-042", "MATCH",
    "grep for logo.svg across templates/ now returns zero matches; the only two references (in unreferenced orphaned files) were removed.",
    DELETED)

upd("U.2.1-002", "MATCH",
    "Every public page (About/Services/FAQ/Contact/Privacy/Terms/Disclaimer/Copyright/Sitemap) is now reachable in exactly one click from any page via the navbar secondary menu or footer.",
    f"{NAV}, {FOOTER}")
upd("U.2.1-004", "PARTIAL",
    "A public /sitemap page now lists the main public, account, policy, and authenticated-area sections — a real improvement, though it curates key sections rather than literally enumerating every one of the ~90 internal routes.",
    "templates/public/sitemap.html, frontend.py")
upd("U.2.1-011", "MISMATCH",
    "An About page now exists and is linked from the footer, but it was not added to the main top navbar menu (only Home/FAQ/Sitemap were added there) — still not in the \"main menu\" as the checklist item specifically asks.",
    f"templates/public/about.html, {FOOTER}")
upd("U.2.1-012", "MISMATCH",
    "A public Contact Us page now exists and is linked from the footer, but it was not added to the main top navbar menu — still not in the \"main menu\" as the checklist item specifically asks.",
    f"templates/public/contact.html, {FOOTER}")
upd("U.2.1-020", "MATCH",
    "navbar.html secondary/utility menu now includes Home, FAQ, and Sitemap links alongside Notifications/Help/Language/User.",
    NAV)
upd("U.2.1-031", "MATCH",
    "An explicit \"Home\" text link (with icon) was added to the navbar secondary menu, distinct from the logo.",
    NAV)
upd("U.2.1-033", "MATCH",
    "GET /sitemap returns 200; templates/public/sitemap.html lists all major site sections grouped by category.",
    f"{FRONTEND}, templates/public/sitemap.html")
upd("U.2.1-034", "MATCH",
    "A Sitemap link was added to the navbar secondary menu, pointing to /sitemap.",
    NAV)
upd("U.2.1-035", "MATCH",
    "templates/public/sitemap.html groups links into four clearly labeled categories (Public pages, Account, Policies, Main app areas), giving a simple but real hierarchy.",
    "templates/public/sitemap.html")
upd("U.2.2-057", "MATCH",
    "footer.html now states \"Best viewed in Chrome, Edge, Firefox, or Safari at 1366x768 resolution or higher\" (bilingual).",
    FOOTER)
upd("U.2.2-059", "MATCH",
    "footer.html links to /privacy, /terms, /disclaimer, /copyright; the register.html Terms/Privacy checkbox text is now hyperlinked to the real pages.",
    f"{FOOTER}, templates/public/legal.html, templates/auth/register.html")
upd("U.2.2-060", "PARTIAL",
    "footer.html and the Contact page now render SUPPORT_CONTACT_EMAIL / SUPPORT_CONTACT_PHONE (new config.py settings) when the operator configures them; both default to empty so no fabricated contact info is ever shown. Fax, P.O. box, map link, and branches-directory link are still not present.",
    "config.py, frontend.py, templates/components/footer.html, templates/public/contact.html")
upd("U.2.2-062", "PARTIAL",
    "footer.html now renders a dynamic {{ current_year }} (computed server-side per request) instead of a hardcoded \"2026\" string — a real but partial step; it shows only the year, not a true last-modified date/timestamp.",
    f"{FRONTEND}, {FOOTER}")
upd("U.2.6-085", "MATCH",
    "register.html now states \"Create your parent account in about 3 minutes\"; enrollment/create.html states \"about 5 minutes\" in its pre-form notice.",
    "templates/auth/register.html, templates/enrollment/create.html")
upd("U.2.6-086", "MATCH",
    "enrollment/create.html now shows a notice listing required documents (birth certificate, health certificate) before the wizard steps begin.",
    "templates/enrollment/create.html")
upd("U.2.6-096", "PARTIAL",
    "A \"Max file size: {{ max_attachment_size_mb }} MB\" hint (sourced from config.py, not hardcoded) was added next to the 2 file inputs the audit evidence identified (daily report photos, message attachments). 4 other admin-only bulk-import file inputs (CSV/Excel import tools) were left unchanged.",
    f"templates/reports/form.html, templates/communication/modals/new_message.html, {FRONTEND}")
upd("U.2.6-097", "PARTIAL",
    "An \"Accepted formats: ...\" hint plus an explicit accept= attribute were added to the same 2 file inputs; the message-attachment input previously had no accept attribute at all. The 4 admin-only import file inputs were left unchanged.",
    "templates/reports/form.html, templates/communication/modals/new_message.html")

upd("C.3.1-001", "MATCH",
    "Both an HTML sitemap (/sitemap) and an XML sitemap (/sitemap.xml) now exist and return 200.",
    f"{FRONTEND}, templates/public/sitemap.html")
upd("C.3.1-002", "MATCH",
    "A public /about page now exists with real content about KinJo's purpose and users.",
    f"{FRONTEND}, templates/public/about.html")
upd("C.3.1-008", "MATCH",
    "A public /services page (Service Guide) now exists describing the kindergarten-enrollment service: description, eligibility, required documents, procedure, fees, completion time, and an \"Apply online\" eService link.",
    f"{FRONTEND}, templates/public/service_guide.html")
upd("C.3.1-009", "MATCH",
    "The same /services page serves as the public Services listing for the platform's one core public service.",
    f"{FRONTEND}, templates/public/service_guide.html")
upd("C.3.1-010", "N/A",
    "templates/public/service_guide.html explicitly states \"Needed forms: None — the enrollment form is completed entirely online\" — a genuine, now-documented reason this does not apply (fully digital service, no offline forms to guide).",
    "templates/public/service_guide.html")
upd("C.3.1-013", "MATCH",
    "A public, unauthenticated /contact page with a real form now exists, POSTing to a new public /api/contact endpoint that creates rows in the existing ContactMessage table. Verified end-to-end with TestClient (200, message persisted).",
    f"{FRONTEND}, templates/public/contact.html, api/public.py, main.py")
upd("C.3.1-014", "PARTIAL",
    "footer.html now has a \"Government Links\" section with some useful external links (Amman Message, e-Government portal, Right to Obtain Information); there is no dedicated standalone Useful Links page.",
    FOOTER)
upd("C.3.1-015", "MATCH",
    "A public /faq page now exists with categorized, real enrollment/account Q&A content.",
    f"{FRONTEND}, templates/public/faq.html")
upd("C.3.2-023", "MATCH",
    "base.html's <title> block now renders \"{Page Title} &ndash; KinJo\" (en dash + site name) for every page; verified rendered output on /about.",
    BASE)
upd("C.3.4-072", "PARTIAL",
    "The Contact page and footer now show email/phone when SUPPORT_CONTACT_EMAIL/SUPPORT_CONTACT_PHONE are configured (new config.py settings, blank by default). Fax, P.O. box, a Google Maps link, a national call-center number, and a branches-directory link are still not present.",
    f"config.py, {FRONTEND}, templates/public/contact.html, {FOOTER}")
upd("C.3.4-073", "MATCH",
    "A public, unauthenticated Contact Us page with a real form now exists at /contact (verified 200 via TestClient).",
    "templates/public/contact.html")
upd("C.3.4-074", "MATCH",
    "The Contact form collects a subject/contact-type dropdown, name, optional phone, and required email, validated server-side via the ContactMessageCreate Pydantic schema in api/public.py.",
    "templates/public/contact.html, api/public.py")
upd("C.3.4-075", "MATCH",
    "On successful submission the page shows a confirmation alert with the server-returned message (\"Your message has been received...\"); verified via TestClient (200, message field present in JSON response).",
    "templates/public/contact.html, api/public.py")
upd("C.3.5-076", "MATCH",
    "footer.html now has a \"Government Links\" column linking to the Amman Message website, the e-Government portal, and the Right to Obtain Information page.",
    FOOTER)
upd("C.3.6-077", "MATCH",
    "A public /faq page now exists.",
    f"{FRONTEND}, templates/public/faq.html")
upd("C.3.6-078", "MATCH",
    "An FAQ link was added to the navbar secondary menu, reachable from every page.",
    NAV)
upd("C.3.6-079", "MATCH",
    "FAQ questions are short, direct questions (e.g. \"How do I enroll my child?\", \"I forgot my password. What do I do?\").",
    "templates/public/faq.html")
upd("C.3.6-080", "MATCH",
    "FAQ content is grouped under two category headings: Enrollment, and Account & access.",
    "templates/public/faq.html")
upd("C.3.6-081", "MATCH",
    "The FAQ page ends with a link to /contact for questions not covered, giving visitors a way to ask something new.",
    "templates/public/faq.html")
upd("C.3.7-082", "MATCH",
    "A public /privacy page now exists with real Privacy Policy content (data collected, usage, retention/security, user rights).",
    f"{FRONTEND}, templates/public/legal.html")
upd("C.3.7-083", "MATCH",
    "A public /copyright page now exists with a real Copyright Statement.",
    f"{FRONTEND}, templates/public/legal.html")
upd("C.3.7-084", "MATCH",
    "A public /terms page now exists with real Terms of Use content; the register.html checkbox now links to it.",
    f"{FRONTEND}, templates/public/legal.html, templates/auth/register.html")
upd("C.3.7-085", "MATCH",
    "A public /disclaimer page now exists with a real Disclaimer section.",
    f"{FRONTEND}, templates/public/legal.html")
upd("C.3.8-094", "PARTIAL",
    "robots.txt, sitemap.xml, and per-page meta description/keywords now exist. Open Graph tags are still not implemented anywhere.",
    f"{FRONTEND}, {BASE}")

upd("S.5.8-018", "PARTIAL",
    "seed_local.py now refuses to run (raises RuntimeError) when ENVIRONMENT=production, preventing the known dev admin credentials from ever being seeded into a real production database. The dev/test seed itself still intentionally sets must_change_password=0 for local convenience (by design, gated to non-production).",
    "seed_local.py")
upd("S.5.9-019", "MATCH",
    "main.py now has a catch-all @app.exception_handler(Exception) returning a generic {\"detail\": \"Internal server error.\"} with no internal details, in every environment (the FastAPI app already runs with debug=False since no debug= kwarg is passed to the constructor).",
    "main.py")
upd("S.5.9-020", "MATCH",
    "The same catch-all handler calls logger.exception(...) first, guaranteeing every uncaught exception is captured with a full traceback in the app's own structured log before the generic response is returned.",
    "main.py")
upd("S.5.10-029", "PARTIAL",
    "middleware/security.py now sets Referrer-Policy: no-referrer specifically on the /reset-password page (instead of the site-wide strict-origin-when-cross-origin), so the single-use reset token cannot leak to a third-party resource via the Referer header. The token is still carried in the URL query string itself by design (existing email-link flow; hashed at rest, single-use, 15-minute expiry per the password-reset implementation) — this is a mitigation, not a full fix.",
    "middleware/security.py")

# Items whose underlying facts changed slightly even though status didn't move
upd("A.1.6-032", "N/A",
    "A public Contact Us page now exists (templates/public/contact.html) but contains no social-media buttons, since KinJo has no official social media accounts to link yet.",
    "templates/public/contact.html")

# Default: everything else keeps Status Before as Status After (no code change made)
unchanged = 0
for r in rows:
    if not r["Status After"]:
        r["Status After"] = r["Status Before"]
        r["Evidence After"] = r["Evidence Before"]
        r["Files Changed"] = ""
        r["Notes"] = "No code change made in this audit pass; see Gap / Fix Needed."
        unchanged += 1

with open("matrix_final.json", "w", encoding="utf-8") as f:
    json.dump(rows, f, ensure_ascii=False, indent=1)

print("Rows updated with a real fix:", len(rows) - unchanged)
print("Rows unchanged:", unchanged)
print("Total:", len(rows))

from collections import Counter
print("Status Before counts:", Counter(r["Status Before"] for r in rows))
print("Status After counts:", Counter(r["Status After"] for r in rows))
