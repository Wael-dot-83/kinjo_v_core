# KinJo Developer Workflow

KinJo is a full-stack kindergarten management platform built with FastAPI, SQLAlchemy, Jinja2, and Bootstrap. This guide covers every step from first-time setup to production deployment.

---

## Table of Contents

1. [Prerequisites](#1-prerequisites)
2. [Initial Setup — Local (No Docker)](#2-initial-setup--local-no-docker)
3. [Docker Development (Recommended)](#3-docker-development-recommended)
4. [Environment Variables Reference](#4-environment-variables-reference)
5. [Running the Application](#5-running-the-application)
6. [Database Migrations](#6-database-migrations)
7. [Seeding Data](#7-seeding-data)
8. [Testing](#8-testing)
9. [Linting and Formatting](#9-linting-and-formatting)
10. [Adding a New Module](#10-adding-a-new-module)
11. [Importing Kindergarten Data](#11-importing-kindergarten-data)
12. [Pre-Deployment Checks](#12-pre-deployment-checks)
13. [Production Deployment](#13-production-deployment)
14. [Project Structure Reference](#14-project-structure-reference)

---

## 1. Prerequisites

| Tool | Minimum Version | Notes |
|------|----------------|-------|
| Python | 3.11 | Use pyenv or official installer |
| PostgreSQL | 15 | Optional locally — Docker handles it |
| Redis | 7 | Optional locally — Docker handles it |
| Docker Desktop | Latest | Recommended for PostgreSQL + Redis |
| Git | 2.x | Required |

> **Node.js is not required.** KinJo uses vanilla JavaScript with CDN-hosted libraries (Bootstrap, Chart.js, SweetAlert2). There is no frontend build step.

---

## 2. Initial Setup — Local (No Docker)

Use this path if you have a local PostgreSQL and Redis installation.

```bash
# 1. Clone the repository
git clone <repo-url>
cd kinjo

# 2. Create and activate a virtual environment
python -m venv .venv

# macOS / Linux
source .venv/bin/activate

# Windows (PowerShell)
.venv\Scripts\Activate.ps1

# 3. Install all dependencies
pip install -r requirements.txt -r requirements-dev.txt

# 4. Configure environment
cp .env.example .env
# Edit .env: set DATABASE_URL, SECRET_KEY, REDIS_URL (see Section 4)

# 5. Apply database migrations
alembic upgrade head

# 6. Seed reference data and demo accounts
python scripts/seed_comprehensive.py

# 7. Start the development server
uvicorn main:app --reload --host 0.0.0.0 --port 8000
```

The application is now running at http://localhost:8000.  
API documentation (Swagger UI) is at http://localhost:8000/docs (development only).

---

## 3. Docker Development (Recommended)

Docker Compose manages PostgreSQL, Redis, and the application as a single stack. No local database installation required.

```bash
# 1. Configure environment
cp .env.example .env
# Edit .env: set SECRET_KEY, GOOGLE_API_KEY (if using AI features), and any overrides

# 2. Start all services
docker compose -f docker-compose.dev.yml up -d

# 3. Apply migrations inside the container
docker compose -f docker-compose.dev.yml exec web alembic upgrade head

# 4. Seed data
docker compose -f docker-compose.dev.yml exec web python scripts/seed_comprehensive.py

# 5. View logs
docker compose -f docker-compose.dev.yml logs -f web

# 6. Stop services
docker compose -f docker-compose.dev.yml down
```

**Docker services:**

| Service | Container Name | Port | Health Check |
|---------|---------------|------|--------------|
| PostgreSQL 15 | `kinjo_postgres_dev` | `127.0.0.1:5432` | `pg_isready` |
| Redis 7 | `kinjo_redis_dev` | `127.0.0.1:6379` | `redis-cli ping` |
| FastAPI app | `kinjo_web_dev` | `0.0.0.0:8000` | `GET /health` |

Data is persisted in Docker volume `kinjo_pgdata_dev`. File uploads/attachments are mounted from `./data:/app/data`.

---

## 4. Environment Variables Reference

Copy `.env.example` to `.env` and fill in the values below. All variables are defined in `config.py` using Pydantic Settings.

### Required

| Variable | Example | Description |
|----------|---------|-------------|
| `DATABASE_URL` | `postgresql://kinjo:pass@localhost:5432/kinjo_db` | PostgreSQL connection string. SQLite is supported for local dev but **not** permitted in production. |
| `SECRET_KEY` | `$(openssl rand -hex 32)` | JWT signing key. Must be at least 32 random bytes. Rotate periodically. |
| `REDIS_URL` | `redis://:password@localhost:6379/0` | Redis connection string (caching + Celery broker). |

### Application

| Variable | Default | Description |
|----------|---------|-------------|
| `ENVIRONMENT` | `development` | `development` \| `staging` \| `production`. Production mode enforces PostgreSQL and disables API docs. |
| `DEBUG` | `false` | Enable verbose SQL logging and debug tracebacks. Never `true` in production. |
| `APP_NAME` | `KinJo` | Displayed in page titles and email templates. |
| `API_DOCS_ENABLED` | `true` | Disable Swagger UI in production (`false`). |
| `CORS_ALLOWED_ORIGINS` | `http://localhost:8000` | Comma-separated list of allowed CORS origins. |
| `TRUSTED_HOSTS` | `localhost,127.0.0.1` | Comma-separated trusted host headers. |

### Security

| Variable | Default | Description |
|----------|---------|-------------|
| `ACCESS_TOKEN_EXPIRE_MINUTES` | `30` | JWT token lifetime. |
| `ALGORITHM` | `HS256` | JWT signing algorithm. |
| `SESSION_COOKIE_NAME` | `kinjo_session` | Session cookie identifier. |
| `SESSION_COOKIE_SAMESITE` | `lax` | Cookie SameSite policy (`lax` \| `strict` \| `none`). |
| `CSRF_COOKIE_NAME` | `kinjo_csrf` | CSRF cookie identifier. |

### Rate Limiting (messages per minute by role)

| Variable | Default |
|----------|---------|
| `RATE_LIMIT_MESSAGES_ADMIN` | `120` |
| `RATE_LIMIT_MESSAGES_MANAGER` | `60` |
| `RATE_LIMIT_MESSAGES_SUPERVISOR` | `20` |
| `RATE_LIMIT_MESSAGES_PARENT` | `15` |

### Optional

| Variable | Description |
|----------|-------------|
| `GOOGLE_API_KEY` | Google Gemini API key for AI insights and embeddings. |
| `MFA_TOTP_ISSUER` | Issuer name shown in authenticator apps (default: `KinJo`). |
| `MFA_TICKET_EXPIRE_MINUTES` | MFA ticket expiry (default: `10`). |

---

## 5. Running the Application

### Development server (hot-reload)

```bash
uvicorn main:app --reload --host 0.0.0.0 --port 8000
```

### Background task worker (Celery)

Celery handles scheduled report dispatching, email delivery, and async exports. Start a worker alongside the web server:

```bash
celery -A celery_app worker --loglevel=info
```

For scheduled tasks (daily report digest, cache warm-up):

```bash
celery -A celery_app beat --loglevel=info
```

### Windows (PowerShell helper)

```powershell
.\run local.ps1
```

This script activates the virtual environment and starts both Uvicorn and a Celery worker.

---

## 6. Database Migrations

KinJo uses Alembic for schema versioning. The database URL is read automatically from `config.py` via `alembic/env.py` — no manual configuration needed.

```bash
# Apply all pending migrations (run this after every pull)
alembic upgrade head

# Create a new migration (after modifying models.py)
alembic revision --autogenerate -m "add class_color column"

# View migration history
alembic history --verbose

# Roll back the most recent migration
alembic downgrade -1

# Roll back to a specific revision
alembic downgrade abc123def456
```

### Migration files

All 11 migration files live in `alembic/versions/`:

| Migration | Purpose |
|-----------|---------|
| `db828d82089e` | Initial schema — all core tables |
| `e2b15dd3c429` | MFA columns on `users` |
| `f4b7a9c2d613` | `notification_language` on parent profiles |
| `a0b1c2d3e4f5` | Task column renames |
| `c0d1e2f3a4b5` | Phase 1 DB constraints |
| `a1b2c3d4e5f7` | Messaging + impersonation schema |
| `a9b8c7d6e5f4` | Government reporting views |
| `c1a2b3d4e5f6` | Production hardening (indexes, constraints) |
| `e3f4a5b6c7d8` | Cross-DB compatibility hardening |
| `b1c2d3e4f5a6` | pgvector AI embeddings schema |
| `d2e3f4a5b6c7` | AI infrastructure tables |

> **SQLite note:** `alembic/env.py` uses Alembic's batch mode for SQLite compatibility. This is automatic — no flags needed.

---

## 7. Seeding Data

```bash
# Full seed: all reference data (governorates, classification types) + demo accounts
python scripts/seed_comprehensive.py

# Minimal seed: just the minimum data to log in
python scripts/seed_data.py

# Personal local overrides (gitignored)
python scripts/seed_local.py
```

**Demo accounts** (created by `seed_comprehensive.py`):

| Role | Username | Password |
|------|----------|----------|
| Admin | `admin@kinjo.jo` | `Admin123!` |
| Manager | `manager@kinjo.jo` | `Manager123!` |
| Supervisor | `supervisor@kinjo.jo` | `Supervisor123!` |
| Parent | `parent@kinjo.jo` | `Parent123!` |

> Demo passwords meet the production password policy (≥ 8 chars, uppercase + lowercase + digit + special character).

---

## 8. Testing

KinJo uses pytest with an in-memory SQLite database for tests. No PostgreSQL or Redis installation is required to run the test suite.

### Quick reference

```bash
# Priority-0 gating tests — run before every push
make test-p0

# Full suite (1254 tests, ~14 minutes)
make test-full

# Single test file
pytest tests/test_enrollment_rules.py -v

# All security tests
pytest -m security -v

# All integration tests
pytest -m integration -v

# Skip slow tests
pytest -m "not slow"

# With coverage report
pytest --cov=. --cov-report=html
# Open htmlcov/index.html in a browser
```

### Test markers

Markers are defined in `pytest.ini`:

| Marker | Purpose |
|--------|---------|
| `p0` | High-priority gating tests (block push on failure) |
| `p1` | Medium-priority non-blocking tests |
| `security` | Security and RBAC tests |
| `integration` | Integration tests (cross-module flows) |
| `slow` | Tests that take > 5 seconds |

### Test infrastructure

- **Test database:** In-memory SQLite via `StaticPool` (configured in `conftest.py`)
- **HTTP client:** Starlette `TestClient` wrapping the FastAPI app
- **Fixtures:** All shared fixtures live in `conftest.py` (root level)
  - `test_db` — fresh SQLAlchemy session per test
  - `client` — authenticated/unauthenticated test client
  - `parent_user`, `supervisor_user`, `manager_user`, `admin_user` — seeded role fixtures
  - `auth_headers_parent`, `auth_headers_supervisor`, etc. — pre-built Authorization headers
  - `sample_kindergarten`, `sample_class` — linked domain fixtures

### Test file conventions

```
tests/
├── api/                      # API-layer tests (analytics, exports)
│   ├── test_p0_analytics_kpi.py
│   └── test_p1_analytics_export.py
├── test_enrollment_rules.py  # Domain: enrollment workflow
├── test_parent_module.py     # Domain: parent endpoints
├── test_admin_security.py    # Security: RBAC, auth bypass
├── test_route_registration.py # Architecture: 0 duplicate routes
└── ...
```

---

## 9. Linting and Formatting

KinJo uses **Ruff** for both linting and formatting. Configuration is in `pyproject.toml`.

```bash
# Check for lint errors
make lint

# Strict lint on critical modules
make lint-py-strict

# Auto-format all Python files
make fmt

# Pre-push gate: lint + strict lint + priority-0 tests
make check

# Full CI equivalent: lint + format check + full test suite
make ci-local

# Remove caches and build artifacts
make clean
```

### Ruff configuration (from `pyproject.toml`)

```toml
[tool.ruff]
line-length = 120
target-version = "py311"

[tool.ruff.lint]
select = ["E722", "F821"]   # bare except, undefined name
```

Line length: **120 characters**. Target: **Python 3.11**.

---

## 10. Adding a New Module

Follow these steps to add a new feature domain (e.g., a `portfolio` module):

### Step 1 — Create the API endpoint file

```python
# api/portfolio.py
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy.orm import Session
import models
from database import get_db
from dependencies import get_current_user

router = APIRouter(tags=["Portfolio"])

class PortfolioEntryCreate(BaseModel):
    child_id: int
    title: str
    content: str

@router.get("/portfolio/{child_id}")
def get_portfolio(
    child_id: int,
    current_user: models.User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    # Enforce RBAC and kindergarten scoping here
    ...
    return {"entries": []}
```

### Step 2 — Register the router in `main.py`

```python
# main.py
from api.portfolio import router as portfolio_router
app.include_router(portfolio_router, prefix="/api", tags=["Portfolio"])
```

> Register your new router **before** the `missing_endpoints` router (which is always last).

### Step 3 — Create the Jinja2 template

```
templates/portfolio/
├── list.html     # extends base.html
└── view.html     # extends base.html
```

Every template must extend `base.html` and use `{% include %}` for shared components:

```jinja2
{% extends "base.html" %}
{% block content %}
{% include 'components/navbar.html' %}
{% include 'components/sidebar.html' %}
<!-- page content -->
{% endblock %}
```

### Step 4 — Add frontend routes in `frontend.py`

```python
# frontend.py
@router.get("/portfolio/{child_id}", response_class=HTMLResponse)
def portfolio_view(child_id: int, request: Request, ...):
    return templates.TemplateResponse("portfolio/view.html", {"request": request, ...})
```

### Step 5 — Write tests

```python
# tests/test_portfolio.py
def test_get_portfolio_returns_200(client, auth_headers_supervisor, sample_kindergarten):
    resp = client.get(f"/api/portfolio/{child_id}", headers=auth_headers_supervisor)
    assert resp.status_code == 200
```

### Step 6 — Generate a migration (if new DB columns)

```bash
# Edit models.py first, then:
alembic revision --autogenerate -m "add portfolio entries table"
alembic upgrade head
```

### Step 7 — Verify no duplicate routes

```bash
pytest tests/test_route_registration.py -v
# Must pass with 0 duplicates
```

---

## 11. Importing Kindergarten Data

```bash
# Import from Excel file
python scripts/import_kindergartens_from_excel.py data/kindergartens.xlsx

# Import from CSV/JSON (legacy script)
python scripts/import_kindergartens.py
```

The import service (`kindergarten_import_service.py`) handles deduplication, Arabic name normalization, and validation. Staging files are in `static/imports/`.

---

## 12. Pre-Deployment Checks

Run the preflight script before deploying to any environment:

```bash
python scripts/preflight_hosting.py
```

This script validates:
- All required environment variables are set
- Database is reachable and all migrations are applied
- Redis is reachable
- File write permissions for `data/` directory
- Production-specific constraints (PostgreSQL enforced, API docs disabled)

---

## 13. Production Deployment

```bash
# 1. Build and start production stack
docker compose -f docker-compose.prod.yml build
docker compose -f docker-compose.prod.yml up -d

# 2. Apply migrations
docker compose -f docker-compose.prod.yml exec web alembic upgrade head

# 3. (First deploy only) Seed reference data
docker compose -f docker-compose.prod.yml exec web python scripts/seed_comprehensive.py

# 4. Verify health
curl https://your-domain.com/health
```

**Production requirements:**

| Setting | Required Value |
|---------|---------------|
| `ENVIRONMENT` | `production` |
| `DATABASE_URL` | PostgreSQL (not SQLite) |
| `DEBUG` | `false` |
| `API_DOCS_ENABLED` | `false` |
| `SECRET_KEY` | ≥ 32 random bytes, rotated periodically |
| `CORS_ALLOWED_ORIGINS` | Explicit domain list (no wildcards) |

The app is served by **supervisord** inside the container, managing Uvicorn workers and Celery. Health endpoint: `GET /health` returns `{"status": "ok"}`.

---

## 14. Project Structure Reference

```
kinjo/
├── main.py                      # FastAPI app init, middleware, router registration
├── config.py                    # All settings (Pydantic BaseSettings)
├── database.py                  # SQLAlchemy engine, session, Base
├── models.py                    # All ORM models and enums
├── auth.py                      # Password hashing, JWT, login logic
├── dependencies.py              # FastAPI dependencies (get_current_user)
├── rbac.py                      # Role guards and permission helpers
├── validators.py                # Shared validation utilities, audit logging
├── i18n.py                      # Localization / gettext helper
├── frontend.py                  # Jinja2 setup, HTML route handlers
│
├── api/                         # REST endpoints by domain
│   ├── enrollment.py
│   ├── parent.py
│   ├── users.py
│   ├── children.py
│   ├── classes.py
│   ├── kindergartens.py
│   ├── daily_reports_routes.py
│   ├── attendance_routes.py
│   ├── absence_requests.py
│   ├── supervisor.py
│   ├── manager.py
│   ├── portfolio.py
│   ├── tasks.py
│   └── ...
│
├── routers/                     # Role-scoped APIRouter groupings
│   ├── manager.py               # Manager-scoped routes (prefix: /api/manager)
│   ├── supervisor.py            # Supervisor-scoped routes (prefix: /api/supervisor)
│   ├── messaging.py             # Real-time messaging
│   ├── admin_impersonation.py   # Admin impersonation flow
│   └── ai.py                   # AI endpoint integrations
│
├── templates/                   # Jinja2 server-rendered templates
│   ├── base.html               # Master layout
│   ├── components/             # Reusable partials (navbar, sidebar, modals)
│   ├── admin/                  # Admin role pages
│   ├── manager/                # Manager role pages
│   ├── supervisor/             # Supervisor role pages
│   ├── parent/                 # Parent role pages
│   ├── enrollment/             # Enrollment workflow
│   ├── attendance/             # Attendance tracking
│   ├── communication/          # Messaging, events, surveys
│   ├── auth/                   # Login, register, MFA, password reset
│   ├── 403.html, 404.html      # Custom error pages
│   └── ...
│
├── static/                      # Frontend assets
│   ├── css/
│   │   ├── kinjo.css           # Core design system
│   │   ├── rtl.css             # Arabic RTL overrides
│   │   └── admin_design_system.css
│   ├── js/
│   │   ├── admin_i18n.js       # appText() i18n helper
│   │   ├── admin_analytics.js
│   │   └── ...
│   └── i18n/
│       ├── ar.json, en.json    # Core translations
│       ├── admin_ar.json, admin_en.json
│       └── app_ar.json, app_en.json
│
├── alembic/                     # Database migration scripts
│   ├── env.py
│   └── versions/               # 11 migration files
│
├── tests/                       # pytest test suite (1254 tests)
│   ├── conftest.py             # Fixtures (moved to root conftest.py)
│   └── test_*.py
│
├── middleware/                  # Request/response middleware
│   ├── auth.py                 # JWT/cookie extraction
│   ├── csrf.py                 # CSRF protection
│   └── security.py             # Security headers, exception handler
│
├── scripts/                     # Utility and one-off scripts
│   ├── seed_comprehensive.py
│   ├── seed_data.py
│   ├── import_kindergartens_from_excel.py
│   └── preflight_hosting.py
│
├── *_service.py                 # Service layer (business logic)
│   # kpi_service.py, report_service.py, analytics_service.py,
│   # communication_service.py, notification_service.py, etc.
│
├── requirements.txt             # Production dependencies
├── requirements-dev.txt         # Dev/test dependencies
├── pyproject.toml               # Ruff config, project metadata
├── Makefile                     # lint, fmt, test, ci targets
├── pytest.ini                   # Test configuration
├── conftest.py                  # Root test fixtures
├── alembic.ini                  # Alembic configuration
├── docker-compose.dev.yml       # Development Docker Compose
├── docker-compose.prod.yml      # Production Docker Compose
├── Dockerfile                   # Multi-stage container build
└── .env.example                 # Environment variable template
```
