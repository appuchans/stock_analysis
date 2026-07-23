"""Alert log and settings endpoints."""

from typing import List

from fastapi import APIRouter, Query

from ..schemas import AlertItem, AlertSettingsRequest, AlertSettingsResponse

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


@router.get("/alerts", response_model=List[AlertItem])
def list_alerts(limit: int = Query(200, ge=1, le=1000)) -> List[AlertItem]:
    from ..alerts import get_alert_log
    return [_log_entry_to_item(e) for e in get_alert_log(limit=limit)]


@router.post("/settings/alerts", response_model=dict)
def save_alert_settings(body: AlertSettingsRequest) -> dict:
    from ..alerts import save_alert_settings as _save

    values = {
        "alert_email": body.alert_email,
        "alert_smtp_host": body.alert_smtp_host,
        "alert_smtp_port": None if body.alert_smtp_port is None else str(body.alert_smtp_port),
        "alert_smtp_user": body.alert_smtp_user,
        "alert_smtp_password": body.alert_smtp_password,
        "alert_webhook_url": body.alert_webhook_url,
    }
    _save(values)
    return {"status": "ok"}


@router.get("/settings/alerts", response_model=AlertSettingsResponse)
def get_alert_settings_route() -> AlertSettingsResponse:
    from ..alerts import get_alert_settings

    cfg = get_alert_settings()
    return AlertSettingsResponse(
        alert_email=cfg["alert_email"],
        alert_smtp_host=cfg["alert_smtp_host"],
        alert_smtp_port=cfg["alert_smtp_port"],
        alert_smtp_user=cfg["alert_smtp_user"],
        alert_smtp_password_set=bool(cfg["alert_smtp_password"]),
        alert_webhook_url=cfg["alert_webhook_url"],
    )
