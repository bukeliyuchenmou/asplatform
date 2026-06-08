from __future__ import annotations

import json
import secrets
from datetime import datetime, timedelta
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel
from sqlalchemy.orm import Session

from api.oauth import create_service_token, get_external_user_by_user_token, get_oauth_client
from config_loader import get
from database import get_db
from models import ExternalUser, PaymentOrder, PaymentOrderEntitlement, TokenRecord
from utils.auth import verify_token
from utils.entitlements import get_token_entitlement_level
from utils.timezone import local_now, to_local_naive

router = APIRouter(prefix="/api/payment", tags=["payment"])


class CreatePaymentRequest(BaseModel):
    product_id: str
    openid: str = ""
    user_token: str = ""
    service_token: str = ""
    state: str = ""


class PaymentNotifyRequest(BaseModel):
    event: str | None = None
    is_pay: int | None = None
    state: int | None = None
    out_trade_no: str | None = None
    third_order_no: str
    client_id: str | None = None
    openid: str | None = None
    pay_request_id: str | None = None
    total_fee: int | float | None = None
    pay_type: int | None = None
    trade_type: int | None = None
    paid_at: str | None = None
    notify_time: str | None = None
    


def get_products_path() -> str:
    return get("oauth.products_path", "") or "/oauth/as-platform-product"


def normalize_product(product: Any) -> dict[str, Any] | None:
    if not isinstance(product, dict):
        return None

    product_id = str(product.get("product_id") or product.get("id") or "").strip()
    if not product_id:
        return None

    price_label = product.get("price_label")
    price = product.get("price")
    if not price_label and price not in (None, ""):
        price_label = f"¥{price}"

    return {
        "product_id": product_id,
        "slug": product.get("slug") or product.get("entitlement_level") or product.get("level") or "experience",
        "name": product.get("name") or product.get("title") or "未命名产品",
        "description": product.get("description") or product.get("remark") or "",
        "price": price,
        "quota": product.get("quota") or product.get("ai_quota"),
        "duration_days": product.get("duration_days") or product.get("expires_days") or 30,
        "price_label": price_label or "",
        "raw": product,
    }


async def fetch_products() -> list[dict[str, Any]]:
    products = await get_oauth_client().list_products(get_products_path())
    normalized = [normalize_product(product) for product in products]
    return [product for product in normalized if product is not None]


def find_product(product_id: str, products: list[dict[str, Any]]) -> dict[str, Any] | None:
    for product in products:
        if str(product.get("product_id", "")) == product_id:
            return product
    return None


def parse_product_quota(product: dict[str, Any] | None) -> float | None:
    if not product:
        return None

    quota = product.get("quota")
    if quota in (None, ""):
        return None

    try:
        return float(quota)
    except (TypeError, ValueError):
        return None


ENTITLEMENT_LEVELS = {
    "experience": 1,
    "basic": 2,
    "pro": 3,
}


def normalize_product_slug(product: dict[str, Any] | None) -> str:
    if not product:
        return "experience"
    slug = str(product.get("slug") or "experience").strip().lower()
    return slug if slug in ENTITLEMENT_LEVELS else "experience"


def parse_product_duration_days(product: dict[str, Any] | None) -> int:
    if not product:
        return 30
    value = product.get("duration_days")
    try:
        days = int(value)
    except (TypeError, ValueError):
        return 30
    return days if days > 0 else 30


def entitlement_rank(slug: str | None) -> int:
    return ENTITLEMENT_LEVELS.get((slug or "experience").strip().lower(), 0)


def is_downgrade(current_slug: str | None, next_slug: str | None) -> bool:
    return entitlement_rank(next_slug) < entitlement_rank(current_slug)


def parse_optional_float(value: Any) -> float | None:
    if value in (None, ""):
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def dump_json(data: Any) -> str:
    return json.dumps(data, ensure_ascii=False, default=str)


