"""Shared HTTP session with connection pooling, retries, and a default timeout.

All tool HTTP traffic should go through :data:`SESSION` (or the :func:`get` /
:func:`post` helpers) so that:

  * TCP connections are pooled and reused across the many small calls a run
    makes — lower latency than a fresh connection per request.
  * Transient failures (429 + 5xx) are retried with exponential backoff, so a
    momentary blip from a free endpoint becomes a success instead of a "Data
    Gap" in the report.
  * Every request has a timeout even if a caller forgets to pass one — a hung
    endpoint can never stall a stage up to its execution-time limit.
"""

import requests
from requests.adapters import HTTPAdapter

try:  # urllib3 v1/v2 keep Retry in different places
    from urllib3.util.retry import Retry
except Exception:  # pragma: no cover - extremely old urllib3
    from requests.packages.urllib3.util.retry import Retry  # type: ignore

# Default per-request timeout (seconds) when a caller does not pass one.
DEFAULT_TIMEOUT = 10

_RETRY = Retry(
    total=2,                      # 2 retries (3 attempts) — enough for blips, not slow
    backoff_factor=0.5,           # 0s, 0.5s, 1.0s between attempts
    status_forcelist=(429, 500, 502, 503, 504),
    allowed_methods=frozenset({"GET", "POST"}),
    raise_on_status=False,
)


def _build_session() -> requests.Session:
    s = requests.Session()
    adapter = HTTPAdapter(max_retries=_RETRY, pool_connections=16, pool_maxsize=16)
    s.mount("http://", adapter)
    s.mount("https://", adapter)
    return s


# Module-level singleton — safe to share across threads (requests.Session is
# thread-safe for issuing requests once adapters are mounted).
SESSION = _build_session()


def get(url: str, **kwargs) -> requests.Response:
    """SESSION.get with a default timeout applied when none is given."""
    kwargs.setdefault("timeout", DEFAULT_TIMEOUT)
    return SESSION.get(url, **kwargs)


def post(url: str, **kwargs) -> requests.Response:
    """SESSION.post with a default timeout applied when none is given."""
    kwargs.setdefault("timeout", DEFAULT_TIMEOUT)
    return SESSION.post(url, **kwargs)
