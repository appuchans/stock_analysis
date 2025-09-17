"""Free data collection tools for stock analysis using only open source and free APIs."""

import os
import asyncio
import aiohttp
import yfinance as yf
import pandas as pd
import numpy as np
from datetime import datetime, timedelta
from typing import Optional, List, Dict, Any, Union
import requests
from bs4 import BeautifulSoup
import feedparser
from newspaper import Article
import json
import re
from urllib.parse import urljoin, urlparse
import xml.etree.ElementTree as ET

from crewai_tools import BaseTool
from pydantic import BaseModel, Field

from ..models.stock_data import (
    StockData, PriceData, VolumeData, CompanyInfo, MarketData,
    NewsData, EarningsData, AnalystData, FundamentalData as FundamentalDataModel,
    TechnicalIndicators, RiskMetrics, IndustryData, CompetitorData, EconomicData
)


class YahooFinanceTool(BaseTool):
    """Tool for collecting data from Yahoo Finance (FREE)."""
    
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
                ceo=info.get('companyOfficers', [{}])[0].get('name') if info.get('companyOfficers') else None,
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


class FreeSECFilingTool(BaseTool):
    """Tool for collecting SEC filing data using free EDGAR access."""
    
    name: str = "Free SEC Filing Data Collector"
    description: str = "Collects SEC filing data using free EDGAR database access"
    
    def _run(self, symbol: str, form_type: str = "10-K", limit: int = 1) -> Dict[str, Any]:
        """Collect SEC filing data using free EDGAR access."""
        try:
            # EDGAR search URL
            search_url = "https://www.sec.gov/cgi-bin/browse-edgar"
            
            params = {
                "action": "getcompany",
                "CIK": symbol,  # This will work for some symbols, for others we need to search
                "type": form_type,
                "dateb": "",
                "owner": "exclude",
                "start": "0",
                "count": str(limit),
                "output": "atom"
            }
            
            headers = {
                "User-Agent": "Stock Analysis Tool (contact@example.com)",
                "Accept-Encoding": "gzip, deflate",
                "Host": "www.sec.gov"
            }
            
            response = requests.get(search_url, params=params, headers=headers)
            response.raise_for_status()
            
            # Parse XML response
            root = ET.fromstring(response.content)
            
            filings = []
            for entry in root.findall(".//{http://www.w3.org/2005/Atom}entry"):
                filing = {}
                
                # Get title
                title_elem = entry.find(".//{http://www.w3.org/2005/Atom}title")
                if title_elem is not None:
                    filing['title'] = title_elem.text
                
                # Get link
                link_elem = entry.find(".//{http://www.w3.org/2005/Atom}link")
                if link_elem is not None:
                    filing['link'] = link_elem.get('href')
                
                # Get updated date
                updated_elem = entry.find(".//{http://www.w3.org/2005/Atom}updated")
                if updated_elem is not None:
                    filing['updated'] = updated_elem.text
                
                # Get summary
                summary_elem = entry.find(".//{http://www.w3.org/2005/Atom}summary")
                if summary_elem is not None:
                    filing['summary'] = summary_elem.text
                
                filings.append(filing)
            
            if not filings:
                return {"error": f"No {form_type} filings found for {symbol}"}
            
            # Get the most recent filing content
            filing_url = filings[0].get('link')
            if filing_url:
                # Get the actual filing document
                filing_response = requests.get(filing_url, headers=headers)
                filing_response.raise_for_status()
                
                # Parse the filing page to find the actual document
                soup = BeautifulSoup(filing_response.content, 'html.parser')
                
                # Look for the actual filing document link
                doc_links = soup.find_all('a', href=True)
                filing_doc_url = None
                
                for link in doc_links:
                    href = link.get('href')
                    if href and (form_type.lower() in href.lower() or 'txt' in href.lower()):
                        filing_doc_url = urljoin(filing_url, href)
                        break
                
                if filing_doc_url:
                    # Get the actual filing document
                    doc_response = requests.get(filing_doc_url, headers=headers)
                    doc_response.raise_for_status()
                    
                    filing_content = doc_response.text
                else:
                    filing_content = filing_response.text
            else:
                filing_content = ""
            
            return {
                "filings": filings,
                "content": filing_content,
                "url": filing_url
            }
            
        except Exception as e:
            return {"error": f"Failed to collect SEC filing data: {str(e)}"}