def get_or_create_entitlement(
    db: Session,
    order: PaymentOrder,
    product: dict[str, Any] | None = None,
) -> PaymentOrderEntitlement:
    entitlement = (
        db.query(PaymentOrderEntitlement)
        .filter(PaymentOrderEntitlement.third_order_no == order.third_order_no)
        .first()
    )
    if entitlement:
        if product:
            entitlement.product_name = entitlement.product_name or product.get("name")
            entitlement.product_slug = entitlement.product_slug or normalize_product_slug(product)
            if entitlement.product_price is None:
                entitlement.product_price = parse_optional_float(product.get("price"))
            if entitlement.product_quota is None:
                entitlement.product_quota = parse_product_quota(product)
            if entitlement.duration_days is None:
                entitlement.duration_days = parse_product_duration_days(product)
            if not entitlement.product_snapshot:
                entitlement.product_snapshot = dump_json(product.get("raw") or product)
            entitlement.updated_at = local_now()
            db.commit()
        return entitlement

    entitlement = PaymentOrderEntitlement(
        third_order_no=order.third_order_no,
        external_user_id=order.external_user_id,
        openid=order.openid,
        product_id=order.product_id,
        product_slug=normalize_product_slug(product),
        product_name=(product or {}).get("name"),
        product_price=parse_optional_float((product or {}).get("price")),
        product_quota=parse_product_quota(product),
        duration_days=parse_product_duration_days(product),
        product_snapshot=dump_json((product or {}).get("raw") or product or {}),
    )
    db.add(entitlement)
    db.commit()
    db.refresh(entitlement)
    return entitlement


def apply_entitlement_level(external_user: ExternalUser, product: dict[str, Any] | None) -> None:
    product_slug = normalize_product_slug(product)
    if entitlement_rank(product_slug) >= entitlement_rank(external_user.entitlement_level):
        external_user.entitlement_level = product_slug
        external_user.updated_at = local_now()


def find_latest_token_for_slug(
    db: Session,
    external_user_id: int,
    product_slug: str,
) -> TokenRecord | None:
    entitlements = (
        db.query(PaymentOrderEntitlement)
        .filter(PaymentOrderEntitlement.external_user_id == external_user_id)
        .filter(PaymentOrderEntitlement.product_slug == product_slug)
        .filter(PaymentOrderEntitlement.issued_token_id.isnot(None))
        .order_by(PaymentOrderEntitlement.id.desc())
        .all()
    )
    for entitlement in entitlements:
        token = db.query(TokenRecord).filter(TokenRecord.id == entitlement.issued_token_id).first()
        if token and token.is_active:
            return token
    return None


def deactivate_lower_level_tokens(
    db: Session,
    external_user: ExternalUser,
    product: dict[str, Any] | None,
    keep_token_id: int | None = None,
) -> None:
    product_slug = normalize_product_slug(product)
    current_slug = external_user.entitlement_level if external_user.entitlement_level in ENTITLEMENT_LEVELS else "experience"
    if entitlement_rank(product_slug) <= entitlement_rank(current_slug):
        return

    entitlements = (
        db.query(PaymentOrderEntitlement)
        .filter(PaymentOrderEntitlement.external_user_id == external_user.id)
        .filter(PaymentOrderEntitlement.issued_token_id.isnot(None))
        .all()
    )
    for entitlement in entitlements:
        entitlement_slug = entitlement.product_slug or "experience"
        if entitlement_rank(entitlement_slug) >= entitlement_rank(product_slug):
            continue
        if keep_token_id and entitlement.issued_token_id == keep_token_id:
            continue
        token = db.query(TokenRecord).filter(TokenRecord.id == entitlement.issued_token_id).first()
        if token and token.is_active:
            token.is_active = False


