"""
Cache service for KPI dashboard and analytics
Supports both Redis and in-memory fallback
"""
import json
import logging
from typing import Any, Optional
from datetime import datetime, timedelta, timezone
import redis
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
        self._init_redis()

    def _init_redis(self):
        """Initialize Redis connection with fallback to memory cache"""
        try:
            if hasattr(settings, 'REDIS_URL') and settings.REDIS_URL:
                self.redis_client = redis.from_url(settings.REDIS_URL, decode_responses=True)
                # Test connection
                self.redis_client.ping()
                logger.info("Redis cache initialized successfully")
            else:
                logger.warning("Redis URL not configured, using in-memory cache")
        except Exception as e:
            logger.warning(f"Redis connection failed: {e}, falling back to in-memory cache")
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
                    expires = datetime.fromisoformat(cached_data['expires'])
                    if expires > datetime.now(timezone.utc):
                        logger.debug(f"Cache hit (Redis): {key}")
                        self._record_hit()
                        if MONITORING_AVAILABLE:
                            performance_monitor.collector.record_cache_request(is_hit=True)
                        return cached_data['value']
                    else:
                        # Expired, remove it
                        self.redis_client.delete(cache_key)
                        logger.debug(f"Cache expired (Redis): {key}")
                        self._record_miss()
                        if MONITORING_AVAILABLE:
                            performance_monitor.collector.record_cache_request(is_hit=False)
            except Exception as e:
                logger.warning(f"Redis get error: {e}")

        # Fall back to memory cache
        entry = self.memory_cache.get(key)
        if entry:
            if entry['expires'] > datetime.now(timezone.utc):
                logger.debug(f"Cache hit (Memory): {key}")
                self._record_hit()
                if MONITORING_AVAILABLE:
                    performance_monitor.collector.record_cache_request(is_hit=True)
                return entry['value']
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
        cache_data = {
            'value': value,
            'expires': expires.isoformat()
        }

        # Try Redis first
        if self.redis_client:
            try:
                self.redis_client.setex(cache_key, ttl_seconds, json.dumps(cache_data))
                logger.debug(f"Cache set (Redis): {key} (TTL: {ttl_seconds}s)")
                self._record_sets()
                return
            except Exception as e:
                logger.warning(f"Redis set error: {e}")

        # Fallback to memory cache
        self.memory_cache[key] = {
            'value': value,
            'expires': expires
        }
        logger.debug(f"Cache set (Memory): {key} (TTL: {ttl_seconds}s)")
        self._record_sets()

    def delete(self, key: str):
        """Delete value from cache"""
        cache_key = self._make_key(key)

        # Try Redis first
        if self.redis_client:
            try:
                self.redis_client.delete(cache_key)
                logger.debug(f"Cache deleted (Redis): {key}")
            except Exception as e:
                logger.warning(f"Redis delete error: {e}")

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
            except Exception as e:
                logger.warning(f"Redis clear error: {e}")

        # Clear memory cache
        self.memory_cache.clear()
        logger.info("Memory cache cleared")

    def get_stats(self) -> dict:
        """Get cache statistics"""
        stats = {
            'memory_entries': len(self.memory_cache),
            'redis_available': self.redis_client is not None,
            'cache_hits': getattr(self, '_cache_hits', 0),
            'cache_misses': getattr(self, '_cache_misses', 0),
            'cache_sets': getattr(self, '_cache_sets', 0)
        }

        if self.redis_client:
            try:
                redis_keys = self.redis_client.keys("kinjo:*")
                stats['redis_entries'] = len(redis_keys)
            except Exception as e:
                logger.warning(f"Redis stats error: {e}")
                stats['redis_entries'] = 0

        # Calculate hit rate
        total_requests = stats['cache_hits'] + stats['cache_misses']
        stats['hit_rate'] = (stats['cache_hits'] / total_requests * 100) if total_requests > 0 else 0

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
                        expires = datetime.fromisoformat(cached_data['expires'])
                        if expires > datetime.now(timezone.utc):
                            result[key] = cached_data['value']
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

            except Exception as e:
                logger.warning(f"Redis mget error: {e}")
                missing_keys = keys.copy()

        # Fallback to memory cache for missing keys
        for key in missing_keys:
            entry = self.memory_cache.get(key)
            if entry and entry['expires'] > datetime.now(timezone.utc):
                result[key] = entry['value']
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
                    cache_data = {
                        'value': value,
                        'expires': expires.isoformat()
                    }
                    redis_data[cache_key] = json.dumps(cache_data)

                self.redis_client.mset(redis_data)
                # Set expiration for each key
                for cache_key in redis_data.keys():
                    self.redis_client.expire(cache_key, ttl_seconds)

                self._record_sets(len(key_value_pairs))
                logger.debug(f"Cache mset (Redis): {len(key_value_pairs)} keys")
                return

            except Exception as e:
                logger.warning(f"Redis mset error: {e}")

        # Fallback to memory cache
        for key, value in key_value_pairs.items():
            self.memory_cache[key] = {
                'value': value,
                'expires': expires
            }

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
        if not hasattr(self, '_cache_hits'):
            self._cache_hits = 0
        self._cache_hits += 1

    def _record_miss(self):
        """Record a cache miss for statistics"""
        if not hasattr(self, '_cache_misses'):
            self._cache_misses = 0
        self._cache_misses += 1

    def _record_sets(self, count: int = 1):
        """Record cache sets for statistics"""
        if not hasattr(self, '_cache_sets'):
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
            except Exception as e:
                logger.warning(f"Redis TTL error: {e}")

        # Fallback to memory cache
        entry = self.memory_cache.get(key)
        if entry:
            remaining = int((entry['expires'] - datetime.now(timezone.utc)).total_seconds())
            return max(0, remaining)

        return None


# Global cache instance
cache_service = CacheService()

# Backward compatibility
dashboard_cache = cache_service
