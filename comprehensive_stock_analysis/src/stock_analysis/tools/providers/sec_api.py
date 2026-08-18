"""sec-api.io client — structured access to SEC filings.

Requires ``SEC_API_KEY``; the router only constructs this provider when the
key is set, so every method assumes one is present.

Why this exists alongside the keyless EDGAR path in ``free_data_collection``:
EDGAR serves filings as HTML that has to be scraped (``_sec_extract_section``
hunts for section headings in markup that changes between filers and years),
and its ``companyfacts`` API exposes only consolidated, non-dimensional facts.
sec-api.io returns the same filings already parsed — Form 4 transactions as
JSON, and named 10-K/10-Q items as clean text. The keyless path stays as the
fallback, so nothing here is required for the app to work.

Two capabilities are covered:

* ``get_insider_trades`` — Form 4 transactions. This is the gap FMP's free
  tier leaves (its insider endpoint answers 402), so with this key configured
  insider analysis stops falling back to thin yfinance aggregates.
* ``get_filing_sections`` — Item 1 (Business), 1A (Risk Factors) and 7 (MD&A)
  from the latest 10-K, which is what the fundamental and risk stages want and
  currently approximate by scraping.

Failures degrade to ``{}``/``{"error": ...}`` like every other provider; a bad
key or an outage never aborts a run.
"""

import html
import logging
import re
from typing import Any, Dict, List, Optional

from .. import _http
from . import base

_logger = logging.getLogger(__name__)

_QUERY_URL = "https://api.sec-api.io"
_INSIDER_URL = "https://api.sec-api.io/insider-trading"
_EXTRACTOR_URL = "https://api.sec-api.io/extractor"

# Form 4 transaction codes worth reporting. 'P'/'S' are open-market buys and
# sells — the only codes that reliably signal conviction. 'A'/'M'/'G' (grants,
# option exercises, gifts) are compensation mechanics and routinely swamp the
# real signal, so they are labelled rather than silently mixed in.
_CODE_MEANING = {
    "P": "open-market buy",
    "S": "open-market sale",
    "A": "grant/award",
    "M": "option exercise",
    "G": "gift",
    "F": "tax withholding",
    "D": "disposition to issuer",
}

# Sections most useful to the analysis stages, by 10-K item number.
_SECTIONS = {
    "1": "business",
    "1A": "risk_factors",
    "7": "mda",
}

# Section text is fed to an LLM; a full Item 1A can run 100k+ characters.
_SECTION_CHAR_CAP = 8000


