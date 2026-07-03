# KinJo — Team Handover Package
**Cleaned & Ready for Team — 2026-05-24**

---

## 1. Package Summary

| Metric | Value |
|---|---|
| Original workspace size | 580 MB |
| After cleanup | ~39 MB |
| Saved | ~541 MB |
| Git commit (HEAD) | `8999543` |
| Tests passing | **1362 / 1362** |
| Secrets in repository | **None** ✅ |
| Cleanup performed | venvs, __pycache__, logs, test DBs, backup archive |

---

## 2. Project Overview

**KinJo** is a full-stack kindergarten management platform built with:
- **Backend:** Python 3.11+, FastAPI, SQLAlchemy, Alembic, Celery
- **Frontend:** Jinja2 HTML templates, Bootstrap 5, vanilla JS
- **Database:** SQLite (local dev) / PostgreSQL (production)
- **Auth:** JWT tokens, RBAC with roles: Admin, Manager, Supervisor, Parent
- **i18n:** Arabic / English (Babel)

---

## 3. Quick Setup

### Prerequisites
- Python 3.11 or 3.12
- pip
- Redis (optional — falls back to in-memory rate limiting for local dev)

### Steps
```bash
# 1. Clone or extract this package
cd kinjo

# 2. Create virtual environment
python -m venv .venv
.venv\Scripts\activate      # Windows
# source .venv/bin/activate  # macOS/Linux

# 3. Install dependencies
pip install -r requirements.txt

# 4. Configure environment
cp .env.example .env
# Edit .env — minimum required for local dev:
#   DATABASE_URL=sqlite:///./data/kinjo.db   (already in .env.example as fallback)
#   SECRET_KEY=<generate with: python -c "import secrets; print(secrets.token_hex(32))">

# 5. Create database schema
alembic upgrade head

# 6. (Optional) Seed with demo data
python seed_local.py

# 7. Start the server
python main.py
# OR
uvicorn main:app --reload --port 8000
```

Server runs at: **http://localhost:8000**  
API docs (dev only): **http://localhost:8000/docs**

---

## 4. Required Environment Variables

See [`.env.example`](.env.example) for the full annotated list.

**Minimum for local development:**
```env
DATABASE_URL=sqlite:///./data/kinjo.db
SECRET_KEY=<generate a 64-char hex string>
```

**Required for production (all fields in `.env.example` marked REQUIRED):**
- `DATABASE_URL` — PostgreSQL connection string
- `SECRET_KEY` — cryptographically random, never reuse the dev key
- `REDIS_URL` — Redis connection for rate limiting and caching
- `CORS_ALLOWED_ORIGINS` — your actual domain(s)
- `SMTP_*` — email credentials for password-reset flows

---

## 5. Running Tests

```bash
# Run full test suite
pytest

# Run with coverage
pytest --cov=. --cov-report=term-missing

# Run specific module
pytest tests/test_admin_security.py -v
```

Expected result: **1362 passing, 0 failing**

---

## 6. Docker / Production Deployment

See [`DEPLOYMENT_GUIDE.md`](DEPLOYMENT_GUIDE.md) for full Docker Compose setup.

Quick start with Docker:
```bash
cp .env.example .env
# Fill in production values in .env
docker-compose up -d
```

Services: `app`, `db` (PostgreSQL), `redis`, `celery-worker`, `nginx`

---

## 7. Project Structure

```
kinjo/
├── main.py               # FastAPI app entry point, router registration
├── models.py             # SQLAlchemy ORM models
├── config.py             # Settings (reads from .env)
├── auth.py               # JWT auth, password hashing
├── database.py           # DB engine and session factory
├── admin_endpoints.py    # Admin API routes
├── routers/              # Manager, parent, supervisor API routers
├── api/                  # Additional API modules (classes, parent, etc.)
├── templates/            # Jinja2 HTML templates (Bootstrap 5)
├── static/               # CSS, JS, images
├── tests/                # 70 test files, pytest
├── alembic/              # DB migrations
├── requirements.txt      # Python dependencies (33 packages)
├── .env.example          # Environment variable template
└── DEPLOYMENT_GUIDE.md   # Full production deployment guide
```

---

## 8. User Roles & Default Accounts

After seeding (`python seed_local.py`), default dev accounts are created.  
All passwords are set per seed script — check `seed_local.py` for values.

| Role | Access |
|---|---|
| Admin | Full system access, KPI dashboard, user management |
| Manager | Kindergarten management, class/supervisor/child CRUD |
| Supervisor | Daily reports, class attendance, child observations |
| Parent | Child profile, daily reports, professional report |

---

## 9. Known Limitations

See [`LIMITATIONS.md`](LIMITATIONS.md) for the up-to-date list.  
All critical limitations have been resolved as of commit `8999543`.

---

## 10. Support & Contribution

- Setup issues: see [`SETUP_AND_RUN.md`](SETUP_AND_RUN.md)
- Developer workflow: see [`DEVELOPER_WORKFLOW.md`](DEVELOPER_WORKFLOW.md)
- Contribution guidelines: see [`POLICIES.md`](POLICIES.md)

For questions, contact the team via your organization's communication channel.

---

*Package prepared by Claude Code on 2026-05-24. Audit report: [`audit_report.md`](audit_report.md).*
