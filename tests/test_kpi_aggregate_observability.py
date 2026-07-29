"""A kindergarten dropped from a KPI aggregate must be visible in the log.

kpi_service degrades rather than failing when one kindergarten's bundle raises —
which is the right call for a national dashboard — but it did so with a bare
`continue`/`pass` and no logging at all (the module had no logger). A site whose
KPI computation was systematically broken was therefore indistinguishable from a
healthy one: it simply vanished from every country and governorate rollup.

These tests drive the real aggregation loops and induce exactly one controlled
failure, rather than mocking the loop away.
"""
import logging
from datetime import date

import pytest

import kpi_service
import models
from database import get_db
from dependencies import get_current_user, require_admin
from fastapi.testclient import TestClient
from main import app

SENSITIVE_MARKERS = (
    "+9627",            # contact phone
    "@",                # any e-mail address
    "Main Street",      # address line
    "حضانة",            # Arabic kindergarten name
)


@pytest.fixture
def client(test_db):
    def override_get_db():
        yield test_db

    admin = models.User(
        username="kpiobs_admin",
        email="kpiobs@test.com",
        hashed_password="x",
        role=models.UserRole.ADMIN,
        status=models.UserStatus.ACTIVE,
    )
    test_db.add(admin)
    test_db.commit()

    app.dependency_overrides[get_db] = override_get_db
    # The rollups gate on require_admin; /kpi/alerts gates on get_current_user
    # and scopes by role, so both have to be overridden for this fixture to
    # reach every endpoint under test.
    app.dependency_overrides[require_admin] = lambda: admin
    app.dependency_overrides[get_current_user] = lambda: admin
    with TestClient(app) as c:
        yield c
    app.dependency_overrides.clear()


@pytest.fixture
def two_kindergartens(test_db):
    """Two ACTIVE kindergartens so an aggregate can lose one and still have data."""
    made = []
    for idx in (1, 2):
        kg = models.Kindergarten(
            name_ar=f"حضانة رقم {idx}",
            name_en=f"Kindergarten {idx}",
            license_number=f"LIC-OBS-{idx}",
            governorate="Amman",
            district="Amman",
            area="Abdoun",
            address_line=f"{idx} Main Street",
            contact_phone=f"+96279000000{idx}",
            contact_email=f"kg{idx}@example.com",
            status=models.KindergartenStatus.ACTIVE,
            license_valid_until=date(2030, 12, 31),
        )
        test_db.add(kg)
        made.append(kg)
    test_db.commit()
    for kg in made:
        test_db.refresh(kg)
    return made


def _break_one(monkeypatch, failing_id):
    """Make compute_kpi_bundle raise for exactly one kindergarten, real for the rest."""
    real = kpi_service.KPIService.compute_kpi_bundle

    def flaky(db, kg_id, period_start, period_end, *args, **kwargs):
        if kg_id == failing_id:
            raise RuntimeError("induced bundle failure")
        return real(db, kg_id, period_start, period_end, *args, **kwargs)

    monkeypatch.setattr(kpi_service.KPIService, "compute_kpi_bundle", staticmethod(flaky))


def _excluded(caplog):
    return [r for r in caplog.records if "KPI_AGGREGATE_RECORD_EXCLUDED" in r.getMessage()]


def _assert_no_sensitive_data(records):
    for record in records:
        text = record.getMessage()
        for marker in SENSITIVE_MARKERS:
            assert marker not in text, f"log leaked {marker!r}: {text}"


@pytest.mark.parametrize(
    "path, operation",
    [
        ("/api/kpi/levels/country", "country_rollup"),
        ("/api/kpi/levels/governorates", "governorate_rollup"),
        ("/api/kpi/alerts", "alerts"),
    ],
)
def test_failing_kindergarten_is_logged_and_does_not_abort_the_aggregate(
    client, test_db, two_kindergartens, monkeypatch, caplog, path, operation
):
    broken, healthy = two_kindergartens
    _break_one(monkeypatch, broken.id)

    with caplog.at_level(logging.WARNING, logger=kpi_service.logger.name):
        response = client.get(path)

    # 1. the aggregate still answers
    assert response.status_code == 200, response.text

    # 2. exactly one warning, naming the operation and the failing record
    excluded = _excluded(caplog)
    assert len(excluded) == 1, [r.getMessage() for r in excluded]
    message = excluded[0].getMessage()
    assert f"operation={operation}" in message
    assert f"kindergarten_id={broken.id}" in message
    assert excluded[0].levelname == "WARNING"

    # 3. the traceback is attached, so the failure is diagnosable
    assert excluded[0].exc_info is not None

    # 4. only the broken record is named — matched on the qualified field, since
    #    a bare id digit also occurs inside the period dates.
    assert f"kindergarten_id={healthy.id}" not in message
    _assert_no_sensitive_data(excluded)


def test_country_rollup_still_counts_the_surviving_kindergarten(
    client, test_db, two_kindergartens, monkeypatch, caplog
):
    """Degradation must be partial: one bad record, not an empty national view."""
    broken, _healthy = two_kindergartens
    _break_one(monkeypatch, broken.id)

    with caplog.at_level(logging.WARNING, logger=kpi_service.logger.name):
        body = client.get("/api/kpi/levels/country").json()

    assert body["level"] == "country"
    assert body["kindergarten_count"] == 1, body
    assert len(_excluded(caplog)) == 1


def test_healthy_network_logs_no_exclusion(client, test_db, two_kindergartens, caplog):
    """No induced failure must mean no warning, or the signal is worthless."""
    with caplog.at_level(logging.WARNING, logger=kpi_service.logger.name):
        response = client.get("/api/kpi/levels/country")

    assert response.status_code == 200
    assert response.json()["kindergarten_count"] == 2
    assert _excluded(caplog) == []


def test_cache_write_failure_does_not_fail_the_request(
    client, test_db, two_kindergartens, monkeypatch, caplog
):
    """A cache outage degrades to recomputation; it never breaks the response."""
    from cache_service import dashboard_cache

    def boom(*args, **kwargs):
        raise RuntimeError("redis down")

    # Leave TESTING off so the cache branch actually executes. /kpi/alerts is a
    # GET, so CSRF (unsafe methods only) is unaffected by this.
    monkeypatch.setattr(kpi_service.settings, "TESTING", False)
    monkeypatch.setattr(dashboard_cache, "get", boom)
    monkeypatch.setattr(dashboard_cache, "set", boom)

    with caplog.at_level(logging.DEBUG, logger=kpi_service.logger.name):
        response = client.get("/api/kpi/alerts")

    assert response.status_code == 200, response.text
    assert "alerts" in response.json()

    # Cache trouble is DEBUG, never WARNING: an outage would otherwise emit a
    # warning per request for its whole duration.
    assert _excluded(caplog) == []
    cache_records = [r for r in caplog.records if "cache" in r.getMessage().lower()]
    assert cache_records, "a cache failure left no trace at all"
    assert all(r.levelno == logging.DEBUG for r in cache_records), (
        [(r.levelname, r.getMessage()) for r in cache_records]
    )
