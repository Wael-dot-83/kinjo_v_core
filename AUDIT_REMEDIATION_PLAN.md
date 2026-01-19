# KinJo Remediation Plan (Admin Audit)

## Scope
- Based on the audit draft and code review of admin user management, authentication UI, and audit logging.
- Live validation of `/admin/users` was blocked by auth redirect; items below include verification steps.

## Quick Wins Implemented
- Login session-expired alert microcopy updated and kept hidden by default (`templates/auth/login.html`).
- Login loading text updated to a clear, dynamic message (`templates/auth/login.html`).
- Admin password reset now requires step-up verification via admin password and is rate-limited (`missing_endpoints.py`, `templates/admin/users/form.html`).
- Admin reset UI updated to collect admin password (`templates/admin/users/form.html`).
- User list destructive actions moved to data attributes to avoid inline onclick string escaping (`templates/admin/users/list.html`).
- Password length constraints aligned to 8 characters for admin resets and user creation (`templates/admin/users/form.html`).
- Audit logging added for login/logout/failed auth and access denied in user management (`main.py`, `missing_endpoints.py`).
- CSV import now supports structured per-row error details and UI rendering (`missing_endpoints.py`, `templates/admin/users/list.html`).
- Remember-me login now issues extended token TTL via `ACCESS_TOKEN_EXPIRE_MINUTES_REMEMBER` (`main.py`, `config.py`, `.env.example`, `static/js/auth.js`).

## Prioritized Remediation Backlog
- P3 | Owner: Frontend | ETA: M | Replace remaining inline handlers with delegated events (non-critical) | Dependency: none

## Patch Proposals (Pending)
- Document and enforce remember-me token TTL and storage rules.
- Expand audit logging to additional sensitive endpoints as needed.

## Verification Needed (Live)
- Manager scoping on list/view/update for `/api/users`.
- Bulk operations behavior and permission enforcement for non-admin users.
- Admin reset flow with step-up password verification and rate limiting.

