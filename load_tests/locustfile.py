"""
KinJo Admin Load Test — Locust

Simulates 50 concurrent admin users exercising the admin API:
  - Dashboard (cached, high-frequency)
  - User list with filters
  - User export (JSON)
  - Contact messages list
  - Governance KPIs

Usage:
    locust -f load_tests/locustfile.py --host http://localhost:8000 \
           --users 50 --spawn-rate 5 --run-time 60s --headless

Environment variables:
    LOAD_TEST_ADMIN_USERNAME  — defaults to "admin"
    LOAD_TEST_ADMIN_PASSWORD  — defaults to "Admin123!"

The test authenticates once per user at startup and reuses the JWT token
for all subsequent requests (mirrors real browser behaviour).
"""

import os
import random
from locust import HttpUser, task, between, events


ADMIN_USERNAME = os.getenv("LOAD_TEST_ADMIN_USERNAME", "admin")
ADMIN_PASSWORD = os.getenv("LOAD_TEST_ADMIN_PASSWORD", "Admin123!")

GOVERNORATES = ["Amman", "Irbid", "Zarqa", "Aqaba", "Mafraq", "Jerash", "Ajloun"]
START_DATE = "2026-01-01"
END_DATE = "2026-06-01"


class AdminUser(HttpUser):
    """Simulates an authenticated admin user navigating the admin API."""

    wait_time = between(0.5, 2.0)

    def on_start(self) -> None:
        """Authenticate once per simulated user and store the JWT."""
        resp = self.client.post(
            "/token",
            data={"username": ADMIN_USERNAME, "password": ADMIN_PASSWORD},
            name="/token [login]",
        )
        if resp.status_code != 200:
            raise RuntimeError(
                f"Login failed ({resp.status_code}): check LOAD_TEST_ADMIN_* env vars "
                f"and ensure the admin user exists in the target database."
            )
        self._token = resp.json()["access_token"]
        self._headers = {"Authorization": f"Bearer {self._token}"}

    # -----------------------------------------------------------------
    # High-frequency: dashboard (cached every 30 s server-side)
    # -----------------------------------------------------------------

    @task(5)
    def get_dashboard(self) -> None:
        gov = random.choice(GOVERNORATES + [""])
        params = f"?governorate={gov}" if gov else ""
        self.client.get(f"/api/admin/dashboard{params}", headers=self._headers, name="/api/admin/dashboard")

    # -----------------------------------------------------------------
    # Medium-frequency: user list with various filters
    # -----------------------------------------------------------------

    @task(3)
    def list_users_no_filter(self) -> None:
        self.client.get("/api/admin/users?page=1&page_size=25", headers=self._headers, name="/api/admin/users")

    @task(2)
    def list_users_role_filter(self) -> None:
        role = random.choice(["ADMIN", "MANAGER", "SUPERVISOR", "PARENT"])
        self.client.get(
            f"/api/admin/users?role={role}&page=1&page_size=25",
            headers=self._headers,
            name="/api/admin/users?role=*",
        )

    @task(2)
    def list_users_search(self) -> None:
        query = random.choice(["a", "mo", "test", "admin"])
        self.client.get(
            f"/api/admin/users?search={query}&page=1&page_size=25",
            headers=self._headers,
            name="/api/admin/users?search=*",
        )

    # -----------------------------------------------------------------
    # Low-frequency: governance KPIs and leaderboard
    # -----------------------------------------------------------------

    @task(2)
    def governance_kpis(self) -> None:
        self.client.get(
            f"/api/admin/governance/kpis?start_date={START_DATE}&end_date={END_DATE}",
            headers=self._headers,
            name="/api/admin/governance/kpis",
        )

    @task(1)
    def governance_leaderboard(self) -> None:
        self.client.get(
            f"/api/admin/governance/leaderboard?start_date={START_DATE}&end_date={END_DATE}",
            headers=self._headers,
            name="/api/admin/governance/leaderboard",
        )

    # -----------------------------------------------------------------
    # Low-frequency: contact messages and export
    # -----------------------------------------------------------------

    @task(1)
    def list_contact_messages(self) -> None:
        self.client.get(
            "/api/admin/contact-messages?page=1&page_size=25",
            headers=self._headers,
            name="/api/admin/contact-messages",
        )

    @task(1)
    def export_users_json(self) -> None:
        self.client.get(
            "/api/admin/users/export?format=json",
            headers=self._headers,
            name="/api/admin/users/export",
        )

    # -----------------------------------------------------------------
    # Admin health check
    # -----------------------------------------------------------------

    @task(1)
    def admin_health(self) -> None:
        self.client.get("/api/admin/health", headers=self._headers, name="/api/admin/health")


@events.quitting.add_listener
def on_locust_quit(environment, **kwargs) -> None:
    """Fail the run if p95 latency > 2 000 ms or error rate > 1 %."""
    stats = environment.stats.total
    if stats.num_requests == 0:
        return

    error_rate = stats.fail_ratio * 100
    p95_ms = stats.get_response_time_percentile(0.95) or 0

    print(f"\nLoad test summary: {stats.num_requests} requests, "
          f"error_rate={error_rate:.2f}%, p95={p95_ms:.0f}ms")

    if error_rate > 1.0:
        print(f"FAIL: error rate {error_rate:.2f}% exceeds 1% threshold")
        environment.process_exit_code = 1
    elif p95_ms > 2000:
        print(f"FAIL: p95 latency {p95_ms:.0f}ms exceeds 2000ms threshold")
        environment.process_exit_code = 1
    else:
        print("PASS: load test thresholds satisfied")
