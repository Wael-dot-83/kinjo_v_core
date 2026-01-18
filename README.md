<<<<<<< HEAD
# Kinjo_v2
python 
=======
# KinJo - Kindergarten & Childcare Management Platform

Enterprise-grade management platform for kindergartens and childcare facilities in Jordan.

## Overview

KinJo is a comprehensive platform built according to IEEE Software Requirements Specification, implementing all requirements from the SRS document including:

- **11 Core Modules** with full functionality
- **5-Level Validation Framework** (L1 Field, L2 Cross-field, L3 Business rule, L4 Permission, L5 Compliance/Audit)
- **22 User Stories** from Agile Backlog with acceptance criteria
- **Governance-Grade KPI Dashboard** with benchmarking
- **Jordan-Specific Compliance** (PDPL, identity rules, phone formats)

## Features

### Module 1: Identity and Access Management

- Parent self-registration with Jordan identity validation
- Staff account creation (Manager, Supervisor) with RBAC
- Role-based access control with kindergarten scope
- Audit logging for security events

### Module 2: Kindergarten Directory

- Kindergarten profiles with location search
- Service catalog management (extended time, waiting hour, etc.)
- Operating calendar for attendance tracking

### Module 3: Child Enrollment

- Parent enrollment applications
- Manager review and acceptance/rejection
- Age eligibility validation (70 days to 4 years 8 months)
- No duplicate enrollment enforcement

### Module 4: Capacity & Waitlist

- Automated waitlist with priority scoring
- Seat offer engine with expiry timers
- Auto-advance to next candidate on expiry
- Sibling and staff child priority rules

### Module 5: Attendance & Ratio Monitoring

- Digital check-in/out (PIN, QR, Kiosk)
- Real-time staff-child ratio compliance
- Authorized pickup tracking
- Operating calendar-aware calculations

### Module 6: Daily Reports

- Supervisor creates and submits daily reports
- Manager approval workflow
- Automated nap duration calculation
- Parents see only approved reports

### Module 7: Communication (Basic)

- Messaging infrastructure
- Events with RSVP and consent tracking
- Survey support with NPS

### Module 8: Curriculum & Portfolios (Basic)

- Observation tracking by learning domain
- Portfolio management with consent
- Curriculum outcome mapping

### Module 9: Safety & Safeguarding

- Incident tracking with severity levels
- SLA-based follow-up management
- Safeguarding cases with restricted access
- Parent notification tracking

### Module 10: KPI & Governance Reporting

- **Attendance Rate**: (Child-days attended / expected) × 100
- **Incident Rate**: Per 100 child-days
- **Serious Incident Rate**: High/critical only
- **Ratio Compliance**: (Compliant minutes / operating minutes) × 100
- **Incident Follow-up SLA**: % closed within deadline
- **Chronic Absence**: Children missing >10% of days
- **Governance Quality Index (GQI)**: Weighted operational metrics
- **Child Experience Index (CEI)**: Weighted experience metrics
- **Final Governance Score**: 0-100 with RED/AMBER/GREEN bands
- **Monthly Immutable Snapshots**: For audit trail

## Technical Stack

- **Framework**: FastAPI 0.115.0
- **Database**: PostgreSQL with SQLAlchemy 2.0
- **Authentication**: JWT with OAuth2
- **Validation**: Pydantic with custom 5-level framework
- **Testing**: Pytest with comprehensive coverage
- **API Documentation**: Auto-generated OpenAPI/Swagger

## Installation

### Prerequisites

- Python 3.9+
- PostgreSQL 12+
- Redis (optional, for Celery tasks)

### Setup

1. Clone the repository:

```bash
cd KInjov2
```

2. Install dependencies:

```bash
pip install -r requirements.txt
```

3. Create environment file:

```bash
cp .env.example .env
```

4. Edit `.env` with your configuration:

```env
DATABASE_URL=postgresql://user:password@localhost:5432/kinjo_db
SECRET_KEY=your-secret-key-change-in-production
```

5. Initialize database:

```bash
python -c "from database import init_db; init_db()"
```

## Running the Application

### Development Server

```bash
uvicorn main:app --reload --host 0.0.0.0 --port 8000
```

### Production Server

```bash
uvicorn main:app --host 0.0.0.0 --port 8000 --workers 4
```

### Access API Documentation

- Swagger UI: http://localhost:8000/docs
- ReDoc: http://localhost:8000/redoc

## Database Migrations

### Using Alembic for Database Migrations

```bash
# Initialize alembic (already done)
alembic init alembic

# Create a new migration after model changes
alembic revision --autogenerate -m "Description of changes"

# Apply all pending migrations
alembic upgrade head

# Rollback one migration
alembic downgrade -1

# View current migration version
alembic current

# View migration history
alembic history
```

