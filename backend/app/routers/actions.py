"""Remote Management routes.

Design principles
-----------------
* **RBAC per kind** — read-only kinds are ``technician+``; every destructive
  kind (see ``DESTRUCTIVE_ACTION_KINDS``) is ``admin+``.
* **Explicit confirmation** — destructive kinds must be sent with
  ``confirm: true``. This prevents accidental fire-off via API clients or
  browser autocompletion.
* **TTL** — every action carries an ``expires_at`` (default 15 min). The
  agent MUST refuse to execute stale commands, and a background sweep marks
  them ``expired`` in the database.
* **Rate limiting** — a device cannot have more than ``MAX_PENDING_PER_DEVICE``
  actions queued at once; further POSTs receive 429.
* **Full audit trail** — every enqueue / cancel / execution records an
  ``action.*`` event with the actor, target, kind, and params.
* **Parameter validation** — each kind has a small validator that runs
  before the action is persisted; invalid params return 400 with a clear
  message rather than silently failing on the endpoint.
"""
from __future__ import annotations

import base64
from datetime import datetime, timedelta, timezone
from typing import Any

from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile

from ..database import get_db
from ..deps import audit_log, get_current_user, get_device_from_api_key, require_role
from ..models import (
    ActionBatch,
    ActionUpdate,
    BulkActionCreate,
    DESTRUCTIVE_ACTION_KINDS,
    RemoteAction,
    RemoteActionCreate,
)
from ..utils import serialize, utcnow
from ..websocket_manager import manager

router = APIRouter(prefix="/actions", tags=["actions"])

# --- Security knobs ------------------------------------------------------
MAX_PENDING_PER_DEVICE = 20
MAX_SCRIPT_SIZE_BYTES = 64 * 1024        # scripts / cmd / powershell commands
MAX_ARTIFACT_SIZE_BYTES = 5 * 1024 * 1024  # 5 MB per uploaded log-zip
ARTIFACT_TTL_HOURS = 72
# Kinds that require admin+ role. Kept in sync with DESTRUCTIVE_ACTION_KINDS
# but reads as a separate constant so we can add "sensitive but non-destructive"
# kinds here in the future without touching the model.
ADMIN_ONLY_KINDS = set(DESTRUCTIVE_ACTION_KINDS)


# --- Per-kind param validation ------------------------------------------

def _validate_params(kind: str, params: dict[str, Any]) -> dict[str, Any]:
    """Return a *sanitised* copy of ``params`` or raise HTTPException(400)."""
    p = dict(params or {})

    def _need(name: str, typ) -> Any:
        v = p.get(name)
        if v is None or not isinstance(v, typ):
            raise HTTPException(status_code=400, detail=f"'{name}' is required for {kind}")
        return v

    def _cap_str(name: str, max_len: int) -> None:
        v = p.get(name)
        if v is not None and isinstance(v, str) and len(v.encode("utf-8")) > max_len:
            raise HTTPException(status_code=400,
                                detail=f"'{name}' exceeds {max_len} bytes for {kind}")

    if kind == "restart_service":
        _need("service_name", str)
    elif kind == "kill_process":
        # Either pid (int) OR name (str).
        if not (isinstance(p.get("pid"), int) or isinstance(p.get("name"), str)):
            raise HTTPException(status_code=400, detail="Provide 'pid' or 'name' for kill_process")
    elif kind == "run_script":
        _need("script", str)
        _cap_str("script", MAX_SCRIPT_SIZE_BYTES)
        # Interpreter defaults to platform shell; allow 'python' | 'bash' | 'powershell' | 'cmd'.
        interp = p.get("interpreter", "auto")
        if interp not in ("auto", "python", "bash", "powershell", "cmd"):
            raise HTTPException(status_code=400, detail="Invalid 'interpreter'")
    elif kind in ("exec_cmd", "exec_powershell"):
        _need("command", str)
        _cap_str("command", MAX_SCRIPT_SIZE_BYTES)
    elif kind == "install_software":
        _need("package", str)
        source = p.get("source", "winget")
        if source not in ("winget", "choco", "apt", "url"):
            raise HTTPException(status_code=400, detail="'source' must be winget|choco|apt|url")
        if source == "url" and not isinstance(p.get("url"), str):
            raise HTTPException(status_code=400, detail="'url' is required when source=url")
    elif kind == "uninstall_software":
        _need("package", str)
    elif kind == "collect_event_logs":
        # channel: System | Application | Security (Windows) — optional whitelist filter
        channels = p.get("channels")
        if channels is not None and not isinstance(channels, list):
            raise HTTPException(status_code=400, detail="'channels' must be a list of channel names")
        max_events = p.get("max_events", 500)
        if not isinstance(max_events, int) or not (1 <= max_events <= 10000):
            raise HTTPException(status_code=400, detail="'max_events' must be 1..10000")
    elif kind in ("collect_diagnostic", "collect_crash_dumps", "restart_agent"):
        pass  # no params
    elif kind in ("refresh_telemetry", "refresh_software", "run_health_check"):
        pass  # no params — these are simple "do it now" pokes
    elif kind == "remote_desktop":
        # Future: caller may supply a ``session_ttl_min`` hint.
        ttl = p.get("session_ttl_min", 30)
        if not isinstance(ttl, int) or not (1 <= ttl <= 240):
            raise HTTPException(status_code=400, detail="'session_ttl_min' must be 1..240")
    elif kind == "file_transfer":
        # Future: {direction: 'push'|'pull', src, dst, sha256?}
        direction = p.get("direction")
        if direction not in ("push", "pull"):
            raise HTTPException(status_code=400, detail="'direction' must be push|pull")
        _need("src", str)
        _need("dst", str)
    elif kind == "patch_deployment":
        # Future: {kb: 'KB5030310'} or {package: 'winget-id'}
        if not (isinstance(p.get("kb"), str) or isinstance(p.get("package"), str)):
            raise HTTPException(status_code=400, detail="Provide 'kb' or 'package' for patch_deployment")
    # sleep / lock / restart / shutdown / clear_temp / refresh_inventory /
    # run_windows_update / download_logs need no params.
    return p


