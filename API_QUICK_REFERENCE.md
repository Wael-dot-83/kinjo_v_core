# KInJo Platform - API Quick Reference

## Base URL

```
http://127.0.0.1:8000
```

## Authentication

### Get Token (Login)

```
POST /token
Content-Type: application/x-www-form-urlencoded

username=admin&password=Admin123!

Response:
{
  "access_token": "eyJhbGc...",
  "token_type": "bearer"
}
```

### Using Token in Requests

```
Authorization: Bearer <access_token>
```

---

## Core Endpoints

### Users

```
GET  /api/users/me              → Get current user info
GET  /api/users/{id}            → Get user by ID
GET  /api/users                 → List all users
```

### Kindergartens

```
GET    /api/kindergartens                → List kindergartens
GET    /api/kindergartens/{id}           → Get kindergarten
POST   /api/kindergartens                → Create kindergarten
PUT    /api/kindergartens/{id}           → Update kindergarten
DELETE /api/kindergartens/{id}           → Delete kindergarten
```

### Classes

```
GET    /api/classes                → List classes
GET    /api/classes/{id}           → Get class details
POST   /api/classes                → Create class
PUT    /api/classes/{id}           → Update class
DELETE /api/classes/{id}           → Delete class
```

### Children & Enrollment

```
GET    /api/children                     → List children
GET    /api/children/{id}                → Get child details
POST   /api/children                     → Create child
PUT    /api/children/{id}                → Update child
GET    /api/enrollments                  → List enrollments
POST   /api/enrollments                  → Create enrollment
```

### Attendance

```
POST   /api/attendance/check-in          → Record check-in
POST   /api/attendance/check-out         → Record check-out
GET    /api/attendance/today             → Get today's attendance
GET    /api/attendance/{date}            → Get attendance by date
```

### Daily Reports

```
POST   /api/daily-reports/create         → Create daily report
GET    /api/daily-reports                → List reports
GET    /api/daily-reports/{id}           → Get report details
POST   /api/daily-reports/{id}/submit    → Submit report
POST   /api/daily-reports/{id}/approve   → Approve report
GET    /api/daily-reports/child/{id}     → Get child reports
```

### Incidents

```
POST   /api/incidents/create             → Report incident
GET    /api/incidents                    → List incidents
GET    /api/incidents/{id}               → Get incident details
PUT    /api/incidents/{id}               → Update incident
```

### Staff Management

```
POST   /api/staff/create                 → Create staff account
GET    /api/staff                        → List staff
GET    /api/staff/{id}                   → Get staff details
PUT    /api/staff/{id}                   → Update staff
```

### Messaging (Communication)

```
POST   /comm/messages                    Send message (direct/class/broadcast)
GET    /comm/messages                    List messages (pagination + filters)
GET    /comm/messages/{id}               Get message details
POST   /comm/messages/{id}/read          Mark message as read
DELETE /comm/messages/{id}               Soft delete for current user
POST   /comm/messages/{id}/archive       Archive message
POST   /comm/messages/{id}/unarchive     Unarchive message
GET    /comm/messages/unread/count       Unread count for current user
POST   /comm/messages/{id}/replies       Reply to direct message
GET    /comm/messages/{id}/replies       Get thread (root + replies)
POST   /comm/messages/{id}/attachments   Upload attachment (multipart)
GET    /comm/messages/{id}/attachments   List message attachments
GET    /comm/messages/attachments/{id}   Download attachment
POST   /comm/messages/bulk               Bulk read/archive/delete
POST   /comm/notifications/devices       Register push device token
DELETE /comm/notifications/devices/{id}  Remove push device token
```

Message list query params (examples):

```
?page=1&page_size=25&thread_type=direct&search=welcome&unread_only=true
?archived_only=true
```

Notes:
- Attachments enforce `MAX_ATTACHMENT_SIZE_MB` and use `STORAGE_PROVIDER` (`local` or `s3`) with `S3_*` settings when enabled.
- Rate-limited endpoints return 429 with `Retry-After` and `{ error: { code: "RATE_LIMITED" } }`.


---

## Dashboard Endpoints

### Manager Dashboard

```
GET /api/manager/dashboard

Response:
{
  "summary": {
    "active_enrollments": 45,
    "attendance_today": 38,
    "incidents": 2,
    "approval_rate": 95
  },
  "daily_attendance": [...],
  "incidents_this_week": [...],
  "recent_reports": [...]
}
```

### Supervisor Dashboard

```
GET /api/supervisor/dashboard

Response:
{
  "my_classes": [...],
  "my_children": [...],
  "attendance_status": {...},
  "pending_reports": [...],
  "performance_metrics": {...}
}
```

### KPI Endpoints

```
GET /api/kpi/attendance-rate            → Attendance percentage
GET /api/kpi/incident-rate              → Incident metrics
GET /api/kpi/ratio-compliance           → Staff ratio compliance
GET /api/kpi/governance-score           → Quality governance score
```

---

## Query Parameters

### Pagination

```
?skip=0&limit=10        → Skip first 10, return next 10 items
?page=1&per_page=20     → Get page 1 with 20 items per page
```

### Filtering

```
?status=ACTIVE          → Filter by status
?role=SUPERVISOR        → Filter by role
?kindergarten_id=1      → Filter by kindergarten
?class_id=2             → Filter by class
```

### Sorting

```
?sort_by=name           → Sort by field name
?order=asc              → Ascending order (default)
?order=desc             → Descending order
```

### Date Filters

```
?start_date=2026-01-01  → Start date for range
?end_date=2026-01-31    → End date for range
?date=2026-01-16        → Specific date
```

---

## Request/Response Examples

### Example 1: Get Current User

