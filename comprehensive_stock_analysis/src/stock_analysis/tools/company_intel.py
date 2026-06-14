"""Focused company-intelligence tools backed by free Yahoo Finance data.

Thin CrewAI tool wrappers around the compact summarizers in yf_summaries.py.
All results are Redis-cached (graceful no-op without Redis) to minimize API calls.
"""

from datetime import datetime
from typing import Any, Dict

import yfinance as yf
from crewai.tools import BaseTool

from .cache import cached_tool
from .yf_summaries import (
    summarize_analyst_data,
    summarize_dividends_splits,
    summarize_etf_portfolio,
    summarize_financial_statements,
    summarize_options_sentiment,
    summarize_ownership,
)


def _envelope(symbol: str, payload: Dict[str, Any]) -> Dict[str, Any]:
    return {
        "symbol": symbol.upper(),
        **payload,
        "source": "yahoo_finance",
        "as_of": datetime.now().isoformat(timespec="minutes"),
    }


class AnalystDataTool(BaseTool):
    """Analyst consensus: price targets, rating trend, upgrades/downgrades, estimates."""

    name: str = "Analyst Consensus and Estimates"
    description: str = (
        "Returns Wall Street analyst data for a symbol: price targets (low/mean/high "
        "and implied upside), buy/hold/sell recommendation trend, recent upgrades and "
        "downgrades with firms and targets, EPS/revenue estimates and 30-day estimate "
        "revisions. Free Yahoo Finance data."
    )

    @cached_tool(ttl=43200)
    def _run(self, symbol: str) -> Dict[str, Any]:
        try:
            return _envelope(symbol, summarize_analyst_data(yf.Ticker(symbol)))
        except Exception as exc:
            return {"error": f"Analyst data collection failed: {exc}"}


class OwnershipTool(BaseTool):
    """Insider transactions and institutional ownership."""

    name: str = "Insider and Institutional Ownership"
    description: str = (
        "Returns ownership data for a symbol: insider vs institutional percentage held, "
        "top institutional holders, and recent insider transactions with a buy/sell "
        "summary. Free Yahoo Finance data."
    )

    @cached_tool(ttl=43200)
    def _run(self, symbol: str) -> Dict[str, Any]:
        try:
            return _envelope(symbol, summarize_ownership(yf.Ticker(symbol)))
        except Exception as exc:
            return {"error": f"Ownership data collection failed: {exc}"}


class FinancialStatementsTool(BaseTool):
    """Annual income statement, balance sheet, and cash flow summary."""

    name: str = "Financial Statements Summary"
    description: str = (
        "Returns a compact summary of the last 3 fiscal years: revenue, gross/operating/"
        "net income with YoY growth, total assets, cash, debt, equity, operating cash "
        "flow, capex, free cash flow, buybacks, and dividends paid (all in USD millions). "
        "Free Yahoo Finance data."
    )

    @cached_tool(ttl=86400)
    def _run(self, symbol: str) -> Dict[str, Any]:
        try:
            ticker = yf.Ticker(symbol)
            payload = summarize_financial_statements(ticker)
            payload.update(summarize_dividends_splits(ticker))
            return _envelope(symbol, payload)
        except Exception as exc:
            return {"error": f"Financial statements collection failed: {exc}"}


class OptionsSentimentTool(BaseTool):
    """Options-market positioning: put/call ratios and ATM implied volatility."""

    name: str = "Options Market Sentiment"
    description: str = (
        "Returns options-derived sentiment for a symbol: put/call open-interest and "
        "volume ratios and at-the-money implied volatility for a 2-6 week expiry. "
        "Low put/call ratio (<0.7) suggests bullish positioning; high (>1.0) bearish. "
        "Returns available=false for assets without listed options."
    )

    @cached_tool(ttl=3600)
    def _run(self, symbol: str) -> Dict[str, Any]:
        try:
            return _envelope(symbol, summarize_options_sentiment(yf.Ticker(symbol)))
        except Exception as exc:
            return {"error": f"Options sentiment collection failed: {exc}"}


class ETFPortfolioTool(BaseTool):
    """ETF portfolio composition: sectors, asset classes, top holdings."""

    name: str = "ETF Portfolio Composition"
    description: str = (
        "Returns ETF/fund portfolio data: sector weightings, asset-class split, and "
        "top-10 holdings with weights. Use only for ETFs and funds."
    )

    @cached_tool(ttl=86400)
    def _run(self, symbol: str) -> Dict[str, Any]:
        try:
            return _envelope(symbol, summarize_etf_portfolio(yf.Ticker(symbol)))
        except Exception as exc:
            return {"error": f"ETF portfolio collection failed: {exc}"}
