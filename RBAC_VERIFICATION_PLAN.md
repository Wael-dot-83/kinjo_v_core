# KinJo RBAC and Admin Workflow Verification Plan

## Preconditions
- Test users: Admin, Manager (KG A), Supervisor, Parent.
- At least two kindergartens (KG A, KG B) with users assigned to each.

## Test Cases

RBAC-01 Admin access to admin user list
- Steps: Login as Admin. Navigate to `/admin/users`.
- Expected: User list loads, filters and actions visible.

RBAC-02 Manager scoping on user list
- Steps: Login as Manager (KG A). Call `GET /api/users` with no filters.
- Expected: Only KG A users returned.

RBAC-03 Manager cannot view other KG user
- Steps: Login as Manager (KG A). Call `GET /api/users/{user_id}` for KG B user.
- Expected: 403 or not found (per policy). No data returned.

RBAC-04 Manager create restrictions
- Steps: Login as Manager. Call `POST /api/users` with role ADMIN/MANAGER.
- Expected: 403. Non-privileged roles succeed within KG A.

RBAC-05 Admin bulk operations
- Steps: Login as Admin. Call `POST /api/users/bulk-create`, `bulk-status-update`, `bulk-delete`.
- Expected: 200/201 with valid results, AuditLog entries created.

RBAC-06 Non-admin bulk operations
- Steps: Login as Manager. Call the bulk endpoints.
- Expected: 403 denied.

SEC-01 Admin reset password step-up
- Steps: Admin triggers reset with correct admin password.
- Expected: 200 success and AuditLog entry.

SEC-02 Admin reset password with wrong admin password
- Steps: Admin triggers reset with invalid admin password.
- Expected: 401 and no password change.

SEC-03 Admin reset rate limit
- Steps: Trigger reset endpoint repeatedly within one minute.
- Expected: 429 rate limit response after threshold.

UI-01 Login session-expired alert
- Steps: Trigger a 401 and redirect to `/login?expired=true`.
- Expected: Session-expired alert shows only in this case; not on fresh `/login`.

UI-02 Login loading state
- Steps: Submit login with invalid credentials.
- Expected: Loading text shows only during submission and reverts on failure.

AUTH-01 Remember-me token expiry
- Steps: Call `/token` with and without `remember_me=true`, compare JWT exp claims.
- Expected: Remember-me token expiry is significantly longer than standard login.

XSS-01 User list escaping
- Steps: Create user with HTML in username/email, view in `/admin/users`.
- Expected: HTML is escaped, no script execution.

