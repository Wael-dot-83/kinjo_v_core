# KinJo Platform - Manual Testing Guide

**Server Status:** Running at http://localhost:8000  
**Interactive API Docs:** http://localhost:8000/docs  
**Database:** kinjo_dev.db (SQLite with seeded data)

---

## Quick Start

### 1. Server is Running ✅

The server was started with:

```bash
python -m uvicorn main:app --reload --host 0.0.0.0 --port 8000
```

### 2. Database Seeded ✅

Fresh database populated with:

- 2 Kindergartens (Al Amal, Al Noor)
- 4 Users (Admin, Manager, Supervisor, Parent)
- 1 Child (Layla Al-Rashid, 3 years old)
- 1 Class (Class A, capacity 20, ages 2-4 years)
- Services and operating calendar

---

## Test Credentials

### 🔑 Admin Account

- **Username:** `admin`
- **Password:** `Admin123!`
- **Access:** Full platform access

### 🔑 Manager Account

- **Username:** `manager1`
- **Password:** `Manager123!`
- **Kindergarten:** Al Amal (ID: 1)
- **Access:** Kindergarten-level management

### 🔑 Supervisor Account

- **Username:** `supervisor1`
- **Password:** `Supervisor123!`
- **Kindergarten:** Al Amal (ID: 1)
- **Class:** Class A (assigned)
- **Access:** Class-level operations

### 🔑 Parent Account

- **Username:** `parent1@example.com`
- **Password:** `Parent123!`
- **Child:** Layla Al-Rashid (ID: 1, 3 years old)
- **Access:** Own children only

---

## Testing Approaches

### Option 1: Interactive API Documentation (Recommended)

**URL:** http://localhost:8000/docs

This is the FastAPI Swagger UI - the easiest way to test!

**Steps:**

1. Open http://localhost:8000/docs in your browser
2. Find the `/api/auth/token` endpoint
3. Click "Try it out"
4. Enter credentials in the form format:
   ```
   username: admin
   password: Admin123!
   ```
5. Click "Execute"
6. Copy the `access_token` from the response
7. Click "Authorize" button at the top
8. Paste token: `Bearer <your_token_here>`
9. Now you can test any endpoint!

### Option 2: Web Interface

**URL:** http://localhost:8000

**Available Pages:**

- `/` - Landing page
- `/login` - Login form
- `/dashboard` - Role-based dashboard
- `/kindergartens` - Kindergarten list
- `/enrollment` - Enrollment management
- `/attendance` - Attendance tracking
- `/reports` - Daily reports
- `/kpi` - KPI dashboard

### Option 3: cURL Commands

See detailed cURL examples below

### Option 4: Postman/Thunder Client

Import the API and test systematically

---

## Complete Testing Scenarios

### Scenario 1: Admin Setup and Configuration

#### 1.1 Login as Admin

```bash
curl -X POST "http://localhost:8000/api/auth/token" \
  -H "Content-Type: application/x-www-form-urlencoded" \
  -d "username=admin&password=Admin123!"
```

**Expected Response:**

```json
{
  "access_token": "eyJ0eXAiOiJKV1QiLCJhbGc...",
  "token_type": "bearer"
}
```

**Save the token** for use in subsequent requests!

#### 1.2 View All Kindergartens

```bash
curl -X GET "http://localhost:8000/api/kindergartens" \
  -H "Authorization: Bearer YOUR_TOKEN"
```

**Expected:** List of 2 kindergartens (Al Amal, Al Noor)

#### 1.3 Create New Class

```bash
curl -X POST "http://localhost:8000/api/classes" \
  -H "Authorization: Bearer YOUR_TOKEN" \
  -H "Content-Type: application/json" \
  -d '{
    "kindergarten_id": 1,
    "name_ar": "الصف الثاني",
    "name_en": "Class B",
    "capacity_total": 15,
    "min_age_months": 36,
    "max_age_months": 60
  }'
```

#### 1.4 Check Class Capacity

```bash
curl -X GET "http://localhost:8000/api/classes/1/capacity-status" \
  -H "Authorization: Bearer YOUR_TOKEN"
```

**Expected:** Capacity info for Class A

---

### Scenario 2: Parent Journey (Complete Enrollment Flow)

#### 2.1 Login as Parent

```bash
curl -X POST "http://localhost:8000/api/auth/token" \
  -H "Content-Type: application/x-www-form-urlencoded" \
  -d "username=parent1@example.com&password=Parent123!"
```

