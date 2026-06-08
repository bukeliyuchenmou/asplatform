from __future__ import annotations

from fastapi import HTTPException
from sqlalchemy.orm import Session

from utils.auth import verify_token
from models import TokenRecord
from utils.entitlements import entitlement_rank, get_token_entitlement_level


async def verify_service_access(db: Session, token: str = None, required_perm: str = "ai"):
    """Verify token access and check quota. Does NOT deduct quota."""
    if not token:
        raise HTTPException(status_code=401, detail="Access token required")
    record = verify_token(token, db, required_perm)
    if required_perm == "bio" and record.external_user_id:
        entitlement_level = get_token_entitlement_level(db, record)
        if entitlement_rank(entitlement_level) < entitlement_rank("pro"):
            raise HTTPException(status_code=403, detail="Bio analysis requires pro entitlement")
    # Check quota if it's an AI call
    if required_perm == "ai":
        if record.ai_quota > 0 and record.used_quota >= record.ai_quota:
            raise HTTPException(status_code=403, detail="Token 额度不足")
    return record


def deduct_token_quota(db: Session, token_id: int, token_usage: float):
    """Deduct token quota based on usage credits."""
    if token_usage <= 0:
        return  # No usage to deduct
    record = db.query(TokenRecord).filter(TokenRecord.id == token_id).first()
    if record:
        record.used_quota += token_usage
        db.commit()
