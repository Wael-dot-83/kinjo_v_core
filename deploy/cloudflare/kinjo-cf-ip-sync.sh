#!/usr/bin/env bash
# =============================================================================
# KinJo — Cloudflare origin allow-list synchroniser
#
# The origin firewall admits only Cloudflare. That list is pinned, so it goes
# stale silently: if Cloudflare adds an edge range, those PoPs start getting
# refused and a fraction of users see errors that look like nothing in
# particular. This keeps the pin current.
#
# Install:  /usr/local/sbin/kinjo-cf-ip-sync.sh  (root, 0755)
# Run:      kinjo-cf-ip-sync.sh [--dry-run]
# Schedule: kinjo-cf-ip-sync.timer (daily)
#
# Design notes that matter:
#
#  * INCREMENTAL, never flush-and-rebuild. A rebuild has a window — however
#    short — in which the DROP rule is absent and the origin is open to the
#    whole internet. This adds and removes individual ACCEPT rules and never
#    touches the DROP, so the deny-by-default posture holds at every instant.
#
#  * The DNAT for a published Docker port rewrites the destination port BEFORE
#    the filter chain, so DOCKER-USER matches the CONTAINER port (8000 for web,
#    443 for nginx), not the host port. Matching 80 here would silently match
#    nothing and leave the origin open.
#
#  * Validation happens before any mutation. An empty or malformed response
#    (captive portal, proxy error page, truncated transfer) must never be able
#    to empty the allow-list — that would lock Cloudflare out and take the site
#    down. On any validation failure the previous known-good list is preserved
#    and the script exits non-zero without touching the firewall.
# =============================================================================
set -euo pipefail

CF_V4_URL="https://www.cloudflare.com/ips-v4"
CF_V6_URL="https://www.cloudflare.com/ips-v6"
STATE_DIR="/var/lib/kinjo/cloudflare"
LOCK_FILE="/var/lock/kinjo-cf-ip-sync.lock"
RULES_SAVE="/etc/iptables/rules.v4"
# Container ports, not host ports — see the DNAT note above.
PORTS=(8000 443)
# Docker-internal traffic (nginx -> web, worker -> web) must never be caught.
INTERNAL_NET="172.16.0.0/12"
# Sanity bounds. Cloudflare publishes ~15 IPv4 and ~7 IPv6 ranges; a response
# far outside this is a signal that we fetched something that is not the list.
MIN_RANGES=5
MAX_RANGES=200

DRY_RUN=false
[[ "${1:-}" == "--dry-run" ]] && DRY_RUN=true

log() { printf '[%s] %s\n' "$(date -Is)" "$*"; }
die() { printf '[%s] ERROR: %s\n' "$(date -Is)" "$*" >&2; exit 1; }

# --- Single instance ---------------------------------------------------------
# Two concurrent runs could interleave add/remove and leave a partial list.
exec 9>>"$LOCK_FILE"
flock -n 9 || die "another sync is running (lock held); exiting"

mkdir -p "$STATE_DIR"

# --- Fetch -------------------------------------------------------------------
TMP="$(mktemp -d)"
trap 'rm -rf "$TMP"' EXIT

fetch() {
  local url="$1" out="$2"
  # --fail so an HTTP error page is never mistaken for data. No mirrors: the
  # allow-list is a security control and must come from Cloudflare over TLS.
  curl --fail --silent --show-error --location --proto '=https' --tlsv1.2 \
       --max-time 30 --retry 3 --retry-delay 5 -o "$out" "$url"
}

