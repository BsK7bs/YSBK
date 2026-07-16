"""Device management routes.

Provides both agent-enrolled and manually-registered computers.
Supports full CRUD with search, filters, and pagination.
"""
import math
import re
import uuid
from datetime import datetime, timedelta, timezone

from fastapi import APIRouter, Depends, HTTPException, Query

from ..config import settings
from ..database import get_db
from ..deps import audit_log, get_current_user, require_role
from ..models import ComputerRegisterRequest, DeviceUpdate
from ..utils import serialize, utcnow

router = APIRouter(prefix="/devices", tags=["devices"])


def _compute_online(device: dict) -> bool:
    ls = device.get("last_seen")
    if not ls:
        return False
    try:
        dt = datetime.fromisoformat(ls) if isinstance(ls, str) else ls
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
    except Exception:
        return False
    return (datetime.now(timezone.utc) - dt).total_seconds() < settings.DEVICE_OFFLINE_THRESHOLD_SECONDS


def _project(device: dict) -> dict:
    device = serialize(device)
    device.pop("api_key_hash", None)
    device["is_online"] = _compute_online(device)
    if not device["is_online"] and device.get("risk_level") != "critical":
        device["risk_level"] = device.get("risk_level") or "offline"
    return device


def _search_regex(q: str) -> dict:
    """Build a case-insensitive OR regex query across multiple fields."""
    esc = re.escape(q.strip())
    if not esc:
        return {}
    pat = {"$regex": esc, "$options": "i"}
    return {
        "$or": [
            {"hostname": pat},
            {"display_name": pat},
            {"ip_address": pat},
            {"mac_address": pat},
            {"serial_number": pat},
            {"os_name": pat},
            {"cpu": pat},
            {"motherboard": pat},
            {"bios_version": pat},
            {"notes": pat},
            {"tags": pat},
        ]
    }


def _status_filter(status: str | None) -> tuple[str, dict] | None:
    """Return an in-memory filter tag; online/offline uses a computed threshold, others are DB fields."""
    return status if status in {"online", "offline", "healthy", "warning", "high_risk", "critical", "has_agent", "no_agent"} else None


ALLOWED_SORT = {
    "hostname": "hostname",
    "os": "os_name",
    "last_seen": "last_seen",
    "enrolled_at": "enrolled_at",
    "health": "health_score",
    "cpu": "cpu",
    "ram": "ram_gb",
}


@router.get("")
async def list_devices(
    q: str | None = Query(default=None, description="Search across hostname, IP, MAC, serial, OS, CPU, notes, tags"),
    status: str | None = Query(default=None, description="online|offline|healthy|warning|high_risk|critical|has_agent|no_agent"),
    os: str | None = Query(default=None, description="Substring match on os_name (case-insensitive)"),
    tag: str | None = Query(default=None, description="Match exact tag"),
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=25, ge=1, le=500),
    sort_by: str = Query(default="enrolled_at"),
    sort_dir: str = Query(default="desc", pattern="^(asc|desc)$"),
    user: dict = Depends(get_current_user),
):
    """List computers with search, filters, and pagination.

    Returns a paginated envelope: `{items, total, page, page_size, total_pages}`.
    """
    db = get_db()
    query: dict = {"org_id": user["org_id"]}
    if q:
        query.update(_search_regex(q))
    if os:
        query["os_name"] = {"$regex": re.escape(os), "$options": "i"}
    if tag:
        query["tags"] = tag
    if status == "has_agent":
        query["has_agent"] = True
    elif status == "no_agent":
        query["has_agent"] = {"$ne": True}
    elif status in {"healthy", "warning", "high_risk", "critical"}:
        query["risk_level"] = status

    # For online/offline, we need to filter in-memory using the threshold.
    online_filter = status if status in {"online", "offline"} else None

    sort_field = ALLOWED_SORT.get(sort_by, "enrolled_at")
    direction = -1 if sort_dir == "desc" else 1

    # If online/offline filtering, we can't paginate correctly at DB level without derived field.
    # We fetch all matching, filter, then paginate. Bounded by org size in practice.
    if online_filter:
        all_docs = await db.devices.find(query, {"_id": 0}).sort(sort_field, direction).to_list(5000)
        projected = [_project(d) for d in all_docs]
        want_online = online_filter == "online"
        projected = [d for d in projected if d["is_online"] == want_online]
        total = len(projected)
        start = (page - 1) * page_size
        items = projected[start:start + page_size]
    else:
        total = await db.devices.count_documents(query)
        cursor = db.devices.find(query, {"_id": 0}).sort(sort_field, direction).skip((page - 1) * page_size).limit(page_size)
        docs = await cursor.to_list(page_size)
        items = [_project(d) for d in docs]

    return {
        "items": items,
        "total": total,
        "page": page,
        "page_size": page_size,
        "total_pages": max(1, math.ceil(total / page_size)) if page_size else 1,
    }


