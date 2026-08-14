#!/usr/bin/env bash
# =============================================================================
# KinJo canonical production deploy.
#
# Runs ON THE DROPLET. Holds an exclusive lock for the ENTIRE mutation window --
# backup, extraction, migration, image build, container recreation and health
# verification -- so two agents cannot deploy at once. Two concurrent
# `docker compose` runs took production down twice on 2026-08-12; a second
# deploy must now exit instead of racing.
#
# Usage (from the workstation):
#   git archive --format=tar -o /tmp/deploy.tar HEAD
#   scp -i <key> /tmp/deploy.tar root@<host>:/tmp/deploy.tar
#   ssh -i <key> root@<host> 'bash /opt/kinjo/scripts/deploy_locked.sh /tmp/deploy.tar <sha>'
#
# Exit codes:
#   0   deployed and verified
#   75  another deployment holds the lock (EX_TEMPFAIL) -- production untouched
#   1   deployment failed; see output
#
# NOTE: the deploy.sh at the repository root is obsolete. It targets /srv/kinjo,
# a virtualenv and systemd units that do not exist on this host, and asserts an
# Alembic head this project moved past. Do not run it.
# =============================================================================
set -euo pipefail

TARBALL="${1:-}"
RELEASE_SHA="${2:-unknown}"
APP_DIR="${KINJO_DIR:-/opt/kinjo}"
COMPOSE_FILE="docker-compose.prod.yml"
LOCK_FILE="/var/lock/kinjo-deploy.lock"
BACKUP_DIR="/var/backups/kinjo"
WEB_CONTAINER="kinjo-web-1"
KEEP_BACKUPS=5

log() { printf '[%s] %s\n' "$(date '+%H:%M:%S')" "$*"; }
die() { printf 'ERROR: %s\n' "$*" >&2; exit 1; }

[[ -n "$TARBALL" ]] || die "usage: $0 <tarball> [release-sha]"
[[ -f "$TARBALL" ]] || die "tarball not found: $TARBALL"
[[ -d "$APP_DIR" ]] || die "app dir not found: $APP_DIR"

# ---------------------------------------------------------------------------
# Acquire the lock BEFORE touching anything.
#
# fd 9 stays open for the life of this process, so the lock covers every step
# below and is released by the kernel even if the script is killed. -n makes a
# busy lock fail immediately rather than queue a second deploy behind the first.
# ---------------------------------------------------------------------------
# Append rather than truncate: `9>` empties the file on open, which wiped the
# holder's metadata before we had even discovered the lock was taken, so the
# refusal below could only ever report an empty holder.
exec 9>>"$LOCK_FILE"
if ! flock -n 9; then
  echo "DEPLOY_LOCK_BUSY: another deployment is in progress; production untouched."
  echo "holder: $(cat "$LOCK_FILE" 2>/dev/null || echo 'unknown')"
  exit 75
fi

# The lock is ours: now it is safe to replace the previous holder's metadata.
: >"$LOCK_FILE"
printf 'pid=%s started=%s sha=%s host=%s\n' \
  "$$" "$(date -Is)" "$RELEASE_SHA" "$(hostname)" >&9
log "lock acquired (pid $$, sha $RELEASE_SHA)"

TS="$(date +%Y%m%d_%H%M%S)"
cd "$APP_DIR"

# ---------------------------------------------------------------------------
# 1. Rollback point
# ---------------------------------------------------------------------------
if docker inspect "$WEB_CONTAINER" >/dev/null 2>&1; then
  ROLLBACK_TAG="kinjo-web:rollback-$TS"
  docker tag "$(docker inspect "$WEB_CONTAINER" --format '{{.Image}}')" "$ROLLBACK_TAG"
  log "rollback image: $ROLLBACK_TAG"
else
  log "no running web container; skipping rollback tag"
fi

# ---------------------------------------------------------------------------
# 2. Database backup when a migration is pending, or on request.
#    Backups are ~850MB, so taking one on every no-op deploy would fill the disk.
# ---------------------------------------------------------------------------
MIGRATION_PENDING=0

# (a) Does the INCOMING RELEASE add a revision this checkout does not have?
#
# This is the case that matters and the one the alembic check below cannot see.
# Asking the running container is asking the OLD image, which by definition does
# not contain the new revision file -- so `current` equals `head` and a release
# whose entire purpose is a migration reports "nothing pending". That is exactly
# backwards: the backup exists for schema changes, and it was being skipped for
# every one of them. Release 97ae00c (2026-08-13) added five indexes with no
# dump taken. Read the revision filenames out of the tarball instead.
NEW_REVISIONS="$(comm -13 \
  <(ls "$APP_DIR/alembic/versions"/*.py 2>/dev/null | xargs -r -n1 basename | sort) \
  <(tar tf "$TARBALL" | sed -n 's|^alembic/versions/\([^/]*\.py\)$|\1|p' | sort))"
if [[ -n "$NEW_REVISIONS" ]]; then
  MIGRATION_PENDING=1
  log "release adds revision file(s): $(echo "$NEW_REVISIONS" | tr '\n' ' ')"
