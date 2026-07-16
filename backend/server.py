"""Digital Twin Platform - FastAPI application entrypoint."""
import logging

from fastapi import APIRouter, FastAPI
from starlette.middleware.cors import CORSMiddleware

from app.config import settings
from app.database import close_db, get_db, init_indexes
from app.routers import (
    actions as actions_module,
    agent_installer as agent_installer_router,
    agent_pair as agent_pair_router,
    alert_rules as alert_rules_router,
    alerts as alerts_router,
    audit as audit_router,
    auth as auth_router,
    debug as debug_router,
    device_groups as device_groups_router,
    devices as devices_router,
    enrollment as enrollment_router,
    health as health_router,
    maintenance as maintenance_router,
    organizations as org_router,
    predictions as predictions_router,
    predictions_fleet as predictions_fleet_router,
    software_policy as software_policy_router,
    users as users_router,
    ws as ws_router,
)
from app.services.alerts import sweep_offline_and_lifecycle
from app.services.prediction.models import warm_all as warm_prediction_models
from app.websocket_manager import manager

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
)
logger = logging.getLogger("digital_twin")

# --- Attach the in-memory pipeline-trace ring buffer to the enrollment,
# --- WebSocket agent, and telemetry loggers so /api/debug/pipeline/logs
# --- and /api/debug/enrollment-status can serve step-by-step audit
# --- events to the operator without needing supervisor shell access.
_pipeline_handler = debug_router.PipelineTraceHandler()
_pipeline_handler.setLevel(logging.INFO)
for _name in ("dta.enroll", "dta.ws", "dta.telemetry", "dta.debug",
              "app.routers.enrollment", "app.routers.ws"):
    _lg = logging.getLogger(_name)
    _lg.setLevel(logging.INFO)
    _lg.addHandler(_pipeline_handler)

app = FastAPI(title="Digital Twin Platform", version="1.0.0")

# ---- CORS ----
app.add_middleware(
    CORSMiddleware,
    allow_credentials=True,
    allow_origins=settings.CORS_ORIGINS if settings.CORS_ORIGINS != ["*"] else ["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

# ---- Main API router (mounted under /api) ----
api = APIRouter(prefix="/api")


@api.get("/")
async def root():
    return {"service": "digital-twin-platform", "status": "ok", "version": "1.0.0"}


@api.get("/health")
async def health():
    return {"status": "ok"}


# Include feature routers
api.include_router(auth_router.router)
api.include_router(org_router.router)
api.include_router(users_router.router)
api.include_router(users_router.inv_router)
api.include_router(enrollment_router.router)
api.include_router(devices_router.router)
api.include_router(health_router.router)
api.include_router(predictions_router.router)
api.include_router(predictions_fleet_router.router)
api.include_router(alerts_router.router)
api.include_router(alert_rules_router.router)
api.include_router(software_policy_router.router)
api.include_router(actions_module.router)
api.include_router(actions_module.agent_router)
api.include_router(device_groups_router.router)
api.include_router(maintenance_router.router)
api.include_router(audit_router.router)
api.include_router(debug_router.router)
api.include_router(ws_router.router)
api.include_router(agent_pair_router.router)
api.include_router(agent_installer_router.router)

app.include_router(api)


import asyncio


async def _alert_sweep_loop():
    """Background loop that catches offline devices and closes lingering alerts."""
    while True:
        try:
            await sweep_offline_and_lifecycle(get_db(), manager)
        except Exception as exc:  # pragma: no cover - defensive
            logger.warning("alert sweep iteration failed: %s", exc)
        await asyncio.sleep(30)


async def _actions_sweep_loop():
    """Background loop that expires stale pending actions and purges old artifacts.

    * Any action whose ``expires_at`` is in the past and is still pending/in_progress
      is moved to status ``expired`` with a note so operators can see it did not run.
    * Action artifacts older than the retention window are deleted to keep the
      collection small (they contain base64-encoded log payloads).
    """
    from datetime import datetime, timedelta, timezone
    while True:
        try:
            db = get_db()
            now_iso = datetime.now(timezone.utc).isoformat()
            expired = await db.actions.update_many(
                {"status": {"$in": ["pending", "in_progress"]}, "expires_at": {"$lt": now_iso}},
                {"$set": {"status": "expired", "finished_at": now_iso,
                          "error": "TTL elapsed before the agent executed the command"}},
            )
            if expired.modified_count:
                logger.info("expired %d stale action(s)", expired.modified_count)
            cutoff = (datetime.now(timezone.utc) - timedelta(hours=72)).isoformat()
            await db.action_artifacts.delete_many({"created_at": {"$lt": cutoff}})
        except Exception as exc:  # pragma: no cover - defensive
            logger.warning("actions sweep iteration failed: %s", exc)
        await asyncio.sleep(60)


async def _maintenance_sweep_loop():
    """Auto-exit devices whose maintenance window has elapsed."""
    from datetime import datetime, timezone
    while True:
        try:
            db = get_db()
            now_iso = datetime.now(timezone.utc).isoformat()
            res = await db.devices.update_many(
                {"maintenance_mode": True, "maintenance_ends_at": {"$lt": now_iso}},
                {"$set": {"maintenance_mode": False, "maintenance_ended_at": now_iso}},
            )
            if res.modified_count:
                logger.info("Auto-exited maintenance for %d device(s)", res.modified_count)
            # Also un-mute alerts whose muted_until elapsed
            await db.alerts.update_many(
                {"muted_reason": "maintenance mode", "muted_until": {"$lt": now_iso}},
                {"$unset": {"muted_until": "", "muted_reason": ""}},
            )
        except Exception as exc:  # pragma: no cover
            logger.warning("maintenance sweep iteration failed: %s", exc)
        await asyncio.sleep(30)


_sweep_task: asyncio.Task | None = None
_actions_sweep_task: asyncio.Task | None = None
_maintenance_sweep_task: asyncio.Task | None = None


@app.on_event("startup")
async def on_startup():
    await init_indexes()
    # Warm-train prediction models so first request is fast.
    try:
        warm_prediction_models()
    except Exception as exc:  # pragma: no cover - defensive
        logger.warning("prediction model warm-up failed: %s", exc)
    global _sweep_task, _actions_sweep_task, _maintenance_sweep_task
    _sweep_task = asyncio.create_task(_alert_sweep_loop())
    _actions_sweep_task = asyncio.create_task(_actions_sweep_loop())
    _maintenance_sweep_task = asyncio.create_task(_maintenance_sweep_loop())
    logger.info("Digital Twin backend started (alert + actions + maintenance sweeps enabled)")


@app.on_event("shutdown")
async def on_shutdown():
    global _sweep_task, _actions_sweep_task, _maintenance_sweep_task
    for t in (_sweep_task, _actions_sweep_task, _maintenance_sweep_task):
        if t and not t.done():
            t.cancel()
    await close_db()
