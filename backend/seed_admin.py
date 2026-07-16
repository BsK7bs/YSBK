"""Seed a single bootstrap admin account (idempotent).

Run once (safe to re-run). Reads from env:
  SEED_ADMIN_EMAIL       (default: admin@digitaltwin.local)
  SEED_ADMIN_PASSWORD    (default: ChangeMe!2026)
  SEED_ADMIN_NAME        (default: Platform Administrator)
  SEED_ADMIN_ORG         (default: Platform Admin)

The seeded account is an Organization Owner (highest role). It is the ONLY
demo/system-level account. All other users must be created via signup or
invitation. Change the password after first login.
"""
import asyncio
import os
import sys
import uuid
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from app.database import get_db, init_indexes, close_db  # noqa: E402
from app.security import hash_password  # noqa: E402


async def seed_admin() -> None:
    await init_indexes()
    db = get_db()

    email = (os.environ.get("SEED_ADMIN_EMAIL") or "admin@digitaltwin.com").lower()
    password = os.environ.get("SEED_ADMIN_PASSWORD") or "ChangeMe!2026"
    name = os.environ.get("SEED_ADMIN_NAME") or "Platform Administrator"
    org_name = os.environ.get("SEED_ADMIN_ORG") or "Platform Admin"

    existing = await db.users.find_one({"email": email})
    if existing:
        print(f"[seed] Admin already exists: {email} (org={existing['org_id']})")
        return

    now = datetime.now(timezone.utc).isoformat()
    org_id = str(uuid.uuid4())
    await db.organizations.insert_one({
        "id": org_id,
        "name": org_name,
        "slug": None,
        "logo_url": None,
        "timezone": "UTC",
        "notification_prefs": {"email": True},
        "created_at": now,
    })

    user_id = str(uuid.uuid4())
    await db.users.insert_one({
        "id": user_id,
        "org_id": org_id,
        "email": email,
        "full_name": name,
        "role": "owner",
        "is_active": True,
        "password_hash": hash_password(password),
        "created_at": now,
        "is_seed": True,
    })
    await db.audit_events.insert_one({
        "id": str(uuid.uuid4()),
        "org_id": org_id,
        "actor_id": None,
        "actor_email": "system",
        "kind": "user.seeded",
        "target": email,
        "metadata": {"reason": "bootstrap admin"},
        "ts": now,
    })

    print("[seed] Bootstrap admin account created:")
    print(f"       Email:    {email}")
    print(f"       Password: {password}  (change immediately after first login)")
    print(f"       Org:      {org_name}")
    print(f"       Role:     owner")


async def main() -> None:
    try:
        await seed_admin()
    finally:
        await close_db()


if __name__ == "__main__":
    asyncio.run(main())
