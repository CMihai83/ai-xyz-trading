#!/usr/bin/env python3
"""
Grok Recommendation #4: Redis Connection Pooling
Replaces single connections with pooled connections and health checks.
"""
import redis
from redis import ConnectionPool, Redis
from redis.exceptions import ConnectionError, TimeoutError
import os
import time
import threading
import logging
from typing import Optional, Any, Dict
from functools import wraps
from contextlib import contextmanager

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


class RedisHealthChecker:
    """Background health checker for Redis connections"""

    def __init__(self, pool: 'RedisPool', check_interval: int = 30):
        self.pool = pool
        self.check_interval = check_interval
        self.running = False
        self._thread: Optional[threading.Thread] = None
        self.last_check_time = 0
        self.last_check_result = True
        self.consecutive_failures = 0

    def start(self):
        """Start background health checking"""
        if self.running:
            return

        self.running = True
        self._thread = threading.Thread(target=self._health_check_loop, daemon=True)
        self._thread.start()
        logger.info("Redis health checker started")

    def stop(self):
        """Stop health checking"""
        self.running = False
        if self._thread:
            self._thread.join(timeout=5)

    def _health_check_loop(self):
        """Background loop for health checks"""
        while self.running:
            try:
                result = self.pool.ping()
                self.last_check_result = result
                self.last_check_time = time.time()

                if result:
                    self.consecutive_failures = 0
                else:
                    self.consecutive_failures += 1
                    logger.warning(f"Redis health check failed ({self.consecutive_failures} consecutive)")

                    if self.consecutive_failures >= 3:
                        logger.error("Redis connection unhealthy, attempting reconnect")
                        self.pool.reconnect()

            except Exception as e:
                logger.error(f"Health check error: {e}")
                self.consecutive_failures += 1

            time.sleep(self.check_interval)

    def is_healthy(self) -> bool:
        """Check if Redis is currently healthy"""
        if time.time() - self.last_check_time > self.check_interval * 2:
            return False  # Stale check
        return self.last_check_result and self.consecutive_failures < 3


class RedisPool:
    """
    Redis connection pool with health checks and automatic reconnection.

    Features:
    - Connection pooling for better performance
    - Background health checking
    - Automatic reconnection on failure
    - Graceful fallback support
    """

    def __init__(
        self,
        host: str = None,
        port: int = None,
        db: int = 0,
        password: str = None,
        min_connections: int = 5,
        max_connections: int = 20,
        socket_timeout: float = 5.0,
        socket_connect_timeout: float = 5.0,
        retry_on_timeout: bool = True,
        health_check_interval: int = 30
    ):
        self.host = host or os.getenv('REDIS_HOST', 'localhost')
        self.port = port or int(os.getenv('REDIS_PORT', 6379))
        self.db = db
        self.password = password
        self.min_connections = min_connections
        self.max_connections = max_connections
        self.socket_timeout = socket_timeout
        self.socket_connect_timeout = socket_connect_timeout
        self.retry_on_timeout = retry_on_timeout

        self._pool: Optional[ConnectionPool] = None
        self._client: Optional[Redis] = None
        self._lock = threading.Lock()
        self._connected = False

        # Initialize pool
        self._create_pool()

        # Start health checker
        self._health_checker = RedisHealthChecker(self, health_check_interval)
        self._health_checker.start()

        # Stats
        self.stats = {
            'connections_created': 0,
            'reconnections': 0,
            'failed_operations': 0,
            'successful_operations': 0
        }

    def _create_pool(self):
        """Create the connection pool"""
        try:
            self._pool = ConnectionPool(
                host=self.host,
                port=self.port,
                db=self.db,
                password=self.password,
                max_connections=self.max_connections,
                socket_timeout=self.socket_timeout,
                socket_connect_timeout=self.socket_connect_timeout,
                retry_on_timeout=self.retry_on_timeout,
                decode_responses=True
            )

            self._client = Redis(connection_pool=self._pool)

            # Test connection
            if self._client.ping():
                self._connected = True
                self.stats['connections_created'] += 1
                logger.info(f"Redis pool created: {self.host}:{self.port} (max={self.max_connections})")
            else:
                raise ConnectionError("Ping failed")

        except Exception as e:
            logger.error(f"Failed to create Redis pool: {e}")
            self._connected = False

    def reconnect(self):
        """Attempt to reconnect to Redis"""
        with self._lock:
            logger.info("Attempting Redis reconnection...")

            # Close existing pool
            if self._pool:
                try:
                    self._pool.disconnect()
                except:
                    pass

            # Create new pool
            self._create_pool()
            self.stats['reconnections'] += 1

    def get_client(self) -> Redis:
        """Get a Redis client from the pool"""
        if not self._connected:
            self.reconnect()

        return self._client

    def ping(self) -> bool:
        """Ping Redis to check connectivity"""
        try:
            return self._client.ping() if self._client else False
        except:
            return False

    def is_connected(self) -> bool:
        """Check if Redis is connected and healthy"""
        return self._connected and self._health_checker.is_healthy()

    @contextmanager
    def connection(self):
        """Context manager for Redis operations with automatic error handling"""
        try:
            yield self.get_client()
            self.stats['successful_operations'] += 1
        except (ConnectionError, TimeoutError) as e:
            self.stats['failed_operations'] += 1
            logger.error(f"Redis operation failed: {e}")
            self.reconnect()
            raise

    def execute_with_retry(self, operation: str, *args, max_retries: int = 3, **kwargs) -> Any:
        """
        Execute a Redis operation with automatic retry.

        Args:
            operation: Name of Redis operation (e.g., 'get', 'set', 'hget')
            *args: Operation arguments
            max_retries: Maximum retry attempts
            **kwargs: Operation keyword arguments

        Returns:
            Operation result
        """
        last_error = None

        for attempt in range(max_retries):
            try:
                client = self.get_client()
                method = getattr(client, operation)
                result = method(*args, **kwargs)
                self.stats['successful_operations'] += 1
                return result

            except (ConnectionError, TimeoutError) as e:
                last_error = e
                self.stats['failed_operations'] += 1
                logger.warning(f"Redis {operation} failed (attempt {attempt + 1}/{max_retries}): {e}")

                if attempt < max_retries - 1:
                    time.sleep(0.5 * (attempt + 1))  # Exponential backoff
                    self.reconnect()

        raise last_error

    # Convenience methods with retry
    def get(self, key: str) -> Optional[str]:
        """Get a value with retry"""
        return self.execute_with_retry('get', key)

    def set(self, key: str, value: str, ex: int = None) -> bool:
        """Set a value with retry"""
        return self.execute_with_retry('set', key, value, ex=ex)

    def hget(self, name: str, key: str) -> Optional[str]:
        """Hash get with retry"""
        return self.execute_with_retry('hget', name, key)

    def hset(self, name: str, key: str = None, value: str = None, mapping: Dict = None) -> int:
        """Hash set with retry"""
        if mapping:
            return self.execute_with_retry('hset', name, mapping=mapping)
        return self.execute_with_retry('hset', name, key, value)

    def hgetall(self, name: str) -> Dict:
        """Hash get all with retry"""
        return self.execute_with_retry('hgetall', name)

    def delete(self, *keys) -> int:
        """Delete keys with retry"""
        return self.execute_with_retry('delete', *keys)

    def exists(self, *keys) -> int:
        """Check key existence with retry"""
        return self.execute_with_retry('exists', *keys)

    def expire(self, name: str, time: int) -> bool:
        """Set key expiration with retry"""
        return self.execute_with_retry('expire', name, time)

    def keys(self, pattern: str = '*') -> list:
        """Get keys matching pattern with retry"""
        return self.execute_with_retry('keys', pattern)

    def get_stats(self) -> Dict:
        """Get connection pool statistics"""
        pool_info = {}
        if self._pool:
            pool_info = {
                'max_connections': self._pool.max_connections,
                'current_connections': len(self._pool._in_use_connections) if hasattr(self._pool, '_in_use_connections') else 'N/A'
            }

        return {
            'connected': self._connected,
            'healthy': self._health_checker.is_healthy(),
            'host': self.host,
            'port': self.port,
            **pool_info,
            **self.stats,
            'health_check': {
                'last_check': self._health_checker.last_check_time,
                'last_result': self._health_checker.last_check_result,
                'consecutive_failures': self._health_checker.consecutive_failures
            }
        }

    def close(self):
        """Close the pool and stop health checker"""
        self._health_checker.stop()
        if self._pool:
            self._pool.disconnect()
        self._connected = False
        logger.info("Redis pool closed")