# --- Endpoints ----------------------------------------------------------

@router.get("")
async def list_actions(
    device_id: str | None = None,
    status: str | None = None,
    limit: int = 100,
    user: dict = Depends(get_current_user),
):
    db = get_db()
    query: dict = {"org_id": user["org_id"]}
    if device_id:
        query["device_id"] = device_id
    if status:
        query["status"] = status
    items = await db.actions.find(query, {"_id": 0}).sort("created_at", -1).limit(limit).to_list(limit)
    return [serialize(x) for x in items]


@router.get("/kinds")
async def list_supported_kinds(user: dict = Depends(get_current_user)):
    """Return the catalog of supported kinds + which ones require admin+ role."""
    supported_now = [
        # Power & lifecycle
        "restart", "shutdown", "sleep", "lock",
        # Agent & service lifecycle
        "restart_agent", "restart_service",
        # Refreshes / on-demand collection
        "refresh_telemetry", "refresh_inventory", "refresh_software",
        "run_health_check", "collect_diagnostic",
        # Existing execution primitives
        "run_script", "exec_cmd", "exec_powershell",
        "kill_process", "install_software", "uninstall_software",
        "clear_temp", "run_windows_update", "download_logs",
        "collect_event_logs", "collect_crash_dumps",
    ]
    # Declared today; the agent will execute them in a future release.
    # Included so the dashboard can render the buttons (disabled) and so
    # integrators can start POSTing them without waiting on a schema bump.
    future_kinds = ["remote_desktop", "file_transfer", "patch_deployment"]
    return {
        "kinds": supported_now,
        "future_kinds": future_kinds,
        "admin_only": sorted(ADMIN_ONLY_KINDS),
        "requires_confirm": sorted(DESTRUCTIVE_ACTION_KINDS),
    }


@router.post("/devices/{device_id}")
async def enqueue_action(
    device_id: str,
    payload: RemoteActionCreate,
    # We authenticate as technician+ and then enforce admin+ for destructive
    # kinds below so the error message can be more explicit than a raw 403.
    user: dict = Depends(require_role("technician")),
):
    kind = payload.kind
    _authorize_kind(kind, payload.confirm, user)
    params = _validate_params(kind, payload.params)

    db = get_db()
    device = await db.devices.find_one({"id": device_id, "org_id": user["org_id"]}, {"_id": 0})
    if not device:
        raise HTTPException(status_code=404, detail="Device not found")

    doc = await _enqueue_action_doc(
        db=db, user=user, device=device, kind=kind, params=params,
        ttl_seconds=payload.ttl_seconds, batch_id=None, parent_action_id=None,
    )
    return serialize(doc)


# --- Bulk / batch action enqueue ---

