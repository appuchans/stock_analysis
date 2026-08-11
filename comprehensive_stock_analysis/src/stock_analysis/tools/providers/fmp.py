"""Financial Modeling Prep client — the premium fundamentals/depth provider.

Requires ``FMP_API_KEY`` (config/settings.py); the router only ever
instantiates this class when that key is set, so every method here assumes a
key is present. Targets FMP's v3 REST API (financialmodelingprep.com/api/v3).
All requests go through ``tools._http`` for pooling/retry/timeout, matching
every other tool in this codebase; failures degrade to ``{"error": ...}``
rather than raising, so a bad/expired key never aborts a run — the router
just falls through to the yfinance provider.
"""

import logging
from datetime import date
from typing import Any, Dict, List, Optional

from .. import _http
from . import base

_logger = logging.getLogger(__name__)

_BASE_URL = "https://financialmodelingprep.com/api/v3"


class FMPProvider(base.ProviderBase):
    name = "fmp"

    def __init__(self, api_key: str) -> None:
        self._api_key = api_key

    def _get(self, path: str, **params: Any) -> Any:
        params["apikey"] = self._api_key
        resp = _http.get(f"{_BASE_URL}/{path}", params=params, timeout=15)
        resp.raise_for_status()
        return resp.json()

    def get_quote(self, symbol: str) -> Dict[str, Any]:
        try:
            data = self._get(f"quote/{symbol}")
            if not data:
                return {}
            q = data[0]
            return {
                "symbol": symbol,
                "price": q.get("price"),
                "previous_close": q.get("previousClose"),
                "change_pct": q.get("changesPercentage"),
                "volume": q.get("volume"),
                "market_cap": q.get("marketCap"),
                "pe_ratio": q.get("pe"),
                "source": self.name,
            }
        except Exception as exc:
            _logger.warning("FMP get_quote failed for %s: %s", symbol, exc)
            return {"error": str(exc)}

    def get_daily_bars(self, symbol: str, start: str, end: str) -> Dict[str, Any]:
        try:
            data = self._get(
                f"historical-price-full/{symbol}", **{"from": start, "to": end}
            )
            rows = (data or {}).get("historical") or []
            bars = [
                {
                    "date": r.get("date"),
                    "open": r.get("open"),
                    "high": r.get("high"),
                    "low": r.get("low"),
                    "close": r.get("close"),
                    "volume": r.get("volume"),
                }
                for r in reversed(rows)  # FMP returns newest-first
            ]
            return {"symbol": symbol, "bars": bars, "source": self.name} if bars else {}
        except Exception as exc:
            _logger.warning("FMP get_daily_bars failed for %s: %s", symbol, exc)
            return {"error": str(exc)}

    def get_statements(self, symbol: str, years: int = 10) -> Dict[str, Any]:
        try:
            income = self._get(
                f"income-statement/{symbol}", period="annual", limit=years
            )
            balance = self._get(
                f"balance-sheet-statement/{symbol}", period="annual", limit=years
            )
            cashflow = self._get(
                f"cash-flow-statement/{symbol}", period="annual", limit=years
            )
            if not (income or balance or cashflow):
                return {}
            return {
                "symbol": symbol,
                "years_available": len(income or []),
                "income_statement": [
                    {
                        "fiscal_year": r.get("calendarYear"),
                        "revenue": r.get("revenue"),
                        "net_income": r.get("netIncome"),
                        "eps": r.get("eps"),
                        "operating_income": r.get("operatingIncome"),
                        "gross_profit": r.get("grossProfit"),
                    }
                    for r in (income or [])
                ],
                "balance_sheet": [
                    {
                        "fiscal_year": r.get("calendarYear"),
                        "total_assets": r.get("totalAssets"),
                        "total_liabilities": r.get("totalLiabilities"),
                        "total_equity": r.get("totalStockholdersEquity"),
                        "cash_and_equivalents": r.get("cashAndCashEquivalents"),
                        "total_debt": r.get("totalDebt"),
                    }
                    for r in (balance or [])
                ],
                "cash_flow": [
                    {
                        "fiscal_year": r.get("calendarYear"),
                        "operating_cash_flow": r.get("operatingCashFlow"),
                        "free_cash_flow": r.get("freeCashFlow"),
                        "capital_expenditure": r.get("capitalExpenditure"),
                    }
                    for r in (cashflow or [])
                ],
                "source": self.name,
            }
        except Exception as exc:
            _logger.warning("FMP get_statements failed for %s: %s", symbol, exc)
            return {"error": str(exc)}

    def get_estimates(self, symbol: str) -> Dict[str, Any]:
        try:
            data = self._get(f"analyst-estimates/{symbol}", period="annual", limit=8)
            if not data:
                return {}
            revisions = [
                {
                    "fiscal_year": r.get("date"),
                    "eps_avg": r.get("estimatedEpsAvg"),
                    "eps_low": r.get("estimatedEpsLow"),
                    "eps_high": r.get("estimatedEpsHigh"),
                    "revenue_avg": r.get("estimatedRevenueAvg"),
                    "num_analysts_eps": r.get("numberAnalystEstimatedEps"),
                }
                for r in data
            ]
            return {
                "symbol": symbol,
                "estimate_revisions": revisions,
                "source": self.name,
            }
        except Exception as exc:
            _logger.warning("FMP get_estimates failed for %s: %s", symbol, exc)
            return {"error": str(exc)}

    def get_transcript(self, symbol: str) -> Dict[str, Any]:
        try:
            # Undated call returns the list of available (year, quarter) —
            # not the transcript text itself.
            available = self._get(f"earning_call_transcript/{symbol}")
            if not available:
                return {}
            latest = available[0]
            year, quarter = latest.get("year"), latest.get("quarter")
            if year is None or quarter is None:
                return {}
            full = self._get(
                f"earning_call_transcript/{symbol}", year=year, quarter=quarter
            )
            if not full:
                return {}
            content = full[0].get("content") or ""
            return {
                "symbol": symbol,
                "year": year,
                "quarter": quarter,
                "date": full[0].get("date"),
                # Full transcripts run tens of thousands of characters — cap
                # what gets carried into an LLM prompt (report_tools' report
                # sections already treat callers' truncation as their job).
                "content_excerpt": content[:6000],
                "source": self.name,
            }
        except Exception as exc:
            _logger.warning("FMP get_transcript failed for %s: %s", symbol, exc)
            return {"error": str(exc)}

    def get_insider_trades(self, symbol: str) -> Dict[str, Any]:
        try:
            data = self._get("insider-trading", symbol=symbol, limit=25)
            if not data:
                return {}
            trades = [
                {
                    "reporting_name": r.get("reportingName"),
                    "transaction_date": r.get("transactionDate"),
                    "transaction_type": r.get("transactionType"),
                    "shares": r.get("securitiesTransacted"),
                    "price": r.get("price"),
                }
                for r in data
            ]
            return {"symbol": symbol, "insider_trades": trades, "source": self.name}
        except Exception as exc:
            _logger.warning("FMP get_insider_trades failed for %s: %s", symbol, exc)
            return {"error": str(exc)}

    def get_calendar(self, symbol: str) -> Dict[str, Any]:
        try:
            earnings = self._get(f"historical/earning_calendar/{symbol}")
            next_earnings: Optional[Dict[str, Any]] = None
            today = date.today().isoformat()
            for r in reversed(
                earnings or []
            ):  # oldest-first -> walk to find next future date
                if (r.get("date") or "") >= today:
                    next_earnings = {
                        "date": r.get("date"),
                        "time": r.get("time"),
                        "eps_estimated": r.get("epsEstimated"),
                        "revenue_estimated": r.get("revenueEstimated"),
                    }
                    break
            result: Dict[str, Any] = {"symbol": symbol, "source": self.name}
            if next_earnings:
                result["next_earnings"] = next_earnings
            return result if next_earnings else {}
        except Exception as exc:
            _logger.warning("FMP get_calendar failed for %s: %s", symbol, exc)
            return {"error": str(exc)}

    def get_etf_holdings(self, symbol: str) -> Dict[str, Any]:
        try:
            holdings = self._get(f"etf-holder/{symbol}")
            sectors = self._get(f"etf-sector-weightings/{symbol}")
            if not (holdings or sectors):
                return {}
            return {
                "symbol": symbol,
                "top_holdings": [
                    {"name": r.get("asset"), "weight_pct": r.get("weightPercentage")}
                    for r in (holdings or [])[:10]
                ],
                "sector_weightings_pct": {
                    r.get("sector"): r.get("weightPercentage") for r in (sectors or [])
                },
                "source": self.name,
            }
        except Exception as exc:
            _logger.warning("FMP get_etf_holdings failed for %s: %s", symbol, exc)
            return {"error": str(exc)}


def screener(**criteria: Any) -> List[Dict[str, Any]]:
    """Module-level (not per-symbol) screener query — used by the Phase 5
    screener view. Kept separate from the MarketDataProvider protocol since
    it isn't a per-symbol capability.

    ``criteria`` maps directly onto FMP's /stock-screener query params, e.g.
    marketCapMoreThan, sector, peRatioLessThan, volumeMoreThan.
    """
    from ...config.settings import settings

    if not settings.fmp_api_key:
        return []
    try:
        params = dict(criteria)
        params["apikey"] = settings.fmp_api_key
        resp = _http.get(f"{_BASE_URL}/stock-screener", params=params, timeout=15)
        resp.raise_for_status()
        return resp.json() or []
    except Exception as exc:
        _logger.warning("FMP screener failed: %s", exc)
        return []
