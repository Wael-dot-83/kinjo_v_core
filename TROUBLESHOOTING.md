# KInJo Platform - Quick Troubleshooting Guide

## 🚀 Quick Start

### Start the Server

```bash
cd e:\KInjov2
python start_server.py
```

Server will run on: `http://127.0.0.1:8000`

### Login

- URL: `http://127.0.0.1:8000/login`
- Username: `admin`
- Password: `Admin123!`

---

## ❌ Common Problems & Solutions

### Problem 1: "Connection Refused" or Server Not Responding

**Symptoms:**

- Can't access http://127.0.0.1:8000
- Message: "Failed to connect" or "Connection refused"

**Solutions:**

1. **Check if server is running:**

   ```bash
   # Open another terminal and check:
   Get-Process | Where-Object {$_.Name -like "*python*"} | Select Name, Id
   ```

2. **Port is already in use:**

   ```bash
   # Find process using port 8000:
   netstat -ano | findstr :8000

   # Kill the process if needed:
   taskkill /PID <PID> /F
   ```

3. **Restart the server:**
   ```bash
   # Press Ctrl+C in server terminal to stop
   # Then restart:
   python start_server.py
   ```

---

### Problem 2: Login Fails with "فشل تسجيل الدخول" (Login Failed)

**Symptoms:**

- Login page shows error message in Arabic
- Credentials aren't accepted
- Error appears after clicking login

**Solutions:**

1. **Verify credentials:**

   - Username: `admin` (not email)
   - Password: `Admin123!`
   - Make sure CAPS LOCK is off

2. **Check server logs:**

   - Look for error messages in server terminal
   - Common error: bcrypt compatibility issue (already fixed)

3. **Clear browser cache:**

   - Clear localStorage: Press F12 → Application → Local Storage → Clear All
   - Clear cookies
   - Refresh page

4. **Check database:**

   ```bash
   # Check if admin user exists in database
   python -c "from database import SessionLocal; from models import User; db = SessionLocal(); user = db.query(User).filter(User.username=='admin').first(); print('Admin exists:', user is not None)"
   ```

5. **Recreate seed data:**
   ```bash
   # Stop server (Ctrl+C)
   # Delete database:
   del kinjo.db
   # Restart server to recreate database:
   python start_server.py
   # Reseed data:
   python seed_data.py
   ```

---

### Problem 3: Dashboard Shows "--" Instead of Numbers

**Symptoms:**

- Dashboard loads but all stats show "--"
- No data displayed in cards
- Charts are empty

**Solutions:**

1. **Check if API calls are working:**

   ```bash
   # Open browser console (F12) and check Network tab
   # Look for GET requests to /api/* endpoints
   # They should return 200 status with JSON data
   ```

2. **Verify API endpoints are callable:**

   ```bash
   # Get auth token first:
   $token = (Invoke-WebRequest -Uri "http://127.0.0.1:8000/token" `
     -Method POST -Body "username=admin&password=Admin123!" `
     -ContentType "application/x-www-form-urlencoded").Content | ConvertFrom-Json

   # Test API endpoint:
   $headers = @{"Authorization" = "Bearer $($token.access_token)"}
   Invoke-WebRequest -Uri "http://127.0.0.1:8000/api/users/me" -Headers $headers
   ```

3. **Check server logs for errors:**

   - Look for 404 or 500 errors in server terminal
   - Verify endpoint paths match exactly

4. **Reload browser:**
   - Hard refresh: Ctrl+Shift+R (Windows) or Cmd+Shift+R (Mac)
   - Clear browser cache before refreshing

---

### Problem 4: "404 Not Found" Errors

**Symptoms:**

- Browser console shows 404 errors for API calls
- Specific endpoints not found
- Examples: `/api/users/me`, `/api/classes`

**Solutions:**

1. **Verify endpoint URL:**

   - Check that URL includes `/api` prefix
   - Example correct path: `/api/users/me`
   - Example wrong path: `/users/me`

2. **Check method type:**

   - Some endpoints require POST (not GET)
   - Check `missing_endpoints.py` for correct method
   - Example: `/api/attendance/check-in` is POST, not GET

3. **Verify authentication:**

   ```bash
   # Endpoint may require valid JWT token in Authorization header
   # Without valid token, you get 401 Unauthorized, not 404
   ```

4. **Check if backend supports endpoint:**
   - Search `missing_endpoints.py` for the endpoint
   - Verify it's decorated with `@router.get()` or `@router.post()`

---

### Problem 5: "TypeError: Cannot read property 'role' of undefined"

**Symptoms:**

- Browser console shows JavaScript errors
- Dashboard doesn't load
- Function errors

**Solutions:**

1. **Check if user is authenticated:**

   ```bash
   # Check localStorage in browser console:
   localStorage.getItem('token')
   # Should show a JWT token, not null
   ```

2. **Verify user object format:**

   ```javascript
   // In browser console:
   const api = window.api; // or however it's accessed
   api.getCurrentUser().then((user) => console.log(user));
   ```

3. **Clear and re-login:**
   - Clear localStorage: `localStorage.clear()`
   - Refresh page
   - Login again with valid credentials

---

### Problem 6: Server Crashes or Shows Errors

**Symptoms:**

- Server terminal shows Python errors
- Red error messages in logs
- Server stops responding

**Solutions:**

1. **Check Python version:**

   ```bash
   python --version
   # Should be 3.9 or higher
   ```

2. **Check dependencies:**

   ```bash
   pip list | findstr fastapi
   pip list | findstr sqlalchemy
   # Verify all required packages are installed
   ```

3. **Reinstall dependencies:**

   ```bash
   pip install -r requirements.txt --force-reinstall
   ```

4. **Check for database corruption:**

   ```bash
   # Delete database and restart:
   del kinjo.db
   python start_server.py
   ```