#### 2.2 View Parent Dashboard

```bash
curl -X GET "http://localhost:8000/api/parent/dashboard" \
  -H "Authorization: Bearer YOUR_TOKEN"
```

**Expected:** Child info, enrollment status, attendance today

#### 2.3 Apply for Enrollment (New Child)

```bash
curl -X POST "http://localhost:8000/api/enrollment/apply" \
  -H "Authorization: Bearer YOUR_TOKEN" \
  -H "Content-Type: application/json" \
  -d '{
    "first_name": "Omar",
    "last_name": "Al-Rashid",
    "gender": "MALE",
    "date_of_birth": "2023-01-15",
    "father_name": "Ahmad Al-Rashid",
    "mother_first_name": "Fatima",
    "mother_last_name": "Hassan",
    "mother_nationality": "Jordanian",
    "mother_national_id": "0987654321",
    "kindergarten_id": 1
  }'
```

**Expected:** New enrollment created in DRAFT status

#### 2.4 Submit Enrollment for Review

```bash
curl -X POST "http://localhost:8000/api/enrollment/2/submit" \
  -H "Authorization: Bearer YOUR_TOKEN"
```

**Expected:** Status changed to SUBMITTED

#### 2.5 View Child's Daily Reports (Once Enrolled)

```bash
curl -X GET "http://localhost:8000/api/daily-reports/child/1" \
  -H "Authorization: Bearer YOUR_TOKEN"
```

**Expected:** List of approved daily reports only

#### 2.6 View Child's Portfolio

```bash
curl -X GET "http://localhost:8000/api/children/1/portfolio" \
  -H "Authorization: Bearer YOUR_TOKEN"
```

**Expected:** Published portfolio entries only

#### 2.7 View Child's Health Alerts

```bash
curl -X GET "http://localhost:8000/api/children/1/health-alerts" \
  -H "Authorization: Bearer YOUR_TOKEN"
```

---

### Scenario 3: Manager Operations

#### 3.1 Login as Manager

```bash
curl -X POST "http://localhost:8000/api/auth/token" \
  -H "Content-Type: application/x-www-form-urlencoded" \
  -d "username=manager1&password=Manager123!"
```

#### 3.2 View Manager Dashboard

```bash
curl -X GET "http://localhost:8000/api/manager/dashboard" \
  -H "Authorization: Bearer YOUR_TOKEN"
```

**Expected:**

- Pending applications count
- Active enrollments
- Waitlist count
- Today's attendance
- Pending reports
- Recent incidents
- Alerts (license expiry, etc.)

#### 3.3 Review Enrollment Application

```bash
curl -X POST "http://localhost:8000/api/enrollment/2/review?decision=accept" \
  -H "Authorization: Bearer YOUR_TOKEN"
```

**Expected:** Enrollment status changed to ACTIVE

#### 3.4 Assign Child to Class

```bash
curl -X POST "http://localhost:8000/api/enrollments/2/assign-class?class_id=1" \
  -H "Authorization: Bearer YOUR_TOKEN"
```

**Expected:** Child assigned to Class A

#### 3.5 Check In Child

```bash
curl -X POST "http://localhost:8000/api/attendance/check-in?child_id=1&method=PIN&dropped_by_name=Father" \
  -H "Authorization: Bearer YOUR_TOKEN"
```

**Expected:** Attendance log created with check-in time

#### 3.6 Check Out Child

```bash
curl -X POST "http://localhost:8000/api/attendance/check-out?child_id=1&picked_by_name=Mother" \
  -H "Authorization: Bearer YOUR_TOKEN"
```

**Expected:** Check-out time recorded

#### 3.7 View KPI Summary

```bash
curl -X GET "http://localhost:8000/api/kpi/summary?kindergarten_id=1&period_start=2026-01-01&period_end=2026-01-31" \
  -H "Authorization: Bearer YOUR_TOKEN"
```

**Expected:**

- Occupancy rate
- Attendance rate
- Governance score with band (GREEN/AMBER/RED)
- Incident count
- Pending reports

#### 3.8 Report Incident

```bash
curl -X POST "http://localhost:8000/api/incidents" \
  -H "Authorization: Bearer YOUR_TOKEN" \
  -H "Content-Type: application/json" \
  -d '{
    "child_id": 1,
    "type": "INJURY",
    "severity_level": "MINOR",
    "description": "Minor scrape on knee during outdoor play",
    "occurred_at": "2026-01-15T10:30:00",
    "followup_required_flag": false
  }'
```