@router.get("/summary")
async def devices_summary(user: dict = Depends(get_current_user)):
    db = get_db()
    devices = await db.devices.find({"org_id": user["org_id"]}, {"_id": 0}).to_list(5000)
    total = len(devices)
    online = healthy = warning = high_risk = critical = with_agent = 0
    total_health = 0
    scored = 0
    for d in devices:
        is_on = _compute_online(d)
        if is_on:
            online += 1
        if d.get("has_agent"):
            with_agent += 1
        risk = d.get("risk_level") if is_on else "offline"
        if risk == "healthy":
            healthy += 1
        elif risk == "warning":
            warning += 1
        elif risk == "high_risk":
            high_risk += 1
        elif risk == "critical":
            critical += 1
        hs = d.get("health_score")
        if hs is not None:
            total_health += hs
            scored += 1
    return {
        "total": total,
        "online": online,
        "offline": total - online,
        "with_agent": with_agent,
        "unmanaged": total - with_agent,
        "healthy": healthy,
        "warning": warning,
        "high_risk": high_risk,
        "critical": critical,
        "avg_health": int(round(total_health / scored)) if scored else None,
    }


@router.get("/{device_id}")
async def get_device(device_id: str, user: dict = Depends(get_current_user)):
    db = get_db()
    device = await db.devices.find_one({"id": device_id, "org_id": user["org_id"]}, {"_id": 0})
    if not device:
        raise HTTPException(status_code=404, detail="Device not found")
    return _project(device)


@router.post("", status_code=201)
async def register_computer(
    payload: ComputerRegisterRequest,
    user: dict = Depends(require_role("technician")),
):
    """Manually register a computer without an agent.

    Fields captured: hostname, IP, MAC, serial number, OS, CPU, RAM, disk,
    motherboard, BIOS version, notes, tags. No API key is issued; the record
    is marked `has_agent=false` until (optionally) enrolled via the agent flow.
    """
    db = get_db()

    # Uniqueness within the org: prevent duplicate hostnames or serial numbers.
    dupe_query: dict = {"org_id": user["org_id"]}
    or_clauses: list[dict] = [{"hostname": payload.hostname.strip()}]
    if payload.serial_number:
        or_clauses.append({"serial_number": payload.serial_number.strip()})
    if payload.mac_address:
        or_clauses.append({"mac_address": payload.mac_address.strip()})
    dupe_query["$or"] = or_clauses
    existing = await db.devices.find_one(dupe_query, {"_id": 0, "hostname": 1, "serial_number": 1, "mac_address": 1})
    if existing:
        conflicts = []
        if existing.get("hostname") == payload.hostname.strip():
            conflicts.append("hostname")
        if payload.serial_number and existing.get("serial_number") == payload.serial_number.strip():
            conflicts.append("serial number")
        if payload.mac_address and existing.get("mac_address") == payload.mac_address.strip():
            conflicts.append("MAC address")
        detail = f"A computer with the same {', '.join(conflicts) or 'identifier'} already exists"
        raise HTTPException(status_code=409, detail=detail)

    now = utcnow().isoformat()
    doc = {
        "id": str(uuid.uuid4()),
        "org_id": user["org_id"],
        "hostname": payload.hostname.strip(),
        "display_name": (payload.display_name or "").strip() or payload.hostname.strip(),
        "os_name": payload.os_name,
        "os_version": payload.os_version,
        "agent_version": None,
        "hardware_id": None,
        "ip_address": (payload.ip_address or "").strip() or None,
        "mac_address": (payload.mac_address or "").strip() or None,
        "serial_number": (payload.serial_number or "").strip() or None,
        "cpu": (payload.cpu or "").strip() or None,
        "ram_gb": payload.ram_gb,
        "disk_gb": payload.disk_gb,
        "motherboard": (payload.motherboard or "").strip() or None,
        "bios_version": (payload.bios_version or "").strip() or None,
        "notes": (payload.notes or "").strip() or None,
        "tags": [t.strip() for t in (payload.tags or []) if t.strip()],
        "managed": True,
        "has_agent": False,
        "created_via": "manual",
        "api_key_hash": None,
        "is_online": False,
        "last_seen": None,
        "enrolled_at": now,
        "enrolled_by": user["id"],
        "latest_metrics": {},
        "inventory": {},
        "health_score": None,
        "risk_level": None,
    }
    await db.devices.insert_one(doc)
    await audit_log(db, user["org_id"], user, "device.registered", target=doc["id"], metadata={"hostname": doc["hostname"], "via": "manual"})
    return _project(doc)


