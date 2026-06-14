"""Finish a report from already-completed analysis stage files.

Usage:  python scripts/finish_report.py SYMBOL

Reconstructs flow state from the markdown files in reports/<SYMBOL>/ and runs
only the remaining stages: recommendation synthesis (if missing), the
narrative, and the deterministic HTML render. Useful when a run was
interrupted after the specialist analyses completed — no need to re-run
(and re-pay for) the analysis stages.
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from stock_analysis.config.settings import settings  # noqa: E402
from stock_analysis.crew.flow_crew import StockAnalysisFlow  # noqa: E402


def main() -> None:
    if len(sys.argv) != 2:
        sys.exit("usage: python scripts/finish_report.py SYMBOL")
    sym = sys.argv[1].upper()
    report_dir = Path(settings.report_output_dir) / sym

    def read(name: str) -> str:
        p = report_dir / f"{sym}_{name}"
        return p.read_text(encoding="utf-8") if p.exists() else ""

    stage_files = {
        "technical": "technical_analysis.md",
        "fundamental": "fundamental_analysis.md",
        "ownership": "ownership_analysis.md",
        "risk": "risk_analysis.md",
        "sentiment": "sentiment_analysis.md",
        "market": "market_analysis.md",
        "industry": "industry_analysis.md",
        "competitor": "competitor_analysis.md",
        "economic": "economic_analysis.md",
    }

    flow = StockAnalysisFlow()
    flow.state.symbol = sym
    flow.state.asset_type = "stock"
    loaded = []
    for key, fname in stage_files.items():
        text = read(fname)
        if text:
            setattr(flow.state, key, {"result": text})
            loaded.append(key)
    if not loaded:
        sys.exit(f"No analysis files found in {report_dir} — nothing to finish.")
    print(f"Loaded stages: {', '.join(loaded)}")

    rec = read("investment_recommendation.json")
    if rec:
        flow.state.recommendation = {"result": rec}
        print("Recommendation present — skipping synthesis.")
    else:
        print("Synthesizing recommendation…")
        flow.synthesize_recommendation()

    print("Writing narrative and rendering HTML…")
    flow.generate_report()
    print(f"Done: {flow.state.report}")


if __name__ == "__main__":
    main()
