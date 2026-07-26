"""Provider health/configuration status — which data sources are active."""

from typing import Any, Dict

from fastapi import APIRouter

router = APIRouter(prefix="/api", tags=["providers"])


@router.get("/providers/status")
def providers_status() -> Dict[str, Any]:
    from ...tools.providers import ROUTER

    return ROUTER.status()
