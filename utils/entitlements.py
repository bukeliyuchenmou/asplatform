from __future__ import annotations

from sqlalchemy.orm import Session

from models import ExternalUser, PaymentOrderEntitlement, TokenRecord


ENTITLEMENT_LEVELS = {
    "experience": 1,
    "basic": 2,
    "pro": 3,
}


def entitlement_rank(slug: str | None) -> int:
    return ENTITLEMENT_LEVELS.get((slug or "experience").strip().lower(), 0)


def get_token_entitlement_level(db: Session, record: TokenRecord) -> str | None:
    if not record.external_user_id:
        return None

    entitlement = (
        db.query(PaymentOrderEntitlement)
        .filter(PaymentOrderEntitlement.issued_token_id == record.id)
        .order_by(PaymentOrderEntitlement.id.desc())
        .first()
    )
    if entitlement and entitlement.product_slug:
        return entitlement.product_slug

    external_user = (
        db.query(ExternalUser)
        .filter(ExternalUser.id == record.external_user_id)
        .first()
    )
    return external_user.entitlement_level if external_user else None