@router.post("/bulk")
async def enqueue_bulk_action(
    payload: BulkActionCreate,
    user: dict = Depends(require_role("technician")),
):
    """Enqueue the same action across many devices atomically.

    Devices are resolved from the union of ``device_ids`` and every device that
    belongs to any of ``group_ids``. Devices that are already at the pending
    cap are skipped with a per-device error rather than aborting the batch.
    A parent ``ActionBatch`` document is created and each per-device action
    references it via ``batch_id`` so the UI can render progress rows.
    """
    kind = payload.kind
    _authorize_kind(kind, payload.confirm, user)
    params = _validate_params(kind, payload.params)

    db = get_db()
    # Resolve devices from ids + groups
    device_ids: set[str] = set(payload.device_ids or [])
    if payload.group_ids:
        cursor = db.devices.find(
            {"org_id": user["org_id"], "group_ids": {"$in": list(payload.group_ids)}},
            {"id": 1, "_id": 0},
        )
        async for d in cursor:
            device_ids.add(d["id"])
    if not device_ids:
        raise HTTPException(status_code=400, detail="No devices resolved from device_ids/group_ids")
    if len(device_ids) > 500:
        raise HTTPException(status_code=400, detail="Bulk action limited to 500 devices at once")

    # Load matching devices (org-scoped)
    devices = await db.devices.find(
        {"org_id": user["org_id"], "id": {"$in": list(device_ids)}}, {"_id": 0}
    ).to_list(len(device_ids))
    if not devices:
        raise HTTPException(status_code=404, detail="No matching devices found")

    batch = ActionBatch(
        org_id=user["org_id"],
        kind=kind,
        params=params,
        label=payload.label,
        created_by=user["id"],
        created_by_email=user.get("email"),
        total=len(devices),
        device_ids=[d["id"] for d in devices],
    )
    batch_doc = batch.model_dump()
    batch_doc["created_at"] = batch_doc["created_at"].isoformat()

    enqueued = []
    skipped = []
    for device in devices:
        # Skip devices currently in maintenance for destructive kinds
        if device.get("maintenance_mode") and kind in DESTRUCTIVE_ACTION_KINDS \
                and kind not in ("collect_event_logs", "collect_diagnostic", "collect_crash_dumps",
                                  "download_logs", "refresh_inventory"):
            skipped.append({"device_id": device["id"], "reason": "device in maintenance mode"})
            continue
        try:
            doc = await _enqueue_action_doc(
                db=db, user=user, device=device, kind=kind, params=params,
                ttl_seconds=payload.ttl_seconds, batch_id=batch_doc["id"],
                parent_action_id=None,
            )
            enqueued.append(doc)
            batch_doc["action_ids"].append(doc["id"])
        except HTTPException as e:
            skipped.append({"device_id": device["id"], "reason": e.detail})

    batch_doc["total"] = len(enqueued)
    await db.action_batches.insert_one(batch_doc)
    await audit_log(
        db, user["org_id"], user, "action.batch_enqueued",
        target=batch_doc["id"],
        metadata={"kind": kind, "count": len(enqueued),
                  "skipped": len(skipped),
                  "params_preview": _params_preview(params)},
    )
    return {
        "batch_id": batch_doc["id"],
        "total": len(enqueued),
        "skipped": skipped,
        "actions": [serialize(a) for a in enqueued],
    }


@router.get("/batches")
async def list_action_batches(
    limit: int = 50,
    user: dict = Depends(get_current_user),
):
    db = get_db()
    items = await db.action_batches.find(
        {"org_id": user["org_id"]}, {"_id": 0}
    ).sort("created_at", -1).limit(limit).to_list(limit)
    # Aggregate per-status counts per batch
    out = []
    for b in items:
        counts = await _batch_status_counts(db, b["id"])
        out.append({**serialize(b), "status_counts": counts})
    return out


@router.get("/batches/{batch_id}")
async def get_action_batch(
    batch_id: str,
    user: dict = Depends(get_current_user),
):
    db = get_db()
    b = await db.action_batches.find_one({"id": batch_id, "org_id": user["org_id"]}, {"_id": 0})
    if not b:
        raise HTTPException(status_code=404, detail="Batch not found")
    counts = await _batch_status_counts(db, batch_id)
    actions = await db.actions.find(
        {"batch_id": batch_id}, {"_id": 0}
    ).sort("created_at", 1).to_list(1000)
    # Include device hostname for UI display
    device_ids = [a.get("device_id") for a in actions if a.get("device_id")]
    devices = await db.devices.find(
        {"id": {"$in": device_ids}}, {"_id": 0, "id": 1, "hostname": 1, "display_name": 1}
    ).to_list(len(device_ids))
    dmap = {d["id"]: d for d in devices}
    for a in actions:
        d = dmap.get(a["device_id"], {})
        a["device_hostname"] = d.get("hostname")
        a["device_display_name"] = d.get("display_name")
    return {**serialize(b), "status_counts": counts, "actions": [serialize(a) for a in actions]}


