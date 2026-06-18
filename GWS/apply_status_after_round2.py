# -*- coding: utf-8 -*-
"""Round 2: apply Status After updates for the accessibility toolbar,
mobile-nav fixes, and image-compression pipeline."""
import json

with open("matrix_final.json", encoding="utf-8") as f:
    rows = json.load(f)
by_id = {r["ID"]: r for r in rows}


def upd(id_, status_after, evidence_after, files_changed):
    r = by_id[id_]
    r["Status Before"] = r["Status Before"]  # unchanged, kept for clarity
    r["Status After"] = status_after
    r["Evidence After"] = evidence_after
    r["Files Changed"] = files_changed
    r["Notes"] = "Fixed in round 2 (continuation pass)."


BASE = "templates/base.html"

upd("A.1.5-024", "MATCH",
    "base.html now has a persistent #a11yWidget toolbar (button + panel) on every page, with text-size, contrast, and night-mode controls, opened via a clearly labeled button near the scroll-to-top control.",
    BASE)
upd("A.1.5-025", "MATCH",
    "The accessibility panel's text-size buttons (A / A+ / A++) add html.a11y-text-lg / a11y-text-xl classes, scaling root font-size to 112.5%/125%; persisted in localStorage and re-applied on every page load via an early inline script (no flash).",
    BASE)
upd("A.1.5-026", "MATCH",
    "The accessibility panel's \"High contrast\" switch adds html.a11y-contrast, which raises contrast/reduces saturation site-wide and underlines inline links (so colour is not the only way to identify a link) — a real, working colour-vision accommodation.",
    BASE)
upd("A.1.5-027", "MATCH",
    "The accessibility panel's \"Night mode\" switch adds html.a11y-dim, applying a brightness/warmth filter to the page; persisted in localStorage like the other two controls.",
    BASE)

upd("R.4.1-005", "MATCH",
    "navbar.html now has a dedicated mobile-only language-toggle button (d-lg-none) placed in the always-visible header row, outside the collapsible #navbarMain — no longer hidden inside the hamburger menu on mobile. The original control is now d-none d-lg-block to avoid a duplicate once the menu is expanded.",
    "templates/components/navbar.html")
upd("R.4.2-018", "MATCH",
    "static/css/kinjo.css now hides nav[aria-label=\"Breadcrumb\"]/nav[aria-label=\"\\u0645\\u0633\\u0627\\u0631 \\u0627\\u0644\\u062a\\u0646\\u0642\\u0644\"] below the md breakpoint (max-width: 767.98px), matching the page-header.html breadcrumb markup exactly.",
    "static/css/kinjo.css")

upd("U.2.5-081", "MATCH",
    "storage_service.py now has compress_image_in_place(): any .jpg/.jpeg/.png/.webp upload is re-encoded with Pillow, capped at 1920px on its longest side, quality=82 for JPEG/WEBP and optimize=True for PNG. Wired into save_attachment() (used for message attachments) and verified with a functional test (3000x2000 94KB JPEG -> 1920x1280 14.7KB).",
    "storage_service.py, requirements.txt")
upd("U.2.5-082", "MATCH",
    "The same compress_image_in_place() helper is now also called from api/children.py's upload_child_photo() right after the file is written to static/uploads/photos/, so daily-report/child photos are capped the same way as message attachments. Compression failures are caught and logged, never block the upload (verified against a deliberately-invalid test fixture image used by the existing test_upload_photo_by_parent test, which still passes).",
    "api/children.py, storage_service.py")

with open("matrix_final.json", "w", encoding="utf-8") as f:
    json.dump(rows, f, ensure_ascii=False, indent=1)

from collections import Counter
print("Status After counts now:", Counter(r["Status After"] for r in rows))
changed_total = sum(1 for r in rows if r["Status Before"] != r["Status After"])
print("Total rows with a status change so far:", changed_total)
