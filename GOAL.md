# KInJo — Product Goal

## Vision

KInJo is a bilingual (Arabic / English) kindergarten management platform built for national-scale deployment.  
Its goal is to give every stakeholder — government regulators, regional managers, kindergarten supervisors, and parents — a single, trusted system for running, monitoring, and improving early-childhood education quality.

---

## Who It Serves

| Role | What they need |
|---|---|
| **Government / Ministry** | System-wide KPI dashboards, governance scores, compliance reports, and export-ready data for policy decisions. |
| **Regional Manager** | Kindergarten benchmarking, enrollment trends, attendance analytics, and staff-ratio compliance across their portfolio. |
| **Kindergarten Supervisor** | Daily operations: child check-in/out, incidents, daily reports, class management, and self-performance metrics. |
| **Parent** | Enrollment applications, real-time child status, daily report cards, messaging, and notifications in their preferred language. |
| **System Administrator** | User and role management, audit logs, MFA, backup scheduling, bulk operations, and production health monitoring. |

---

## Core Product Objectives

### 1. Operational Coverage
Provide end-to-end workflow support for the full kindergarten lifecycle:
- Kindergarten registration and licensing
- Child enrollment, waitlist management, and age-policy enforcement
- Daily attendance, check-in/out, and ratio-compliance logging
- Incident recording, safeguarding cases, and SLA tracking
- Daily report generation and parent delivery
- Staff training tracking and regulatory status management

### 2. Data-Driven Quality Governance
Surface actionable quality signals at every level of the hierarchy:
- **GQI** (Governance Quality Index): ratio compliance, checklist adherence, regulatory status, training coverage, incident follow-up SLA
- **CEI** (Child Experience Index): attendance rate, chronic absence, serious incident rate, parent satisfaction
- **Final Governance Score**: GREEN / AMBER / RED bands with automatic RED override for expired licenses
- Predictive analytics to flag at-risk kindergartens before scores deteriorate

### 3. Bilingual First-Class Experience
Arabic and English are co-equal throughout the system:
- All UI labels, notifications, email templates, and PDF-ready reports are fully translated
- Parents choose their preferred language; the system stores and respects that preference end-to-end
- No hardcoded Arabic or English strings in production code paths

### 4. Security and Compliance by Default
The platform ships with production-grade security enabled out of the box:
- Role-based access control (RBAC) with fine-grained permission checks on every endpoint
- Multi-factor authentication with emergency admin recovery
- Rate limiting on all authentication and bulk-operation endpoints
- Full audit trail for all sensitive actions (create / update / delete / impersonate / export)
- OWASP Top-10 mitigations applied and verified across 80+ dedicated security tests

### 5. Production-Ready Infrastructure
The system is deployable today without code changes:
- Docker Compose stack (app + PostgreSQL + Redis + Celery workers)
- Alembic migration history at HEAD — zero manual schema steps required
- Automated daily backups with 30-day retention and one-command restore
- Real-time WebSocket dashboard with exponential back-off reconnection
- Health endpoint (`/health`) suitable for load-balancer probes and uptime monitors

---

## Success Criteria (Definition of "Ready")

| Criterion | Status |
|---|---|
| All automated tests pass (1 244 / 1 244) | ✅ |
| Zero critical security findings (OWASP Top 10 scan) | ✅ |
| All API routers mounted and reachable | ✅ |
| Database schema at Alembic HEAD | ✅ |
| Bilingual templates — 0 hardcoded strings | ✅ |
| Production environment validation blocks bad config at startup | ✅ |
| Backup scheduler active in production lifespan | ✅ |
| Audit log populated for all sensitive operations | ✅ |
| Launch audit score ≥ 98 / 100 | ✅ 98 / 100 |
| Docker Compose stack builds and starts cleanly | ✅ |

---

## Known Boundaries (Out of Scope for v1)

- **Server-side PDF export** — browser print with `@media print` stylesheet is the current path; a background export queue is modelled and ready for a future PDF library.
- **WebSocket push for messages** — `/ws/notify` is not yet live; the frontend polls every 60 seconds as a fallback.
- **Full-text search** — child and enrollment search uses SQL `LIKE`; suitable for < 50 000 rows. A `tsvector` / MeiliSearch upgrade is planned for large deployments.
- **Supervisor / parent impersonation** — admin impersonation is intentionally limited to manager accounts to prevent privilege escalation.

---

## Deployment Checklist (Final Steps Before Go-Live)

1. Set `DATABASE_URL` to a PostgreSQL connection string.
2. Set `REDIS_URL`, `CELERY_BROKER_URL`, and `CELERY_RESULT_BACKEND` to Redis-backed values.
3. Generate a random `SECRET_KEY` of at least 32 bytes.
4. Set `ENVIRONMENT=production`, `DEBUG=false`, `API_DOCS_ENABLED=false`.
5. Configure `CORS_ALLOWED_ORIGINS` and `TRUSTED_HOSTS` to exact production domains.
6. Set `SESSION_COOKIE_SAMESITE=strict` and enable HTTPS at the reverse proxy.
7. Configure SMTP credentials for password-reset email delivery.
8. Run `alembic upgrade head` on first deploy.
9. Verify `/health` returns `200` after startup.

---

*KInJo v2.0 — Final Version — May 2026*