# --- Validate ----------------------------------------------------------------
# Returns 0 only for a plausible, well-formed, non-empty CIDR list.
validate() {
  local file="$1" family="$2" count line
  [[ -s "$file" ]] || { log "VALIDATION FAIL ($family): empty response"; return 1; }

  # Reject anything that is not a bare CIDR list (HTML error pages, JSON, etc).
  while IFS= read -r line; do
    [[ -z "$line" ]] && continue
    if [[ "$family" == "v4" ]]; then
      [[ "$line" =~ ^([0-9]{1,3}\.){3}[0-9]{1,3}/[0-9]{1,2}$ ]] \
        || { log "VALIDATION FAIL (v4): malformed CIDR: ${line:0:60}"; return 1; }
    else
      [[ "$line" =~ ^[0-9a-fA-F:]+/[0-9]{1,3}$ ]] \
        || { log "VALIDATION FAIL (v6): malformed CIDR: ${line:0:60}"; return 1; }
    fi
  done < "$file"

  count="$(grep -c . "$file")"
  (( count >= MIN_RANGES && count <= MAX_RANGES )) \
    || { log "VALIDATION FAIL ($family): implausible range count: $count"; return 1; }

  log "validated $family: $count ranges"
  return 0
}

log "=== Cloudflare allow-list sync starting (dry-run=$DRY_RUN) ==="

fetch "$CF_V4_URL" "$TMP/v4" || die "fetch failed for $CF_V4_URL — previous list left untouched"
fetch "$CF_V6_URL" "$TMP/v6" || die "fetch failed for $CF_V6_URL — previous list left untouched"

validate "$TMP/v4" v4 || die "IPv4 validation failed — previous list left untouched"
validate "$TMP/v6" v6 || die "IPv6 validation failed — previous list left untouched"

sort -o "$TMP/v4" "$TMP/v4"
sort -o "$TMP/v6" "$TMP/v6"

# --- IPv6 applicability ------------------------------------------------------
# Fetched and validated regardless so a future IPv6 rollout has current data,
# but rules are only applied when the host actually has global IPv6 AND Docker
# publishes on it. Writing ip6tables rules on a host with no IPv6 address would
# be inert clutter that later reads as protection that was never in effect.
# IPv6 rule application is NOT implemented. Docker's docker-proxy binds [::]:80
# and [::]:443, so if this host ever gains a global IPv6 address those ports
# become reachable over IPv6 with NO ip6tables DROP in place — the IPv4
# allow-list would not cover them. Rather than ship untested firewall code, this
# refuses to run silently in that state: it warns loudly and exits non-zero so
# the gap is acted on instead of being papered over by a green log line.
if [[ "$(ip -6 addr show scope global 2>/dev/null | grep -c inet6)" -gt 0 ]]; then
  log "WARNING: host has a global IPv6 address, but IPv6 firewall rules are NOT"
  log "         implemented here. docker-proxy binds [::]:80 and [::]:443, so the"
  log "         origin is reachable over IPv6 without an allow-list."
  log "         Add ip6tables DOCKER-USER rules before relying on this control."
  V6_GAP=1
else
  log "host has no global IPv6 — v6 ranges validated and stored; no v6 rules needed"
  V6_GAP=0
fi

# --- Diff --------------------------------------------------------------------
PREV_V4="$STATE_DIR/cf-ips-v4.txt"
PREV_V6="$STATE_DIR/cf-ips-v6.txt"
[[ -f "$PREV_V4" ]] || : > "$PREV_V4"
[[ -f "$PREV_V6" ]] || : > "$PREV_V6"

ADDED="$(comm -13 "$PREV_V4" "$TMP/v4" || true)"
REMOVED="$(comm -23 "$PREV_V4" "$TMP/v4" || true)"

if [[ -z "$ADDED" && -z "$REMOVED" ]] && diff -q "$PREV_V6" "$TMP/v6" >/dev/null 2>&1; then
  log "no change in Cloudflare ranges"
  date -Is > "$STATE_DIR/last-success"
  if [[ "${V6_GAP:-0}" == "1" ]]; then log "=== no-op for IPv4; IPv6 gap UNADDRESSED ==="; exit 3; fi
  log "=== sync complete (no-op) ==="
  exit 0
fi

