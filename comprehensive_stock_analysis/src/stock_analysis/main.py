"""Main application entry point for comprehensive stock analysis."""

import argparse
import json
import sys
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional

from .config.settings import settings
from .crew.flow_crew import DeepDiveAnalysisFlowCrew, QuickAnalysisFlowCrew, StockAnalysisFlowCrew
from .crew.modern_crew import ModernStockAnalysisCrew
from .crew.stock_analysis_crew import StockAnalysisCrew


class StockAnalysisApp:
    """Main application class for stock analysis.

    llm_provider and model are both optional — when None (the default) the
    values come from config/llm_config.yaml (with env-var overrides).  Pass
    explicit values only when you need a one-off runtime override.
    """

    def __init__(
        self,
        llm_provider: Optional[str] = None,
        model: Optional[str] = None,
        crew_type: str = "modern",
    ):
        self.llm_provider = llm_provider
        self.model = model
        self.crew_type = crew_type

        crew_map = {
            "modern": ModernStockAnalysisCrew,
            "standard": StockAnalysisCrew,
            "flow": StockAnalysisFlowCrew,
            "quick": QuickAnalysisFlowCrew,
            "deep_dive": DeepDiveAnalysisFlowCrew,
        }
        if crew_type not in crew_map:
            raise ValueError(
                f"Unknown crew type '{crew_type}'. "
                f"Valid options: {', '.join(crew_map)}"
            )
        self.crew = crew_map[crew_type](llm_provider, model)

    def analyze_stock(self, symbol: str, **kwargs: Any) -> Dict[str, Any]:
        print(f"Starting comprehensive analysis for {symbol}…")
        try:
            result = self.crew.analyze_stock(symbol, **kwargs)
            if result["status"] == "completed":
                print(f"Analysis completed for {symbol}")
            else:
                print(f"Analysis failed for {symbol}: {result.get('error', 'Unknown error')}")
            return result
        except Exception as e:
            print(f"Error analysing {symbol}: {e}")
            return {
                "symbol": symbol,
                "error": str(e),
                "status": "failed",
                "timestamp": datetime.now().isoformat(),
            }

    def analyze_multiple_stocks(self, symbols: List[str], **kwargs: Any) -> Dict[str, Any]:
        print(f"Starting analysis for {len(symbols)} stocks: {', '.join(symbols)}")
        results: Dict[str, Any] = {}
        for symbol in symbols:
            print(f"\nAnalysing {symbol}…")
            results[symbol] = self.analyze_stock(symbol, **kwargs)
        completed = sum(1 for r in results.values() if r["status"] == "completed")
        failed = len(symbols) - completed
        print(f"\nSummary — completed: {completed}, failed: {failed}")
        return {
            "results": results,
            "summary": {"total": len(symbols), "completed": completed, "failed": failed},
            "timestamp": datetime.now().isoformat(),
        }

    def save_results(self, results: Dict[str, Any], output_file: str) -> None:
        output_path = Path(output_file)
        output_path.parent.mkdir(parents=True, exist_ok=True)
        with open(output_path, "w") as f:
            json.dump(results, f, indent=2, default=str)
        print(f"Results saved to {output_file}")

    def load_config(self, config_file: str) -> Dict[str, Any]:
        try:
            with open(config_file, "r") as f:
                return json.load(f)
        except Exception as e:
            print(f"Error loading config {config_file}: {e}")
            return {}


def main() -> None:
    """CLI entry point."""
    parser = argparse.ArgumentParser(
        description="Comprehensive Stock Analysis Tool",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
LLM configuration priority (highest wins):
  CLI flags  >  env vars (LLM_PROVIDER, LLM_MODEL)  >  llm_config.yaml per-agent
  >  env vars  >  llm_config.yaml global defaults

Examples:
  # Use defaults from config/llm_config.yaml
  python -m stock_analysis.main AAPL

  # Override provider/model at runtime
  python -m stock_analysis.main AAPL --llm-provider anthropic --model claude-sonnet-4-6

  # Analyse multiple stocks with the deep-dive flow
  python -m stock_analysis.main AAPL MSFT GOOGL --crew-type deep_dive
""",
    )
    parser.add_argument("symbol", nargs="+", help="Stock symbol(s) to analyse")
    parser.add_argument("--output", "-o", help="Output file for results (default: auto-named)")
    parser.add_argument("--config", "-c", help="Optional JSON config file")
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
        "--timeframe", default=settings.analysis_timeframe, help="Analysis timeframe (default: 1y)"
    )
    parser.add_argument(
        "--format",
        default=settings.report_format,
        choices=["json", "pdf", "html"],
        help="Output format",
    )
    parser.add_argument(
        "--crew-type",
        default="modern",
        choices=["modern", "standard", "flow", "quick", "deep_dive"],
        help="Crew implementation to use (default: modern)",
    )

    args = parser.parse_args()

    app = StockAnalysisApp(args.llm_provider, args.model, args.crew_type)

    extra: Dict[str, Any] = {"timeframe": args.timeframe, "format": args.format}
    if args.config:
        extra.update(app.load_config(args.config))

    if len(args.symbol) == 1:
        results = app.analyze_stock(args.symbol[0], **extra)
    else:
        results = app.analyze_multiple_stocks(args.symbol, **extra)

    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    if args.output:
        output_file = args.output
    elif len(args.symbol) == 1:
        output_file = f"reports/{args.symbol[0]}_analysis_{timestamp}.json"
    else:
        output_file = f"reports/multi_stock_analysis_{timestamp}.json"

    app.save_results(results, output_file)

    if results.get("status") == "failed":
        print(f"\nAnalysis failed: {results.get('error', 'Unknown error')}")
        sys.exit(1)
    elif "summary" in results:
        s = results["summary"]
        print(f"\nDone — {s['completed']}/{s['total']} symbols completed.")
    else:
        print("\nAnalysis completed successfully.")


if __name__ == "__main__":
    main()
