#!/usr/bin/env bash
# =============================================================================
# KinJo — Cloudflare Origin CA certificate/key rotation
#
# Two-phase so the private key NEVER leaves the production host and never passes
# through a chat window, a clipboard, a ticket, or shell history:
#
#   Phase 1 (this host, no credentials needed):
#       kinjo-origin-cert-rotate.sh generate
#     Creates a new private key + CSR under /opt/kinjo/secrets/origin/pending/.
#     Prints ONLY the CSR, which is public by construction.
#
#   Phase 2 (needs the Cloudflare dashboard or an Origin CA credential):
#     Submit that CSR at Cloudflare > SSL/TLS > Origin Server > Create
#     Certificate > "I have my own private key and CSR". Save the returned
#     certificate to a file, then:
#       kinjo-origin-cert-rotate.sh install /path/to/new-cert.pem
#
# install is rollback-safe: it validates everything BEFORE touching the live
# certificate, keeps a timestamped backup, verifies what is actually served on
# :443 afterwards, and restores automatically if verification fails. The old key
# is retired only after the new one is proven to be serving.
#
# Usage: kinjo-origin-cert-rotate.sh {generate|csr|install <cert>|status}
# =============================================================================
set -euo pipefail

SECRETS_DIR="/opt/kinjo/secrets/origin"
PENDING_DIR="$SECRETS_DIR/pending"
BACKUP_DIR="$SECRETS_DIR/retired"
DOMAIN="kinjordan.org"
SNI_HOST="www.${DOMAIN}"
NGINX_CONTAINER="kinjo_nginx"

log() { printf '[%s] %s\n' "$(date -Is)" "$*"; }
die() { printf '[%s] ERROR: %s\n' "$(date -Is)" "$*" >&2; exit 1; }

[[ $EUID -eq 0 ]] || die "must run as root (secrets are 0600 root-owned)"

cmd_generate() {
  install -d -m 700 -o root -g root "$PENDING_DIR"
  local key="$PENDING_DIR/key.pem" csr="$PENDING_DIR/origin.csr"

  if [[ -f "$key" ]]; then
    die "a pending key already exists at $key — finish or remove that rotation first"
  fi

  log "generating a new 2048-bit RSA key on this host (it will not be printed)"
  # Cloudflare Origin CA accepts RSA 2048; keep parity with the current cert.
  openssl req -new -newkey rsa:2048 -nodes \
      -keyout "$key" \
      -out "$csr" \
      -subj "/C=US/O=KinJo/CN=${DOMAIN}" \
      -addext "subjectAltName=DNS:${DOMAIN},DNS:*.${DOMAIN}" 2>/dev/null \
    || die "key/CSR generation failed"

  chmod 600 "$key" "$csr"; chown root:root "$key" "$csr"

  # Prove the CSR carries both names before anyone submits it — a CSR missing
  # the wildcard produces a certificate that fails on www and is only discovered
  # after it is installed.
  local sans
  sans="$(openssl req -in "$csr" -noout -text | grep -A1 "Subject Alternative Name" | tail -1 | tr -d ' ')"
  grep -q "DNS:${DOMAIN}" <<< "$sans" || die "CSR is missing DNS:${DOMAIN}"
  grep -q "DNS:\*.${DOMAIN}" <<< "$sans" || die "CSR is missing DNS:*.${DOMAIN}"
  log "CSR SANs verified: $sans"

  echo
  echo "=== SUBMIT THIS CSR TO CLOUDFLARE (public data, safe to copy) ==="
  cat "$csr"
  echo "=== END CSR ==="
  echo
  log "private key stored at $key (0600 root) — never print or copy it"
  log "next: kinjo-origin-cert-rotate.sh install <cert-from-cloudflare.pem>"
}