#### 3.9 Add Health Alert

```bash
curl -X POST "http://localhost:8000/api/children/1/health-alerts" \
  -H "Authorization: Bearer YOUR_TOKEN" \
  -H "Content-Type: application/json" \
  -d '{
    "alert_type": "Allergy",
    "description": "Peanut allergy - severe",
    "severity": "High"
  }'
```

#### 3.10 Create Task

```bash
curl -X POST "http://localhost:8000/api/tasks" \
  -H "Authorization: Bearer YOUR_TOKEN" \
  -H "Content-Type: application/json" \
  -d '{
    "title": "Update emergency contact list",
    "description": "Verify all parent contact information is current",
    "priority": "HIGH",
    "assigned_to": 3,
    "due_date": "2026-01-20"
  }'
```

---

### Scenario 4: Supervisor Daily Operations

#### 4.1 Login as Supervisor

```bash
curl -X POST "http://localhost:8000/api/auth/token" \
  -H "Content-Type: application/x-www-form-urlencoded" \
  -d "username=supervisor1&password=Supervisor123!"
```

#### 4.2 View Supervisor Dashboard

```bash
curl -X GET "http://localhost:8000/api/supervisor/dashboard" \
  -H "Authorization: Bearer YOUR_TOKEN"
```

**Expected:**

- Assigned classes count
- Total children
- Today's attendance
- Pending draft reports

#### 4.3 View My Classes

```bash
curl -X GET "http://localhost:8000/api/supervisor/my-classes" \
  -H "Authorization: Bearer YOUR_TOKEN"
```

**Expected:** List of assigned classes (Class A)

#### 4.4 Record Observation

```bash
curl -X POST "http://localhost:8000/api/observations" \
  -H "Authorization: Bearer YOUR_TOKEN" \
  -H "Content-Type: application/json" \
  -d '{
    "child_id": 1,
    "domain": "COGNITIVE",
    "observation_text": "Layla successfully counted to 20 independently and recognized all numbers",
    "mastery_level": "ON_TRACK",
    "observed_at": "2026-01-15T11:00:00"
  }'
```

#### 4.5 Create Daily Report

```bash
curl -X POST "http://localhost:8000/api/daily-reports/create" \
  -H "Authorization: Bearer YOUR_TOKEN" \
  -H "Content-Type: application/json" \
  -d '{
    "child_id": 1,
    "date": "2026-01-15",
    "arrival_time": "08:00",
    "leave_time": "14:30",
    "breakfast": true,
    "snack": true,
    "milk": true,
    "lunch": true,
    "nap_start": "12:00",
    "nap_end": "13:30",
    "activities": "Art class, outdoor play, story time",
    "notes": "Great day! Very engaged in art activities"
  }'
```

#### 4.6 Submit Daily Report

```bash
curl -X POST "http://localhost:8000/api/daily-reports/1/submit" \
  -H "Authorization: Bearer YOUR_TOKEN"
```

**Expected:** Status changed to SUBMITTED (awaiting manager approval)

#### 4.7 Create Portfolio Entry

```bash
curl -X POST "http://localhost:8000/api/portfolios" \
  -H "Authorization: Bearer YOUR_TOKEN" \
  -H "Content-Type: application/json" \
  -d '{
    "child_id": 1,
    "title": "Winter Watercolor Painting",
    "description": "Beautiful winter scene with snowflakes and trees"
  }'
```

**Expected:** Portfolio entry created in DRAFT status

---

## Testing Validation Rules

### Age Validation (Enrollment)

**Test:** Try to enroll child younger than 70 days

```bash
curl -X POST "http://localhost:8000/api/enrollment/apply" \
  -H "Authorization: Bearer PARENT_TOKEN" \
  -H "Content-Type: application/json" \
  -d '{
    "first_name": "Baby",
    "last_name": "Too-Young",
    "gender": "MALE",
    "date_of_birth": "2026-01-01",
    ...
  }'
```

**Expected:** 400 error - "Child must be at least 70 days old"

### Capacity Enforcement

**Test:** Try to assign child when class full

1. Fill Class A to capacity (20 children)
2. Try to assign 21st child
   **Expected:** 400 error - "Class is at full capacity"

### Duplicate Check-In Prevention

**Test:** Try to check in same child twice

1. Check in child: `POST /api/attendance/check-in?child_id=1&method=PIN`
2. Try again: `POST /api/attendance/check-in?child_id=1&method=PIN`
   **Expected:** 400 error - "Child already checked in today"

