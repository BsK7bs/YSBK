"""MongoDB connection and index bootstrap."""
import logging
from motor.motor_asyncio import AsyncIOMotorClient, AsyncIOMotorDatabase
from .config import settings

logger = logging.getLogger(__name__)

_client: AsyncIOMotorClient | None = None
_db: AsyncIOMotorDatabase | None = None


def get_client() -> AsyncIOMotorClient:
    global _client
    if _client is None:
        _client = AsyncIOMotorClient(settings.MONGO_URL)
    return _client


def get_db() -> AsyncIOMotorDatabase:
    global _db
    if _db is None:
        _db = get_client()[settings.DB_NAME]
    return _db


async def init_indexes() -> None:
    """Create MongoDB indexes required for the app."""
    db = get_db()
    # users: email must be unique globally (we lowercase it before storing)
    await db.users.create_index("email", unique=True)
    await db.users.create_index("org_id")
    # organizations
    await db.organizations.create_index("id", unique=True)
    # enrollment codes
    await db.enrollment_codes.create_index("code", unique=True)
    await db.enrollment_codes.create_index("org_id")
    # devices
    await db.devices.create_index("id", unique=True)
    await db.devices.create_index("org_id")
    await db.devices.create_index("api_key_hash")
    # telemetry
    await db.telemetry.create_index([("device_id", 1), ("ts", -1)])
    await db.telemetry.create_index("org_id")
    # invitations
    await db.invitations.create_index("token", unique=True)
    await db.invitations.create_index("org_id")
    # refresh tokens (session mgmt)
    await db.refresh_tokens.create_index("jti", unique=True)
    await db.refresh_tokens.create_index("user_id")

    await db.device_refresh_tokens.create_index("jti", unique=True)
    await db.device_refresh_tokens.create_index("device_id")
    await db.device_refresh_tokens.create_index("org_id")

    await db.software_events.create_index([("org_id", 1), ("ts", -1)])
    await db.software_events.create_index([("device_id", 1), ("ts", -1)])
    await db.software_events.create_index("kind")
    # audit
    await db.audit_events.create_index([("org_id", 1), ("ts", -1)])
    # alerts
    await db.alerts.create_index([("org_id", 1), ("ts", -1)])
    await db.alerts.create_index([("device_id", 1), ("ts", -1)])
    # actions
    await db.actions.create_index([("device_id", 1), ("created_at", -1)])
    await db.actions.create_index("org_id")
    await db.actions.create_index("status")
    await db.actions.create_index("expires_at")
    # action artifacts (log-zip uploads etc.)
    await db.action_artifacts.create_index("action_id", unique=True)
    await db.action_artifacts.create_index("created_at")
    # health timeline
    await db.health_timeline.create_index([("device_id", 1), ("ts", -1)])
    await db.health_timeline.create_index([("org_id", 1), ("ts", -1)])
    # predictions timeline
    await db.predictions_timeline.create_index([("device_id", 1), ("ts", -1)])
    await db.predictions_timeline.create_index([("org_id", 1), ("ts", -1)])
    # alerts (production engine)
    await db.alerts.create_index([("org_id", 1), ("status", 1), ("last_seen_at", -1)])
    await db.alerts.create_index([("device_id", 1), ("last_seen_at", -1)])
    await db.alerts.create_index([("org_id", 1), ("severity", 1), ("status", 1)])
    await db.alerts.create_index(
        [("org_id", 1), ("device_id", 1), ("rule_key", 1), ("dimension_key", 1), ("status", 1)]
    )
    await db.alert_dwell.create_index("key", unique=True)
    await db.alert_dwell.create_index("org_id")
    await db.alert_policies.create_index("org_id", unique=True)
    await db.notification_channels.create_index("org_id", unique=True)
    # software policy & compliance
    await db.software_policies.create_index("org_id", unique=True)
    await db.software_rules.create_index([("org_id", 1), ("mode", 1)])
    await db.software_catalog.create_index([("org_id", 1), ("key", 1)], unique=True)
    await db.software_catalog.create_index([("org_id", 1), ("device_count", -1)])
    await db.software_device_index.create_index([("org_id", 1), ("device_id", 1)])
    await db.software_device_index.create_index([("org_id", 1), ("key", 1)])
    # device groups
    await db.device_groups.create_index([("org_id", 1), ("name", 1)], unique=True)
    await db.devices.create_index("group_ids")
    # action batches
    await db.action_batches.create_index([("org_id", 1), ("created_at", -1)])
    await db.actions.create_index("batch_id")
    # maintenance mode
    await db.devices.create_index([("maintenance_mode", 1), ("maintenance_ends_at", 1)])
    # Agent v2 -- diagnostics
    await db.agent_diagnostics.create_index("device_id", unique=True)
    await db.agent_diagnostics.create_index([("org_id", 1), ("ts", -1)])
    await db.agent_diagnostics_history.create_index([("device_id", 1), ("ts", -1)])
    # Cap history to a manageable size per device (14-day TTL)
    try:
        await db.agent_diagnostics_history.create_index("ts", expireAfterSeconds=14 * 24 * 3600)
    except Exception:
        # Index may already exist with different options; ignore.
        pass
    logger.info("MongoDB indexes ensured")


async def close_db() -> None:
    global _client
    if _client is not None:
        _client.close()
        _client = None
