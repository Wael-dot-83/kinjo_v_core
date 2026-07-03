# KinJo Admin System — Claude Code Project Guide

## Stack
| Layer | Technology |
|---|---|
| Backend | FastAPI + SQLAlchemy (sync), Python 3.13 |
| Templates | Jinja2 with bilingual guards (`{% if ui_lang == 'en' %}`) |
| Frontend | Vanilla JS ES6 classes, Chart.js 4, Bootstrap 5.3 RTL, Bootstrap Icons |
| i18n | `static/i18n/admin_en.json` / `static/i18n/admin_ar.json` — Arabic primary |
| Tests | pytest, `tests/test_*.py` |
| Cache | `cache_service.py` wrapping Redis; 30-second TTL on dashboard data |

## Non-negotiable conventions

### Timezone — Jordan UTC+3
```python
from datetime import datetime, timezone, timedelta
_JORDAN_TZ = timezone(timedelta(hours=3))
now = datetime.now(_JORDAN_TZ)
today = now.date()
```
- **Never** use `date.today()` or `datetime.now(timezone.utc)` for operational dates
- Cache keys that include a date must use the Jordan date, not UTC

### Bilingual output
- Backend strings shown in the UI must supply both `_ar` and `_en` variants
- Templates use `{% if ui_lang == 'en' %}...{% else %}...{% endif %}` guards
- `window.KINJO_LANG` is injected by Jinja2 and consumed by JS
- i18n keys follow dot-notation under their section: `dashboard.enrollment_active`
- Enrollment chart keys must be **uppercase** (`ACTIVE`, `PENDING_REVIEW`) to match `ENROLLMENT_I18N` in JS

### Database queries
- Never introduce N+1 queries; batch with `.in_()` or `GROUP BY` + `func.count()`
- All admin endpoints must use the `require_admin` FastAPI dependency
- Every state-changing operation must call `log_audit_event()` from `admin_security.py`
- Use `AuditAction` constants from `audit_actions.py` — never raw action strings

### KPI integrity
- KPI computations belong in `kpi_service.py` — do not duplicate logic in endpoints
- `data_quality_score` = % of active kindergartens that filed a report in last 7 days (not attendance rate)
- The `kpis` dict in `AdminDashboardResponse` has exactly 7 keys — must match `KPI_CONFIG` in `admin_dashboard.js`

## Key files
| File | Purpose |
|---|---|
| `frontend.py` | All HTML page routes; `language_context_processor` injects `ui_lang`/`ui_dir` |
| `admin_endpoints.py` | All `/api/admin/*` REST endpoints |
| `admin_security.py` | `require_admin`, `log_audit_event`, `can_admin_access_user` |
| `audit_actions.py` | `AuditAction` string constants |
| `kpi_service.py` | Authoritative KPI computation engine |
| `kpi_standards.py` | Thresholds, band assignment, override rules |
| `models.py` | All SQLAlchemy models and enums |
| `static/js/admin_dashboard.js` | Dashboard frontend controller |
| `static/i18n/admin_*.json` | All UI strings |
| `templates/admin_base.html` | Master layout: sidebar, auth, i18n, RTL/LTR |

## Running the project
```bash
# Start dev server
uvicorn main:app --reload --host 127.0.0.1 --port 8000

# Run targeted tests (fast)
python -m pytest tests/test_kpi_dashboard.py tests/test_i18n_key_coverage.py tests/test_kpi_service.py tests/test_admin_operations.py -q

# Run full suite
python -m pytest

# Single file with verbose output
python -m pytest tests/test_new_modules.py -x -v
```

## Agent roles (see AGENTS.md)
- **Architect** — planning only; saves plans to `.kilo/plans/`
- **Code Reviewer** — read-only analysis; flags issues by severity
- **Code Skeptic** — adversarial QA; challenges unverified claims, enforces proof
- **Test Engineer** — writes/edits Python tests in `tests/`

## What NOT to do
- Do not use `date.today()` or `datetime.now(timezone.utc)` for Jordan-facing dates
- Do not hardcode Arabic-only strings in API response fields visible in the UI
- Do not compute KPI values inline in endpoints — delegate to `kpi_service.py`
- Do not add N+1 queries; always batch aggregates
- Do not skip `log_audit_event()` on admin state-changing operations
- Do not use Pydantic v1 patterns (`.dict()`, `@validator`, `class Config`) — use Pydantic v2
- Do not create or use git worktrees — all agent work happens directly in the repo root (`d:\Final Version`) on `main`; historical reports go in `docs/reports/`, manual scripts in `scripts/manual-diagnostics/`