@router.post("/{action_id}/retry")
async def retry_action(
    action_id: str,
    user: dict = Depends(require_role("technician")),
):
    """Re-queue a failed / expired / cancelled action with the same kind + params."""
    db = get_db()
    prev = await db.actions.find_one({"id": action_id, "org_id": user["org_id"]}, {"_id": 0})
    if not prev:
        raise HTTPException(status_code=404, detail="Action not found")
    if prev["status"] in ("pending", "in_progress"):
        raise HTTPException(status_code=400, detail="Action is still active — cannot retry")
    kind = prev["kind"]
    _authorize_kind(kind, True, user)  # implicit confirm on retry (was already confirmed)
    device = await db.devices.find_one({"id": prev["device_id"], "org_id": user["org_id"]}, {"_id": 0})
    if not device:
        raise HTTPException(status_code=404, detail="Device no longer exists")

    doc = await _enqueue_action_doc(
        db=db, user=user, device=device, kind=kind,
        params=prev.get("params") or {},
        ttl_seconds=900,
        batch_id=prev.get("batch_id"),
        parent_action_id=action_id,
    )
    return serialize(doc)


@router.post("/{action_id}/cancel")
async def cancel_action(
    action_id: str,
    user: dict = Depends(require_role("technician")),
):
    db = get_db()
    action = await db.actions.find_one({"id": action_id, "org_id": user["org_id"]}, {"_id": 0})
    if not action:
        raise HTTPException(status_code=404, detail="Action not found")
    if action["status"] not in ("pending", "in_progress"):
        raise HTTPException(status_code=400,
                            detail=f"Cannot cancel an action in status '{action['status']}'")
    await db.actions.update_one(
        {"id": action_id},
        {"$set": {"status": "cancelled", "finished_at": utcnow().isoformat()}},
    )
    await audit_log(db, user["org_id"], user, "action.cancelled",
                    target=action["device_id"], metadata={"kind": action["kind"], "action_id": action_id})
    return {"ok": True}


@router.get("/{action_id}/artifact")
async def download_action_artifact(
    action_id: str,
    user: dict = Depends(get_current_user),
):
    """Return the artifact (e.g. log zip) produced by a completed action.

    We return the artifact base64-encoded so clients don't need to negotiate
    a signed URL. Artifacts older than ``ARTIFACT_TTL_HOURS`` are purged by
    the background sweep and return 404.
    """
    db = get_db()
    art = await db.action_artifacts.find_one(
        {"action_id": action_id, "org_id": user["org_id"]}, {"_id": 0}
    )
    if not art:
        raise HTTPException(status_code=404, detail="Artifact not found or expired")
    return {
        "action_id": action_id,
        "filename": art.get("filename") or f"{action_id}.zip",
        "content_type": art.get("content_type") or "application/octet-stream",
        "size_bytes": art.get("size_bytes"),
        "created_at": art.get("created_at"),
        # Content is stored base64-encoded already.
        "content_b64": art.get("content_b64"),
    }


# --- Agent-facing endpoints ---------------------------------------------

agent_router = APIRouter(prefix="/agent", tags=["agent"])


@agent_router.get("/actions/pending")
async def pending_actions_for_agent(device: dict = Depends(get_device_from_api_key)):
    db = get_db()
    items = await db.actions.find(
        {"device_id": device["id"], "status": "pending"}, {"_id": 0}
    ).sort("created_at", 1).to_list(50)
    return [serialize(x) for x in items]


@agent_router.patch("/actions/{action_id}")
async def update_action_from_agent(
    action_id: str,
    payload: ActionUpdate,
    device: dict = Depends(get_device_from_api_key),
):
    db = get_db()
    action = await db.actions.find_one({"id": action_id, "device_id": device["id"]}, {"_id": 0})
    if not action:
        raise HTTPException(status_code=404, detail="Action not found")
    update: dict = {"status": payload.status}
    now = utcnow().isoformat()
    if payload.status == "in_progress" and not action.get("started_at"):
        update["started_at"] = now
    if payload.status in ("succeeded", "failed", "cancelled", "expired"):
        update["finished_at"] = now
    if payload.result is not None:
        update["result"] = payload.result
    if payload.error is not None:
        update["error"] = payload.error
    await db.actions.update_one({"id": action_id}, {"$set": update})
    return {"ok": True}


