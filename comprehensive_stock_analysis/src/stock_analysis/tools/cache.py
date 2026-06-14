"""Caching for tool results.

Three tiers, tried in order of locality:
  1. Redis (shared, cross-process) — used when reachable.
  2. In-process memory — fast, but lost when the process exits.
  3. Filesystem (cross-process) — survives between CLI invocations, so a
     second analysis of the same symbol within the TTL reuses pulled data
     even when Redis is not running.

When Redis is up it is authoritative (memory/disk are skipped). When Redis is
down, reads fall through memory→disk and writes populate both.
"""

import hashlib
import json
import logging
import os
import threading
import time
from functools import wraps
from typing import Any, Callable, Dict, Optional, Tuple

_logger = logging.getLogger(__name__)
_redis_client: Any = None
_redis_unavailable: bool = False

# In-process fallback cache used when Redis is unreachable. Besides saving API
# calls, it makes repeated identical tool calls return identical results, which
# lets CrewAI's repeated-call guard terminate agent tool loops.
_memory_cache: Dict[str, Tuple[float, str]] = {}
_memory_lock = threading.Lock()
_MEMORY_CACHE_MAX = 256

# Filesystem tier — persists across processes so per-invocation CLI runs reuse
# data. Resolved lazily under the data dir; "" means unavailable.
_disk_dir_cached: Optional[str] = None


def _memory_get(key: str) -> Optional[str]:
    with _memory_lock:
        entry = _memory_cache.get(key)
        if entry is None:
            return None
        expires, payload = entry
        if time.time() > expires:
            del _memory_cache[key]
            return None
        return payload


def _memory_set(key: str, payload: str, ttl: int) -> None:
    with _memory_lock:
        if len(_memory_cache) >= _MEMORY_CACHE_MAX:
            # Drop the soonest-to-expire entries
            for old_key, _ in sorted(_memory_cache.items(), key=lambda kv: kv[1][0])[:32]:
                del _memory_cache[old_key]
        _memory_cache[key] = (time.time() + ttl, payload)


# Housekeeping bounds for the on-disk tier — entries delete themselves on
# access when expired, but symbols analysed once and never re-requested would
# otherwise linger forever. A one-time sweep on first use keeps the dir bounded.
_MAX_DISK_CACHE_FILES = 512
_DISK_SWEEP_MAX_AGE = 7 * 86400  # hard age cap regardless of per-entry TTL


def _sweep_disk_cache(d: str) -> None:
    """Delete cache files older than the age cap and trim to a file count cap."""
    try:
        import glob
        files = glob.glob(os.path.join(d, "*.json"))
        now = time.time()
        survivors = []
        for f in files:
            try:
                age = now - os.path.getmtime(f)
                if age > _DISK_SWEEP_MAX_AGE:
                    os.remove(f)
                else:
                    survivors.append((os.path.getmtime(f), f))
            except OSError:
                pass
        # Trim oldest beyond the count cap
        if len(survivors) > _MAX_DISK_CACHE_FILES:
            survivors.sort()  # oldest first
            for _, f in survivors[: len(survivors) - _MAX_DISK_CACHE_FILES]:
                try:
                    os.remove(f)
                except OSError:
                    pass
    except Exception as exc:  # housekeeping must never break the run
        _logger.debug("Disk cache sweep skipped: %s", exc)


def _disk_dir() -> Optional[str]:
    """Cache directory under the data dir, created and swept on first use."""
    global _disk_dir_cached
    if _disk_dir_cached is None:
        try:
            from ..config.settings import settings
            d = os.path.join(settings.data_output_dir, ".tool_cache")
            os.makedirs(d, exist_ok=True)
            _sweep_disk_cache(d)
            _disk_dir_cached = d
        except Exception as exc:
            _logger.debug("Disk cache unavailable: %s", exc)
            _disk_dir_cached = ""
    return _disk_dir_cached or None


def _disk_path(cache_key: str) -> Optional[str]:
    d = _disk_dir()
    return os.path.join(d, cache_key.replace(":", "_") + ".json") if d else None


