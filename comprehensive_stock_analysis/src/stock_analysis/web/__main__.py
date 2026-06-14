"""Launch the local web UI: `python -m stock_analysis.web`.

Single uvicorn worker (workers=1) — analyses are serialized by the JobManager
and rely on process-global token/budget state, so multiple workers would break
accounting. Defaults to localhost-only.
"""

import argparse
import logging
from pathlib import Path

from ..config.settings import settings
from ..main import _drop_noise, _quiet_noisy_loggers, _rotate_if_large

_logger = logging.getLogger(__name__)


def _setup_logging() -> None:
    log_path = Path(settings.crew_log_file)
    log_path.parent.mkdir(parents=True, exist_ok=True)
    _rotate_if_large(log_path)
    handler = logging.FileHandler(log_path, encoding="utf-8")
    handler.setFormatter(logging.Formatter("%(asctime)s %(levelname)s %(name)s %(message)s"))
    handler.addFilter(_drop_noise)
    root = logging.getLogger()
    root.addHandler(handler)
    root.setLevel(getattr(logging, settings.log_level, logging.INFO))
    _quiet_noisy_loggers()


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
    uvicorn.run(
        "stock_analysis.web.app:app",
        host=args.host,
        port=args.port,
        workers=1,
        log_level=settings.log_level.lower(),
    )


if __name__ == "__main__":
    main()