### RBAC Enforcement

**Test:** Parent tries to access other parent's child

```bash
curl -X GET "http://localhost:8000/api/children/999/observations" \
  -H "Authorization: Bearer PARENT_TOKEN"
```

**Expected:** 403 error - "Access denied"

---

## Web Interface Testing

### Login Flow

1. Navigate to http://localhost:8000/login
2. Enter credentials: `admin` / `Admin123!`
3. Should redirect to dashboard

### Dashboard Navigation

- **Admin/Manager:** See pending applications, stats, alerts
- **Supervisor:** See assigned classes, attendance, pending reports
- **Parent:** See children, daily reports, portfolios

### Kindergarten Management

1. Go to http://localhost:8000/kindergartens
2. View list of kindergartens
3. Click on a kindergarten to see details

### Attendance Tracking

1. Go to http://localhost:8000/attendance
2. View today's attendance
3. Check in/out children (manager/supervisor only)

### KPI Dashboard

1. Go to http://localhost:8000/kpi
2. View charts and metrics
3. See governance score with traffic light

---

## Advanced Testing

### Concurrent Operations

Test with 2 browser windows:

1. Window 1: Manager reviews enrollment
2. Window 2: Parent submits same enrollment
   **Expected:** Proper state management, no conflicts

### Performance Testing

```bash
# Apache Bench (if installed)
ab -n 100 -c 10 -H "Authorization: Bearer YOUR_TOKEN" http://localhost:8000/api/manager/dashboard
```

### Data Integrity

1. Create child
2. Create enrollment
3. Assign to class
4. Check database: `sqlite3 kinjo_dev.db "SELECT * FROM enrollment_applications;"`

---

## Common Issues & Solutions

### Issue: Server won't start

**Solution:** Check port 8000 is not in use

```bash
netstat -ano | findstr :8000
```

### Issue: Token expired

**Solution:** Login again to get fresh token

```bash
curl -X POST "http://localhost:8000/api/auth/token" ...
```

### Issue: CORS errors in browser

**Solution:** Server is configured to allow all origins. Check browser console for details.

### Issue: 422 Validation Error

**Solution:** Check request body matches the expected schema. View detailed error message in response.

---

## Quick Reference: All Seeded Data

### Kindergartens

1. **Al Amal Kindergarten** (ID: 1)

   - Location: Abdoun, Amman
   - Status: ACTIVE
   - Operating Hours: 07:00 - 15:00

2. **Al Noor Kindergarten** (ID: 2)
   - Location: Sweifieh, Amman
   - Status: ACTIVE
   - Operating Hours: 07:30 - 14:30

### Users

1. **Admin** (admin / Admin123!)
2. **Manager** (manager1 / Manager123!) - Al Amal
3. **Supervisor** (supervisor1 / Supervisor123!) - Al Amal, Class A
4. **Parent** (parent1@example.com / Parent123!)

### Children

1. **Layla Al-Rashid** (ID: 1)
   - Age: 3 years old
   - Parent: Ahmad Al-Rashid
   - Gender: Female

### Classes

1. **Class A** (ID: 1)
   - Kindergarten: Al Amal
   - Capacity: 20
   - Age Range: 24-48 months (2-4 years)
   - Supervisor: supervisor1

---

## Next Steps After Testing

### If Everything Works ✅

- Document any bugs found
- Test edge cases
- Load test with more data
- Prepare for staging deployment

### If Issues Found ❌

- Document exact steps to reproduce
- Check error logs
- Run tests: `python -m pytest -v`
- Check database state: `sqlite3 kinjo_dev.db`

---

## Stopping the Server

Press `Ctrl+C` in the server terminal window, or:

```bash
# Find process
Get-Process | Where-Object {$_.ProcessName -eq "python"} | Stop-Process
```

---

## Re-Seeding Database

If you need fresh data:

```bash
cd e:\KInjov2
Remove-Item kinjo_dev.db -Force
python seed_data.py
```

Then restart the server.

---

**Happy Testing! 🚀**

For issues or questions, check:

- [PRODUCTION_READY_IMPLEMENTATION.md](PRODUCTION_READY_IMPLEMENTATION.md) - Full implementation details
- [MODULES_AND_WORKFLOWS.md](MODULES_AND_WORKFLOWS.md) - All workflows
- [QUICK_REFERENCE.md](QUICK_REFERENCE.md) - Quick API reference
- Interactive API docs: http://localhost:8000/docs
