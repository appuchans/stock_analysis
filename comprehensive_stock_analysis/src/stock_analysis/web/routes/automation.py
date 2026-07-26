"""CRUD endpoints for scheduled re-analysis and alert rules."""

from typing import List

from fastapi import APIRouter, HTTPException

from .. import db
from ..schemas import RuleCreateRequest, RuleItem, ScheduleCreateRequest, ScheduleItem

router = APIRouter(prefix="/api", tags=["automation"])


# ── Schedules ────────────────────────────────────────────────────────────────
@router.get("/schedules", response_model=List[ScheduleItem])
def list_schedules() -> List[dict]:
    from .. import scheduler

    return scheduler.list_schedules()


@router.post("/schedules", response_model=ScheduleItem, status_code=201)
def create_schedule(req: ScheduleCreateRequest) -> dict:
    from .. import scheduler

    try:
        return scheduler.create_schedule(
            target=req.target, cron_expr=req.cron_expr, depth=req.depth,
            use_cache=req.use_cache, monitor_only=req.monitor_only,
        )
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=f"invalid cron expression: {exc}")


@router.post("/schedules/{schedule_id}/toggle")
def toggle_schedule(schedule_id: str, enabled: bool) -> dict:
    from .. import scheduler

    if not scheduler.toggle_schedule(schedule_id, enabled):
        raise HTTPException(status_code=404, detail="unknown schedule id")
    return {"id": schedule_id, "enabled": enabled}


@router.delete("/schedules/{schedule_id}", status_code=204)
def delete_schedule(schedule_id: str) -> None:
    from .. import scheduler

    if not scheduler.remove_schedule(schedule_id):
        raise HTTPException(status_code=404, detail="unknown schedule id")


# ── Alert rules ──────────────────────────────────────────────────────────────
@router.get("/rules", response_model=List[RuleItem])
def list_rules() -> List[dict]:
    return db.list_rules()


@router.post("/rules", response_model=RuleItem, status_code=201)
def create_rule(req: RuleCreateRequest) -> dict:
    from .. import rules as rules_mod

    return rules_mod.create_rule(
        symbol=req.symbol, rule_type=req.rule_type, threshold=req.threshold,
        cooldown_min=req.cooldown_min,
    )


@router.post("/rules/{rule_id}/toggle")
def toggle_rule(rule_id: str, enabled: bool) -> dict:
    if not db.set_rule_enabled(rule_id, enabled):
        raise HTTPException(status_code=404, detail="unknown rule id")
    return {"id": rule_id, "enabled": enabled}


@router.delete("/rules/{rule_id}", status_code=204)
def delete_rule(rule_id: str) -> None:
    if not db.delete_rule(rule_id):
        raise HTTPException(status_code=404, detail="unknown rule id")
