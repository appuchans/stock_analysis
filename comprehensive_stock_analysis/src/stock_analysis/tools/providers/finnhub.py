"""Finnhub client — analyst trends, earnings surprises, insider sentiment, news.

Requires ``FINNHUB_API_KEY``; the router only constructs this provider when the
key is set.

What it adds that nothing else in the chain covers:

* **Recommendation trends** — the buy/hold/sell analyst mix by month. yfinance
  supplies this only patchily and FMP's free tier does not, yet it is the
  headline of the sentiment stage's "professional view" section.
* **Earnings surprises** — actual vs. estimated EPS per quarter, which is what
  the fundamental stage's "did management deliver?" question needs. Previously
  that came from whatever the data-collection LLM happened to transcribe.
* **Insider sentiment (MSPR)** — a monthly aggregate that complements the
  individual Form 4 filings from sec-api.io: one gives the transactions, the
  other the trend.
* **Company news** — structured, dated, source-attributed. The keyless path
  scrapes Google/Bing/Yahoo RSS, which breaks silently when a layout changes.

Every method degrades to ``{}`` (capability gap) or ``{"error": ...}`` like the
other providers, so a missing key or an outage never aborts a run.
"""

import logging
from datetime import date, timedelta
from typing import Any, Dict, List

from .. import _http
from . import base

_logger = logging.getLogger(__name__)

_BASE_URL = "https://finnhub.io/api/v1"

# Finnhub answers 401/403 for a bad key and 429 when the free minute-rate is
# exceeded. None of those are "this data does not exist", but for the router's
# purposes they all mean "try the next provider", and a rate limit in
# particular must not surface as a scary error in a client-facing report.
_SOFT_FAIL = (401, 403, 429)


class _Unavailable(Exception):
    """Key rejected or rate limited — caller returns {} (capability gap)."""


