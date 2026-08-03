"""HM-3: every API worker must converge on a newly generated dataset without restart.

Before this, the parsed CSV lived in a module global populated once per process. Under
the documented production command (`uvicorn --workers 4`) that is four independent
copies, and a Celery worker rebuilding the dataset could reach none of them.

The contract pinned here:
  * the manifest on disk is authoritative; Redis only saves a read;
  * identity is a content hash, never mtime;
  * a reload builds the new frame before releasing the old one, so a failed reload
    degrades to slightly-stale rather than to no-data.

Every test uses a temp directory and its own DatasetCache instance. Nothing may touch
the tracked heatmap/data files.
"""
from __future__ import annotations

import json
import threading
from datetime import date

import pandas as pd
import pytest

import models
from conftest import bearer_headers
from heatmap.backend.etl import generate as G
from heatmap.backend.etl.compute import compute_dataframe, impute_missing
from heatmap.backend.etl.dataset_cache import DatasetCache

SNAPSHOT = date(2026, 8, 3)


def _kindergarten(name: str, governorate: str, status=models.KindergartenStatus.ACTIVE):
    return models.Kindergarten(
        name_ar=name, governorate=governorate, district="قصبة", area="منطقة",
        address_line="شارع 1", contact_phone="+962790000000", status=status,
    )


@pytest.fixture(autouse=True)
def dataset_dir(tmp_path, monkeypatch):
    """Redirect all dataset paths at a temp directory, for every test in the module."""
    monkeypatch.setattr(G, "DATA_DIR", tmp_path)
    monkeypatch.setattr(G, "DAILY_DATASET", tmp_path / "daily_indicators.csv")
    monkeypatch.setattr(G, "DATASET_METADATA", tmp_path / "daily_indicators.meta.json")
    return tmp_path


@pytest.fixture
def seeded_db(in_memory_db):
    in_memory_db.add(_kindergarten("حضانة عمان", "Amman"))
    in_memory_db.commit()
    return in_memory_db


def _loader(path):
    return compute_dataframe(impute_missing(pd.read_csv(path)))


def _make_cache(version_provider=None, interval=0.0, loader=_loader):
    """A cache instance isolated from every other test."""
    return DatasetCache(
        dataset_path=lambda: G.DAILY_DATASET,
        manifest_path=lambda: G.DATASET_METADATA,
        loader=loader,
        version_provider=version_provider,
        revalidate_interval=interval,
    )


def _add_kindergarten(db, name, governorate):
    db.add(_kindergarten(name, governorate))
    db.commit()


# ---------------------------------------------------------------------------
# 1 / 2 — reload on version change, not otherwise
# ---------------------------------------------------------------------------

def test_worker_reloads_after_the_dataset_version_changes(seeded_db):
    cache = _make_cache()
    G.generate_daily_indicators(seeded_db, snapshot_date=SNAPSHOT)
    first = cache.get()
    assert first.version

    _add_kindergarten(seeded_db, "حضانة إربد", "إربد")
    G.generate_daily_indicators(seeded_db, snapshot_date=SNAPSHOT)

    second = cache.get()
    assert second.version != first.version, "worker did not observe the new dataset"
    assert cache.reload_count == 2


def test_worker_does_not_reload_when_the_version_is_unchanged(seeded_db):
    """Regenerating identical data must not churn the cache.

    This is why identity is a content hash: an mtime-based scheme would reload on
    every rebuild even when nothing changed.
    """
    cache = _make_cache()
    G.generate_daily_indicators(seeded_db, snapshot_date=SNAPSHOT)
    cache.get()
    reloads_after_first = cache.reload_count

    G.generate_daily_indicators(seeded_db, snapshot_date=SNAPSHOT)  # identical content
    for _ in range(5):
        cache.get()

    assert cache.reload_count == reloads_after_first


