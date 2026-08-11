import os

out_dir = r'D:\Final Version_mvp_ADMIN\.kilo\phase1_reports'
os.makedirs(out_dir, exist_ok=True)

report1 = """# 1. Repository Architecture

## Overview
KinJo is a FastAPI-based kindergarten management platform serving the Jordanian early childhood education market. The application follows a monolithic architecture with server-side Jinja2 rendering for admin pages and a REST API backend.

## Directory Structure (key)
- `main.py` - FastAPI app factory, route registration, WebSocket endpoints (6895+ lines)
- `config.py` - Pydantic Settings configuration with 150+ settings
- `models.py` - SQLAlchemy ORM models (~40+ domain models, 700+ lines)
- `database.py` - Engine/session management, SQLite/PostgreSQL support
- `auth.py` - Authentication, password hashing, JWT token management
- `dependencies.py` - FastAPI dependencies, role-based access control, session management
- `admin_endpoints.py` - Admin CRUD operations (6895 lines, largest single file)
- `admin_security.py` - Security hardening: error contracts, audit logging, rate limiting, IDOR protection
- `audit_service.py` - Audit log listing/export, admin router (289 lines)
- `dashboard_api.py` - Dashboard widgets, summary, suggested actions (368 lines)
- `frontend.py` - Compatibility wrapper for legacy frontend routes (12 lines)
- `missing_endpoints.py` - Compatibility wrapper for legacy missing-endpoints (not found at root; API: `api/missing_endpoints.py`)
- `api/` - Modular API routers (18 core files + sub-packages)
- `api/analytics/` - Analytics sub-package with scope_domain.py
- `api/auth/` - Password reset service
- `api/reports/` - Report constants
- `scripts/` - 50+ utility scripts including compat wrappers and manual diagnostics (49 scripts)
- `scripts/compat/` - Legacy compat wrappers (frontend_orig.py, missing_endpoints_orig.py)
- `alembic/` - 45 migration files for database schema evolution

## Template Structure
- `templates/base.html` - Public base template
- `templates/admin_base.html` - Admin shell (476 lines): RTL/LTR support, Bootstrap 5.3.2, USWDS, custom CSS, all JS dependencies
- `templates/admin_base_premium.html` - Compatibility wrapper extending admin_base.html (7 lines)
- `templates/admin/` - 40 admin page templates organized by subdirectory
- `templates/components/` - 20+ reusable Jinja2 partials (navbar, sidebar, kpi-card, data-table, filter-bar, confirm-modal, toast, etc.)

## Static Assets
- `static/css/` - 18 CSS files (admin_design_system.css, components.css, layout.css, rtl.css, dark-mode.css, etc.)
- `static/js/` - 43 project JS files (admin_*.js modules, kinjo-app.js, kinjo-api.js, dashboard.js, etc.)
- `static/vendor/` - Vendored Bootstrap 5.3.2, USWDS v3, Plotly 2.35.2, SweetAlert2 11.14.5, Chart.js, odometer 0.4.8, tablesort, Material Icons (5800+ SVGs), USA Icons

## Route Architecture (from main.py)
- `/api/admin/*` - Admin endpoints (users, audit logs, roles, etc.) via admin_router
- `/api/admin/analytics/*` - Advanced analytics (33 metrics across 5 layers) via admin_advanced_analytics_router
- `/api/admin/reports/*` - Admin reports via admin_reports_router
- `/api/admin/heat-map/*` - Heat map admin endpoints (via heatmap.backend.admin_router)
- `/api/admin/impersonation/*` - Admin impersonation endpoints
- `/api/dashboard/*` - Cross-role dashboard (widgets, summary, actions) via dashboard_api.py
- `/api/analytics/*` - Analytics endpoints via analytics_router
- `/api/heatmap/*` - Heat map ETL/analytics (legacy React app path)
- `/api/kindergartens/*` - Kindergarten CRUD
- `/api/absence-requests/*` - Absence management
- `/api/attendance/*` - Attendance tracking
- `/api/classes/*` - Class management
- `/api/children/*` - Child records
- `/api/enrollment/*` - Enrollment applications
- `/api/daily-reports/*` - Daily reports (two routers: daily_reports_api_router + dr_analytics_router)
- `/api/manager/*` - Manager-scoped endpoints via manager_router
- `/api/supervisor/*` - Supervisor-scoped via supervisor_scoped_router
- `/api/parent/*` - Parent-facing endpoints via parent_router
- `/api/users/*` - User management via users_router
- `/api/tasks/*` - Task management
- `/api/messaging/*` - Messaging
- `/api/portfolio/*` - Portfolio
- `/api/government/*` - Government APIs
- `/api/public/*` - Public endpoints
- `/api/me/*` - Account self-service (me_router)
- `/comm/*` - Communication routes (communication_router)
- `/api/*` - Safety, KPI, monitoring, analytics, filter, export, audit
- `/` - Frontend routes via frontend_router
- `/ws/dashboard`, `/ws/heatmap`, `/ws/notify` - WebSocket endpoints

## Key Architectural Patterns
1. Router composition: Routes registered in main.py from modular routers
2. Dependency injection: get_db, get_current_user, require_admin, require_manager, etc.
3. Admin security: admin_security.py provides standardized error responses, correlation IDs, audit logging, rate limiting, IDOR protection
4. CSRF: Meta tag csrf-token in templates, cookies for session auth
5. i18n: Arabic (RTL) and English (LTR) with _t() Jinja2 global, kinjo_lang cookie
6. Cache: Redis-backed via cache_service for dashboard widgets, analytics
7. Celery: Background task queue for async operations
8. Testing: pytest + pytest-asyncio, SQLite in-memory for tests, Postgres for CI E2E
9. Migrations: Alembic with 45 migration files
10. Containerized: Docker + Docker Compose with PostgreSQL, Redis, web app
11. Config: Pydantic Settings with .env, type coercion, comma-list parsing for List[str] fields
12. Logging: JSON or text format configurable, INFO level default
"""