5. **View full error details:**
   ```bash
   # Run with verbose logging:
   python -u start_server.py 2>&1 | tee server.log
   # Check server.log file for full error traces
   ```

---

### Problem 7: "Module not found" or Import Errors

**Symptoms:**

- Python ImportError when starting server
- Message like: "No module named 'fastapi'"
- Server won't start

**Solutions:**

1. **Activate virtual environment (if using one):**

   ```bash
   # For venv:
   venv\Scripts\activate

   # For conda:
   conda activate kinjo
   ```

2. **Install missing package:**

   ```bash
   pip install <package-name>
   # Example: pip install fastapi
   ```

3. **Reinstall all dependencies:**

   ```bash
   pip install -r requirements.txt
   ```

4. **Check Python path:**
   ```bash
   python -c "import sys; print(sys.executable)"
   # Make sure this points to correct Python environment
   ```

---

### Problem 8: Database Lock or "Database is locked" Error

**Symptoms:**

- Error message: "database is locked"
- Can't write to database
- Operations hang or timeout

**Solutions:**

1. **Close all database connections:**

   - Stop the server (Ctrl+C)
   - Wait 5 seconds
   - Restart server

2. **Check for multiple server instances:**

   ```bash
   Get-Process | Where-Object {$_.Name -eq "python"}
   # Should only see one instance
   # Kill others if needed: taskkill /PID <PID> /F
   ```

3. **Delete database and reseed:**
   ```bash
   del kinjo.db
   python start_server.py
   python seed_data.py
   ```

---

## ✅ Health Checks

### Check Server Status

```bash
curl http://127.0.0.1:8000/health
# Response should be JSON: {"status":"ok"}
```

### Check API Authentication

```bash
curl -X POST http://127.0.0.1:8000/token \
  -H "Content-Type: application/x-www-form-urlencoded" \
  -d "username=admin&password=Admin123!"
# Response should include: {"access_token": "..."}
```

### Check Database Connection

```bash
# Python code:
python -c "
from database import engine
from sqlalchemy import text
with engine.connect() as conn:
    result = conn.execute(text('SELECT 1'))
    print('Database OK:', result.scalar())
"
```

---

## 🔧 Manual Testing Commands

### Test User Login

```bash
# Get access token
$response = Invoke-WebRequest -Uri "http://127.0.0.1:8000/token" `
  -Method POST `
  -Body "username=admin&password=Admin123!" `
  -ContentType "application/x-www-form-urlencoded"

$token = ($response.Content | ConvertFrom-Json).access_token
Write-Host "Token: $token"
```

### Test API Endpoint

```bash
# Get current user info
$headers = @{"Authorization" = "Bearer $token"}
$response = Invoke-WebRequest -Uri "http://127.0.0.1:8000/api/users/me" `
  -Headers $headers -Method GET
$response.Content | ConvertFrom-Json | Format-List
```

### Test Manager Dashboard

```bash
# Get dashboard data
$response = Invoke-WebRequest -Uri "http://127.0.0.1:8000/api/manager/dashboard" `
  -Headers $headers -Method GET
$response.Content | ConvertFrom-Json | Format-List
```

---

## 📊 Checking Database Data

### View Users

```bash
python -c "
from database import SessionLocal
from models import User
db = SessionLocal()
users = db.query(User).all()
for u in users:
    print(f'{u.username} - {u.role} - {u.status}')
db.close()
"
```

### View Classes

```bash
python -c "
from database import SessionLocal
from models import Class as ClassModel
db = SessionLocal()
classes = db.query(ClassModel).all()
for c in classes:
    print(f'{c.name} - Capacity: {c.capacity}')
db.close()
"
```

### View Children

```bash
python -c "
from database import SessionLocal
from models import Child
db = SessionLocal()
children = db.query(Child).all()
print(f'Total children: {len(children)}')
for c in children[:5]:  # Show first 5
    print(f'  {c.first_name} {c.last_name}')
db.close()
"
```

---

## 🆘 Getting Help

### Check These Files First

1. **SYSTEM_STATUS_REPORT.md** - Overall system status
2. **FIXES_APPLIED.md** - What has been fixed
3. **README.md** - General documentation
4. **MODULES_AND_WORKFLOWS.md** - Feature descriptions

### Collect Information for Debugging

When reporting issues, gather:

1. Full error message (screenshot if possible)
2. Server console output (copy full error trace)
3. Browser console output (F12 → Console tab)
4. Steps to reproduce the issue
5. Which user role you're testing with

### Check Server Logs

```bash
# Check recent errors:
python start_server.py 2>&1 | tail -100
# Or save to file and review:
python start_server.py 2>&1 > server.log
```

---

## 🚨 Emergency Reset

If everything is broken and you want to start fresh:

```bash
# Stop server (Ctrl+C in server terminal)

# Delete database
del kinjo.db

# Delete any temp files
del tmpclaude-*

# Reinstall dependencies
pip install -r requirements.txt --force-reinstall

# Start fresh
python start_server.py

# Seed data
python seed_data.py

# Test login
# Go to http://127.0.0.1:8000/login
# Use admin / Admin123!
```

---

## ✨ Tips for Success

1. **Always check server logs first** - Most errors are logged
2. **Use browser console (F12)** - JavaScript errors appear there
3. **Test with curl before UI** - Isolates API vs frontend issues
4. **Clear cache frequently** - Old JS/CSS can cause issues
5. **Check port conflicts** - Only one server can use port 8000
6. **Verify credentials** - Copy/paste from docs to avoid typos
7. **Read error messages carefully** - They usually tell you what's wrong

---

_Last Updated: 2026-01-16_
_Version: 1.0 - Quick Troubleshooting Guide_
