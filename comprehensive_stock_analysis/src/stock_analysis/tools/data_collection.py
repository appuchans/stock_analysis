"""Data collection tools for stock analysis."""

import os
import asyncio
import aiohttp
import yfinance as yf
import pandas as pd
import numpy as np
from datetime import datetime, timedelta
from typing import Optional, List, Dict, Any, Union
from alpha_vantage.timeseries import TimeSeries
from alpha_vantage.fundamentaldata import FundamentalData
from sec_api import QueryApi, RenderApi
from fredapi import Fred
import quandl
import requests
from bs4 import BeautifulSoup
import feedparser
from newspaper import Article
import json

from crewai_tools import BaseTool
from pydantic import BaseModel, Field

from ..models.stock_data import (
    StockData, PriceData, VolumeData, CompanyInfo, MarketData,
    NewsData, EarningsData, AnalystData, FundamentalData as FundamentalDataModel,
    TechnicalIndicators, RiskMetrics, IndustryData, CompetitorData, EconomicData
)


class YahooFinanceTool(BaseTool):
    """Tool for collecting data from Yahoo Finance."""
    
    name: str = "Yahoo Finance Data Collector"
    description: str = "Collects comprehensive stock data from Yahoo Finance including prices, fundamentals, and company information"
    
    def _run(self, symbol: str, period: str = "1y", interval: str = "1d") -> Dict[str, Any]:
        """Collect data from Yahoo Finance."""
        try:
            ticker = yf.Ticker(symbol)
            
            # Get basic info
            info = ticker.info
            
            # Get historical data
            hist = ticker.history(period=period, interval=interval)
            
            # Get company info
            company_info = CompanyInfo(
                symbol=symbol,
                name=info.get('longName', symbol),
                sector=info.get('sector'),
                industry=info.get('industry'),
                country=info.get('country'),
                exchange=info.get('exchange'),
                currency=info.get('currency'),
                website=info.get('website'),
                description=info.get('longBusinessSummary'),
                employees=info.get('fullTimeEmployees'),
                founded_year=info.get('founded'),
                ceo=next((o.get('name') for o in info.get('companyOfficers', [])), None),
                headquarters=info.get('city') + ', ' + info.get('state') if info.get('city') and info.get('state') else None
            )
            
            # Get market data
            current_price = hist['Close'].iloc[-1] if not hist.empty else 0
            previous_close = info.get('previousClose', current_price)
            day_change = current_price - previous_close
            day_change_percent = (day_change / previous_close * 100) if previous_close != 0 else 0
            
            market_data = MarketData(
                symbol=symbol,
                current_price=current_price,
                previous_close=previous_close,
                day_change=day_change,
                day_change_percent=day_change_percent,
                volume=hist['Volume'].iloc[-1] if not hist.empty else 0,
                avg_volume=info.get('averageVolume'),
                market_cap=info.get('marketCap'),
                high_52w=info.get('fiftyTwoWeekHigh'),
                low_52w=info.get('fiftyTwoWeekLow'),
                beta=info.get('beta'),
                timestamp=datetime.now()
            )
            
            # Get price history
            price_history = []
            for idx, row in hist.iterrows():
                price_history.append(PriceData(
                    open=row['Open'],
                    high=row['High'],
                    low=row['Low'],
                    close=row['Close'],
                    adjusted_close=row.get('Adj Close'),
                    timestamp=idx.to_pydatetime()
                ))
            
            # Get volume history
            volume_history = []
            for idx, row in hist.iterrows():
                volume_history.append(VolumeData(
                    volume=int(row['Volume']),
                    timestamp=idx.to_pydatetime()
                ))
            
            # Get fundamental data
            fundamental_data = FundamentalDataModel(
                pe_ratio=info.get('trailingPE'),
                pb_ratio=info.get('priceToBook'),
                ps_ratio=info.get('priceToSalesTrailing12Months'),
                peg_ratio=info.get('pegRatio'),
                ev_ebitda=info.get('enterpriseToEbitda'),
                roe=info.get('returnOnEquity'),
                roa=info.get('returnOnAssets'),
                gross_margin=info.get('grossMargins'),
                operating_margin=info.get('operatingMargins'),
                net_margin=info.get('profitMargins'),
                debt_to_equity=info.get('debtToEquity'),
                current_ratio=info.get('currentRatio'),
                quick_ratio=info.get('quickRatio'),
                market_cap=info.get('marketCap'),
                enterprise_value=info.get('enterpriseValue'),
                total_revenue=info.get('totalRevenue'),
                net_income=info.get('netIncomeToCommon'),
                total_assets=info.get('totalAssets'),
                total_liabilities=info.get('totalLiab'),
                total_equity=info.get('totalStockholderEquity'),
                free_cash_flow=info.get('freeCashflow'),
                dividend_yield=info.get('dividendYield'),
                dividend_per_share=info.get('dividendRate'),
                payout_ratio=info.get('payoutRatio'),
                timestamp=datetime.now()
            )
            
            return {
                "company_info": company_info.dict(),
                "market_data": market_data.dict(),
                "price_history": [p.dict() for p in price_history],
                "volume_history": [v.dict() for v in volume_history],
                "fundamental_data": fundamental_data.dict(),
                "raw_info": info
            }
            
        except Exception as e:
            return {"error": f"Failed to collect Yahoo Finance data: {str(e)}"}