def calculate_token_expires_at(
    db: Session,
    external_user: ExternalUser,
    product: dict[str, Any] | None,
) -> datetime:
    now = local_now()
    product_slug = normalize_product_slug(product)
    duration_days = parse_product_duration_days(product)

    if normalize_product_slug({"slug": external_user.entitlement_level}) == product_slug:
        current_token = find_latest_token_for_slug(db, external_user.id, product_slug)
        if current_token and current_token.expires_at:
            current_expires_at = to_local_naive(current_token.expires_at)
            base_time = current_expires_at if current_expires_at > now else now
            return base_time + timedelta(days=duration_days)

    return now + timedelta(days=duration_days)


def build_third_order_no() -> str:
    return f"AS{local_now().strftime('%Y%m%d%H%M%S')}{secrets.token_hex(4)}"


@router.get("/products")
async def list_payment_products():
    return {"products": await fetch_products()}


@router.get("/upgrade-context")
async def get_upgrade_context(
    service_token: str = Query(default=""),
    db: Session = Depends(get_db),
):
    if not service_token:
        raise HTTPException(status_code=400, detail="Service token is required")

    current_token = verify_token(service_token, db)
    if not current_token.external_user_id:
        raise HTTPException(status_code=400, detail="Service token is not linked to an OAuth user")

    external_user = (
        db.query(ExternalUser)
        .filter(ExternalUser.id == current_token.external_user_id)
        .first()
    )
    if not external_user:
        raise HTTPException(status_code=404, detail="External user not found")

    token_slug = get_token_entitlement_level(db, current_token)
    current_slug = token_slug if token_slug in ENTITLEMENT_LEVELS else "experience"
    products = await fetch_products()
    return {
        "current_slug": current_slug,
        "products": [
            {
                **product,
                "is_current": normalize_product_slug(product) == current_slug,
                "is_downgrade": is_downgrade(current_slug, normalize_product_slug(product)),
            }
            for product in products
        ],
    }


@router.get("/orders")
async def list_payment_orders(
    service_token: str = Query(default=""),
    db: Session = Depends(get_db),
):
    if not service_token:
        raise HTTPException(status_code=400, detail="Service token is required")

    current_token = verify_token(service_token, db)
    if not current_token.external_user_id:
        return {"orders": []}

    rows = (
        db.query(PaymentOrder, PaymentOrderEntitlement)
        .outerjoin(
            PaymentOrderEntitlement,
            PaymentOrderEntitlement.third_order_no == PaymentOrder.third_order_no,
        )
        .filter(PaymentOrder.external_user_id == current_token.external_user_id)
        .order_by(PaymentOrder.id.desc())
        .limit(100)
        .all()
    )

    orders = []
    for order, entitlement in rows:
        issued_token = None
        if entitlement and entitlement.issued_token_id:
            issued_token = (
                db.query(TokenRecord)
                .filter(TokenRecord.id == entitlement.issued_token_id)
                .first()
            )
        orders.append(
            {
                "third_order_no": order.third_order_no,
                "request_id": order.request_id,
                "product_id": order.product_id,
                "product_slug": entitlement.product_slug if entitlement else None,
                "product_name": entitlement.product_name if entitlement else None,
                "product_price": entitlement.product_price if entitlement else None,
                "product_quota": entitlement.product_quota if entitlement else None,
                "duration_days": entitlement.duration_days if entitlement else None,
                "paid_amount": entitlement.paid_amount if entitlement else None,
                "paid_at": entitlement.paid_at if entitlement else None,
                "issued_ai_quota": entitlement.issued_ai_quota if entitlement else None,
                "issued_token_id": entitlement.issued_token_id if entitlement else None,
                "issued_token_expires_at": issued_token.expires_at if issued_token else None,
                "issued_token_is_active": issued_token.is_active if issued_token else None,
                "status": order.status,
                "created_at": order.created_at,
                "updated_at": order.updated_at,
            }
        )

    return {"orders": orders}


