"""Device Group routes.

Groups let admins organize devices into logical buckets (labs, rooms,
departments, etc.). Devices reference groups by id in a ``group_ids: []``
field so they can belong to multiple groups. Bulk actions accept group_ids
in addition to device_ids.
"""
from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException

from ..database import get_db
from ..deps import audit_log, get_current_user, require_role
from ..models import DeviceGroup, DeviceGroupAssignRequest, DeviceGroupCreate, DeviceGroupUpdate
from ..utils import serialize, utcnow

router = APIRouter(prefix="/device-groups", tags=["device-groups"])


@router.get("")
async def list_groups(user: dict = Depends(get_current_user)):
    db = get_db()
    items = await db.device_groups.find(
        {"org_id": user["org_id"]}, {"_id": 0}
    ).sort("name", 1).to_list(1000)
    # Attach device count per group
    counts_pipeline = [
        {"$match": {"org_id": user["org_id"], "group_ids": {"$exists": True, "$ne": []}}},
        {"$unwind": "$group_ids"},
        {"$group": {"_id": "$group_ids", "n": {"$sum": 1}}},
    ]
    counts: dict[str, int] = {}
    async for row in db.devices.aggregate(counts_pipeline):
        counts[row["_id"]] = row["n"]
    return [
        {**serialize(g), "device_count": counts.get(g["id"], 0)} for g in items
    ]


@router.post("")
async def create_group(
    payload: DeviceGroupCreate,
    user: dict = Depends(require_role("admin")),
):
    db = get_db()
    # Ensure name is unique within org
    existing = await db.device_groups.find_one(
        {"org_id": user["org_id"], "name": payload.name}, {"_id": 0}
    )
    if existing:
        raise HTTPException(status_code=409, detail=f"A group named '{payload.name}' already exists")
    group = DeviceGroup(
        org_id=user["org_id"],
        name=payload.name.strip(),
        description=(payload.description or "").strip() or None,
        color=payload.color,
        icon=payload.icon,
        created_by=user["id"],
    )
    doc = group.model_dump()
    doc["created_at"] = doc["created_at"].isoformat()
    await db.device_groups.insert_one(doc)
    await audit_log(db, user["org_id"], user, "device_group.created",
                    target=doc["id"], metadata={"name": doc["name"]})
    return {**serialize(doc), "device_count": 0}


@router.patch("/{group_id}")
async def update_group(
    group_id: str,
    payload: DeviceGroupUpdate,
    user: dict = Depends(require_role("admin")),
):
    db = get_db()
    group = await db.device_groups.find_one({"id": group_id, "org_id": user["org_id"]}, {"_id": 0})
    if not group:
        raise HTTPException(status_code=404, detail="Group not found")
    changes: dict = {}
    if payload.name is not None:
        clash = await db.device_groups.find_one(
            {"org_id": user["org_id"], "name": payload.name, "id": {"$ne": group_id}}, {"_id": 0}
        )
        if clash:
            raise HTTPException(status_code=409, detail=f"A group named '{payload.name}' already exists")
        changes["name"] = payload.name.strip()
    if payload.description is not None:
        changes["description"] = payload.description.strip() or None
    if payload.color is not None:
        changes["color"] = payload.color
    if payload.icon is not None:
        changes["icon"] = payload.icon
    if not changes:
        return serialize(group)
    changes["updated_at"] = utcnow().isoformat()
    await db.device_groups.update_one({"id": group_id}, {"$set": changes})
    await audit_log(db, user["org_id"], user, "device_group.updated",
                    target=group_id, metadata={"changes": list(changes.keys())})
    updated = await db.device_groups.find_one({"id": group_id}, {"_id": 0})
    return serialize(updated)


@router.delete("/{group_id}")
async def delete_group(
    group_id: str,
    user: dict = Depends(require_role("admin")),
):
    db = get_db()
    group = await db.device_groups.find_one({"id": group_id, "org_id": user["org_id"]}, {"_id": 0})
    if not group:
        raise HTTPException(status_code=404, detail="Group not found")
    await db.device_groups.delete_one({"id": group_id})
    # Remove group_id from all devices
    await db.devices.update_many(
        {"org_id": user["org_id"], "group_ids": group_id},
        {"$pull": {"group_ids": group_id}},
    )
    await audit_log(db, user["org_id"], user, "device_group.deleted",
                    target=group_id, metadata={"name": group.get("name")})
    return {"ok": True}


@router.get("/{group_id}/devices")
async def list_group_devices(
    group_id: str,
    user: dict = Depends(get_current_user),
):
    db = get_db()
    group = await db.device_groups.find_one({"id": group_id, "org_id": user["org_id"]}, {"_id": 0})
    if not group:
        raise HTTPException(status_code=404, detail="Group not found")
    devices = await db.devices.find(
        {"org_id": user["org_id"], "group_ids": group_id}, {"_id": 0, "api_key_hash": 0}
    ).sort("hostname", 1).to_list(2000)
    return [serialize(d) for d in devices]


@router.post("/{group_id}/assign")
async def assign_devices(
    group_id: str,
    payload: DeviceGroupAssignRequest,
    user: dict = Depends(require_role("technician")),
):
    db = get_db()
    group = await db.device_groups.find_one({"id": group_id, "org_id": user["org_id"]}, {"_id": 0})
    if not group:
        raise HTTPException(status_code=404, detail="Group not found")
    res = await db.devices.update_many(
        {"org_id": user["org_id"], "id": {"$in": payload.device_ids}},
        {"$addToSet": {"group_ids": group_id}},
    )
    await audit_log(db, user["org_id"], user, "device_group.assigned",
                    target=group_id, metadata={"device_ids": payload.device_ids,
                                                "matched": res.matched_count})
    return {"ok": True, "matched": res.matched_count, "modified": res.modified_count}


@router.post("/{group_id}/unassign")
async def unassign_devices(
    group_id: str,
    payload: DeviceGroupAssignRequest,
    user: dict = Depends(require_role("technician")),
):
    db = get_db()
    group = await db.device_groups.find_one({"id": group_id, "org_id": user["org_id"]}, {"_id": 0})
    if not group:
        raise HTTPException(status_code=404, detail="Group not found")
    res = await db.devices.update_many(
        {"org_id": user["org_id"], "id": {"$in": payload.device_ids}},
        {"$pull": {"group_ids": group_id}},
    )
    await audit_log(db, user["org_id"], user, "device_group.unassigned",
                    target=group_id, metadata={"device_ids": payload.device_ids})
    return {"ok": True, "matched": res.matched_count, "modified": res.modified_count}
