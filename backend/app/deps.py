"""FastAPI dependencies for auth, current user/org, and RBAC."""
from typing import Callable

from fastapi import Depends, Header, HTTPException, Request, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer

from .database import get_db
from .models import ROLE_HIERARCHY, Role
from .security import decode_token, hash_api_key

bearer_scheme = HTTPBearer(auto_error=False)


async def get_current_user(
    credentials: HTTPAuthorizationCredentials | None = Depends(bearer_scheme),
) -> dict:
    if not credentials or credentials.scheme.lower() != "bearer":
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Missing bearer token")
    try:
        payload = decode_token(credentials.credentials)
    except Exception:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid or expired token")
    if payload.get("type") != "access":
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Not an access token")
    db = get_db()
    user = await db.users.find_one({"id": payload["sub"]}, {"_id": 0})
    if not user or not user.get("is_active", True):
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="User not found")
    return user


def require_role(min_role: Role) -> Callable:
    async def _dep(user: dict = Depends(get_current_user)) -> dict:
        if ROLE_HIERARCHY.get(user.get("role", "viewer"), 0) < ROLE_HIERARCHY[min_role]:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=f"Requires role >= {min_role}",
            )
        return user

    return _dep


async def get_device_from_api_key(
    x_device_api_key: str | None = Header(default=None, alias="X-Device-API-Key"),
    authorization: str | None = Header(default=None),
) -> dict:
    """Return the device doc for an authenticated agent.

    Accepts three forms (in priority order):
      1. ``X-Device-API-Key: <api-key>``
      2. ``Authorization: Bearer <device-JWT>``  (issued by /api/agent/pair)
      3. ``Authorization: Bearer <api-key>``      (legacy)
    """
    from .security import decode_token

    bearer_token = None
    if authorization and authorization.lower().startswith("bearer "):
        bearer_token = authorization.split(" ", 1)[1].strip()

    db = get_db()

    # --- 1. Try JWT first if we have a bearer token (looks like a JWT) ---
    if bearer_token and bearer_token.count(".") == 2:
        try:
            claims = decode_token(bearer_token)
            if claims.get("kind") == "device" and claims.get("type") == "device_access":
                device_id = claims.get("sub"); org_id = claims.get("org_id")
                if device_id and org_id:
                    device = await db.devices.find_one({"id": device_id, "org_id": org_id}, {"_id": 0})
                    if device:
                        return device
        except Exception:
            pass  # fall through to api-key check

    # --- 2. X-Device-API-Key header OR bearer-token treated as api-key ---
    key = x_device_api_key or bearer_token
    if not key:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Missing device credentials")
    device = await db.devices.find_one({"api_key_hash": hash_api_key(key)}, {"_id": 0})
    if not device:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid device credentials")
    return device


async def audit_log(db, org_id: str, actor: dict | None, kind: str, target: str | None = None, metadata: dict | None = None):
    import uuid
    from datetime import datetime, timezone
    doc = {
        "id": str(uuid.uuid4()),
        "org_id": org_id,
        "actor_id": actor.get("id") if actor else None,
        "actor_email": actor.get("email") if actor else None,
        "kind": kind,
        "target": target,
        "metadata": metadata or {},
        "ts": datetime.now(timezone.utc).isoformat(),
    }
    await db.audit_events.insert_one(doc)