### Migration Best Practices

- Always review auto-generated migrations before applying
- Test migrations on staging before production
- Back up database before applying migrations
- Use meaningful migration message descriptions

## Running Tests

### Quick Test Commands

```bash
# Run all tests
pytest -v

# Run unit tests only
pytest test_api.py -v

# Run integration tests
pytest test_integration.py -v

# Run comprehensive integration tests
pytest tests/test_integration_comprehensive.py -v

# Run security tests
pytest tests/test_security.py -v

# Run with coverage report
pytest --cov=. --cov-report=html --cov-report=term-missing

# Run specific test class
pytest test_integration.py::TestAuthenticationWorkflow -v

# Run tests matching pattern
pytest -k "test_login" -v

# Run tests with detailed output
pytest -v --tb=long

# Run tests in parallel (requires pytest-xdist)
pytest -n auto

# View HTML coverage report
start htmlcov/index.html  # Windows
open htmlcov/index.html   # macOS
xdg-open htmlcov/index.html  # Linux
```

### Test Categories

| Test File                                 | Purpose                 | Count |
| ----------------------------------------- | ----------------------- | ----- |
| `test_api.py`                             | API endpoint tests      | ~50   |
| `test_integration.py`                     | Integration workflows   | ~30   |
| `tests/test_integration_comprehensive.py` | Full workflow tests     | ~40   |
| `tests/test_security.py`                  | Security boundary tests | ~25   |

## API Endpoints

### Authentication

- `POST /token` - Login and get JWT token
- `POST /register/parent` - Parent registration
- `GET /users/me` - Get current user info

### Staff Management

- `POST /staff/create` - Create staff account (Admin/Manager only)

### Enrollment

- `POST /enrollment/apply` - Create enrollment application
- `POST /enrollment/{id}/submit` - Submit for review
- `POST /enrollment/{id}/review` - Manager accepts/rejects

### Waitlist

- `POST /waitlist/{id}/offer` - Generate seat offer
- `POST /waitlist/{id}/accept` - Parent accepts offer

### Attendance

- `POST /attendance/check-in` - Child check-in
- `POST /attendance/check-out` - Child check-out

### Daily Reports

- `POST /daily-reports/create` - Create daily report
- `POST /daily-reports/{id}/submit` - Submit for approval
- `POST /daily-reports/{id}/approve` - Manager approves
- `GET /daily-reports/child/{id}` - Get child's reports

### Safety

- `POST /incidents/create` - Create incident report
- `POST /safeguarding/create` - Create safeguarding case

### KPIs

- `GET /kpi/attendance-rate` - Attendance rate KPI
- `GET /kpi/incident-rate` - Incident rate KPI
- `GET /kpi/ratio-compliance` - Ratio compliance KPI
- `GET /kpi/governance-score` - Full governance score (GQI, CEI, final score, band)
- `POST /kpi/monthly-snapshots` - Generate immutable monthly snapshots

## Validation Framework

The platform implements a 5-level validation hierarchy:

### L1: Field-Level Validation

- Data type, format, required fields
- Jordan phone number format: `^(\+962|00962|0)[0-9]{9}$`
- National ID format: 10 digits
- Email format validation

### L2: Cross-Field Validation

- Identity rules: Jordanian requires National ID, non-Jordanian requires Passport
- Time ordering: check-out after check-in, nap end after nap start
- Date range validation

### L3: Business Rule Validation

- Child age eligibility: 70 days to 56 months (4 years 8 months)
- No double enrollment across kindergartens
- One manager per kindergarten
- No double supervisor assignment
- Class capacity enforcement
- Age band eligibility
- Offer expiry validation
- One daily report per child per date

### L4: Permission Validation

- Kindergarten scope enforcement for staff
- Parent can only access own children
- Manager/Admin role requirements
- Supervisor can only access assigned class
- Cross-tenant access prevention

### L5: Compliance/Audit Validation

- Media consent requirement
- Safeguarding access restriction
- Audit logging for sensitive actions
- Export masking for National IDs
- Elevated audit levels for sensitive data

## Key Business Rules

### Age Eligibility

- Minimum age: 70 days
- Maximum age: 4 years 8 months (56 months)
- Validated at application submission

### Identity Validation

- Jordanian nationality → National ID required (10 digits)
- Non-Jordanian → Passport number required
- Applied to both Parent and Mother identity fields

### Enrollment Rules

- One active enrollment per child across all kindergartens
- Applications go through: Draft → Submitted → Pending Review → Accepted/Rejected
- Accepted applications with no capacity → Waitlisted
- Accepted applications with capacity → Active

