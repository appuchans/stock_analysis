"""Financial Modeling Prep client — the premium fundamentals/depth provider.

Requires ``FMP_API_KEY`` (config/settings.py); the router only ever
instantiates this class when that key is set, so every method here assumes a
key is present.

**Targets FMP's ``/stable`` API.** The older ``/api/v3`` and ``/api/v4``
endpoints this module used to call were retired on 2025-08-31 and now answer
403 "Legacy Endpoint" for any key issued after that date — meaning every
premium capability silently degraded to yfinance for new keys. ``/stable``
also moved the symbol from the URL path into a query parameter, so paths here
are bare resource names and ``symbol=`` is always passed as a param.

Tier note: several endpoints (insider trading, ETF holdings/sectors, earnings
transcripts) answer **402 Restricted** on the free tier. Those are reported as
a *capability gap* (``{}``) rather than a failure (``{"error": ...}``), which
is the distinction ``providers/base.py`` defines and the router relies on to
fall through to yfinance. A tier limit is not a malfunction.

All requests go through ``tools._http`` for pooling/retry/timeout; failures
degrade to ``{"error": ...}`` rather than raising, so a bad or expired key
never aborts a run.
"""

import logging
from datetime import date
from typing import Any, Dict, List, Optional

from .. import _http
from . import base

_logger = logging.getLogger(__name__)

_BASE_URL = "https://financialmodelingprep.com/stable"

# HTTP codes meaning "your key is fine, this data isn't included in your plan".
# Distinct from a real error: the router should quietly try the next provider.
_TIER_LIMITED = (402, 403)


class _NotInPlan(Exception):
    """Raised for a 402/403 so the caller can return {} (capability gap)."""