async def _apply_update(db, device_id: str, org_id: str, payload: DeviceUpdate, actor: dict) -> dict:
    body = payload.model_dump(exclude_unset=True)
    update: dict = {}
    for k, v in body.items():
        if v is None:
            update[k] = None
            continue
        if isinstance(v, str):
            update[k] = v.strip() or None
        elif isinstance(v, list):
            update[k] = [str(x).strip() for x in v if str(x).strip()]
        else:
            update[k] = v
    if not update:
        raise HTTPException(status_code=400, detail="Nothing to update")

    # Uniqueness checks for hostname/serial/mac if changed
    conflicts = {}
    if "hostname" in update and update["hostname"]:
        conflicts["hostname"] = update["hostname"]
    if "serial_number" in update and update["serial_number"]:
        conflicts["serial_number"] = update["serial_number"]
    if "mac_address" in update and update["mac_address"]:
        conflicts["mac_address"] = update["mac_address"]
    if conflicts:
        or_clauses = [{k: v} for k, v in conflicts.items()]
        clash = await db.devices.find_one(
            {"org_id": org_id, "id": {"$ne": device_id}, "$or": or_clauses}, {"_id": 0, "hostname": 1}
        )
        if clash:
            raise HTTPException(status_code=409, detail="Another computer already uses one of these identifiers")

    res = await db.devices.update_one({"id": device_id, "org_id": org_id}, {"$set": update})
    if res.matched_count == 0:
        raise HTTPException(status_code=404, detail="Device not found")
    await audit_log(db, org_id, actor, "device.updated", target=device_id, metadata=update)
    device = await db.devices.find_one({"id": device_id, "org_id": org_id}, {"_id": 0})
    return _project(device)


@router.patch("/{device_id}")
async def update_device(device_id: str, payload: DeviceUpdate, user: dict = Depends(require_role("technician"))):
    db = get_db()
    return await _apply_update(db, device_id, user["org_id"], payload, user)


@router.put("/{device_id}")
async def replace_device(device_id: str, payload: DeviceUpdate, user: dict = Depends(require_role("technician"))):
    """Full replace-style update. Missing optional fields will be set to null."""
    db = get_db()
    return await _apply_update(db, device_id, user["org_id"], payload, user)


@router.delete("/{device_id}")
async def delete_device(device_id: str, user: dict = Depends(require_role("admin"))):
    db = get_db()
    res = await db.devices.delete_one({"id": device_id, "org_id": user["org_id"]})
    if res.deleted_count == 0:
        raise HTTPException(status_code=404, detail="Device not found")
    await db.telemetry.delete_many({"device_id": device_id, "org_id": user["org_id"]})
    await db.alerts.delete_many({"device_id": device_id, "org_id": user["org_id"]})
    await db.actions.delete_many({"device_id": device_id, "org_id": user["org_id"]})
    await audit_log(db, user["org_id"], user, "device.removed", target=device_id)
    return {"ok": True}


@router.get("/{device_id}/telemetry")
async def get_device_telemetry(
    device_id: str,
    minutes: int = Query(default=60, ge=1, le=1440 * 7),
    limit: int = Query(default=500, ge=1, le=5000),
    user: dict = Depends(get_current_user),
):
    db = get_db()
    device = await db.devices.find_one({"id": device_id, "org_id": user["org_id"]}, {"_id": 0})
    if not device:
        raise HTTPException(status_code=404, detail="Device not found")
    since = (datetime.now(timezone.utc) - timedelta(minutes=minutes)).isoformat()
    cursor = db.telemetry.find(
        {"device_id": device_id, "org_id": user["org_id"], "ts": {"$gte": since}},
        {"_id": 0},
    ).sort("ts", 1).limit(limit)
    items = await cursor.to_list(limit)
    return [serialize(x) for x in items]
