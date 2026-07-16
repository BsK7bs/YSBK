"""WebSocket routes: agent telemetry channel and dashboard live channel."""
import base64
import gzip
import json
import logging
from datetime import datetime, timezone
from typing import Any

from fastapi import APIRouter, WebSocket, WebSocketDisconnect, Query, status

from ..database import get_db
from ..security import decode_token, hash_api_key
from ..services.alerts import evaluate_and_apply, evaluate_and_apply_inventory
from ..services.alerts.software_policy import upsert_catalog_from_device
from ..services.health import assess_device
from ..utils import utcnow
from ..websocket_manager import manager

logger = logging.getLogger("dta.ws")
telemetry_logger = logging.getLogger("dta.telemetry")
router = APIRouter(prefix="/ws", tags=["ws"])


def _maybe_inflate(msg: dict[str, Any]) -> dict[str, Any]:
    """If the frame arrived as {'type':'gz', 'payload': base64(gzip)}, inflate it."""
    if msg.get("type") == "gz" and "payload" in msg:
        try:
            raw = gzip.decompress(base64.b64decode(msg["payload"]))
            return json.loads(raw.decode("utf-8"))
        except Exception as exc:
            logger.warning("[ws-step] gz_inflate FAIL: %s", exc)
    return msg


async def _resolve_agent_device(key: str) -> dict | None:
    db = get_db()
    return await db.devices.find_one({"api_key_hash": hash_api_key(key)}, {"_id": 0})