report2 = """# 2. Technology Stack

## Backend
- **Framework**: FastAPI 0.121.3+ (async Python web framework)
- **WSGI/ASGI Server**: Uvicorn 0.32.0
- **ORM**: SQLAlchemy 2.0.36 (declarative models, session management)
- **Migration**: Alembic 1.14.0 (45 migration files)
- **Validation**: Pydantic 2.10.0 (request/response schemas)
- **Authentication**: python-jose[cryptography] 3.5.0 (JWT), passlib[bcrypt] 1.7.4 (password hashing)
- **Rate Limiting**: slowapi 0.1.9 (Redis-backed)
- **Caching**: Redis 5.2.0 (cache_service module)
- **Task Queue**: Celery 5.4.0 (background tasks)
- **Database**: PostgreSQL 15 (production), SQLite (dev/testing)
- **Email**: SMTP-based password reset
- **Real-time**: WebSockets (dashboard, heatmap, notifications), Redis pub/sub
- **ML/Analytics**: numpy 2.4.2, scikit-learn>=1.5,<2, pandas 3.0.0, plotly 6.5.2, scikit-learn
- **File Processing**: openpyxl>=3.1,<4 (Excel import), python-multipart>=0.0.27
- **Security**: cryptography>=43.0, bleach==6.4.0 (HTML sanitization)
- **Captcha**: hCaptcha or reCAPTCHA v2 (configurable)
- **Virus Scanning**: ClamAV integration (optional)
- **Observability**: psutil 6.1.0, python-json-logger>=2.0,<4
- **Search**: google-genai 1.60.0 (Generative AI integration)
- **Supervision**: supervisor 4.2.5 (process management)
- **Storage**: Local filesystem or S3 (boto3)

## Frontend
- **Template Engine**: Jinja2 3.1.6 (server-side rendering)
- **CSS Framework**: Bootstrap 5.3.2 (self-hosted, RTL variant included)
- **Design System**: USWDS (U.S. Web Design System) v3, KinJo custom design tokens
- **Icons**: Material Symbols Outlined, USA Icons, Bootstrap Icons (material-icons 5800+ SVGs)
- **Charts**: Plotly 2.35.2 (bundled minified), Chart.js 4.x (CDN or bundled), custom chart_utils.js
- **Date/Number Formatting**: odometer.js v0.4.8
- **Table Sorting**: tablesort.min.js
- **HTTP Client**: Native fetch API with auth headers (kinjo-api.js)
- **State Management**: Vanilla JS (no framework), client_error_monitor.js for error tracking
- **i18n**: Custom JavaScript i18n with Arabic/English parity (app_i18n.js, admin_i18n.js)
- **RTL Support**: Bootstrap RTL stylesheet (bootstrap.rtl.min.css), CSS logical properties
- **Accessibility**: axe-selenium-python for automated a11y testing
- **Performance**: page_load_timer.js, api_timing.js, web_vitals_collector.js

## Development & DevOps
- **Python**: >=3.11
- **Testing**: pytest 9.0.3+, pytest-asyncio 1.0+, pytest-cov 6.0.0, pytest-xdist 3.5.0, pytest-timeout>=2.3,<3
- **Linting**: ruff 0.15.1 (only E722 bare-except, F821 undefined-name)
- **Type Checking**: mypy>=1.11,<2
- **Security Scanning**: bandit>=1.7,<2
- **Load Testing**: locust>=2.31,<3
- **E2E Testing**: Selenium>=4.0,<5, Playwright>=1.49,<2, webdriver-manager>=4.0,<5
- **Containerization**: Docker (python:3.12-slim), Docker Compose
- **Process Management**: supervisor 4.2.5
- **CI/CD**: Artifacts in docs/reports/ and .ai-review/
- **Static Analysis**: ruff, mypy, bandit, check_routes.py (duplicate route detection)

## Configuration Management
- **Settings**: Pydantic Settings (config.py) with .env file loading via pydantic-settings 2.6.1
- **Environment**: Development vs Production with strict validation (validate_production_settings)
- **Secrets**: SECRET_KEY (64-char hex), JWT algorithm HS256
- **Cookie Management**: Strict SameSite default, secure flag in production, SESSION_TIMEOUT_MINUTES=30
- **Rate Limits**: Configurable per operation type (password reset 3/min, bulk write 10/min, admin read 60/min, etc.)
- **Pagination**: DEFAULT_PAGE_SIZE=25, MAX_PAGE_SIZE=100
- **File Uploads**: MAX_ATTACHMENT_SIZE_MB=10, ALLOWED_IMAGE_TYPES, ALLOWED_DOCUMENT_TYPES
- **Localization**: DEFAULT_LANGUAGE=ar, SUPPORTED_LANGUAGES=ar,en
"""