@router.get("/status/{third_order_no}")
async def get_payment_status(
    third_order_no: str,
    user_token: str = Query(default=""),
    service_token_query: str = Query(default="", alias="service_token"),
    db: Session = Depends(get_db),
):
    order = (
        db.query(PaymentOrder)
        .filter(PaymentOrder.third_order_no == third_order_no)
        .first()
    )
    if not order:
        raise HTTPException(status_code=404, detail="Payment order not found")

    service_token = None
    can_return_service_token = False
    if user_token:
        external_user = get_external_user_by_user_token(db, user_token)
        can_return_service_token = bool(external_user and external_user.id == order.external_user_id)
    elif service_token_query:
        try:
            current_token = verify_token(service_token_query, db)
            can_return_service_token = bool(current_token.external_user_id == order.external_user_id)
            if can_return_service_token:
                external_user = (
                    db.query(ExternalUser)
                    .filter(ExternalUser.id == order.external_user_id)
                    .first()
                )
        except HTTPException:
            can_return_service_token = False

    if order.status == "paid" and can_return_service_token:
        entitlement = get_or_create_entitlement(db, order)
        product = None
        token = None
        if entitlement.issued_token_id:
            token = db.query(TokenRecord).filter(TokenRecord.id == entitlement.issued_token_id).first()
        if not token:
            token = (
                db.query(TokenRecord)
                .filter(TokenRecord.external_user_id == order.external_user_id)
                .filter(TokenRecord.name == f"oauth:biyu:{order.openid}:{order.third_order_no}")
                .order_by(TokenRecord.id.desc())
                .first()
            )
            if token:
                entitlement.issued_token_id = token.id
                entitlement.issued_ai_quota = token.ai_quota
                if entitlement.product_quota is None:
                    entitlement.product_quota = token.ai_quota
                try:
                    product = find_product(order.product_id, await fetch_products())
                except HTTPException as exc:
                    print(
                        "[PAYMENT_STATUS] fetch_product_failed",
                        {
                            "status_code": exc.status_code,
                            "detail": exc.detail,
                            "product_id": order.product_id,
                        },
                    )
                entitlement = get_or_create_entitlement(db, order, product)
                entitlement.updated_at = local_now()
                deactivate_lower_level_tokens(db, external_user, product, keep_token_id=token.id)
                apply_entitlement_level(external_user, product)
                db.commit()
        if not token:
            if external_user:
                try:
                    product = find_product(order.product_id, await fetch_products())
                except HTTPException as exc:
                    print(
                        "[PAYMENT_STATUS] fetch_product_failed",
                        {
                            "status_code": exc.status_code,
                            "detail": exc.detail,
                            "product_id": order.product_id,
                        },
                    )
                token = create_service_token(
                    db,
                    external_user,
                    ai_quota=parse_product_quota(product),
                    expires_at=calculate_token_expires_at(db, external_user, product),
                    name_suffix=order.third_order_no,
                )
                entitlement = get_or_create_entitlement(db, order, product)
                entitlement.issued_token_id = token.id
                entitlement.issued_ai_quota = token.ai_quota
                if entitlement.product_quota is None:
                    entitlement.product_quota = token.ai_quota
                entitlement.updated_at = local_now()
                deactivate_lower_level_tokens(db, external_user, product, keep_token_id=token.id)
                apply_entitlement_level(external_user, product)
                db.commit()
        if token and token.is_active:
            service_token = token.token

    return {
        "third_order_no": order.third_order_no,
        "request_id": order.request_id,
        "status": order.status,
        "product_id": order.product_id,
        "service_token": service_token,
        "issued_ai_quota": entitlement.issued_ai_quota if order.status == "paid" and can_return_service_token else None,
        "created_at": order.created_at,
        "updated_at": order.updated_at,
    }


