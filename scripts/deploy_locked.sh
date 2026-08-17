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

# ---------------------------------------------------------------------------
# Which compose files to drive.
#
# Deploys must drive the SAME set the host actually runs -- a deploy that omits
# an overlay tears its containers down as orphans and takes the site offline
# while reporting success. That much was already true; what was wrong was
# *guessing* the set.
#
# The overlay used to be hardcoded to docker-compose.edge.yml, and by
# 2026-08-17 that was no longer what production ran. The live stack is
# prod + docker-compose.cf-origin.yml (nginx fronting Cloudflare with an Origin
# CA certificate, no certbot). Deploying prod + edge would have reconfigured
# kinjo_nginx onto Let's Encrypt paths and started a certbot container against
# a host that does not use one. KINJO_EDGE=0 was no escape either: that drops
# to prod alone and orphans nginx alone.
#
# The running container's compose label records exactly which files created the
# stack, so ask it rather than guess. Falls back to the old auto-detect only
# when there is no container to ask (first deploy onto a bare host), and
# KINJO_COMPOSE_FILES overrides both for a deliberate stack change.
# ---------------------------------------------------------------------------
COMPOSE_ARGS=(-f "$COMPOSE_FILE")
if [[ -n "${KINJO_COMPOSE_FILES:-}" ]]; then
  COMPOSE_ARGS=()
  IFS=',' read -r -a _requested <<< "$KINJO_COMPOSE_FILES"
  for _f in "${_requested[@]}"; do
    _f="$(basename "${_f// /}")"
    [[ -n "$_f" ]] || continue
    [[ -f "$APP_DIR/$_f" ]] || die "KINJO_COMPOSE_FILES names a missing file: $_f"
    COMPOSE_ARGS+=(-f "$_f")
  done
  [[ ${#COMPOSE_ARGS[@]} -gt 0 ]] || die "KINJO_COMPOSE_FILES resolved to no files"
  log "compose files: from KINJO_COMPOSE_FILES"
else
  _running_files="$(docker inspect "$WEB_CONTAINER" \
    --format '{{index .Config.Labels "com.docker.compose.project.config_files"}}' 2>/dev/null || true)"
  if [[ -n "$_running_files" ]]; then
    COMPOSE_ARGS=()
    IFS=',' read -r -a _running <<< "$_running_files"
    for _f in "${_running[@]}"; do
      _f="$(basename "${_f// /}")"
      [[ -n "$_f" && -f "$APP_DIR/$_f" ]] || continue
      COMPOSE_ARGS+=(-f "$_f")
    done
    [[ ${#COMPOSE_ARGS[@]} -gt 0 ]] \
      || die "the running stack's compose files are not present in $APP_DIR: $_running_files"
    log "compose files: adopted from the running $WEB_CONTAINER label"
  else
    # No container to ask: bare host / first deploy. Keep the previous
    # behaviour so a fresh install still brings the TLS edge up.
    EDGE_FILE="docker-compose.edge.yml"
    if [[ "${KINJO_EDGE:-auto}" != "0" && -f "$APP_DIR/$EDGE_FILE" ]]; then
      COMPOSE_ARGS+=(-f "$EDGE_FILE")
    fi
    log "compose files: no running container; auto-detected"
  fi
fi

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
# 3b. Bind-mount ownership for the non-root container.
#
# The image used to run as root, so ./data (bind-mounted to /app/data) is owned
# by uid 0 -- and data/attachments is mode dr-x---r-x, which grants a non-root
# uid no write bit at all. The hardened image runs as uid 10001, so without this
# step the containers start cleanly, pass their health check, serve pages, and
# then fail every attachment, upload and export write at runtime. A deploy that
# looks entirely successful while silently breaking file storage is exactly the
# failure mode worth spending a few lines to prevent.
#
# Idempotent: after the first deploy the ownership already matches and this is a
# no-op. Runs BEFORE the containers are recreated so there is no window in which
# the new image is live against an unwritable directory.
# ---------------------------------------------------------------------------
APP_UID="${KINJO_APP_UID:-10001}"
APP_GID="${KINJO_APP_GID:-10001}"
if [[ -d "$APP_DIR/data" ]]; then
  CURRENT_OWNER="$(stat -c '%u:%g' "$APP_DIR/data")"
  if [[ "$CURRENT_OWNER" != "$APP_UID:$APP_GID" ]]; then
    log "data/ is owned by $CURRENT_OWNER; chowning to $APP_UID:$APP_GID for the non-root image"
    chown -R "$APP_UID:$APP_GID" "$APP_DIR/data"
    # attachments/ ships without an owner write bit (dr-x---r-x). Ownership alone
    # does not make it writable, so restore u+rwX as well.
    chmod -R u+rwX "$APP_DIR/data"
    log "data/ ownership now $(stat -c '%u:%g' "$APP_DIR/data")"
  else
    log "data/ ownership already $APP_UID:$APP_GID"
  fi
fi

# ---------------------------------------------------------------------------
# 4. Build and recreate
# ---------------------------------------------------------------------------
log "building and recreating containers (compose: ${COMPOSE_ARGS[*]})"
docker compose "${COMPOSE_ARGS[@]}" up -d --build

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
# Probe the APP container directly rather than host :80. Once nginx terminates
# TLS, host :80 answers "301 -> https" without the app being involved at all, and
# `curl -f` treats a 301 as success -- so the old check would have gone green
# against a completely dead application. Hitting /health inside the container
# proves the thing we actually care about is up.
HEALTHY=0
for _ in $(seq 1 30); do
  if docker exec "$WEB_CONTAINER" curl -sSf -o /dev/null --max-time 5 \
       http://127.0.0.1:8000/health 2>/dev/null; then HEALTHY=1; break; fi
  sleep 3
done
[[ "$HEALTHY" == "1" ]] || die "web did not become healthy -- rollback image was tagged above"

# With the edge deployed, also prove the public path terminates TLS and reaches
# the app. Non-fatal on its own: certificate problems must be loud but must not
# trigger a rollback of an application that is demonstrably healthy above.
if [[ " ${COMPOSE_ARGS[*]} " == *"$EDGE_FILE"* ]]; then
  if curl -sSf -o /dev/null --max-time 10 https://127.0.0.1/health \
       --resolve "${KINJO_DOMAIN:-localhost}:443:127.0.0.1" 2>/dev/null; then
    log "edge: https health OK"
  else
    log "WARNING: https health probe failed -- check 'docker logs kinjo_nginx' and certificate validity"
  fi
fi

for svc in kinjo-worker-1 kinjo-beat-1; do
  docker inspect "$svc" >/dev/null 2>&1 || log "WARNING: $svc is not running"
done

log "alembic: $(docker exec "$WEB_CONTAINER" alembic current 2>/dev/null | grep -v INFO | head -1)"
log "containers:"
docker ps --format '  {{.Names}} | {{.Status}}'
# ---------------------------------------------------------------------------
# 7. Seed manager module data -- OPT-IN.
#
# Was unconditional. Three reasons it is not:
#
#   * `seed_manager_module.py --force` calls Base.metadata.drop_all(). Nothing
#     in the deploy passes --force, but a script that can erase every table
#     does not belong on the automatic path of every production release.
#   * On a populated database the script prints [SKIP] and returns without
#     creating anything, so running it here cannot achieve what it looks like
#     it achieves -- it only ever fires on an empty database.
#   * It prints the seeded account passwords on stdout, which this step piped
#     straight into the deploy log.
#
# Set SEED_MANAGER_MODULE=1 to run it deliberately.
# ---------------------------------------------------------------------------
if [[ "${SEED_MANAGER_MODULE:-0}" == "1" ]]; then
  log "seeding manager module data (SEED_MANAGER_MODULE=1)"
  # Capture rather than pipe into `grep -q`: with `set -o pipefail`, grep exits
  # on its first match and SIGPIPEs python, so the pipeline returned non-zero on
  # SUCCESS and logged a warning. Worse, on a real failure grep -q swallowed the
  # traceback and left nothing to diagnose.
  if SEED_LOG="$(docker exec -e SEED_MANAGER_MODULE=1 "$WEB_CONTAINER" \
                 python scripts/seed_manager_module.py 2>&1)"; then
    # Never echo the credential block into the deploy log.
    printf '%s\n' "$SEED_LOG" | grep -E '^\s*\[(OK|SKIP|DONE|WIPE)\]' || true
    log "seed finished"
  else
    printf '%s\n' "$SEED_LOG" | grep -viE 'password|Test@' || true
    log "WARNING: seed script failed (credential lines withheld)"
  fi
else
  log "seed skipped (set SEED_MANAGER_MODULE=1 to run scripts/seed_manager_module.py)"
fi

log "DEPLOY_OK sha=$RELEASE_SHA"
# Lock is released here when fd 9 closes with the process.
