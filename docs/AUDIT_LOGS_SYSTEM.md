# AUDIT LOGS SYSTEM — ERROR, WARNING, AND INFO DEFINITIONS

> **Version:** 1.0.0
> **Date:** 2026-01-26
> **Status:** Implementation-Ready
> **Applies to:** KinJo Platform v1.x

---

## Table of Contents

1. [Global Logging Standard](#1-global-logging-standard)
2. [Error Object Schema](#2-error-object-schema)
3. [ERROR Definitions (ERR_001–ERR_021)](#3-error-definitions)
4. [WARNING Definition (WARN_001)](#4-warning-definition)
5. [INFO Definitions (INFO_001–INFO_083)](#5-info-definitions)
6. [Redaction & Privacy Appendix](#appendix-a-redaction--privacy)
7. [Alerting & Monitoring Appendix](#appendix-b-alerting--monitoring)
8. [QA Checklist](#appendix-c-qa-checklist)
9. [Localization Readiness](#appendix-d-localization-readiness)

---

## 1. Global Logging Standard

### 1.1 Event Naming Convention

All audit events follow the pattern:

```
audit.<domain>.<action>.<result>
```

**Examples:**
- `audit.auth.login.success`
- `audit.auth.login.failure`
- `audit.user.create.success`
- `audit.kindergarten.delete.success`
- `audit.enrollment.approve.success`

### 1.2 Log Levels

| Level   | Severity       | Usage                                                              |
|---------|----------------|--------------------------------------------------------------------|
| `ERROR` | Critical/High  | Operation failed; data loss risk, security violation, or outage    |
| `WARN`  | Medium         | Degraded state; anomaly detected but system continues              |
| `INFO`  | Low            | Normal operation completed successfully; audit trail record        |

### 1.3 Timestamp

All timestamps MUST be ISO 8601 UTC:

```
2026-01-26T07:55:11.123Z
```

- Database column: `DateTime(timezone=True)` with `server_default=func.now()`
- JSON output: Always serialize as UTC with `Z` suffix
- Never use local time in log records

### 1.4 Standard Fields (All Logs)

Every audit log record MUST include:

| Field             | Type       | Required | Description                                    |
|-------------------|------------|----------|------------------------------------------------|
| `event_id`        | string     | YES      | Unique code (e.g., `ERR_001`, `INFO_042`)      |
| `event_name`      | string     | YES      | Canonical name (e.g., `audit.auth.login.failure`) |
| `level`           | string     | YES      | `ERROR`, `WARN`, or `INFO`                     |
| `timestamp`       | string     | YES      | ISO 8601 UTC                                   |
| `correlation_id`  | string     | YES      | Request-scoped UUID from `X-Correlation-ID`    |
| `request_id`      | string     | YES      | Unique per HTTP request                        |
| `action`          | string     | YES      | Action enum (e.g., `LOGIN_FAILED`)             |
| `entity_type`     | string     | YES      | Target entity (e.g., `Auth`, `User`)           |
| `message`         | string     | YES      | Human-readable summary                         |

### 1.5 Actor Fields

| Field          | Type    | Required | Description                          |
|----------------|---------|----------|--------------------------------------|
| `user_id`      | integer | NO*      | Acting user ID (*null for anonymous)  |
| `role`         | string  | NO*      | Actor role (`admin`, `manager`, etc.) |
| `ip_address`   | string  | YES      | Client IP address                    |
| `user_agent`   | string  | NO       | Browser/client user agent string     |

### 1.6 Target Fields

| Field          | Type    | Required | Description                            |
|----------------|---------|----------|----------------------------------------|
| `entity_type`  | string  | YES      | Target type (e.g., `User`, `Class`)    |
| `entity_id`    | integer | NO       | Target record ID                       |
| `endpoint`     | string  | NO       | API endpoint path                      |
| `http_method`  | string  | NO       | `GET`, `POST`, `PUT`, `DELETE`         |

### 1.7 Outcome Fields

| Field              | Type    | Required for ERROR | Description                          |
|--------------------|---------|-------------------|--------------------------------------|
| `status`           | string  | YES               | `success`, `failure`, `partial`      |
| `http_status`      | integer | YES               | HTTP response status code            |
| `error_code`       | string  | YES (errors only) | Enum code (e.g., `AUTH_LOGIN_FAILED`)|
| `retryable`        | boolean | YES (errors only) | Whether client can retry             |
| `latency_ms`       | integer | NO                | Request duration in milliseconds     |
| `sensitivity_level`| integer | YES               | 1=Low, 2=Medium, 3=High             |

### 1.8 Data Minimization Policy

- Log only fields listed in the standard schema
- Never log request/response bodies by default
- For debugging: log truncated body (first 256 chars), content-type, and status code
- Store full debug payloads only in secure debug storage with 72-hour retention and restricted access

### 1.9 PII Policy

**Classified as PII:**
- Email addresses
- Phone numbers
- National ID / Passport numbers
- Home addresses
- Child names (in combination with parent identifiers)

**Masking Rules:**
- Email: `w***@domain.com` (first char + mask + domain)
- Phone: `+9627******12` (country code + first digit + mask + last 2)
- National ID: `****5678` (mask all but last 4)
- Names: Allowed in audit logs (needed for investigation) but excluded from external exports

**Never Log:**
- Passwords, password hashes, reset tokens
- MFA secrets, API keys, session tokens
- Full authorization headers
- Credit card / payment data

### 1.10 Sensitive Fields Redaction List

```python
SENSITIVE_FIELDS = {
    'password', 'hashed_password', 'secret', 'token', 'api_key',
    'admin_password', 'new_password', 'old_password', 'access_token',
    'refresh_token', 'private_key', 'secret_key', 'mfa_secret',
    'credit_card', 'cvv', 'session_id'
}
```

---

## 2. Error Object Schema

All API error responses MUST use this schema:

```json
{
  "error": {
    "code": "AUTH_LOGIN_FAILED",
    "message": "Invalid username or password.",
    "details": {},
    "fields": {},
    "request_id": "req_a1b2c3d4",
    "correlation_id": "corr_e5f6g7h8",
    "timestamp": "2026-01-26T07:55:11.123Z",
    "retryable": false
  }
}
```

| Field            | Type   | Required | Description                                     |
|------------------|--------|----------|-------------------------------------------------|
| `code`           | string | YES      | Machine-readable error code                     |
| `message`        | string | YES      | User-safe message (no internal details)         |
| `details`        | object | NO       | Additional context (never PII or secrets)       |
| `fields`         | object | NO       | Per-field validation errors                     |
| `request_id`     | string | YES      | Unique request identifier                       |
| `correlation_id` | string | YES      | Trace correlation ID                            |
| `timestamp`      | string | YES      | ISO 8601 UTC                                    |
| `retryable`      | boolean| YES      | Whether the client should retry                 |

---

## 3. ERROR Definitions

---

### ERR_001 — Authentication Failed

| Field                | Value                                                                 |
|----------------------|-----------------------------------------------------------------------|
| **Event ID**         | `ERR_001`                                                             |
| **Event Name**       | `audit.auth.login.failure`                                            |
| **Error Code**       | `AUTH_LOGIN_FAILED`                                                   |
| **Log Level**        | ERROR                                                                 |
| **Severity**         | High                                                                  |
| **Category**         | Authentication                                                        |
| **Sensitivity**      | 2 (Medium)                                                            |

**When to Trigger:**
The `/api/auth/login` endpoint receives a POST with credentials that fail validation — either the username does not match any active user record, or the password hash comparison returns false.

**Meaning:**
A login attempt was made with invalid credentials. The actor could be a legitimate user who mistyped, or a malicious actor attempting credential stuffing.

**Likely Root Causes:**
1. User mistyped username or password
2. User account was deactivated or deleted after the login page loaded
3. Credential stuffing or brute-force attack
4. Stale cached credentials in a client application
5. Password was recently changed and user is using old password
6. Username enumeration probe

**User Impact:**
User sees a login error and cannot access the platform. After repeated failures, the account or IP may be rate-limited.

**System Impact:**
No data corruption. Excessive failures increase auth service load and may trigger rate limiting for legitimate users sharing an IP.

**Detection Signals:**
- Spike in `LOGIN_FAILED` audit logs (> 10/min per IP)
- High ratio of failed-to-successful logins (> 50% in 5-min window)
- Same IP with different usernames (credential stuffing pattern)

**Recommended Response:**

| Phase        | Action                                                                              |
|--------------|-------------------------------------------------------------------------------------|
| Immediate    | Rate-limit the source IP after 5 failures in 5 minutes                              |
| Engineering  | Implement progressive delays; add CAPTCHA after 3 failures                          |
| Prevention   | Add account lockout after 10 failures; monitor with alert rule; add geo-IP checks   |

**Logging Fields:**

| Field            | Required | Redaction      |
|------------------|----------|----------------|
| `correlation_id` | YES      | —              |
| `ip_address`     | YES      | —              |
| `user_agent`     | YES      | —              |
| `username`       | YES      | Mask as email  |
| `endpoint`       | YES      | —              |
| `http_method`    | YES      | —              |
| `failure_reason` | YES      | Generic only*  |

*`failure_reason` must be generic: `"invalid_credentials"`. Never distinguish between "user not found" vs "wrong password" in logs or responses.

**User-Facing Message:**
- **Text:** "The username or password you entered is incorrect. Please try again."
- **Message Key:** `error.auth.login_failed`
- **UI Action:** Focus the password field; show "Forgot password?" link

**HTTP Mapping:**

| Field         | Value                         |
|---------------|-------------------------------|
| Status Code   | `401 Unauthorized`            |
| Response Body | Error object with `AUTH_LOGIN_FAILED` |

**Retry Guidance:**
- Client retry: Yes, with user correction
- Backoff: Not applicable (user-driven)

**Example Structured Log:**
```json
{
  "event_id": "ERR_001",
  "event_name": "audit.auth.login.failure",
  "level": "ERROR",
  "timestamp": "2026-01-26T07:55:11.123Z",
  "correlation_id": "corr_a1b2c3d4-e5f6-7890-abcd-ef1234567890",
  "request_id": "req_f1e2d3c4",
  "action": "LOGIN_FAILED",
  "entity_type": "Auth",
  "entity_id": null,
  "user_id": null,
  "ip_address": "192.168.1.100",
  "user_agent": "Mozilla/5.0 ...",
  "endpoint": "/api/auth/login",
  "http_method": "POST",
  "http_status": 401,
  "status": "failure",
  "error_code": "AUTH_LOGIN_FAILED",
  "sensitivity_level": 2,
  "retryable": true,
  "details": {
    "username": "w***@domain.com",
    "failure_reason": "invalid_credentials"
  }
}
```

**Example API Error Response:**
```json
{
  "error": {
    "code": "AUTH_LOGIN_FAILED",
    "message": "The username or password you entered is incorrect.",
    "request_id": "req_f1e2d3c4",
    "correlation_id": "corr_a1b2c3d4-e5f6-7890-abcd-ef1234567890",
    "timestamp": "2026-01-26T07:55:11.123Z",
    "retryable": true
  }
}
```

**Observability:**
- **Alert:** `LOGIN_FAILED` count > 50/hour per IP → P2 security alert
- **Dashboard:** "Failed Logins" time-series chart, grouped by IP and username prefix

---

### ERR_002 — Token Expired or Invalid

| Field                | Value                                                                 |
|----------------------|-----------------------------------------------------------------------|
| **Event ID**         | `ERR_002`                                                             |
| **Event Name**       | `audit.auth.token.invalid`                                            |
| **Error Code**       | `AUTH_TOKEN_INVALID`                                                  |
| **Log Level**        | ERROR                                                                 |
| **Severity**         | Medium                                                                |
| **Category**         | Authentication                                                        |
| **Sensitivity**      | 2 (Medium)                                                            |

**When to Trigger:**
Any authenticated endpoint receives a request where the JWT token in the `Authorization` header or cookie is expired, malformed, has an invalid signature, or references a non-existent user.

**Meaning:**
The request carried an authentication token that could not be validated. This is normal for expired sessions but could indicate token theft or tampering.

**Likely Root Causes:**
1. Token expired after `ACCESS_TOKEN_EXPIRE_MINUTES` (30 min default)
2. User's browser sent a stale cookie after session timeout
3. Token was signed with a different `SECRET_KEY` (deployment mismatch)
4. Token was manually crafted or tampered with (attack)
5. Clock skew between server and token issuer
6. User was deleted or deactivated after token was issued

**User Impact:**
User is redirected to the login page. Any unsaved form data may be lost.

**System Impact:**
No data corruption. May cause a cascade of 401s if a frontend SPA retries multiple API calls simultaneously.

**Detection Signals:**
- Sudden spike in 401 responses across all endpoints
- Token signature mismatches (indicates tampering or key rotation issue)
- Expired tokens with timestamps far in the past (> 24h)

**Recommended Response:**

| Phase        | Action                                                                     |
|--------------|---------------------------------------------------------------------------|
| Immediate    | Return 401; frontend redirects to login                                    |
| Engineering  | Implement silent token refresh; add token-expiry warning in frontend       |
| Prevention   | Add token rotation; monitor for signature mismatch spikes                  |

**Logging Fields:**

| Field            | Required | Redaction                       |
|------------------|----------|---------------------------------|
| `correlation_id` | YES      | —                               |
| `ip_address`     | YES      | —                               |
| `endpoint`       | YES      | —                               |
| `token_error`    | YES      | Generic: `expired` or `invalid` |
| `token_sub`      | NO       | User ID only, no token value    |

**Never log the token value itself.**

**User-Facing Message:**
- **Text:** "Your session has expired. Please log in again."
- **Message Key:** `error.auth.token_expired`
- **UI Action:** Redirect to `/login` with return URL preserved

**HTTP Mapping:**

| Field         | Value                          |
|---------------|--------------------------------|
| Status Code   | `401 Unauthorized`             |
| Response Body | Error object with `AUTH_TOKEN_INVALID` |

**Retry Guidance:**
- Client retry: No (must re-authenticate)
- Backoff: Not applicable

**Example Structured Log:**
```json
{
  "event_id": "ERR_002",
  "event_name": "audit.auth.token.invalid",
  "level": "ERROR",
  "timestamp": "2026-01-26T08:25:00.000Z",
  "correlation_id": "corr_b2c3d4e5-f6a7-8901-bcde-f23456789012",
  "request_id": "req_g2h3i4j5",
  "action": "TOKEN_INVALID",
  "entity_type": "Auth",
  "entity_id": null,
  "user_id": null,
  "ip_address": "10.0.0.50",
  "endpoint": "/api/enrollments",
  "http_method": "GET",
  "http_status": 401,
  "status": "failure",
  "error_code": "AUTH_TOKEN_INVALID",
  "sensitivity_level": 2,
  "retryable": false,
  "details": {
    "token_error": "expired",
    "token_sub": 42
  }
}
```

**Observability:**
- **Alert:** Signature mismatch count > 5/hour → P1 security alert (possible key compromise)
- **Dashboard:** "Token Errors" chart split by `expired` vs `invalid`

---

### ERR_003 — Access Denied (Forbidden)

| Field                | Value                                                                 |
|----------------------|-----------------------------------------------------------------------|
| **Event ID**         | `ERR_003`                                                             |
| **Event Name**       | `audit.auth.access.denied`                                            |
| **Error Code**       | `FORBIDDEN`                                                           |
| **Log Level**        | ERROR                                                                 |
| **Severity**         | High                                                                  |
| **Category**         | Authorization                                                         |
| **Sensitivity**      | 3 (High)                                                              |

**When to Trigger:**
An authenticated user attempts to access a resource or perform an action that their role does not permit. Examples: a `parent` accessing `/api/admin/users`, a `supervisor` attempting to delete a kindergarten.

**Meaning:**
A valid, authenticated user tried to perform an action beyond their authorization level. This may be a UI bug exposing links they shouldn't see, or a deliberate privilege escalation attempt.

**Likely Root Causes:**
1. User manually crafted a URL to an admin endpoint
2. Frontend displayed a link/button the user's role should not see
3. Role was changed (downgraded) after the page loaded
4. API client or script probing for privilege escalation
5. Misconfigured role-based access control (RBAC) rule

**User Impact:**
Action is blocked. User sees a "Permission denied" message.

**System Impact:**
No data change occurs. Repeated occurrences may indicate an active attack.

**Detection Signals:**
- Any `ACCESS_DENIED` log entry from a non-admin role targeting admin endpoints
- Same user generating multiple `ACCESS_DENIED` events in a short window
- Access denied events from IPs not associated with the user's login history

**Recommended Response:**

| Phase        | Action                                                                   |
|--------------|-------------------------------------------------------------------------|
| Immediate    | Return 403; log full context including user role and target resource      |
| Engineering  | Audit frontend to ensure role-gated UI elements are hidden properly      |
| Prevention   | Add RBAC integration tests; alert on any ACCESS_DENIED occurrence        |

**Logging Fields:**

| Field            | Required | Redaction |
|------------------|----------|-----------|
| `correlation_id` | YES      | —         |
| `user_id`        | YES      | —         |
| `role`           | YES      | —         |
| `ip_address`     | YES      | —         |
| `endpoint`       | YES      | —         |
| `http_method`    | YES      | —         |
| `required_role`  | YES      | —         |

**User-Facing Message:**
- **Text:** "You do not have permission to perform this action."
- **Message Key:** `error.auth.access_denied`
- **UI Action:** Display inline error; optionally redirect to dashboard

**HTTP Mapping:**

| Field         | Value                    |
|---------------|--------------------------|
| Status Code   | `403 Forbidden`          |
| Response Body | Error object with `FORBIDDEN` |

**Retry Guidance:**
- Client retry: No (same credentials will produce the same result)
- Backoff: Not applicable

**Example Structured Log:**
```json
{
  "event_id": "ERR_003",
  "event_name": "audit.auth.access.denied",
  "level": "ERROR",
  "timestamp": "2026-01-26T09:00:00.000Z",
  "correlation_id": "corr_c3d4e5f6-a7b8-9012-cdef-345678901234",
  "request_id": "req_h3i4j5k6",
  "action": "ACCESS_DENIED",
  "entity_type": "User",
  "entity_id": null,
  "user_id": 15,
  "role": "parent",
  "ip_address": "172.16.0.22",
  "endpoint": "/api/admin/users",
  "http_method": "GET",
  "http_status": 403,
  "status": "failure",
  "error_code": "FORBIDDEN",
  "sensitivity_level": 3,
  "retryable": false,
  "details": {
    "required_role": "admin",
    "actual_role": "parent"
  }
}
```

**Observability:**
- **Alert:** Any `ACCESS_DENIED` event → P2 security alert (immediate review)
- **Dashboard:** "Access Denied Events" table with user, role, endpoint, timestamp

---

### ERR_004 — IDOR Attempt Detected

| Field                | Value                                                                 |
|----------------------|-----------------------------------------------------------------------|
| **Event ID**         | `ERR_004`                                                             |
| **Event Name**       | `audit.auth.idor.detected`                                            |
| **Error Code**       | `FORBIDDEN`                                                           |
| **Log Level**        | ERROR                                                                 |
| **Severity**         | Critical                                                              |
| **Category**         | Authorization                                                         |
| **Sensitivity**      | 3 (High)                                                              |

**When to Trigger:**
An authenticated user attempts to access or modify a resource (user, child, enrollment, etc.) that belongs to a different tenant or user scope, and the ownership check fails. For example, a parent trying to view another parent's child record by manipulating the `entity_id` in the URL.

**Meaning:**
An Insecure Direct Object Reference (IDOR) was attempted. The user's request referenced a resource they do not own. This is a high-severity security event.

**Likely Root Causes:**
1. Deliberate IDOR attack — user manipulated URL/API parameters
2. Broken link or stale bookmark pointing to a resource that was reassigned
3. Frontend bug passing incorrect entity IDs
4. Automated scanner probing sequential IDs

**User Impact:**
Action is blocked. User receives a generic "not found" or "forbidden" response (do not confirm the resource exists).

**System Impact:**
No data exposure. However, this is a strong signal of active exploitation.

**Detection Signals:**
- `ACCESS_DENIED` with `reason: "idor_check_failed"` in details
- Sequential entity_id probing from a single user (e.g., IDs 1, 2, 3, 4…)
- Cross-tenant access attempts

**Recommended Response:**

| Phase        | Action                                                                      |
|--------------|----------------------------------------------------------------------------|
| Immediate    | Return 403; log with `sensitivity_level: 3`; alert security team            |
| Engineering  | Ensure all entity access includes ownership/scope checks                    |
| Prevention   | Add IDOR-specific integration tests; use UUIDs instead of sequential IDs    |

**Logging Fields:**

| Field              | Required | Redaction |
|--------------------|----------|-----------|
| `correlation_id`   | YES      | —         |
| `user_id`          | YES      | —         |
| `role`             | YES      | —         |
| `ip_address`       | YES      | —         |
| `endpoint`         | YES      | —         |
| `target_entity_id` | YES      | —         |
| `target_owner_id`  | YES      | —         |

**User-Facing Message:**
- **Text:** "The requested resource was not found."
- **Message Key:** `error.resource.not_found`
- **UI Action:** Redirect to dashboard (do not confirm resource existence)

**HTTP Mapping:**

| Field         | Value                       |
|---------------|-----------------------------|
| Status Code   | `403 Forbidden`             |
| Response Body | Error object with `FORBIDDEN` |

**Retry Guidance:**
- Client retry: No
- Backoff: Not applicable

**Example Structured Log:**
```json
{
  "event_id": "ERR_004",
  "event_name": "audit.auth.idor.detected",
  "level": "ERROR",
  "timestamp": "2026-01-26T09:15:00.000Z",
  "correlation_id": "corr_d4e5f6a7-b8c9-0123-defa-456789012345",
  "request_id": "req_i4j5k6l7",
  "action": "ACCESS_DENIED",
  "entity_type": "User",
  "entity_id": 99,
  "user_id": 15,
  "role": "parent",
  "ip_address": "172.16.0.22",
  "endpoint": "/api/admin/users/99",
  "http_method": "GET",
  "http_status": 403,
  "status": "failure",
  "error_code": "FORBIDDEN",
  "sensitivity_level": 3,
  "retryable": false,
  "details": {
    "reason": "idor_check_failed",
    "target_owner_id": 42
  }
}
```

**Observability:**
- **Alert:** Any IDOR detection → P1 security alert (immediate investigation)
- **Dashboard:** "IDOR Attempts" counter with user breakdown

---

### ERR_005 — Bulk Access Denied

| Field                | Value                                                                 |
|----------------------|-----------------------------------------------------------------------|
| **Event ID**         | `ERR_005`                                                             |
| **Event Name**       | `audit.admin.bulk.access_denied`                                      |
| **Error Code**       | `FORBIDDEN`                                                           |
| **Log Level**        | ERROR                                                                 |
| **Severity**         | High                                                                  |
| **Category**         | Authorization                                                         |
| **Sensitivity**      | 3 (High)                                                              |

**When to Trigger:**
A bulk operation (bulk status update, bulk delete, bulk create) targets entity IDs that include records outside the actor's authorized scope. The admin_endpoints.py ownership pre-check rejects the entire batch.

**Meaning:**
An admin attempted a bulk operation that included resources they do not have authority over (e.g., users from another kindergarten in a multi-tenant setup, or system admin accounts).

**Likely Root Causes:**
1. Admin selected records across tenant boundaries
2. Frontend bug included stale or incorrect IDs in the batch
3. Deliberate privilege escalation via API manipulation
4. Race condition: records reassigned between selection and submission

**User Impact:**
Entire bulk operation is rejected. No partial execution.

**System Impact:**
No data changes. Protects against unauthorized mass modifications.

**Detection Signals:**
- `BULK_ACCESS_DENIED` action in audit logs
- Bulk requests containing IDs from multiple tenants

**Recommended Response:**

| Phase        | Action                                                                      |
|--------------|----------------------------------------------------------------------------|
| Immediate    | Reject entire batch with 403; log all attempted target IDs                  |
| Engineering  | Validate all IDs in a single query before executing any operation            |
| Prevention   | Add frontend scope-filtering to only show selectable records                |

**Logging Fields:**

| Field              | Required | Redaction |
|--------------------|----------|-----------|
| `correlation_id`   | YES      | —         |
| `user_id`          | YES      | —         |
| `role`             | YES      | —         |
| `ip_address`       | YES      | —         |
| `endpoint`         | YES      | —         |
| `target_ids`       | YES      | —         |
| `forbidden_ids`    | YES      | —         |
| `operation`        | YES      | —         |

**User-Facing Message:**
- **Text:** "You do not have permission to modify some of the selected records. No changes were made."
- **Message Key:** `error.bulk.access_denied`
- **UI Action:** Highlight forbidden records in the selection list

**HTTP Mapping:**

| Field         | Value                    |
|---------------|--------------------------|
| Status Code   | `403 Forbidden`          |
| Response Body | Error object with `FORBIDDEN` and list of `forbidden_ids` |

**Retry Guidance:**
- Client retry: Yes, after removing forbidden IDs from the batch
- Backoff: Not applicable

**Example Structured Log:**
```json
{
  "event_id": "ERR_005",
  "event_name": "audit.admin.bulk.access_denied",
  "level": "ERROR",
  "timestamp": "2026-01-26T09:30:00.000Z",
  "correlation_id": "corr_e5f6a7b8-c9d0-1234-efab-567890123456",
  "request_id": "req_j5k6l7m8",
  "action": "BULK_ACCESS_DENIED",
  "entity_type": "User",
  "entity_id": null,
  "user_id": 3,
  "role": "admin",
  "ip_address": "10.0.0.5",
  "endpoint": "/api/admin/users/bulk-delete",
  "http_method": "POST",
  "http_status": 403,
  "status": "failure",
  "error_code": "FORBIDDEN",
  "sensitivity_level": 3,
  "retryable": true,
  "details": {
    "operation": "BULK_USER_DELETE",
    "requested_ids": [10, 11, 12, 1],
    "forbidden_ids": [1]
  }
}
```

**Observability:**
- **Alert:** Any `BULK_ACCESS_DENIED` → P2 security alert
- **Dashboard:** "Bulk Operation Denials" counter

---

### ERR_006 — Admin Password Reset Failed

| Field                | Value                                                                 |
|----------------------|-----------------------------------------------------------------------|
| **Event ID**         | `ERR_006`                                                             |
| **Event Name**       | `audit.auth.password_reset.failure`                                   |
| **Error Code**       | `AUTH_PASSWORD_RESET_FAILED`                                          |
| **Log Level**        | ERROR                                                                 |
| **Severity**         | High                                                                  |
| **Category**         | Authentication                                                        |
| **Sensitivity**      | 3 (High)                                                              |

**When to Trigger:**
An admin attempts to reset another user's password via `/api/admin/users/{id}/reset-password`, but the operation fails due to: target user not found, target user is a higher-privilege account, validation failure on the new password, or a database error during the update.

**Meaning:**
A privileged password reset operation was attempted and failed. This is security-sensitive because admin password resets bypass the normal email-based flow.

**Likely Root Causes:**
1. Target user ID does not exist (deleted between page load and submission)
2. Admin attempted to reset another admin's or system account's password (forbidden)
3. New password does not meet complexity requirements
4. Database write failure (connection issue, constraint violation)
5. Rate limit exceeded for password reset operations

**User Impact:**
The target user's password remains unchanged. The admin sees an error message.

**System Impact:**
No credential change. Failed attempt is recorded for security review.

**Detection Signals:**
- `ADMIN_PASSWORD_RESET_FAILED` in audit logs
- Multiple reset attempts for the same target user
- Reset attempts targeting admin accounts

**Recommended Response:**

| Phase        | Action                                                                        |
|--------------|------------------------------------------------------------------------------|
| Immediate    | Return appropriate error; log with `sensitivity_level: 3`                     |
| Engineering  | Ensure clear error messages distinguish validation vs authorization failures  |
| Prevention   | Rate-limit password resets to 3/minute; require re-authentication for admin resets |

**Logging Fields:**

| Field             | Required | Redaction                    |
|-------------------|----------|------------------------------|
| `correlation_id`  | YES      | —                            |
| `user_id`         | YES      | —                            |
| `target_user_id`  | YES      | —                            |
| `ip_address`      | YES      | —                            |
| `endpoint`        | YES      | —                            |
| `failure_reason`  | YES      | —                            |
| `new_password`    | NEVER    | Never log — `[REDACTED]`    |

**User-Facing Message:**
- **Text:** "Unable to reset the password. Please verify the account and try again."
- **Message Key:** `error.auth.password_reset_failed`
- **UI Action:** Display error inline on the reset form

**HTTP Mapping:**

| Field         | Value                                     |
|---------------|-------------------------------------------|
| Status Code   | `400`, `403`, or `404` depending on cause |
| Response Body | Error object with `AUTH_PASSWORD_RESET_FAILED` |

**Retry Guidance:**
- Client retry: Yes, after correcting the issue
- Backoff: Rate-limited to 3/minute

**Example Structured Log:**
```json
{
  "event_id": "ERR_006",
  "event_name": "audit.auth.password_reset.failure",
  "level": "ERROR",
  "timestamp": "2026-01-26T10:00:00.000Z",
  "correlation_id": "corr_f6a7b8c9-d0e1-2345-fabc-678901234567",
  "request_id": "req_k6l7m8n9",
  "action": "ADMIN_PASSWORD_RESET_FAILED",
  "entity_type": "Auth",
  "entity_id": 25,
  "user_id": 3,
  "role": "admin",
  "ip_address": "10.0.0.5",
  "endpoint": "/api/admin/users/25/reset-password",
  "http_method": "POST",
  "http_status": 403,
  "status": "failure",
  "error_code": "AUTH_PASSWORD_RESET_FAILED",
  "sensitivity_level": 3,
  "retryable": false,
  "details": {
    "target_user_id": 25,
    "failure_reason": "target_is_admin"
  }
}
```

**Observability:**
- **Alert:** `ADMIN_PASSWORD_RESET_FAILED` count > 3/hour → P1 security alert
- **Dashboard:** "Password Reset Failures" with actor and target breakdown

---

### ERR_007 — Validation Error

| Field                | Value                                                                 |
|----------------------|-----------------------------------------------------------------------|
| **Event ID**         | `ERR_007`                                                             |
| **Event Name**       | `audit.request.validation.failure`                                    |
| **Error Code**       | `VALIDATION_ERROR`                                                    |
| **Log Level**        | ERROR                                                                 |
| **Severity**         | Low                                                                   |
| **Category**         | Input Validation                                                      |
| **Sensitivity**      | 1 (Low)                                                               |

**When to Trigger:**
Any API endpoint receives input that fails Pydantic model validation, custom validator checks, or business rule validation (e.g., child age outside allowed range, invalid phone format, duplicate email).

**Meaning:**
The client submitted data that does not meet the expected schema or business rules. This is a normal operational event for user-input errors, but high volumes may indicate a misconfigured client or fuzzing attack.

**Likely Root Causes:**
1. User submitted a form with invalid data (missing required fields, wrong format)
2. Frontend validation was bypassed or out of sync with backend rules
3. API client sent malformed JSON
4. Automated fuzzing or injection attack probing
5. Business rule change not reflected in frontend validation
6. Encoding issue (e.g., Arabic text in a field expecting Latin characters)

**User Impact:**
Form submission is rejected. User sees field-specific error messages.

**System Impact:**
No data change. High volumes may indicate attack probing.

**Detection Signals:**
- Spike in 400 responses on a specific endpoint
- Repeated validation failures from the same IP with unusual field values (injection patterns)

**Recommended Response:**

| Phase        | Action                                                            |
|--------------|------------------------------------------------------------------|
| Immediate    | Return 400 with per-field error details                           |
| Engineering  | Keep frontend and backend validation rules in sync                |
| Prevention   | Add input sanitization; monitor for injection patterns in values  |

**Logging Fields:**

| Field            | Required | Redaction                              |
|------------------|----------|----------------------------------------|
| `correlation_id` | YES      | —                                      |
| `user_id`        | NO       | —                                      |
| `ip_address`     | YES      | —                                      |
| `endpoint`       | YES      | —                                      |
| `failed_fields`  | YES      | Redact values for sensitive fields     |

**User-Facing Message:**
- **Text:** "Please correct the highlighted fields and try again."
- **Message Key:** `error.validation.failed`
- **UI Action:** Highlight invalid fields with per-field error messages

**HTTP Mapping:**

| Field         | Value                                             |
|---------------|---------------------------------------------------|
| Status Code   | `400 Bad Request`                                 |
| Response Body | Error object with `VALIDATION_ERROR` and `fields` map |

**Retry Guidance:**
- Client retry: Yes, after correcting invalid fields
- Backoff: Not applicable

**Example Structured Log:**
```json
{
  "event_id": "ERR_007",
  "event_name": "audit.request.validation.failure",
  "level": "ERROR",
  "timestamp": "2026-01-26T10:15:00.000Z",
  "correlation_id": "corr_a7b8c9d0-e1f2-3456-abcd-789012345678",
  "request_id": "req_l7m8n9o0",
  "action": "VALIDATION_ERROR",
  "entity_type": "User",
  "entity_id": null,
  "user_id": 3,
  "ip_address": "10.0.0.5",
  "endpoint": "/api/admin/users",
  "http_method": "POST",
  "http_status": 400,
  "status": "failure",
  "error_code": "VALIDATION_ERROR",
  "sensitivity_level": 1,
  "retryable": true,
  "details": {
    "failed_fields": {
      "email": "Invalid email format",
      "phone": "Must match Jordan phone pattern"
    }
  }
}
```

**Observability:**
- **Alert:** Validation errors > 100/hour on a single endpoint → P3 investigate
- **Dashboard:** "Validation Errors" grouped by endpoint and field name

---

### ERR_008 — Resource Not Found

| Field                | Value                                                                 |
|----------------------|-----------------------------------------------------------------------|
| **Event ID**         | `ERR_008`                                                             |
| **Event Name**       | `audit.resource.not_found`                                            |
| **Error Code**       | `NOT_FOUND`                                                           |
| **Log Level**        | ERROR                                                                 |
| **Severity**         | Low                                                                   |
| **Category**         | Data Access                                                           |
| **Sensitivity**      | 1 (Low)                                                               |

**When to Trigger:**
An API endpoint receives a request referencing an entity ID that does not exist in the database (e.g., `GET /api/users/999` where user 999 does not exist).

**Meaning:**
The requested resource could not be found. This is normal for stale links or deleted records, but may indicate enumeration probing if patterns are detected.

**Likely Root Causes:**
1. Resource was deleted between page load and API call
2. User bookmarked a URL for a resource that no longer exists
3. Frontend passed an incorrect ID (bug)
4. ID enumeration attack (sequential probing)
5. Typo in manually constructed URL

**User Impact:**
User sees "Resource not found" message.

**System Impact:**
No data change. Informational only.

**Recommended Response:**

| Phase        | Action                                                     |
|--------------|------------------------------------------------------------|
| Immediate    | Return 404                                                  |
| Engineering  | Ensure 404 responses are generic (do not leak entity types) |
| Prevention   | Monitor for sequential ID probing patterns                  |

**Logging Fields:**

| Field            | Required | Redaction |
|------------------|----------|-----------|
| `correlation_id` | YES      | —         |
| `user_id`        | NO       | —         |
| `ip_address`     | YES      | —         |
| `endpoint`       | YES      | —         |
| `entity_type`    | YES      | —         |
| `entity_id`      | YES      | —         |

**User-Facing Message:**
- **Text:** "The requested item could not be found. It may have been removed."
- **Message Key:** `error.resource.not_found`
- **UI Action:** Show message with "Go back" button

**HTTP Mapping:**

| Field         | Value                     |
|---------------|---------------------------|
| Status Code   | `404 Not Found`           |
| Response Body | Error object with `NOT_FOUND` |

**Retry Guidance:**
- Client retry: No (resource does not exist)
- Backoff: Not applicable

**Example Structured Log:**
```json
{
  "event_id": "ERR_008",
  "event_name": "audit.resource.not_found",
  "level": "ERROR",
  "timestamp": "2026-01-26T10:30:00.000Z",
  "correlation_id": "corr_b8c9d0e1-f2a3-4567-bcde-890123456789",
  "request_id": "req_m8n9o0p1",
  "action": "NOT_FOUND",
  "entity_type": "User",
  "entity_id": 999,
  "user_id": 3,
  "ip_address": "10.0.0.5",
  "endpoint": "/api/users/999",
  "http_method": "GET",
  "http_status": 404,
  "status": "failure",
  "error_code": "NOT_FOUND",
  "sensitivity_level": 1,
  "retryable": false
}
```

**Observability:**
- **Alert:** 404 count > 50/min from single IP → P3 investigate (possible enumeration)
- **Dashboard:** "Not Found Errors" by endpoint

---

### ERR_009 — Resource Conflict

| Field                | Value                                                                 |
|----------------------|-----------------------------------------------------------------------|
| **Event ID**         | `ERR_009`                                                             |
| **Event Name**       | `audit.resource.conflict`                                             |
| **Error Code**       | `CONFLICT`                                                            |
| **Log Level**        | ERROR                                                                 |
| **Severity**         | Medium                                                                |
| **Category**         | Data Integrity                                                        |
| **Sensitivity**      | 1 (Low)                                                               |

**When to Trigger:**
A create or update operation violates a uniqueness constraint. Examples: duplicate email on user creation, duplicate enrollment application for the same child+kindergarten, duplicate daily report for the same child+date.

**Meaning:**
The operation would create a duplicate record that violates a business or database uniqueness rule.

**Likely Root Causes:**
1. User submitted a form twice (double-click)
2. Concurrent requests from different sessions creating the same resource
3. Data migration left duplicate records
4. Frontend did not disable the submit button after first click

**User Impact:**
Operation is rejected. User sees a message explaining the conflict.

**System Impact:**
No data corruption. Database constraint enforced correctly.

**Recommended Response:**

| Phase        | Action                                                           |
|--------------|------------------------------------------------------------------|
| Immediate    | Return 409 with details about which field caused the conflict     |
| Engineering  | Add optimistic locking or idempotency keys for critical operations |
| Prevention   | Disable submit buttons after click; add frontend dedup logic      |

**Logging Fields:**

| Field              | Required | Redaction                |
|--------------------|----------|--------------------------|
| `correlation_id`   | YES      | —                        |
| `user_id`          | YES      | —                        |
| `endpoint`         | YES      | —                        |
| `conflict_field`   | YES      | Mask value if PII field  |
| `entity_type`      | YES      | —                        |

**User-Facing Message:**
- **Text:** "A record with these details already exists. Please check and try again."
- **Message Key:** `error.resource.conflict`
- **UI Action:** Highlight the conflicting field

**HTTP Mapping:**

| Field         | Value                      |
|---------------|----------------------------|
| Status Code   | `409 Conflict`             |
| Response Body | Error object with `CONFLICT` and `fields` |

**Retry Guidance:**
- Client retry: Yes, after changing the conflicting value
- Backoff: Not applicable

**Example Structured Log:**
```json
{
  "event_id": "ERR_009",
  "event_name": "audit.resource.conflict",
  "level": "ERROR",
  "timestamp": "2026-01-26T10:45:00.000Z",
  "correlation_id": "corr_c9d0e1f2-a3b4-5678-cdef-901234567890",
  "request_id": "req_n9o0p1q2",
  "action": "CONFLICT",
  "entity_type": "User",
  "entity_id": null,
  "user_id": 3,
  "ip_address": "10.0.0.5",
  "endpoint": "/api/admin/users",
  "http_method": "POST",
  "http_status": 409,
  "status": "failure",
  "error_code": "CONFLICT",
  "sensitivity_level": 1,
  "retryable": true,
  "details": {
    "conflict_field": "email",
    "conflict_value": "w***@domain.com"
  }
}
```

**Observability:**
- **Alert:** Conflict rate > 20/hour on a single endpoint → P3 investigate
- **Dashboard:** "Conflict Errors" by entity type

---

### ERR_010 — Rate Limit Exceeded

| Field                | Value                                                                 |
|----------------------|-----------------------------------------------------------------------|
| **Event ID**         | `ERR_010`                                                             |
| **Event Name**       | `audit.request.rate_limited`                                          |
| **Error Code**       | `RATE_LIMITED`                                                        |
| **Log Level**        | ERROR                                                                 |
| **Severity**         | Medium                                                                |
| **Category**         | Traffic Control                                                       |
| **Sensitivity**      | 1 (Low)                                                               |

**When to Trigger:**
The SlowAPI rate limiter middleware rejects a request because the client has exceeded the configured request rate for the endpoint (e.g., `30/minute` for message sending, `5/minute` for bulk operations).

**Meaning:**
The client is sending requests faster than the allowed rate. This protects the system from abuse but may also affect legitimate power users.

**Likely Root Causes:**
1. Automated script or bot hammering an endpoint
2. Frontend retry loop gone wrong (e.g., infinite retry on failure)
3. Legitimate high-usage admin performing bulk work
4. DDoS or scraping attempt
5. Rate limit configuration too aggressive for the use case

**User Impact:**
Request is rejected. User must wait before retrying.

**System Impact:**
System is protected. Other users are unaffected.

**Recommended Response:**

| Phase        | Action                                                              |
|--------------|---------------------------------------------------------------------|
| Immediate    | Return 429 with `Retry-After` header                                |
| Engineering  | Tune rate limits per role; add burst allowance                      |
| Prevention   | Add frontend rate awareness; show cooldown timer to user            |

**Logging Fields:**

| Field            | Required | Redaction |
|------------------|----------|-----------|
| `correlation_id` | YES      | —         |
| `user_id`        | NO       | —         |
| `ip_address`     | YES      | —         |
| `endpoint`       | YES      | —         |
| `rate_limit`     | YES      | —         |
| `retry_after`    | YES      | —         |

**User-Facing Message:**
- **Text:** "You are making requests too quickly. Please wait a moment and try again."
- **Message Key:** `error.request.rate_limited`
- **UI Action:** Show countdown timer; disable submit button until `Retry-After` expires

**HTTP Mapping:**

| Field         | Value                                |
|---------------|--------------------------------------|
| Status Code   | `429 Too Many Requests`              |
| Response Body | Error object with `RATE_LIMITED`     |
| Headers       | `Retry-After: <seconds>`            |

**Retry Guidance:**
- Client retry: Yes
- Backoff: Wait for `Retry-After` seconds, then retry once

**Example Structured Log:**
```json
{
  "event_id": "ERR_010",
  "event_name": "audit.request.rate_limited",
  "level": "ERROR",
  "timestamp": "2026-01-26T11:00:00.000Z",
  "correlation_id": "corr_d0e1f2a3-b4c5-6789-defa-012345678901",
  "request_id": "req_o0p1q2r3",
  "action": "RATE_LIMITED",
  "entity_type": "Request",
  "entity_id": null,
  "user_id": 3,
  "ip_address": "10.0.0.5",
  "endpoint": "/api/messages",
  "http_method": "POST",
  "http_status": 429,
  "status": "failure",
  "error_code": "RATE_LIMITED",
  "sensitivity_level": 1,
  "retryable": true,
  "details": {
    "rate_limit": "30/minute",
    "retry_after": 45
  }
}
```

**Observability:**
- **Alert:** Rate limit hits > 100/hour per IP → P3 (possible bot)
- **Dashboard:** "Rate Limited Requests" by endpoint and IP

---

### ERR_011 — Internal Server Error

| Field                | Value                                                                 |
|----------------------|-----------------------------------------------------------------------|
| **Event ID**         | `ERR_011`                                                             |
| **Event Name**       | `audit.system.internal_error`                                         |
| **Error Code**       | `INTERNAL_ERROR`                                                      |
| **Log Level**        | ERROR                                                                 |
| **Severity**         | Critical                                                              |
| **Category**         | System                                                                |
| **Sensitivity**      | 2 (Medium)                                                            |

**When to Trigger:**
An unhandled exception occurs in any endpoint handler, middleware, or background task, resulting in a 500 response. The global exception handler catches this.

**Meaning:**
An unexpected error occurred that the application did not handle gracefully. This indicates a bug, infrastructure issue, or data inconsistency.

**Likely Root Causes:**
1. Unhandled Python exception (NoneType, KeyError, AttributeError)
2. Database schema mismatch (missing column, as seen with `profile_complete`)
3. External service unavailable (Redis, Celery)
4. Memory or resource exhaustion
5. Race condition or deadlock
6. Corrupted data triggering unexpected code paths

**User Impact:**
User sees a generic error page. The operation failed and may need to be retried.

**System Impact:**
Potential data inconsistency if the error occurred mid-transaction. Service degradation if repeated.

**Detection Signals:**
- HTTP 500 response codes in access logs
- Unhandled exception stack traces in application logs
- Error rate increase on health check dashboards

**Recommended Response:**

| Phase        | Action                                                                  |
|--------------|------------------------------------------------------------------------|
| Immediate    | Return 500 with generic message; log full stack trace server-side       |
| Engineering  | Investigate stack trace; add specific error handling for the root cause  |
| Prevention   | Add integration tests; improve error handling coverage; add circuit breakers |

**Logging Fields:**

| Field              | Required | Redaction                                |
|--------------------|----------|------------------------------------------|
| `correlation_id`   | YES      | —                                        |
| `user_id`          | NO       | —                                        |
| `ip_address`       | YES      | —                                        |
| `endpoint`         | YES      | —                                        |
| `exception_type`   | YES      | —                                        |
| `exception_message`| YES      | Redact if contains PII or SQL with data  |
| `stack_trace`      | YES*     | *Server-side only, never in API response |

**User-Facing Message:**
- **Text:** "Something went wrong. Please try again later. If the problem continues, contact support."
- **Message Key:** `error.system.internal`
- **UI Action:** Show error page with "Try Again" and "Contact Support" buttons

**HTTP Mapping:**

| Field         | Value                           |
|---------------|---------------------------------|
| Status Code   | `500 Internal Server Error`     |
| Response Body | Error object with `INTERNAL_ERROR` (no stack trace) |

**Retry Guidance:**
- Client retry: Yes
- Backoff: Exponential — 1s, 2s, 4s, max 3 retries

**Example Structured Log:**
```json
{
  "event_id": "ERR_011",
  "event_name": "audit.system.internal_error",
  "level": "ERROR",
  "timestamp": "2026-01-26T11:15:00.000Z",
  "correlation_id": "corr_e1f2a3b4-c5d6-7890-efab-123456789012",
  "request_id": "req_p1q2r3s4",
  "action": "INTERNAL_ERROR",
  "entity_type": "System",
  "entity_id": null,
  "user_id": 3,
  "ip_address": "10.0.0.5",
  "endpoint": "/api/enrollments",
  "http_method": "GET",
  "http_status": 500,
  "status": "failure",
  "error_code": "INTERNAL_ERROR",
  "sensitivity_level": 2,
  "retryable": true,
  "details": {
    "exception_type": "OperationalError",
    "exception_message": "no such column: parent_profiles.profile_complete",
    "stack_trace_ref": "trace_abc123"
  }
}
```

**Observability:**
- **Alert:** Any 500 error → P2 alert; > 10/min → P1 (service degradation)
- **Dashboard:** "Internal Errors" time-series with endpoint breakdown

---

### ERR_012 — Database Connection Error

| Field                | Value                                                                 |
|----------------------|-----------------------------------------------------------------------|
| **Event ID**         | `ERR_012`                                                             |
| **Event Name**       | `audit.system.database.connection_failed`                             |
| **Error Code**       | `DB_CONNECTION_FAILED`                                                |
| **Log Level**        | ERROR                                                                 |
| **Severity**         | Critical                                                              |
| **Category**         | Infrastructure                                                        |
| **Sensitivity**      | 2 (Medium)                                                            |

**When to Trigger:**
SQLAlchemy's `get_db()` dependency or any database operation raises a connection error (`OperationalError` with connection-related messages), connection pool exhaustion, or timeout acquiring a connection.

**Meaning:**
The application cannot communicate with the database. All read/write operations are blocked.

**Likely Root Causes:**
1. Database server is down or unreachable
2. Connection pool exhausted (too many concurrent requests)
3. Network issue between app and database
4. Database credentials changed or expired
5. DNS resolution failure for database host
6. Database disk full or in recovery mode

**User Impact:**
All operations fail. Users see generic error pages on every action.

**System Impact:**
Complete service outage. No reads or writes possible.

**Recommended Response:**

| Phase        | Action                                                                |
|--------------|----------------------------------------------------------------------|
| Immediate    | Page on-call; check database health; verify network connectivity      |
| Engineering  | Add connection retry with backoff; implement health check endpoint    |
| Prevention   | Monitor connection pool usage; set up database failover; add alerts on pool saturation |

**Logging Fields:**

| Field              | Required | Redaction                         |
|--------------------|----------|-----------------------------------|
| `correlation_id`   | YES      | —                                 |
| `endpoint`         | YES      | —                                 |
| `db_host`          | YES      | Hostname only, no credentials     |
| `error_type`       | YES      | —                                 |
| `pool_size`        | NO       | —                                 |
| `pool_checked_out` | NO       | —                                 |

**Never log the `DATABASE_URL` — it contains credentials.**

**User-Facing Message:**
- **Text:** "We are experiencing a temporary issue. Please try again in a few moments."
- **Message Key:** `error.system.unavailable`
- **UI Action:** Show maintenance-style error page with auto-refresh

**HTTP Mapping:**

| Field         | Value                             |
|---------------|-----------------------------------|
| Status Code   | `503 Service Unavailable`         |
| Response Body | Error object with `DB_CONNECTION_FAILED` |
| Headers       | `Retry-After: 30`                |

**Retry Guidance:**
- Client retry: Yes
- Backoff: Exponential — 5s, 10s, 20s, max 5 retries

**Example Structured Log:**
```json
{
  "event_id": "ERR_012",
  "event_name": "audit.system.database.connection_failed",
  "level": "ERROR",
  "timestamp": "2026-01-26T11:30:00.000Z",
  "correlation_id": "corr_f2a3b4c5-d6e7-8901-fabc-234567890123",
  "request_id": "req_q2r3s4t5",
  "action": "DB_CONNECTION_FAILED",
  "entity_type": "System",
  "entity_id": null,
  "user_id": null,
  "ip_address": "10.0.0.5",
  "endpoint": "/api/enrollments",
  "http_method": "GET",
  "http_status": 503,
  "status": "failure",
  "error_code": "DB_CONNECTION_FAILED",
  "sensitivity_level": 2,
  "retryable": true,
  "details": {
    "db_host": "localhost:5432",
    "error_type": "OperationalError",
    "pool_size": 10,
    "pool_checked_out": 10
  }
}
```

**Observability:**
- **Alert:** Any DB connection error → P1 page on-call immediately
- **Dashboard:** "Database Connectivity" status panel; connection pool usage gauge

---

### ERR_013 — Database Query Timeout

| Field                | Value                                                                 |
|----------------------|-----------------------------------------------------------------------|
| **Event ID**         | `ERR_013`                                                             |
| **Event Name**       | `audit.system.database.query_timeout`                                 |
| **Error Code**       | `DB_QUERY_TIMEOUT`                                                    |
| **Log Level**        | ERROR                                                                 |
| **Severity**         | High                                                                  |
| **Category**         | Infrastructure                                                        |
| **Sensitivity**      | 1 (Low)                                                               |

**When to Trigger:**
A database query exceeds the configured statement timeout (or takes longer than 30 seconds by default) and is cancelled by the database or application layer.

**Meaning:**
A specific query is too slow, likely due to missing indexes, large table scans, or lock contention.

**Likely Root Causes:**
1. Missing database index on a filtered or joined column
2. Query returning too many rows (unbounded query)
3. Table lock contention from concurrent bulk operations
4. Database under heavy load (other queries competing)
5. Complex query plan with multiple joins (e.g., enrollment queries)
6. Database statistics stale (query planner using suboptimal plan)

**User Impact:**
The specific operation times out. User sees a loading spinner followed by an error.

**System Impact:**
Connection held during timeout; may exhaust pool if many queries timeout simultaneously.

**Recommended Response:**

| Phase        | Action                                                           |
|--------------|------------------------------------------------------------------|
| Immediate    | Return 504; investigate the slow query via `EXPLAIN ANALYZE`      |
| Engineering  | Add missing indexes; add pagination; optimize query               |
| Prevention   | Add query monitoring; set statement_timeout; add query cost alerts |

**Logging Fields:**

| Field              | Required | Redaction                      |
|--------------------|----------|--------------------------------|
| `correlation_id`   | YES      | —                              |
| `endpoint`         | YES      | —                              |
| `query_summary`    | YES      | Table/action only, no values   |
| `duration_ms`      | YES      | —                              |
| `entity_type`      | YES      | —                              |

**User-Facing Message:**
- **Text:** "The request is taking too long. Please try again."
- **Message Key:** `error.system.timeout`
- **UI Action:** Show timeout message with "Retry" button

**HTTP Mapping:**

| Field         | Value                      |
|---------------|----------------------------|
| Status Code   | `504 Gateway Timeout`      |
| Response Body | Error object with `DB_QUERY_TIMEOUT` |

**Retry Guidance:**
- Client retry: Yes
- Backoff: Fixed 5-second delay, max 2 retries

**Example Structured Log:**
```json
{
  "event_id": "ERR_013",
  "event_name": "audit.system.database.query_timeout",
  "level": "ERROR",
  "timestamp": "2026-01-26T11:45:00.000Z",
  "correlation_id": "corr_a3b4c5d6-e7f8-9012-abcd-345678901234",
  "request_id": "req_r3s4t5u6",
  "action": "DB_QUERY_TIMEOUT",
  "entity_type": "Enrollment",
  "entity_id": null,
  "user_id": 3,
  "ip_address": "10.0.0.5",
  "endpoint": "/api/enrollments",
  "http_method": "GET",
  "http_status": 504,
  "status": "failure",
  "error_code": "DB_QUERY_TIMEOUT",
  "sensitivity_level": 1,
  "retryable": true,
  "details": {
    "query_summary": "SELECT enrollment_applications JOIN children JOIN parent_profiles",
    "duration_ms": 30500
  }
}
```

**Observability:**
- **Alert:** Any query timeout → P2 alert; > 5/hour → P1
- **Dashboard:** "Slow Queries" by endpoint with p95/p99 latency

---

### ERR_014 — CSV Import Failed

| Field                | Value                                                                 |
|----------------------|-----------------------------------------------------------------------|
| **Event ID**         | `ERR_014`                                                             |
| **Event Name**       | `audit.admin.csv_import.failure`                                      |
| **Error Code**       | `CSV_IMPORT_FAILED`                                                   |
| **Log Level**        | ERROR                                                                 |
| **Severity**         | Medium                                                                |
| **Category**         | Bulk Operations                                                       |
| **Sensitivity**      | 2 (Medium)                                                            |

**When to Trigger:**
The CSV import endpoint (`/api/admin/users/import-csv`) fails to process the uploaded file. Causes include: invalid CSV format, missing required columns, encoding errors, row-level validation failures that exceed the tolerance threshold, or database errors during batch insert.

**Meaning:**
A bulk user import operation was attempted but could not be completed.

**Likely Root Causes:**
1. CSV file has wrong encoding (not UTF-8)
2. Missing required columns (name, email, role)
3. Row data fails validation (invalid emails, duplicate entries)
4. File too large or exceeds row limit
5. Database constraint violation on batch insert
6. Malformed CSV (unquoted commas, mismatched columns)

**User Impact:**
No users are imported. Admin sees an error with details about what went wrong.

**System Impact:**
No data change (transaction rolled back). Large file processing may have consumed memory briefly.

**Recommended Response:**

| Phase        | Action                                                                  |
|--------------|------------------------------------------------------------------------|
| Immediate    | Return error with row-level details; roll back all changes              |
| Engineering  | Add CSV preview/validation step before committing; improve error detail |
| Prevention   | Add file size limits; provide CSV template download; validate headers first |

**Logging Fields:**

| Field              | Required | Redaction                    |
|--------------------|----------|------------------------------|
| `correlation_id`   | YES      | —                            |
| `user_id`          | YES      | —                            |
| `ip_address`       | YES      | —                            |
| `file_name`        | YES      | —                            |
| `total_rows`       | YES      | —                            |
| `failed_rows`      | YES      | —                            |
| `error_summary`    | YES      | Redact PII from row data     |

**User-Facing Message:**
- **Text:** "The CSV file could not be imported. Please check the format and try again."
- **Message Key:** `error.admin.csv_import_failed`
- **UI Action:** Show error details per row; provide link to download CSV template

**HTTP Mapping:**

| Field         | Value                              |
|---------------|------------------------------------|
| Status Code   | `400 Bad Request`                  |
| Response Body | Error object with `CSV_IMPORT_FAILED` and row-level errors |

**Retry Guidance:**
- Client retry: Yes, after fixing the CSV file
- Backoff: Not applicable

**Example Structured Log:**
```json
{
  "event_id": "ERR_014",
  "event_name": "audit.admin.csv_import.failure",
  "level": "ERROR",
  "timestamp": "2026-01-26T12:00:00.000Z",
  "correlation_id": "corr_b4c5d6e7-f8a9-0123-bcde-456789012345",
  "request_id": "req_s4t5u6v7",
  "action": "CSV_IMPORT",
  "entity_type": "User",
  "entity_id": null,
  "user_id": 3,
  "role": "admin",
  "ip_address": "10.0.0.5",
  "endpoint": "/api/admin/users/import-csv",
  "http_method": "POST",
  "http_status": 400,
  "status": "failure",
  "error_code": "CSV_IMPORT_FAILED",
  "sensitivity_level": 2,
  "retryable": true,
  "details": {
    "file_name": "users_jan.csv",
    "total_rows": 50,
    "failed_rows": 3,
    "error_summary": "Rows 12,28,45: invalid email format"
  }
}
```

**Observability:**
- **Alert:** CSV import failures > 5/day → P3 (template issue or user training needed)
- **Dashboard:** "CSV Import Success/Failure" ratio chart

---

### ERR_015 — Message Send Failed

| Field                | Value                                                                 |
|----------------------|-----------------------------------------------------------------------|
| **Event ID**         | `ERR_015`                                                             |
| **Event Name**       | `audit.messaging.send.failure`                                        |
| **Error Code**       | `MESSAGE_SEND_FAILED`                                                 |
| **Log Level**        | ERROR                                                                 |
| **Severity**         | High                                                                  |
| **Category**         | Messaging                                                             |
| **Sensitivity**      | 2 (Medium)                                                            |

**When to Trigger:**
The admin message send endpoint fails to persist the message to the database. This triggers when `db.commit()` raises an exception in the message creation flow.

**Meaning:**
A message (direct, group, or announcement) could not be saved. Recipients will not receive the message.

**Likely Root Causes:**
1. Database constraint violation (missing required fields)
2. Foreign key violation (sender or recipient user deleted)
3. Database connection lost mid-transaction
4. Message body exceeds column size limit
5. Concurrent conflicting write (deadlock)

**User Impact:**
Message is not sent. Admin sees an error and must retry.

**System Impact:**
Transaction rolled back. No partial data. But the admin's composed message content may be lost if not preserved client-side.

**Recommended Response:**

| Phase        | Action                                                            |
|--------------|------------------------------------------------------------------|
| Immediate    | Return 500; preserve message content client-side for retry        |
| Engineering  | Add retry logic in service layer; improve error handling          |
| Prevention   | Add draft auto-save feature; validate all FKs before commit      |

**Logging Fields:**

| Field              | Required | Redaction                    |
|--------------------|----------|------------------------------|
| `correlation_id`   | YES      | —                            |
| `user_id`          | YES      | —                            |
| `ip_address`       | YES      | —                            |
| `recipient_count`  | YES      | —                            |
| `message_type`     | YES      | —                            |
| `exception_type`   | YES      | —                            |
| `message_content`  | NEVER    | Never log message body       |

**User-Facing Message:**
- **Text:** "The message could not be sent. Please try again."
- **Message Key:** `error.messaging.send_failed`
- **UI Action:** Keep message content in the form; show "Retry" button

**HTTP Mapping:**

| Field         | Value                               |
|---------------|-------------------------------------|
| Status Code   | `500 Internal Server Error`         |
| Response Body | Error object with `MESSAGE_SEND_FAILED` |

**Retry Guidance:**
- Client retry: Yes
- Backoff: Wait 2 seconds, then retry once

**Example Structured Log:**
```json
{
  "event_id": "ERR_015",
  "event_name": "audit.messaging.send.failure",
  "level": "ERROR",
  "timestamp": "2026-01-26T12:15:00.000Z",
  "correlation_id": "corr_c5d6e7f8-a9b0-1234-cdef-567890123456",
  "request_id": "req_t5u6v7w8",
  "action": "MESSAGE_SEND_FAILED",
  "entity_type": "Message",
  "entity_id": null,
  "user_id": 3,
  "role": "admin",
  "ip_address": "10.0.0.5",
  "endpoint": "/api/admin/messages",
  "http_method": "POST",
  "http_status": 500,
  "status": "failure",
  "error_code": "MESSAGE_SEND_FAILED",
  "sensitivity_level": 2,
  "retryable": true,
  "details": {
    "message_type": "announcement",
    "recipient_count": 45,
    "exception_type": "IntegrityError"
  }
}
```

**Observability:**
- **Alert:** Any message send failure → P2 alert
- **Dashboard:** "Message Delivery" success/failure ratio

---

### ERR_016 — Notification Queue Failed

| Field                | Value                                                                 |
|----------------------|-----------------------------------------------------------------------|
| **Event ID**         | `ERR_016`                                                             |
| **Event Name**       | `audit.notification.queue.failure`                                    |
| **Error Code**       | `NOTIFICATION_QUEUE_FAILED`                                           |
| **Log Level**        | ERROR                                                                 |
| **Severity**         | Medium                                                                |
| **Category**         | Notifications                                                         |
| **Sensitivity**      | 1 (Low)                                                               |

**When to Trigger:**
After a message is successfully persisted, the attempt to enqueue notifications (email, push) via Celery/Redis fails. The message itself is saved, but recipients will not be notified in real-time.

**Meaning:**
Message was saved but push/email notifications could not be queued. Recipients will see the message when they next open the app, but won't receive a proactive notification.

**Likely Root Causes:**
1. Redis is unreachable (Celery broker down)
2. Celery worker is not running
3. Notification task serialization error
4. Redis memory limit exceeded
5. Network timeout to Redis

**User Impact:**
Message is delivered (visible in inbox) but recipients are not notified. They may miss time-sensitive communications.

**System Impact:**
Notification pipeline is broken. Messages accumulate without notifications. Non-blocking — the core message flow still works.

**Recommended Response:**

| Phase        | Action                                                                  |
|--------------|------------------------------------------------------------------------|
| Immediate    | Log warning; the message is saved — no data loss                        |
| Engineering  | Add retry queue for failed notifications; implement fallback mechanism  |
| Prevention   | Monitor Redis health; add Celery heartbeat checks                      |

**Logging Fields:**

| Field            | Required | Redaction |
|------------------|----------|-----------|
| `correlation_id` | YES      | —         |
| `user_id`        | YES      | —         |
| `message_id`     | YES      | —         |
| `exception_type` | YES      | —         |
| `broker_url`     | NO       | Mask password in URL |

**User-Facing Message:**
- **Text:** "Your message was sent, but some recipients may not receive a notification immediately."
- **Message Key:** `warning.notification.queue_failed`
- **UI Action:** Show as a non-blocking warning toast

**HTTP Mapping:**
Not applicable — the HTTP response for the message send is already 201 (success). This error is logged server-side only.

**Retry Guidance:**
- Server-side retry: Yes, automatic via dead-letter queue
- Backoff: Exponential — 10s, 30s, 60s

**Example Structured Log:**
```json
{
  "event_id": "ERR_016",
  "event_name": "audit.notification.queue.failure",
  "level": "ERROR",
  "timestamp": "2026-01-26T12:30:00.000Z",
  "correlation_id": "corr_d6e7f8a9-b0c1-2345-defa-678901234567",
  "request_id": "req_u6v7w8x9",
  "action": "NOTIFICATION_QUEUE_FAILED",
  "entity_type": "Notification",
  "entity_id": null,
  "user_id": 3,
  "ip_address": "10.0.0.5",
  "endpoint": "/api/admin/messages",
  "http_method": "POST",
  "http_status": 201,
  "status": "partial",
  "error_code": "NOTIFICATION_QUEUE_FAILED",
  "sensitivity_level": 1,
  "retryable": true,
  "details": {
    "message_id": 142,
    "exception_type": "ConnectionError",
    "notification_count": 45
  }
}
```

**Observability:**
- **Alert:** Notification queue failures > 5/hour → P2 (Redis health check)
- **Dashboard:** "Notification Pipeline Health" with queue depth and failure rate

---

### ERR_017 — Export Generation Failed

| Field                | Value                                                                 |
|----------------------|-----------------------------------------------------------------------|
| **Event ID**         | `ERR_017`                                                             |
| **Event Name**       | `audit.admin.export.failure`                                          |
| **Error Code**       | `EXPORT_FAILED`                                                       |
| **Log Level**        | ERROR                                                                 |
| **Severity**         | Medium                                                                |
| **Category**         | Data Export                                                           |
| **Sensitivity**      | 2 (Medium)                                                            |

**When to Trigger:**
An export operation (user data export, audit log export, analytics report export) fails during data retrieval, formatting (CSV/JSON/PDF), or file generation.

**Meaning:**
The requested data export could not be completed.

**Likely Root Causes:**
1. Query returns too many rows (memory exhaustion)
2. Database timeout during export data retrieval
3. Disk space insufficient for temporary file
4. CSV/JSON serialization error (unexpected data types)
5. PDF generation library error

**User Impact:**
Admin does not receive the requested export file.

**System Impact:**
Temporary resource usage spike (memory/disk) that was reclaimed on failure. No data modification.

**Recommended Response:**

| Phase        | Action                                                            |
|--------------|------------------------------------------------------------------|
| Immediate    | Return error; suggest reducing date range or applying filters     |
| Engineering  | Implement streaming exports; add row limit with pagination        |
| Prevention   | Add export size estimation; warn before large exports             |

**Logging Fields:**

| Field            | Required | Redaction |
|------------------|----------|-----------|
| `correlation_id` | YES      | —         |
| `user_id`        | YES      | —         |
| `export_type`    | YES      | —         |
| `export_format`  | YES      | —         |
| `filter_params`  | YES      | —         |
| `row_count_est`  | NO       | —         |
| `exception_type` | YES      | —         |

**User-Facing Message:**
- **Text:** "The export could not be generated. Try applying more filters to reduce the data size."
- **Message Key:** `error.admin.export_failed`
- **UI Action:** Return to export form with filters preserved

**HTTP Mapping:**

| Field         | Value                          |
|---------------|--------------------------------|
| Status Code   | `500 Internal Server Error`    |
| Response Body | Error object with `EXPORT_FAILED` |

**Retry Guidance:**
- Client retry: Yes, with narrower filters
- Backoff: Not applicable

**Example Structured Log:**
```json
{
  "event_id": "ERR_017",
  "event_name": "audit.admin.export.failure",
  "level": "ERROR",
  "timestamp": "2026-01-26T12:45:00.000Z",
  "correlation_id": "corr_e7f8a9b0-c1d2-3456-efab-789012345678",
  "request_id": "req_v7w8x9y0",
  "action": "EXPORT_FAILED",
  "entity_type": "Export",
  "entity_id": null,
  "user_id": 3,
  "role": "admin",
  "ip_address": "10.0.0.5",
  "endpoint": "/api/audit-logs/export",
  "http_method": "GET",
  "http_status": 500,
  "status": "failure",
  "error_code": "EXPORT_FAILED",
  "sensitivity_level": 2,
  "retryable": true,
  "details": {
    "export_type": "audit_logs",
    "export_format": "csv",
    "filter_params": {"period": 365},
    "exception_type": "MemoryError"
  }
}
```

**Observability:**
- **Alert:** Export failure → P3 alert
- **Dashboard:** "Export Success/Failure" by type and format

---

### ERR_018 — File Upload Failed

| Field                | Value                                                                 |
|----------------------|-----------------------------------------------------------------------|
| **Event ID**         | `ERR_018`                                                             |
| **Event Name**       | `audit.storage.upload.failure`                                        |
| **Error Code**       | `FILE_UPLOAD_FAILED`                                                  |
| **Log Level**        | ERROR                                                                 |
| **Severity**         | Medium                                                                |
| **Category**         | Storage                                                               |
| **Sensitivity**      | 1 (Low)                                                               |

**When to Trigger:**
A file upload operation (message attachment, CSV import file, portfolio document) fails during file reception, validation, or storage (local disk or S3).

**Meaning:**
The uploaded file could not be saved to the configured storage backend.

**Likely Root Causes:**
1. File exceeds `MAX_ATTACHMENT_SIZE_MB` (10 MB default)
2. File type not in allowed list
3. Storage backend unavailable (S3 unreachable, local disk full)
4. Upload interrupted (client disconnected)
5. File name contains invalid characters
6. Storage permissions error

**User Impact:**
Upload is rejected. User must re-select and re-upload the file.

**System Impact:**
No data stored. Temporary upload buffer released.

**Recommended Response:**

| Phase        | Action                                                         |
|--------------|----------------------------------------------------------------|
| Immediate    | Return error with specific reason (size, type, etc.)            |
| Engineering  | Add client-side file validation before upload                   |
| Prevention   | Show max file size in UI; validate type before upload starts    |

**Logging Fields:**

| Field            | Required | Redaction |
|------------------|----------|-----------|
| `correlation_id` | YES      | —         |
| `user_id`        | YES      | —         |
| `file_name`      | YES      | —         |
| `file_size_bytes` | YES     | —         |
| `content_type`   | YES      | —         |
| `failure_reason` | YES      | —         |

**User-Facing Message:**
- **Text:** "The file could not be uploaded. Please check the file size and format."
- **Message Key:** `error.storage.upload_failed`
- **UI Action:** Show specific error (e.g., "File exceeds 10 MB limit")

**HTTP Mapping:**

| Field         | Value                              |
|---------------|------------------------------------|
| Status Code   | `400 Bad Request` or `413 Payload Too Large` |
| Response Body | Error object with `FILE_UPLOAD_FAILED` |

**Retry Guidance:**
- Client retry: Yes, after fixing file issue
- Backoff: Not applicable

**Example Structured Log:**
```json
{
  "event_id": "ERR_018",
  "event_name": "audit.storage.upload.failure",
  "level": "ERROR",
  "timestamp": "2026-01-26T13:00:00.000Z",
  "correlation_id": "corr_f8a9b0c1-d2e3-4567-fabc-890123456789",
  "request_id": "req_w8x9y0z1",
  "action": "FILE_UPLOAD_FAILED",
  "entity_type": "Attachment",
  "entity_id": null,
  "user_id": 3,
  "ip_address": "10.0.0.5",
  "endpoint": "/api/messages/attachments",
  "http_method": "POST",
  "http_status": 413,
  "status": "failure",
  "error_code": "FILE_UPLOAD_FAILED",
  "sensitivity_level": 1,
  "retryable": true,
  "details": {
    "file_name": "report.pdf",
    "file_size_bytes": 15728640,
    "content_type": "application/pdf",
    "failure_reason": "exceeds_max_size",
    "max_size_bytes": 10485760
  }
}
```

**Observability:**
- **Alert:** Storage backend errors (not size/type) > 5/hour → P2
- **Dashboard:** "Upload Success/Failure" by reason

---

### ERR_019 — Invalid API Response

| Field                | Value                                                                 |
|----------------------|-----------------------------------------------------------------------|
| **Event ID**         | `ERR_019`                                                             |
| **Event Name**       | `audit.system.api_response.invalid`                                   |
| **Error Code**       | `INVALID_API_RESPONSE`                                                |
| **Log Level**        | ERROR                                                                 |
| **Severity**         | High                                                                  |
| **Category**         | Integration                                                           |
| **Sensitivity**      | 2 (Medium)                                                            |

**When to Trigger:**
An external API call (e.g., Google GenAI, S3, SMTP, FCM) returns a response that cannot be parsed as expected — invalid JSON, unexpected status code, missing required fields, or HTML error page instead of JSON.

**Meaning:**
An external service returned an unexpected response. The integration is broken or degraded.

**Likely Root Causes:**
1. External API changed its response format (breaking change)
2. External API returned an HTML error page (maintenance mode)
3. Network proxy/CDN intercepted the request and returned its own error
4. API key expired or was revoked
5. Rate limited by external service
6. SSL/TLS handshake failure

**User Impact:**
The feature depending on the external API is unavailable (e.g., AI-generated content, push notifications, file storage).

**System Impact:**
Dependent feature degraded. Core platform continues to function.

**Detection Signals:**
- Non-2xx responses from external API calls
- JSON parse errors on external responses
- Unexpected `Content-Type` headers

**Recommended Response:**

| Phase        | Action                                                                     |
|--------------|---------------------------------------------------------------------------|
| Immediate    | Return graceful fallback; log response metadata (NOT full body)            |
| Engineering  | Add circuit breaker for external calls; implement fallback behavior        |
| Prevention   | Monitor external API health; set up status page alerts; add contract tests |

**Logging Fields:**

| Field              | Required | Redaction                                     |
|--------------------|----------|-----------------------------------------------|
| `correlation_id`   | YES      | —                                             |
| `external_service` | YES      | —                                             |
| `external_url`     | YES      | Mask query params with secrets                 |
| `response_status`  | YES      | —                                             |
| `content_type`     | YES      | —                                             |
| `response_body`    | NO*      | *Truncated to 256 chars; hash full body; store full in secure debug storage only |
| `api_key`          | NEVER    | Never log API keys                             |

**User-Facing Message:**
- **Text:** "A supporting service is temporarily unavailable. The main features are still working."
- **Message Key:** `error.integration.unavailable`
- **UI Action:** Hide or grey out the dependent feature with tooltip

**HTTP Mapping:**

| Field         | Value                           |
|---------------|---------------------------------|
| Status Code   | `502 Bad Gateway`               |
| Response Body | Error object with `INVALID_API_RESPONSE` |

**Retry Guidance:**
- Client retry: Yes (for transient issues)
- Backoff: Exponential — 2s, 4s, 8s, max 3 retries; circuit-break after 5 consecutive failures

**Example Structured Log:**
```json
{
  "event_id": "ERR_019",
  "event_name": "audit.system.api_response.invalid",
  "level": "ERROR",
  "timestamp": "2026-01-26T13:15:00.000Z",
  "correlation_id": "corr_a9b0c1d2-e3f4-5678-abcd-901234567890",
  "request_id": "req_x9y0z1a2",
  "action": "INVALID_API_RESPONSE",
  "entity_type": "Integration",
  "entity_id": null,
  "user_id": 3,
  "ip_address": "10.0.0.5",
  "endpoint": "/api/kpi/ai-insights",
  "http_method": "GET",
  "http_status": 502,
  "status": "failure",
  "error_code": "INVALID_API_RESPONSE",
  "sensitivity_level": 2,
  "retryable": true,
  "details": {
    "external_service": "google_genai",
    "external_url": "https://generativelanguage.googleapis.com/v1/***",
    "response_status": 503,
    "content_type": "text/html",
    "response_body_truncated": "<!DOCTYPE html><html><head><title>Service Unavai...",
    "response_body_hash": "sha256:abc123..."
  }
}
```

**Observability:**
- **Alert:** External API errors > 10/hour → P2; circuit open → P1
- **Dashboard:** "External API Health" per service with success rate and latency

---

### ERR_020 — Bulk Operation Partial Failure

| Field                | Value                                                                 |
|----------------------|-----------------------------------------------------------------------|
| **Event ID**         | `ERR_020`                                                             |
| **Event Name**       | `audit.admin.bulk.partial_failure`                                    |
| **Error Code**       | `BULK_PARTIAL_FAILURE`                                                |
| **Log Level**        | ERROR                                                                 |
| **Severity**         | High                                                                  |
| **Category**         | Bulk Operations                                                       |
| **Sensitivity**      | 2 (Medium)                                                            |

**When to Trigger:**
A bulk operation (create, update, delete) succeeds for some records but fails for others. The operation is not fully atomic — some changes were committed while others failed.

**Meaning:**
A batch operation completed partially. Some records were modified while others were not, creating an inconsistent state that the admin must reconcile.

**Likely Root Causes:**
1. Some records failed validation while others passed
2. Concurrent modification — some records were changed by another user during the batch
3. Database constraint violation on specific records (e.g., duplicate email for one user)
4. Record-level permission check failed for a subset
5. Transaction timeout on a large batch

**User Impact:**
Admin sees a partial success report listing which records succeeded and which failed. Must manually resolve the failures.

**System Impact:**
Data is partially modified. The system is consistent per-record but the admin's intended batch was not fully applied.

**Recommended Response:**

| Phase        | Action                                                                    |
|--------------|--------------------------------------------------------------------------|
| Immediate    | Return 207 Multi-Status with per-record results                          |
| Engineering  | Consider making bulk ops atomic (all-or-nothing) for critical operations  |
| Prevention   | Add batch validation preview; reduce max batch size                       |

**Logging Fields:**

| Field              | Required | Redaction |
|--------------------|----------|-----------|
| `correlation_id`   | YES      | —         |
| `user_id`          | YES      | —         |
| `operation`        | YES      | —         |
| `total_count`      | YES      | —         |
| `success_count`    | YES      | —         |
| `failure_count`    | YES      | —         |
| `failed_ids`       | YES      | —         |
| `failure_reasons`  | YES      | —         |

**User-Facing Message:**
- **Text:** "The operation partially completed: X of Y records were updated. See details for failures."
- **Message Key:** `error.bulk.partial_failure`
- **UI Action:** Show success/failure breakdown table with per-record status

**HTTP Mapping:**

| Field         | Value                             |
|---------------|-----------------------------------|
| Status Code   | `207 Multi-Status`                |
| Response Body | Error object with `BULK_PARTIAL_FAILURE` and per-record results |

**Retry Guidance:**
- Client retry: Yes, for failed records only
- Backoff: Not applicable

**Example Structured Log:**
```json
{
  "event_id": "ERR_020",
  "event_name": "audit.admin.bulk.partial_failure",
  "level": "ERROR",
  "timestamp": "2026-01-26T13:30:00.000Z",
  "correlation_id": "corr_b0c1d2e3-f4a5-6789-bcde-012345678901",
  "request_id": "req_y0z1a2b3",
  "action": "BULK_STATUS_UPDATE",
  "entity_type": "User",
  "entity_id": null,
  "user_id": 3,
  "role": "admin",
  "ip_address": "10.0.0.5",
  "endpoint": "/api/admin/users/bulk-status",
  "http_method": "PUT",
  "http_status": 207,
  "status": "partial",
  "error_code": "BULK_PARTIAL_FAILURE",
  "sensitivity_level": 2,
  "retryable": true,
  "details": {
    "operation": "BULK_STATUS_UPDATE",
    "total_count": 10,
    "success_count": 8,
    "failure_count": 2,
    "failed_ids": [15, 22],
    "failure_reasons": {
      "15": "user_not_found",
      "22": "constraint_violation"
    }
  }
}
```

**Observability:**
- **Alert:** Any partial failure → P3 alert
- **Dashboard:** "Bulk Operations" with success/partial/failure breakdown

---

### ERR_021 — Audit Log Write Failed

| Field                | Value                                                                 |
|----------------------|-----------------------------------------------------------------------|
| **Event ID**         | `ERR_021`                                                             |
| **Event Name**       | `audit.system.audit_write.failure`                                    |
| **Error Code**       | `AUDIT_WRITE_FAILED`                                                  |
| **Log Level**        | ERROR                                                                 |
| **Severity**         | Critical                                                              |
| **Category**         | System Integrity                                                      |
| **Sensitivity**      | 3 (High)                                                              |

**When to Trigger:**
The `log_audit_action()` or `log_audit_event()` function raises an exception when attempting to write an audit log record to the database. The primary operation may have succeeded, but the audit trail is broken.

**Meaning:**
The audit logging system itself has failed. This is a critical integrity issue — operations are occurring without being recorded, which violates compliance requirements.

**Likely Root Causes:**
1. Database connection failure (same as ERR_012 but specific to audit writes)
2. `audit_logs` table is full or disk space exhausted
3. Column constraint violation in audit log record (unlikely — text fields)
4. Transaction isolation conflict
5. `details` field exceeds `AUDIT_LOG_MAX_DETAILS_SIZE` after truncation fails

**User Impact:**
None directly — the primary operation succeeded. But there is no audit record of the action.

**System Impact:**
Compliance gap. Actions are unaudited. Forensic investigation capability is degraded.

**Detection Signals:**
- Application error logs containing audit write exceptions
- Gap in audit log timestamps (missing expected events)
- Discrepancy between operation counts and audit log counts

**Recommended Response:**

| Phase        | Action                                                                       |
|--------------|-----------------------------------------------------------------------------|
| Immediate    | Fall back to Python file logger; write audit event to a fallback log file    |
| Engineering  | Add audit write retry with separate connection; add fallback to file logging |
| Prevention   | Monitor audit log write latency; alert on gaps in audit log sequence         |

**Logging Fields:**

| Field              | Required | Redaction                     |
|--------------------|----------|-------------------------------|
| `correlation_id`   | YES      | —                             |
| `original_action`  | YES      | —                             |
| `original_entity`  | YES      | —                             |
| `exception_type`   | YES      | —                             |
| `exception_message`| YES      | Redact if contains SQL data   |

**User-Facing Message:**
Not applicable — this is an internal system error not surfaced to users.

**HTTP Mapping:**
Not applicable — the primary HTTP response is unaffected. This error is logged server-side only.

**Retry Guidance:**
- Server-side retry: Yes, immediate retry once; then fallback to file logger
- Backoff: Immediate retry, then fallback

**Example Structured Log:**
```json
{
  "event_id": "ERR_021",
  "event_name": "audit.system.audit_write.failure",
  "level": "ERROR",
  "timestamp": "2026-01-26T13:45:00.000Z",
  "correlation_id": "corr_c1d2e3f4-a5b6-7890-cdef-123456789012",
  "request_id": "req_z1a2b3c4",
  "action": "AUDIT_WRITE_FAILED",
  "entity_type": "System",
  "entity_id": null,
  "user_id": null,
  "ip_address": "10.0.0.5",
  "endpoint": "/api/admin/users",
  "http_method": "POST",
  "http_status": 201,
  "status": "failure",
  "error_code": "AUDIT_WRITE_FAILED",
  "sensitivity_level": 3,
  "retryable": true,
  "details": {
    "original_action": "USER_CREATED",
    "original_entity_type": "User",
    "original_entity_id": 50,
    "exception_type": "OperationalError",
    "fallback": "file_logger"
  }
}
```

**Observability:**
- **Alert:** Any audit write failure → P1 alert (compliance critical)
- **Dashboard:** "Audit System Health" with write success rate and gap detection

---

## 4. WARNING Definition

---

### WARN_001 — KPI Anomaly Detected

| Field                | Value                                                                 |
|----------------------|-----------------------------------------------------------------------|
| **Event ID**         | `WARN_001`                                                            |
| **Event Name**       | `audit.kpi.anomaly.detected`                                          |
| **Log Level**        | WARN                                                                  |
| **Severity**         | Medium                                                                |
| **Category**         | Analytics                                                             |
| **Sensitivity**      | 1 (Low)                                                               |

**When to Trigger:**
During KPI snapshot calculation, a metric value deviates significantly from its historical baseline or expected range. Examples: attendance rate drops below 50%, staff-to-child ratio exceeds regulatory maximum, enrollment rate changes by more than 30% week-over-week.

**Meaning:**
A KPI metric has entered an anomalous state. This may indicate a data quality issue, an operational problem, or a genuine change in conditions that requires management attention.

**Likely Root Causes:**
1. Genuine operational change (flu outbreak causing low attendance)
2. Data entry errors (bulk incorrect attendance records)
3. Calculation bug in KPI service
4. Missing data (attendance not recorded, causing zero rates)
5. Configuration change (class capacity modified, skewing ratios)
6. Seasonal variation not accounted for in baseline

**User Impact:**
KPI dashboard may show unexpected or alarming values. No feature is broken.

**System Impact:**
None — this is informational. Analytics cache may be updated with anomalous values.

**Detection Signals:**
- `KPI_ANOMALY:` prefix in application logs
- KPI values outside 2 standard deviations from 30-day rolling average
- Sudden zero-value metrics

**Recommended Response:**

| Phase        | Action                                                                      |
|--------------|----------------------------------------------------------------------------|
| Immediate    | Flag anomalous KPIs on the dashboard; notify kindergarten manager           |
| Engineering  | Add anomaly annotations to KPI charts; implement data quality pre-checks    |
| Prevention   | Add data entry validation; implement expected-range alerts per metric       |

**Logging Fields:**

| Field                  | Required | Redaction |
|------------------------|----------|-----------|
| `correlation_id`       | YES      | —         |
| `kpi_name`             | YES      | —         |
| `kindergarten_id`      | YES      | —         |
| `current_value`        | YES      | —         |
| `expected_range_low`   | YES      | —         |
| `expected_range_high`  | YES      | —         |
| `baseline_value`       | YES      | —         |
| `deviation_percentage` | YES      | —         |

**User-Facing Message:**
- **Text:** "Some metrics are showing unusual values. Please review the highlighted indicators."
- **Message Key:** `warning.kpi.anomaly_detected`
- **UI Action:** Add warning badge on anomalous KPI cards on the dashboard

**HTTP Mapping:**
Not directly applicable — KPI anomalies are detected during background calculation, not in response to a specific HTTP request. If surfaced via API:

| Field         | Value                                    |
|---------------|------------------------------------------|
| Status Code   | `200 OK` (with anomaly flags in payload) |

**Retry Guidance:**
Not applicable — this is a detection event, not a request failure.

**Example Structured Log:**
```json
{
  "event_id": "WARN_001",
  "event_name": "audit.kpi.anomaly.detected",
  "level": "WARN",
  "timestamp": "2026-01-26T06:00:00.000Z",
  "correlation_id": "corr_kpi_daily_20260126",
  "request_id": null,
  "action": "KPI_ANOMALY",
  "entity_type": "KPISnapshot",
  "entity_id": null,
  "user_id": null,
  "ip_address": null,
  "endpoint": null,
  "http_method": null,
  "http_status": null,
  "status": "detected",
  "sensitivity_level": 1,
  "retryable": false,
  "details": {
    "kpi_name": "attendance_rate",
    "kindergarten_id": 5,
    "current_value": 0.32,
    "expected_range_low": 0.70,
    "expected_range_high": 0.95,
    "baseline_value": 0.85,
    "deviation_percentage": -62.4
  }
}
```

**Observability:**
- **Alert:** Critical KPI anomaly (safety ratios) → P2 alert to management
- **Dashboard:** "KPI Anomalies" panel with anomaly history and sparklines

---

## 5. INFO Definitions

> INFO events use a compressed format. Each entry includes: Event ID, Event Name, Category, Trigger, Meaning, Required Fields, Redaction Rules, and Example Log.

---