@router.post("/notify")
async def notify_payment(request: PaymentNotifyRequest, db: Session = Depends(get_db)):
    print("[PAYMENT_NOTIFY] incoming", request.dict())
    order = (
        db.query(PaymentOrder)
        .filter(PaymentOrder.third_order_no == request.third_order_no)
        .first()
    )
    if not order:
        print("[PAYMENT_NOTIFY] order_not_found", {"third_order_no": request.third_order_no})
        raise HTTPException(status_code=404, detail="Payment order not found")

    is_paid = request.event == "as_platform_product.paid" or request.is_pay == 1 or request.state == 1
    entitlement = get_or_create_entitlement(db, order)
    if is_paid and not entitlement.issued_token_id:
        existing_token = (
            db.query(TokenRecord)
            .filter(TokenRecord.external_user_id == order.external_user_id)
            .filter(TokenRecord.name == f"oauth:biyu:{order.openid}:{order.third_order_no}")
            .order_by(TokenRecord.id.desc())
            .first()
        )
        if existing_token:
            entitlement.issued_token_id = existing_token.id
            entitlement.issued_ai_quota = existing_token.ai_quota
            if entitlement.product_quota is None:
                entitlement.product_quota = existing_token.ai_quota
            entitlement.updated_at = local_now()
            db.commit()
    should_issue_token = is_paid and not entitlement.issued_token_id

    issued_token = None
    if should_issue_token:
        external_user = (
            db.query(ExternalUser)
            .filter(ExternalUser.id == order.external_user_id)
            .first()
        )
        if external_user:
            product = None
            try:
                product = find_product(order.product_id, await fetch_products())
            except HTTPException as exc:
                print(
                    "[PAYMENT_NOTIFY] fetch_product_failed",
                    {
                        "status_code": exc.status_code,
                        "detail": exc.detail,
                        "product_id": order.product_id,
                    },
                )
            issued_token = create_service_token(
                db,
                external_user,
                ai_quota=parse_product_quota(product),
                expires_at=calculate_token_expires_at(db, external_user, product),
                name_suffix=order.third_order_no,
            )
            entitlement = get_or_create_entitlement(db, order, product)
            entitlement.issued_token_id = issued_token.id
            entitlement.issued_ai_quota = issued_token.ai_quota
            if entitlement.product_quota is None:
                entitlement.product_quota = issued_token.ai_quota
            deactivate_lower_level_tokens(db, external_user, product, keep_token_id=issued_token.id)
            apply_entitlement_level(external_user, product)
        else:
            print(
                "[PAYMENT_NOTIFY] external_user_not_found",
                {"external_user_id": order.external_user_id, "third_order_no": order.third_order_no},
            )

    order.status = "paid" if is_paid else "notify_received"
    if request.pay_request_id and not order.request_id:
        order.request_id = request.pay_request_id
    order.updated_at = local_now()
    entitlement.paid_amount = parse_optional_float(request.total_fee)
    entitlement.paid_at = request.paid_at
    entitlement.notify_payload = dump_json(request.dict())
    entitlement.updated_at = local_now()
    db.commit()

    print(
        "[PAYMENT_NOTIFY] updated",
        {
            "third_order_no": order.third_order_no,
            "status": order.status,
            "request_id": order.request_id,
            "issued_token_id": issued_token.id if issued_token else None,
        },
    )
    return {"ok": True, "status": order.status}


