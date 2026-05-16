# KInJo Production Deployment Guide

## Quick Start - Deploy to Production

### Prerequisites

- PostgreSQL 12+ running
- Redis (optional, auto-fallback to in-memory cache)
- Python 3.9+
- 2+ GB RAM minimum

### Step 1: Prepare Environment

```bash
# Set production environment variables
export ENVIRONMENT=production
export DEBUG=False
export API_DOCS_ENABLED=False
export DATABASE_URL=postgresql://user:password@host:5432/kinjo
export SECRET_KEY=$(python -c "import secrets; print(secrets.token_urlsafe(32))")
export ALGORITHM=HS256
export ACCESS_TOKEN_EXPIRE_MINUTES=480

# Optional: Configure backup location
export BACKUP_DIR=/var/backups/kinjo
mkdir -p $BACKUP_DIR
chmod 700 $BACKUP_DIR
```

### Step 2: Validate Production Configuration

```bash
# Run preflight checks
python scripts/preflight_hosting.py

# Output should show:
# ✅ Production environment validated
# ✅ Database: PostgreSQL detected
# ✅ Secret key: Sufficient length
# ✅ CORS configured
# ✅ Ready for deployment
```

### Step 3: Initialize Database

```bash
# Run migrations
alembic upgrade head

# Create admin user (one-time)
python -c "
from database import SessionLocal
from models import User, UserRole, UserStatus
from auth import get_password_hash
import os

db = SessionLocal()
admin = User(
    username='admin',
    email=os.environ.get('ADMIN_EMAIL', 'admin@example.com'),
    hashed_password=get_password_hash('ChangeMe123!'),
    role=UserRole.ADMIN,
    status=UserStatus.ACTIVE
)
db.add(admin)
db.commit()
print(f'✅ Admin user created: {admin.username}')
"
```

### Step 4: Enable Automated Backups

```bash
# Backups will run automatically at 2:00 AM UTC
# Logs appear in the application logs
# Retention: 30-day automatic cleanup

# To change backup time, set before app startup:
export BACKUP_TIME_HOUR=2
export BACKUP_TIME_MINUTE=0
```

### Step 5: Deploy Application

```bash
# Using gunicorn (recommended)
gunicorn main:app \
  --workers 4 \
  --worker-class uvicorn.workers.UvicornWorker \
  --timeout 120 \
  --access-logfile - \
  --error-logfile - \
  --log-level info

# OR using built-in server (development)
python main.py
```

### Step 6: Verify Deployment

```bash
# Health check
curl http://localhost:8000/health
# Expected: {"status": "healthy", "app": "KInJo", "version": "1.0.0"}

# Comprehensive health (admin only - after login)
curl -H "Authorization: Bearer $TOKEN" http://localhost:8000/api/health

# Check metrics
curl -H "Authorization: Bearer $TOKEN" http://localhost:8000/api/metrics
```

---

## Post-Deployment Monitoring

### Key Metrics to Monitor

1. **Application Health**

   ```bash
   # Check every 5 minutes
   GET /health
   # Should return status: "healthy"
   ```

2. **Database Connectivity**
   - Monitor PostgreSQL connection pool
   - Alert on connection errors
   - Expected: < 100ms response time for `SELECT 1`

3. **Backup Status**
   - Check backup directory: `/var/backups/kinjo`
   - Expected: Daily backup file created at 2:00 AM UTC
   - Size: 50-500 MB depending on data

4. **Error Rates**
   - Monitor 5xx error logs
   - Alert if error rate > 1% of requests
   - Check `/api/metrics` for trends

5. **Performance**
   - Response time: Target < 200ms for most endpoints
   - CPU: Monitor for spikes > 80%
   - Memory: Monitor for leaks (should stabilize after warm-up)

### Troubleshooting

**Problem**: PostgreSQL connection errors

```
Solution:
1. Verify DATABASE_URL is correct
2. Check PostgreSQL is running: psql -U user -d kinjo -c "SELECT 1"
3. Check firewall: telnet host 5432
```

**Problem**: MFA locked out admin

```
Solution:
1. Use MFA bypass endpoint: POST /admin/users/{user_id}/mfa-bypass
2. Requires admin password verification
3. User must re-enroll MFA
```

**Problem**: Backup folder permission denied

```
Solution:
1. Verify backup directory permissions: ls -la /var/backups/kinjo
2. Must be readable/writable by app user: chmod 700 /var/backups/kinjo
3. Check disk space: df -h /var/backups
```

**Problem**: High error rates after deployment

```
Solution:
1. Check logs: tail -f /var/log/kinjo/app.log
2. Monitor health endpoint: GET /health
3. Check database status: GET /api/health (admin)
4. Verify all configuration variables are set correctly
```

---

## Security Checklist

Before going live:

- [ ] Environment set to `production`
- [ ] `DEBUG` set to `False`
- [ ] `API_DOCS_ENABLED` set to `False`
- [ ] `SECRET_KEY` is cryptographically strong (32+ chars)
- [ ] `DATABASE_URL` uses PostgreSQL
- [ ] HTTPS/TLS certificates installed
- [ ] Admin user created with strong password
- [ ] Backup directory configured and tested
- [ ] Rate limiting verified on auth endpoints
- [ ] Audit logging enabled
- [ ] CORS origins configured correctly
- [ ] Session cookie security headers set

---

## Maintenance

### Weekly

- [ ] Review error logs for patterns
- [ ] Verify backup files are created
- [ ] Check system metrics

### Monthly

- [ ] Review audit logs
- [ ] Test backup restore procedure
- [ ] Update dependencies (if applicable)

### Quarterly

- [ ] Security audit
- [ ] Performance tuning
- [ ] Database optimization

---

## Support & Escalation

**Issue Type**: Deployment/Configuration

- Check: environment variables, PostgreSQL connectivity, disk space

**Issue Type**: Authentication/Authorization

- Check: MFA status, user roles, permissions

**Issue Type**: Data Loss/Corruption

- Restore from automated backup: See backup_manager.py docs

**Issue Type**: Performance Degradation

- Check: System metrics (`/api/metrics`), database query logs

---

## Rollback Procedure

If critical issues occur:

```bash
# 1. Restore previous database snapshot
alembic downgrade -1

# 2. Deploy previous application version
git checkout <previous-tag>
pip install -r requirements.txt
gunicorn main:app --workers 4

# 3. Verify rollback
curl http://localhost:8000/health
```

---

_Deployment Guide v1.0 - KInJo v2.0.0_  
_Last Updated: April 25, 2026_
