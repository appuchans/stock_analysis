"""Alert dispatcher and alert log/settings persistence (SQLite-backed).

Settings saved via ``POST /api/settings/alerts`` are persisted in the
``settings_kv`` table (see ``web/db.py``) so they survive a restart; ``.env``
values (``config/settings.py``) remain the fallback for anything never
overridden through the UI.
"""

import logging
import smtplib
from datetime import datetime
from email.mime.text import MIMEText
from typing import Any, Dict, List, Optional

from ..config.settings import settings

_logger = logging.getLogger(__name__)

# settings_kv keys, mirroring the Settings fields they can override.
_SETTINGS_FIELDS = (
    "alert_email",
    "alert_smtp_host",
    "alert_smtp_port",
    "alert_smtp_user",
    "alert_smtp_password",
    "alert_webhook_url",
)


def _resolved_setting(key: str) -> str:
    """A persisted override (from the web UI) wins; otherwise fall back to
    the .env-backed Settings value."""
    from . import db

    override = db.get_setting(key)
    if override is not None:
        return override
    return str(getattr(settings, key, "") or "")


def get_alert_settings() -> Dict[str, Any]:
    """Resolved alert settings (persisted override > .env default)."""
    raw = {k: _resolved_setting(k) for k in _SETTINGS_FIELDS}
    try:
        raw["alert_smtp_port"] = int(raw["alert_smtp_port"]) if raw["alert_smtp_port"] else 587
    except ValueError:
        raw["alert_smtp_port"] = 587
    return raw


def save_alert_settings(values: Dict[str, Optional[str]]) -> None:
    """Persist any non-None fields to settings_kv (partial update)."""
    from . import db

    for key in _SETTINGS_FIELDS:
        val = values.get(key)
        if val is not None:
            db.set_setting(key, str(val))


def _send_email(subject: str, body: str) -> None:
    cfg = get_alert_settings()
    if not cfg["alert_email"] or not cfg["alert_smtp_user"]:
        return
    try:
        msg = MIMEText(body)
        msg["Subject"] = subject
        msg["From"] = cfg["alert_smtp_user"]
        msg["To"] = cfg["alert_email"]
        with smtplib.SMTP(cfg["alert_smtp_host"], cfg["alert_smtp_port"], timeout=10) as s:
            s.ehlo()
            s.starttls()
            s.login(cfg["alert_smtp_user"], cfg["alert_smtp_password"])
            s.sendmail(cfg["alert_smtp_user"], [cfg["alert_email"]], msg.as_string())
        _logger.info("alert email sent to %s", cfg["alert_email"])
    except Exception as exc:
        _logger.warning("alert email failed: %s", exc)


def _send_webhook(payload: Dict[str, Any]) -> None:
    cfg = get_alert_settings()
    if not cfg["alert_webhook_url"]:
        return
    try:
        from ..tools._http import SESSION

        SESSION.post(cfg["alert_webhook_url"], json=payload, timeout=10)
        _logger.info("alert webhook sent to %s", cfg["alert_webhook_url"])
    except Exception as exc:
        _logger.warning("alert webhook failed: %s", exc)


def check_and_dispatch(
    symbol: str,
    new_rec: Optional[Dict[str, Any]],
    prev_rec: Optional[Dict[str, Any]],
) -> None:
    """Compare new vs previous recommendation and fire an alert if warranted.

    Triggers on:
    - Recommendation flip (e.g. Buy -> Sell)
    - Confidence drop > 0.2
    """
    if not new_rec or not prev_rec:
        return

    new_r = new_rec.get("recommendation") or ""
    old_r = prev_rec.get("recommendation") or ""
    new_c = _to_float(new_rec.get("confidence"))
    old_c = _to_float(prev_rec.get("confidence"))

    reasons = []
    if new_r and old_r and new_r != old_r:
        reasons.append(f"recommendation changed: {old_r} -> {new_r}")
    if new_c is not None and old_c is not None and (old_c - new_c) > 0.2:
        reasons.append(f"confidence dropped: {old_c:.0%} -> {new_c:.0%}")

    if not reasons:
        return

    reason_str = "; ".join(reasons)
    entry = {
        "symbol": symbol,
        "fired_at": datetime.now().isoformat(timespec="seconds"),
        "reason": reason_str,
        "old_recommendation": old_r,
        "new_recommendation": new_r,
        "old_confidence": old_c,
        "new_confidence": new_c,
    }
    _append_alert(entry)
    _logger.info("[alert] %s: %s", symbol, reason_str)

    subject = f"Equity Lens alert: {symbol} -- {reason_str}"
    body = (
        f"Symbol: {symbol}\n"
        f"Change: {reason_str}\n"
        f"Previous: {old_r} (confidence {_format_confidence(old_c)})\n"
        f"Current:  {new_r} (confidence {_format_confidence(new_c)})\n"
    )
    _send_email(subject, body)
    _send_webhook(entry)


def _append_alert(entry: Dict[str, Any]) -> None:
    try:
        from . import db

        db.append_alert(entry)
    except Exception as exc:
        _logger.debug("alert log write failed: %s", exc)


def _to_float(v: Any) -> Optional[float]:
    try:
        f = float(v)
        return None if f != f else f
    except (TypeError, ValueError):
        return None


def _format_confidence(value: Optional[float]) -> str:
    """Format an optional recommendation confidence for a notification."""
    return f"{value:.0%}" if value is not None else "N/A"


def get_alert_log(limit: int = 200) -> List[Dict[str, Any]]:
    from . import db

    rows = db.list_alerts(limit=limit)
    # Normalize key names to what the API layer already expects.
    return [
        {
            "symbol": r["symbol"],
            "fired_at": r["fired_at"],
            "reason": r["reason"],
            "old_recommendation": r["old_recommendation"],
            "new_recommendation": r["new_recommendation"],
            "old_confidence": r["old_confidence"],
            "new_confidence": r["new_confidence"],
        }
        for r in rows
    ]
