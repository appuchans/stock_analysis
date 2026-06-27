"""Alert log and settings endpoints."""

from typing import List

from fastapi import APIRouter

from ..schemas import AlertItem, AlertSettingsRequest, AlertSettingsResponse, AlertsResponse
from ...config.settings import settings

router = APIRouter(prefix="/api", tags=["alerts"])


def _log_entry_to_item(entry: dict) -> AlertItem:
    return AlertItem(
        symbol=entry.get("symbol", ""),
        timestamp=entry.get("fired_at", entry.get("timestamp", "")),
        reason=entry.get("reason", ""),
        old_rec=entry.get("old_recommendation") or entry.get("old_rec") or None,
        new_rec=entry.get("new_recommendation") or entry.get("new_rec") or None,
        old_confidence=entry.get("old_confidence"),
        new_confidence=entry.get("new_confidence"),
    )


@router.get("/alerts", response_model=AlertsResponse)
def list_alerts() -> AlertsResponse:
    from ..alerts import get_alert_log
    entries = get_alert_log()
    return AlertsResponse(items=[_log_entry_to_item(e) for e in entries])


@router.post("/settings", response_model=dict)
def save_alert_settings(body: AlertSettingsRequest) -> dict:
    _FIELDS = (
        "alert_email",
        "alert_smtp_host",
        "alert_smtp_port",
        "alert_smtp_user",
        "alert_smtp_password",
        "alert_webhook_url",
    )
    updated: List[str] = []
    for field in _FIELDS:
        val = getattr(body, field)
        if val is not None:
            try:
                object.__setattr__(settings, field, val)
                updated.append(field)
            except Exception:
                pass
    return {"saved": True, "fields": updated}


@router.get("/settings", response_model=AlertSettingsResponse)
def get_alert_settings() -> AlertSettingsResponse:
    return AlertSettingsResponse(
        alert_email=settings.alert_email,
        alert_smtp_host=settings.alert_smtp_host,
        alert_smtp_port=settings.alert_smtp_port,
        alert_smtp_user=settings.alert_smtp_user,
        alert_smtp_password_set=bool(settings.alert_smtp_password),
        alert_webhook_url=settings.alert_webhook_url,
    )
