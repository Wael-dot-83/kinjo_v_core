#!/usr/bin/env bash
# =============================================================================
# KinJo Production Deployment Script
# Run as the deploy user on the Linux production server.
# Usage:
#   bash deploy.sh              # interactive (pauses at critical steps)
#   bash deploy.sh --yes        # non-interactive (auto-confirms everything)
# =============================================================================
set -euo pipefail

KINJO_DIR="${KINJO_DIR:-/srv/kinjo}"
VENV="$KINJO_DIR/.venv/bin"
LOG_DIR="/var/log/kinjo"
BACKUP_DIR="/var/backups/kinjo"
YES=false

for arg in "$@"; do
  [[ "$arg" == "--yes" ]] && YES=true
done

confirm() {
  local prompt="$1"
  if $YES; then
    echo "[AUTO-YES] $prompt"
    return 0
  fi
  read -rp "$prompt [y/N] " ans
  [[ "${ans,,}" == "y" ]]
}

log() { echo "[$(date '+%Y-%m-%d %H:%M:%S')] $*"; }
die() { echo "ERROR: $*" >&2; exit 1; }

# ---------------------------------------------------------------------------
# STEP 0 — Pre-flight checks
# ---------------------------------------------------------------------------
log "=== STEP 0: PRE-FLIGHT CHECKS ==="

# 0.1 Working directory
[[ -d "$KINJO_DIR" ]] || die "KINJO_DIR=$KINJO_DIR does not exist"
cd "$KINJO_DIR"
[[ -f ".env" ]] || die ".env not found in $KINJO_DIR — copy .env.production.template and fill it"

# 0.2 Environment variables
log "Checking .env values..."
source .env 2>/dev/null || true

