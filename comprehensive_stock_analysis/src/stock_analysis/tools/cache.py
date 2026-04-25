"""Redis-backed caching for tool results."""

import hashlib
import json
import logging
from functools import wraps
from typing import Any, Callable, Optional

_logger = logging.getLogger(__name__)
_redis_client: Any = None
_redis_unavailable: bool = False


def _get_redis():
    """Return a connected Redis client, or None when Redis is unreachable."""
    global _redis_client, _redis_unavailable
    if _redis_unavailable:
        return None
    if _redis_client is None:
        try:
            import redis
            from ..config.settings import settings
            client = redis.from_url(settings.redis_url, socket_connect_timeout=2)
            client.ping()
            _redis_client = client
            _logger.debug("Redis cache connected: %s", settings.redis_url)
        except Exception as exc:
            _logger.warning("Redis unavailable, caching disabled: %s", exc)
            _redis_unavailable = True
    return _redis_client


def cached_tool(ttl: Optional[int] = None) -> Callable:
    """Decorator for BaseTool._run methods that caches results in Redis.

    Silently degrades to no-cache when Redis is unreachable.
    """
    def decorator(func: Callable) -> Callable:
        @wraps(func)
        def wrapper(self, *args, **kwargs):
            client = _get_redis()
            if client is None:
                return func(self, *args, **kwargs)

            key_raw = json.dumps(
                {"tool": self.name, "args": args, "kwargs": kwargs},
                sort_keys=True,
                default=str,
            )
            cache_key = "sa:" + hashlib.sha256(key_raw.encode()).hexdigest()

            try:
                hit = client.get(cache_key)
                if hit:
                    _logger.debug("Cache hit: %s", cache_key)
                    return json.loads(hit)
            except Exception:
                pass

            result = func(self, *args, **kwargs)

            try:
                from ..config.settings import settings
                client.setex(
                    cache_key,
                    ttl if ttl is not None else settings.cache_ttl,
                    json.dumps(result, default=str),
                )
            except Exception:
                pass

            return result

        return wrapper
    return decorator
