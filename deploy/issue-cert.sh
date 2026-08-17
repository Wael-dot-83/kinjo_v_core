#!/usr/bin/env bash
# =============================================================================
# KinJo — first-time TLS certificate issuance
#
# Run ONCE per domain, before the first `up` with docker-compose.edge.yml.
#
# Why this is a separate script and not part of the certbot service: nginx
# refuses to start without a certificate file to load, and certbot's webroot
# challenge needs a running nginx to serve it. Bootstrapping through the webroot
# is a deadlock. This uses the standalone challenge (certbot binds :80 itself),
# which needs nothing running.
#
# Usage:
#   sudo bash deploy/issue-cert.sh kinjo.example.com admin@example.com
#   sudo bash deploy/issue-cert.sh kinjo.example.com admin@example.com --staging
# =============================================================================
set -euo pipefail

DOMAIN="${1:-}"
EMAIL="${2:-}"
STAGING_FLAG=""

for arg in "$@"; do
  [[ "$arg" == "--staging" ]] && STAGING_FLAG="--staging"
done

die() { echo "ERROR: $*" >&2; exit 1; }

[[ -n "$DOMAIN" ]] || die "usage: $0 <domain> <email> [--staging]"
[[ -n "$EMAIL"  ]] || die "usage: $0 <domain> <email> [--staging]"
command -v docker >/dev/null || die "docker is not installed — run deploy/harden-droplet.sh first"

COMPOSE_PROJECT="$(basename "$(pwd)")"
CERT_VOLUME="${COMPOSE_PROJECT}_kinjo_certs"
ACME_VOLUME="${COMPOSE_PROJECT}_kinjo_acme"

echo "==> Domain:      $DOMAIN"
echo "==> Contact:     $EMAIL"
echo "==> Cert volume: $CERT_VOLUME"
[[ -n "$STAGING_FLAG" ]] && echo "==> MODE: STAGING (certificate will NOT be trusted by browsers)"

# Let's Encrypt allows 5 failed validations per account/hostname/hour and 5
# duplicate certificates per week. Getting DNS wrong and retrying burns that
# budget fast, so confirm the record resolves to THIS host before asking.
echo "==> Checking that $DOMAIN resolves to this droplet..."
RESOLVED="$(getent hosts "$DOMAIN" | awk '{print $1}' | head -1 || true)"
PUBLIC_IP="$(curl -fsS --max-time 10 https://api.ipify.org || true)"
if [[ -z "$RESOLVED" ]]; then
  die "$DOMAIN does not resolve. Create the DNS A record and wait for propagation."
fi
if [[ -n "$PUBLIC_IP" && "$RESOLVED" != "$PUBLIC_IP" ]]; then
  echo "WARNING: $DOMAIN resolves to $RESOLVED but this host is $PUBLIC_IP."
  echo "         If DNS is proxied (Cloudflare orange cloud), issuance over HTTP-01"
  echo "         will fail — grey-cloud the record until the certificate exists."
  read -rp "Continue anyway? [y/N] " ans
  [[ "${ans,,}" == "y" ]] || exit 1
fi

docker volume create "$CERT_VOLUME" >/dev/null
docker volume create "$ACME_VOLUME" >/dev/null

# :80 must be free for the standalone challenge.
if ss -tln 2>/dev/null | grep -q ':80 '; then
  echo "==> Port 80 is in use; stopping the nginx container for issuance..."
  docker stop kinjo_nginx >/dev/null 2>&1 || true
fi

echo "==> Requesting certificate..."
docker run --rm \
  -p 80:80 \
  -v "$CERT_VOLUME:/etc/letsencrypt" \
  -v "$ACME_VOLUME:/var/www/certbot" \
  certbot/certbot:latest certonly \
    --standalone \
    $STAGING_FLAG \
    --non-interactive \
    --agree-tos \
    --email "$EMAIL" \
    -d "$DOMAIN" \
    -d "www.$DOMAIN" \
    --key-type ecdsa \
    --rsa-key-size 4096

echo "==> Certificate issued. Verifying the files nginx will load..."
docker run --rm -v "$CERT_VOLUME:/etc/letsencrypt:ro" alpine:3 \
  sh -c "ls -l /etc/letsencrypt/live/$DOMAIN/fullchain.pem \
                /etc/letsencrypt/live/$DOMAIN/privkey.pem \
                /etc/letsencrypt/live/$DOMAIN/chain.pem"

cat <<EOF

==> Done. Next:
    1. Set KINJO_DOMAIN=$DOMAIN in .env
    2. docker compose -f docker-compose.prod.yml -f docker-compose.edge.yml up -d
    3. Verify from OUTSIDE the droplet:
         curl -sSI https://$DOMAIN/health
         curl -sSI http://$DOMAIN/health      # expect 301 to https
EOF
