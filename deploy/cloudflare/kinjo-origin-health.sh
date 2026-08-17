#!/usr/bin/env bash
# =============================================================================
# KinJo — origin/edge TLS health checks
#
# Detects the ways this configuration can degrade SILENTLY. Every check here
# exists because its failure mode produces either no symptom at all or a symptom
# that looks like something unrelated:
#
#   * certificate expiry            — works perfectly, then stops dead on a date
#   * Cloudflare allow-list drift   — a fraction of PoPs refused; looks flaky
#   * origin publicly reachable     — no symptom whatsoever, just exposure
#   * nginx config invalid on disk  — fine until the next reload/restart
#   * sync job stopped running      — the pin quietly ages
#
# Exit non-zero if any check fails, so systemd records the unit as failed and it
# surfaces in `systemctl list-units --failed` rather than scrolling past in a log.
#
# Install: /usr/local/sbin/kinjo-origin-health.sh (root, 0755)
# =============================================================================
set -uo pipefail

DOMAIN="${KINJO_DOMAIN:-www.kinjordan.org}"
ORIGIN_CERT="/opt/kinjo/secrets/origin/cert.pem"
STATE_DIR="/var/lib/kinjo/cloudflare"
STATUS_FILE="/var/lib/kinjo/origin-health.status"
CERT_WARN_DAYS=30
SYNC_STALE_HOURS=48

FAILURES=0
RESULTS=()

ok()   { RESULTS+=("OK       $*");   printf 'OK       %s\n' "$*"; }
fail() { RESULTS+=("FAIL     $*"); printf 'FAIL     %s\n' "$*" >&2; FAILURES=$((FAILURES+1)); }
warn() { RESULTS+=("WARN     $*"); printf 'WARN     %s\n' "$*"; }

# --- 1. Public site reachable through Cloudflare -----------------------------
code="$(curl -sS -o /dev/null -w '%{http_code}' --max-time 20 "https://$DOMAIN/health" 2>/dev/null || echo 000)"
if [[ "$code" == "200" ]]; then ok "public site https://$DOMAIN/health -> 200"
else fail "public site https://$DOMAIN/health -> $code"; fi

# --- 2. No Cloudflare origin-TLS errors --------------------------------------
# 525 = TLS handshake with origin failed; 526 = origin cert failed validation.
# These appear only once Full (strict) is on, which is exactly when a bad origin
# certificate stops being harmless.
case "$code" in
  525) fail "Cloudflare 525 — TLS handshake to origin failing" ;;
  526) fail "Cloudflare 526 — origin certificate rejected by Cloudflare" ;;
  *)   ok "no Cloudflare 525/526 on the public path" ;;
esac

# --- 3. Redirect sanity (loop detection) -------------------------------------
hops="$(curl -sS -o /dev/null -L --max-redirs 5 -w '%{num_redirects}' --max-time 25 "http://$DOMAIN/health" 2>/dev/null || echo 99)"
final="$(curl -sS -o /dev/null -L --max-redirs 5 -w '%{http_code}' --max-time 25 "http://$DOMAIN/health" 2>/dev/null || echo 000)"
if [[ "$final" == "200" && "$hops" -le 2 ]]; then ok "no redirect loop (hops=$hops, final=$final)"
else fail "redirect anomaly: hops=$hops final=$final"; fi

# --- 4. Origin certificate: expiry + hostname coverage -----------------------
if [[ -r "$ORIGIN_CERT" ]]; then
  end_epoch="$(date -d "$(openssl x509 -in "$ORIGIN_CERT" -noout -enddate 2>/dev/null | cut -d= -f2)" +%s 2>/dev/null || echo 0)"
  now_epoch="$(date +%s)"
  days_left=$(( (end_epoch - now_epoch) / 86400 ))
  if (( end_epoch == 0 )); then fail "origin certificate unparseable"
  elif (( days_left < 0 )); then fail "origin certificate EXPIRED ($days_left days)"
  elif (( days_left < CERT_WARN_DAYS )); then warn "origin certificate expires in $days_left days"
  else ok "origin certificate valid for $days_left more days"; fi

  sans="$(openssl x509 -in "$ORIGIN_CERT" -noout -ext subjectAltName 2>/dev/null | tr -d ' ')"
  if grep -q "DNS:kinjordan.org" <<< "$sans" && grep -q "DNS:\*.kinjordan.org" <<< "$sans"; then
    ok "origin certificate covers kinjordan.org and *.kinjordan.org"
  else fail "origin certificate hostname coverage wrong: $sans"; fi
else
  fail "origin certificate not readable at $ORIGIN_CERT"
fi

# --- 5. Origin TLS actually serving on :443 ----------------------------------
served="$(echo | timeout 15 openssl s_client -connect 127.0.0.1:443 -servername "$DOMAIN" 2>/dev/null | openssl x509 -noout -subject 2>/dev/null || true)"
if grep -qi "CloudFlare Origin Certificate" <<< "$served"; then ok "origin :443 presents the Cloudflare Origin certificate"
else fail "origin :443 did not present the expected certificate (got: ${served:-nothing})"; fi

# --- 6. nginx configuration valid --------------------------------------------
if docker exec kinjo_nginx nginx -t >/dev/null 2>&1; then ok "nginx config valid"
else fail "nginx config test FAILED — a reload or restart would drop the site"; fi

# --- 7. Origin must NOT be reachable except via Cloudflare -------------------
# Checked from the host's own public interface toward itself would traverse
# OUTPUT, not FORWARD, and would wrongly pass. So assert on the firewall state
# instead: deny-by-default present and the allow-list populated.
for port in 8000 443; do
  if iptables -C DOCKER-USER -p tcp -m tcp --dport "$port" -j DROP 2>/dev/null; then
    n="$(iptables -S DOCKER-USER | grep -c -- "--dport $port -j ACCEPT")"
    if (( n >= 5 )); then ok "origin :$port deny-by-default with $n allow rules"
    else fail "origin :$port has only $n allow rules — allow-list looks emptied"; fi
  else
    fail "origin :$port has NO deny rule — origin is publicly reachable"
  fi
done

# --- 8. Cloudflare allow-list sync freshness ---------------------------------
if [[ -r "$STATE_DIR/last-success" ]]; then
  last="$(cat "$STATE_DIR/last-success")"
  age_h=$(( ( $(date +%s) - $(date -d "$last" +%s) ) / 3600 ))
  if (( age_h <= SYNC_STALE_HOURS )); then ok "Cloudflare IP sync last succeeded ${age_h}h ago"
  else fail "Cloudflare IP sync stale: last success ${age_h}h ago (>${SYNC_STALE_HOURS}h)"; fi
else
  warn "Cloudflare IP sync has no recorded success yet"
fi

# --- Summary -----------------------------------------------------------------
mkdir -p "$(dirname "$STATUS_FILE")"
{
  printf 'checked_at=%s\n' "$(date -Is)"
  printf 'failures=%s\n' "$FAILURES"
  printf '%s\n' "${RESULTS[@]}"
} > "$STATUS_FILE"

echo "----"
if (( FAILURES > 0 )); then
  echo "RESULT: $FAILURES check(s) FAILED"
  exit 1
fi
echo "RESULT: all checks passed"
exit 0