class AlphaVantageTool(BaseTool):
    """Tool for collecting data from Alpha Vantage API."""
    
    name: str = "Alpha Vantage Data Collector"
    description: str = "Collects additional financial data from Alpha Vantage API"
    
    def __init__(self, api_key: Optional[str] = None):
        super().__init__()
        self.api_key = api_key or os.getenv('ALPHA_VANTAGE_API_KEY')
        if not self.api_key:
            raise ValueError("Alpha Vantage API key is required")
        
        self.ts = TimeSeries(key=self.api_key)
        self.fd = FundamentalData(key=self.api_key)
    
    def _run(self, symbol: str, function: str = "TIME_SERIES_DAILY") -> Dict[str, Any]:
        """Collect data from Alpha Vantage."""
        try:
            if function == "TIME_SERIES_DAILY":
                data, meta_data = self.ts.get_daily(symbol)
                return {"data": data, "meta_data": meta_data}
            elif function == "BALANCE_SHEET":
                data, meta_data = self.fd.get_balance_sheet_annual(symbol)
                return {"data": data, "meta_data": meta_data}
            elif function == "INCOME_STATEMENT":
                data, meta_data = self.fd.get_income_statement_annual(symbol)
                return {"data": data, "meta_data": meta_data}
            elif function == "CASH_FLOW":
                data, meta_data = self.fd.get_cash_flow_annual(symbol)
                return {"data": data, "meta_data": meta_data}
            else:
                return {"error": f"Unsupported function: {function}"}
                
        except Exception as e:
            return {"error": f"Failed to collect Alpha Vantage data: {str(e)}"}


class SECFilingTool(BaseTool):
    """Tool for collecting SEC filing data."""
    
    name: str = "SEC Filing Data Collector"
    description: str = "Collects SEC filing data including 10-K, 10-Q, and 8-K forms"
    
    def __init__(self, api_key: Optional[str] = None):
        super().__init__()
        self.api_key = api_key or os.getenv('SEC_API_KEY')
        if not self.api_key:
            raise ValueError("SEC API key is required")
        
        self.query_api = QueryApi(api_key=self.api_key)
        self.render_api = RenderApi(api_key=self.api_key)
    
    def _run(self, symbol: str, form_type: str = "10-K", limit: int = 1) -> Dict[str, Any]:
        """Collect SEC filing data."""
        try:
            query = {
                "query": {
                    "query_string": {
                        "query": f"ticker:{symbol} AND formType:\"{form_type}\""
                    }
                },
                "from": "0",
                "size": str(limit),
                "sort": [{"filedAt": {"order": "desc"}}]
            }
            
            filings = self.query_api.get_filings(query)
            
            if not filings.get('filings'):
                return {"error": f"No {form_type} filings found for {symbol}"}
            
            filing = filings['filings'][0]
            
            # Get the filing content
            filing_url = filing['linkToFilingDetails']
            filing_content = self.render_api.get_filing(filing_url)
            
            return {
                "filing": filing,
                "content": filing_content,
                "url": filing_url
            }
            
        except Exception as e:
            return {"error": f"Failed to collect SEC filing data: {str(e)}"}


