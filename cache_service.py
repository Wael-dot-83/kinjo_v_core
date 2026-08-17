"""
Cache service for KPI dashboard and analytics
Supports both Redis and in-memory fallback
"""

import json
import logging
import threading
from typing import Any, Optional
from datetime import datetime, timedelta, timezone
import redis
from redis.exceptions import RedisError
from config import settings

logger = logging.getLogger(__name__)

# Import monitoring for cache metrics
try:
    from monitoring_service import performance_monitor

    MONITORING_AVAILABLE = True
except ImportError:
    MONITORING_AVAILABLE = False
    logger.warning("Monitoring service not available, cache metrics will not be recorded")


class CacheService:
    """Unified cache service with Redis support and in-memory fallback"""

    def __init__(self):
        self.redis_client = None
        self.memory_cache = {}
        self._memory_lock = threading.Lock()
        self._init_redis()

    def _init_redis(self):
        """Initialize Redis connection with fallback to memory cache"""
        try:
            if hasattr(settings, "REDIS_URL") and settings.REDIS_URL:
                self.redis_client = redis.from_url(settings.REDIS_URL, decode_responses=True)
                # Test connection
                self.redis_client.ping()
                logger.info("Redis cache initialized successfully")
            else:
                logger.warning("Redis URL not configured, using in-memory cache")
        except (RedisError, OSError, TypeError, ValueError) as e:
            logger.warning("Redis connection failed: %s, falling back to in-memory cache", str(e))
            self.redis_client = None

    def _make_key(self, key: str) -> str:
        """Create a namespaced cache key"""
        return f"kinjo:{key}"

    def get(self, key: str) -> Optional[Any]:
        """Get value from cache with Redis priority"""
        cache_key = self._make_key(key)

        # Try Redis first
        if self.redis_client:
            try:
                data = self.redis_client.get(cache_key)
                if data:
                    cached_data = json.loads(data)
                    expires = datetime.fromisoformat(cached_data["expires"])
                    if expires > datetime.now(timezone.utc):
                        logger.debug(f"Cache hit (Redis): {key}")
                        self._record_hit()
                        if MONITORING_AVAILABLE:
                            performance_monitor.collector.record_cache_request(is_hit=True)
                        return cached_data["value"]
                    else:
                        # Expired, remove it
                        self.redis_client.delete(cache_key)
                        logger.debug(f"Cache expired (Redis): {key}")
                        self._record_miss()
                        if MONITORING_AVAILABLE:
                            performance_monitor.collector.record_cache_request(is_hit=False)
            except RedisError as e:
                logger.warning("Redis get error for key %s: %s", key, str(e))
            except (json.JSONDecodeError, KeyError, TypeError, ValueError) as e:
                logger.warning("Invalid cached payload for key %s: %s", key, str(e))
                try:
                    self.redis_client.delete(cache_key)
                except RedisError as delete_error:
                    logger.warning("Failed to delete invalid Redis cache entry for key %s: %s", key, str(delete_error))

        # Fall back to memory cache
        entry = self.memory_cache.get(key)
        if entry:
            if entry["expires"] > datetime.now(timezone.utc):
                logger.debug(f"Cache hit (Memory): {key}")
                self._record_hit()
                if MONITORING_AVAILABLE:
                    performance_monitor.collector.record_cache_request(is_hit=True)
                return entry["value"]
            else:
                del self.memory_cache[key]
                logger.debug(f"Cache expired (Memory): {key}")
                self._record_miss()
                if MONITORING_AVAILABLE:
                    performance_monitor.collector.record_cache_request(is_hit=False)

        logger.debug(f"Cache miss: {key}")
        self._record_miss()
        if MONITORING_AVAILABLE:
            performance_monitor.collector.record_cache_request(is_hit=False)
        return None

    def set(self, key: str, value: Any, ttl_seconds: int = 300):
        """Set value in cache with Redis priority"""
        cache_key = self._make_key(key)
        expires = datetime.now(timezone.utc) + timedelta(seconds=ttl_seconds)
        cache_data = {"value": value, "expires": expires.isoformat()}

        # Try Redis first
        if self.redis_client:
            try:
                self.redis_client.set(
                    cache_key,
                    json.dumps(cache_data),
                    ex=ttl_seconds,
                )
                logger.debug(f"Cache set (Redis): {key} (TTL: {ttl_seconds}s)")
                self._record_sets()
                return
            except RedisError as e:
                logger.warning("Redis set error for key %s: %s", key, str(e))
            except (TypeError, ValueError) as e:
                logger.warning("Cache value for key %s could not be serialized for Redis: %s", key, str(e))

        # Fallback to memory cache
        self.memory_cache[key] = {"value": value, "expires": expires}
        logger.debug(f"Cache set (Memory): {key} (TTL: {ttl_seconds}s)")
        self._record_sets()

    def add_if_absent(self, key: str, value: Any, ttl_seconds: int = 300) -> Optional[bool]:
        """Atomically reserve a key; return None when a required shared store fails."""
        cache_key = self._make_key(key)
        expires = datetime.now(timezone.utc) + timedelta(seconds=ttl_seconds)
        cache_data = {"value": value, "expires": expires.isoformat()}

        if self.redis_client:
            try:
                created = self.redis_client.set(
                    cache_key,
                    json.dumps(cache_data),
                    ex=ttl_seconds,
                    nx=True,
                )
                if created:
                    self._record_sets()
                return bool(created)
            except (RedisError, TypeError, ValueError) as exc:
                logger.error("Redis atomic reservation failed for key %s: %s", key, exc)
                if settings.ENVIRONMENT.lower() == "production":
                    return None

        if settings.ENVIRONMENT.lower() == "production":
            logger.error("Shared Redis is unavailable for security key %s", key)
            return None

        with self._memory_lock:
            existing = self.memory_cache.get(key)
            if existing and existing["expires"] > datetime.now(timezone.utc):
                return False
            self.memory_cache[key] = {"value": value, "expires": expires}
            self._record_sets()
            return True

    def consume(self, key: str) -> Optional[Any]:
        """Atomically read and delete a cache value.

        Redis GETDEL provides the shared-store guarantee. The Lua fallback keeps
        compatibility with older Redis servers while remaining atomic. Production
        never falls back to worker-local memory for security-sensitive consumes.
        """
        cache_key = self._make_key(key)

        if self.redis_client:
            try:
                getdel = getattr(self.redis_client, "getdel", None)
                if callable(getdel):
                    try:
                        data = getdel(cache_key)
                    except RedisError:
                        data = self.redis_client.eval(
                            "local value = redis.call('GET', KEYS[1]); "
                            "if value then redis.call('DEL', KEYS[1]); end; "
                            "return value",
                            1,
                            cache_key,
                        )
                else:
                    data = self.redis_client.eval(
                        "local value = redis.call('GET', KEYS[1]); "
                        "if value then redis.call('DEL', KEYS[1]); end; "
                        "return value",
                        1,
                        cache_key,
                    )

                if not data:
                    return None

                cached_data = json.loads(data)
                expires = datetime.fromisoformat(cached_data["expires"])
                if expires <= datetime.now(timezone.utc):
                    return None
                return cached_data["value"]
            except (RedisError, json.JSONDecodeError, KeyError, TypeError, ValueError) as exc:
                logger.error("Redis atomic consume failed for key %s: %s", key, exc)
                if settings.ENVIRONMENT.lower() == "production":
                    return None

        if settings.ENVIRONMENT.lower() == "production":
            logger.error("Shared Redis is unavailable for security consume key %s", key)
            return None

        with self._memory_lock:
            entry = self.memory_cache.pop(key, None)
            if not entry or entry["expires"] <= datetime.now(timezone.utc):
                return None
            return entry["value"]

    def delete(self, key: str):
        """Delete value from cache"""
        cache_key = self._make_key(key)

        # Try Redis first
        if self.redis_client:
            try:
                self.redis_client.delete(cache_key)
                logger.debug(f"Cache deleted (Redis): {key}")
            except RedisError as e:
                logger.warning("Redis delete error for key %s: %s", key, str(e))

        # Also remove from memory cache
        if key in self.memory_cache:
            del self.memory_cache[key]
            logger.debug(f"Cache deleted (Memory): {key}")

    def clear(self):
        """Clear all cache entries"""
        # Clear Redis
        if self.redis_client:
            try:
                # Delete all keys with our namespace
                keys = self.redis_client.keys("kinjo:*")
                if keys:
                    self.redis_client.delete(*keys)
                logger.info("Redis cache cleared")
            except RedisError as e:
                logger.warning("Redis clear error: %s", str(e))

        # Clear memory cache
        self.memory_cache.clear()
        logger.info("Memory cache cleared")

    def clear_prefix(self, prefix: str) -> int:
        """Clear all cache entries whose key starts with prefix. Returns count deleted."""
        deleted = 0
        if self.redis_client:
            try:
                pattern = f"kinjo:{prefix}*"
                keys = self.redis_client.keys(pattern)
                if keys:
                    self.redis_client.delete(*keys)
                    deleted += len(keys)
                logger.info("Redis cache cleared for prefix '%s' (%d keys)", prefix, len(keys) if keys else 0)
            except RedisError as e:
                logger.warning("Redis clear_prefix error for '%s': %s", prefix, str(e))

        matching = [k for k in list(self.memory_cache.keys()) if k.startswith(prefix)]
        for key in matching:
            del self.memory_cache[key]
        deleted += len(matching)
        logger.info("Memory cache cleared for prefix '%s' (%d keys)", prefix, len(matching))
        return deleted

    def get_stats(self) -> dict:
        """Get cache statistics"""
        stats = {
            "memory_entries": len(self.memory_cache),
            "redis_available": self.redis_client is not None,
            "cache_hits": getattr(self, "_cache_hits", 0),
            "cache_misses": getattr(self, "_cache_misses", 0),
            "cache_sets": getattr(self, "_cache_sets", 0),
        }

        if self.redis_client:
            try:
                redis_keys = self.redis_client.keys("kinjo:*")
                stats["redis_entries"] = len(redis_keys)
            except RedisError as e:
                logger.warning("Redis stats error: %s", str(e))
                stats["redis_entries"] = 0

        # Calculate hit rate
        total_requests = stats["cache_hits"] + stats["cache_misses"]
        stats["hit_rate"] = (stats["cache_hits"] / total_requests * 100) if total_requests > 0 else 0

        return stats

    def mget(self, keys: list) -> dict:
        """Get multiple values from cache efficiently"""
        if not keys:
            return {}

        result = {}
        missing_keys = []

        # Try Redis first for batch operation
        if self.redis_client:
            try:
                cache_keys = [self._make_key(key) for key in keys]
                redis_data = self.redis_client.mget(cache_keys)

                for key, data in zip(keys, redis_data):
                    if data:
                        cached_data = json.loads(data)
                        expires = datetime.fromisoformat(cached_data["expires"])
                        if expires > datetime.now(timezone.utc):
                            result[key] = cached_data["value"]
                            self._record_hit()
                        else:
                            # Expired, will be fetched fresh
                            self.redis_client.delete(self._make_key(key))
                            missing_keys.append(key)
                            self._record_miss()
                    else:
                        missing_keys.append(key)
                        self._record_miss()

                # Return early if all found in Redis
                if not missing_keys:
                    return result

            except RedisError as e:
                logger.warning("Redis mget error for %d keys: %s", len(keys), str(e))
                missing_keys = keys.copy()
            except (json.JSONDecodeError, KeyError, TypeError, ValueError) as e:
                logger.warning("Invalid cached payload during mget: %s", str(e))
                missing_keys = keys.copy()

        # Fallback to memory cache for missing keys
        for key in missing_keys:
            entry = self.memory_cache.get(key)
            if entry and entry["expires"] > datetime.now(timezone.utc):
                result[key] = entry["value"]
                self._record_hit()
            else:
                self._record_miss()

        return result

    def mset(self, key_value_pairs: dict, ttl_seconds: int = 300):
        """Set multiple values in cache efficiently"""
        if not key_value_pairs:
            return

        expires = datetime.now(timezone.utc) + timedelta(seconds=ttl_seconds)

        # Try Redis first for batch operation
        if self.redis_client:
            try:
                redis_data = {}
                for key, value in key_value_pairs.items():
                    cache_key = self._make_key(key)
                    cache_data = {"value": value, "expires": expires.isoformat()}
                    redis_data[cache_key] = json.dumps(cache_data)

                self.redis_client.mset(redis_data)
                # Set expiration for each key
                for cache_key in redis_data.keys():
                    self.redis_client.expire(cache_key, ttl_seconds)

                self._record_sets(len(key_value_pairs))
                logger.debug(f"Cache mset (Redis): {len(key_value_pairs)} keys")
                return

            except RedisError as e:
                logger.warning("Redis mset error for %d keys: %s", len(key_value_pairs), str(e))
            except (TypeError, ValueError) as e:
                logger.warning("One or more cache values could not be serialized for Redis mset: %s", str(e))

        # Fallback to memory cache
        for key, value in key_value_pairs.items():
            self.memory_cache[key] = {"value": value, "expires": expires}

        self._record_sets(len(key_value_pairs))
        logger.debug(f"Cache mset (Memory): {len(key_value_pairs)} keys")

    def warm_cache(self, key_value_pairs: dict, ttl_seconds: int = 300):
        """Warm the cache with initial data (useful for startup)"""
        self.mset(key_value_pairs, ttl_seconds)
        logger.info(f"Cache warmed with {len(key_value_pairs)} entries")

    def get_or_set(self, key: str, getter_func, ttl_seconds: int = 300):
        """Get from cache or set using a getter function (cache-aside pattern)"""
        value = self.get(key)
        if value is not None:
            return value

        # Cache miss, call getter function
        value = getter_func()
        if value is not None:
            self.set(key, value, ttl_seconds)
        return value

    def _record_hit(self):
        """Record a cache hit for statistics"""
        if not hasattr(self, "_cache_hits"):
            self._cache_hits = 0
        self._cache_hits += 1

    def _record_miss(self):
        """Record a cache miss for statistics"""
        if not hasattr(self, "_cache_misses"):
            self._cache_misses = 0
        self._cache_misses += 1

    def _record_sets(self, count: int = 1):
        """Record cache sets for statistics"""
        if not hasattr(self, "_cache_sets"):
            self._cache_sets = 0
        self._cache_sets += count

    def get_ttl(self, key: str) -> Optional[int]:
        """Get remaining TTL for a key in seconds"""
        cache_key = self._make_key(key)

        # Try Redis first
        if self.redis_client:
            try:
                ttl = self.redis_client.ttl(cache_key)
                if ttl > 0:
                    return ttl
            except RedisError as e:
                logger.warning("Redis TTL error for key %s: %s", key, str(e))

        # Fallback to memory cache
        entry = self.memory_cache.get(key)
        if entry:
            remaining = int((entry["expires"] - datetime.now(timezone.utc)).total_seconds())
            return max(0, remaining)

        return None


# Global cache instance
cache_service = CacheService()

# Backward compatibility
dashboard_cache = cache_service