@agent_router.post("/actions/{action_id}/artifact")
async def upload_action_artifact(
    action_id: str,
    file: UploadFile = File(...),
    filename: str = Form(None),
    device: dict = Depends(get_device_from_api_key),
):
    """Agent-only: upload a small artifact (e.g. a log zip) tied to an action."""
    db = get_db()
    action = await db.actions.find_one({"id": action_id, "device_id": device["id"]}, {"_id": 0})
    if not action:
        raise HTTPException(status_code=404, detail="Action not found")
    contents = await file.read()
    if len(contents) > MAX_ARTIFACT_SIZE_BYTES:
        raise HTTPException(status_code=413,
                            detail=f"Artifact exceeds {MAX_ARTIFACT_SIZE_BYTES // 1024 // 1024} MB limit")
    # Replace any prior artifact for this action.
    await db.action_artifacts.delete_many({"action_id": action_id})
    await db.action_artifacts.insert_one({
        "action_id": action_id,
        "org_id": action["org_id"],
        "device_id": action["device_id"],
        "filename": filename or file.filename or f"{action_id}.zip",
        "content_type": file.content_type or "application/octet-stream",
        "size_bytes": len(contents),
        "content_b64": base64.b64encode(contents).decode("ascii"),
        "created_at": utcnow().isoformat(),
    })
    return {"ok": True, "size_bytes": len(contents)}


# --- Helpers ------------------------------------------------------------

def _authorize_kind(kind: str, confirm: bool, user: dict) -> None:
    """Enforce RBAC + explicit-confirm gate for destructive kinds."""
    if kind in ADMIN_ONLY_KINDS:
        if user.get("role") not in ("admin", "owner"):
            raise HTTPException(status_code=403,
                                detail=f"'{kind}' requires the 'admin' role or higher")
        if not confirm:
            raise HTTPException(status_code=400,
                                detail=f"'{kind}' is a destructive action — please resend with confirm=true")


async def _enqueue_action_doc(
    *,
    db,
    user: dict,
    device: dict,
    kind: str,
    params: dict[str, Any],
    ttl_seconds: int,
    batch_id: str | None,
    parent_action_id: str | None,
) -> dict:
    """Insert an action, enforce per-device rate limit, audit-log, and push to agent."""
    device_id = device["id"]
    pending_count = await db.actions.count_documents(
        {"device_id": device_id, "status": {"$in": ["pending", "in_progress"]}}
    )
    if pending_count >= MAX_PENDING_PER_DEVICE:
        raise HTTPException(status_code=429,
                            detail=f"Device already has {pending_count} in-flight actions "
                                   f"(max {MAX_PENDING_PER_DEVICE}). Wait for them to complete.")

    now = utcnow()
    action = RemoteAction(
        org_id=user["org_id"],
        device_id=device_id,
        kind=kind,  # type: ignore[arg-type]
        params=params,
        created_by=user["id"],
        created_by_email=user.get("email"),
        expires_at=now + timedelta(seconds=ttl_seconds),
        batch_id=batch_id,
        parent_action_id=parent_action_id,
    )
    doc = action.model_dump()
    doc["created_at"] = doc["created_at"].isoformat()
    if doc.get("expires_at"):
        doc["expires_at"] = doc["expires_at"].isoformat()
    await db.actions.insert_one(doc)

    await audit_log(
        db, user["org_id"], user, "action.enqueued",
        target=device_id,
        metadata={"kind": kind, "action_id": doc["id"],
                  "batch_id": batch_id,
                  "parent_action_id": parent_action_id,
                  "params_preview": _params_preview(params)},
    )

    # Real-time push
    await manager.send_to_device(device_id, {
        "type": "action",
        "action": {
            "id": doc["id"],
            "kind": kind,
            "params": params,
            "expires_at": doc.get("expires_at"),
        },
    })
    return doc


async def _batch_status_counts(db, batch_id: str) -> dict[str, int]:
    """Aggregate per-status counts for a batch."""
    pipeline = [
        {"$match": {"batch_id": batch_id}},
        {"$group": {"_id": "$status", "n": {"$sum": 1}}},
    ]
    out: dict[str, int] = {
        "pending": 0, "in_progress": 0, "succeeded": 0,
        "failed": 0, "cancelled": 0, "expired": 0,
    }
    async for row in db.actions.aggregate(pipeline):
        if row["_id"] in out:
            out[row["_id"]] = row["n"]
    out["total"] = sum(out.values())
    return out


def _params_preview(params: dict[str, Any]) -> dict[str, Any]:
    """Redact / shorten params for audit-log storage."""
    out: dict[str, Any] = {}
    for k, v in (params or {}).items():
        if isinstance(v, str):
            out[k] = v[:200] + ("…" if len(v) > 200 else "")
        else:
            out[k] = v
    return out