```bash
curl -X GET http://127.0.0.1:8000/api/users/me \
  -H "Authorization: Bearer <token>" \
  -H "Content-Type: application/json"

Response:
{
  "id": 1,
  "username": "admin",
  "email": "admin@kinjo.local",
  "role": "ADMIN",
  "status": "ACTIVE",
  "kindergarten_id": 1
}
```

### Example 2: Check In Child

```bash
curl -X POST http://127.0.0.1:8000/api/attendance/check-in \
  -H "Authorization: Bearer <token>" \
  -H "Content-Type: application/json" \
  -d '{
    "child_id": 5,
    "method": "MANUAL",
    "dropped_by_name": "أم أحمد"
  }'

Response:
{
  "id": 142,
  "child_id": 5,
  "check_in_time": "2026-01-16T08:15:00",
  "method": "MANUAL",
  "dropped_by_name": "أم أحمد",
  "status": "CHECKED_IN"
}
```

### Example 3: Create Daily Report

```bash
curl -X POST http://127.0.0.1:8000/api/daily-reports/create \
  -H "Authorization: Bearer <token>" \
  -H "Content-Type: application/json" \
  -d '{
    "child_id": 5,
    "report_date": "2026-01-16",
    "mood": "HAPPY",
    "appetite": "GOOD",
    "sleep_duration": 90,
    "activities": "Played with blocks and colored",
    "notes": "Had a great day today"
  }'

Response:
{
  "id": 78,
  "child_id": 5,
  "report_date": "2026-01-16",
  "status": "DRAFT",
  "created_at": "2026-01-16T10:30:00"
}
```

### Example 4: List Classes

```bash
curl -X GET "http://127.0.0.1:8000/api/classes?skip=0&limit=10" \
  -H "Authorization: Bearer <token>" \
  -H "Content-Type: application/json"

Response:
{
  "total": 5,
  "items": [
    {
      "id": 1,
      "name": "الفئة الصغرى",
      "capacity": 20,
      "current_enrollment": 18,
      "supervisor_id": 2,
      "kindergarten_id": 1
    },
    {
      "id": 2,
      "name": "الفئة الوسطى",
      "capacity": 25,
      "current_enrollment": 22,
      "supervisor_id": 3,
      "kindergarten_id": 1
    }
  ]
}
```

---

## Common Response Codes

| Code | Meaning             | Action                        |
| ---- | ------------------- | ----------------------------- |
| 200  | OK                  | Request succeeded             |
| 201  | Created             | Resource created successfully |
| 204  | No Content          | Success with no response body |
| 400  | Bad Request         | Invalid request parameters    |
| 401  | Unauthorized        | Missing or invalid token      |
| 403  | Forbidden           | User lacks permission         |
| 404  | Not Found           | Resource doesn't exist        |
| 422  | Validation Error    | Invalid data format           |
| 500  | Server Error        | Backend error                 |
| 503  | Service Unavailable | Server down or database error |

---

## Error Response Format

```json
{
  "error": {
    "code": "VALIDATION_ERROR",
    "message": "Message body is required",
    "fields": {
      "message_body": "required"
    },
    "correlation_id": "b3a1c5e4-1234-4cdd-9a2d-9d9d0d8a1c2f"
  }
}
```
## Rate Limits & Pagination

**Pagination:** `page` + `page_size` (defaults 25, max 100)
**Rate limiting:** Enabled; tune via `RATE_LIMIT_*` settings in `.env`

Username: admin
Password: Admin123!
Role: ADMIN

Username: manager1
Password: Manager123!
Role: MANAGER

Username: supervisor1
Password: Supervisor123!
Role: SUPERVISOR

Username: parent1
Password: Parent123!
Role: PARENT
```

---

## Browser Console Testing

```javascript
// Get API instance (should be available in window.api)
const api = window.api;

// Test getCurrentUser
api.getCurrentUser().then((user) => console.log(user));

// Test getClasses
api.getClasses().then((classes) => console.log(classes));

// Test getSupervisorDashboard
api.getSupervisorDashboard().then((dashboard) => console.log(dashboard));

// Check stored token
console.log("Token:", localStorage.getItem("token"));

// Check user info
console.log("User:", localStorage.getItem("user"));
```

---

## cURL Command Templates

### GET Request

```bash
curl -X GET "http://127.0.0.1:8000/api/endpoint" \
  -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/json"
```

### POST Request

```bash
curl -X POST "http://127.0.0.1:8000/api/endpoint" \
  -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/json" \
  -d '{"key": "value"}'
```

### PUT Request

```bash
curl -X PUT "http://127.0.0.1:8000/api/endpoint/1" \
  -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/json" \
  -d '{"key": "new_value"}'
```

### DELETE Request

```bash
curl -X DELETE "http://127.0.0.1:8000/api/endpoint/1" \
  -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/json"
```

---

## PowerShell Examples

### Get Token

```powershell
$response = Invoke-WebRequest -Uri "http://127.0.0.1:8000/token" `
  -Method POST `
  -Body "username=admin&password=Admin123!" `
  -ContentType "application/x-www-form-urlencoded"

$token = ($response.Content | ConvertFrom-Json).access_token
```

### Call API

```powershell
$headers = @{"Authorization" = "Bearer $token"}
$response = Invoke-WebRequest -Uri "http://127.0.0.1:8000/api/users/me" `
  -Headers $headers -Method GET

$response.Content | ConvertFrom-Json | Format-List
```

---

## Endpoint Documentation

For full API documentation with interactive testing:

```
http://127.0.0.1:8000/docs
```

This opens Swagger UI where you can:

- View all endpoints
- Test endpoints directly
- See request/response schemas
- Authorize with your token

---

_Last Updated: 2026-01-16_
_API Version: 1.0_