def _disk_get(cache_key: str) -> Optional[str]:
    """Return the cached payload string, or None on miss/expiry/error."""
    path = _disk_path(cache_key)
    if not path:
        return None
    try:
        with open(path, "r", encoding="utf-8") as f:
            entry = json.load(f)
        if time.time() > entry["expires"]:
            try:
                os.remove(path)
            except OSError:
                pass
            return None
        return entry["payload"]
    except (OSError, ValueError, KeyError):
        return None


def _disk_set(cache_key: str, payload: str, ttl: int) -> None:
    path = _disk_path(cache_key)
    if not path:
        return
    try:
        tmp = path + ".tmp"
        with open(tmp, "w", encoding="utf-8") as f:
            json.dump({"expires": time.time() + ttl, "payload": payload}, f)
        os.replace(tmp, path)  # atomic — never serve a half-written file
    except OSError as exc:
        _logger.debug("Disk cache write failed: %s", exc)


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
            _logger.debug("Redis unavailable, caching disabled: %s", exc)
            _redis_unavailable = True
    return _redis_client


def cached_tool(ttl: Optional[int] = None) -> Callable:
    """Decorator for BaseTool._run methods that caches results in Redis.

    Silently degrades to no-cache when Redis is unreachable.
    """
    def decorator(func: Callable) -> Callable:
        @wraps(func)
        def wrapper(self, *args, **kwargs):
            key_raw = json.dumps(
                {"tool": self.name, "args": args, "kwargs": kwargs},
                sort_keys=True,
                default=str,
            )
            cache_key = "sa:" + hashlib.sha256(key_raw.encode()).hexdigest()
            client = _get_redis()

            if client is not None:
                try:
                    hit = client.get(cache_key)
                    if hit:
                        _logger.debug("Cache hit (redis): %s", cache_key)
                        return json.loads(hit)
                except Exception:
                    pass
            else:
                hit = _memory_get(cache_key)
                if hit is not None:
                    _logger.debug("Cache hit (memory): %s", cache_key)
                    return json.loads(hit)
                hit = _disk_get(cache_key)
                if hit is not None:
                    _logger.debug("Cache hit (disk): %s", cache_key)
                    return json.loads(hit)

            result = func(self, *args, **kwargs)

            # Never cache failures — a transient API error must not be served
            # back as a "result" for the rest of the TTL window.
            is_error = isinstance(result, dict) and "error" in result
            if not is_error:
                from ..config.settings import settings
                effective_ttl = ttl if ttl is not None else settings.cache_ttl
                payload = json.dumps(result, default=str)
                if client is not None:
                    try:
                        client.setex(cache_key, effective_ttl, payload)
                    except Exception:
                        pass
                else:
                    _memory_set(cache_key, payload, effective_ttl)
                    _disk_set(cache_key, payload, effective_ttl)

            return result

        return wrapper
    return decorator


def get_cached(namespace: str, key: str) -> Optional[Any]:
    """Cross-process cache read for non-BaseTool callers (Redis→memory→disk)."""
    cache_key = "sa:" + namespace + ":" + hashlib.sha256(key.encode()).hexdigest()
    client = _get_redis()
    if client is not None:
        try:
            hit = client.get(cache_key)
            return json.loads(hit) if hit else None
        except Exception:
            return None
    raw = _memory_get(cache_key)
    if raw is None:
        raw = _disk_get(cache_key)
    return json.loads(raw) if raw is not None else None


def set_cached(namespace: str, key: str, value: Any, ttl: int) -> None:
    """Cross-process cache write for non-BaseTool callers. Skips error dicts."""
    if isinstance(value, dict) and "error" in value:
        return
    cache_key = "sa:" + namespace + ":" + hashlib.sha256(key.encode()).hexdigest()
    payload = json.dumps(value, default=str)
    client = _get_redis()
    if client is not None:
        try:
            client.setex(cache_key, ttl, payload)
        except Exception:
            pass
    else:
        _memory_set(cache_key, payload, ttl)
        _disk_set(cache_key, payload, ttl)