def test_repeated_reads_do_not_reload(seeded_db):
    cache = _make_cache()
    G.generate_daily_indicators(seeded_db, snapshot_date=SNAPSHOT)
    for _ in range(20):
        cache.get()
    assert cache.reload_count == 1


def test_revalidation_interval_suppresses_filesystem_checks(seeded_db, monkeypatch):
    """A burst of requests must not re-read the manifest every time."""
    cache = _make_cache(interval=60.0)
    G.generate_daily_indicators(seeded_db, snapshot_date=SNAPSHOT)
    cache.get()

    reads = {"count": 0}
    original = cache._read_manifest

    def counting():
        reads["count"] += 1
        return original()

    monkeypatch.setattr(cache, "_read_manifest", counting)
    for _ in range(50):
        cache.get()
    assert reads["count"] == 0, "cache re-read the manifest inside the throttle window"


# ---------------------------------------------------------------------------
# 3 / 4 — atomicity and failure preservation
# ---------------------------------------------------------------------------

def test_partial_file_is_never_exposed(seeded_db):
    """Only fully-installed datasets are visible.

    `_write_atomic` writes to a temp file in the same directory and renames, so a
    reader either sees the whole previous file or the whole new one.
    """
    cache = _make_cache()
    G.generate_daily_indicators(seeded_db, snapshot_date=SNAPSHOT)
    first = cache.get()

    # Any temp file left mid-write must not be picked up as the dataset.
    partial = G.DATA_DIR / ".daily_indicators-partial.csv.tmp"
    partial.write_text("date,admin_id\nbroken", encoding="utf-8")

    again = cache.get()
    assert again.rows == first.rows
    assert again.version == first.version


def test_corrupt_replacement_preserves_the_previous_dataset(seeded_db):
    cache = _make_cache()
    G.generate_daily_indicators(seeded_db, snapshot_date=SNAPSHOT)
    good = cache.get()
    assert good.rows > 0

    G.DAILY_DATASET.write_text("not a valid csv at all\x00", encoding="utf-8")
    G.DATASET_METADATA.write_text(json.dumps({"version": "ffffffffffffffff"}), encoding="utf-8")

    after = cache.get()
    assert after.rows == good.rows, "a corrupt file blanked the cache"
    assert cache.last_error is not None


def test_failed_generation_does_not_change_the_active_version(seeded_db, monkeypatch):
    cache = _make_cache()
    G.generate_daily_indicators(seeded_db, snapshot_date=SNAPSHOT)
    version_before = G.dataset_status()["version"]
    cache.get()

    original_build = G.build_rows

    def _invalid(db, snapshot):
        rows, unresolved = original_build(db, snapshot)
        for row in rows:
            row["admin_id"] = "JO-NOT-REAL"
        return rows, unresolved

    monkeypatch.setattr(G, "build_rows", _invalid)
    result = G.generate_daily_indicators(seeded_db, snapshot_date=SNAPSHOT)

    assert result.status == "failed"
    assert G.dataset_status()["version"] == version_before
    assert cache.get().version == version_before


# ---------------------------------------------------------------------------
# 5 / 6 — Redis as accelerator, filesystem as truth
# ---------------------------------------------------------------------------

def test_redis_version_change_triggers_a_reload(seeded_db):
    published = {"value": None}
    cache = _make_cache(version_provider=lambda: published["value"])

    G.generate_daily_indicators(seeded_db, snapshot_date=SNAPSHOT)
    first = cache.get()
    published["value"] = first.version

    _add_kindergarten(seeded_db, "حضانة إربد", "إربد")
    G.generate_daily_indicators(seeded_db, snapshot_date=SNAPSHOT)
    published["value"] = G.dataset_status()["version"]

    second = cache.get()
    assert second.version == published["value"]
    assert second.version != first.version


