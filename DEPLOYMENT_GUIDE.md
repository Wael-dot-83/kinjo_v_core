# KinJo Production Deployment Guide

Target: a single DigitalOcean droplet running Docker Compose behind Nginx with
Let's Encrypt TLS.

> **This guide replaces the previous one**, which described a `/srv/kinjo`
> virtualenv managed by systemd. That environment does not exist. Production runs
> Docker at `/opt/kinjo`, and the root `deploy.sh` that targeted the old layout
> now refuses to run rather than half-applying itself to a live host.

---

## 1. Architecture

```
                        ┌─────────────── droplet ───────────────┐
  Internet ──:443──►    │  nginx  ──────► web (uvicorn, N workers)│
             :80  ──►   │  (TLS)          │                       │
                        │  certbot        ├──► db     (postgres 15)│
                        │                 ├──► redis  (redis 7)    │
                        │                 ├──► worker (celery)     │
                        │                 └──► beat   (celery beat)│
                        └───────────────────────────────────────────┘
```

| Concern | Owner |
|---|---|
| TLS termination, HTTP→HTTPS, rate limiting, static caching | `nginx` |
| Certificate issue + renewal | `deploy/issue-cert.sh`, then `certbot` service |
| Process supervision | Docker `restart: unless-stopped` + `supervisord` inside `web` |
| Schema migration | `alembic upgrade head`, run by `scripts/deploy_locked.sh` |
| Scheduled work (exports, backups, heatmaps) | `worker` + `beat` |

**Only `nginx` publishes public ports.** `web` binds `127.0.0.1:8000` for on-box
debugging; `db` and `redis` publish nothing and are reachable only on the compose
network.

> Docker writes its own `DOCKER-USER` iptables rules that **bypass ufw**. A
> container published on `0.0.0.0` is reachable from the internet even while
> `ufw status` says the port is denied. Never add a `ports:` mapping for `db` or
> `redis`, and never set `KINJO_WEB_PORT` to a non-loopback value.

### Process management note

The requirement called for PM2. PM2 is a Node.js process manager and this is a
Python/FastAPI application — it is the wrong tool. The equivalent guarantees are
provided by Docker restart policies (crash/reboot recovery), `supervisord` inside
the web container (per-process restart), and compose healthchecks (liveness).
`live-restore` in `/etc/docker/daemon.json` keeps containers running across a
Docker daemon restart.

---

## 2. First-time droplet setup

### 2.1 Create the droplet

- Ubuntu 24.04 LTS, **minimum 2 vCPU / 4 GB RAM** (2 GB works only with the swap
  file the hardening script creates; Postgres + Redis + 3 uvicorn workers +
  2 celery processes will OOM under a large export otherwise).
- Add your SSH public key during creation.
- Create a DNS `A` record for your domain pointing at the droplet's IPv4 address,
  and an `AAAA` record if you use IPv6.

### 2.2 Harden the host

```bash
scp deploy/harden-droplet.sh root@<droplet-ip>:/tmp/
ssh root@<droplet-ip> 'bash /tmp/harden-droplet.sh deploy "$(cat ~/.ssh/authorized_keys | head -1)"'
```

This creates the `deploy` user, installs Docker, enables ufw (22/80/443 only),
fail2ban and unattended-upgrades, disables SSH password and root login, caps
container log size, and adds a 2 GB swap file. It is idempotent.

> **Before closing your root session**, open a second terminal and confirm
> `ssh deploy@<droplet-ip>` works. The script disables password authentication;
> a bad key means console-only recovery.

### 2.3 Install the application

```bash
ssh deploy@<droplet-ip>
sudo chown -R deploy:deploy /opt/kinjo
cd /opt/kinjo
```

From your workstation, ship the current commit:

```bash
SHA="$(git rev-parse HEAD)"
scripts/build_release_artifact.sh "$SHA" /tmp/deploy.tar
scp /tmp/deploy.tar deploy@<droplet-ip>:/tmp/deploy.tar
ssh deploy@<droplet-ip> 'tar xf /tmp/deploy.tar -C /opt/kinjo'
```

