"""Alert Rules API: expose per-org threshold + severity + dwell overrides."""
from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel

from ..database import get_db
from ..deps import audit_log, get_current_user, require_role
from ..services.alerts.policies import DEFAULT_POLICIES, RESOLUTION_GRACE_BY_SEVERITY, merge_policy

router = APIRouter(prefix="/alert-rules", tags=["alert-rules"])


@router.get("")
async def list_rules(user: dict = Depends(get_current_user)):
    db = get_db()
    doc = await db.alert_policies.find_one({"org_id": user["org_id"]}, {"_id": 0}) or {}
    overrides = doc.get("policies") or {}
    merged = {
        key: {
            **merge_policy(default, overrides.get(key)),
            "key": key,
            "is_overridden": key in overrides,
        }
        for key, default in DEFAULT_POLICIES.items()
    }
    return {
        "resolution_grace_by_severity": RESOLUTION_GRACE_BY_SEVERITY,
        "rules": list(merged.values()),
    }


class RulePatch(BaseModel):
    enabled: bool | None = None
    escalations: list[dict] | None = None
    recommendation: str | None = None
    title: str | None = None
    unit: str | None = None


@router.patch("/{rule_key}")
async def patch_rule(rule_key: str, body: RulePatch,
                     user: dict = Depends(require_role("admin"))):
    if rule_key not in DEFAULT_POLICIES:
        raise HTTPException(status_code=404, detail="Unknown rule")
    db = get_db()
    doc = await db.alert_policies.find_one({"org_id": user["org_id"]}, {"_id": 0}) or {
        "org_id": user["org_id"], "policies": {}}
    overrides = doc.get("policies") or {}
    current = overrides.get(rule_key) or {}
    new = {**current, **{k: v for k, v in body.model_dump().items() if v is not None}}
    overrides[rule_key] = new
    await db.alert_policies.update_one(
        {"org_id": user["org_id"]}, {"$set": {"policies": overrides}}, upsert=True
    )
    await audit_log(db, user["org_id"], user, "alert_rule.updated", target=rule_key,
                    metadata={"patch": body.model_dump()})
    return {"ok": True, "rule": {**merge_policy(DEFAULT_POLICIES[rule_key], new), "key": rule_key, "is_overridden": True}}


@router.post("/{rule_key}/reset")
async def reset_rule(rule_key: str, user: dict = Depends(require_role("admin"))):
    if rule_key not in DEFAULT_POLICIES:
        raise HTTPException(status_code=404, detail="Unknown rule")
    db = get_db()
    await db.alert_policies.update_one(
        {"org_id": user["org_id"]}, {"$unset": {f"policies.{rule_key}": ""}}
    )
    await audit_log(db, user["org_id"], user, "alert_rule.reset", target=rule_key)
    return {"ok": True, "rule": {**DEFAULT_POLICIES[rule_key], "key": rule_key, "is_overridden": False}}
