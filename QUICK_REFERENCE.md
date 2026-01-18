# KinJo - Quick Reference Guide

## Quick Start (3 Steps)

```bash
# 1. Install dependencies
pip install -r requirements.txt

# 2. Run quick start script
python quickstart.py

# 3. Access API
# http://localhost:8000/docs
```

## Test Credentials (After Seed)

```
Admin:      admin / Admin123!
Manager:    manager1 / Manager123!
Supervisor: supervisor1 / Supervisor123!
Parent:     parent1@example.com / Parent123!
```

## Common API Workflows

### 1. Parent Registration & Login

```bash
# Register
curl -X POST http://localhost:8000/register/parent \
  -H "Content-Type: application/json" \
  -d '{
    "first_name": "Ahmad",
    "last_name": "Al-Rashid",
    "phone_number": "+962791234567",
    "gender": "male",
    "nationality": "Jordanian",
    "national_id": "1234567890",
    "home_governorate": "Amman",
    "home_city": "Amman",
    "home_area": "Abdoun",
    "home_address_line": "Street 123",
    "correspondence_preference": true,
    "email": "ahmad@example.com",
    "password": "SecurePass123!"
  }'

# Login
curl -X POST http://localhost:8000/token \
  -H "Content-Type: application/x-www-form-urlencoded" \
  -d "username=ahmad@example.com&password=SecurePass123!"

# Response: { "access_token": "eyJ...", "token_type": "bearer" }
```

### 2. Create Enrollment Application

```bash
# Use token from login
curl -X POST http://localhost:8000/enrollment/apply \
  -H "Authorization: Bearer YOUR_TOKEN" \
  -H "Content-Type: application/json" \
  -d '{
    "first_name": "Layla",
    "last_name": "Al-Rashid",
    "gender": "female",
    "date_of_birth": "2021-06-15",
    "father_name": "Ahmad Al-Rashid",
    "mother_first_name": "Fatima",
    "mother_last_name": "Hassan",
    "mother_nationality": "Jordanian",
    "mother_national_id": "0987654321",
    "kindergarten_id": 1
  }'
```

### 3. Manager Review Enrollment

```bash
# Login as manager
curl -X POST http://localhost:8000/token \
  -H "Content-Type: application/x-www-form-urlencoded" \
  -d "username=manager1&password=Manager123!"

# Review application
curl -X POST http://localhost:8000/enrollment/1/review?decision=accept \
  -H "Authorization: Bearer MANAGER_TOKEN"
```

### 4. Check-in Child

```bash
curl -X POST "http://localhost:8000/attendance/check-in?child_id=1&method=pin&dropped_by_name=Father" \
  -H "Authorization: Bearer YOUR_TOKEN"
```

### 5. Create Daily Report

```bash
curl -X POST http://localhost:8000/daily-reports/create \
  -H "Authorization: Bearer SUPERVISOR_TOKEN" \
  -H "Content-Type: application/json" \
  -d '{
    "child_id": 1,
    "date": "2026-01-13",
    "arrival_time": "07:30",
    "leave_time": "14:00",
    "breakfast": true,
    "lunch": true,
    "nap_start": "12:00",
    "nap_end": "13:30",
    "activities": "Outdoor play, story time",
    "notes": "Great day!"
  }'
```

### 6. Get KPIs

```bash
# Attendance Rate
curl "http://localhost:8000/kpi/attendance-rate?kindergarten_id=1&period_start=2026-01-01&period_end=2026-01-31" \
  -H "Authorization: Bearer MANAGER_TOKEN"

# Governance Score
curl "http://localhost:8000/kpi/governance-score?kindergarten_id=1&period_start=2026-01-01&period_end=2026-01-31" \
  -H "Authorization: Bearer ADMIN_TOKEN"
```

## Validation Reference

### Jordan Phone Format
```
Valid:   +962791234567, 00962791234567, 0791234567
Invalid: 791234567, +962-79-123-4567
```

### National ID
```
Valid:   1234567890 (10 digits)
Invalid: 123456789 (too short)
```

### Child Age Eligibility
```
Minimum: 70 days
Maximum: 56 months (4 years 8 months)
```

## Database Models Quick Ref

### User Roles
- `ADMIN` - Platform administrator
- `MANAGER` - Kindergarten manager (one per kindergarten)
- `SUPERVISOR` - Class supervisor
- `PARENT` - Parent/guardian

### Enrollment Status Flow
```
DRAFT → SUBMITTED → PENDING_REVIEW → ACCEPTED/REJECTED
                                    ↓
                              WAITLISTED (if no capacity)
                                    ↓
                                 ACTIVE (when seat available)
```