@router.websocket("/agent")
async def ws_agent(
    websocket: WebSocket,
    api_key: str | None = Query(default=None),
    token: str | None = Query(default=None),
):
    """WebSocket for the desktop agent.

    Auth (any of):
      * ``?token=<device_access_token>``    -- new JWT flow (post /api/agent/pair)
      * ``?api_key=<device_api_key>``       -- legacy device-key flow
      * first frame ``{"type": "auth", "token"|"api_key": ...}``

    Emits ``[ws-step]`` structured log lines so ``/api/debug/pipeline/logs``
    can show whether the agent ever reached this endpoint and whether
    authentication succeeded.
    """
    client = f"{websocket.client.host}:{websocket.client.port}" if websocket.client else "?"
    await websocket.accept()
    logger.info("[ws-step] step=1_accepted client=%s has_token_query=%s has_api_key_query=%s",
                client, bool(token), bool(api_key))
    key = api_key
    jwt_tok = token
    if not key and not jwt_tok:
        try:
            first = await websocket.receive_json()
            if isinstance(first, dict) and first.get("type") == "auth":
                key = first.get("api_key")
                jwt_tok = first.get("token") or first.get("access_token")
                logger.info("[ws-step] step=2_auth_frame_received client=%s has_key=%s has_token=%s",
                            client, bool(key), bool(jwt_tok))
        except Exception as exc:
            logger.warning(
                "[ws-step] step=2_auth_frame_received verdict=FAIL exception=%s: %s client=%s",
                type(exc).__name__, exc, client,
            )
            await websocket.close(code=4401)
            return

    device: dict | None = None
    if jwt_tok:
        # ---- JWT flow (new): decode + look up device by id ----
        try:
            claims = decode_token(jwt_tok)
        except Exception as exc:
            logger.warning("[ws-step] step=3_jwt_decode verdict=FAIL exc=%s client=%s", exc, client)
            await websocket.close(code=4401)
            return
        if claims.get("type") != "device_access" or claims.get("kind") != "device":
            logger.warning("[ws-step] step=3_jwt_decode verdict=FAIL reason=wrong_type client=%s", client)
            await websocket.close(code=4401)
            return
        device_id = claims.get("sub")
        org_id_claim = claims.get("org_id")
        if not (device_id and org_id_claim):
            await websocket.close(code=4401); return
        db = get_db()
        device = await db.devices.find_one({"id": device_id, "org_id": org_id_claim}, {"_id": 0})
        if not device:
            logger.warning("[ws-step] step=4_jwt_lookup verdict=FAIL device_id=%s", device_id)
            await websocket.close(code=4403); return
        logger.info("[ws-step] step=4_jwt_lookup verdict=OK device_id=%s", device_id)
    elif key:
        device = await _resolve_agent_device(key)
        if not device:
            logger.warning(
                "[ws-step] step=4_key_resolve verdict=FAIL reason=no_matching_device "
                "client=%s key_prefix=%s...",
                client, key[:8],
            )
            await websocket.close(code=4403)
            return
    else:
        logger.warning("[ws-step] step=3_key_present verdict=FAIL reason=missing client=%s", client)
        await websocket.close(code=4401)
        return

    device_id = device["id"]
    org_id = device["org_id"]
    logger.info(
        "[ws-step] step=4_key_resolve verdict=OK device_id=%s hostname=%s org=%s client=%s",
        device_id, device.get("hostname"), org_id, client,
    )
    db = get_db()

    await manager.connect_device(device_id, websocket)
    now = utcnow()
    await db.devices.update_one(
        {"id": device_id},
        {"$set": {"is_online": True, "last_seen": now.isoformat()}},
    )
    await manager.broadcast_to_org(org_id, {
        "type": "device.online",
        "device_id": device_id,
        "ts": now.isoformat(),
    })
    logger.info(
        "[ws-step] step=5_device_marked_online verdict=OK device_id=%s hostname=%s",
        device_id, device.get("hostname"),
    )
    await websocket.send_json({"type": "hello", "device_id": device_id, "server_time": now.isoformat()})

    frames_received = 0
    try:
        while True:
            raw = await websocket.receive_text()
            try:
                msg: dict[str, Any] = json.loads(raw)
            except json.JSONDecodeError:
                logger.warning("[ws-step] step=6_invalid_json device_id=%s size=%d",
                               device_id, len(raw))
                await websocket.send_json({"type": "error", "error": "invalid_json"})
                continue
            frames_received += 1
            msg = _maybe_inflate(msg)
            ack_id = msg.get("ack_id")
            await _handle_agent_message(db, device_id, org_id, msg)
            ack_payload = {"type": "ack", "kind": msg.get("type", "unknown")}
            if ack_id:
                ack_payload["ack_id"] = ack_id
            await websocket.send_json(ack_payload)
    except WebSocketDisconnect:
        logger.info(
            "[ws-step] step=99_disconnect device_id=%s frames_received=%d",
            device_id, frames_received,
        )
    except Exception as e:
        logger.exception(
            "[ws-step] step=99_disconnect device_id=%s frames_received=%d exception=%s",
            device_id, frames_received, e,
        )
    finally:
        await manager.disconnect_device(device_id, websocket)
        now = utcnow()
        await db.devices.update_one({"id": device_id}, {"$set": {"is_online": False}})
        await manager.broadcast_to_org(org_id, {
            "type": "device.offline",
            "device_id": device_id,
            "ts": now.isoformat(),
        })