### 2.4 Configure the environment

```bash
cd /opt/kinjo
cp .env.production.template .env
chmod 600 .env
python3 -c "import secrets; print(secrets.token_hex(32))"   # paste into SECRET_KEY
```

Every `REPLACE_ME` must be filled. The application refuses to boot in production
if `SECRET_KEY` is missing, short, still a placeholder, or **matches a key that
has ever been published in this repository** — those are rejected by value, since
a high-entropy key is still worthless once it is public.

Required beyond the template:

```ini
KINJO_DOMAIN=kinjo.example.com          # used by nginx and cert issuance
KINJO_WORKERS=3                          # 2 x vCPU + 1 is a reasonable start
POSTGRES_PASSWORD=<generated>
REDIS_PASSWORD=<generated>
TRUSTED_HOSTS=["kinjo.example.com","www.kinjo.example.com"]
CORS_ALLOWED_ORIGINS=["https://kinjo.example.com"]
```

Leave `KINJO_WEB_PORT` **unset**. If it is set to `80` (the value used before TLS
terminated on the droplet) it will both re-expose the app in plaintext and
collide with nginx.

### 2.5 Issue the TLS certificate

```bash
sudo bash deploy/issue-cert.sh kinjo.example.com admin@example.com
```

Run it once per domain, **before** the first `up`. It uses a standalone challenge
because nginx cannot start without a certificate and certbot's webroot cannot be
served without nginx — a bootstrap deadlock the renewal service cannot break.

Rehearse with `--staging` first if you are unsure about DNS: Let's Encrypt allows
only 5 failed validations per hour and 5 duplicate certificates per week.

If your DNS is proxied through Cloudflare, set the record to "DNS only" (grey
cloud) until the certificate exists, then re-enable proxying.

### 2.6 Start

```bash
cd /opt/kinjo
docker compose -f docker-compose.prod.yml -f docker-compose.edge.yml up -d --build
docker compose -f docker-compose.prod.yml -f docker-compose.edge.yml exec web alembic upgrade head
```

---

## 3. Routine deployments

Always use the locked script. It holds an exclusive lock across the entire
mutation window — backup, extract, build, migrate, verify — so two concurrent
deploys cannot race. (Two did, and took production down twice on 2026-08-12.)

```bash
# from the workstation, on the commit you intend to ship
SHA="$(git rev-parse HEAD)"
scripts/build_release_artifact.sh "$SHA" /tmp/deploy.tar
scp /tmp/deploy.tar deploy@<droplet-ip>:/tmp/deploy.tar
ssh deploy@<droplet-ip> \
  "bash /opt/kinjo/scripts/deploy_locked.sh /tmp/deploy.tar $SHA"
```

Exit codes: `0` deployed and verified · `75` another deploy holds the lock,
production untouched · `1` failed, see output.

The script auto-detects `docker-compose.edge.yml` and includes it. Set
`KINJO_EDGE=0` only if you deliberately run without the TLS edge — omitting it
while nginx is deployed would remove the nginx container as an orphan and take
the site offline.

> **Build only through `scripts/build_release_artifact.sh`.**
> A bare `git archive` applies the *producer's* `core.autocrlf`, and this project
> has two producers: a Windows workstation with `core.autocrlf=true` and a
> `runs-on: ubuntu-latest` workflow. One commit therefore exported two different
> artifacts -- 1,263 of 3,950 files diverged -- so "this SHA reproduces this
> artifact" was not a fact. Worse, the self-hosted Plotly `integrity` digest
> matched only the Windows byte-set; the first release built on Linux would have
> shipped the other one and Chromium would have refused to execute Plotly on the
> Charts Explorer.
>
> The builder pins the conversion settings on the command line, where they
> outrank any global or repository config, so canonical release bytes are the
> committed Git blob bytes on every machine. It also refuses a short SHA.
> Enforced by `tests/test_release_artifact_determinism.py` (which builds under a
> hostile `core.autocrlf=true` and proves a naive `git archive` really does
> diverge) and `tests/test_vendor_sri.py`.

