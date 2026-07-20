"""Main application entry point for comprehensive stock analysis."""

import argparse
import logging
import sys
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional

from .config.settings import settings
from .crew.flow_crew import StockAnalysisFlow

_logger = logging.getLogger(__name__)


def _print_token_usage(symbol: str, token_usage: Dict[str, Any], llm_calls: int = 0) -> None:
    """Print token usage (and LLM call count) to console and log file."""
    if not token_usage:
        return
    inp = token_usage.get("prompt_tokens") or token_usage.get("input_tokens") or 0
    out = token_usage.get("completion_tokens") or token_usage.get("output_tokens") or 0
    total = token_usage.get("total_tokens") or (inp + out)
    cached = token_usage.get("cached_prompt_tokens") or 0
    calls_str = f"  LLM calls: {llm_calls}" if llm_calls else ""
    cached_str = f"  (cached prompt: {cached:,})" if cached else ""
    line = f"  Tokens — input: {inp:,}  output: {out:,}  total: {total:,}{cached_str}{calls_str}"
    print(line, flush=True)
    _logger.info(
        "[token-usage] symbol=%s input=%d output=%d total=%d cached=%d llm_calls=%d",
        symbol, inp, out, total, cached, llm_calls,
    )


class StockAnalysisApp:
    """Main application class for stock analysis.

    llm_provider and model are both optional — when None (the default) the
    values come from config/llm_config.yaml (with env-var overrides).  Pass
    explicit values only when you need a one-off runtime override.

    The analysis runs the event-driven Flow pipeline; `depth` controls scope:
      "quick"    — fundamental (+ technical for stocks)
      "standard" — + ownership, risk, sentiment  (default)
      "deep"     — all specialist analysts
    """

    def __init__(
        self,
        llm_provider: Optional[str] = None,
        model: Optional[str] = None,
        depth: str = "standard",
        asset_type: str = "auto",
        use_data_cache: bool = True,
    ):
        self.llm_provider = llm_provider
        self.model = model
        self.depth = depth
        self.asset_type = asset_type
        self.crew = StockAnalysisFlow(
            llm_provider, model, asset_type=asset_type, use_data_cache=use_data_cache
        )

    def analyze_stock(self, symbol: str, **kwargs: Any) -> Dict[str, Any]:
        print(f"\nStarting analysis for {symbol}…")
        try:
            result = self.crew.analyze_stock(symbol, analysis_depth=self.depth, **kwargs)
            if result["status"] == "completed":
                _print_token_usage(
                    symbol, result.get("token_usage") or {}, result.get("llm_calls") or 0
                )
                report_path = result.get("report_path")
                if not report_path:
                    report_dir = Path(settings.report_output_dir) / symbol.upper() / "html"
                    reports = sorted(report_dir.glob("*.html")) if report_dir.exists() else []
                    report_path = reports[-1] if reports else None
                if report_path:
                    print(f"  Report: {report_path}")
                else:
                    print(
                        f"  Warning: no HTML report was generated for {symbol} — "
                        f"check {settings.crew_log_file} for details."
                    )
            else:
                print(f"  Failed: {result.get('error', 'Unknown error')}")
            return result
        except Exception as e:
            print(f"  Error: {e}")
            return {
                "symbol": symbol,
                "error": str(e),
                "status": "failed",
                "timestamp": datetime.now().isoformat(),
            }

    def analyze_multiple_stocks(self, symbols: List[str], **kwargs: Any) -> Dict[str, Any]:
        print(f"Analysing {len(symbols)} stocks: {', '.join(symbols)}")
        results: Dict[str, Any] = {}
        for symbol in symbols:
            results[symbol] = self.analyze_stock(symbol, **kwargs)
        completed = sum(1 for r in results.values() if r["status"] == "completed")
        failed = len(symbols) - completed
        print(f"\nSummary — completed: {completed}, failed: {failed}")
        return {
            "results": results,
            "summary": {"total": len(symbols), "completed": completed, "failed": failed},
            "timestamp": datetime.now().isoformat(),
        }

def _rotate_if_large(path: Path, max_bytes: int = 5_000_000) -> None:
    """Size-based rotation: keep one .old generation, never grow unbounded."""
    try:
        if path.exists() and path.stat().st_size > max_bytes:
            path.replace(path.with_suffix(path.suffix + ".old"))
    except OSError as exc:
        _logger.warning("Log rotation failed for %s: %s", path, exc)


def _drop_noise(record: logging.LogRecord) -> bool:
    """Filter chatty per-call lines out of the persistent log."""
    msg = record.getMessage()
    return "Successfully validated tool" not in msg