class FMPProvider(base.ProviderBase):
    name = "fmp"

    def __init__(self, api_key: str) -> None:
        self._api_key = api_key

    def _get(self, path: str, **params: Any) -> Any:
        params["apikey"] = self._api_key
        resp = _http.get(f"{_BASE_URL}/{path}", params=params, timeout=15)
        if resp.status_code in _TIER_LIMITED:
            raise _NotInPlan(f"{path} not available on this FMP plan")
        resp.raise_for_status()
        return resp.json()

    def get_quote(self, symbol: str) -> Dict[str, Any]:
        try:
            data = self._get("quote", symbol=symbol)
            if not data:
                return {}
            q = data[0]
            return {
                "symbol": symbol,
                "price": q.get("price"),
                "previous_close": q.get("previousClose"),
                "change_pct": q.get("changePercentage"),
                "volume": q.get("volume"),
                "market_cap": q.get("marketCap"),
                "pe_ratio": q.get("pe"),
                "source": self.name,
            }
        except _NotInPlan:
            return {}
        except Exception as exc:
            _logger.warning("FMP get_quote failed for %s: %s", symbol, exc)
            return {"error": str(exc)}

    def get_daily_bars(self, symbol: str, start: str, end: str) -> Dict[str, Any]:
        try:
            rows = self._get(
                "historical-price-eod/full",
                symbol=symbol,
                **{"from": start, "to": end},
            )
            if not rows:
                return {}
            # /stable returns a flat newest-first list (v3 wrapped it in
            # {"historical": [...]}). Sort rather than reverse so a future
            # ordering change can't silently invert every chart.
            bars = [
                {
                    "date": r.get("date"),
                    "open": r.get("open"),
                    "high": r.get("high"),
                    "low": r.get("low"),
                    "close": r.get("close"),
                    "volume": r.get("volume"),
                }
                for r in sorted(rows, key=lambda r: r.get("date") or "")
            ]
            return {"symbol": symbol, "bars": bars, "source": self.name}
        except _NotInPlan:
            return {}
        except Exception as exc:
            _logger.warning("FMP get_daily_bars failed for %s: %s", symbol, exc)
            return {"error": str(exc)}

    def get_statements(self, symbol: str, years: int = 10) -> Dict[str, Any]:
        try:
            income = self._get(
                "income-statement", symbol=symbol, period="annual", limit=years
            )
            balance = self._get(
                "balance-sheet-statement", symbol=symbol, period="annual", limit=years
            )
            cashflow = self._get(
                "cash-flow-statement", symbol=symbol, period="annual", limit=years
            )
            if not (income or balance or cashflow):
                return {}
            return {
                "symbol": symbol,
                "years_available": len(income or []),
                "income_statement": [
                    {
                        # /stable renamed calendarYear -> fiscalYear.
                        "fiscal_year": r.get("fiscalYear"),
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
                        "fiscal_year": r.get("fiscalYear"),
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
                        "fiscal_year": r.get("fiscalYear"),
                        "operating_cash_flow": r.get("operatingCashFlow"),
                        "free_cash_flow": r.get("freeCashFlow"),
                        "capital_expenditure": r.get("capitalExpenditure"),
                    }
                    for r in (cashflow or [])
                ],
                "source": self.name,
            }
        except _NotInPlan:
            return {}
        except Exception as exc:
            _logger.warning("FMP get_statements failed for %s: %s", symbol, exc)
            return {"error": str(exc)}

    def get_revenue_segments(self, symbol: str) -> Dict[str, Any]:
        """Revenue split by product line and by geography.

        This is the one breakdown neither yfinance nor the SEC's companyfacts
        API exposes (companyfacts carries only consolidated, non-dimensional
        facts), so it has no keyless fallback — absent an FMP key the report
        simply has no segment section.
        """
        try:
            product = self._get("revenue-product-segmentation", symbol=symbol)
            geographic = self._get("revenue-geographic-segmentation", symbol=symbol)
            if not (product or geographic):
                return {}

            def _series(rows: Any) -> List[Dict[str, Any]]:
                out: List[Dict[str, Any]] = []
                # Newest first, and only the last few years — this feeds an LLM
                # prompt and a chart, neither of which wants 16 years of detail.
                for r in sorted(
                    rows or [], key=lambda r: r.get("fiscalYear") or 0, reverse=True
                )[:4]:
                    breakdown = r.get("data") or {}
                    if not isinstance(breakdown, dict) or not breakdown:
                        continue
                    total = sum(v for v in breakdown.values() if isinstance(v, (int, float)))
                    out.append(
                        {
                            "fiscal_year": r.get("fiscalYear"),
                            "period_end": r.get("date"),
                            "currency": r.get("reportedCurrency"),
                            "total": total or None,
                            "segments": {
                                k: {
                                    "revenue": v,
                                    "pct_of_total": (
                                        round(v / total * 100, 1)
                                        if total and isinstance(v, (int, float))
                                        else None
                                    ),
                                }
                                for k, v in sorted(
                                    breakdown.items(),
                                    key=lambda kv: kv[1]
                                    if isinstance(kv[1], (int, float))
                                    else 0,
                                    reverse=True,
                                )
                            },
                        }
                    )
                return out

            result: Dict[str, Any] = {"symbol": symbol, "source": self.name}
            by_product = _series(product)
            by_geography = _series(geographic)
            if by_product:
                result["by_product"] = by_product
            if by_geography:
                result["by_geography"] = by_geography
            return result if (by_product or by_geography) else {}
        except _NotInPlan:
            return {}
        except Exception as exc:
            _logger.warning("FMP get_revenue_segments failed for %s: %s", symbol, exc)
            return {"error": str(exc)}

    def get_peers(self, symbol: str) -> Dict[str, Any]:
        """Comparable companies with price and market cap already attached."""
        try:
            rows = self._get("stock-peers", symbol=symbol) or []
            peers = [
                {
                    "symbol": r.get("symbol"),
                    "name": r.get("companyName"),
                    "price": r.get("price"),
                    "market_cap": r.get("mktCap"),
                }
                for r in rows
                if (r.get("symbol") or "").upper() != symbol.upper()
            ]
            if not peers:
                return {}
            # Largest first: a comparables table is read against the biggest
            # names in the group, not in whatever order the API returned.
            peers.sort(key=lambda p: p.get("market_cap") or 0, reverse=True)
            return {"symbol": symbol, "peers": peers[:10], "source": self.name}
        except _NotInPlan:
            return {}
        except Exception as exc:
            _logger.warning("FMP get_peers failed for %s: %s", symbol, exc)
            return {"error": str(exc)}

    def get_shareholder_returns(self, symbol: str) -> Dict[str, Any]:
        """Dividends, buybacks and the yields they imply.

        Answers "what is management doing with the cash?" — the question the
        ownership and capital-allocation section is built around, and one the
        reports repeatedly flagged as uncomputable.
        """
        # Each sub-call is tolerated independently: these three endpoints sit on
        # different FMP tiers, and `dividends` in particular answers 402 on the
        # free plan. A shared try-block would have thrown away the yields that
        # key-metrics and ratios return perfectly well.
        def _maybe(path: str, **params: Any) -> Any:
            try:
                return self._get(path, **params) or []
            except Exception:
                return []

        try:
            metrics = _maybe("key-metrics", symbol=symbol, limit=1)
            ratios = _maybe("ratios", symbol=symbol, limit=1)
            dividends = _maybe("dividends", symbol=symbol, limit=8)
            if not (metrics or ratios or dividends):
                return {}

            m = metrics[0] if metrics else {}
            r = ratios[0] if ratios else {}

            def _pct(v: Any) -> Optional[float]:
                # FMP returns these as fractions; the report speaks in percent.
                try:
                    return round(float(v) * 100, 2)
                except (TypeError, ValueError):
                    return None

            out: Dict[str, Any] = {
                "symbol": symbol,
                "fiscal_year": m.get("fiscalYear") or r.get("fiscalYear"),
                "dividend_yield_pct": _pct(
                    r.get("dividendYield") or m.get("dividendYield")
                ),
                "payout_ratio_pct": _pct(r.get("dividendPayoutRatio")),
                "free_cash_flow_yield_pct": _pct(m.get("freeCashFlowYield")),
                "earnings_yield_pct": _pct(m.get("earningsYield")),
                "source": self.name,
            }
            if dividends:
                out["recent_dividends"] = [
                    {
                        "date": d.get("date"),
                        "payment_date": d.get("paymentDate"),
                        "amount": d.get("adjDividend") or d.get("dividend"),
                        "frequency": d.get("frequency"),
                    }
                    for d in dividends[:8]
                ]
            # Drop keys with nothing in them so a sparse payload does not read
            # as a full one with zeros.
            populated = {
                k: v for k, v in out.items() if v not in (None, [], "")
            }
            return populated if len(populated) > 2 else {}
        except _NotInPlan:
            return {}
        except Exception as exc:
            _logger.warning(
                "FMP get_shareholder_returns failed for %s: %s", symbol, exc
            )
            return {"error": str(exc)}

    def get_estimates(self, symbol: str) -> Dict[str, Any]:
        try:
            data = self._get(
                "analyst-estimates", symbol=symbol, period="annual", limit=8
            )
            if not data:
                return {}
            revisions = [
                {
                    "fiscal_year": r.get("date"),
                    # /stable flattened estimatedEpsAvg -> epsAvg, etc.
                    "eps_avg": r.get("epsAvg"),
                    "eps_low": r.get("epsLow"),
                    "eps_high": r.get("epsHigh"),
                    "revenue_avg": r.get("revenueAvg"),
                    "num_analysts_eps": r.get("numAnalystsEps"),
                }
                for r in data
            ]
            return {
                "symbol": symbol,
                "estimate_revisions": revisions,
                "source": self.name,
            }
        except _NotInPlan:
            return {}
        except Exception as exc:
            _logger.warning("FMP get_estimates failed for %s: %s", symbol, exc)
            return {"error": str(exc)}

    def get_transcript(self, symbol: str) -> Dict[str, Any]:
        try:
            latest = self._get("earning-call-transcript-latest", symbol=symbol)
            if not latest:
                return {}
            row = latest[0]
            content = row.get("content") or ""
            if not content:
                return {}
            return {
                "symbol": symbol,
                "year": row.get("fiscalYear") or row.get("year"),
                "quarter": row.get("period") or row.get("quarter"),
                "date": row.get("date"),
                # Full transcripts run tens of thousands of characters — cap
                # what gets carried into an LLM prompt.
                "content_excerpt": content[:6000],
                "source": self.name,
            }
        except _NotInPlan:
            return {}
        except Exception as exc:
            _logger.warning("FMP get_transcript failed for %s: %s", symbol, exc)
            return {"error": str(exc)}

    def get_insider_trades(self, symbol: str) -> Dict[str, Any]:
        try:
            data = self._get("insider-trading/search", symbol=symbol, limit=25)
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
        except _NotInPlan:
            return {}
        except Exception as exc:
            _logger.warning("FMP get_insider_trades failed for %s: %s", symbol, exc)
            return {"error": str(exc)}

    def get_calendar(self, symbol: str) -> Dict[str, Any]:
        try:
            earnings = self._get("earnings", symbol=symbol, limit=40)
            next_earnings: Optional[Dict[str, Any]] = None
            today = date.today().isoformat()
            # Newest-first; walk forward in time to the nearest future date.
            for r in sorted(earnings or [], key=lambda r: r.get("date") or ""):
                if (r.get("date") or "") >= today:
                    next_earnings = {
                        "date": r.get("date"),
                        "eps_estimated": r.get("epsEstimated"),
                        "revenue_estimated": r.get("revenueEstimated"),
                    }
                    break
            if not next_earnings:
                return {}
            return {"symbol": symbol, "next_earnings": next_earnings, "source": self.name}
        except _NotInPlan:
            return {}
        except Exception as exc:
            _logger.warning("FMP get_calendar failed for %s: %s", symbol, exc)
            return {"error": str(exc)}

    def get_etf_holdings(self, symbol: str) -> Dict[str, Any]:
        try:
            holdings = self._get("etf/holdings", symbol=symbol)
            sectors = self._get("etf/sector-weightings", symbol=symbol)
            if not (holdings or sectors):
                return {}
            return {
                "symbol": symbol,
                "top_holdings": [
                    {"name": r.get("name") or r.get("asset"), "weight_pct": r.get("weightPercentage")}
                    for r in (holdings or [])[:10]
                ],
                "sector_weightings_pct": {
                    r.get("sector"): r.get("weightPercentage") for r in (sectors or [])
                },
                "source": self.name,
            }
        except _NotInPlan:
            return {}
        except Exception as exc:
            _logger.warning("FMP get_etf_holdings failed for %s: %s", symbol, exc)
            return {"error": str(exc)}


def screener(**criteria: Any) -> List[Dict[str, Any]]:
    """Module-level (not per-symbol) screener query.

    ``criteria`` maps onto FMP's company-screener query params, e.g.
    marketCapMoreThan, sector, peRatioLessThan, volumeMoreThan.
    """
    from ...config.settings import settings

    if not settings.fmp_api_key:
        return []
    try:
        params = dict(criteria)
        params["apikey"] = settings.fmp_api_key
        resp = _http.get(f"{_BASE_URL}/company-screener", params=params, timeout=15)
        if resp.status_code in _TIER_LIMITED:
            return []
        resp.raise_for_status()
        return resp.json() or []
    except Exception as exc:
        _logger.warning("FMP screener failed: %s", exc)
        return []