class FinnhubProvider(base.ProviderBase):
    name = "finnhub"

    def __init__(self, api_key: str) -> None:
        self._api_key = api_key

    def _get(self, path: str, **params: Any) -> Any:
        params["token"] = self._api_key
        resp = _http.get(f"{_BASE_URL}/{path}", params=params, timeout=15)
        if resp.status_code in _SOFT_FAIL:
            raise _Unavailable(f"{path}: HTTP {resp.status_code}")
        resp.raise_for_status()
        return resp.json()

    def get_quote(self, symbol: str) -> Dict[str, Any]:
        try:
            q = self._get("quote", symbol=symbol) or {}
            # Finnhub returns a 200 with all-zero fields for unknown symbols.
            if not q.get("c"):
                return {}
            return {
                "symbol": symbol,
                "price": q.get("c"),
                "previous_close": q.get("pc"),
                "change_pct": q.get("dp"),
                "day_high": q.get("h"),
                "day_low": q.get("l"),
                "source": self.name,
            }
        except _Unavailable:
            return {}
        except Exception as exc:
            _logger.warning("Finnhub get_quote failed for %s: %s", symbol, exc)
            return {"error": str(exc)}

    def get_recommendation_trends(self, symbol: str) -> Dict[str, Any]:
        """Analyst buy/hold/sell mix, newest period first."""
        try:
            rows = self._get("stock/recommendation", symbol=symbol) or []
            if not rows:
                return {}
            trend: List[Dict[str, Any]] = []
            for r in sorted(rows, key=lambda r: r.get("period") or "", reverse=True)[:6]:
                strong_buy = r.get("strongBuy") or 0
                buy = r.get("buy") or 0
                hold = r.get("hold") or 0
                sell = r.get("sell") or 0
                strong_sell = r.get("strongSell") or 0
                total = strong_buy + buy + hold + sell + strong_sell
                trend.append(
                    {
                        "period": r.get("period"),
                        "strong_buy": strong_buy,
                        "buy": buy,
                        "hold": hold,
                        "sell": sell,
                        "strong_sell": strong_sell,
                        "total_analysts": total,
                        # Share of analysts positive — the single number the
                        # sentiment stage actually reasons about.
                        "bullish_pct": (
                            round((strong_buy + buy) / total * 100, 1) if total else None
                        ),
                    }
                )
            return {"symbol": symbol, "recommendation_trend": trend, "source": self.name}
        except _Unavailable:
            return {}
        except Exception as exc:
            _logger.warning(
                "Finnhub get_recommendation_trends failed for %s: %s", symbol, exc
            )
            return {"error": str(exc)}

    def get_earnings_surprises(self, symbol: str) -> Dict[str, Any]:
        """Actual vs estimated EPS by quarter — the execution track record."""
        try:
            rows = self._get("stock/earnings", symbol=symbol) or []
            if not rows:
                return {}
            quarters = [
                {
                    "period": r.get("period"),
                    "fiscal_year": r.get("year"),
                    "fiscal_quarter": r.get("quarter"),
                    "eps_actual": r.get("actual"),
                    "eps_estimate": r.get("estimate"),
                    "surprise": r.get("surprise"),
                    "surprise_pct": r.get("surprisePercent"),
                    "beat": (
                        None
                        if r.get("surprise") is None
                        else bool(r.get("surprise") > 0)
                    ),
                }
                for r in sorted(
                    rows, key=lambda r: r.get("period") or "", reverse=True
                )[:8]
            ]
            scored = [q for q in quarters if q["beat"] is not None]
            return {
                "symbol": symbol,
                "quarters": quarters,
                "beats": sum(1 for q in scored if q["beat"]),
                "misses": sum(1 for q in scored if not q["beat"]),
                "source": self.name,
            }
        except _Unavailable:
            return {}
        except Exception as exc:
            _logger.warning(
                "Finnhub get_earnings_surprises failed for %s: %s", symbol, exc
            )
            return {"error": str(exc)}

    def get_insider_sentiment(self, symbol: str, months: int = 12) -> Dict[str, Any]:
        """Monthly insider sentiment (MSPR, -100..100) and net share change."""
        try:
            end = date.today()
            start = end - timedelta(days=31 * months)
            payload = self._get(
                "stock/insider-sentiment",
                symbol=symbol,
                **{"from": start.isoformat(), "to": end.isoformat()},
            )
            rows = (payload or {}).get("data") or []
            if not rows:
                return {}
            months_out = [
                {
                    "year": r.get("year"),
                    "month": r.get("month"),
                    "net_share_change": r.get("change"),
                    # Monthly Share Purchase Ratio: positive = net accumulation.
                    "mspr": round(r["mspr"], 1) if r.get("mspr") is not None else None,
                }
                for r in sorted(
                    rows, key=lambda r: (r.get("year") or 0, r.get("month") or 0)
                )
            ]
            net = sum(m["net_share_change"] or 0 for m in months_out)
            return {
                "symbol": symbol,
                "months": months_out[-12:],
                "net_share_change_total": net,
                "source": self.name,
            }
        except _Unavailable:
            return {}
        except Exception as exc:
            _logger.warning(
                "Finnhub get_insider_sentiment failed for %s: %s", symbol, exc
            )
            return {"error": str(exc)}

    def get_peers(self, symbol: str) -> Dict[str, Any]:
        """Comparable companies, as Finnhub groups them by sub-industry."""
        try:
            rows = self._get("stock/peers", symbol=symbol) or []
            # The subject company is included in its own peer list; drop it so
            # callers never compare a company against itself.
            peers = [p for p in rows if isinstance(p, str) and p.upper() != symbol.upper()]
            if not peers:
                return {}
            return {"symbol": symbol, "peers": peers[:10], "source": self.name}
        except _Unavailable:
            return {}
        except Exception as exc:
            _logger.warning("Finnhub get_peers failed for %s: %s", symbol, exc)
            return {"error": str(exc)}

    def get_company_news(self, symbol: str, days: int = 14) -> Dict[str, Any]:
        try:
            end = date.today()
            start = end - timedelta(days=days)
            rows = (
                self._get(
                    "company-news",
                    symbol=symbol,
                    **{"from": start.isoformat(), "to": end.isoformat()},
                )
                or []
            )
            if not rows:
                return {}
            from datetime import datetime as _dt

            items = []
            for r in sorted(
                rows, key=lambda r: r.get("datetime") or 0, reverse=True
            )[:15]:
                ts = r.get("datetime")
                items.append(
                    {
                        "headline": r.get("headline"),
                        "summary": (r.get("summary") or "")[:400],
                        "source": r.get("source"),
                        "url": r.get("url"),
                        "published_at": (
                            _dt.fromtimestamp(ts).isoformat(timespec="seconds")
                            if ts
                            else None
                        ),
                    }
                )
            return {"symbol": symbol, "news": items, "source": self.name}
        except _Unavailable:
            return {}
        except Exception as exc:
            _logger.warning("Finnhub get_company_news failed for %s: %s", symbol, exc)
            return {"error": str(exc)}
