from __future__ import annotations

import secrets
from datetime import datetime, timedelta

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from config_loader import get
from database import get_db
from models import ExternalUser, OAuthUserSession, TokenRecord
from services.oauth_client import BiyuOAuthClient
from utils.timezone import local_now, to_local_naive

router = APIRouter(prefix="/api/oauth", tags=["oauth"])

_oauth_client: BiyuOAuthClient | None = None
_oauth_client_config: tuple[str, str, str, str, bool, str] | None = None


class OAuthExchangeRequest(BaseModel):
    code: str


def mask_sensitive(value):
    if isinstance(value, dict):
        masked = {}
        for key, item in value.items():
            key_lower = str(key).lower()
            if any(word in key_lower for word in ("secret", "token", "authorization")):
                masked[key] = "***"
            else:
                masked[key] = mask_sensitive(item)
        return masked
    if isinstance(value, list):
        return [mask_sensitive(item) for item in value]
    return value


def upstream_error(message: str, upstream_data: dict) -> HTTPException:
    return HTTPException(
        status_code=502,
        detail={
            "message": message,
            "upstream_data": mask_sensitive(upstream_data),
        },
    )


def get_oauth_client() -> BiyuOAuthClient:
    global _oauth_client, _oauth_client_config

    base_url = get("oauth.base_url", "")
    client_id = get("oauth.client_id", "")
    client_secret = get("oauth.client_secret", "")
    redirect_uri = get("oauth.redirect_uri", "")
    trust_env = bool(get("oauth.trust_env", False))
    payment_base_url = get("oauth.payment_base_url", "") or base_url

    if not all([base_url, client_id, client_secret, redirect_uri]):
        raise HTTPException(status_code=500, detail="OAuth is not configured")

    config_key = (base_url, client_id, client_secret, redirect_uri, trust_env, payment_base_url)
    if _oauth_client is None or _oauth_client_config != config_key:
        _oauth_client = BiyuOAuthClient(
            base_url,
            client_id,
            client_secret,
            redirect_uri,
            trust_env,
            payment_base_url,
        )
        _oauth_client_config = config_key
    return _oauth_client


def create_service_token(
    db: Session,
    external_user: ExternalUser,
    ai_quota: float | None = None,
    expires_days: int | None = None,
    expires_at: datetime | None = None,
    name_suffix: str | None = None,
) -> TokenRecord:
    expires_days = expires_days if expires_days is not None else get("oauth.default_token_expires_days", None)
    if expires_at is None and expires_days:
        expires_at = local_now() + timedelta(days=int(expires_days))

    token_name = f"oauth:{external_user.provider}:{external_user.openid}"
    if name_suffix:
        token_name = f"{token_name}:{name_suffix}"

    token = TokenRecord(
        token=secrets.token_hex(16),
        name=token_name,
        external_user_id=external_user.id,
        expires_at=expires_at,
        ai_quota=float(ai_quota if ai_quota is not None else get("oauth.default_ai_quota", 1000000.0)),
        permissions=get("oauth.default_permissions", "bio,ai"),
        is_active=True,
    )
    db.add(token)
    db.commit()
    db.refresh(token)

    return token


def create_oauth_user_session(db: Session, external_user: ExternalUser) -> OAuthUserSession:
    expires_hours = int(get("oauth.user_session_expires_hours", 24))
    session = OAuthUserSession(
        user_token=secrets.token_urlsafe(32),
        external_user_id=external_user.id,
        openid=external_user.openid,
        expires_at=local_now() + timedelta(hours=expires_hours),
        is_active=True,
    )
    db.add(session)
    db.commit()
    db.refresh(session)
    return session


def is_oauth_user_session_usable(session: OAuthUserSession) -> bool:
    if not session.is_active:
        return False
    if not session.expires_at:
        return True

    expires_at = to_local_naive(session.expires_at)
    return expires_at >= local_now()


def get_external_user_by_user_token(db: Session, user_token: str) -> ExternalUser | None:
    session = (
        db.query(OAuthUserSession)
        .filter(OAuthUserSession.user_token == user_token)
        .first()
    )
    if not session or not is_oauth_user_session_usable(session):
        return None

    return (
        db.query(ExternalUser)
        .filter(ExternalUser.id == session.external_user_id)
        .first()
    )


def get_or_create_service_token(db: Session, external_user: ExternalUser) -> TokenRecord:
    existing_token = get_current_service_token(db, external_user)
    if existing_token and is_service_token_usable(existing_token):
        return existing_token

    return create_service_token(db, external_user)


def get_current_service_token(db: Session, external_user: ExternalUser) -> TokenRecord | None:
    tokens = (
        db.query(TokenRecord)
        .filter(TokenRecord.external_user_id == external_user.id)
        .order_by(TokenRecord.id.desc())
        .all()
    )
    for token in tokens:
        if is_service_token_usable(token):
            return token
    return tokens[0] if tokens else None


def is_service_token_usable(token: TokenRecord) -> bool:
    if not token.is_active:
        return False
    if not token.expires_at:
        return True

    expires_at = to_local_naive(token.expires_at)
    return expires_at >= local_now()


@router.get("/start")
async def start_oauth_login():
    authorize_url = await get_oauth_client().create_authorize_url()
    return {"authorize_url": authorize_url}


@router.post("/exchange")
async def exchange_oauth_code(request: OAuthExchangeRequest, db: Session = Depends(get_db)):
    code = request.code.strip()
    if not code:
        raise HTTPException(status_code=400, detail="Missing OAuth code")

    token_data = await get_oauth_client().exchange_user_access_token(code)
    user_access_token = token_data.get("access_token")
    if not user_access_token:
        raise upstream_error("OAuth user token missing", token_data)

    user_info = await get_oauth_client().get_user_info(user_access_token)
    openid = user_info.get("openid")
    if not openid:
        raise upstream_error("OAuth openid missing", user_info)

    external_user = (
        db.query(ExternalUser)
        .filter(ExternalUser.provider == "biyu", ExternalUser.openid == openid)
        .first()
    )
    if not external_user:
        external_user = ExternalUser(provider="biyu", openid=openid)
        db.add(external_user)
        try:
            db.commit()
            db.refresh(external_user)
        except IntegrityError:
            db.rollback()
            external_user = (
                db.query(ExternalUser)
                .filter(ExternalUser.provider == "biyu", ExternalUser.openid == openid)
                .first()
            )
            if not external_user:
                raise HTTPException(status_code=500, detail="Failed to bind OAuth user")

    user_session = create_oauth_user_session(db, external_user)
    service_token = get_current_service_token(db, external_user)
    if not service_token and bool(get("oauth.auto_provision_token", False)):
        service_token = get_or_create_service_token(db, external_user)

    if not service_token or not is_service_token_usable(service_token):
        return {
            "openid": openid,
            "user_token": user_session.user_token,
            "status": "purchase_required",
            "purchase_url": get("oauth.purchase_url", ""),
        }

    return {
        "openid": openid,
        "user_token": user_session.user_token,
        "status": "ok",
        "service_token": service_token.token,
        "permissions": service_token.permissions,
        "ai_quota": service_token.ai_quota,
        "used_quota": service_token.used_quota,
        "expires_at": service_token.expires_at,
    }