fi

# (b) Is the database behind the code that is already running? Kept as a second
#     trigger -- it catches a migration that was added by an earlier deploy but
#     never applied.
if docker inspect "$WEB_CONTAINER" >/dev/null 2>&1; then
  CURRENT_REV="$(docker exec "$WEB_CONTAINER" alembic current 2>/dev/null | grep -v INFO | tr -d ' \n' || true)"
  HEAD_REV="$(docker exec "$WEB_CONTAINER" alembic heads 2>/dev/null | grep -v INFO | awk '{print $1}' | tr -d ' \n' || true)"
  [[ -n "$HEAD_REV" && "$CURRENT_REV" != *"$HEAD_REV"* ]] && MIGRATION_PENDING=1
fi
if [[ "$MIGRATION_PENDING" == "1" || "${FORCE_BACKUP:-0}" == "1" ]]; then
  mkdir -p "$BACKUP_DIR"
  log "migration pending or backup forced -- dumping database"
  docker exec kinjo_postgres pg_dump -U "${POSTGRES_USER:-kinjo_user}" -d "${POSTGRES_DB:-kinjo_db}" \
    > "$BACKUP_DIR/db-pre-deploy-$TS.sql"
  [[ -s "$BACKUP_DIR/db-pre-deploy-$TS.sql" ]] || die "database backup is empty -- refusing to continue"
  log "backup: $(stat -c %s "$BACKUP_DIR/db-pre-deploy-$TS.sql") bytes"
  # Keep the newest few so the disk stays bounded.
  ls -t "$BACKUP_DIR"/db-pre-deploy-*.sql 2>/dev/null | tail -n +$((KEEP_BACKUPS + 1)) | xargs -r rm -f
else
  log "no migration pending; skipping database dump"
fi

# ---------------------------------------------------------------------------
# 3. Extract the release. .env is not in the archive and must survive.
# ---------------------------------------------------------------------------
ENV_BEFORE="$(md5sum .env | awk '{print $1}')"
tar xf "$TARBALL" -C "$APP_DIR"
ENV_AFTER="$(md5sum .env | awk '{print $1}')"
[[ "$ENV_BEFORE" == "$ENV_AFTER" ]] || die ".env changed during extraction -- aborting"
log "release extracted; .env intact"

# ---------------------------------------------------------------------------
# 4. Build and recreate
# ---------------------------------------------------------------------------
log "building and recreating containers"
docker compose -f "$COMPOSE_FILE" up -d --build

# ---------------------------------------------------------------------------
# 5. Migrate after the new image is running, so the migration matches the code.
# ---------------------------------------------------------------------------
for _ in $(seq 1 30); do
  docker inspect "$WEB_CONTAINER" >/dev/null 2>&1 && break
  sleep 2
done
log "applying migrations"
# `alembic upgrade head | grep ... || true` swallowed the migration's exit code
# entirely: the pipeline's status is grep's, and `|| true` discarded even that.
# A migration could fail and the deploy would still print DEPLOY_OK. The most
# likely failure is a branched revision graph -- alembic refuses to upgrade when
# there are two heads, which is precisely how a bad down_revision presents, and
# the release would have shipped code expecting a schema that was never applied.
# Capture first, then filter, so a failure is fatal and the log still prints.
if ! MIGRATION_LOG="$(docker exec "$WEB_CONTAINER" alembic upgrade head 2>&1)"; then
  printf '%s\n' "$MIGRATION_LOG"
  die "alembic upgrade head failed -- schema NOT migrated; rollback image was tagged above"
fi
printf '%s\n' "$MIGRATION_LOG" | grep -viE '^INFO.*(Context|Will assume)' || true

# ---------------------------------------------------------------------------
# 6. Health verification -- still inside the lock.
# ---------------------------------------------------------------------------
HEALTHY=0
for _ in $(seq 1 30); do
  if curl -sSf -o /dev/null --max-time 5 http://127.0.0.1:80/ 2>/dev/null; then HEALTHY=1; break; fi
  sleep 3
done
[[ "$HEALTHY" == "1" ]] || die "web did not become healthy -- rollback image was tagged above"

for svc in kinjo-worker-1 kinjo-beat-1; do
  docker inspect "$svc" >/dev/null 2>&1 || log "WARNING: $svc is not running"
done

log "alembic: $(docker exec "$WEB_CONTAINER" alembic current 2>/dev/null | grep -v INFO | head -1)"
log "containers:"
docker ps --format '  {{.Names}} | {{.Status}}'
# ---------------------------------------------------------------------------
# 7. Seed manager module data if the database is fresh.
#    The seed script is idempotent: it skips when data already exists.
# ---------------------------------------------------------------------------
log "seeding manager module data"
if ! docker exec "$WEB_CONTAINER" python scripts/seed_manager_module.py 2>&1 | grep -qE '(\[SKIP\]|\[DONE\])'; then
  log "WARNING: seed script did not complete cleanly"
else
  log "seed complete"
fi

log "DEPLOY_OK sha=$RELEASE_SHA"
# Lock is released here when fd 9 closes with the process.
