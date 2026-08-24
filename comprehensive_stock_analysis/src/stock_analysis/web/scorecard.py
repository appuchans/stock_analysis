"""Grade recorded recommendations against what the market did next.

The raw material is ``rec_history`` (written by jobs._capture_rec_history and
backfilled from report artifacts). For each record we pull daily bars from the
recommendation date forward and compute 30/60/90-day returns, then grade
whether the recommendation direction matched: buy → positive return, sell →
negative, hold → small move. Pure functions; DB access belongs to routes.
"""

from datetime import date, datetime, timedelta
from typing import Any, Dict, List, Optional

from ..symbols import safe_symbol
from ..tools.providers import ROUTER

HORIZONS_DAYS = (30, 60, 90)
# A hold is "correct" when the price stayed within ±HOLD_BAND of the rec price.
HOLD_BAND_PCT = 10.0
_FETCH_BUFFER_DAYS = 14  # slack beyond the longest horizon for market holidays


def _parse_ts(recorded_at: Optional[str]) -> Optional[date]:
    """Parse an ISO timestamp; tolerate naive backfill mtimes."""
    if not recorded_at:
        return None
    try:
        return datetime.fromisoformat(recorded_at).date()
    except (ValueError, TypeError):
        return None


def _close_on_or_after(bars: List[Dict[str, Any]], start: date) -> Optional[float]:
    """First close on/after `start` — the market's answer at that horizon."""
    for b in bars:
        try:
            d = date.fromisoformat(str(b.get("date", ""))[:10])
        except ValueError:
            continue
        if d >= start and b.get("close") is not None:
            return float(b["close"])
    return None


def grade_direction(
    recommendation: Optional[str], ret_pct: Optional[float]
) -> Optional[str]:
    """'correct' | 'wrong' | None (ungradeable — no call or no price data).

    Substring match mirrors the frontend's existing recClass() classification;
    a recommendation string outside these families stays ungradeable rather
    than being forced into the nearest bucket.
    """
    if recommendation is None or ret_pct is None:
        return None
    rec = recommendation.lower()
    if "buy" in rec or "outperform" in rec:
        return "correct" if ret_pct > 0 else "wrong"
    if "sell" in rec or "underperform" in rec:
        return "correct" if ret_pct < 0 else "wrong"
    if "hold" in rec:
        return "correct" if abs(ret_pct) <= HOLD_BAND_PCT else "wrong"
    return None


def build_scorecard(records: List[Dict[str, Any]]) -> Dict[str, Any]:
    """Compute graded outcomes for all rec_history records.

    Records without enough elapsed time (or without prices) come back with
    null returns — visible in the UI as pending, never silently dropped.
    One bars fetch per symbol covers all of that symbol's records.
    """
    by_symbol: Dict[str, List[Dict[str, Any]]] = {}
    for r in records:
        sym = safe_symbol(r.get("symbol") or "")
        if sym:
            by_symbol.setdefault(sym, []).append(r)

    items: List[Dict[str, Any]] = []
    today = date.today()
    for sym, recs in sorted(by_symbol.items()):
        earliest = min(
            (d for d in (_parse_ts(r.get("recorded_at")) for r in recs) if d),
            default=None,
        )
        bars: List[Dict[str, Any]] = []
        if earliest:
            fetched = ROUTER.get_daily_bars(
                sym,
                earliest.isoformat(),
                (today + timedelta(days=_FETCH_BUFFER_DAYS)).isoformat(),
            )
            if fetched and "error" not in fetched:
                bars = fetched.get("bars") or []

        for r in recs:
            rec_date = _parse_ts(r.get("recorded_at"))
            entry: Dict[str, Any] = {
                "symbol": sym,
                "recorded_at": r.get("recorded_at"),
                "recommendation": r.get("recommendation"),
                "confidence": r.get("confidence"),
                "price_at_rec": r.get("price_at_rec"),
                "returns": {},
                "grade": None,
            }
            if rec_date is None or not bars:
                items.append(entry)
                continue
            # The recorded close when available; otherwise the first traded
            # close on/after the record date (backfilled rows may lack one).
            base = r.get("price_at_rec") or _close_on_or_after(bars, rec_date)
            returns: Dict[str, Optional[float]] = {}
            latest_ret: Optional[float] = None
            for h in HORIZONS_DAYS:
                px = _close_on_or_after(bars, rec_date + timedelta(days=h))
                val = round((px - base) / base * 100, 2) if (base and px) else None
                returns[str(h)] = val
                if h == HORIZONS_DAYS[-1]:
                    latest_ret = val
            entry["returns"] = returns
            entry["grade"] = grade_direction(r.get("recommendation"), latest_ret)
            items.append(entry)

    graded = [i for i in items if i["grade"]]
    correct = sum(1 for i in graded if i["grade"] == "correct")
    return {
        "items": items,
        "summary": {
            "total": len(items),
            "graded": len(graded),
            "correct": correct,
            "accuracy_pct": round(correct / len(graded) * 100, 1) if graded else None,
        },
    }