report3 = """# 3. Frontend Modules

## 1. Admin Shell (templates/admin_base.html, 476 lines)
- RTL/LTR support for Arabic/English (auto-detected from kinjo_lang cookie or ui_lang context)
- CSRF meta tag: `<meta name="csrf-token" content="{{ csrf_token | default('') }}" />`
- Session timeout meta tag (known issue: hardcoded 30min fallback in JS; not emitted anywhere)
- Bootstrap 5.3.2 direction-aware (bootstrap.min.css / bootstrap.rtl.min.css)
- USWDS v3 stylesheet
- Custom CSS chain (v3.1, v1.0, v1, v1.1, v1.2, v20260714): admin_design_system.css, top-menu.css, design-tokens.css, layout.css, components.css, utilities.css, kinjo.css, rtl.css, dark-mode.css
- SweetAlert2 v11.14.5, Odometer v0.4.8, Material Symbols Outlined font
- Google Fonts: Inter (Latin) + Noto Sans Arabic
- JS: sanitize.js, page_load_timer.js (loaded in all admin pages)
- Block-based template: title, breadcrumb, extra_head, content

## 2. Admin Dashboard (templates/admin/admin_dashboard.html)
- Main admin landing page
- KPI cards with live data
- Charts section (Chart.js / Plotly)
- Quick actions toolbar
- Widget customization support (via dashboard_api.py)

## 3. Kindergarten Management (templates/admin/kindergartens/)
- list.html - Table view with search, governorate/status filters, pagination (20/page)
- form.html - Create/edit form with Arabic RTL layout, validation
- detail.html - Full details with statistics (child count, attendance %, occupancy %, teachers), audit log

## 4. User Management (templates/admin/users/)
- list.html - User listing with role/status/kindergarten filters
- form.html - User creation/edit form with profile fields, identity validation

## 5. Analytics (templates/admin/analytics/)
- dashboard.html - Main analytics dashboard
- charts_dashboard.html - Chart-based analytics view
- explorer.html - Data exploration interface
- drilldown.html - Drill-down analytics
- reporting_dashboard.html - Reporting dashboard
- reports.html - Report list
- incident_reports_list.html, incident_reports_generate.html, incident_report_detail.html

## 6. Manager Dashboard (templates/manager/)
- dashboard.html - Manager-specific dashboard (KPI, alerts)
- kpi.html - KPI view
- benchmarking.html - Benchmarking comparisons
- children.html - Child oversight
- daily_reports_review.html - Daily report review
- supervisors.html - Supervisor management
- attendance.html, safety.html, observations.html, performance.html
- children.html, profile.html, settings.html

## 7. Supervised Pages (templates/supervisor/)
- attendance.html, daily_reports.html, messages.html
- observations.html, performance.html, profile.html
- safety.html, settings.html

## 8. Parent Portal (templates/parent/)
- attendance.html, children.html, enrollments.html, profile.html
- wizard/kindergarten_select.html, wizard/step3_parent_info.html

## 9. Public Pages (templates/public/)
- home.html, about.html, contact.html, faq.html, legal.html, service_guide.html, sitemap.html

## 10. Auth Pages (templates/auth/)
- login.html, register.html, forgot-password.html, reset-password.html
- change-password.html, mfa_setup.html

## 11. Other Module Templates
- attendance/: daily.html, history.html, absence_requests.html
- communication/: index.html, events.html, messages.html + modals (new_event, new_message, new_survey)
- enrollment/: create.html, list.html, view.html
- reports/: analytics_dashboard.html, form.html, list.html, parent_list.html, view.html
- safety/: index.html, incident_form.html, incident_detail.html
- classes/: list.html, form.html, view.html, class_form.html
- tasks/: list.html
- dashboard/: index.html, parent.html, supervisor.html
- user/: notifications.html, settings.html
- help_center.html, impersonate.html
- agency_reports/: agency.html, index.html, report.html

## 12. Jinja2 Components (templates/components/)
20+ partials including: navbar, sidebar, footer, page-header, kpi-card, data-table, filter-bar, filter-panel, filter-row, confirm-modal, modal, help-modal, toast, chart-container, export-modal, submit-button, step-indicator, alert-banner, card-wrapper, date-range-filter, location-filter, manager-context-strip, admin-page-context, impersonation-banner, uswds_header, uswds_sidenav, kinjo_logo

## JavaScript Modules (43 files, non-vendor)
- kinjo-app.js - Main app initialization, global setup
- kinjo-api.js - API communication layer with JWT/auth header injection
- dashboard.js - Dashboard page functionality
- dashboard_filters.js - Dashboard filter panel and summary endpoint consumer
- admin_dashboard.js - Admin dashboard widget JS
- admin_analytics.js - Analytics page navigation and chart rendering
- admin_agency_reports.js - Agency report JS functionality
- admin_agency_reports_dashboard_summary.js - Summary pills for agency reports
- admin_agency_reports_custom.js - Custom report builder
- admin_kindergartens.js - KG management (list, form, detail)
- admin_governance.js - Governance report features
- admin_components.js - Reusable admin UI components
- admin_i18n.js - Frontend i18n (Arabic/English switching)
- admin_activity_filters.js - Activity feed filtering
- admin_reporting_dashboard.js - Reporting dashboard JS
- admin_observability.js - Observability dashboard JS
- admin_alerts.js - Alert management
- admin_messages_list_frontend_contract.js - Messages list contract validation
- admin_period_frontend_contract.js - Period filter contract
- admin_sidebar_navigation.js - Sidebar link resolution
- admin_upload_security.js - Upload security (CSRF token injection)
- admin_write_csrf_integration.js - CSRF integration for state-changing operations
- auth.js - Authentication flow (login, logout, token refresh, MFA)
- validation.js - Form validation utilities (Arabic-friendly)
- sanitize.js - HTML sanitization (XSS prevention, CSV injection prevention)
- chart_utils.js - Chart rendering and configuration utilities
- manager_benchmarking.js - Manager benchmarking features
- manager_context_strip.js - Manager kindergarten context indicator
- decision_support.js - Decision support report features
- ncfa_strong_reports.js - NCFA strong reports functionality
- kg_overview.js - Kindergarten overview page JS (KPI loading, customisation drawer)
- supervisor_performance.js - Supervisor performance features
- advanced_analytics.js - Advanced analytics page JS
- agency_report_location_filter.js - Location filter for agency reports
- plotly-locale-ar.js - Plotly Arabic locale configuration
- tailwind.js - Tailwind CSS integration
- app_i18n.js - Application-level i18n utilities
- kpi-validation.js - KPI formula validation
- page_load_timer.js - Page load performance measurement
- client_error_monitor.js - Client-side error tracking and reporting
- web_vitals_collector.js - Web Vitals (LCP, FID, CLS) collection
- api_timing.js - API response time measurement
- audit-logs.js - Audit log page JS
- jordan_cesium_map.js - Cesium globe (legacy, Google Maps now used)

## CSS Files (18 non-vendor)
admin_design_system.css v3.1, top-menu.css v1.0, design-tokens.css v1, layout.css v1.1, components.css v1.2, utilities.css v1, kinjo.css v20260714, rtl.css, dark-mode.css v1.0, admin_analytics_v2.css, admin_kindergartens.css, agency_reports.css, dashboard-enhanced.css, dashboard-pro.css, manager_design.css, ncfa_strong_reports.css, print.css
"""

# Write all reports
for filename, content in [("01_repository_architecture.md", report1), ("02_technology_stack.md", report2), ("03_frontend_modules.md", report3)]:
    filepath = os.path.join(out_dir, filename)
    with open(filepath, 'w', encoding='utf-8') as f:
        f.write(content)
    print(f'Wrote {filename} ({len(content)} chars)')

print("Reports 1-3 done")