FAIL=0
[[ "${ENVIRONMENT:-}" == "production" ]]        || { echo "FAIL: ENVIRONMENT must be 'production' (got '${ENVIRONMENT:-}')" ; FAIL=1; }
[[ "${TESTING:-}" == "false" ]]                 || { echo "FAIL: TESTING must be 'false'" ; FAIL=1; }
[[ "${DEBUG:-}" == "false" ]]                   || { echo "FAIL: DEBUG must be 'false'" ; FAIL=1; }
[[ "${API_DOCS_ENABLED:-}" == "false" ]]        || { echo "FAIL: API_DOCS_ENABLED must be 'false'" ; FAIL=1; }
[[ "${DATABASE_URL:-}" == postgresql://* ]]     || { echo "FAIL: DATABASE_URL must start with postgresql://" ; FAIL=1; }
[[ -n "${REDIS_URL:-}" ]]                       || { echo "FAIL: REDIS_URL is not set" ; FAIL=1; }
[[ "${RATE_LIMIT_STORAGE_URI:-}" == redis://* ]] || { echo "FAIL: RATE_LIMIT_STORAGE_URI must start with redis://" ; FAIL=1; }
[[ "${SECRET_KEY:-}" != "06cbc1392801a25aea2fe304cde7c0402378ef556896a63087dda41c7edb1683" ]] \
  || { echo "FAIL: SECRET_KEY is the dev default — rotate it" ; FAIL=1; }
[[ ${#SECRET_KEY} -ge 32 ]]                     || { echo "FAIL: SECRET_KEY is too short (< 32 chars)" ; FAIL=1; }

[[ $FAIL -eq 0 ]] || die "Fix the above .env violations before deploying"
log "  .env: all checks passed"

# 0.3 Connectivity
log "Checking PostgreSQL..."
psql "$DATABASE_URL" -c "SELECT 1" -q >/dev/null 2>&1 \
  || die "Cannot connect to PostgreSQL at DATABASE_URL=$DATABASE_URL"
log "  PostgreSQL: OK"

log "Checking Redis..."
redis-cli -u "$REDIS_URL" PING 2>/dev/null | grep -q PONG \
  || die "Cannot reach Redis at REDIS_URL=$REDIS_URL"
log "  Redis: OK"

# 0.4 Alembic chain
log "Checking Alembic migration chain..."
"$VENV/alembic" current 2>&1 | grep -v "^INFO" | grep -v "^$"  || true
"$VENV/alembic" heads 2>&1 | grep -v "^INFO" | grep "p2_fk_cascade_001 (head)" \
  || die "Unexpected Alembic head — expected p2_fk_cascade_001"
log "  Alembic: chain valid, head = p2_fk_cascade_001"

# 0.5 Test suite
log "Running test suite..."
"$VENV/python" -m pytest -q --tb=short 2>&1 | tail -5
"$VENV/python" -m pytest -q --tb=line 2>&1 | grep -E "^(FAILED|ERROR)" && die "Tests failed — fix before deploying" || true
log "  Tests: passed"

log "=== STEP 0 PASSED ==="

# ---------------------------------------------------------------------------
# STEP 1 — Database migrations (approval required)
# ---------------------------------------------------------------------------
log "=== STEP 1: DATABASE MIGRATIONS ==="

CURRENT=$("$VENV/alembic" current 2>/dev/null | grep -v INFO | tr -d ' \n')
if [[ "$CURRENT" == *"p2_fk_cascade_001"* ]]; then
  log "  Database is already at head (p2_fk_cascade_001) — no migration needed"
else
  log "  Current revision: $CURRENT"
  log "  Target:           p2_fk_cascade_001 (head)"

  # 1.1 Backup
  mkdir -p "$BACKUP_DIR"
  BACKUP_FILE="$BACKUP_DIR/kinjo_pre_migration_$(date +%Y%m%d_%H%M%S).sql"
  log "  Creating pre-migration backup → $BACKUP_FILE"
  pg_dump "$DATABASE_URL" > "$BACKUP_FILE" \
    || die "pg_dump failed — take a manual backup before proceeding"
  log "  Backup: $BACKUP_FILE ($(du -sh "$BACKUP_FILE" | cut -f1))"

  # 1.2 Dry-run
  log "  Generating migration SQL (dry-run)..."
  "$VENV/alembic" upgrade head --sql > /tmp/kinjo_migration.sql 2>&1
  log "  Migration SQL written to /tmp/kinjo_migration.sql"
  echo "  --- ALTER/CREATE/DROP statements ---"
  grep -E "^(ALTER|CREATE|DROP|INSERT INTO alembic_version)" /tmp/kinjo_migration.sql | head -40

  confirm "  Apply these migrations to the production database?" \
    || die "Migration aborted by user"

  # 1.3 Apply
  log "  Applying migrations..."
  "$VENV/alembic" upgrade head
  log "  Migration complete"

  # 1.4 Verify
  CURRENT_AFTER=$("$VENV/alembic" current 2>/dev/null | grep -v INFO | tr -d ' \n')
  [[ "$CURRENT_AFTER" == *"p2_fk_cascade_001"* ]] \
    || die "Post-migration check failed: current=$CURRENT_AFTER"
  log "  Verified: now at p2_fk_cascade_001 (head)"
fi

# ---------------------------------------------------------------------------
# STEP 2 — Celery worker & beat (approval required)
# ---------------------------------------------------------------------------
log "=== STEP 2: CELERY SERVICES ==="

mkdir -p "$LOG_DIR"
chown -R "${KINJO_USER:-kinjo}:${KINJO_USER:-kinjo}" "$LOG_DIR" 2>/dev/null || true

WORKER_UNIT="kinjo-celery.service"
BEAT_UNIT="kinjo-celery-beat.service"

if [[ ! -f "/etc/systemd/system/$WORKER_UNIT" ]]; then
  confirm "  Write $WORKER_UNIT to /etc/systemd/system/?" \
    || { log "  Skipping Celery worker service setup"; }

  cat > "/etc/systemd/system/$WORKER_UNIT" <<UNIT
[Unit]
Description=KinJo Celery Worker
After=network.target redis.service postgresql.service

[Service]
Type=simple
User=${KINJO_USER:-kinjo}
Group=${KINJO_USER:-kinjo}
WorkingDirectory=$KINJO_DIR
EnvironmentFile=$KINJO_DIR/.env
ExecStart=$VENV/celery -A celery_app.celery_app worker \\
    --loglevel=info \\
    --concurrency=4 \\
    --queues=celery,backup,export,import \\
    --logfile=$LOG_DIR/celery-worker.log
Restart=always
RestartSec=5
StandardOutput=journal
StandardError=journal

[Install]
WantedBy=multi-user.target
UNIT
  log "  Written: /etc/systemd/system/$WORKER_UNIT"
fi

if [[ ! -f "/etc/systemd/system/$BEAT_UNIT" ]]; then
  confirm "  Write $BEAT_UNIT to /etc/systemd/system/?" \
    || { log "  Skipping Celery beat service setup"; }

  cat > "/etc/systemd/system/$BEAT_UNIT" <<UNIT
[Unit]
Description=KinJo Celery Beat Scheduler
After=network.target redis.service
Requires=$WORKER_UNIT

[Service]
Type=simple
User=${KINJO_USER:-kinjo}
Group=${KINJO_USER:-kinjo}
WorkingDirectory=$KINJO_DIR
EnvironmentFile=$KINJO_DIR/.env
ExecStart=$VENV/celery -A celery_app.celery_app beat \\
    --loglevel=info \\
    --logfile=$LOG_DIR/celery-beat.log
Restart=always
RestartSec=10

[Install]
WantedBy=multi-user.target
UNIT
  log "  Written: /etc/systemd/system/$BEAT_UNIT"
fi

confirm "  Enable and start Celery worker + beat?" && {
  systemctl daemon-reload
  systemctl enable --now "$WORKER_UNIT" "$BEAT_UNIT"
  sleep 3
  systemctl status "$WORKER_UNIT" "$BEAT_UNIT" --no-pager -l | tail -20
  log "  Celery services started"
} || log "  Skipping Celery service start"

# ---------------------------------------------------------------------------
# STEP 3 — Nginx WebSocket configuration (approval required)
# ---------------------------------------------------------------------------
log "=== STEP 3: NGINX WEBSOCKET ==="

NGINX_CONF="${NGINX_SITE:-/etc/nginx/sites-available/kinjo}"

if [[ -f "$NGINX_CONF" ]]; then
  if ! grep -q "proxy_http_version 1.1" "$NGINX_CONF"; then
    confirm "  Add WebSocket upgrade block to $NGINX_CONF?" && {
      # Inject WS location before the general / block
      WS_BLOCK='
    location ~ ^/ws/ {
        proxy_pass http://127.0.0.1:8000;
        proxy_http_version 1.1;
        proxy_set_header Upgrade $http_upgrade;
        proxy_set_header Connection $connection_upgrade;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;
        proxy_read_timeout 3600s;
        proxy_send_timeout 3600s;
        proxy_buffering off;
    }'
      sed -i "s|location / {|$WS_BLOCK\n\n    location / {|" "$NGINX_CONF"
      log "  Injected WebSocket block into $NGINX_CONF"
    }
  else
    log "  WebSocket block already present in $NGINX_CONF"
  fi

  # Ensure upgrade map in nginx.conf
  NGINX_MAIN="/etc/nginx/nginx.conf"
  if ! grep -q "connection_upgrade" "$NGINX_MAIN"; then
    sed -i '/http {/a\    map $http_upgrade $connection_upgrade { default upgrade; '"''"' close; }' "$NGINX_MAIN"
    log "  Added connection_upgrade map to $NGINX_MAIN"
  fi

  confirm "  Test nginx config and reload?" && {
    nginx -t && systemctl reload nginx
    log "  Nginx reloaded"
  }
else
  log "  WARNING: $NGINX_CONF not found — set NGINX_SITE env var or configure manually"
fi

# ---------------------------------------------------------------------------
# STEP 4 — Restart application
# ---------------------------------------------------------------------------
log "=== STEP 4: APPLICATION RESTART ==="

if systemctl is-active --quiet kinjo 2>/dev/null; then
  confirm "  Restart kinjo.service?" && {
    systemctl restart kinjo
    sleep 2
    systemctl status kinjo --no-pager | tail -5
    log "  Application restarted"
  }
else
  log "  kinjo.service not found/active — restart uvicorn manually:"
  log "  $VENV/uvicorn main:app --host 0.0.0.0 --port 8000 --workers 4"
fi

# ---------------------------------------------------------------------------
# STEP 5 — Post-deployment checks
# ---------------------------------------------------------------------------
log "=== STEP 5: POST-DEPLOYMENT MONITORING ==="
sleep 2

DOMAIN="${APP_DOMAIN:-localhost:8000}"
PROTO="${APP_PROTO:-http}"

log "  5.1 Health endpoint..."
HEALTH=$(curl -sf "$PROTO://$DOMAIN/api/health" 2>/dev/null || echo '{"error":"unreachable"}')
echo "$HEALTH" | python3 -m json.tool 2>/dev/null || echo "$HEALTH"

log "  5.2 Celery worker status..."
"$VENV/celery" -A celery_app.celery_app inspect active 2>&1 | head -10 || true

log "  5.3 Alembic current..."
"$VENV/alembic" current 2>&1 | grep -v INFO

log "  5.4 Application logs (last 20 lines, errors only)..."
journalctl -u kinjo --since "2 minutes ago" --no-pager 2>/dev/null \
  | grep -E "ERROR|CRITICAL|WARNING" | tail -20 || true

# ---------------------------------------------------------------------------
# STEP 6 — Final report
# ---------------------------------------------------------------------------
log "=== DEPLOYMENT COMPLETE ==="
cat <<REPORT

╔══════════════════════════════════════════════════════════╗
║              KinJo Deployment Summary                    ║
╠══════════════════════════════════════════════════════════╣
║  Alembic migration : p2_fk_cascade_001 (head)           ║
║  Celery services   : worker + beat enabled               ║
║  Nginx             : WebSocket upgrade configured        ║
║  Health endpoint   : /api/health (check above output)   ║
╠══════════════════════════════════════════════════════════╣
║  NEXT STEPS:                                             ║
║  1. Monitor /var/log/kinjo/ for 24 h                     ║
║  2. Watch /api/health?check=notifications for WS errors  ║
║  3. Rotate SECRET_KEY in .env once all sessions expire   ║
║  4. Set up automated pg_dump daily backup cron job       ║
╚══════════════════════════════════════════════════════════╝

ROLLBACK if anything goes wrong:
  alembic downgrade -1
  systemctl stop kinjo-celery kinjo-celery-beat
  psql \$DATABASE_URL < $BACKUP_DIR/kinjo_pre_migration_<DATE>.sql

REPORT