class FREDTool(BaseTool):
    """Tool for collecting economic data from FRED."""
    
    name: str = "FRED Economic Data Collector"
    description: str = "Collects economic indicators from Federal Reserve Economic Data (FRED)"
    
    def __init__(self, api_key: Optional[str] = None):
        super().__init__()
        self.api_key = api_key or os.getenv('FRED_API_KEY')
        if not self.api_key:
            raise ValueError("FRED API key is required")
        
        self.fred = Fred(api_key=self.api_key)
    
    def _run(self, series_id: str, start_date: Optional[str] = None, end_date: Optional[str] = None) -> Dict[str, Any]:
        """Collect economic data from FRED."""
        try:
            if start_date is None:
                start_date = (datetime.now() - timedelta(days=365)).strftime('%Y-%m-%d')
            if end_date is None:
                end_date = datetime.now().strftime('%Y-%m-%d')
            
            data = self.fred.get_series(series_id, start_date, end_date)
            series_info = self.fred.get_series_info(series_id)
            
            return {
                "data": data.to_dict(),
                "info": series_info,
                "series_id": series_id
            }
            
        except Exception as e:
            return {"error": f"Failed to collect FRED data: {str(e)}"}


class QuandlTool(BaseTool):
    """Tool for collecting data from Quandl."""
    
    name: str = "Quandl Data Collector"
    description: str = "Collects financial and economic data from Quandl"
    
    def __init__(self, api_key: Optional[str] = None):
        super().__init__()
        self.api_key = api_key or os.getenv('QUANDL_API_KEY')
        if not self.api_key:
            raise ValueError("Quandl API key is required")
        
        quandl.ApiConfig.api_key = self.api_key
    
    def _run(self, dataset: str, start_date: Optional[str] = None, end_date: Optional[str] = None) -> Dict[str, Any]:
        """Collect data from Quandl."""
        try:
            if start_date is None:
                start_date = (datetime.now() - timedelta(days=365)).strftime('%Y-%m-%d')
            if end_date is None:
                end_date = datetime.now().strftime('%Y-%m-%d')
            
            data = quandl.get(dataset, start_date=start_date, end_date=end_date)
            
            return {
                "data": data.to_dict(),
                "dataset": dataset,
                "columns": list(data.columns)
            }
            
        except Exception as e:
            return {"error": f"Failed to collect Quandl data: {str(e)}"}