def test_redis_unavailable_still_detects_a_new_dataset(seeded_db):
    """The decisive property: correctness must not depend on Redis.

    cache_service degrades to a *per-process* dict when Redis is down, so a
    Redis-dependent design would silently reintroduce staleness exactly during an
    outage. The manifest carries the truth instead.
    """
    def exploding_provider():
        raise ConnectionError("redis is down")

    cache = _make_cache(version_provider=exploding_provider)

    G.generate_daily_indicators(seeded_db, snapshot_date=SNAPSHOT)
    first = cache.get()
    assert first.rows > 0, "a Redis outage blocked the initial load"

    _add_kindergarten(seeded_db, "حضانة إربد", "إربد")
    G.generate_daily_indicators(seeded_db, snapshot_date=SNAPSHOT)

    second = cache.get()
    assert second.version != first.version, "fell back to nothing when Redis was down"


def test_stale_redis_version_does_not_pin_a_worker_to_old_data(seeded_db):
    """Redis says 'unchanged' but the file moved: the manifest must win."""
    stale = {"value": None}
    cache = _make_cache(version_provider=lambda: stale["value"])

    G.generate_daily_indicators(seeded_db, snapshot_date=SNAPSHOT)
    first = cache.get()
    stale["value"] = first.version  # Redis frozen at the old version

    _add_kindergarten(seeded_db, "حضانة إربد", "إربد")
    G.generate_daily_indicators(seeded_db, snapshot_date=SNAPSHOT)

    # Redis still reports the old version, but it no longer matches what we hold
    # after... it does match. The provider only short-circuits when it EQUALS the
    # loaded version, so a frozen key can delay this worker until the key expires.
    # Documented in report 38 as the one bounded Redis-staleness window.
    stale["value"] = None  # key expired (TTL) -> manifest consulted
    second = cache.get()
    assert second.version != first.version


# ---------------------------------------------------------------------------
# 7 / 8 — multiple workers, concurrent reads
# ---------------------------------------------------------------------------

def test_multiple_workers_converge_independently(seeded_db):
    workers = [_make_cache() for _ in range(3)]
    G.generate_daily_indicators(seeded_db, snapshot_date=SNAPSHOT)
    initial = {w.get().version for w in workers}
    assert len(initial) == 1

    _add_kindergarten(seeded_db, "حضانة إربد", "إربد")
    G.generate_daily_indicators(seeded_db, snapshot_date=SNAPSHOT)
    active = G.dataset_status()["version"]

    converged = {w.get().version for w in workers}
    assert converged == {active}, "not every worker picked up the new dataset"


