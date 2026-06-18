"""
Tests for the heat map caching layer.
"""
import os
import sys
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import pytest

from heatmap.backend import cache as heatmap_cache


def test_cached_set_and_get_roundtrip(monkeypatch):
    """cached_set + cached_get should roundtrip a value via the cache service."""
    storage = {}

    class _FakeCache:
        def get(self, key):
            return storage.get(key)
        def set(self, key, value, ttl=None):
            storage[key] = value
        def delete(self, key):
            storage.pop(key, None)

    def fake_get_cache():
        return _FakeCache()
    monkeypatch.setattr(heatmap_cache, "get_cache", fake_get_cache)

    # First call: miss
    assert heatmap_cache.cached_get("test_key") is None
    # Set a value
    heatmap_cache.cached_set("test_key", {"x": 1}, ttl=60)
    # Second call: hit
    assert heatmap_cache.cached_get("test_key") == {"x": 1}


def test_cached_get_returns_none_on_cache_error(monkeypatch):
    def broken_get_cache():
        raise RuntimeError("redis is down")
    monkeypatch.setattr(heatmap_cache, "get_cache", broken_get_cache)
    # Should return None (not raise) on cache errors
    assert heatmap_cache.cached_get("any") is None


def test_cached_set_silently_swallows_errors(monkeypatch):
    def broken_get_cache():
        raise RuntimeError("redis is down")
    monkeypatch.setattr(heatmap_cache, "get_cache", broken_get_cache)
    # Should not raise
    heatmap_cache.cached_set("any", {"v": 1}, ttl=60)


def test_invalidate_heat_map_cache(monkeypatch):
    """invalidate_heat_map_cache should delete all known keys."""
    storage = {}
    deleted = []

    class _FakeCache:
        def get(self, key):
            return storage.get(key)
        def set(self, key, value, ttl=None):
            storage[key] = value
        def delete(self, key):
            deleted.append(key)
            storage.pop(key, None)
    monkeypatch.setattr(heatmap_cache, "get_cache", lambda: _FakeCache())

    heatmap_cache.invalidate_heat_map_cache()
    # Should have tried to delete all 7 known keys
    assert len(deleted) == 7
    for key in ["governorates", "indicators", "data", "geojson",
                "correlations", "regression", "daily_update"]:
        assert f"admin_heat_map:{key}" in deleted


def test_cached_get_returns_none_when_get_cache_unavailable(monkeypatch):
    monkeypatch.setattr(heatmap_cache, "get_cache", None)
    assert heatmap_cache.cached_get("anything") is None
    # Should not raise
    heatmap_cache.cached_set("anything", {"v": 1})
    # Should not raise
    heatmap_cache.invalidate_heat_map_cache()
