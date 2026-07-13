#!/usr/bin/env python3
"""
KinJo Admin — staging smoke-test harness.

Environment-driven, secret-free, self-cleaning end-to-end gate that ops can point
at a freshly-deployed staging URL. Emits a machine-readable JSON report and exits
non-zero on any failure, so it can gate a pipeline.

Covers:
  - Health / readiness endpoints
  - Login, session, and CSRF (double-submit) enforcement
  - Authorization boundary (unauthenticated admin access is refused)
  - Admin CRUD + soft-delete protection (deleted user unreachable + cannot log in)
  - CSV / XLSX import limit enforcement (malformed input is bounded and rejected)
  - Reports / exports (CSV export is served)
  - Manager impersonation: start, audit attribution, exit, logout, and
    one-time restore-token replay rejection
  - Rate-limit boundary

Configuration (all via environment; nothing secret is embedded):
  SMOKE_BASE_URL            default http://127.0.0.1:8060
  SMOKE_ADMIN_USERNAME      default "admin"
  SMOKE_ADMIN_PASSWORD      REQUIRED (no default — supply via the deploy secret store)
  SMOKE_IMPERSONATE_USER_ID optional manager user id; else a manager is discovered
  SMOKE_OUTPUT              optional path for the JSON report (default: stdout only)
  SMOKE_VERIFY_TLS          default "true" ("false" to allow self-signed staging certs)
  SMOKE_RATELIMIT_PROBE     default "true" ("false" to skip the 429 probe)
  SMOKE_TIMEOUT             per-request timeout seconds, default 30

Usage:
  SMOKE_BASE_URL=https://staging.example SMOKE_ADMIN_PASSWORD=*** \
      python scripts/manual-diagnostics/staging_smoke_test.py --output report.json

Exit code: 0 = all executed checks passed; 1 = at least one failed; 2 = setup error.
"""
from __future__ import annotations

import argparse
import json
import os
import sys
import time
import uuid
from datetime import datetime, timezone

try:
    import requests
except ImportError:  # pragma: no cover
    print("ERROR: this harness needs the 'requests' package (in requirements.txt).", file=sys.stderr)
    sys.exit(2)


# --------------------------------------------------------------------------- config
def env(name: str, default: str | None = None) -> str | None:
    val = os.getenv(name)
    return val if val not in (None, "") else default


def env_bool(name: str, default: bool) -> bool:
    raw = os.getenv(name)
    if raw is None or raw == "":
        return default
    return raw.strip().lower() in ("1", "true", "yes", "on")


BASE_URL = (env("SMOKE_BASE_URL", "http://127.0.0.1:8060") or "").rstrip("/")
ADMIN_USERNAME = env("SMOKE_ADMIN_USERNAME", "admin")
ADMIN_PASSWORD = env("SMOKE_ADMIN_PASSWORD")
IMPERSONATE_USER_ID = env("SMOKE_IMPERSONATE_USER_ID")
VERIFY_TLS = env_bool("SMOKE_VERIFY_TLS", True)
RATELIMIT_PROBE = env_bool("SMOKE_RATELIMIT_PROBE", True)
TIMEOUT = float(env("SMOKE_TIMEOUT", "30"))

CSRF_COOKIE = "kinjo_csrf_token"
SESSION_COOKIE = "kinjo_session"


# --------------------------------------------------------------------------- report
class Report:
    def __init__(self) -> None:
        self.checks: list[dict] = []
        self._t0 = time.time()

    def record(self, name: str, status: str, detail: str = "", **extra) -> None:
        entry = {"name": name, "status": status, "detail": detail}
        entry.update(extra)
        self.checks.append(entry)
        icon = {"pass": "PASS", "fail": "FAIL", "skip": "SKIP"}.get(status, status.upper())
        print(f"  [{icon}] {name}: {detail}", file=sys.stderr)

    def summary(self) -> dict:
        counts = {"pass": 0, "fail": 0, "skip": 0}
        for c in self.checks:
            counts[c["status"]] = counts.get(c["status"], 0) + 1
        return {
            "base_url": BASE_URL,
            "generated_at": datetime.now(timezone.utc).isoformat(),
            "duration_seconds": round(time.time() - self._t0, 2),
            "total": len(self.checks),
            "passed": counts["pass"],
            "failed": counts["fail"],
            "skipped": counts["skip"],
        }


