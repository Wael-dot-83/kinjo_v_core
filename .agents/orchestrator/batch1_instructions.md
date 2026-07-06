# Instructions for Implementer - Batch 1 (Incident Management & Data)

Your task is to implement the first batch of production-readiness improvements for the Health & Safety page and incident management workflows.

## Refactoring & Consolidating Incident Management
- Consolidate all incident-related API routes from `api/children.py` into `api/safety_service.py` (or rename it to `api/incidents.py` if more appropriate, but updating imports).
- Ensure `POST /api/incidents` and `GET /api/incidents` are clearly namespaced.
- Remove duplicate incident creation functions: keep only one version (e.g. JSON payload) and delete the query-parameters endpoint (`POST /incidents/create` mentioned in the broad sweep).
- Remove the duplicate audit-logs endpoint mentioned in the broad sweep report (`audit_service.py` exposes them twice). Fix `main.py` namespacing for `/api/admin` to be consistent.

## Backend / Database Updates (R1 & R4)
- Add a `status` field to the `Incident` model (using an Enum for Open, Under Investigation, Action Required, Resolved, Closed).
- Add an `owner_id` (ForeignKey to users) for owner assignment.
- Create an `IncidentHistory` model to track status changes, owner changes, timestamps, and who made the change.
- Implement file attachments support (e.g. `attachment_url` is there, make sure the API accepts file uploads for medical reports/photos or URLs).
- Ensure role-based access control (RBAC): nursery staff (Supervisors) can only query or view incidents belonging to children in their assigned classes/kindergarten. Managers can see all in their kindergarten.
- Address N+1 queries in the incident listing endpoints (use SQLAlchemy `joinedload` for `child`, `reported_by`, `owner`, etc.).

## UI Updates
- Connect the frontend `/safety` page to the new real API-driven data. Remove hardcoded samples.
- The UI should support the new incident lifecycle statuses and show history.

## Output
Produce a detailed `handoff.md` with:
- Files changed.
- Tests or commands you ran to verify.
- Explanation of how RBAC is enforced.