async def _handle_agent_message(db, device_id: str, org_id: str, msg: dict[str, Any]) -> None:
    kind = msg.get("type", "metrics")
    now_iso = utcnow().isoformat()

    if kind in ("heartbeat", "ping"):
        telemetry_logger.info(
            "[telemetry-step] step=heartbeat device_id=%s", device_id,
        )
        await db.devices.update_one({"id": device_id}, {"$set": {"is_online": True, "last_seen": now_iso}})
        return

    if kind == "metrics":
        metrics = msg.get("metrics") or {}
        ts = msg.get("ts") or now_iso
        telemetry_logger.info(
            "[telemetry-step] step=metrics_received device_id=%s ts=%s keys=%d",
            device_id, ts, len(metrics),
        )
        # store a compact telemetry point
        telemetry_doc = {
            "device_id": device_id,
            "org_id": org_id,
            "ts": ts,
            "metrics": metrics,
        }
        try:
            await db.telemetry.insert_one(telemetry_doc)
            telemetry_logger.info(
                "[telemetry-step] step=metrics_stored verdict=OK device_id=%s ts=%s",
                device_id, ts,
            )
        except Exception as exc:
            telemetry_logger.exception(
                "[telemetry-step] step=metrics_stored verdict=FAIL device_id=%s exception=%s",
                device_id, exc,
            )
            return

        # Pull the device (with latest inventory) then recompute a full
        # explainable health assessment using the pluggable engine.
        current_device = await db.devices.find_one({"id": device_id}, {"_id": 0}) or {}
        # Include the fresh metrics into the context (they haven't been
        # persisted onto the device yet at this point).
        current_device["latest_metrics"] = metrics
        current_device["is_online"] = True
        current_device["last_seen"] = now_iso

        # Recent timeline (used for trend detection)
        timeline = await db.health_timeline.find(
            {"device_id": device_id, "org_id": org_id},
            {"_id": 0, "score": 1, "ts": 1},
        ).sort("ts", -1).limit(30).to_list(30)
        timeline.reverse()

        assessment = assess_device({
            "device": current_device,
            "metrics": metrics,
            "inventory": current_device.get("inventory") or {},
            "recent_alerts": [],
            "recent_telemetry": [],
            "timeline": timeline,
        })
        # Persist the timeline snapshot for /health/timeline queries.
        await db.health_timeline.insert_one({
            "device_id": device_id,
            "org_id": org_id,
            "ts": now_iso,
            "engine_version": assessment.engine_version,
            "score": assessment.score,
            "tier": assessment.tier,
            "trend": assessment.trend,
            "failure_risk_percent": assessment.failure_risk_percent,
            "confidence_percent": assessment.confidence_percent,
            "data_completeness_percent": assessment.data_completeness_percent,
        })

        # Map engine tier \u2192 legacy risk_level buckets used by existing UI.
        tier_to_risk = {
            "excellent": "healthy",
            "good": "healthy",
            "warning": "warning",
            "critical": "critical",
        }
        risk = tier_to_risk.get(assessment.tier, "warning")
        device_update = {
            "latest_metrics": metrics,
            "last_seen": now_iso,
            "is_online": True,
            "health_score": assessment.score,
            "risk_level": risk,
            "health_tier": assessment.tier,
            "health_trend": assessment.trend,
            "failure_risk_percent": assessment.failure_risk_percent,
            "confidence_percent": assessment.confidence_percent,
            "data_completeness_percent": assessment.data_completeness_percent,
            "latest_health_assessment": assessment.to_public_dict(),
        }
        await db.devices.update_one({"id": device_id}, {"$set": device_update})
        device = await db.devices.find_one({"id": device_id}, {"_id": 0})

        # Run the production alert engine (dwell-aware, escalating,
        # dedup + notify). It handles broadcasting alert lifecycle events.
        try:
            await evaluate_and_apply(db, device, metrics, manager)
        except Exception as exc:
            logger.warning("alert engine failed for %s: %s", device_id, exc)

        await manager.broadcast_to_org(org_id, {
            "type": "telemetry",
            "device_id": device_id,
            "ts": ts,
            "metrics": metrics,
            "health_score": assessment.score,
            "risk_level": risk,
            "health": {
                "score": assessment.score,
                "tier": assessment.tier,
                "trend": assessment.trend,
                "failure_risk_percent": assessment.failure_risk_percent,
                "confidence_percent": assessment.confidence_percent,
                "data_completeness_percent": assessment.data_completeness_percent,
                "engine_version": assessment.engine_version,
            },
        })
        return

    if kind == "inventory":
        inventory = msg.get("inventory") or {}
        set_fields: dict = {"inventory": inventory, "last_seen": now_iso}
        # Promote common inventory fields to top-level for search/filter/table
        promote_map = {
            "ip_address": "ip_address",
            "mac_address": "mac_address",
            "serial_number": "serial_number",
            "cpu_model": "cpu",
            "cpu": "cpu",
            "ram_total_gb": "ram_gb",
            "ram_gb": "ram_gb",
            "disk_total_gb": "disk_gb",
            "disk_gb": "disk_gb",
            "motherboard": "motherboard",
            "bios_version": "bios_version",
        }
        for src, dst in promote_map.items():
            if src in inventory and inventory[src] is not None:
                set_fields[dst] = inventory[src]
        # If disks list is present, sum totals
        if "disks" in inventory and isinstance(inventory["disks"], list):
            try:
                total_gb = sum(float(d.get("total_gb") or 0) for d in inventory["disks"])
                if total_gb:
                    set_fields.setdefault("disk_gb", total_gb)
            except Exception:
                pass
        await db.devices.update_one({"id": device_id}, {"$set": set_fields})

        # -- Refresh org software catalog + diff for new/removed/version_changed --
        try:
            await upsert_catalog_from_device(db, org_id, device_id, inventory)
        except Exception as exc:  # pragma: no cover - defensive
            telemetry_logger.warning("[inventory] catalog refresh failed device=%s exc=%s", device_id, exc)

        # -- Run inventory-based alert rules (software policy violations etc.) --
        try:
            device_ctx = await db.devices.find_one({"id": device_id}, {"_id": 0}) or {}
            await evaluate_and_apply_inventory(db, org_id, device_ctx, inventory, manager)
        except Exception as exc:  # pragma: no cover
            telemetry_logger.warning("[inventory] alert eval failed device=%s exc=%s", device_id, exc)

        await manager.broadcast_to_org(org_id, {
            "type": "inventory",
            "device_id": device_id,
            "ts": now_iso,
        })
        return

    if kind == "event":
        event = msg.get("event") or {}
        # Persist as an audit event under the org
        await db.audit_events.insert_one({
            "id": __import__("uuid").uuid4().hex,
            "org_id": org_id,
            "actor_id": None,
            "actor_email": None,
            "kind": f"agent.{event.get('kind', 'event')}",
            "target": device_id,
            "metadata": event,
            "ts": now_iso,
        })
        return

    if kind == "action_result":
        action_id = msg.get("action_id")
        if action_id:
            update = {
                "status": msg.get("status", "succeeded"),
                "result": msg.get("result"),
                "error": msg.get("error"),
                "finished_at": now_iso,
            }
            await db.actions.update_one({"id": action_id, "device_id": device_id}, {"$set": update})
        return