class FreeFREDTool(BaseTool):
    """Tool for collecting economic data from FRED (FREE)."""
    
    name: str = "Free FRED Economic Data Collector"
    description: str = "Collects economic indicators from Federal Reserve Economic Data (FRED) - FREE"
    
    def __init__(self, api_key: Optional[str] = None):
        super().__init__()
        # FRED API key is free, but we'll make it optional
        self.api_key = api_key or os.getenv('FRED_API_KEY')
        if not self.api_key:
            # Use a demo key or direct web scraping
            self.api_key = "demo"  # FRED allows demo access
    
    def _run(self, series_id: str, start_date: Optional[str] = None, end_date: Optional[str] = None) -> Dict[str, Any]:
        """Collect economic data from FRED."""
        try:
            if start_date is None:
                start_date = (datetime.now() - timedelta(days=365)).strftime('%Y-%m-%d')
            if end_date is None:
                end_date = datetime.now().strftime('%Y-%m-%d')
            
            # FRED API URL
            base_url = "https://api.stlouisfed.org/fred"
            
            # Get series data
            data_url = f"{base_url}/series/observations"
            data_params = {
                "series_id": series_id,
                "api_key": self.api_key,
                "file_type": "json",
                "observation_start": start_date,
                "observation_end": end_date
            }
            
            response = requests.get(data_url, params=data_params)
            response.raise_for_status()
            
            data = response.json()
            
            # Get series info
            info_url = f"{base_url}/series"
            info_params = {
                "series_id": series_id,
                "api_key": self.api_key,
                "file_type": "json"
            }
            
            info_response = requests.get(info_url, params=info_params)
            info_response.raise_for_status()
            
            series_info = info_response.json()
            
            return {
                "data": data,
                "info": series_info,
                "series_id": series_id
            }
            
        except Exception as e:
            return {"error": f"Failed to collect FRED data: {str(e)}"}


