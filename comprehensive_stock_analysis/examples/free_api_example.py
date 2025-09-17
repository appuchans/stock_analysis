"""Example demonstrating the free API implementation."""

import os
import sys
from pathlib import Path

# Add the src directory to the Python path
sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

from stock_analysis.tools.free_data_collection import (
    YahooFinanceTool, FreeSECFilingTool, FreeFREDTool,
    FreeNewsTool, FreeEconomicDataTool, FreeWebSearchTool,
    FreeCompetitorAnalysisTool, FreeIndustryAnalysisTool
)


def main():
    """Demonstrate free API usage."""
    
    print("🚀 Free API Stock Analysis Example")
    print("=" * 50)
    
    symbol = "AAPL"
    
    # 1. Yahoo Finance (Free)
    print(f"\n1. Yahoo Finance Data for {symbol}")
    print("-" * 40)
    
    yahoo_tool = YahooFinanceTool()
    yahoo_data = yahoo_tool._run(symbol, period="6mo")
    
    if "error" not in yahoo_data:
        company_info = yahoo_data.get("company_info", {})
        market_data = yahoo_data.get("market_data", {})
        
        print(f"✅ Company: {company_info.get('name', 'N/A')}")
        print(f"✅ Sector: {company_info.get('sector', 'N/A')}")
        print(f"✅ Industry: {company_info.get('industry', 'N/A')}")
        print(f"✅ Current Price: ${market_data.get('current_price', 0):.2f}")
        print(f"✅ Market Cap: ${market_data.get('market_cap', 0):,}")
        print(f"✅ Price History: {len(yahoo_data.get('price_history', []))} data points")
    else:
        print(f"❌ Error: {yahoo_data['error']}")
    
    # 2. SEC Filings (Free)
    print(f"\n2. SEC Filings for {symbol}")
    print("-" * 40)
    
    sec_tool = FreeSECFilingTool()
    sec_data = sec_tool._run(symbol, form_type="10-K")
    
    if "error" not in sec_data:
        filings = sec_data.get("filings", [])
        print(f"✅ Found {len(filings)} 10-K filings")
        if filings:
            print(f"✅ Latest filing: {filings[0].get('title', 'N/A')}")
            print(f"✅ Filing date: {filings[0].get('updated', 'N/A')}")
    else:
        print(f"❌ Error: {sec_data['error']}")
    
    # 3. Economic Data (Free)
    print(f"\n3. Economic Data from FRED")
    print("-" * 40)
    
    fred_tool = FreeFREDTool(api_key="demo")  # Free demo key
    fred_data = fred_tool._run("GDPC1")  # Real GDP
    
    if "error" not in fred_data:
        data = fred_data.get("data", {})
        observations = data.get("observations", [])
        print(f"✅ GDP data points: {len(observations)}")
        if observations:
            latest = observations[-1]
            print(f"✅ Latest GDP: {latest.get('value', 'N/A')} ({latest.get('date', 'N/A')})")
    else:
        print(f"❌ Error: {fred_data['error']}")
    
    # 4. News Data (Free)
    print(f"\n4. News Data for {symbol}")
    print("-" * 40)
    
    news_tool = FreeNewsTool()
    news_data = news_tool._run(symbol, limit=5)
    
    if "error" not in news_data:
        news_items = news_data.get("news_data", [])
        print(f"✅ Found {len(news_items)} news articles")
        for i, news in enumerate(news_items[:3], 1):
            print(f"   {i}. {news.get('title', 'N/A')[:80]}...")
            print(f"      Source: {news.get('source', 'N/A')}")
    else:
        print(f"❌ Error: {news_data['error']}")
    
    # 5. Web Search (Free)
    print(f"\n5. Web Search for {symbol}")
    print("-" * 40)
    
    search_tool = FreeWebSearchTool()
    search_data = search_tool._run(f"{symbol} stock analysis 2024", num_results=3)
    
    if "error" not in search_data:
        results = search_data.get("results", [])
        print(f"✅ Found {len(results)} search results")
        for i, result in enumerate(results, 1):
            print(f"   {i}. {result.get('title', 'N/A')[:60]}...")
            print(f"      URL: {result.get('url', 'N/A')[:50]}...")
    else:
        print(f"❌ Error: {search_data['error']}")
    
    # 6. Competitor Analysis (Free)
    print(f"\n6. Competitor Analysis for {symbol}")
    print("-" * 40)
    
    competitor_tool = FreeCompetitorAnalysisTool()
    competitor_data = competitor_tool._run(symbol)
    
    if "error" not in competitor_data:
        competitors = competitor_data.get("competitors", [])
        print(f"✅ Found {len(competitors)} competitors")
        for i, comp in enumerate(competitors[:3], 1):
            print(f"   {i}. {comp.get('symbol', 'N/A')} - {comp.get('name', 'N/A')}")
            print(f"      Market Cap: ${comp.get('market_cap', 0):,}")
    else:
        print(f"❌ Error: {competitor_data['error']}")
    
    # 7. Industry Analysis (Free)
    print(f"\n7. Industry Analysis")
    print("-" * 40)
    
    industry_tool = FreeIndustryAnalysisTool()
    industry_data = industry_tool._run("Technology")
    
    if "error" not in industry_data:
        search_results = industry_data.get("search_results", [])
        print(f"✅ Found {len(search_results)} industry analysis results")
        for i, result in enumerate(search_results[:2], 1):
            print(f"   {i}. {result.get('title', 'N/A')[:60]}...")
    else:
        print(f"❌ Error: {industry_data['error']}")
    
    # 8. Economic Data (Free)
    print(f"\n8. Comprehensive Economic Data")
    print("-" * 40)
    
    economic_tool = FreeEconomicDataTool(fred_api_key="demo")
    economic_data = economic_tool._run()
    
    if "error" not in economic_data:
        econ_data = economic_data.get("economic_data", {})
        print(f"✅ GDP Growth: {econ_data.get('gdp_growth', 'N/A')}%")
        print(f"✅ Inflation Rate: {econ_data.get('inflation_rate', 'N/A')}%")
        print(f"✅ Interest Rate: {econ_data.get('interest_rate', 'N/A')}%")
        print(f"✅ Unemployment Rate: {econ_data.get('unemployment_rate', 'N/A')}%")
    else:
        print(f"❌ Error: {economic_data['error']}")
    
    print(f"\n🎉 Free API Example Completed!")
    print(f"\nKey Benefits:")
    print(f"  ✅ Zero cost for all data collection")
    print(f"  ✅ High quality data from reliable sources")
    print(f"  ✅ No API key requirements for most services")
    print(f"  ✅ Open source and transparent")
    print(f"  ✅ No vendor lock-in")
    print(f"  ✅ Comprehensive coverage of analysis needs")


if __name__ == "__main__":
    main()