@router.websocket("/dashboard")
async def ws_dashboard(websocket: WebSocket, token: str | None = Query(default=None)):
    """WebSocket for authenticated dashboard users. Auth via ?token=<access_jwt>."""
    await websocket.accept()
    if not token:
        try:
            first = await websocket.receive_json()
            if isinstance(first, dict) and first.get("type") == "auth":
                token = first.get("token")
        except Exception:
            await websocket.close(code=4401)
            return
    if not token:
        await websocket.close(code=4401)
        return
    try:
        payload = decode_token(token)
        if payload.get("type") != "access":
            raise ValueError("not access")
        org_id = payload["org_id"]
    except Exception:
        await websocket.close(code=4401)
        return

    await manager.subscribe_org(org_id, websocket)
    await websocket.send_json({"type": "subscribed", "org_id": org_id, "ts": utcnow().isoformat()})
    try:
        while True:
            # Keep connection open; ignore incoming messages except pings
            data = await websocket.receive_text()
            if data:
                try:
                    m = json.loads(data)
                    if m.get("type") == "ping":
                        await websocket.send_json({"type": "pong", "ts": utcnow().isoformat()})
                except Exception:
                    pass
    except WebSocketDisconnect:
        pass
    finally:
        await manager.unsubscribe_org(org_id, websocket)