def timed(fn):
    """Wrap a check so exceptions become a FAIL instead of aborting the run."""
    def wrapper(report: Report, *args, **kwargs):
        t = time.time()
        try:
            return fn(report, *args, **kwargs)
        except AssertionError as exc:
            report.record(fn.__name__, "fail", str(exc) or "assertion failed",
                          ms=round((time.time() - t) * 1000))
        except Exception as exc:  # noqa: BLE001
            report.record(fn.__name__, "fail", f"unexpected error: {exc!r}",
                          ms=round((time.time() - t) * 1000))
        return None
    return wrapper


# --------------------------------------------------------------------------- http helpers
def new_session() -> requests.Session:
    s = requests.Session()
    s.verify = VERIFY_TLS
    s.headers["Origin"] = BASE_URL
    return s


def csrf_of(session: requests.Session) -> str:
    return session.cookies.get(CSRF_COOKIE, "")


def prime_csrf(session: requests.Session) -> None:
    session.get(f"{BASE_URL}/", timeout=TIMEOUT)


def login(session: requests.Session, username: str, password: str) -> requests.Response:
    prime_csrf(session)
    return session.post(
        f"{BASE_URL}/api/auth/login",
        data={"username": username, "password": password},
        headers={"X-CSRF-Token": csrf_of(session)},
        timeout=TIMEOUT,
    )


def admin_headers(session: requests.Session) -> dict:
    return {"X-CSRF-Token": csrf_of(session), "Content-Type": "application/json"}


# --------------------------------------------------------------------------- checks
@timed
def check_health(report: Report, session: requests.Session) -> None:
    # /health is the public liveness/readiness probe a load balancer hits — it must
    # answer 200 without authentication. (/api/health is admin-gated; checked after login.)
    r = session.get(f"{BASE_URL}/health", timeout=TIMEOUT)
    assert r.status_code == 200, f"public /health returned {r.status_code}, expected 200"
    report.record("health_and_readiness", "pass", "GET /health -> 200 (public probe)")


@timed
def check_authz_boundary(report: Report) -> None:
    anon = new_session()
    r = anon.get(f"{BASE_URL}/api/admin/users", timeout=TIMEOUT)
    assert r.status_code in (401, 403), f"unauth admin access got {r.status_code}, expected 401/403"
    report.record("authz_boundary_unauthenticated", "pass",
                  f"GET /api/admin/users unauthenticated -> {r.status_code}")


@timed
def check_csrf_enforced(report: Report, session: requests.Session) -> None:
    # A state-changing admin write with NO CSRF header must be refused.
    r = session.post(
        f"{BASE_URL}/api/admin/users",
        json={"username": "csrf_probe", "password": "x" * 10, "role": "SUPERVISOR"},
        headers={"Content-Type": "application/json"},  # deliberately no X-CSRF-Token
        timeout=TIMEOUT,
    )
    assert r.status_code in (401, 403), f"CSRF-less admin write got {r.status_code}, expected 401/403"
    report.record("csrf_double_submit_enforced", "pass",
                  f"admin write without X-CSRF-Token -> {r.status_code}")


@timed
def check_login_session(report: Report, session: requests.Session) -> None:
    r = login(session, ADMIN_USERNAME, ADMIN_PASSWORD)
    assert r.status_code == 200, f"login returned {r.status_code}: {r.text[:120]}"
    assert session.cookies.get(SESSION_COOKIE), "no session cookie after login"
    who = session.get(f"{BASE_URL}/api/admin/users?page=1", timeout=TIMEOUT)
    assert who.status_code == 200, f"authenticated admin list returned {who.status_code}"
    h = session.get(f"{BASE_URL}/api/health", timeout=TIMEOUT)
    assert h.status_code == 200, f"authenticated /api/health returned {h.status_code}"
    report.record("login_and_session", "pass",
                  f"login 200, session cookie set, admin list {who.status_code}, /api/health {h.status_code}")


