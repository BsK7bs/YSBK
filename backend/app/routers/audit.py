"""Audit logs routes."""
from fastapi import APIRouter, Depends, Query

from ..database import get_db
from ..deps import require_role
from ..utils import serialize

router = APIRouter(prefix="/audit", tags=["audit"])


@router.get("")
async def list_audit_events(
    limit: int = Query(default=200, ge=1, le=2000),
    user: dict = Depends(require_role("admin")),
):
    db = get_db()
    items = await db.audit_events.find({"org_id": user["org_id"]}, {"_id": 0}).sort("ts", -1).limit(limit).to_list(limit)
    return [serialize(x) for x in items]