cmd_install() {
  local new_cert="${1:-}"
  [[ -n "$new_cert" && -r "$new_cert" ]] || die "usage: install <path-to-new-cert.pem>"
  local new_key="$PENDING_DIR/key.pem"
  [[ -r "$new_key" ]] || die "no pending key at $new_key — run 'generate' first"

  # ---- Validate BEFORE touching anything live -------------------------------
  log "validating candidate certificate"
  openssl x509 -in "$new_cert" -noout >/dev/null 2>&1 || die "candidate is not a parseable PEM certificate"
  openssl rsa  -in "$new_key"  -noout >/dev/null 2>&1 || die "pending key is not a parseable PEM key"

  local cmod kmod
  cmod="$(openssl x509 -in "$new_cert" -noout -modulus | openssl sha256)"
  kmod="$(openssl rsa  -in "$new_key"  -noout -modulus | openssl sha256)"
  [[ "$cmod" == "$kmod" ]] || die "certificate and pending key DO NOT MATCH — refusing"
  log "  key/certificate modulus match: OK"

  local sans
  sans="$(openssl x509 -in "$new_cert" -noout -ext subjectAltName | tr -d ' ')"
  grep -q "DNS:${DOMAIN}" <<< "$sans"    || die "certificate missing DNS:${DOMAIN}"
  grep -q "DNS:\*.${DOMAIN}" <<< "$sans" || die "certificate missing DNS:*.${DOMAIN}"
  log "  SANs: $sans"

  local end_epoch now_epoch
  end_epoch="$(date -d "$(openssl x509 -in "$new_cert" -noout -enddate | cut -d= -f2)" +%s)"
  now_epoch="$(date +%s)"
  (( end_epoch > now_epoch + 86400 )) || die "certificate expires within 24h — refusing"
  log "  valid for $(( (end_epoch - now_epoch) / 86400 )) days"

  # ---- Backup, then swap ----------------------------------------------------
  local ts; ts="$(date +%Y%m%d_%H%M%S)"
  install -d -m 700 -o root -g root "$BACKUP_DIR"
  cp -a "$SECRETS_DIR/cert.pem" "$BACKUP_DIR/cert.pem.$ts"
  cp -a "$SECRETS_DIR/key.pem"  "$BACKUP_DIR/key.pem.$ts"
  log "current material backed up to $BACKUP_DIR/*.$ts"

  restore() {
    log "!!! restoring previous certificate/key"
    cp -a "$BACKUP_DIR/cert.pem.$ts" "$SECRETS_DIR/cert.pem"
    cp -a "$BACKUP_DIR/key.pem.$ts"  "$SECRETS_DIR/key.pem"
    chmod 600 "$SECRETS_DIR/cert.pem" "$SECRETS_DIR/key.pem"
    docker exec "$NGINX_CONTAINER" nginx -s reload >/dev/null 2>&1 || true
    log "restore complete"
  }

  # Write via temp + mv so nginx can never observe a half-written file.
  install -m 600 -o root -g root "$new_cert" "$SECRETS_DIR/.cert.pem.new"
  install -m 600 -o root -g root "$new_key"  "$SECRETS_DIR/.key.pem.new"
  mv -f "$SECRETS_DIR/.cert.pem.new" "$SECRETS_DIR/cert.pem"
  mv -f "$SECRETS_DIR/.key.pem.new"  "$SECRETS_DIR/key.pem"
  log "new material staged into $SECRETS_DIR"

  # ---- Validate config, then GRACEFUL reload (no restart) -------------------
  if ! docker exec "$NGINX_CONTAINER" nginx -t >/dev/null 2>&1; then
    restore; die "nginx config test failed with the new certificate — restored"
  fi
  log "  nginx config test: OK"
  docker exec "$NGINX_CONTAINER" nginx -s reload >/dev/null 2>&1 \
    || { restore; die "nginx reload failed — restored"; }
  log "  nginx reloaded gracefully (no restart, connections preserved)"
  sleep 3

  # ---- Prove the NEW certificate is what is actually served ----------------
  local served_serial new_serial
  new_serial="$(openssl x509 -in "$SECRETS_DIR/cert.pem" -noout -serial | cut -d= -f2)"
  served_serial="$(echo | timeout 15 openssl s_client -connect 127.0.0.1:443 -servername "$SNI_HOST" 2>/dev/null | openssl x509 -noout -serial 2>/dev/null | cut -d= -f2)"
  if [[ "$served_serial" != "$new_serial" ]]; then
    restore; die "origin :443 is not serving the new certificate (served=$served_serial expected=$new_serial) — restored"
  fi
  log "  origin :443 is serving the new certificate (serial $new_serial)"

  # ---- Prove the edge still works end to end -------------------------------
  local code
  code="$(curl -sS -o /dev/null -w '%{http_code}' --max-time 25 "https://${SNI_HOST}/health" || echo 000)"
  if [[ "$code" != "200" ]]; then
    restore; die "public site returned $code after rotation — restored"
  fi
  log "  public site still 200 through Cloudflare"

  # ---- Retire the old material only now ------------------------------------
  rm -f "$PENDING_DIR/key.pem" "$PENDING_DIR/origin.csr"
  rmdir "$PENDING_DIR" 2>/dev/null || true
  log "rotation COMPLETE. Previous key/cert retained (0600) under $BACKUP_DIR for rollback."
  log "Delete $BACKUP_DIR/*.$ts once you are satisfied, and revoke the old certificate in Cloudflare."
}

cmd_csr() {
  # Re-print the pending CSR. Needed because `generate` deliberately refuses once
  # a pending key exists (regenerating would orphan the key and silently produce
  # a certificate that cannot be installed), and `status` shows the live cert
  # rather than the request. Without this there was no way to recover the CSR for
  # submission except reading the file by hand.
  local csr="$PENDING_DIR/origin.csr"
  [[ -r "$csr" ]] || die "no pending CSR at $csr — run '$0 generate' first"
  openssl req -in "$csr" -noout -verify >/dev/null 2>&1 || die "pending CSR is not a valid PEM request"
  local sans
  sans="$(openssl req -in "$csr" -noout -text | grep -A1 "Subject Alternative Name" | tail -1 | tr -d ' ')"
  log "pending CSR SANs: $sans"
  echo
  echo "=== SUBMIT THIS CSR TO CLOUDFLARE (public data, safe to copy) ==="
  cat "$csr"
  echo "=== END CSR ==="
}

cmd_status() {
  echo "=== live certificate ==="
  openssl x509 -in "$SECRETS_DIR/cert.pem" -noout -serial -subject -dates -ext subjectAltName 2>/dev/null | sed 's/^/  /'
  echo "=== served on :443 ==="
  echo | timeout 15 openssl s_client -connect 127.0.0.1:443 -servername "$SNI_HOST" 2>/dev/null \
    | openssl x509 -noout -serial -dates 2>/dev/null | sed 's/^/  /'
  echo "=== pending rotation ==="
  [[ -f "$PENDING_DIR/key.pem" ]] && echo "  pending key present (awaiting certificate)" || echo "  none"
}

case "${1:-}" in
  generate) cmd_generate ;;
  install)  shift; cmd_install "${1:-}" ;;
  csr)      cmd_csr ;;
  status)   cmd_status ;;
  *) die "usage: $0 {generate|csr|install <cert.pem>|status}" ;;
esac
