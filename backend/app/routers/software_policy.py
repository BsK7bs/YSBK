"""Software Policy & Compliance API."""
from __future__ import annotations

from typing import Literal

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel

from ..database import get_db
from ..deps import audit_log, get_current_user, require_role
from ..services.alerts import software_policy as sp

router = APIRouter(prefix="/software", tags=["software-policy"])


@router.get("/policy")
async def get_policy(user: dict = Depends(get_current_user)):
    db = get_db()
    return await sp.get_policy(db, user["org_id"])


class PolicyBody(BaseModel):
    mode: Literal["monitor", "blocklist", "allowlist"]


@router.put("/policy")
async def put_policy(body: PolicyBody, user: dict = Depends(require_role("admin"))):
    db = get_db()
    doc = await sp.set_policy(db, user["org_id"], body.mode, actor=user)
    await audit_log(db, user["org_id"], user, "software_policy.mode_changed",
                    metadata={"mode": body.mode})
    return doc


@router.get("/rules")
async def list_rules(mode: Literal["allow", "block"] | None = None,
                    user: dict = Depends(get_current_user)):
    db = get_db()
    return await sp.list_rules(db, user["org_id"], mode)


class RuleBody(BaseModel):
    mode: Literal["allow", "block"]
    name: str | None = None
    publisher: str | None = None
    min_version: str | None = None
    max_version: str | None = None
    category: str | None = None
    severity_override: Literal["critical", "high", "medium", "low", "info"] | None = None
    notes: str | None = None


@router.post("/rules")
async def add_rule(body: RuleBody, user: dict = Depends(require_role("admin"))):
    if not body.name and not body.publisher:
        raise HTTPException(status_code=400, detail="name or publisher is required")
    db = get_db()
    doc = await sp.add_rule(db, user["org_id"], body.model_dump(), actor=user)
    await audit_log(db, user["org_id"], user, "software_policy.rule_added",
                    metadata={"mode": body.mode, "name": body.name, "publisher": body.publisher})
    return doc


@router.delete("/rules/{rule_id}")
async def delete_rule(rule_id: str, user: dict = Depends(require_role("admin"))):
    db = get_db()
    ok = await sp.delete_rule(db, user["org_id"], rule_id)
    if not ok:
        raise HTTPException(status_code=404, detail="Rule not found")
    await audit_log(db, user["org_id"], user, "software_policy.rule_deleted", target=rule_id)
    return {"ok": True}


class BulkRulesBody(BaseModel):
    mode: Literal["allow", "block"]
    entries: list[dict]


@router.post("/rules/bulk")
async def bulk_rules(body: BulkRulesBody, user: dict = Depends(require_role("admin"))):
    db = get_db()
    n = await sp.bulk_add_rules(db, user["org_id"], body.entries, body.mode, actor=user)
    await audit_log(db, user["org_id"], user, "software_policy.rules_bulk_added",
                    metadata={"mode": body.mode, "count": n})
    return {"ok": True, "count": n}


@router.get("/inventory")
async def inventory(q: str | None = None,
                    category: str | None = None,
                    limit: int = Query(default=200, ge=1, le=2000),
                    user: dict = Depends(get_current_user)):
    db = get_db()
    return await sp.list_inventory(db, user["org_id"], q=q, category=category, limit=limit)


@router.get("/compliance")
async def compliance(user: dict = Depends(get_current_user)):
    db = get_db()
    return await sp.compliance_summary(db, user["org_id"])


# ---------------------------------------------------------------------------
# Software change events (new / removed / version_changed / outdated)
# ---------------------------------------------------------------------------
@router.get("/changes")
async def list_software_changes(
    kind: Literal["new", "removed", "version_changed"] | None = None,
    device_id: str | None = None,
    since: str | None = None,
    limit: int = Query(default=200, ge=1, le=2000),
    user: dict = Depends(get_current_user),
):
    """Return recent software-inventory changes for the org.

    * ``kind``        filter to `new` / `removed` / `version_changed`
    * ``device_id``   filter to a single device
    * ``since``       ISO-8601 cutoff; if omitted, returns latest `limit`
    """
    db = get_db()
    q: dict = {"org_id": user["org_id"]}
    if kind:
        q["kind"] = kind
    if device_id:
        q["device_id"] = device_id
    if since:
        q["ts"] = {"$gte": since}
    cur = db.software_events.find(q, {"_id": 0}).sort("ts", -1).limit(limit)
    return await cur.to_list(limit)


@router.get("/outdated")
async def list_outdated(
    limit: int = Query(default=500, ge=1, le=5000),
    user: dict = Depends(get_current_user),
):
    """Return per-device installations whose version is behind the
    ``latest_known_version`` field on their catalog entry.
    """
    db = get_db()
    catalog = await db.software_catalog.find(
        {"org_id": user["org_id"],
         "latest_known_version": {"$exists": True, "$nin": [None, ""]}},
        {"_id": 0, "key": 1, "name": 1, "publisher": 1, "latest_known_version": 1},
    ).to_list(5000)
    latest_by_key = {c["key"]: c for c in catalog}
    if not latest_by_key:
        return []
    out: list[dict] = []
    cur = db.software_device_index.find(
        {"org_id": user["org_id"], "key": {"$in": list(latest_by_key.keys())}},
        {"_id": 0},
    ).limit(limit * 2)
    async for row in cur:
        latest = latest_by_key[row["key"]]["latest_known_version"]
        if row.get("version") and row["version"] != latest:
            out.append({**row, "latest_known_version": latest})
            if len(out) >= limit:
                break
    return out


class LatestVersionBody(BaseModel):
    latest_known_version: str


@router.post("/catalog/{key}/latest")
async def set_latest_version(
    key: str, body: LatestVersionBody,
    user: dict = Depends(require_role("admin")),
):
    """Set the ``latest_known_version`` on a catalog entry.  Every device
    whose installed version differs will be reported by ``/outdated``.
    """
    db = get_db()
    res = await db.software_catalog.update_one(
        {"org_id": user["org_id"], "key": key},
        {"$set": {"latest_known_version": body.latest_known_version}},
    )
    if res.matched_count == 0:
        raise HTTPException(status_code=404, detail="Catalog entry not found")
    # Recompute per-catalog outdated_count.
    outdated_count = await db.software_device_index.count_documents({
        "org_id": user["org_id"], "key": key,
        "version": {"$nin": ["", body.latest_known_version]},
    })
    await db.software_catalog.update_one(
        {"org_id": user["org_id"], "key": key},
        {"$set": {"outdated_count": outdated_count}},
    )
    await audit_log(db, user["org_id"], user, "software_policy.latest_version_set",
                    target=key, metadata={"latest_known_version": body.latest_known_version})
    return {"ok": True, "key": key,
            "latest_known_version": body.latest_known_version,
            "outdated_count": outdated_count}
