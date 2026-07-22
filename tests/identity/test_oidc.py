from __future__ import annotations

import asyncio
import time

import httpx
import jwt
import pytest
from cryptography.hazmat.primitives.asymmetric import rsa

from faultwitness.identity.oidc import AuthenticationError, OIDCAuthenticator, OIDCSettings


def test_oidc_validates_signature_audience_issuer_and_tenant() -> None:
    asyncio.run(_exercise_oidc())


async def _exercise_oidc() -> None:
    private_key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    public_jwk = jwt.algorithms.RSAAlgorithm.to_jwk(private_key.public_key(), as_dict=True)
    public_jwk.update({"kid": "test-key", "alg": "RS256", "use": "sig"})

    async def handler(request: httpx.Request) -> httpx.Response:
        assert request.url.path == "/jwks"
        return httpx.Response(200, json={"keys": [public_jwk]})

    client = httpx.AsyncClient(transport=httpx.MockTransport(handler))
    settings = OIDCSettings("https://issuer.test", "faultwitness-api", "https://issuer.test/jwks")
    authenticator = OIDCAuthenticator(settings, client)
    now = int(time.time())
    claims = {
        "iss": settings.issuer,
        "aud": settings.audience,
        "sub": "user-1",
        "jti": "token-1",
        "iat": now,
        "exp": now + 60,
        "tenant_id": "tenant-a",
        "realm_access": {"roles": ["operator"]},
    }
    token = jwt.encode(claims, private_key, algorithm="RS256", headers={"kid": "test-key"})
    principal = await authenticator.authenticate("Bearer " + token)
    assert principal.tenant_id == "tenant-a"
    assert principal.roles == frozenset({"operator"})

    wrong_audience = jwt.encode(
        claims | {"aud": "other"}, private_key, algorithm="RS256", headers={"kid": "test-key"}
    )
    with pytest.raises(AuthenticationError, match="validation failed"):
        await authenticator.authenticate("Bearer " + wrong_audience)
    with pytest.raises(AuthenticationError):
        await authenticator.authenticate(None)
    await client.aclose()