def _quiet_noisy_loggers() -> None:
    """Third-party loggers emit per-request noise at INFO/ERROR that our tools
    already handle and report through Data Gaps — keep the log signal-rich."""
    logging.getLogger("httpx").setLevel(logging.WARNING)
    logging.getLogger("openai").setLevel(logging.WARNING)
    logging.getLogger("LiteLLM").setLevel(logging.WARNING)
    # yfinance logs ERROR for invalid/delisted symbols that our tools probe and
    # discard deliberately (e.g. competitor candidate validation)
    logging.getLogger("yfinance").setLevel(logging.CRITICAL)


def main() -> None:
    """CLI entry point."""
    parser = argparse.ArgumentParser(
        description="Comprehensive Stock Analysis Tool",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
LLM configuration priority (highest wins):
  CLI flags  >  env vars (LLM_PROVIDER, LLM_MODEL)  >  llm_config.yaml per-agent
  >  env vars  >  llm_config.yaml global defaults

Analysis depth (--depth):
  quick     — fundamental (+ technical for stocks)
  standard  — + ownership, risk, sentiment  (default)
  deep      — all specialist analysts

Examples:
  # Standard-depth analysis with defaults from config/llm_config.yaml
  python -m stock_analysis.main AAPL

  # Deep analysis
  python -m stock_analysis.main AAPL --depth deep

  # Override provider/model at runtime
  python -m stock_analysis.main AAPL --llm-provider anthropic --model claude-sonnet-4-6

  # Analyse multiple stocks
  python -m stock_analysis.main AAPL MSFT GOOGL
""",
    )
    parser.add_argument("symbol", nargs="+", help="Stock symbol(s) to analyse")
    parser.add_argument(
        "--llm-provider",
        default=None,
        help=(
            "LLM provider override (e.g. openai, anthropic, ollama, groq, mistral). "
            "Defaults to llm_config.yaml / LLM_PROVIDER env var."
        ),
    )
    parser.add_argument(
        "--model",
        default=None,
        help=(
            "Model name override (e.g. gpt-4o, claude-sonnet-4-6, llama3). "
            "Defaults to llm_config.yaml / LLM_MODEL env var."
        ),
    )
    parser.add_argument(
        "--depth",
        default="standard",
        choices=["quick", "standard", "deep"],
        help="Analysis depth (default: standard)",
    )
    parser.add_argument(
        "--asset-type",
        default="auto",
        choices=["auto", "stock", "etf"],
        help="Asset type override (default: auto-detect from yfinance)",
    )
    parser.add_argument(
        "--no-cache",
        action="store_true",
        help=(
            "Force a fresh data pull, ignoring any cached structured data for the "
            "symbol. The freshly pulled data still refreshes the cache for later runs."
        ),
    )

    args = parser.parse_args()

    # Configure logging so _logger.info() writes to the log file
    log_path = Path(settings.crew_log_file)
    log_path.parent.mkdir(parents=True, exist_ok=True)
    _rotate_if_large(log_path)
    _rotate_if_large(Path(str(log_path) + ".txt"))  # CrewAI output_log_file
    _file_handler = logging.FileHandler(log_path, encoding="utf-8")
    _file_handler.setFormatter(logging.Formatter("%(asctime)s %(levelname)s %(name)s %(message)s"))
    _file_handler.addFilter(_drop_noise)
    logging.getLogger().addHandler(_file_handler)
    logging.getLogger().setLevel(getattr(logging, settings.log_level, logging.INFO))
    _quiet_noisy_loggers()

    # Fail fast on missing credentials before any data is fetched.
    from .agents.base_agent import preflight_llm_credentials
    problems = preflight_llm_credentials(args.llm_provider)
    if problems:
        print("Configuration error — cannot start analysis:")
        for p in problems:
            print(f"  • {p}")
        print("Set the key in .env or as an environment variable and retry.")
        sys.exit(2)

    app = StockAnalysisApp(
        args.llm_provider, args.model, args.depth, args.asset_type,
        use_data_cache=not args.no_cache,
    )

    if len(args.symbol) == 1:
        results = app.analyze_stock(args.symbol[0])
        if s["failed"]:
            sys.exit(1)
    else:
        results = app.analyze_multiple_stocks(args.symbol)

    if results.get("status") == "failed":
        print(f"\nAnalysis failed: {results.get('error', 'Unknown error')}")
        sys.exit(1)
    elif "summary" in results:
        s = results["summary"]
        print(f"\nDone — {s['completed']}/{s['total']} symbols completed.")
    else:
        print("\nDone.")


if __name__ == "__main__":
    main()