> **Deploy from an explicit commit, not from whatever `main` happens to be.**
> `git archive HEAD` ships your local checkout; a stale or unmerged local `main`
> silently becomes production.

### Static assets

Templates cache-bust with `?v=<hash>` and nginx serves `/static/` with a
one-year immutable TTL. **If you change an asset without bumping its `?v=`,
returning users keep the old file for a year.** Verify by fetching the asset URLs
from outside the droplet, not by grepping templates.

---

## 4. Verification after every deploy

Run from **outside** the droplet:

```bash
curl -sSI https://kinjo.example.com/health          # 200
curl -sSI http://kinjo.example.com/health           # 301 -> https
curl -sS  https://kinjo.example.com/health          # body

# TLS floor: both must FAIL to connect
curl -sk --tlsv1.1 --tls-max 1.1 https://kinjo.example.com/ && echo "TLS 1.1 ACCEPTED - FAIL"

# Security headers
curl -sSI https://kinjo.example.com/ | grep -iE 'strict-transport|x-content-type|referrer-policy'
```

On the droplet:

```bash
docker compose -f docker-compose.prod.yml -f docker-compose.edge.yml ps
# web, worker, beat, db, redis, nginx, certbot must all be Up (web healthy)

ss -tlnp | grep -E ':(80|443|8000|5432|6379) '
# 80/443  -> 0.0.0.0 (nginx)
# 8000    -> 127.0.0.1 ONLY
# 5432/6379 -> must NOT appear

docker exec kinjo-web-1 alembic current      # matches the shipped head
docker logs --tail 50 kinjo_nginx
```

**Background work is the thing most likely to be silently dead.** `worker` and
`beat` being "Up" is not proof they process anything — both once ran while no
scheduled export, message dispatch or backup executed at all. Confirm a task
actually completes:

```bash
docker logs --tail 100 kinjo-beat-1 | grep -i "Scheduler: Sending"
docker logs --tail 100 kinjo-worker-1 | grep -i "succeeded"
```

Same for SMTP: a configured `SMTP_HOST` is not a working mail path. Send a real
test message before declaring email operational.

---

## 5. Certificate renewal

The `certbot` service attempts renewal every 12 hours; Let's Encrypt certificates
last 90 days and renew within the final 30, so a transient failure has roughly 60
retries before expiry. **nginx reloads every 6 hours** to pick up a renewed
certificate — without that reload it would keep serving the old one from memory
until something restarted it.

Check status:

```bash
docker exec kinjo_certbot certbot certificates
curl -sSI https://kinjo.example.com/ -w '%{ssl_verify_result}\n' -o /dev/null
```

Force a renewal test: `docker exec kinjo_certbot certbot renew --dry-run`

---

## 6. Backup and rollback

`scripts/deploy_locked.sh` takes a `pg_dump` into `/var/backups/kinjo` before
mutating anything and tags the previous image for rollback. Restore:

```bash
docker exec -i kinjo_postgres psql -U kinjo -d kinjo_db < /var/backups/kinjo/<dump>.sql
```

Verify a restore into a scratch database periodically. An untested backup is not
a backup.

---

## 7. Troubleshooting

| Symptom | Cause | Action |
|---|---|---|
| nginx exits at start | certificate missing | run `deploy/issue-cert.sh` first |
| `host not found in upstream "web:8000"` | `web` not started | `docker compose ... up -d web` |
| All users share one rate-limit bucket | `--proxy-headers` off | confirm `KINJO_FORWARDED_ALLOW_IPS` is set on `web` |
| 502 from nginx | app crashed | `docker logs kinjo-web-1` |
| App boots then exits with `CRITICAL: SECRET_KEY...` | placeholder or published key | generate a fresh key |
| `supervisord: not found` | image predates the dependency fix | rebuild with `--build` |
| Renewed cert not served | nginx not reloaded | `docker exec kinjo_nginx nginx -s reload` |

Config changes to nginx: **always** validate before reloading a live site —
`docker exec kinjo_nginx nginx -t`, then `nginx -s reload`.
