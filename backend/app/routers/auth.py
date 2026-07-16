"""Authentication routes: signup, login, refresh, logout, me, change-password."""
import uuid
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException, status

from ..database import get_db
from ..deps import audit_log, get_current_user
from ..models import (
    AccessTokenResponse,
    ChangePasswordRequest,
    LoginRequest,
    RefreshRequest,
    SignupRequest,
    TokenResponse,
)
from ..security import (
    create_access_token,
    create_refresh_token,
    decode_token,
    hash_password,
    verify_password,
)
from ..utils import serialize, utcnow

router = APIRouter(prefix="/auth", tags=["auth"])


@router.post("/signup", response_model=TokenResponse)
async def signup(payload: SignupRequest):
    db = get_db()
    email = payload.email.lower()
    existing = await db.users.find_one({"email": email})
    if existing:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Email already registered")

    org_id = str(uuid.uuid4())
    org_doc = {
        "id": org_id,
        "name": payload.organization_name.strip(),
        "slug": None,
        "logo_url": None,
        "timezone": "UTC",
        "notification_prefs": {"email": True},
        "created_at": utcnow().isoformat(),
    }
    await db.organizations.insert_one(org_doc)

    user_id = str(uuid.uuid4())
    user_doc = {
        "id": user_id,
        "org_id": org_id,
        "email": email,
        "full_name": payload.full_name.strip(),
        "role": "owner",
        "is_active": True,
        "password_hash": hash_password(payload.password),
        "created_at": utcnow().isoformat(),
    }
    await db.users.insert_one(user_doc)

    access = create_access_token(user_id, org_id, "owner")
    refresh, jti, exp = create_refresh_token(user_id, org_id, "owner", remember_me=False)
    await db.refresh_tokens.insert_one({
        "jti": jti,
        "user_id": user_id,
        "org_id": org_id,
        "expires_at": exp.isoformat(),
        "revoked": False,
        "created_at": utcnow().isoformat(),
    })

    await audit_log(db, org_id, user_doc, "user.signup", target=email)

    return {
        "access_token": access,
        "refresh_token": refresh,
        "token_type": "bearer",
        "user": serialize({k: v for k, v in user_doc.items() if k != "password_hash"}),
        "organization": serialize(org_doc),
    }


@router.post("/login", response_model=TokenResponse)
async def login(payload: LoginRequest):
    db = get_db()
    email = payload.email.lower()
    user = await db.users.find_one({"email": email}, {"_id": 0})
    if not user or not verify_password(payload.password, user.get("password_hash", "")):
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid credentials")
    if not user.get("is_active", True):
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="User is disabled")

    org = await db.organizations.find_one({"id": user["org_id"]}, {"_id": 0})
    if not org:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Organization not found")

    access = create_access_token(user["id"], user["org_id"], user["role"])
    refresh, jti, exp = create_refresh_token(user["id"], user["org_id"], user["role"], remember_me=payload.remember_me)
    await db.refresh_tokens.insert_one({
        "jti": jti,
        "user_id": user["id"],
        "org_id": user["org_id"],
        "expires_at": exp.isoformat(),
        "revoked": False,
        "created_at": utcnow().isoformat(),
    })
    await audit_log(db, user["org_id"], user, "user.login", target=email)

    public_user = {k: v for k, v in user.items() if k != "password_hash"}
    return {
        "access_token": access,
        "refresh_token": refresh,
        "token_type": "bearer",
        "user": serialize(public_user),
        "organization": serialize(org),
    }


@router.post("/refresh", response_model=AccessTokenResponse)
async def refresh(payload: RefreshRequest):
    db = get_db()
    try:
        data = decode_token(payload.refresh_token)
    except Exception:
        raise HTTPException(status_code=401, detail="Invalid refresh token")
    if data.get("type") != "refresh":
        raise HTTPException(status_code=401, detail="Not a refresh token")
    stored = await db.refresh_tokens.find_one({"jti": data["jti"]}, {"_id": 0})
    if not stored or stored.get("revoked"):
        raise HTTPException(status_code=401, detail="Refresh token revoked")
    user = await db.users.find_one({"id": data["sub"]}, {"_id": 0})
    if not user or not user.get("is_active", True):
        raise HTTPException(status_code=401, detail="User not available")
    access = create_access_token(user["id"], user["org_id"], user["role"])
    return {"access_token": access, "token_type": "bearer"}


@router.post("/logout")
async def logout(payload: RefreshRequest, user: dict = Depends(get_current_user)):
    db = get_db()
    try:
        data = decode_token(payload.refresh_token)
        await db.refresh_tokens.update_one({"jti": data.get("jti")}, {"$set": {"revoked": True}})
    except Exception:
        pass
    await audit_log(db, user["org_id"], user, "user.logout", target=user["email"])
    return {"ok": True}


@router.get("/me")
async def me(user: dict = Depends(get_current_user)):
    db = get_db()
    org = await db.organizations.find_one({"id": user["org_id"]}, {"_id": 0})
    public_user = {k: v for k, v in user.items() if k != "password_hash"}
    return {"user": serialize(public_user), "organization": serialize(org)}


@router.post("/change-password")
async def change_password(payload: ChangePasswordRequest, user: dict = Depends(get_current_user)):
    if not verify_password(payload.current_password, user.get("password_hash", "")):
        raise HTTPException(status_code=400, detail="Current password is incorrect")
    db = get_db()
    await db.users.update_one({"id": user["id"]}, {"$set": {"password_hash": hash_password(payload.new_password)}})
    # revoke all refresh tokens for this user
    await db.refresh_tokens.update_many({"user_id": user["id"]}, {"$set": {"revoked": True}})
    await audit_log(db, user["org_id"], user, "user.change_password")
    return {"ok": True}
