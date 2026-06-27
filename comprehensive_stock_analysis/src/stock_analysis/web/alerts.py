"""Alert dispatcher and in-process alert log."""

import json
import logging
import smtplib
from datetime import datetime
from email.mime.text import MIMEText
from pathlib import Path
from typing import Any, Dict, List, Optional

from ..config.settings import settings

_logger = logging.getLogger(__name__)
_MAX_LOG = 50


def _log_path() -> Path:
    return Path(settings.data_output_dir) / "alert_log.json"


def _read_log() -> List[Dict[str, Any]]:
    try:
        p = _log_path()
        if p.exists():
            return json.loads(p.read_text(encoding="utf-8"))
    except Exception:
        pass
    return []


def _write_log(entries: List[Dict[str, Any]]) -> None:
    try:
        p = _log_path()
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(json.dumps(entries, indent=2), encoding="utf-8")
    except Exception as exc:
        _logger.debug("alert log write failed: %s", exc)


def _append_alert(entry: Dict[str, Any]) -> None:
    log = _read_log()
    log.insert(0, entry)
    _write_log(log[:_MAX_LOG])


def _send_email(subject: str, body: str) -> None:
    if not settings.alert_email or not settings.alert_smtp_user:
        return
    try:
        msg = MIMEText(body)
        msg["Subject"] = subject
        msg["From"] = settings.alert_smtp_user
        msg["To"] = settings.alert_email
        with smtplib.SMTP(settings.alert_smtp_host, settings.alert_smtp_port, timeout=10) as s:
            s.ehlo()
            s.starttls()
            s.login(settings.alert_smtp_user, settings.alert_smtp_password)
            s.sendmail(settings.alert_smtp_user, [settings.alert_email], msg.as_string())
        _logger.info("alert email sent to %s", settings.alert_email)
    except Exception as exc:
        _logger.warning("alert email failed: %s", exc)


def _send_webhook(payload: Dict[str, Any]) -> None:
    if not settings.alert_webhook_url:
        return
    try:
        import requests
        requests.post(settings.alert_webhook_url, json=payload, timeout=10)
        _logger.info("alert webhook sent to %s", settings.alert_webhook_url)
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
        f"Previous: {old_r} (confidence {old_c:.0%})\n"
        f"Current:  {new_r} (confidence {new_c:.0%})\n"
    )
    _send_email(subject, body)
    _send_webhook(entry)


def _to_float(v: Any) -> Optional[float]:
    try:
        f = float(v)
        return None if f != f else f
    except (TypeError, ValueError):
        return None


def check_and_fire(
    symbol: str,
    prev_rec_path: Any,
    new_rec_path: Any,
) -> Optional[Dict[str, Any]]:
    """Path-based wrapper around check_and_dispatch.

    Reads both JSON files and delegates to check_and_dispatch.  Returns None
    when no alert fires; returns the log entry dict when one does.
    """
    try:
        from pathlib import Path as _Path

        def _load(p: Any) -> Optional[Dict[str, Any]]:
            if p is None:
                return None
            path = _Path(p)
            if not path.exists():
                return None
            return json.loads(path.read_text(encoding="utf-8"))

        new_rec = _load(new_rec_path)
        prev_rec = _load(prev_rec_path)
        if not new_rec or not prev_rec:
            return None

        new_r = new_rec.get("recommendation") or ""
        old_r = prev_rec.get("recommendation") or ""
        new_c = _to_float(new_rec.get("confidence"))
        old_c = _to_float(prev_rec.get("confidence"))

        reasons = []
        if new_r and old_r and new_r != old_r:
            reasons.append(f"recommendation changed: {old_r} -> {new_r}")
        if new_c is not None and old_c is not None and (old_c - new_c) >= 0.15:
            reasons.append(f"confidence dropped: {old_c:.0%} -> {new_c:.0%}")

        if not reasons:
            return None

        reason_str = "; ".join(reasons)
        entry: Dict[str, Any] = {
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
            f"Previous: {old_r} (confidence {old_c:.0%})\n"
            f"Current:  {new_r} (confidence {new_c:.0%})\n"
        )
        _send_email(subject, body)
        _send_webhook(entry)
        return entry
    except Exception as exc:
        _logger.debug("check_and_fire error for %s: %s", symbol, exc)
        return None


def get_alert_log() -> List[Dict[str, Any]]:
    return _read_log()
