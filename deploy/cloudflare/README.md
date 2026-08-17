# Cloudflare origin hardening

`kinjordan.org` is proxied through Cloudflare. The droplet is the **origin**, and
these files keep the Cloudflare↔origin leg encrypted and reachable only by
Cloudflare.

## What is in git vs on the host

| Path | Location | Contains secrets |
|---|---|---|
| `kinjo-cf-ip-sync.sh` | git → `/usr/local/sbin/` | no |
| `kinjo-origin-health.sh` | git → `/usr/local/sbin/` | no |
| `kinjo-origin-cert-rotate.sh` | git → `/usr/local/sbin/` | no |
| `*.service`, `*.timer` | git → `/etc/systemd/system/` | no |
| `/opt/kinjo/secrets/origin/cert.pem`, `key.pem` | **host only** | **yes — never commit** |
| `/var/lib/kinjo/cloudflare/` | host only (runtime state) | no |

The certificate and private key are deliberately outside git. They are installed
by `kinjo-origin-cert-rotate.sh install`, are `0600` root-owned, and are mounted
read-only into the nginx container by `docker-compose.cf-origin.yml`.

## Installation

```bash
install -m 0755 -o root -g root deploy/cloudflare/kinjo-*.sh /usr/local/sbin/
install -m 0644 -o root -g root deploy/cloudflare/kinjo-*.service /etc/systemd/system/
install -m 0644 -o root -g root deploy/cloudflare/kinjo-*.timer   /etc/systemd/system/
systemctl daemon-reload
/usr/local/sbin/kinjo-cf-ip-sync.sh --dry-run   # inspect before applying
/usr/local/sbin/kinjo-cf-ip-sync.sh             # must succeed once first
systemctl enable --now kinjo-cf-ip-sync.timer kinjo-origin-health.timer
```

## kinjo-cf-ip-sync.sh

Keeps the firewall allow-list matching Cloudflare's published ranges.

It is **incremental, never flush-and-rebuild**. A rebuild has a window in which
the `DROP` rule is absent and the origin is open to the whole internet; this adds
and removes individual `ACCEPT` rules and never removes the `DROP`, so
deny-by-default holds at every instant.

`DOCKER-USER` matches the **container** port (`8000` web, `443` nginx) because
Docker's DNAT rewrites the destination port before the filter chain. Matching the
host port would silently match nothing and leave the origin open.

Validation runs before any mutation: an empty or malformed response can never
empty the allow-list, which would lock Cloudflare out and take the site down. On
failure the previous known-good list is kept and the script exits non-zero.

## kinjo-origin-health.sh

Detects the failure modes that are otherwise silent — certificate expiry, an aged
allow-list, an origin that has become publicly reachable, an nginx config that is
invalid on disk but fine until the next reload. Exits non-zero so a failure shows
up in `systemctl list-units --failed` instead of scrolling past in a log.

## kinjo-origin-cert-rotate.sh

Two-phase rotation so the private key never leaves the host:

```bash
kinjo-origin-cert-rotate.sh generate            # new key + CSR; prints only the CSR
kinjo-origin-cert-rotate.sh csr                # re-print the pending CSR at any time
# submit the CSR at Cloudflare > SSL/TLS > Origin Server > Create Certificate
#   -> "I have my own private key and CSR"
kinjo-origin-cert-rotate.sh install new-cert.pem
kinjo-origin-cert-rotate.sh status
```

`csr` exists because `generate` deliberately refuses once a pending key is
present — regenerating would orphan that key and produce a certificate that
cannot be installed — and `status` reports the *live* certificate, not the
request. Without it the only way to recover the CSR for submission was reading
the file by hand.

`install` validates modulus match, SANs, validity and PEM parseability **before**
touching the live files, backs up the current pair, swaps atomically, tests the
nginx config, reloads gracefully (no restart), then verifies the serial actually
served on `:443` and that the public site still returns 200 — restoring
automatically if any step fails. The old material is retired only after that.

## Important constraint

Do **not** deploy `docker-compose.edge.yml` / `deploy/nginx/kinjo.conf` here.
Those target a zone *without* Cloudflare in front, and their HTTP→HTTPS redirect
loops infinitely while Cloudflare speaks HTTP to the origin. Use
`docker-compose.cf-origin.yml` + `deploy/nginx/kinjo-origin-cloudflare.conf`.
