"""Enrollment code routes: create/list/revoke, and the public enroll endpoint used by agents."""
import base64
import io
import logging
from datetime import datetime, timedelta, timezone

import qrcode
from fastapi import APIRouter, Depends, HTTPException, Request

from ..config import settings
from ..database import get_db
from ..deps import audit_log, require_role
from ..models import (
    DeviceEnrollRequest,
    DeviceEnrollResponse,
    EnrollmentCodeCreate,
    EnrollmentCodeResponse,
)
from ..security import generate_device_api_key, generate_enrollment_code, hash_api_key
from ..utils import serialize, utcnow

logger = logging.getLogger("dta.enroll")
router = APIRouter(prefix="/enrollment", tags=["enrollment"])


def _qr_payload_for(code: str) -> str:
    return f"digitaltwin://enroll?code={code}"


@router.post("/codes", response_model=EnrollmentCodeResponse)
async def create_enrollment_code(
    payload: EnrollmentCodeCreate,
    actor: dict = Depends(require_role("technician")),
):
    db = get_db()
    for _ in range(5):
        code = generate_enrollment_code()
        if not await db.enrollment_codes.find_one({"code": code}):
            break
    else:
        raise HTTPException(status_code=500, detail="Failed to generate unique code")
    now = utcnow()
    doc = {
        "id": __import__("uuid").uuid4().hex,
        "code": code,
        "org_id": actor["org_id"],
        "created_by": actor["id"],
        "label": (payload.label or "").strip() or None,
        "used": False,
        "used_by_device_id": None,
        "created_at": now.isoformat(),
        "expires_at": (now + timedelta(minutes=settings.ENROLLMENT_CODE_TTL_MINUTES)).isoformat(),
    }
    await db.enrollment_codes.insert_one(doc)
    await audit_log(db, actor["org_id"], actor, "enrollment.code_created", target=code, metadata={"label": doc["label"]})
    return EnrollmentCodeResponse(
        id=doc["id"],
        code=code,
        expires_at=datetime.fromisoformat(doc["expires_at"]),
        label=doc["label"],
        qr_payload=_qr_payload_for(code),
    )


@router.get("/codes")
async def list_enrollment_codes(actor: dict = Depends(require_role("technician"))):
    db = get_db()
    now_iso = utcnow().isoformat()
    items = await db.enrollment_codes.find(
        {"org_id": actor["org_id"]}, {"_id": 0}
    ).sort("created_at", -1).to_list(200)
    out = []
    for i in items:
        i = serialize(i)
        i["qr_payload"] = _qr_payload_for(i["code"])
        i["is_expired"] = i["expires_at"] < now_iso
        out.append(i)
    return out


@router.delete("/codes/{code_id}")
async def revoke_enrollment_code(code_id: str, actor: dict = Depends(require_role("technician"))):
    db = get_db()
    res = await db.enrollment_codes.delete_one({"id": code_id, "org_id": actor["org_id"]})
    if res.deleted_count == 0:
        raise HTTPException(status_code=404, detail="Enrollment code not found")
    await audit_log(db, actor["org_id"], actor, "enrollment.code_revoked", target=code_id)
    return {"ok": True}


@router.get("/codes/{code_id}/qr.png")
async def get_qr_png(code_id: str, actor: dict = Depends(require_role("technician"))):
    from fastapi.responses import Response

    db = get_db()
    doc = await db.enrollment_codes.find_one({"id": code_id, "org_id": actor["org_id"]}, {"_id": 0})
    if not doc:
        raise HTTPException(status_code=404, detail="Not found")
    img = qrcode.make(_qr_payload_for(doc["code"]))
    buf = io.BytesIO()
    img.save(buf, format="PNG")
    return Response(content=buf.getvalue(), media_type="image/png")
