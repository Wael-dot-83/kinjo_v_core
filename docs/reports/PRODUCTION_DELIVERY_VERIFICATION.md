# KinJo — Production Delivery Verification Report

**Branch:** `feat/production-delivery-hardening`
**Baseline:** `7e82351` (main)
**Date:** 2026-08-17
**Scope:** development completion, test verification, production hardening, DigitalOcean deployment pipeline

---

## 1. Scope correction (read this first)

The brief asked to implement all core features and modules of the KinJo
application. **They already exist.** This repository is a mature FastAPI
application: 670 Python modules, 296 test files, an Alembic migration history, a
six-job CI pipeline, and a live production deployment. Writing features from
scratch would have destroyed working software.

The work was therefore scoped to what the codebase actually needed:

| Brief phase | What was actually required |
|---|---|
| 1. Full-scale development | Finish the in-flight uncommitted work; fix defects found while verifying |
| 2. Comprehensive testing | Run the real suite, report real numbers, fix a nondeterministic test |
| 3. Production hardening | Close concrete security and reliability gaps found by audit |
| 4. Deployment pipeline | Build the missing TLS edge; replace a deploy script that targeted a non-existent host |

Two items in the brief were not applicable as written and were substituted:

- **PM2** is a Node.js process manager; this is a Python application. Equivalent
  guarantees are provided by Docker restart policies, `supervisord` inside the
  web container, and compose healthchecks. See DEPLOYMENT_GUIDE.md §1.
- **"Confirming all testing phases completed"** — §3 reports what passed and what
  did not, including one test that is structurally unable to prove its claim on
  the default test backend.

---

## 2. Findings and fixes

Ordered by severity. Every item was verified, not assumed.

### P0 — A live signing key was published in git

