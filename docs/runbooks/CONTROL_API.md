# Control API Runbook

## Configuration

Production startup uses `faultwitness.api.server:app`. It requires PostgreSQL credentials from the existing private Secret plus `FW_OIDC_ISSUER`, `FW_OIDC_AUDIENCE`, and `FW_OIDC_JWKS_URL`. The service fails during startup when PostgreSQL is unavailable and fails every new authenticated request closed when JWKS validation is unavailable. Tokens, database URLs, realm credentials, and raw user identifiers must not enter logs or public evidence.

Apply both additive migrations from a clean candidate:

```powershell
$candidateSha = git rev-parse HEAD
uv run python -m faultwitness_dev deploy-runtime-schema --candidate-sha $candidateSha
uv run python -m faultwitness_dev inspect-runtime-schema --candidate-sha $candidateSha
uv run python -m faultwitness_dev deploy-control-api --candidate-sha $candidateSha
uv run python -m faultwitness_dev inspect-control-api --candidate-sha $candidateSha
```

The deploy command stages the digest-pinned Python base through the repository's private offline-image path, builds the locked application image on the server, imports it into K3s, copies PostgreSQL Secret data across namespaces without printing values, and creates a private `ClusterIP` workload with default-deny and explicit DNS/PostgreSQL/Keycloak traffic. Local synthetic conformance injects a test authenticator explicitly; the production entrypoint never enables such a bypass.

## Operational checks

1. Confirm migration `002_i0012` and the candidate binding.
2. Confirm the OIDC discovery/JWKS endpoint is reachable from `fw-control` but the Control API remains private `ClusterIP` only.
3. Exercise all eight paths with two synthetic tenants and viewer/operator/approver/admin roles.
4. Confirm body/header identity injection, invalid issuer/audience/signature, cross-tenant reads, false approvals, and stale versions all fail before unauthorized mutation.
5. Reconnect SSE from a retained cursor and confirm exact order; exercise future cursor, retention gap, token expiry, and a saturated buffer.

## Recovery

The PostgreSQL projection is authoritative. A restarted API replays from `event_projection`; it does not reconstruct state from an in-memory queue. An individual slow connection is closed and resumes from its last delivered cursor. Keycloak/JWKS outage rejects new requests; database outage returns dependency failure and never falls back to memory. G01 uses one Control API replica, so cross-replica live fanout is not claimed.