### Waitlist Priority

- Application date (earlier = higher priority)
- Sibling already enrolled
- Staff child
- Configurable priority rules

### Staff Assignments

- One active Manager per kindergarten
- One active Supervisor per class
- Staff belong to one kindergarten only
- Replacement supervisors require start/end dates

### Attendance

- One attendance record per child per day
- Check-out must be after check-in
- Only for children with active enrollment

### Daily Reports

- One report per child per date
- Supervisor submits → Manager approves → Parent views
- Parents see only approved reports
- Automatic nap duration calculation

### Governance Scoring

- GQI (0-100): Operational quality metrics
- CEI (0-100): Child experience metrics
- Final Score: Weighted combination
- Bands: GREEN (≥80), AMBER (60-79), RED (<60)
- Regulatory non-compliance overrides green banding

## Security Features

- JWT-based authentication
- Password hashing with bcrypt
- Role-based access control (RBAC)
- Kindergarten scope isolation
- Audit logging for sensitive actions
- Data masking for exports
- Consent-gated media sharing
- Restricted safeguarding access

## Architecture

```
├── main.py              # FastAPI application & API endpoints
├── models.py            # SQLAlchemy database models
├── validators.py        # 5-level validation framework
├── services.py          # Business logic services
├── kpi_service.py       # KPI calculation & reporting
├── auth.py              # Authentication & authorization
├── database.py          # Database configuration
├── config.py            # Configuration management
├── requirements.txt     # Python dependencies
├── test_api.py          # Comprehensive test suite
└── README.md            # This file
```

## Data Model Highlights

- **10 Core Entities**: User, ParentProfile, Child, Kindergarten, Class, EnrollmentApplication, WaitlistEntry, AttendanceLog, DailyReport, Incident
- **15+ Supporting Entities**: SupervisorAssignment, SafeguardingCase, KPISnapshot, GovernanceScore, etc.
- **Full Audit Trail**: AuditLog table with sensitivity levels
- **Temporal Data**: Operating calendar, staff presence logs
- **Immutable Snapshots**: Monthly KPI snapshots for audit compliance

## Compliance

### Jordan-Specific Features

- National ID validation for Jordanian nationals
- Passport validation for non-Jordanian nationals
- Jordan phone number format validation
- Arabic-first UI support (RTL ready)
- Governorate/City/Area location hierarchy

### Privacy & Data Protection (PDPL)

- Consent-gated media sharing
- Data masking for exports (National IDs, Passports)
- Tenant data isolation
- Audit logs for data access
- Right to access/delete (implementation ready)

## KPI Refresh Cadence

- **Real-time**: Ratio compliance alerts
- **Daily**: All KPIs refreshed for operational dashboards
- **Monthly**: Immutable snapshots locked for audit
- **On-demand**: Manual KPI computation via API

## Deployment

### Docker (Recommended)

The project includes optimal Docker configuration for deployment.

1. **Build and Run with Docker Compose** (Easiest):

   ```bash
   docker-compose up --build
   ```

   This will:

   - Build the container using `python:3.9-slim`
   - Start the web service on port 8000
   - Mount a volume for the SQLite database so data persists

2. **Manual Docker Build**:

   ```bash
   docker build -t kinjo-platform .
   docker run -p 8000:8000 -v %cd%/data:/app/data kinjo-platform
   ```

### Local Windows Execution

A convenience script `run_server_dev.bat` is included for Windows users. Double-click it or run from terminal:

```cmd
.\run_server_dev.bat
```

### Database Migration

The Docker container runs database initialization automatically on startup. For manual runs:

```bash
# Initialize DB
python -c "from database import init_db; init_db()"

# Or using Alembic
alembic upgrade head
```

## Future Enhancements

- Frontend application (React/Vue.js with Arabic support)
- Mobile apps for parents (iOS/Android)
- SMS gateway integration for notifications
- Advanced reporting with PDF exports
- Multi-language support (Arabic/English toggle)
- Checklists module (daily/weekly tasks)
- Training and qualification tracking
- Financial management (fees, payments)
- Media library with consent management

## Support

For issues or questions about the implementation, refer to the SRS document:

- `KinJo_IEEE_SRS_and_Agile_Backlog_v1.2_Audit_Enhanced.docx`

## License

Proprietary - All rights reserved

## Version

**v1.0.0** - Full implementation of SRS v1.2

- Date: 13 January 2026
- Based on: IEEE SRS + Agile Backlog
- Modules: 11/11 implemented
- User Stories: 22/22 implemented
- Validation Levels: L1-L5 complete
- KPIs: Full governance dashboard
>>>>>>> 7afd898 (Initial commit)