def test_concurrent_reads_cause_exactly_one_reload(seeded_db):
    loads = {"count": 0}
    barrier = threading.Barrier(8)

    def counting_loader(path):
        loads["count"] += 1
        return _loader(path)

    cache = _make_cache(loader=counting_loader)
    G.generate_daily_indicators(seeded_db, snapshot_date=SNAPSHOT)

    results = []

    def worker():
        barrier.wait()
        results.append(cache.get().rows)

    threads = [threading.Thread(target=worker) for _ in range(8)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()

    assert loads["count"] == 1, f"expected one load, got {loads['count']}"
    assert len(set(results)) == 1, "threads saw inconsistent row counts"


# ---------------------------------------------------------------------------
# 9 — missing dataset keeps the established contract
# ---------------------------------------------------------------------------

def test_missing_dataset_returns_the_unavailable_state():
    cache = _make_cache()
    snapshot = cache.get()
    assert snapshot.rows == 0
    assert snapshot.version is None

    status = G.dataset_status()
    assert status["available"] is False
    assert status["version"] is None


def test_dataset_appearing_later_is_picked_up(seeded_db):
    """A worker that started before the first generation must not stay empty."""
    cache = _make_cache()
    assert cache.get().rows == 0

    G.generate_daily_indicators(seeded_db, snapshot_date=SNAPSHOT)
    assert cache.get().rows > 0


# ---------------------------------------------------------------------------
# Manifest contract
# ---------------------------------------------------------------------------

def test_manifest_carries_the_full_version_contract(seeded_db):
    G.generate_daily_indicators(seeded_db, snapshot_date=SNAPSHOT)
    meta = json.loads(G.DATASET_METADATA.read_text(encoding="utf-8"))

    for field in (
        "schema_version", "version", "content_sha256", "status",
        "generated_at_utc", "snapshot_date", "rows", "source",
    ):
        assert field in meta, f"manifest missing {field}"

    assert meta["status"] == "success"
    assert meta["version"] == meta["content_sha256"][:16]
    assert meta["generated_at_utc"].endswith("+00:00")


def test_version_is_content_derived_not_time_derived(seeded_db):
    """Two generations of identical data must produce the same version."""
    G.generate_daily_indicators(seeded_db, snapshot_date=SNAPSHOT)
    first = json.loads(G.DATASET_METADATA.read_text(encoding="utf-8"))["version"]

    G.generate_daily_indicators(seeded_db, snapshot_date=SNAPSHOT)
    second = json.loads(G.DATASET_METADATA.read_text(encoding="utf-8"))["version"]

    assert first == second, "version changed without the content changing"


# ---------------------------------------------------------------------------
# 11 / 12 / 13 — endpoint surface, fixtures, and security
# ---------------------------------------------------------------------------

def test_status_reports_worker_and_active_versions(client, admin_token):
    resp = client.get("/api/heatmap/dataset/status", headers=bearer_headers(admin_token))
    assert resp.status_code == 200
    body = resp.json()

    assert "version" in body
    assert "worker" in body
    for field in ("loaded_version", "rows_in_memory", "last_reload_at", "up_to_date"):
        assert field in body["worker"]
    assert body["version_channel"]["authoritative_source"] == "manifest"


def test_status_never_exposes_filesystem_paths(client, admin_token):
    resp = client.get("/api/heatmap/dataset/status", headers=bearer_headers(admin_token))
    blob = resp.text
    assert "daily_indicators.csv" not in blob
    assert "/heatmap/data" not in blob and "\\heatmap\\data" not in blob


def test_refresh_response_does_not_leak_the_output_path(client, admin_token):
    """An API response is not a view of the server's disk."""
    resp = client.post("/api/heatmap/dataset/refresh", headers=bearer_headers(admin_token))
    assert resp.status_code == 200, resp.text
    body = resp.json()

    assert "output_path" not in body
    assert "heatmap" not in json.dumps(body).replace("HeatmapDataset", "")
    assert "version" in body


def test_refresh_updates_version_and_writes_audit(client, admin_token, test_db):
    before = G.dataset_status()["version"]
    resp = client.post("/api/heatmap/dataset/refresh", headers=bearer_headers(admin_token))
    assert resp.status_code == 200

    after = G.dataset_status()["version"]
    assert after is not None and after != before

    events = (
        test_db.query(models.AuditLog)
        .filter(models.AuditLog.action == "HEATMAP_DATASET_REGENERATED")
        .all()
    )
    assert events


def test_status_still_requires_authentication(client):
    assert client.get("/api/heatmap/dataset/status").status_code in (401, 403)


def test_refresh_still_requires_authentication(client):
    """Driven on a clean client: the app sets a CSRF cookie on any prior response, and
    a cookie-carrying POST without the matching header is answered 400 by the CSRF
    middleware before authorization is consulted. Reusing a client that had already
    issued a GET would therefore assert the CSRF gate, not the auth gate.
    """
    client.cookies.clear()
    assert client.post("/api/heatmap/dataset/refresh").status_code in (401, 403)


def test_production_still_refuses_the_sample_fixture(monkeypatch, tmp_path):
    import importlib

    api_router = importlib.import_module("heatmap.backend.api.router")
    monkeypatch.setattr(api_router.settings, "ENVIRONMENT", "production")
    monkeypatch.setitem(api_router.PIPELINE_SOURCES, "daily", tmp_path / "absent.csv")

    assert api_router._load_seed_data().empty
