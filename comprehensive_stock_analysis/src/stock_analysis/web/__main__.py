"""Launch the local web UI: `python -m stock_analysis.web`.

Single uvicorn worker (workers=1) — analyses are serialized by the JobManager
and rely on process-global token/budget state, so multiple workers would break
accounting. Defaults to localhost-only.
"""

import argparse
import logging
from pathlib import Path

from .. import diagnostics
from ..config.settings import settings
from ..main import _drop_noise, _quiet_noisy_loggers, _rotate_if_large

_logger = logging.getLogger(__name__)


def _setup_logging() -> None:
    log_path = Path(settings.crew_log_file)
    log_path.parent.mkdir(parents=True, exist_ok=True)
    _rotate_if_large(log_path)
    handler = logging.FileHandler(log_path, encoding="utf-8")
    handler.setFormatter(
        logging.Formatter(
            # thread name included: analyses run in a JobManager worker, and
            # knowing which thread emitted a line is what separates "the server
            # died" from "the analysis died".
            "%(asctime)s %(levelname)s [%(threadName)s] %(name)s %(message)s"
        )
    )
    handler.addFilter(_drop_noise)
    root = logging.getLogger()
    root.addHandler(handler)

    # The server is long-lived and unattended, so the persistent log must hold
    # enough to reconstruct a crash after the fact. LOG_LEVEL is typically
    # ERROR, which drops every lifecycle breadcrumb (startup, shutdown, signal,
    # job transitions) and left a previous mid-analysis death undiagnosable.
    # Floor the level at INFO here; _quiet_noisy_loggers() keeps third-party
    # chatter out, so this buys detail without flooding the file.
    configured = getattr(logging, settings.log_level, logging.INFO)
    root.setLevel(min(configured, logging.INFO))
    _quiet_noisy_loggers()

    diagnostics.install(log_path, role="web")
    if configured > logging.INFO:
        _logger.info(
            "log level floored to INFO for the persistent log (LOG_LEVEL=%s)",
            settings.log_level,
        )


def main() -> None:
    parser = argparse.ArgumentParser(description="Stock Analysis web UI")
    parser.add_argument("--host", default=settings.web_host)
    parser.add_argument("--port", type=int, default=settings.web_port)
    args = parser.parse_args()

    _setup_logging()

    # Warn (don't exit) if no LLM key is configured — the UI still serves the
    # gallery and past reports; only new runs would fail, and they surface it.
    try:
        from ..agents.base_agent import preflight_llm_credentials

        for problem in preflight_llm_credentials():
            _logger.warning("[preflight] %s", problem)
            print(f"  Warning: {problem}")
    except Exception as exc:  # pragma: no cover
        _logger.debug("preflight skipped: %s", exc)

    import uvicorn

    print(f"\nStock Analysis UI → http://{args.host}:{args.port}\n")
    # uvicorn's log level is floored to "info" for the same reason the root
    # logger is: at "error" uvicorn emits no "Shutting down"/"Application
    # shutdown complete" lines, which are the clearest evidence of whether the
    # process ended gracefully or was killed mid-request.
    uvicorn_level = settings.log_level.lower()
    if uvicorn_level in ("error", "critical", "warning"):
        uvicorn_level = "info"
    try:
        uvicorn.run(
            "stock_analysis.web.app:app",
            host=args.host,
            port=args.port,
            workers=1,
            log_level=uvicorn_level,
        )
    except BaseException as exc:  # noqa: BLE001 - last chance to record the cause
        # uvicorn.run() normally swallows the signal path, so anything escaping
        # here (including SystemExit) is worth a record before the process ends.
        _logger.critical(
            "uvicorn.run exited: %s: %s", type(exc).__name__, exc, exc_info=True
        )
        raise
    finally:
        _logger.info("uvicorn.run returned — server loop has stopped")


if __name__ == "__main__":
    main()