class NewsTool(BaseTool):
    """Tool for collecting news data."""
    
    name: str = "News Data Collector"
    description: str = "Collects news articles and sentiment data for stocks"
    
    def __init__(self, tavily_api_key: Optional[str] = None, serpapi_api_key: Optional[str] = None):
        super().__init__()
        self.tavily_api_key = tavily_api_key or os.getenv('TAVILY_API_KEY')
        self.serpapi_api_key = serpapi_api_key or os.getenv('SERPAPI_API_KEY')
    
    def _run(self, symbol: str, query: Optional[str] = None, limit: int = 10) -> Dict[str, Any]:
        """Collect news data for a stock."""
        try:
            if not query:
                query = f"{symbol} stock news"
            
            news_data = []
            
            # Use Tavily if available
            if self.tavily_api_key:
                try:
                    from tavily import TavilyClient
                    client = TavilyClient(api_key=self.tavily_api_key)
                    response = client.search(query=query, max_results=limit)
                    
                    for result in response.get('results', []):
                        news_data.append(NewsData(
                            title=result.get('title', ''),
                            summary=result.get('content', ''),
                            url=result.get('url', ''),
                            source=result.get('source', ''),
                            published_at=datetime.now(),  # Tavily doesn't provide exact dates
                            sentiment_score=None,
                            relevance_score=result.get('score', 0.5),
                            tags=[]
                        ))
                except Exception as e:
                    print(f"Tavily search failed: {e}")
            
            # Fallback to RSS feeds
            if not news_data:
                rss_feeds = [
                    f"https://feeds.finance.yahoo.com/rss/2.0/headline?s={symbol}&region=US&lang=en-US",
                    f"https://feeds.marketwatch.com/marketwatch/marketpulse/",
                ]
                
                for feed_url in rss_feeds:
                    try:
                        feed = feedparser.parse(feed_url)
                        for entry in feed.entries[:limit//len(rss_feeds)]:
                            if symbol.lower() in entry.title.lower() or symbol.lower() in entry.get('summary', '').lower():
                                news_data.append(NewsData(
                                    title=entry.title,
                                    summary=entry.get('summary', ''),
                                    url=entry.link,
                                    source=feed.feed.get('title', 'Unknown'),
                                    published_at=datetime(*entry.published_parsed[:6]) if hasattr(entry, 'published_parsed') else datetime.now(),
                                    sentiment_score=None,
                                    relevance_score=0.8,
                                    tags=[]
                                ))
                    except Exception as e:
                        print(f"RSS feed {feed_url} failed: {e}")
            
            return {
                "news_data": [n.dict() for n in news_data],
                "total_count": len(news_data)
            }
            
        except Exception as e:
            return {"error": f"Failed to collect news data: {str(e)}"}


class EconomicDataTool(BaseTool):
    """Tool for collecting economic data from multiple sources."""
    
    name: str = "Economic Data Collector"
    description: str = "Collects comprehensive economic data from multiple sources"
    
    def __init__(self, fred_api_key: Optional[str] = None, quandl_api_key: Optional[str] = None):
        super().__init__()
        self.fred_api_key = fred_api_key or os.getenv('FRED_API_KEY')
        self.quandl_api_key = quandl_api_key or os.getenv('QUANDL_API_KEY')
        
        if self.fred_api_key:
            self.fred = Fred(api_key=self.fred_api_key)
        if self.quandl_api_key:
            quandl.ApiConfig.api_key = self.quandl_api_key
    
    def _run(self, country: str = "US", indicators: Optional[List[str]] = None) -> Dict[str, Any]:
        """Collect economic data."""
        try:
            if indicators is None:
                indicators = [
                    "GDPC1",  # Real GDP
                    "CPIAUCSL",  # Consumer Price Index
                    "FEDFUNDS",  # Federal Funds Rate
                    "UNRATE",  # Unemployment Rate
                    "UMCSENT",  # Consumer Sentiment
                    "PAYEMS",  # Nonfarm Payrolls
                ]
            
            economic_data = {}
            
            if self.fred_api_key:
                for indicator in indicators:
                    try:
                        data = self.fred.get_series(indicator)
                        series_info = self.fred.get_series_info(indicator)
                        economic_data[indicator] = {
                            "data": data.to_dict(),
                            "info": series_info
                        }
                    except Exception as e:
                        print(f"Failed to get {indicator}: {e}")
            
            # Create EconomicData model
            gdp_data = economic_data.get("GDPC1", {}).get("data", {})
            cpi_data = economic_data.get("CPIAUCSL", {}).get("data", {})
            fed_funds_data = economic_data.get("FEDFUNDS", {}).get("data", {})
            unemployment_data = economic_data.get("UNRATE", {}).get("data", {})
            
            # Calculate growth rates
            gdp_growth = None
            if gdp_data:
                gdp_values = list(gdp_data.values())
                if len(gdp_values) >= 2:
                    gdp_growth = ((gdp_values[-1] - gdp_values[-2]) / gdp_values[-2] * 100)
            
            inflation_rate = None
            if cpi_data:
                cpi_values = list(cpi_data.values())
                if len(cpi_values) >= 12:
                    inflation_rate = ((cpi_values[-1] - cpi_values[-12]) / cpi_values[-12] * 100)
            
            interest_rate = list(fed_funds_data.values())[-1] if fed_funds_data else None
            unemployment_rate = list(unemployment_data.values())[-1] if unemployment_data else None
            
            economic_data_model = EconomicData(
                gdp_growth=gdp_growth,
                inflation_rate=inflation_rate,
                interest_rate=interest_rate,
                unemployment_rate=unemployment_rate,
                consumer_confidence=None,
                business_confidence=None,
                currency_strength=None,
                country=country,
                timestamp=datetime.now()
            )
            
            return {
                "economic_data": economic_data_model.dict(),
                "raw_data": economic_data
            }
            
        except Exception as e:
            return {"error": f"Failed to collect economic data: {str(e)}"}