if [[ -n "$ADDED" || -n "$REMOVED" ]]; then
  log "IPv4 range changes detected:"
  [[ -n "$ADDED"   ]] && while read -r c; do [[ -n "$c" ]] && log "  + $c"; done <<< "$ADDED"
  [[ -n "$REMOVED" ]] && while read -r c; do [[ -n "$c" ]] && log "  - $c"; done <<< "$REMOVED"
else
  # Reached when only the stored IPv6 list differs (e.g. first run seeding it).
  # Saying "IPv4 changes" here would send someone hunting a firewall delta that
  # does not exist.
  log "no IPv4 range changes; refreshing stored IPv6 list only"
fi

if $DRY_RUN; then
  log "dry-run: no firewall changes applied"
  exit 0
fi

# --- Apply -------------------------------------------------------------------
SNAPSHOT="$TMP/iptables-before.rules"
iptables-save > "$SNAPSHOT"

rollback() {
  log "!!! applying rollback from pre-change snapshot"
  iptables-restore < "$SNAPSHOT" && log "rollback complete" || log "ROLLBACK FAILED — manual intervention required"
}

apply_v4() {
  local port cidr
  for port in "${PORTS[@]}"; do
    # Additions first: widening before narrowing means Cloudflare is never
    # locked out mid-update.
    while read -r cidr; do
      [[ -z "$cidr" ]] && continue
      if ! iptables -C DOCKER-USER -s "$cidr" -p tcp -m tcp --dport "$port" -j ACCEPT 2>/dev/null; then
        iptables -I DOCKER-USER 1 -s "$cidr" -p tcp -m tcp --dport "$port" -j ACCEPT
        log "  ACCEPT added   $cidr -> :$port"
      fi
    done <<< "$ADDED"

    while read -r cidr; do
      [[ -z "$cidr" ]] && continue
      if iptables -C DOCKER-USER -s "$cidr" -p tcp -m tcp --dport "$port" -j ACCEPT 2>/dev/null; then
        iptables -D DOCKER-USER -s "$cidr" -p tcp -m tcp --dport "$port" -j ACCEPT
        log "  ACCEPT removed $cidr -> :$port"
      fi
    done <<< "$REMOVED"

    # Invariants — the whole point of the control.
    iptables -C DOCKER-USER -s "$INTERNAL_NET" -p tcp -m tcp --dport "$port" -j ACCEPT 2>/dev/null \
      || iptables -I DOCKER-USER 1 -s "$INTERNAL_NET" -p tcp -m tcp --dport "$port" -j ACCEPT
    iptables -C DOCKER-USER -p tcp -m tcp --dport "$port" -j DROP 2>/dev/null \
      || { iptables -A DOCKER-USER -p tcp -m tcp --dport "$port" -j DROP; log "  DROP re-added for :$port"; }
  done
}

apply_v4 || { rollback; die "failed while applying IPv4 rules"; }

# --- Post-apply invariant check ---------------------------------------------
for port in "${PORTS[@]}"; do
  iptables -C DOCKER-USER -p tcp -m tcp --dport "$port" -j DROP 2>/dev/null \
    || { rollback; die "DROP rule missing for :$port after apply — rolled back"; }
  n="$(iptables -S DOCKER-USER | grep -c -- "--dport $port -j ACCEPT")"
  (( n >= MIN_RANGES )) || { rollback; die "only $n ACCEPT rules for :$port after apply — rolled back"; }
done
log "invariants OK: deny-by-default intact, allow-list populated"

# --- Persist -----------------------------------------------------------------
iptables-save > "$RULES_SAVE" || { rollback; die "failed to persist rules"; }
cp "$TMP/v4" "$PREV_V4"
cp "$TMP/v6" "$PREV_V6"
date -Is > "$STATE_DIR/last-success"
log "rules persisted to $RULES_SAVE; state updated"
if [[ "${V6_GAP:-0}" == "1" ]]; then
  log "=== sync complete for IPv4, but the IPv6 gap above is UNADDRESSED ==="
  exit 3
fi
log "=== sync complete ==="
