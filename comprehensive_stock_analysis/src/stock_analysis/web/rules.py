"""User-defined alert rules: price-based rules evaluated by periodic quote
polling (zero LLM calls, safe to run concurrently with an analysis), and
recommendation-based rules evaluated right after a run completes.

Dispatch reuses ``alerts``'s email/webhook/log machinery so a rule firing
looks identical to the built-in recommendation-flip/confidence-drop alerts —
same log, same settings, same channels.
"""

import logging
import uuid
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, Optional

from . import db

_logger = logging.getLogger(__name__)

PRICE_RULE_TYPES = {"price_above", "price_below", "pct_move_day"}
POST_RUN_RULE_TYPES = {
    "target_price_hit", "stop_loss_hit", "recommendation_changed", "confidence_dropped",
}


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def create_rule(
    symbol: str, rule_type: str, threshold: Optional[float] = None, cooldown_min: int = 60,
) -> Dict[str, Any]:
    row = {
        "id": uuid.uuid4().hex, "symbol": symbol, "rule_type": rule_type,
        "threshold": threshold, "cooldown_min": cooldown_min, "enabled": True,
        "created_at": _now_iso(),
    }
    db.add_rule(row)
    return row


def _off_cooldown(rule: Dict[str, Any]) -> bool:
    last = rule.get("last_fired_at")
    if not last:
        return True
    try:
        last_dt = datetime.fromisoformat(last)
    except ValueError:
        return True
    return datetime.now(timezone.utc) - last_dt >= timedelta(minutes=rule["cooldown_min"])


def _dispatch(symbol: str, rule: Dict[str, Any], reason: str) -> None:
    from . import alerts

    entry = {
        "symbol": symbol, "fired_at": _now_iso(), "reason": reason,
        "old_recommendation": None, "new_recommendation": None,
        "old_confidence": None, "new_confidence": None,
    }
    alerts._append_alert(entry)
    db.record_rule_fired(rule["id"])
    _logger.info("[rule] %s: %s", symbol, reason)
    subject = f"Equity Lens rule alert: {symbol} — {reason}"
    alerts._send_email(subject, f"Symbol: {symbol}\nRule: {rule['rule_type']}\n{reason}\n")
    alerts._send_webhook(entry)


# ── Price-based rules (quote-poll evaluator) ──────────────────────────────────
def evaluate_price_rules_for_symbol(symbol: str, quote: Optional[Dict[str, Any]] = None) -> None:
    """Evaluate this symbol's enabled price-type rules against a live quote.
    Never touches token_meter/llm_budget — safe to call from anywhere,
    including while an analysis is running."""
    rules = [r for r in db.list_rules(symbol) if r["enabled"] and r["rule_type"] in PRICE_RULE_TYPES]
    if not rules:
        return
    if quote is None:
        from ..tools.providers import ROUTER

        quote = ROUTER.get_quote(symbol)
    price = quote.get("price") if quote else None
    change_pct = quote.get("change_pct") if quote else None
    if price is None:
        return

    for rule in rules:
        if not _off_cooldown(rule):
            continue
        threshold = rule.get("threshold")
        if threshold is None:
            continue
        fired_reason = None
        if rule["rule_type"] == "price_above" and price > threshold:
            fired_reason = f"price {price:.2f} crossed above {threshold:.2f}"
        elif rule["rule_type"] == "price_below" and price < threshold:
            fired_reason = f"price {price:.2f} crossed below {threshold:.2f}"
        elif rule["rule_type"] == "pct_move_day" and change_pct is not None and abs(change_pct) >= threshold:
            fired_reason = f"day move {change_pct:+.1f}% reached the {threshold:.1f}% threshold"
        if fired_reason:
            _dispatch(symbol, rule, fired_reason)


def evaluate_all_price_rules() -> int:
    """Batch entry point for the periodic quote-poll job. Uses Polygon's
    batch-quote endpoint when configured (one call for every symbol with a
    price rule); otherwise falls back to a per-symbol yfinance quote via the
    router. Returns the number of symbols evaluated."""
    symbols = sorted({
        r["symbol"] for r in db.list_rules()
        if r["enabled"] and r["rule_type"] in PRICE_RULE_TYPES
    })
    if not symbols:
        return 0
    from ..tools.providers import ROUTER

    batch = ROUTER.get_batch_quotes(symbols)
    for sym in symbols:
        quote = batch.get(sym) or ROUTER.get_quote(sym)
        evaluate_price_rules_for_symbol(sym, quote=quote)
    return len(symbols)


# ── Post-run rules (recommendation-based) ─────────────────────────────────────
def evaluate_post_run_rules(
    symbol: str, new_rec: Optional[Dict[str, Any]], prev_rec: Optional[Dict[str, Any]],
) -> None:
    """User-configured recommendation/target/stop-loss rules for *symbol*,
    evaluated right after a run completes — additive to (not a replacement
    for) alerts.check_and_dispatch's built-in recommendation-flip and
    confidence-drop triggers, which fire unconditionally with zero setup."""
    rules = [r for r in db.list_rules(symbol) if r["enabled"] and r["rule_type"] in POST_RUN_RULE_TYPES]
    if not rules or not new_rec:
        return

    price = None
    for rule in rules:
        if not _off_cooldown(rule):
            continue
        fired_reason = None
        if rule["rule_type"] == "recommendation_changed" and prev_rec:
            old_r, new_r = prev_rec.get("recommendation"), new_rec.get("recommendation")
            if old_r and new_r and old_r != new_r:
                fired_reason = f"recommendation changed: {old_r} -> {new_r}"
        elif rule["rule_type"] == "confidence_dropped" and prev_rec:
            old_c, new_c = prev_rec.get("confidence"), new_rec.get("confidence")
            threshold = rule.get("threshold") or 0.2
            both_numeric = isinstance(old_c, (int, float)) and isinstance(new_c, (int, float))
            if both_numeric and (old_c - new_c) >= threshold:
                fired_reason = f"confidence dropped {old_c:.0%} -> {new_c:.0%}"
        elif rule["rule_type"] in ("target_price_hit", "stop_loss_hit"):
            level = new_rec.get("target_price" if rule["rule_type"] == "target_price_hit" else "stop_loss")
            if level is None:
                continue
            if price is None:
                from ..tools.providers import ROUTER

                quote = ROUTER.get_quote(symbol)
                price = quote.get("price")
            if price is None:
                continue
            if rule["rule_type"] == "target_price_hit" and price >= level:
                fired_reason = f"price {price:.2f} reached target {level:.2f}"
            elif rule["rule_type"] == "stop_loss_hit" and price <= level:
                fired_reason = f"price {price:.2f} hit stop-loss {level:.2f}"
        if fired_reason:
            _dispatch(symbol, rule, fired_reason)