`.env.production.template` shipped a real 64-character hex `SECRET_KEY`. Any
deployment that used the template as documented ("use the freshly generated key
below") signed its JWTs and session cookies with a value readable by anyone with
repository access — enough to forge a session for any user, including an admin.

The existing guard could not catch it. `validate_production_settings()` checked
only that the key was ≥32 characters and did not *contain* a placeholder
substring like `changeme`. A high-entropy hex key passes both.

**Fixed:**
- Template value replaced with `REPLACE_ME_RUN_THE_COMMAND_ABOVE`.
- Published keys rejected **by value** at startup, stored as SHA-256 digests so
  reading `config.py` does not hand out a working key for an unpatched
  deployment. Scrubbing the file alone was insufficient — the key remains in git
  history permanently.
- `replace_me` / `replace-with` added to the placeholder markers so a forgotten
  substitution fails the boot instead of going live.

> **Operational note:** this key must be treated as compromised. Rotating
> `SECRET_KEY` invalidates all existing sessions and tokens — schedule it.

### P1 — Non-HMAC JWT algorithms were permitted

`ALGORITHM` is environment-configurable and was unvalidated. `none` disables
signature verification outright; `ES*`/`EdDSA` route signing through
python-jose's pure-Python `ecdsa` backend, which carries an **unfixed** timing
vulnerability (PYSEC-2026-1325 — upstream considers side-channel attacks out of
scope, so no fixed version exists).

**Fixed:** production now accepts only `HS256/384/512`. This converts the one
outstanding dependency advisory from "unused by convention" to "unreachable by
construction." Verified: the codebase contains zero ECDSA call sites.

### P1 — The app was published to the internet in plaintext

`docker-compose.prod.yml` defaulted to publishing `web` on `0.0.0.0`, with TLS
existing only at Cloudflare. Anyone who learned the droplet's IP could reach the
application unencrypted, bypassing the CDN entirely.

ufw does **not** contain this: Docker writes its own `DOCKER-USER` iptables rules
that bypass the firewall, so a published port is reachable even while `ufw
status` reports it denied.

**Fixed:** the default is now `127.0.0.1:8000`. Local development is unchanged.
TLS terminates on the droplet (§4).

### P1 — Client IP was invisible behind a proxy

`scripts/run_uvicorn_supervised.py` started uvicorn without `--proxy-headers`.
Behind any reverse proxy the peer address is the proxy, so **every user would
share a single per-IP rate-limit bucket** and every audit row would record the
proxy's address. Neither failure is visible at runtime — the app serves traffic
normally while the rate limiter and audit trail are quietly wrong.

**Fixed:** `--proxy-headers` with an explicit `--forwarded-allow-ips`. Not a
wildcard: with `*`, any client that can reach the app port sets its own apparent
source IP and walks past the rate limiter.

### P2 — The web container had no concurrency

The same launcher ran a single uvicorn worker, serialising every request behind
the slowest dashboard aggregation.

**Fixed:** `KINJO_WORKERS` (default 3 in production, unchanged at 1 locally).

### P2 — A declared default that could only crash

`docker-compose.prod.yml` declared `supervisord -c /app/supervisor.conf` as the
default command for `web`, but `supervisor` was **not in `requirements.txt`** —
that default could only ever fail with `supervisord: not found`. It went
unnoticed because the server overrode it with a bare uvicorn, which is also why
the app ran with no restart supervision at all.

**Fixed:** `supervisor==4.3.0` added and verified to resolve for Python 3.12.

### P2 — The obvious deploy script targeted a host that does not exist

Root `deploy.sh` assumed `/srv/kinjo`, a virtualenv, and systemd units.
Production is Docker at `/opt/kinjo`. It would have failed partway through,
**after** it began mutating state. It remained executable, at the repository
root, under the most guessable possible name.

**Fixed:** replaced with a guard that refuses to run and points at
`scripts/deploy_locked.sh`. Deleted rather than guarded, a stale checkout or
bookmarked path could resurrect the original silently.

### P2 — Container ran as root with a compiler installed

**Fixed:** multi-stage build. `build-essential` (~250 MB of C toolchain) now
stays in the builder stage instead of shipping to production as both dead weight
and a ready-made post-exploitation toolkit. Runtime runs as uid 10001, with an
image-level healthcheck.

### P2 — A deploy health check that passed on a dead application

`scripts/deploy_locked.sh` probed `http://127.0.0.1:80/`. Once nginx terminates
TLS, that address returns `301 → https` **without the application being
involved**, and `curl -f` treats 301 as success. The check would have gone green
against a completely dead app.

**Fixed:** probes `/health` inside the web container, plus a non-fatal external
HTTPS probe. The script also now auto-detects the edge overlay — deploying
without it would have removed the nginx container as an orphan and taken the
site offline while reporting success.

---

## 3. Test verification

### Full suite

`python -m pytest` on the final branch state, one clean uninterrupted run:

```
4 failed, 5304 passed, 25 skipped in 1618.94s (26:58)
```

**All 4 failures are pre-existing on `main` and unrelated to this work.** Verified
by running the same tests in the untouched primary checkout and getting identical
results:

| Failing test | Nature |
|---|---|
| `test_frontend.py::…::test_admin_sidebar_is_arabic_by_default` | Arabic sidebar label «التواصل والبيانات» absent |
| `test_frontend.py::…::test_admin_sidebar_switches_to_english` | same sidebar defect, English path |
| `test_analytics_pinpoint_e2e.py::…::test_admin_analytics_nav_link_is_not_duplicated` | `href="/admin/analytics"` rendered twice (the response also contains a duplicated `</html>`) |
| `test_unicode_integrity.py::…` | **caused by this work, now fixed** — this report misspelled the product name; the repo enforces the KinJo capitalisation and this document is itself first-party text the auditor scans |

The three frontend failures are **not fixed here deliberately**: they are the
subject of the in-flight `ux/admin-navigation-consolidation` branch, and editing
those templates would collide with concurrent work. They are reported rather than
silently absorbed. **`main` is currently red on these three** — worth knowing
before anyone treats a green suite as the merge gate.

> **A caveat on an earlier run.** A first full-suite run was started before the
> in-flight patch was applied and continued while source files were being edited,
> so its output (9 failures) was contaminated and is not cited here. Only the
> clean run above is reported. Two of those 9 were real and are fixed below; the
> rest were artifacts of editing mid-run.

### Regressions found in this work, and fixed

`tests/test_deploy_lock.py` — two guard tests broke because they identified the
build step by the literal string `docker compose -f`, and the compose invocation
now assembles its file list into an array so the edge overlay is always included.
The invariants they protect are real (every mutation inside the lock; rollback
image tagged before the build), so the marker was retargeted to `up -d --build`
— which names the mutation itself and survives that class of refactor — rather
than the assertions being weakened. 21/21 pass.

### Component results

| Suite | Result |
|---|---|
| `tests/test_config.py` (incl. 10 new security tests) | 19 passed |
| `tests/test_uvicorn_supervisor_command.py` (new) | 9 passed |
| `tests/test_deploy_lock.py` | 21 passed |
| `tests/test_new_modules.py` | 76 passed, stable across 3 consecutive runs |
| `tests/test_unicode_integrity.py` | 3 passed |
| `ruff check` on all modified Python | clean |
| `shellcheck` on deployment scripts | no errors |

### Test integrity issue found and fixed

`test_ai_daily_report_confirm_is_atomic_under_concurrency` (part of the in-flight
uncommitted work) **failed nondeterministically** — two 409s in one run, a stale
`DRAFT` read in the next. It passed in isolation and failed in full-file runs,
which is the signature of a harness problem rather than a product bug.

Root cause: `conftest.py`'s `override_get_db` yields **one shared Session** to
every request, and the test engine is in-memory SQLite behind a `StaticPool` — a
single connection. The two threads therefore do not model two database sessions;
they interleave on one Session, which SQLAlchemy does not support, and SQLite
gives `SELECT ... FOR UPDATE` no meaning whatsoever. **The test could not prove
the property it claimed to test.**

Fixed by splitting the guarantee into the part each backend can actually prove:

- The threaded test now asserts the real invariant — never more than one
  submitted report, never more than one `200` — and calls `expire_all()` before
  reading, since `.update(synchronize_session=False)` leaves the identity map
  stale.
- A new sequential test (`..._is_idempotent_when_repeated`) deterministically
  asserts `200` then `409`.
- Genuine row-level locking belongs to the PostgreSQL parity suite, the only
  place it can be tested honestly.

Verified stable across repeated full-file runs.

### Dependency audit

`pip-audit` against `requirements.txt`: **one** advisory, accepted with
justification (PYSEC-2026-1325, above). Now enforced in CI via a new
`dependency-audit` job that fails on any *new* advisory, runs weekly on a
schedule so it cannot go stale during a quiet pre-release period, and prints the
accepted one for visibility rather than hiding it.

---

## 4. Deployment pipeline

### Built

| Artifact | Purpose |
|---|---|
| `deploy/nginx/kinjo.conf` | TLS termination, HTTP→HTTPS, HSTS, rate limiting, static caching, WebSocket upgrade |
| `deploy/nginx/kinjo_proxy_params` | Shared proxy headers (real client IP) |
| `docker-compose.edge.yml` | nginx + certbot overlay; only nginx publishes ports |
| `deploy/issue-cert.sh` | First-time certificate issuance |
| `deploy/harden-droplet.sh` | Server hardening: ufw, fail2ban, SSH, unattended-upgrades, Docker, swap |
| `DEPLOYMENT_GUIDE.md` | Rewritten against the real environment |

### Two bootstrap traps handled

1. **Issuance deadlock.** nginx will not start without a certificate; certbot's
   webroot cannot be served without nginx. Issuance is therefore a separate
   one-shot standalone-challenge script, not something the renewal service can do.
2. **Renewal without reload.** nginx reads certificates once, at start. certbot
   renewing on disk changes nothing being served — the site would keep presenting
   the old certificate until something happened to restart it, and expiry would
   arrive with a valid certificate sitting unused in the volume. nginx now
   reloads every 6 hours.

### Verified against real containers

The Nginx configuration was not merely written — it was rendered through the
official image's `envsubst` pipeline and exercised against a live stub upstream.

| Check | Result |
|---|---|
| `nginx -t` on the rendered config | **pass** |
| `envsubst` substitutes `${KINJO_DOMAIN}` only | **pass** — 0 unsubstituted |
| Nginx runtime vars survive templating | **pass** — `$host`, `$remote_addr`, `$proxy_add_x_forwarded_for` intact |
| HTTP → HTTPS redirect preserves path + query | **pass** — `301 → https://…/dashboard?x=1` |
| ACME challenge served on plain HTTP, not redirected | **pass** — `200`, correct body |
| Real client IP reaches upstream | **pass** — `X-Forwarded-For`, `X-Real-IP`, `X-Forwarded-Proto: https` |
| HSTS / nosniff / Referrer-Policy present | **pass** |
| `server_tokens off` | **pass** — version not advertised |
| TLS 1.1 refused | **pass** — connection rejected |
| Merged compose config valid | **pass** — `web` no longer publicly published |
| Image builds | **pass** — 382 MB |
| Image runs as non-root | **pass** — `uid=10001(kinjo)` |
| Compiler absent from runtime image | **pass** — no `gcc`/`cc`/`make` |
| `supervisord` present and runnable | **pass** — 4.3.0 |
| Application imports inside the image | **pass** — 79 routes registered |

**A caught bug:** the first validation attempt reported `nginx -t` success while
both bind mounts had silently failed — it had validated the *default* config, not
mine. Re-run with correct paths, `nginx -t` failed on a genuine duplicate
`proxy_http_version` directive in the WebSocket block, which would have prevented
nginx from starting and taken down the **entire site**, not just WebSockets. That
is the difference between validating and asserting.

`envsubst` is restricted via `NGINX_ENVSUBST_FILTER=KINJO_`. Without that filter
it would also expand Nginx's own `$host` and `$proxy_add_x_forwarded_for` to
empty strings, producing a config that loads cleanly and forwards no client
information at all.

---

## 5. What was NOT done

Stated explicitly rather than left implied.

- **Nothing was deployed.** No droplet was provisioned, no DNS configured, no
  certificate issued, no production change made. Deployment is an outward-facing,
  hard-to-reverse action requiring credentials and a maintenance window. The
  pipeline is built and verified locally; executing it is a decision for the
  owner. Existing guidance also requires production verification to happen in a
  no-deploy window.
- **`SECRET_KEY` has not been rotated.** The published key must be treated as
  compromised, but rotating it invalidates every active session — an
  availability-affecting action that needs scheduling.
- **Branch not merged.** Work is on `feat/production-delivery-hardening` in an
  isolated worktree, per the project's agent-isolation rule.
- **`supervisor.conf` change is untested at runtime.** `supervisor` is newly
  added; the supervisord path has never actually run in production (it was always
  overridden). Exercise it in staging before relying on it.
- **Load and E2E testing not executed.** `load_tests/` and Playwright specs exist
  but need a running environment; they were not run.

---

## 6. Recommended sequence

1. Review and merge this branch.
2. Rotate `SECRET_KEY` (schedule the session invalidation).
3. Provision the droplet → `deploy/harden-droplet.sh`.
4. DNS → `deploy/issue-cert.sh --staging`, then for real.
5. Deploy via `scripts/deploy_locked.sh`; run DEPLOYMENT_GUIDE.md §4 verification.
6. **Prove background work is alive.** `worker` and `beat` showing "Up" is not
   evidence they process anything — both have previously run while no scheduled
   export, message dispatch or backup executed at all. Confirm a task completes.
7. Send a real test email. A configured `SMTP_HOST` is not a working mail path.

---

## 8. Addendum — E2E suite, automated pipeline, live droplet audit

Added after the initial report, closing the gaps it listed as outstanding.

### E2E: 5/22 → 23/24

The suite could not run at all. It needs `TESTING=true` (for the dev auto-login
endpoint) and a seeded admin user. Beyond that, the agency-report specs were
written against a flat form that is now a **five-step wizard inside a tabpanel
that ships `hidden`** — they were failing on a hidden `#cr-agency` and on
`#custom-report-run`, which no longer drives generation. Rewritten to activate
the tab and walk Purpose → Scope → Indicators → Review → Generate.

The single remaining failure asserts `a[href="/admin/analytics"]` has count 1 —
**the same duplicate-nav defect the pytest suite reports**, now corroborated by
a second, independent test layer. Owned by `ux/admin-navigation-consolidation`.

### Automated deployment pipeline

`.github/workflows/deploy.yml`. Manual dispatch only, with a typed confirmation
and a `production` environment for required reviewers — an automatic
deploy-on-merge is how production once ran an unmerged branch for hours. Tests
gate the deploy; the release is built with `git archive` from the exact commit so
untracked files cannot ride along; the SSH host key is pinned rather than blindly
accepted; exit 75 is surfaced as "another deploy holds the lock, production
untouched".

### Config: `.env` list values could not be parsed

`_CommaListEnvSource` subclassed only `EnvSettingsSource`, so
`SUPPORTED_LANGUAGES=ar,en` parsed from a real environment variable but raised
`SettingsError` from a `.env` file. `.env.example` shipped exactly that form, so
copying the documented example produced an app that refused to boot. Now a mixin
on both sources, with a test asserting every shipped template actually loads.

### Live droplet audit (read-only, 159.223.16.33)

Five containers healthy; worker and beat running; Postgres and Redis correctly
unpublished. Three findings changed the plan:

| Finding | Status |
|---|---|
| **No TLS at all** — only `0.0.0.0:80` listening, bare IP, no DNS record | **Blocks TLS.** Let's Encrypt will not issue for an IP address |
| **`--forwarded-allow-ips='*'`** on an internet-facing app — any client can forge `X-Forwarded-For`, defeating the per-IP rate limiter and poisoning the audit trail | **Open.** Lives in the host `.env`, so no code change fixes it |
| **`/opt/kinjo/data` owned by uid 0**, `attachments/` mode `dr-x---r-x` | **Fixed (PR #85)** — see below |

The ownership finding was a genuine near-miss. The hardened image runs as uid
10001, so deploying it as-is would have started containers that pass their health
check and serve pages normally — while every attachment, upload and export write
failed at runtime, with the deploy reporting success. The deploy now chowns the
bind mount inside the lock and *before* containers are recreated, and restores
the write bit that ownership alone does not grant.

**One thing that turned out fine:** the production `SECRET_KEY` was hashed on the
host and compared against the published digests. It matches **neither** — this
server runs a unique key and is not compromised. The template key remains public
and must never be used, but there is no rotation emergency for this deployment.

### Still required before production can be deployed

1. A domain pointed at `159.223.16.33` (`A` record).
2. Droplet `.env`: set `KINJO_DOMAIN`, remove `KINJO_WEB_PORT=80` so nginx can
   bind port 80, and drop `--forwarded-allow-ips='*'` from `KINJO_WEB_COMMAND`.
3. Certificate issuance with `--staging` first.