class SecApiProvider(base.ProviderBase):
    name = "sec_api"

    def __init__(self, api_key: str) -> None:
        self._api_key = api_key

    # ── low-level ────────────────────────────────────────────────────────────
    def _query(self, lucene: str, size: int = 1) -> List[Dict[str, Any]]:
        resp = _http.post(
            _QUERY_URL,
            params={"token": self._api_key},
            json={
                "query": lucene,
                "from": "0",
                "size": str(size),
                "sort": [{"filedAt": {"order": "desc"}}],
            },
            timeout=25,
        )
        resp.raise_for_status()
        return (resp.json() or {}).get("filings") or []

    # ── capabilities ─────────────────────────────────────────────────────────
    def get_insider_trades(self, symbol: str) -> Dict[str, Any]:
        try:
            resp = _http.post(
                _INSIDER_URL,
                params={"token": self._api_key},
                json={
                    "query": f"issuer.tradingSymbol:{symbol}",
                    "from": "0",
                    "size": "50",
                },
                timeout=25,
            )
            resp.raise_for_status()
            rows = (resp.json() or {}).get("transactions") or []
            if not rows:
                return {}

            trades: List[Dict[str, Any]] = []
            for row in rows:
                owner = row.get("reportingOwner") or {}
                rel = owner.get("relationship") or {}
                table = row.get("nonDerivativeTable") or {}
                for txn in table.get("transactions") or []:
                    amounts = txn.get("amounts") or {}
                    code = (txn.get("coding") or {}).get("code")
                    shares = amounts.get("shares")
                    price = amounts.get("pricePerShare")
                    trades.append(
                        {
                            "reporting_name": owner.get("name"),
                            "officer_title": rel.get("officerTitle"),
                            "is_director": rel.get("isDirector"),
                            "is_officer": rel.get("isOfficer"),
                            "is_ten_percent_owner": rel.get("isTenPercentOwner"),
                            "transaction_date": txn.get("transactionDate"),
                            # 'A' = acquired, 'D' = disposed.
                            "direction": (
                                "acquired"
                                if amounts.get("acquiredDisposedCode") == "A"
                                else "disposed"
                            ),
                            "transaction_code": code,
                            "transaction_type": _CODE_MEANING.get(code, code),
                            "shares": shares,
                            "price": price,
                            "value": (
                                round(shares * price, 2)
                                if isinstance(shares, (int, float))
                                and isinstance(price, (int, float))
                                and price
                                else None
                            ),
                            "shares_owned_after": (
                                txn.get("postTransactionAmounts") or {}
                            ).get("sharesOwnedFollowingTransaction"),
                        }
                    )
            if not trades:
                return {}

            # Open-market activity summarised separately: grants and tax
            # withholding are mechanical and would otherwise dominate the totals
            # and read as "heavy insider selling" when nothing was chosen.
            open_market = [t for t in trades if t["transaction_code"] in ("P", "S")]
            bought = sum(
                t["value"] or 0 for t in open_market if t["direction"] == "acquired"
            )
            sold = sum(
                t["value"] or 0 for t in open_market if t["direction"] == "disposed"
            )
            return {
                "symbol": symbol,
                "insider_trades": trades[:25],
                "open_market_summary": {
                    "buy_count": sum(
                        1 for t in open_market if t["direction"] == "acquired"
                    ),
                    "sell_count": sum(
                        1 for t in open_market if t["direction"] == "disposed"
                    ),
                    "buy_value": round(bought, 2) or None,
                    "sell_value": round(sold, 2) or None,
                    "net_value": round(bought - sold, 2),
                },
                "source": self.name,
            }
        except Exception as exc:
            _logger.warning("sec-api get_insider_trades failed for %s: %s", symbol, exc)
            return {"error": str(exc)}

    def get_filing_sections(self, symbol: str) -> Dict[str, Any]:
        """Business, Risk Factors and MD&A text from the latest 10-K."""
        try:
            filings = self._query(f'ticker:{symbol} AND formType:"10-K"', size=1)
            if not filings:
                return {}
            filing = filings[0]
            url = filing.get("linkToFilingDetails")
            if not url:
                return {}

            sections: Dict[str, str] = {}
            for item, label in _SECTIONS.items():
                try:
                    resp = _http.get(
                        _EXTRACTOR_URL,
                        params={
                            "url": url,
                            "item": item,
                            "type": "text",
                            "token": self._api_key,
                        },
                        timeout=30,
                    )
                    if resp.status_code != 200:
                        continue
                    text = (resp.text or "").strip()
                    # The extractor marks table boundaries with a sentinel that
                    # means nothing to a reader or an LLM.
                    text = text.replace("##TABLE_END", " ").replace("##TABLE_START", " ")
                    # Filing text carries raw HTML entities (&#8217; etc.);
                    # left as-is they reach the report as literal escape codes.
                    text = html.unescape(text)
                    text = re.sub(r"[ \t]{2,}", " ", text)
                    if len(text) > 200:
                        sections[label] = text[:_SECTION_CHAR_CAP]
                except Exception as exc:  # one bad item must not lose the rest
                    _logger.debug("sec-api extractor item %s failed: %s", item, exc)

            if not sections:
                return {}
            return {
                "symbol": symbol,
                "form_type": filing.get("formType"),
                "filed_at": filing.get("filedAt"),
                "period_of_report": filing.get("periodOfReport"),
                "accession_no": filing.get("accessionNo"),
                "sections": sections,
                "source": self.name,
            }
        except Exception as exc:
            _logger.warning(
                "sec-api get_filing_sections failed for %s: %s", symbol, exc
            )
            return {"error": str(exc)}
