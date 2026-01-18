# KInJo Modules and User Workflows

This guide describes the implemented modules and the end-to-end flows for each user role. All API routes in `missing_endpoints.py` and most services are mounted under the `/api` prefix; communication routes are mounted under `/comm`. Frontend pages come from `frontend.py`.

## Modules

### Identity and Access

- Responsibilities: login, logout, token refresh, RBAC enforcement, parent self-registration, and current-user introspection.
- Key endpoints: `/token`, `/api/auth/login`, `/api/auth/logout`, `/api/auth/refresh`, `/api/auth/register`, `/api/register/parent`, `/api/users/me`.
- UI: `/login`, `/register`, `/dashboard` (role-aware dashboards for admin/manager, supervisor, and parent).

### Kindergarten and Classes

- Responsibilities: create and maintain kindergarten records, create classes with age bands, view class capacity, assign active enrollments to classes, and bind supervisors to classes.
- Key endpoints: `/api/kindergartens` (CRUD), `/api/classes` (create/list), `/api/classes/{class_id}/capacity-status`, `/api/enrollments/{enrollment_id}/assign-class`, `/api/supervisor/assign`, `/api/supervisor/my-classes`, `/api/supervisor/dashboard`, `/api/manager/dashboard`.
- UI: `/kindergartens`, `/kindergartens/create`, `/kindergartens/{id}`, `/dashboard`.

### Enrollment and Waitlist Readiness

- Responsibilities: parent-driven enrollment creation and submission, manager review (accept or reject), age eligibility enforcement (70 days to 56 months), duplicate-enrollment prevention, and visibility of waitlisted counts in the manager dashboard.
- Key endpoints: `/api/enrollment/apply`, `/api/enrollment/{enrollment_id}/submit`, `/api/enrollment/{enrollment_id}/review`.
- UI: `/enrollments`, `/enrollments/create`, `/enrollments/{id}`.

### Attendance

- Responsibilities: same-day check-in/check-out for children with active enrollments, attendance method tracking (PIN, QR, Kiosk), prevention of duplicate check-ins, and optional pickup/drop-off names.
- Key endpoints: `/api/attendance/check-in`, `/api/attendance/check-out`.
- UI: `/attendance/daily`, `/attendance/history`.

### Daily Reports

- Responsibilities: capture daily child activity (meals, naps, activities, notes), enforce report status transitions (DRAFT → SUBMITTED → APPROVED), and gate parent visibility to approved reports only.
- Key endpoints: `/api/daily-reports/create`, `/api/daily-reports/{report_id}/submit`, `/api/daily-reports/{report_id}/approve`, `/api/daily-reports/child/{child_id}`.
- UI: `/reports`, `/reports/create`, `/reports/{id}`.

### Communication (Messages, Events, Surveys)

- Responsibilities: direct/class/broadcast messaging, kindergarten-scoped events with optional consent flags, and NPS-enabled surveys with one response per parent.
- Key endpoints (prefixed with `/comm`): `/comm/messages`, `/comm/events`, `/comm/surveys`, `/comm/surveys/{survey_id}/submit`.
- UI: `/communication`, `/communication/messages`, `/communication/events`, `/communication/surveys`.

### Curriculum and Portfolio

- Responsibilities: curriculum outcome lookup, observation capture by learning domain, and child portfolios with publish gating.
- Key endpoints: `/api/curriculum/outcomes`, `/api/observations`, `/api/children/{child_id}/observations`, `/api/portfolios`, `/api/children/{child_id}/portfolio`.
- UI: `/curriculum`.

### Safety and Health

- Responsibilities: incident reporting with severity and follow-up flags, incident listing/updating, and child-level health alerts (allergies/conditions/medications).
- Key endpoints: `/api/incidents` (create/list/update), `/api/incidents/create` (manager-focused shortcut), `/api/children/{child_id}/health-alerts` (create/list).
- UI: `/safety`, `/safety/incidents/new`.

### KPI and Governance

- Responsibilities: calculate operational KPIs (attendance rate, incident rate, serious incident rate, ratio compliance), derive governance/experience scores, and generate monthly KPI snapshots.
- Key endpoints: `/api/kpi/summary`, `/api/kpi/attendance-rate`, `/api/kpi/governance-score`.
- UI: `/kpi/dashboard` (Chart.js visualization).

### Task Management

- Responsibilities: track operational tasks with priority, assignment, filtering, status toggling, and audit-friendly role checks.
- Key endpoints: `/api/tasks` (create/list), `/api/tasks/{task_id}` (read/update/delete), `/api/tasks/{task_id}/toggle`.
- UI: `/tasks`.

## Role-Based Workflows

### Admin Setup

- Sign in via `/login`, then create kindergartens (`/api/kindergartens`) and seed classes (`/api/classes`) as needed.
- Perform any manager-level operations (class assignment, approvals, attendance, communications) because admin passes manager role checks.
- Verify platform health with `/api/health` and adjust configuration in `.env`/`config.py` as required.

### Manager Day-to-Day

- Land on the manager dashboard (`/dashboard` UI or `/api/manager/dashboard`) to see pending applications, waitlist counts, attendance today, incident counts, and report approvals needed.
- Configure structure: create/update classes, assign supervisors (`/api/supervisor/assign`), and place accepted enrollments into classes (`/api/enrollments/{id}/assign-class`).
- Process enrollments: review submissions (`/api/enrollment/{id}/review`) and enforce kindergarten scope.
- Run operations: check children in/out (`/api/attendance/check-in` and `/api/attendance/check-out`), approve daily reports, and update incidents as follow-ups close.
- Engage families: send broadcasts, events, and surveys via `/comm` routes; monitor responses.
- Monitor performance: open `/kpi/dashboard` and pull `/api/kpi/summary` (or attendance/governance endpoints) for current-period scores.
- Coordinate work: create and manage tasks for staff with `/api/tasks`.

### Supervisor Day-to-Day

- Open the supervisor dashboard (`/dashboard` UI or `/api/supervisor/dashboard`) to see assigned classes, active children, attendance today, and pending drafts.
- Capture child learning: record observations (`/api/observations`) and create portfolio entries (`/api/portfolios`); parents only see published items.
- Produce and submit daily reports (`/api/daily-reports/create` then `/api/daily-reports/{id}/submit`) for manager approval.
- Maintain safety: log incidents (`/api/incidents`) and add health alerts when needed.
- Communicate and coordinate: send direct/class messages, view events/surveys, and update tasks assigned to them (`/api/tasks/{id}` or toggle).

### Parent Journey

- Register via `/register` UI or `/api/register/parent`, then sign in to the parent dashboard.
- Submit enrollment applications (`/api/enrollment/apply`) for a selected kindergarten, then finalize submission (`/api/enrollment/{id}/submit`); eligibility and duplicate checks run automatically.
- After acceptance and activation, monitor the child’s day: view approved daily reports (`/api/daily-reports/child/{child_id}`) and published portfolio items (`/api/children/{child_id}/portfolio`); observations use the same child-scoped endpoint.
- Participate in feedback loops by responding once per survey (`/comm/surveys/{id}/submit`); use incoming communications surfaced through the `/comm` routes when enabled.