class FreeNewsTool(BaseTool):
    """Tool for collecting news data using free sources."""
    
    name: str = "Free News Data Collector"
    description: str = "Collects news articles and sentiment data using free RSS feeds and web scraping"
    
    def _run(self, symbol: str, query: Optional[str] = None, limit: int = 10) -> Dict[str, Any]:
        """Collect news data for a stock using free sources."""
        try:
            if not query:
                query = f"{symbol} stock news"
            
            news_data = []
            
            # Free RSS feeds
            rss_feeds = [
                f"https://feeds.finance.yahoo.com/rss/2.0/headline?s={symbol}&region=US&lang=en-US",
                "https://feeds.marketwatch.com/marketwatch/marketpulse/",
                "https://feeds.bloomberg.com/markets/news.rss",
                "https://feeds.reuters.com/news/wealth",
                "https://feeds.finance.yahoo.com/rss/2.0/headline?s=^GSPC&region=US&lang=en-US",  # S&P 500
            ]
            
            for feed_url in rss_feeds:
                try:
                    feed = feedparser.parse(feed_url)
                    for entry in feed.entries[:limit//len(rss_feeds)]:
                        # Check if the symbol is mentioned in the title or summary
                        title = entry.get('title', '')
                        summary = entry.get('summary', '')
                        
                        if (symbol.lower() in title.lower() or 
                            symbol.lower() in summary.lower() or
                            symbol.lower() in entry.get('description', '').lower()):
                            
                            # Extract published date
                            published_at = datetime.now()
                            if hasattr(entry, 'published_parsed') and entry.published_parsed:
                                published_at = datetime(*entry.published_parsed[:6])
                            
                            news_data.append(NewsData(
                                title=title,
                                summary=summary,
                                url=entry.get('link', ''),
                                source=feed.feed.get('title', 'Unknown'),
                                published_at=published_at,
                                sentiment_score=None,
                                relevance_score=0.8,
                                tags=[]
                            ))
                except Exception as e:
                    print(f"RSS feed {feed_url} failed: {e}")
                    continue
            
            # Web scraping from financial news sites
            news_sites = [
                f"https://finance.yahoo.com/quote/{symbol}/news",
                f"https://www.marketwatch.com/investing/stock/{symbol}",
                f"https://seekingalpha.com/symbol/{symbol}/news",
            ]
            
            for site_url in news_sites:
                try:
                    headers = {
                        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36"
                    }
                    
                    response = requests.get(site_url, headers=headers)
                    response.raise_for_status()
                    
                    soup = BeautifulSoup(response.content, 'html.parser')
                    
                    # Look for news articles (this is site-specific)
                    if 'yahoo.com' in site_url:
                        articles = soup.find_all('h3', class_='Mb(5px)')
                        for article in articles[:5]:
                            link = article.find('a')
                            if link:
                                title = link.get_text(strip=True)
                                href = link.get('href', '')
                                if href and not href.startswith('http'):
                                    href = urljoin(site_url, href)
                                
                                news_data.append(NewsData(
                                    title=title,
                                    summary="",
                                    url=href,
                                    source="Yahoo Finance",
                                    published_at=datetime.now(),
                                    sentiment_score=None,
                                    relevance_score=0.9,
                                    tags=[]
                                ))
                    
                except Exception as e:
                    print(f"Web scraping {site_url} failed: {e}")
                    continue
            
            # Remove duplicates based on URL
            seen_urls = set()
            unique_news = []
            for news in news_data:
                if news.url not in seen_urls:
                    seen_urls.add(news.url)
                    unique_news.append(news)
            
            return {
                "news_data": [n.dict() for n in unique_news[:limit]],
                "total_count": len(unique_news)
            }
            
        except Exception as e:
            return {"error": f"Failed to collect news data: {str(e)}"}


class FreeEconomicDataTool(BaseTool):
    """Tool for collecting economic data from free sources."""
    
    name: str = "Free Economic Data Collector"
    description: str = "Collects comprehensive economic data from free sources including FRED and web scraping"
    
    def __init__(self, fred_api_key: Optional[str] = None):
        super().__init__()
        self.fred_api_key = fred_api_key or os.getenv('FRED_API_KEY', 'demo')
    
    def _run(self, country: str = "US", indicators: Optional[List[str]] = None) -> Dict[str, Any]:
        """Collect economic data from free sources."""
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
            
            # Use FRED API (free)
            for indicator in indicators:
                try:
                    base_url = "https://api.stlouisfed.org/fred"
                    
                    # Get series data
                    data_url = f"{base_url}/series/observations"
                    data_params = {
                        "series_id": indicator,
                        "api_key": self.fred_api_key,
                        "file_type": "json",
                        "observation_start": (datetime.now() - timedelta(days=365*2)).strftime('%Y-%m-%d'),
                        "observation_end": datetime.now().strftime('%Y-%m-%d')
                    }
                    
                    response = requests.get(data_url, params=data_params)
                    response.raise_for_status()
                    
                    data = response.json()
                    
                    # Get series info
                    info_url = f"{base_url}/series"
                    info_params = {
                        "series_id": indicator,
                        "api_key": self.fred_api_key,
                        "file_type": "json"
                    }
                    
                    info_response = requests.get(info_url, params=info_params)
                    info_response.raise_for_status()
                    
                    series_info = info_response.json()
                    
                    economic_data[indicator] = {
                        "data": data,
                        "info": series_info
                    }
                except Exception as e:
                    print(f"Failed to get {indicator}: {e}")
                    continue
            
            # Create EconomicData model
            gdp_data = economic_data.get("GDPC1", {}).get("data", {}).get("observations", [])
            cpi_data = economic_data.get("CPIAUCSL", {}).get("data", {}).get("observations", [])
            fed_funds_data = economic_data.get("FEDFUNDS", {}).get("data", {}).get("observations", [])
            unemployment_data = economic_data.get("UNRATE", {}).get("data", {}).get("observations", [])
            
            # Calculate growth rates
            gdp_growth = None
            if gdp_data and len(gdp_data) >= 2:
                gdp_values = [float(obs.get('value', 0)) for obs in gdp_data if obs.get('value') != '.']
                if len(gdp_values) >= 2:
                    gdp_growth = ((gdp_values[-1] - gdp_values[-2]) / gdp_values[-2] * 100)
            
            inflation_rate = None
            if cpi_data and len(cpi_data) >= 12:
                cpi_values = [float(obs.get('value', 0)) for obs in cpi_data if obs.get('value') != '.']
                if len(cpi_values) >= 12:
                    inflation_rate = ((cpi_values[-1] - cpi_values[-12]) / cpi_values[-12] * 100)
            
            interest_rate = None
            if fed_funds_data:
                fed_values = [float(obs.get('value', 0)) for obs in fed_funds_data if obs.get('value') != '.']
                if fed_values:
                    interest_rate = fed_values[-1]
            
            unemployment_rate = None
            if unemployment_data:
                unemp_values = [float(obs.get('value', 0)) for obs in unemployment_data if obs.get('value') != '.']
                if unemp_values:
                    unemployment_rate = unemp_values[-1]
            
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


class FreeWebSearchTool(BaseTool):
    """Tool for web search using free methods."""
    
    name: str = "Free Web Search Tool"
    description: str = "Performs web searches using free methods like DuckDuckGo and web scraping"
    
    def _run(self, query: str, num_results: int = 5) -> Dict[str, Any]:
        """Perform web search using free methods."""
        try:
            # Use DuckDuckGo search (free)
            search_url = "https://html.duckduckgo.com/html/"
            params = {
                "q": query,
                "kl": "us-en"
            }
            
            headers = {
                "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36"
            }
            
            response = requests.get(search_url, params=params, headers=headers)
            response.raise_for_status()
            
            soup = BeautifulSoup(response.content, 'html.parser')
            
            results = []
            search_results = soup.find_all('div', class_='result')
            
            for result in search_results[:num_results]:
                title_elem = result.find('a', class_='result__a')
                snippet_elem = result.find('a', class_='result__snippet')
                url_elem = result.find('a', class_='result__url')
                
                if title_elem:
                    title = title_elem.get_text(strip=True)
                    url = title_elem.get('href', '')
                    snippet = snippet_elem.get_text(strip=True) if snippet_elem else ""
                    
                    results.append({
                        "title": title,
                        "url": url,
                        "snippet": snippet
                    })
            
            return {
                "results": results,
                "query": query,
                "total_results": len(results)
            }
            
        except Exception as e:
            return {"error": f"Failed to perform web search: {str(e)}"}


class FreeCompetitorAnalysisTool(BaseTool):
    """Tool for competitor analysis using free data sources."""
    
    name: str = "Free Competitor Analysis Tool"
    description: str = "Analyzes competitors using free data sources like Yahoo Finance and web scraping"
    
    def _run(self, symbol: str, industry: Optional[str] = None) -> Dict[str, Any]:
        """Analyze competitors using free sources."""
        try:
            # Get company info first
            yahoo_tool = YahooFinanceTool()
            company_data = yahoo_tool._run(symbol)
            
            if "error" in company_data:
                return company_data
            
            company_info = company_data.get("company_info", {})
            sector = company_info.get("sector")
            industry = industry or company_info.get("industry")
            
            # Find competitors using web search
            search_tool = FreeWebSearchTool()
            search_query = f"{symbol} competitors {industry} {sector}"
            search_results = search_tool._run(search_query, num_results=10)
            
            competitors = []
            
            # Look for competitor mentions in search results
            for result in search_results.get("results", []):
                title = result.get("title", "")
                snippet = result.get("snippet", "")
                
                # Extract potential competitor symbols (simple heuristic)
                text = f"{title} {snippet}"
                potential_symbols = re.findall(r'\b[A-Z]{1,5}\b', text)
                
                for symbol_candidate in potential_symbols:
                    if (symbol_candidate != symbol and 
                        len(symbol_candidate) >= 2 and 
                        len(symbol_candidate) <= 5):
                        
                        # Verify it's a real stock by checking Yahoo Finance
                        try:
                            competitor_data = yahoo_tool._run(symbol_candidate)
                            if "error" not in competitor_data:
                                competitors.append({
                                    "symbol": symbol_candidate,
                                    "name": competitor_data.get("company_info", {}).get("name", symbol_candidate),
                                    "sector": competitor_data.get("company_info", {}).get("sector"),
                                    "industry": competitor_data.get("company_info", {}).get("industry"),
                                    "market_cap": competitor_data.get("market_data", {}).get("market_cap"),
                                    "current_price": competitor_data.get("market_data", {}).get("current_price")
                                })
                        except:
                            continue
            
            # Remove duplicates
            seen_symbols = set()
            unique_competitors = []
            for comp in competitors:
                if comp["symbol"] not in seen_symbols:
                    seen_symbols.add(comp["symbol"])
                    unique_competitors.append(comp)
            
            return {
                "competitors": unique_competitors[:10],  # Limit to top 10
                "industry": industry,
                "sector": sector,
                "total_found": len(unique_competitors)
            }
            
        except Exception as e:
            return {"error": f"Failed to analyze competitors: {str(e)}"}


class FreeIndustryAnalysisTool(BaseTool):
    """Tool for industry analysis using free data sources."""
    
    name: str = "Free Industry Analysis Tool"
    description: str = "Analyzes industry trends using free data sources"
    
    def _run(self, industry: str, sector: Optional[str] = None) -> Dict[str, Any]:
        """Analyze industry using free sources."""
        try:
            # Get industry data from web search
            search_tool = FreeWebSearchTool()
            search_query = f"{industry} sector analysis trends 2024"
            search_results = search_tool._run(search_query, num_results=10)
            
            # Get economic data
            economic_tool = FreeEconomicDataTool()
            economic_data = economic_tool._run()
            
            # Get news about the industry
            news_tool = FreeNewsTool()
            news_data = news_tool._run(industry, query=f"{industry} industry news")
            
            return {
                "industry": industry,
                "sector": sector,
                "search_results": search_results.get("results", []),
                "economic_context": economic_data.get("economic_data", {}),
                "news_sentiment": news_data.get("news_data", []),
                "analysis_timestamp": datetime.now().isoformat()
            }
            
        except Exception as e:
            return {"error": f"Failed to analyze industry: {str(e)}"}