@router.post("/create")
async def create_payment(request: CreatePaymentRequest, db: Session = Depends(get_db)):
    product_id = request.product_id.strip()
    openid = request.openid.strip()
    user_token = request.user_token.strip()
    service_token = request.service_token.strip()
    print(
        "[PAYMENT_CREATE] incoming",
        {
            "product_id": product_id,
            "openid": openid,
            "has_user_token": bool(user_token),
            "has_service_token": bool(service_token),
            "state": request.state,
        },
    )

    if not product_id:
        raise HTTPException(status_code=400, detail="Product is required")
    if not openid and not user_token and not service_token:
        raise HTTPException(status_code=400, detail="User token, service token or openid is required")

    products = await fetch_products()
    print(
        "[PAYMENT_CREATE] fetched_products",
        {
            "count": len(products),
            "product_ids": [product.get("product_id") for product in products],
        },
    )
    if not products:
        raise HTTPException(status_code=502, detail="No products returned from OAuth service")

    product = find_product(product_id, products)
    if not product:
        print(
            "[PAYMENT_CREATE] product_not_found",
            {
                "requested_product_id": product_id,
                "available_product_ids": [product.get("product_id") for product in products],
            },
        )
        raise HTTPException(status_code=404, detail="Product not found")

    external_user = None
    if user_token:
        external_user = get_external_user_by_user_token(db, user_token)
        if not external_user:
            print("[PAYMENT_CREATE] invalid_user_token")
            raise HTTPException(status_code=401, detail="Invalid user token")
        openid = external_user.openid
    elif service_token:
        current_token = verify_token(service_token, db)
        if not current_token.external_user_id:
            raise HTTPException(status_code=400, detail="Service token is not linked to an OAuth user")
        external_user = (
            db.query(ExternalUser)
            .filter(ExternalUser.id == current_token.external_user_id)
            .first()
        )
        if not external_user:
            print("[PAYMENT_CREATE] service_token_external_user_not_found")
            raise HTTPException(status_code=404, detail="External user not found")
        openid = external_user.openid
        product_slug = normalize_product_slug(product)
        if is_downgrade(external_user.entitlement_level, product_slug):
            raise HTTPException(status_code=400, detail="Cannot downgrade before current entitlement expires")
    else:
        external_user = (
            db.query(ExternalUser)
            .filter(ExternalUser.provider == "biyu", ExternalUser.openid == openid)
            .first()
        )
    if not external_user:
        print("[PAYMENT_CREATE] external_user_not_found", {"openid": openid})
        raise HTTPException(status_code=404, detail="External user not found")

    return_url = get("oauth.payment_return_url", "") or get("oauth.purchase_return_url", "")
    if not return_url:
        print("[PAYMENT_CREATE] missing_return_url")
        raise HTTPException(status_code=500, detail="Payment return URL is not configured")

    third_order_no = build_third_order_no()
    order = PaymentOrder(
        third_order_no=third_order_no,
        external_user_id=external_user.id,
        openid=openid,
        product_id=product_id,
        status="pending",
        state=request.state,
    )
    db.add(order)
    db.commit()
    db.refresh(order)
    get_or_create_entitlement(db, order, product)

    pay_payload = {
        "product_id": product_id,
        "openid": openid,
        "third_order_no": third_order_no,
        "return_url": return_url,
        "state": request.state,
    }
    print("[PAYMENT_CREATE] upstream_request", pay_payload)

    try:
        pay_request = await get_oauth_client().create_pay_request(**pay_payload)
    except HTTPException as exc:
        order.status = "request_failed"
        order.updated_at = local_now()
        db.commit()
        print(
            "[PAYMENT_CREATE] upstream_error",
            {
                "status_code": exc.status_code,
                "detail": exc.detail,
                "third_order_no": third_order_no,
            },
        )
        raise

    request_id = pay_request.get("request_id")
    pay_url = pay_request.get("pay_url")
    print(
        "[PAYMENT_CREATE] upstream_response",
        {
            "request_id": request_id,
            "pay_url": pay_url,
            "expires_in": pay_request.get("expires_in"),
            "raw": pay_request,
        },
    )
    if not request_id or not pay_url:
        order.status = "request_failed"
        order.updated_at = local_now()
        db.commit()
        raise HTTPException(status_code=502, detail="Payment request missing pay_url")

    order.request_id = request_id
    order.pay_url = pay_url
    order.updated_at = local_now()
    db.commit()

    return {
        "third_order_no": third_order_no,
        "request_id": request_id,
        "pay_url": pay_url,
        "expires_in": pay_request.get("expires_in"),
        "product": product,
    }
