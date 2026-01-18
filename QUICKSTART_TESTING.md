# KinJo Platform - Quick Start Testing Guide

## 🚀 Server Status

- **URL**: http://127.0.0.1:8000
- **API Docs**: http://127.0.0.1:8000/docs
- **Health Check**: http://127.0.0.1:8000/health

## 👥 Test User Credentials

| Role           | Username              | Password         | Kindergarten         |
| -------------- | --------------------- | ---------------- | -------------------- |
| **Admin**      | `admin`               | `Admin123!`      | All (System-wide)    |
| **Manager**    | `manager1`            | `Manager123!`    | Al Amal Kindergarten |
| **Supervisor** | `supervisor1`         | `Supervisor123!` | Al Amal Kindergarten |
| **Parent**     | `parent1@example.com` | `Parent123!`     | -                    |

## 🔐 How to Login (via API Docs)

1. Open http://127.0.0.1:8000/docs
2. Click **"Authorize"** button (top right)
3. Enter username and password
4. Click **"Authorize"**
5. Now all endpoints will use your authentication

## 📋 Test Workflows

### Workflow 1: Manager Creates Enrollment

1. Login as `manager1`
2. POST `/enrollment/submit?child_id=1&kindergarten_id=1&source=manager`
3. POST `/enrollment/{id}/accept`
4. POST `/enrollment/{id}/assign-class?class_id=1`

### Workflow 2: Supervisor Daily Operations

1. Login as `supervisor1`
2. GET `/supervisor/dashboard` - View dashboard
3. GET `/supervisor/my-classes` - View assigned classes
4. POST `/attendance/check-in?child_id=1&method=pin` - Check in child
5. POST `/supervisor/observations/record?child_id=1&domain=social_emotional&observation_text=Test` - Record observation
6. POST `/daily-reports/create` - Create daily report

### Workflow 3: Parent View

1. Login as `parent1@example.com`
2. GET `/parent/my-children` - View children
3. GET `/daily-reports/child/{child_id}` - View daily reports (after approval)

## 🏫 Seeded Data

### Kindergartens

- **Al Amal Kindergarten** (ID: 1) - Abdoun, Amman
- **Al Noor Kindergarten** (ID: 2) - Sweifieh, Amman

### Classes

- **Class A** (ID: 1) - Capacity: 20, Ages: 24-48 months

### Children

- **Layla Al-Rashid** (ID: 1) - 3 years old, Parent: Ahmad

### Supervisor Assignments

- `supervisor1` → Class A (Primary)

## 🔧 Terminal Commands

```powershell
# Start server
cd E:\KInjov2
python -m uvicorn main:app --host 127.0.0.1 --port 8000

# Start with auto-reload (development)
python -m uvicorn main:app --host 127.0.0.1 --port 8000 --reload

# Run tests
$env:TESTING="true"; python -m pytest test_api.py test_integration.py -v

# Re-seed database (clears and re-creates data)
Remove-Item kinjo.db -Force; python seed_data.py
```

## 🧪 Sample API Calls (PowerShell)

```powershell
# Login and get token
$body = @{username='manager1'; password='Manager123!'}
$token = (Invoke-RestMethod -Uri "http://127.0.0.1:8000/token" -Method POST -Body $body -ContentType "application/x-www-form-urlencoded").access_token
$headers = @{Authorization="Bearer $token"}

# Health check
Invoke-RestMethod -Uri "http://127.0.0.1:8000/health"

# Supervisor dashboard
Invoke-RestMethod -Uri "http://127.0.0.1:8000/supervisor/dashboard" -Headers $headers

# Create enrollment
Invoke-RestMethod -Uri "http://127.0.0.1:8000/enrollment/submit?child_id=1&kindergarten_id=1&source=manager" -Method POST -Headers $headers

# Check-in child
Invoke-RestMethod -Uri "http://127.0.0.1:8000/attendance/check-in?child_id=1&method=pin&dropped_by_name=Mother" -Method POST -Headers $headers
```

## ⚠️ Notes

- **Rate Limiting**: In production mode, too many failed logins will trigger a 25-minute block
- **Security Middleware**: Enabled by default. Set `$env:SECURITY_ENABLED="false"` to disable for testing
- **Database**: SQLite file at `kinjo.db`. Delete to reset all data.

## 📊 Available Endpoints Summary

| Category      | Count | Key Endpoints                                         |
| ------------- | ----- | ----------------------------------------------------- |
| Auth          | 2     | `/token`, `/users/me`                                 |
| Kindergarten  | 4     | `/kindergartens`, `/kindergartens/{id}`               |
| Enrollment    | 6     | `/enrollment/submit`, `/enrollment/{id}/accept`       |
| Attendance    | 3     | `/attendance/check-in`, `/attendance/check-out`       |
| Daily Reports | 4     | `/daily-reports/create`, `/daily-reports/{id}/submit` |
| Supervisor    | 8     | `/supervisor/dashboard`, `/supervisor/assign`         |
| KPI           | 3     | `/kpi/snapshot`, `/kpi/kindergarten/{id}`             |
| Parent        | 2     | `/parent/my-children`, `/parent/children/{id}`        |

---

**Happy Testing! 🎉**