# ---------------------------------------------------------------------------
# Public demo channel for the landing page 3D scene (no auth).
# Streams synthetic telemetry for a given "node_id" so the marketing site can
# show a live-updating device modal without exposing any real device data.
# ---------------------------------------------------------------------------

import asyncio
import hashlib
import math
import random


@router.websocket("/demo/{node_id}")
async def ws_demo(websocket: WebSocket, node_id: str):
    """Public demo telemetry stream used by the landing hero.

    Deterministic per-node baselines (hash of node_id) with per-tick jitter,
    emitted at ~1 Hz. No auth, no DB writes, safe to expose publicly.
    """
    await websocket.accept()

    # Deterministic per-node baselines
    seed = int(hashlib.md5(node_id.encode()).hexdigest()[:8], 16)
    rng = random.Random(seed)
    hostname_pool = [
        "LAB-PC-{n:02d}", "STUDIO-{n:02d}", "EDU-BOX-{n:02d}",
        "ENG-WKS-{n:02d}", "MSP-CLIENT-{n:02d}", "DEV-{n:02d}",
    ]
    hostname = rng.choice(hostname_pool).format(n=(seed % 90) + 10)
    os_name = rng.choice(["Windows 11 Pro", "Windows 11 Ent", "Windows 10 Pro"])
    cpu_model = rng.choice([
        "Intel Core i5-13400", "Intel Core i7-13700",
        "AMD Ryzen 5 7600", "AMD Ryzen 7 7700X",
    ])
    ram_gb = rng.choice([16, 32, 64])
    base_cpu = rng.uniform(20, 55)
    base_ram = rng.uniform(45, 72)
    base_temp = rng.uniform(52, 68)
    base_health = rng.uniform(82, 97)
    uptime_days = rng.randint(1, 42)
    disk_used_pct = rng.uniform(38, 78)

    started = datetime.now(timezone.utc)

    try:
        tick = 0
        while True:
            tick += 1
            # Smooth oscillating values with light noise
            cpu = max(3, min(99, base_cpu + math.sin(tick / 6.0) * 12 + rng.uniform(-3, 3)))
            ram = max(20, min(96, base_ram + math.cos(tick / 8.0) * 5 + rng.uniform(-1.5, 1.5)))
            temp = max(35, min(95, base_temp + math.sin(tick / 5.0) * 6 + rng.uniform(-1.2, 1.2)))
            health = max(40, min(100, base_health + math.sin(tick / 11.0) * 3))
            net_rx = max(0, math.sin(tick / 3.0) * 240 + rng.uniform(20, 90))
            net_tx = max(0, math.cos(tick / 4.0) * 180 + rng.uniform(10, 60))

            # Occasional alert to make it feel alive
            recent_events = []
            if tick % 12 == 0:
                recent_events.append({
                    "severity": rng.choice(["info", "warning"]),
                    "text": rng.choice([
                        "SMART self-test passed",
                        "Windows update ready",
                        "Antivirus definitions updated",
                        "Background inventory refresh",
                    ]),
                })

            payload = {
                "type": "telemetry",
                "node_id": node_id,
                "hostname": hostname,
                "os": os_name,
                "cpu_model": cpu_model,
                "ram_gb": ram_gb,
                "uptime_days": uptime_days,
                "disk_used_pct": round(disk_used_pct, 1),
                "metrics": {
                    "cpu_pct": round(cpu, 1),
                    "ram_pct": round(ram, 1),
                    "temp_c": round(temp, 1),
                    "net_rx_kbps": round(net_rx, 0),
                    "net_tx_kbps": round(net_tx, 0),
                    "health_score": round(health, 1),
                },
                "recent_events": recent_events,
                "tick": tick,
                "ts": datetime.now(timezone.utc).isoformat(),
            }
            await websocket.send_json(payload)
            await asyncio.sleep(1.0)
    except WebSocketDisconnect:
        pass
    except Exception as exc:  # noqa: BLE001
        logger.warning("demo ws error: %s", exc)
