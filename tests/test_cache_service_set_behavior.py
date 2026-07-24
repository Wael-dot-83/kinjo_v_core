import json
from datetime import datetime, timezone

from cache_service import CacheService
from redis.exceptions import RedisError


class _RedisSetRecorder:
    def __init__(self):
        self.calls = []

    def set(self, key, value, ex=None):
        self.calls.append((key, value, ex))
        return True


class _RedisSetError:
    def set(self, key, value, ex=None):
        raise RedisError("redis write failed")


def test_cache_service_set_uses_redis_set_with_ex_ttl(monkeypatch):
    cache = CacheService()
    recorder = _RedisSetRecorder()
    cache.redis_client = recorder

    cache.set("kpi:test", {"a": 1}, ttl_seconds=120)

    assert len(recorder.calls) == 1
    key, payload, ttl = recorder.calls[0]
    assert key == "kinjo:kpi:test"
    assert ttl == 120

    decoded = json.loads(payload)
    assert decoded["value"] == {"a": 1}

    expires = datetime.fromisoformat(decoded["expires"])
    assert expires.tzinfo is not None
    assert expires > datetime.now(timezone.utc)


def test_cache_service_set_falls_back_to_memory_when_redis_set_fails(monkeypatch):
    cache = CacheService()
    cache.redis_client = _RedisSetError()

    cache.set("kpi:fallback", {"ok": True}, ttl_seconds=30)

    assert "kpi:fallback" in cache.memory_cache
    entry = cache.memory_cache["kpi:fallback"]
    assert entry["value"] == {"ok": True}
    assert entry["expires"] > datetime.now(timezone.utc)