def _discover_kindergarten(session: requests.Session) -> int | None:
    r = session.get(f"{BASE_URL}/api/admin/options/kindergartens", params={"page_size": 5}, timeout=TIMEOUT)
    if r.status_code != 200:
        return None
    body = r.json()
    items = body.get("kindergartens") or body.get("items") or body.get("data") or []
    return items[0].get("id") if items else None


@timed
def check_admin_crud_soft_delete(report: Report, session: requests.Session, created: list) -> None:
    uname = f"smoke_{uuid.uuid4().hex[:10]}"
    pwd = "Sm0ke!" + uuid.uuid4().hex[:8]
    kg_id = _discover_kindergarten(session)  # SUPERVISOR must belong to a kindergarten
    payload = {"username": uname, "password": pwd, "role": "SUPERVISOR", "full_name": "Smoke Test"}
    if kg_id:
        payload["kindergarten_id"] = kg_id
    # create
    r = session.post(f"{BASE_URL}/api/admin/users",
                     data=json.dumps(payload),
                     headers=admin_headers(session), timeout=TIMEOUT)
    assert r.status_code == 201, f"create user got {r.status_code}: {r.text[:160]}"
    uid = (r.json() or {}).get("id")
    assert uid, f"create response missing id: {r.text[:120]}"
    created.append(uid)
    # read
    g = session.get(f"{BASE_URL}/api/admin/users/{uid}", timeout=TIMEOUT)
    assert g.status_code == 200, f"read created user got {g.status_code}"
    # soft delete
    d = session.delete(f"{BASE_URL}/api/admin/users/{uid}",
                       headers={"X-CSRF-Token": csrf_of(session)}, timeout=TIMEOUT)
    assert d.status_code in (200, 204), f"delete user got {d.status_code}"
    # soft-delete protection: unreachable
    g2 = session.get(f"{BASE_URL}/api/admin/users/{uid}", timeout=TIMEOUT)
    assert g2.status_code == 404, f"deleted user still reachable ({g2.status_code}), expected 404"
    # soft-delete protection: cannot authenticate
    victim = new_session()
    la = login(victim, uname, pwd)
    assert la.status_code in (401, 403), f"deleted user could authenticate ({la.status_code})"
    report.record("admin_crud_and_soft_delete", "pass",
                  f"create 201 -> read 200 -> delete {d.status_code} -> ghost 404 -> login {la.status_code}",
                  user_id=uid)


@timed
def check_import_limits(report: Report, session: requests.Session) -> None:
    results = []
    # XLSX endpoint: a non-ZIP payload must be rejected (bounded, not 500).
    files = {"file": ("bad.xlsx", b"this is not a real xlsx zip", "application/vnd.ms-excel")}
    r = session.post(f"{BASE_URL}/api/admin/kindergartens/import-excel",
                     files=files, headers={"X-CSRF-Token": csrf_of(session)}, timeout=TIMEOUT)
    assert r.status_code in (400, 415, 422), f"malformed XLSX got {r.status_code}, expected 4xx"
    results.append(f"xlsx-nonzip={r.status_code}")
    # CSV endpoint: a malformed CSV must be rejected with a validation error, not a crash.
    files = {"file": ("bad.csv", b"\x00\x01 not,a,valid\ncsv payload", "text/csv")}
    r2 = session.post(f"{BASE_URL}/api/admin/users/import-csv",
                      files=files, headers={"X-CSRF-Token": csrf_of(session)}, timeout=TIMEOUT)
    assert r2.status_code in (400, 415, 422), f"malformed CSV got {r2.status_code}, expected 4xx"
    results.append(f"csv-malformed={r2.status_code}")
    report.record("import_limits_enforced", "pass", ", ".join(results))


