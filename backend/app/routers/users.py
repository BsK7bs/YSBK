"""Users & Invitations routes."""
import uuid
from datetime import datetime, timedelta, timezone

from fastapi import APIRouter, Depends, HTTPException

from ..database import get_db
from ..deps import audit_log, get_current_user, require_role
from ..models import (
    AcceptInvitationRequest,
    InvitationCreate,
    ROLE_HIERARCHY,
    TokenResponse,
)
from ..security import (
    create_access_token,
    create_refresh_token,
    generate_invitation_token,
    hash_password,
)
from ..utils import serialize, utcnow

router = APIRouter(prefix="/users", tags=["users"])


@router.get("")
async def list_users(user: dict = Depends(get_current_user)):
    db = get_db()
    users = await db.users.find(
        {"org_id": user["org_id"]},
        {"_id": 0, "password_hash": 0},
    ).sort("created_at", 1).to_list(1000)
    return [serialize(u) for u in users]


@router.patch("/{user_id}/role")
async def change_role(user_id: str, body: dict, actor: dict = Depends(require_role("admin"))):
    role = body.get("role")
    if role not in ROLE_HIERARCHY:
        raise HTTPException(status_code=400, detail="Invalid role")
    db = get_db()
    target = await db.users.find_one({"id": user_id, "org_id": actor["org_id"]}, {"_id": 0})
    if not target:
        raise HTTPException(status_code=404, detail="User not found")
    if target["role"] == "owner" and actor["role"] != "owner":
        raise HTTPException(status_code=403, detail="Only owners can modify owners")
    if role == "owner" and actor["role"] != "owner":
        raise HTTPException(status_code=403, detail="Only owners can assign owner role")
    await db.users.update_one({"id": user_id}, {"$set": {"role": role}})
    await audit_log(db, actor["org_id"], actor, "user.role_changed", target=target["email"], metadata={"new_role": role})
    return {"ok": True}


@router.delete("/{user_id}")
async def remove_user(user_id: str, actor: dict = Depends(require_role("admin"))):
    if user_id == actor["id"]:
        raise HTTPException(status_code=400, detail="Cannot remove yourself")
    db = get_db()
    target = await db.users.find_one({"id": user_id, "org_id": actor["org_id"]}, {"_id": 0})
    if not target:
        raise HTTPException(status_code=404, detail="User not found")
    if target["role"] == "owner":
        raise HTTPException(status_code=403, detail="Cannot remove owner")
    await db.users.delete_one({"id": user_id})
    await db.refresh_tokens.update_many({"user_id": user_id}, {"$set": {"revoked": True}})
    await audit_log(db, actor["org_id"], actor, "user.removed", target=target["email"])
    return {"ok": True}


# ---------- Invitations ----------

inv_router = APIRouter(prefix="/invitations", tags=["invitations"])


@inv_router.post("")
async def create_invitation(payload: InvitationCreate, actor: dict = Depends(require_role("admin"))):
    db = get_db()
    if payload.role not in ROLE_HIERARCHY:
        raise HTTPException(status_code=400, detail="Invalid role")
    if payload.role == "owner":
        raise HTTPException(status_code=400, detail="Cannot invite an owner")
    email = payload.email.lower()
    existing = await db.users.find_one({"email": email})
    if existing:
        raise HTTPException(status_code=409, detail="User with this email already exists")
    token = generate_invitation_token()
    now = utcnow()
    doc = {
        "id": str(uuid.uuid4()),
        "org_id": actor["org_id"],
        "email": email,
        "role": payload.role,
        "token": token,
        "invited_by": actor["id"],
        "accepted": False,
        "created_at": now.isoformat(),
        "expires_at": (now + timedelta(days=7)).isoformat(),
    }
    await db.invitations.insert_one(doc)
    await audit_log(db, actor["org_id"], actor, "invitation.created", target=email, metadata={"role": payload.role})
    return {"invitation": serialize(doc)}


@inv_router.get("")
async def list_invitations(actor: dict = Depends(require_role("admin"))):
    db = get_db()
    items = await db.invitations.find({"org_id": actor["org_id"]}, {"_id": 0}).sort("created_at", -1).to_list(500)
    return [serialize(i) for i in items]


@inv_router.delete("/{invitation_id}")
async def revoke_invitation(invitation_id: str, actor: dict = Depends(require_role("admin"))):
    db = get_db()
    res = await db.invitations.delete_one({"id": invitation_id, "org_id": actor["org_id"]})
    if res.deleted_count == 0:
        raise HTTPException(status_code=404, detail="Invitation not found")
    await audit_log(db, actor["org_id"], actor, "invitation.revoked", target=invitation_id)
    return {"ok": True}


@inv_router.get("/lookup/{token}")
async def lookup_invitation(token: str):
    db = get_db()
    inv = await db.invitations.find_one({"token": token}, {"_id": 0})
    if not inv or inv.get("accepted"):
        raise HTTPException(status_code=404, detail="Invitation not found or already used")
    exp = inv.get("expires_at")
    if exp and datetime.fromisoformat(exp) < datetime.now(timezone.utc):
        raise HTTPException(status_code=410, detail="Invitation expired")
    org = await db.organizations.find_one({"id": inv["org_id"]}, {"_id": 0})
    return {"email": inv["email"], "role": inv["role"], "organization": serialize(org)}


@inv_router.post("/accept", response_model=TokenResponse)
async def accept_invitation(payload: AcceptInvitationRequest):
    db = get_db()
    inv = await db.invitations.find_one({"token": payload.token}, {"_id": 0})
    if not inv or inv.get("accepted"):
        raise HTTPException(status_code=404, detail="Invitation not found or already used")
    exp = inv.get("expires_at")
    if exp and datetime.fromisoformat(exp) < datetime.now(timezone.utc):
        raise HTTPException(status_code=410, detail="Invitation expired")
    if await db.users.find_one({"email": inv["email"]}):
        raise HTTPException(status_code=409, detail="User already exists")
    now = utcnow()
    user_id = str(uuid.uuid4())
    user_doc = {
        "id": user_id,
        "org_id": inv["org_id"],
        "email": inv["email"],
        "full_name": payload.full_name.strip(),
        "role": inv["role"],
        "is_active": True,
        "password_hash": hash_password(payload.password),
        "created_at": now.isoformat(),
    }
    await db.users.insert_one(user_doc)
    await db.invitations.update_one({"id": inv["id"]}, {"$set": {"accepted": True, "accepted_at": now.isoformat()}})
    org = await db.organizations.find_one({"id": inv["org_id"]}, {"_id": 0})

    access = create_access_token(user_id, inv["org_id"], inv["role"])
    refresh, jti, rexp = create_refresh_token(user_id, inv["org_id"], inv["role"])
    await db.refresh_tokens.insert_one({
        "jti": jti,
        "user_id": user_id,
        "org_id": inv["org_id"],
        "expires_at": rexp.isoformat(),
        "revoked": False,
        "created_at": now.isoformat(),
    })
    await audit_log(db, inv["org_id"], user_doc, "invitation.accepted", target=inv["email"])
    return {
        "access_token": access,
        "refresh_token": refresh,
        "token_type": "bearer",
        "user": serialize({k: v for k, v in user_doc.items() if k != "password_hash"}),
        "organization": serialize(org),
    }
