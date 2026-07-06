# Instructions for Implementer - Batches 2 & 3 (UI/UX, Filtering, Metrics)

Your task is to implement the second and third batches for the Health & Safety page (`/safety`) and incident management workflows.

## Advanced UI/UX & Filtering (R2)
- Update `templates/safety/index.html` (and any associated JS like `static/js/safety.js`) to implement comprehensive table filtering for Incidents:
  - Filters: Date range, Child name, Incident Type, Severity, Status, and general text search.
  - Implement saved states for these filters (e.g. using URL parameters or localStorage).
- Enhance the incident table with frontend sorting, pagination, and empty/loading/error states.
- Add export capabilities (buttons/functions for PDF, Excel, Print). You can use existing libraries (like DataTables if already in the project, or simple CSV generation in JS).
- Ensure mobile responsiveness and RTL alignment consistency (`dir="rtl"`, Bootstrap 5 RTL classes like `ms-` and `me-` instead of `ml-` and `mr-`).

## Health Alerts & Dashboard Metrics (R3)
- Build Dashboard Summary Cards at the top of the `/safety` page showing:
  - Total Open Incidents
  - High-Severity Incidents
  - Resolved Incidents
  - You may need to fetch these from `/api/incidents` and calculate on the frontend, or add a summary endpoint to `safety_service.py`.
- Build a Health Alerts section:
  - Fetch children with medical conditions/allergies (either from `HealthAlert` table or `Child` medical notes).
  - Display them prominently on the Health & Safety page.

## Requirements
- Do not introduce large new frameworks; use the vanilla architecture / Bootstrap 5 / JS already present.
- Ensure all fetch calls are CSRF-safe (they are intercepted by `auth.js` globally, so `fetch` is fine).
- DO NOT CHEAT. Write genuine implementations.

## Output
Write your findings and what you changed to `d:\Final Version\.agents\batch2_3_worker\handoff.md` and send a completion message.