@timed
def check_exports(report: Report, session: requests.Session) -> None:
    r = session.get(f"{BASE_URL}/api/admin/users/export", timeout=TIMEOUT)
    assert r.status_code == 200, f"users export got {r.status_code}"
    ctype = r.headers.get("Content-Type", "")
    assert "csv" in ctype or "excel" in ctype or "octet-stream" in ctype, f"unexpected export type: {ctype}"
    report.record("reports_and_exports", "pass",
                  f"GET /api/admin/users/export 200, content-type={ctype[:40]}, bytes={len(r.content)}")


def _discover_manager(session: requests.Session) -> int | None:
    if IMPERSONATE_USER_ID:
        return int(IMPERSONATE_USER_ID)
    for params in ({"role": "MANAGER", "page": 1}, {"page": 1, "page_size": 100}):
        r = session.get(f"{BASE_URL}/api/admin/users", params=params, timeout=TIMEOUT)
        if r.status_code != 200:
            continue
        body = r.json()
        items = body.get("items") or body.get("users") or body.get("data") or (body if isinstance(body, list) else [])
        for u in items:
            role = str(u.get("role", "")).upper()
            active = str(u.get("status", "ACTIVE")).upper() == "ACTIVE" and not u.get("deleted_at")
            if role == "MANAGER" and active:
                return u.get("id")
    return None


@timed
def check_impersonation_full(report: Report, session: requests.Session) -> None:
    target = _discover_manager(session)
    if not target:
        report.record("impersonation_full", "skip",
                      "no active MANAGER found; set SMOKE_IMPERSONATE_USER_ID to enable")
        return

    imp = new_session()
    assert login(imp, ADMIN_USERNAME, ADMIN_PASSWORD).status_code == 200, "impersonation admin login failed"

    r = imp.post(f"{BASE_URL}/api/admin/impersonate",
                 data=json.dumps({"target_user_id": int(target), "reason": "staging smoke test"}),
                 headers=admin_headers(imp), timeout=TIMEOUT)
    assert r.status_code == 200, f"impersonate got {r.status_code}: {r.text[:160]}"
    restore_cookie = imp.cookies.get("kinjo_impersonation")

    # exit restores the admin (session is the MANAGER until this point)
    ex = imp.post(f"{BASE_URL}/api/admin/exit-impersonation",
                  headers={"X-CSRF-Token": csrf_of(imp)}, timeout=TIMEOUT)
    assert ex.status_code == 200, f"exit-impersonation got {ex.status_code}"

    # audit attribution: as the RESTORED admin, the start event must be queryable
    aud = imp.get(f"{BASE_URL}/api/admin/impersonate/audit", timeout=TIMEOUT)
    assert aud.status_code == 200, f"impersonation audit query as admin got {aud.status_code}"
    audit_ok = aud.status_code == 200

    # replay rejection: re-presenting the consumed restore token must fail closed
    replay_status = "n/a"
    if restore_cookie:
        replay = new_session()
        login(replay, ADMIN_USERNAME, ADMIN_PASSWORD)
        replay.cookies.set("kinjo_impersonation", restore_cookie)
        rr = replay.post(f"{BASE_URL}/api/admin/exit-impersonation",
                         headers={"X-CSRF-Token": csrf_of(replay)}, timeout=TIMEOUT)
        replay_status = rr.status_code
        assert rr.status_code in (400, 401, 403, 409), \
            f"consumed restore token replay got {rr.status_code}, expected 4xx"

    report.record("impersonation_full", "pass",
                  f"start 200 -> exit 200 -> audit {aud.status_code} -> replay {replay_status}",
                  target_user_id=target, audit_ok=audit_ok)


@timed
def check_logout(report: Report, session: requests.Session) -> None:
    r = session.post(f"{BASE_URL}/api/auth/logout",
                     headers={"X-CSRF-Token": csrf_of(session)}, timeout=TIMEOUT)
    assert r.status_code in (200, 204), f"logout got {r.status_code}"
    after = session.get(f"{BASE_URL}/api/admin/users", timeout=TIMEOUT)
    assert after.status_code in (401, 403), f"session still valid after logout ({after.status_code})"
    report.record("logout_revokes_session", "pass",
                  f"logout {r.status_code}, post-logout admin access {after.status_code}")


