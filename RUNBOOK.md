# KinJo — Operations Runbook

## Table of Contents
1. [First Deploy](#1-first-deploy)
2. [Routine Deploy (zero-downtime)](#2-routine-deploy-zero-downtime)
3. [Rollback Plan](#3-rollback-plan)
4. [Common Incidents](#4-common-incidents)
5. [Escalation Paths](#5-escalation-paths)
6. [Health Checks](#6-health-checks)
7. [Backup & Restore](#7-backup--restore)
8. [Performance Triage](#8-performance-triage)

---

## 1. First Deploy

### Prerequisites
| Requirement | Minimum |
|---|---|
| Python | 3.11 |
| PostgreSQL | 15 |
| Redis | 7 |
| Docker Compose | 2.20 |

### Steps

```bash
# 1. Clone and enter the repo
git clone <repo-url> kinjo && cd kinjo

# 2. Copy and fill in secrets
cp .env.example .env
# Required: SECRET_KEY, DATABASE_URL, REDIS_URL, CORS_ALLOWED_ORIGINS, TRUSTED_HOSTS
# Generate SECRET_KEY:
python -c "import secrets; print(secrets.token_hex(32))"

# 3. Start infrastructure
docker compose up -d db redis

# 4. Install Python deps
pip install -r requirements.txt

# 5. Run migrations (never skip in production)
alembic upgrade head

# 6. Seed initial admin user
python seed_local.py   # development
# OR
python scripts/seed_comprehensive.py  # production (uses SEED_*_PASSWORD env vars)

# 7. Start the app
uvicorn main:app --host 0.0.0.0 --port 8000 --workers 4

# 8. Verify
curl -f http://localhost:8000/health | python -m json.tool
```

---

## 2. Routine Deploy (zero-downtime)

```bash
# Pull new code
git fetch origin && git checkout <new-tag-or-sha>

# Install any new dependencies
pip install -r requirements.txt

# Check for pending migrations BEFORE restarting
alembic current          # shows current revision
alembic heads            # shows latest revision
alembic upgrade head     # apply — safe to run on a live DB (uses CONCURRENTLY where possible)

# Rolling restart (if using systemd)
systemctl reload kinjo   # SIGHUP triggers graceful restart in uvicorn

# Verify health
curl -sf http://localhost:8000/health
curl -sf http://localhost:8000/api/health
```

---

## 3. Rollback Plan

### Code rollback

```bash
git checkout <previous-tag-or-sha>
pip install -r requirements.txt
systemctl restart kinjo
```

### Migration rollback (use with caution — data loss risk)

```bash
# Identify the revision to roll back to
alembic history --verbose

# Roll back one step
alembic downgrade -1

# Roll back to a specific revision
alembic downgrade <revision-id>
```

> **Warning:** Migrations that drop columns or tables cannot be safely reversed on a
> live database with running application code. Always snapshot the database before
> applying a destructive migration.

### Database snapshot before migration

```bash
# PostgreSQL pg_dump snapshot
pg_dump $DATABASE_URL > backup_pre_migration_$(date +%Y%m%dT%H%M%S).sql

# Or trigger an in-app backup
curl -X POST http://localhost:8000/api/admin/backup/create \
  -H "Authorization: Bearer <admin-token>"
```

---

## 4. Common Incidents

### 4.1 Application returns 500 on all requests

**Symptoms:** Every API endpoint returns 500. Health check fails.

**Diagnosis:**
```bash
# Check logs (JSON structured output)
journalctl -u kinjo -n 100 --no-pager | python -m json.tool | grep '"level":"ERROR"'

# Check DB connectivity
psql $DATABASE_URL -c "SELECT 1"

# Check Redis
redis-cli -u $REDIS_URL ping
```

**Resolution:**
1. If DB is unreachable — restore connectivity or failover to replica.
2. If Redis is down — `RATE_LIMIT_STORAGE_URI=memory://` allows the app to start without Redis (rate limiting degrades to per-process memory).
3. Restart: `systemctl restart kinjo`

---

### 4.2 Rate limit 429s flooding admin users

**Symptoms:** Admins receive 429 Too Many Requests unexpectedly.

**Diagnosis:**
```bash
# Check current rate limit config
grep RATE_LIMIT .env

# Check Redis rate limit keys
redis-cli -u $REDIS_URL KEYS "LIMITS:*" | head -20
```

**Resolution:**
- Temporarily raise `RATE_LIMIT_ADMIN_READ` in `.env` and restart.
- If Redis is accumulating stale keys: `redis-cli FLUSHDB` (clears all limit counters — use only in emergency).

---

### 4.3 DB connection pool exhausted

**Symptoms:** Log lines: `TimeoutError: QueuePool limit of size 10 overflow 20 reached`.

**Diagnosis:**
```bash
# Check active PG connections
psql $DATABASE_URL -c "SELECT count(*) FROM pg_stat_activity WHERE datname = 'kinjo_db'"
```

**Resolution:**
1. Increase pool: set `DB_POOL_SIZE=20 DB_MAX_OVERFLOW=40` in `.env` and restart.
2. If connections are idle-in-transaction: kill them with `pg_terminate_backend`.
3. Long-term: add PgBouncer as a connection pooler in front of PostgreSQL.

---

### 4.4 Disk full — backup fails

**Symptoms:** `POST /api/admin/backup/create` returns 500 or 507.

**Diagnosis:**
```bash
df -h /data
du -sh /data/backups/*
```

**Resolution:**
```bash
# Remove old backups (keep latest 7)
ls -t /data/backups/*.sql.gz | tail -n +8 | xargs rm -f

# Trigger new backup after freeing space
curl -X POST http://localhost:8000/api/admin/backup/create \
  -H "Authorization: Bearer <admin-token>"
```

---

### 4.5 Admin session expires too quickly

**Symptom:** Users complain of being logged out after a few minutes.

**Resolution:**
- Increase `SESSION_TIMEOUT_MINUTES` in `.env` (default: 30).
- Also increase `ACCESS_TOKEN_EXPIRE_MINUTES` if the JWT itself is expiring.
- Restart the app for `.env` changes to take effect.

---

### 4.6 Migration fails mid-apply

**Symptoms:** `alembic upgrade head` exits with an error partway through.

**Resolution:**
1. Check which revision was partially applied: `alembic current`
2. Do NOT re-run `alembic upgrade` without investigating — partial state can break idempotency.
3. Inspect the failed migration file and apply the remaining SQL manually if safe.
4. Or: restore the pre-migration database snapshot and investigate the cause before retrying.

---

## 5. Escalation Paths

| Severity | First Responder | Escalate to |
|---|---|---|
| P0 — site down | On-call engineer | Engineering lead within 15 min |
| P1 — admin module down | On-call engineer | Engineering lead within 30 min |
| P2 — degraded performance | On-call engineer | Engineering lead within 2 h |
| Security incident | On-call engineer → immediate | CISO + Engineering lead within 1 h |

For security incidents: isolate the instance, do NOT wipe logs, and notify the CISO before any remediation.

---

## 6. Health Checks

| Endpoint | Auth | Purpose |
|---|---|---|
| `GET /health` | None | Basic app liveness (DB + uptime) |
| `GET /api/health` | None | Detailed component health (DB, Redis, disk) |
| `GET /api/admin/health` | Admin JWT | Admin-scoped check (DB + cache) |

All health endpoints return JSON:
```json
{
  "status": "ok",
  "checks": { "database": "ok", "cache": "ok" },
  "timestamp": "2026-06-14T10:00:00+00:00"
}
```

`status` is one of: `"ok"` | `"degraded"` | `"error"`.

---

## 7. Backup & Restore

### Create backup
```bash
curl -X POST http://localhost:8000/api/admin/backup/create \
  -H "Authorization: Bearer <admin-token>"
```

### List backups
```bash
curl http://localhost:8000/api/admin/backup/list \
  -H "Authorization: Bearer <admin-token>"
```

### Restore (requires two-step confirmation)
```bash
# Step 1: Get confirmation token
TOKEN=$(curl -s -X POST http://localhost:8000/api/admin/backup/restore/<backup-name> \
  -H "Authorization: Bearer <admin-token>" \
  -H "Content-Type: application/json" \
  -d '{}' | python -m json.tool | grep confirmation_token | cut -d'"' -f4)

# Step 2: Confirm restore (OVERWRITES ALL DATA)
curl -X POST http://localhost:8000/api/admin/backup/restore/<backup-name> \
  -H "Authorization: Bearer <admin-token>" \
  -H "Content-Type: application/json" \
  -d "{\"confirmation_token\": \"$TOKEN\"}"
```

> **Warning:** Restore overwrites the entire database. Ensure you have a pre-restore
> snapshot before proceeding.

---

## 8. Performance Triage

### Run the load test (requires Locust)
```bash
pip install locust
locust -f load_tests/locustfile.py --host http://localhost:8000 \
  --users 50 --spawn-rate 5 --run-time 60s --headless \
  -e LOAD_TEST_ADMIN_USERNAME=admin \
  -e LOAD_TEST_ADMIN_PASSWORD=<password>
```

Thresholds: error rate < 1%, p95 latency < 2 000 ms.

### Slow query diagnosis
```sql
-- Top 10 slowest queries (requires pg_stat_statements)
SELECT query, mean_exec_time, calls
FROM pg_stat_statements
ORDER BY mean_exec_time DESC
LIMIT 10;

-- Check missing indexes on users table
SELECT schemaname, tablename, attname, n_distinct, correlation
FROM pg_stats
WHERE tablename = 'users';
```

### Apply performance indexes (if not yet applied)
Performance indexes are included in the regular migration chain — running
`alembic upgrade head` (see §1/§2) applies them. No separate step needed.
