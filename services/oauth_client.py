from __future__ import annotations

import time
from typing import Any
from urllib.parse import urlparse

import httpx
from fastapi import HTTPException


class BiyuOAuthClient:
    def __init__(
        self,
        base_url: str,
        client_id: str,
        client_secret: str,
        redirect_uri: str,
        trust_env: bool = False,
        payment_base_url: str | None = None,
    ):
        self.base_url = base_url.rstrip("/")
        self.payment_base_url = (payment_base_url or base_url).rstrip("/")
        self.client_id = client_id
        self.client_secret = client_secret
        self.redirect_uri = redirect_uri
        self.trust_env = trust_env
        self._client_access_token: str | None = None
        self._client_access_token_expires_at = 0.0

    def _mask_sensitive(self, value: Any) -> Any:
        if isinstance(value, dict):
            masked = {}
            for key, item in value.items():
                key_lower = str(key).lower()
                if any(word in key_lower for word in ("secret", "token", "authorization")):
                    masked[key] = "***"
                else:
                    masked[key] = self._mask_sensitive(item)
            return masked
        if isinstance(value, list):
            return [self._mask_sensitive(item) for item in value]
        return value

    def _missing_field_error(self, message: str, upstream_data: dict[str, Any]) -> HTTPException:
        return HTTPException(
            status_code=502,
            detail={
                "message": message,
                "upstream_data": self._mask_sensitive(upstream_data),
            },
        )

    async def _request(self, method: str, path: str, **kwargs) -> dict[str, Any]:
        base_url = kwargs.pop("base_url", self.base_url)
        url = f"{base_url}{path}"
        try:
            headers = {
                "Accept": "application/json",
                **(kwargs.pop("headers", {}) or {}),
            }
            async with httpx.AsyncClient(
                timeout=10.0,
                follow_redirects=False,
                trust_env=self.trust_env,
            ) as client:
                response = await client.request(method, url, headers=headers, **kwargs)
        except httpx.RequestError as exc:
            host = urlparse(base_url).netloc or base_url
            raise HTTPException(
                status_code=502,
                detail=f"Cannot connect to OAuth service: {host}",
            ) from exc

        try:
            data = response.json()
        except ValueError:
            body_preview = response.text[:2000]
            content_type = response.headers.get("content-type", "")
            raise HTTPException(
                status_code=response.status_code,
                detail={
                    "message": "OAuth service returned invalid JSON",
                    "url": url,
                    "status_code": response.status_code,
                    "content_type": content_type,
                    "body_preview": body_preview,
                },
            )

        if response.status_code >= 400:
            raise HTTPException(
                status_code=response.status_code,
                detail={
                    "message": data.get("error_description") or data.get("error") or "OAuth request failed",
                    "url": url,
                    "status_code": response.status_code,
                    "upstream_data": self._mask_sensitive(data),
                },
            )

        return data

    async def get_client_access_token(self) -> str:
        if self._client_access_token and time.time() < self._client_access_token_expires_at - 60:
            return self._client_access_token

        data = await self._request("POST", "/oauth/client/token", json={
            "client_id": self.client_id,
            "client_secret": self.client_secret,
        })

        token_data = data.get("data") or {}
        token = token_data.get("access_token")
        if not token:
            raise self._missing_field_error("OAuth client token missing", data)

        self._client_access_token = token
        self._client_access_token_expires_at = time.time() + int(token_data.get("expires_in", 7200))
        return token

    async def create_authorize_url(self) -> str:
        client_access_token = await self.get_client_access_token()
        data = await self._request(
            "POST",
            "/oauth/authorize/request",
            headers={"X-OAuth-Client-Token": client_access_token},
            json={"redirect_uri": self.redirect_uri},
        )

        authorize_url = (data.get("data") or {}).get("authorize_url")
        if not authorize_url:
            raise self._missing_field_error("OAuth authorize URL missing", data)
        return authorize_url

    async def exchange_user_access_token(self, code: str) -> dict[str, Any]:
        data = await self._request("POST", "/oauth/token", json={
            "client_id": self.client_id,
            "client_secret": self.client_secret,
            "code": code,
            "redirect_uri": self.redirect_uri,
        })
        return data.get("data") or {}

    async def get_user_info(self, user_access_token: str) -> dict[str, Any]:
        data = await self._request(
            "GET",
            "/oauth/user/info",
            headers={"Authorization": f"Bearer {user_access_token}"},
        )
        return data.get("data") or {}

    async def list_products(self, products_path: str) -> list[dict[str, Any]]:
        data = await self._request(
            "GET",
            products_path,
            base_url=self.payment_base_url,
        )
        payload = data.get("data") or []
        if isinstance(payload, dict):
            products = payload.get("products") or payload.get("list") or payload.get("items") or []
        else:
            products = payload
        return products if isinstance(products, list) else []

    async def create_pay_request(
        self,
        product_id: str,
        openid: str,
        third_order_no: str,
        return_url: str,
        state: str = "",
    ) -> dict[str, Any]:
        client_access_token = await self.get_client_access_token()
        print("[OAUTH_PAY_REQUEST] client_access_token", client_access_token)
        payload = {
            "product_id": product_id,
            "openid": openid,
            "third_order_no": third_order_no,
            "return_url": return_url,
            "state": state,
        }
        print(
            "[OAUTH_PAY_REQUEST] request",
            {
                "url": f"{self.payment_base_url}/oauth/as-platform-product/pay/request",
                "payload": payload,
                "has_client_token": bool(client_access_token),
            },
        )
        data = await self._request(
            "POST",
            "/oauth/as-platform-product/pay/request",
            base_url=self.payment_base_url,
            headers={"X-OAuth-Client-Token": client_access_token},
            json=payload,
        )
        print("[OAUTH_PAY_REQUEST] response", data)
        return data.get("data") or {}