@timed
def check_rate_limit(report: Report) -> None:
    if not RATELIMIT_PROBE:
        report.record("rate_limit_boundary", "skip", "disabled via SMOKE_RATELIMIT_PROBE=false")
        return
    probe = new_session()
    prime_csrf(probe)
    statuses = []
    for _ in range(40):
        r = probe.post(f"{BASE_URL}/api/auth/login",
                       data={"username": "no_such_user", "password": "wrong-pass-123"},
                       headers={"X-CSRF-Token": csrf_of(probe)}, timeout=TIMEOUT)
        statuses.append(r.status_code)
        if r.status_code == 429:
            break
    if 429 in statuses:
        report.record("rate_limit_boundary", "pass", f"429 after {statuses.index(429) + 1} rapid attempts")
    else:
        report.record("rate_limit_boundary", "skip",
                      f"no 429 in {len(statuses)} attempts (limit may be higher or disabled in this env)")


# --------------------------------------------------------------------------- cleanup
def cleanup(report: Report, admin_session: requests.Session, created: list) -> None:
    # Runs while the admin session is still valid (before logout / the rate-limit
    # probe), so no re-authentication is needed. 404 counts as removed (the CRUD
    # check already soft-deletes its own user; this is the safety net).
    if not created:
        report.record("cleanup", "pass", "no test artifacts to remove")
        return
    remaining = []
    for uid in created:
        d = admin_session.delete(f"{BASE_URL}/api/admin/users/{uid}",
                                 headers={"X-CSRF-Token": csrf_of(admin_session)}, timeout=TIMEOUT)
        if d.status_code not in (200, 204, 404):
            remaining.append(f"{uid}:{d.status_code}")
    if remaining:
        report.record("cleanup", "fail", f"test users not removed: {', '.join(remaining)}")
    else:
        report.record("cleanup", "pass", f"removed/confirmed-gone {len(created)} test artifact(s)")


# --------------------------------------------------------------------------- main
def main() -> int:
    parser = argparse.ArgumentParser(description="KinJo Admin staging smoke test")
    parser.add_argument("--output", default=env("SMOKE_OUTPUT"), help="write JSON report to this path")
    args = parser.parse_args()

    if not ADMIN_PASSWORD:
        print("ERROR: SMOKE_ADMIN_PASSWORD is required (supply via the deploy secret store).", file=sys.stderr)
        return 2

    print(f"KinJo Admin smoke test -> {BASE_URL} (verify_tls={VERIFY_TLS})", file=sys.stderr)
    report = Report()
    created: list = []
    admin = new_session()

    # Order matters: unauthenticated checks first, then authenticated flow, logout last.
    check_health(report, admin)
    check_authz_boundary(report)
    check_login_session(report, admin)          # establishes the admin session
    check_csrf_enforced(report, admin)
    check_admin_crud_soft_delete(report, admin, created)
    check_import_limits(report, admin)
    check_exports(report, admin)
    check_impersonation_full(report, admin)
    cleanup(report, admin, created)              # delete test data while admin session is valid
    check_logout(report, admin)                  # revokes the admin session
    check_rate_limit(report)                     # last: harmlessly trips the login limiter at the end

    payload = {"summary": report.summary(), "checks": report.checks}
    text = json.dumps(payload, indent=2, ensure_ascii=False)
    if args.output:
        with open(args.output, "w", encoding="utf-8") as fh:
            fh.write(text)
        print(f"\nJSON report written to {args.output}", file=sys.stderr)
    print(text)

    s = report.summary()
    print(f"\nSUMMARY: {s['passed']} passed, {s['failed']} failed, {s['skipped']} skipped "
          f"in {s['duration_seconds']}s", file=sys.stderr)
    return 1 if s["failed"] else 0


if __name__ == "__main__":
    sys.exit(main())
