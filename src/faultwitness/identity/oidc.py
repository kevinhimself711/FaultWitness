"""Fail-closed OIDC JWT validation with bounded JWKS caching."""

from __future__ import annotations

import asyncio
import time
from dataclasses import dataclass
from typing import Any

import httpx
import jwt
from jwt import InvalidTokenError, PyJWK


class AuthenticationError(RuntimeError):
    pass


@dataclass(frozen=True, slots=True)
class OIDCSettings:
    issuer: str
    audience: str
    jwks_url: str
    tenant_claim: str = "tenant_id"
    cache_seconds: int = 300
    timeout_seconds: float = 3.0


@dataclass(frozen=True, slots=True)
class AuthenticatedPrincipal:
    tenant_id: str
    user_id: str
    roles: frozenset[str]
    token_id: str
    expires_at: int


class OIDCAuthenticator:
    def __init__(self, settings: OIDCSettings, client: httpx.AsyncClient | None = None) -> None:
        self.settings = settings
        self.client = client or httpx.AsyncClient(timeout=settings.timeout_seconds)
        self._keys: dict[str, Any] = {}
        self._loaded_at = 0.0
        self._lock = asyncio.Lock()

    async def authenticate(self, authorization: str | None) -> AuthenticatedPrincipal:
        if not authorization or not authorization.startswith("Bearer "):
            raise AuthenticationError("bearer token is required")
        token = authorization[7:].strip()
        if not token:
            raise AuthenticationError("bearer token is required")
        try:
            header = jwt.get_unverified_header(token)
            if header.get("alg") != "RS256" or not isinstance(header.get("kid"), str):
                raise AuthenticationError("unsupported token header")
            key = await self._key(header["kid"])
            claims = jwt.decode(
                token,
                key=key,
                algorithms=["RS256"],
                audience=self.settings.audience,
                issuer=self.settings.issuer,
                options={"require": ["exp", "iat", "iss", "aud", "sub", "jti"]},
            )
        except AuthenticationError:
            raise
        except (InvalidTokenError, httpx.HTTPError, KeyError, TypeError, ValueError) as error:
            raise AuthenticationError("OIDC token validation failed") from error
        tenant_id = claims.get(self.settings.tenant_claim)
        roles = (claims.get("realm_access") or {}).get("roles")
        if not isinstance(tenant_id, str) or not tenant_id or not isinstance(roles, list):
            raise AuthenticationError("required tenant or role claims are absent")
        normalized_roles = frozenset(role for role in roles if isinstance(role, str) and role)
        if not normalized_roles:
            raise AuthenticationError("required role claims are absent")
        return AuthenticatedPrincipal(
            tenant_id=tenant_id,
            user_id=str(claims["sub"]),
            roles=normalized_roles,
            token_id=str(claims["jti"]),
            expires_at=int(claims["exp"]),
        )

    async def _key(self, kid: str) -> Any:
        now = time.monotonic()
        if now - self._loaded_at >= self.settings.cache_seconds or kid not in self._keys:
            async with self._lock:
                now = time.monotonic()
                if now - self._loaded_at >= self.settings.cache_seconds or kid not in self._keys:
                    response = await self.client.get(self.settings.jwks_url)
                    response.raise_for_status()
                    document = response.json()
                    keys = document.get("keys") if isinstance(document, dict) else None
                    if not isinstance(keys, list):
                        raise AuthenticationError("OIDC JWKS is malformed")
                    loaded: dict[str, Any] = {}
                    for item in keys:
                        if isinstance(item, dict) and isinstance(item.get("kid"), str):
                            loaded[item["kid"]] = PyJWK.from_dict(item).key
                    if not loaded:
                        raise AuthenticationError("OIDC JWKS contains no usable keys")
                    self._keys = loaded
                    self._loaded_at = now
        try:
            return self._keys[kid]
        except KeyError as error:
            raise AuthenticationError("OIDC signing key is unknown") from error