# Singleton instance
_pool_instance: Optional[RedisPool] = None

def get_redis_pool() -> RedisPool:
    """Get singleton Redis pool instance"""
    global _pool_instance
    if _pool_instance is None:
        _pool_instance = RedisPool()
    return _pool_instance


def with_redis_fallback(fallback_fn):
    """
    Decorator for graceful fallback when Redis is unavailable.

    Usage:
        @with_redis_fallback(lambda: load_from_file())
        def get_data():
            return redis.get('data')
    """
    def decorator(fn):
        @wraps(fn)
        def wrapper(*args, **kwargs):
            pool = get_redis_pool()
            if pool.is_connected():
                try:
                    return fn(*args, **kwargs)
                except Exception as e:
                    logger.warning(f"Redis operation failed, using fallback: {e}")
                    return fallback_fn()
            else:
                logger.warning("Redis not connected, using fallback")
                return fallback_fn()
        return wrapper
    return decorator


if __name__ == "__main__":
    # Demo
    print("Testing Redis Connection Pool...")
    print("-" * 50)

    pool = RedisPool(
        host='localhost',
        port=6379,
        min_connections=2,
        max_connections=10,
        health_check_interval=10
    )

    if pool.is_connected():
        print("✅ Connected to Redis")

        # Test operations
        pool.set('test_key', 'test_value', ex=60)
        value = pool.get('test_key')
        print(f"✅ Set/Get: {value}")

        # Test hash
        pool.hset('test_hash', mapping={'field1': 'value1', 'field2': 'value2'})
        hash_data = pool.hgetall('test_hash')
        print(f"✅ Hash: {hash_data}")

        # Stats
        print(f"\n📊 Pool Stats: {pool.get_stats()}")

        # Cleanup
        pool.delete('test_key', 'test_hash')

    else:
        print("❌ Could not connect to Redis")

    # Test fallback decorator
    @with_redis_fallback(lambda: "fallback_value")
    def get_cached_data():
        return pool.get('nonexistent_key') or "default_value"

    result = get_cached_data()
    print(f"\n📦 Fallback test result: {result}")

    pool.close()
    print("\n✅ Pool closed")
