"""Main application entry point for comprehensive stock analysis."""

import argparse
import json
import sys
from pathlib import Path
from typing import Dict, Any, Optional
from datetime import datetime

from .crew.modern_crew import ModernStockAnalysisCrew
from .crew.flow_crew import StockAnalysisFlowCrew, QuickAnalysisFlowCrew, DeepDiveAnalysisFlowCrew
from .config.settings import settings


class StockAnalysisApp:
    """Main application class for stock analysis."""
    
    def __init__(self, llm_provider: str = "openai", model: str = "gpt-4", crew_type: str = "modern"):
        """Initialize the stock analysis application."""
        self.llm_provider = llm_provider
        self.model = model
        self.crew_type = crew_type
        
        # Initialize the appropriate crew type
        if crew_type == "modern":
            self.crew = ModernStockAnalysisCrew(llm_provider, model)
        elif crew_type == "flow":
            self.crew = StockAnalysisFlowCrew(llm_provider, model)
        elif crew_type == "quick":
            self.crew = QuickAnalysisFlowCrew(llm_provider, model)
        elif crew_type == "deep_dive":
            self.crew = DeepDiveAnalysisFlowCrew(llm_provider, model)
        else:
            raise ValueError(f"Unknown crew type: {crew_type}")
    
    def analyze_stock(self, symbol: str, **kwargs) -> Dict[str, Any]:
        """Analyze a single stock."""
        print(f"Starting comprehensive analysis for {symbol}...")
        
        try:
            result = self.crew.analyze_stock(symbol, **kwargs)
            
            if result["status"] == "completed":
                print(f"Analysis completed successfully for {symbol}")
                return result
            else:
                print(f"Analysis failed for {symbol}: {result.get('error', 'Unknown error')}")
                return result
                
        except Exception as e:
            print(f"Error analyzing {symbol}: {str(e)}")
            return {
                "symbol": symbol,
                "error": str(e),
                "status": "failed",
                "timestamp": datetime.now().isoformat()
            }
    
    def analyze_multiple_stocks(self, symbols: list, **kwargs) -> Dict[str, Any]:
        """Analyze multiple stocks."""
        print(f"Starting analysis for {len(symbols)} stocks: {', '.join(symbols)}")
        
        results = {}
        
        for symbol in symbols:
            print(f"\nAnalyzing {symbol}...")
            result = self.analyze_stock(symbol, **kwargs)
            results[symbol] = result
        
        # Summary
        completed = sum(1 for r in results.values() if r["status"] == "completed")
        failed = sum(1 for r in results.values() if r["status"] == "failed")
        
        print(f"\nAnalysis Summary:")
        print(f"Completed: {completed}")
        print(f"Failed: {failed}")
        
        return {
            "results": results,
            "summary": {
                "total": len(symbols),
                "completed": completed,
                "failed": failed
            },
            "timestamp": datetime.now().isoformat()
        }
    
    def save_results(self, results: Dict[str, Any], output_file: str):
        """Save analysis results to file."""
        try:
            output_path = Path(output_file)
            output_path.parent.mkdir(parents=True, exist_ok=True)
            
            with open(output_path, 'w') as f:
                json.dump(results, f, indent=2, default=str)
            
            print(f"Results saved to {output_file}")
            
        except Exception as e:
            print(f"Error saving results: {str(e)}")
    
    def load_config(self, config_file: str) -> Dict[str, Any]:
        """Load configuration from file."""
        try:
            with open(config_file, 'r') as f:
                return json.load(f)
        except Exception as e:
            print(f"Error loading config: {str(e)}")
            return {}


def main():
    """Main entry point."""
    parser = argparse.ArgumentParser(description="Comprehensive Stock Analysis Tool")
    parser.add_argument("symbol", nargs="+", help="Stock symbol(s) to analyze")
    parser.add_argument("--output", "-o", help="Output file for results")
    parser.add_argument("--config", "-c", help="Configuration file")
    parser.add_argument("--llm-provider", default="openai", choices=["openai", "anthropic"], 
                       help="LLM provider to use")
    parser.add_argument("--model", default="gpt-4", help="LLM model to use")
    parser.add_argument("--timeframe", default="1y", help="Analysis timeframe")
    parser.add_argument("--format", default="json", choices=["json", "pdf"], 
                       help="Output format")
    parser.add_argument("--crew-type", default="modern", 
                       choices=["modern", "flow", "quick", "deep_dive"],
                       help="Type of crew to use for analysis")
    
    args = parser.parse_args()
    
    # Initialize application
    app = StockAnalysisApp(args.llm_provider, args.model, args.crew_type)
    
    # Load configuration if provided
    config = {}
    if args.config:
        config = app.load_config(args.config)
    
    # Prepare analysis parameters
    analysis_params = {
        "timeframe": args.timeframe,
        "format": args.format,
        **config
    }
    
    # Analyze stocks
    if len(args.symbol) == 1:
        results = app.analyze_stock(args.symbol[0], **analysis_params)
    else:
        results = app.analyze_multiple_stocks(args.symbol, **analysis_params)
    
    # Save results
    if args.output:
        app.save_results(results, args.output)
    else:
        # Default output file
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        if len(args.symbol) == 1:
            output_file = f"reports/{args.symbol[0]}_analysis_{timestamp}.json"
        else:
            output_file = f"reports/multi_stock_analysis_{timestamp}.json"
        app.save_results(results, output_file)
    
    # Print summary
    if results.get("status") == "completed":
        print(f"\nAnalysis completed successfully!")
    elif results.get("status") == "failed":
        print(f"\nAnalysis failed: {results.get('error', 'Unknown error')}")
        sys.exit(1)
    else:
        # Multiple stocks
        summary = results.get("summary", {})
        print(f"\nAnalysis completed: {summary.get('completed', 0)}/{summary.get('total', 0)} stocks")


if __name__ == "__main__":
    main()
