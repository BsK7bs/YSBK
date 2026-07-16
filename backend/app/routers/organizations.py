"""Organization routes: get/update current org, notification prefs."""
from fastapi import APIRouter, Depends, HTTPException

from ..database import get_db
from ..deps import audit_log, get_current_user, require_role
from ..models import OrganizationUpdate
from ..utils import serialize

router = APIRouter(prefix="/org", tags=["organization"])


@router.get("")
async def get_current_org(user: dict = Depends(get_current_user)):
    db = get_db()
    org = await db.organizations.find_one({"id": user["org_id"]}, {"_id": 0})
    if not org:
        raise HTTPException(status_code=404, detail="Organization not found")
    return serialize(org)


@router.patch("")
async def update_current_org(
    payload: OrganizationUpdate,
    user: dict = Depends(require_role("admin")),
):
    db = get_db()
    update: dict = {k: v for k, v in payload.model_dump(exclude_unset=True).items() if v is not None}
    if update:
        await db.organizations.update_one({"id": user["org_id"]}, {"$set": update})
        await audit_log(db, user["org_id"], user, "org.update", metadata=update)
    org = await db.organizations.find_one({"id": user["org_id"]}, {"_id": 0})
    return serialize(org)
