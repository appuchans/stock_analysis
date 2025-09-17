"""Basic example of using the comprehensive stock analysis solution."""

import os
import sys
from pathlib import Path

# Add the src directory to the Python path
sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

from stock_analysis import StockAnalysisCrew
from stock_analysis.config.settings import settings


def main():
    """Run a basic stock analysis example."""
    
    # Set up API keys (you can also use environment variables)
    # settings.openai_api_key = "your-openai-api-key"
    # settings.anthropic_api_key = "your-anthropic-api-key"
    
    # Initialize the stock analysis crew
    print("Initializing Stock Analysis Crew...")
    crew = StockAnalysisCrew(
        llm_provider="openai",  # or "anthropic"
        model="gpt-4"  # or "claude-3-sonnet"
    )
    
    # Analyze a stock
    symbol = "AAPL"  # Apple Inc.
    print(f"\nAnalyzing {symbol}...")
    
    try:
        result = crew.analyze_stock(symbol)
        
        if result["status"] == "completed":
            print(f"✅ Analysis completed successfully for {symbol}")
            print(f"📊 Analysis result: {result['analysis_result']}")
        else:
            print(f"❌ Analysis failed for {symbol}: {result.get('error', 'Unknown error')}")
            
    except Exception as e:
        print(f"❌ Error analyzing {symbol}: {str(e)}")
    
    # Analyze multiple stocks
    symbols = ["AAPL", "MSFT", "GOOGL"]
    print(f"\nAnalyzing multiple stocks: {', '.join(symbols)}")
    
    try:
        results = crew.analyze_multiple_stocks(symbols)
        
        summary = results.get("summary", {})
        print(f"📈 Analysis Summary:")
        print(f"   Total: {summary.get('total', 0)}")
        print(f"   Completed: {summary.get('completed', 0)}")
        print(f"   Failed: {summary.get('failed', 0)}")
        
        # Print individual results
        for symbol, result in results.get("results", {}).items():
            status = "✅" if result["status"] == "completed" else "❌"
            print(f"   {status} {symbol}: {result['status']}")
            
    except Exception as e:
        print(f"❌ Error analyzing multiple stocks: {str(e)}")


if __name__ == "__main__":
    main()
