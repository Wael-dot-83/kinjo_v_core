# Known Limitations

## PDF Export

PDF generation for daily reports and analytics is not implemented in this release.

**Why:** Server-side PDF rendering (e.g., WeasyPrint, Puppeteer) requires additional system dependencies and was deferred to avoid deployment complexity.

**Alternatives available now:**
- Browser print (`Ctrl+P` / `Cmd+P`) — all report and analytics pages have a `@media print` stylesheet that produces a clean single-column layout suitable for saving as PDF.
- CSV export is available for attendance and enrollment data via the analytics endpoints.

**Planned:** A background export job using `export_jobs` table is modelled in the database. When a PDF library is added, the `POST /api/export/pdf` endpoint can be wired up to that queue without schema changes.

---

## Real-time Notifications

WebSocket push for KPI updates and alerts is implemented on `/ws/dashboard` with exponential back-off reconnection (1 s → 2 s → … → 30 s cap, ±10 % jitter, max 10 retries). A visible status pill in the dashboard header shows *Live / Reconnecting… / Live updates unavailable* so users are always informed of the connection state.

The server endpoint `/ws/notify` (message/incident push) is **not yet implemented**. Until it is, the page polls `GET /api/messages?unread=true` on a 60-second interval as a fallback so counts stay roughly accurate.

---

## Impersonation Scope

Admin impersonation is restricted to manager accounts only. Impersonating a supervisor or parent is intentionally blocked (`403`) to prevent privilege escalation through the supervisor's class-scoped data.

---

## Preferred Language Choices

Only Arabic (`ar`) and English (`en`) are accepted by `PUT /api/supervisor/settings`. Adding a new language requires:
1. Adding the locale file under `static/i18n/<code>.json`
2. Adding `<code>` to the `SUPPORTED_LANGUAGES` list in `.env` / `settings.py`
3. Updating the `preferred_language` validator in `routers/supervisor.py`

---

## Full-Text Search

Child and enrollment search uses SQL `LIKE` pattern matching. For datasets larger than ~50 000 rows, consider replacing with a PostgreSQL `tsvector` index or an external search service (e.g., MeiliSearch).

---

## Test Suite — Pre-existing Failures

Four tests in the suite were already failing before this sprint and are unrelated to changes made here:

| Test | Reason |
|------|--------|
| `test_frontend_integration.py::test_enrollment_list` | Frontend route returns login redirect; auth cookie not set in test client |
| `test_frontend_integration.py::test_kpi_dashboard` | Same auth redirect issue |
| `test_frontend_integration.py::test_404_template` | `/nonexistent` returns 200 (catch-all route) instead of 404 |
| `test_integration_comprehensive.py::TestEnrollmentWorkflowIntegration::test_full_enrollment_workflow` | `ImportError: cannot import name 'resolve_corresponding' from 'validators'` — missing function stub |

These do not affect the 287 tests that pass, including all 28 tests introduced in this sprint.