### Daily Report Status Flow
```
DRAFT → SUBMITTED → APPROVED/RETURNED
```

## Common Validation Errors

### "National ID is required for Jordanian nationality"
- **Cause**: Registering with nationality="Jordanian" without national_id
- **Fix**: Provide national_id field with 10-digit ID

### "Child must be at least 70 days old"
- **Cause**: Child date_of_birth is too recent
- **Fix**: Ensure child is at least 70 days old

### "Child already has an active enrollment at another kindergarten"
- **Cause**: Attempting to enroll in 2+ kindergartens simultaneously
- **Fix**: Withdraw from other kindergarten first

### "Kindergarten already has an active Manager"
- **Cause**: Trying to assign second manager to kindergarten
- **Fix**: Deactivate existing manager first

## Environment Variables

```env
# Required
DATABASE_URL=postgresql://user:pass@localhost:5432/kinjo_db
SECRET_KEY=your-secret-key-min-32-chars

# Optional
ACCESS_TOKEN_EXPIRE_MINUTES=30
MIN_CHILD_AGE_DAYS=70
MAX_CHILD_AGE_MONTHS=56
WAITLIST_OFFER_EXPIRY_HOURS=48
```

## Testing

```bash
# Run all tests
pytest test_api.py -v

# Run specific test
pytest test_api.py::test_parent_registration_valid -v

# With coverage
pytest test_api.py --cov=. --cov-report=html
```

## Database Commands

```python
# Initialize database
from database import init_db
init_db()

# Seed with sample data
from seed_data import seed_database
seed_database()

# Direct DB access
from database import SessionLocal
db = SessionLocal()
kindergartens = db.query(models.Kindergarten).all()
```

## Common Python Snippets

### Create Admin User
```python
from database import SessionLocal
from auth import get_password_hash
import models

db = SessionLocal()
admin = models.User(
    username="admin",
    email="admin@kinjo.jo",
    hashed_password=get_password_hash("SecurePassword"),
    role=models.UserRole.ADMIN,
    status=models.UserStatus.ACTIVE
)
db.add(admin)
db.commit()
```

### Calculate Age in Months
```python
from datetime import date

def age_in_months(dob: date) -> int:
    today = date.today()
    months = (today.year - dob.year) * 12 + today.month - dob.month
    if today.day < dob.day:
        months -= 1
    return months
```

### Check Age Eligibility
```python
from validators import validate_child_age_eligibility
from datetime import date

dob = date(2021, 6, 15)
try:
    validate_child_age_eligibility(dob)
    print("✓ Eligible")
except ValidationError as e:
    print(f"✗ Not eligible: {e.message}")
```

## File Locations

```
Configuration:  config.py, .env
Models:         models.py
Validation:     validators.py
Services:       services.py, kpi_service.py, auth.py
API:            main.py
Tests:          test_api.py
Database:       database.py
Seed Data:      seed_data.py
```

## API Documentation

- **Swagger UI**: http://localhost:8000/docs
- **ReDoc**: http://localhost:8000/redoc
- **OpenAPI JSON**: http://localhost:8000/openapi.json

## Troubleshooting

### "Could not validate credentials"
- Token expired (default 30 min) - login again
- Invalid token - check Authorization header format: `Bearer YOUR_TOKEN`

### "User does not have permission to access this kindergarten"
- Manager/Supervisor trying to access different kindergarten
- Check user.kindergarten_id matches target kindergarten

### "Database connection error"
- Check DATABASE_URL in .env
- Ensure PostgreSQL is running
- Verify database exists

### "Module not found"
- Run: `pip install -r requirements.txt`
- Check virtual environment is activated

## Performance Tips

- Use database indexes (already implemented on key fields)
- Batch KPI calculations for multiple kindergartens
- Cache frequently accessed KPIs (Redis integration ready)
- Use pagination for large result sets
- Consider Celery for async KPI computation

## Next Steps

1. **Frontend**: Build React/Vue.js app with Arabic RTL support
2. **Mobile**: Develop iOS/Android apps for parents
3. **Notifications**: Integrate SMS/email gateway
4. **Reports**: Add PDF export functionality
5. **Analytics**: Build governance dashboard UI
6. **i18n**: Complete Arabic/English localization

## Support Resources

- SRS Document: `KinJo_IEEE_SRS_and_Agile_Backlog_v1.2_Audit_Enhanced.docx`
- Full README: `README.md`
- Implementation Summary: `IMPLEMENTATION_SUMMARY.md`
- API Docs: http://localhost:8000/docs

---

**Version**: v1.0.0
**Last Updated**: 13 January 2026
