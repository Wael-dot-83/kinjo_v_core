"""Security contracts for dangerous-operation confirmation tokens."""

import json
import threading
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timedelta, timezone
from unittest.mock import patch

import pytest
from redis.exceptions import RedisError

from admin_security import (
    APIError,
    _confirmation_token_key,
    generate_confirmation_token,
    verify_confirmation_token,
)
from cache_service import CacheService, cache_service
from config import settings


@pytest.fixture(autouse=True)
def isolated_confirmation_store(monkeypatch):
    monkeypatch.setattr(settings, "ENVIRONMENT", "development")
    monkeypatch.setattr(cache_service, "redis_client", None)
    with cache_service._memory_lock:
        cache_service.memory_cache.clear()
    yield
    with cache_service._memory_lock:
        cache_service.memory_cache.clear()


def test_token_is_random_and_single_use():
    first = generate_confirmation_token("bulk_delete", [1, 2], actor_id=7)
    second = generate_confirmation_token("bulk_delete", [1, 2], actor_id=7)

    assert first != second
    assert verify_confirmation_token(first, "bulk_delete", [2, 1], actor_id=7) is True
    assert verify_confirmation_token(first, "bulk_delete", [1, 2], actor_id=7) is False


@pytest.mark.parametrize(
    ("actual_action", "actual_targets", "actual_actor"),
    [
        ("bulk_status_update", [1, 2], 7),
        ("bulk_delete", [1, 3], 7),
        ("bulk_delete", [1, 2], 8),
    ],
)
def test_token_is_bound_to_action_targets_and_actor(actual_action, actual_targets, actual_actor):
    token = generate_confirmation_token("bulk_delete", [1, 2], actor_id=7)

    assert verify_confirmation_token(token, actual_action, actual_targets, actual_actor) is False


def test_expired_token_is_rejected():
    token = generate_confirmation_token("bulk_delete", [1], actor_id=7)
    key = _confirmation_token_key(token)
    cache_service.memory_cache[key]["expires"] = datetime.now(timezone.utc) - timedelta(seconds=1)

    assert verify_confirmation_token(token, "bulk_delete", [1], actor_id=7) is False


def test_concurrent_verification_has_exactly_one_winner():
    token = generate_confirmation_token("bulk_delete", [1, 2], actor_id=7)
    barrier = threading.Barrier(8)

    def verify_once():
        barrier.wait()
        return verify_confirmation_token(token, "bulk_delete", [1, 2], actor_id=7)

    with ThreadPoolExecutor(max_workers=8) as executor:
        results = list(executor.map(lambda _index: verify_once(), range(8)))

    assert results.count(True) == 1
    assert results.count(False) == 7


def test_verification_uses_constant_time_binding_comparison():
    token = generate_confirmation_token("bulk_delete", [1], actor_id=7)

    with patch("admin_security.hmac.compare_digest", wraps=__import__("hmac").compare_digest) as compare:
        assert verify_confirmation_token(token, "bulk_delete", [1], actor_id=7) is True

    compare.assert_called_once()


def test_production_without_shared_store_fails_closed(monkeypatch):
    monkeypatch.setattr(settings, "ENVIRONMENT", "production")
    monkeypatch.setattr(cache_service, "redis_client", None)

    with pytest.raises(APIError) as exc_info:
        generate_confirmation_token("bulk_delete", [1], actor_id=7)

    assert exc_info.value.status_code == 503
    assert verify_confirmation_token("attacker-token", "bulk_delete", [1], actor_id=7) is False


class _GetDelRedis:
    def __init__(self, payload):
        self.payload = payload
        self.calls = 0

    def getdel(self, key):
        self.calls += 1
        payload, self.payload = self.payload, None
        return payload


class _LuaRedis:
    def __init__(self, payload):
        self.payload = payload
        self.calls = 0

    def eval(self, script, key_count, key):
        self.calls += 1
        payload, self.payload = self.payload, None
        return payload


class _FailingRedis:
    def getdel(self, key):
        raise RedisError("store unavailable")

    def eval(self, script, key_count, key):
        raise RedisError("store unavailable")


def _cache_with_redis(redis_client):
    cache = CacheService.__new__(CacheService)
    cache.redis_client = redis_client
    cache.memory_cache = {}
    cache._memory_lock = threading.Lock()
    return cache


def _redis_payload(value):
    return json.dumps(
        {
            "value": value,
            "expires": (datetime.now(timezone.utc) + timedelta(minutes=5)).isoformat(),
        }
    )


def test_cache_consume_prefers_redis_getdel():
    redis_client = _GetDelRedis(_redis_payload({"binding": "value"}))
    cache = _cache_with_redis(redis_client)

    assert cache.consume("security-key") == {"binding": "value"}
    assert cache.consume("security-key") is None
    assert redis_client.calls == 2


def test_cache_consume_uses_atomic_lua_fallback_without_getdel():
    redis_client = _LuaRedis(_redis_payload({"binding": "value"}))
    cache = _cache_with_redis(redis_client)

    assert cache.consume("security-key") == {"binding": "value"}
    assert cache.consume("security-key") is None
    assert redis_client.calls == 2


def test_cache_consume_does_not_fall_back_to_memory_in_production(monkeypatch):
    cache = _cache_with_redis(_FailingRedis())
    cache.memory_cache["security-key"] = {
        "value": "unsafe-worker-local-value",
        "expires": datetime.now(timezone.utc) + timedelta(minutes=5),
    }
    monkeypatch.setattr(settings, "ENVIRONMENT", "production")

    assert cache.consume("security-key") is None
    assert "security-key" in cache.memory_cache
