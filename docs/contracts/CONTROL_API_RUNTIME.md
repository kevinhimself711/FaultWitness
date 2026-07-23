# Control API Runtime Contract

## Identity boundary

The eight frozen public paths accept tenant, user, role, and token authority only from a verified RS256 OIDC token. Verification requires an exact issuer and audience, a known JWKS `kid`, expiration, issued-at, subject, token ID, tenant claim, and at least one recognized realm role. Identity-like request headers are rejected and identity-like body fields fail strict extra-field validation before any write.

`viewer` has read scope, `operator` has read/write scope, `approver` has read/approval scope, and `admin` has all three. Tenant-qualified lookup intentionally returns `ERR-NOT-FOUND` for another tenant rather than disclosing existence.

## Write semantics

- Create, cancel, feedback, and approval require a tenant/operation-scoped `Idempotency-Key` and canonical request digest.
- Same key and digest returns the original response; same key with another digest returns `ERR-CONFLICT`.
- Expected state version is checked while the Incident row is locked.
- Incident snapshot, projection event, and idempotent response commit in one PostgreSQL transaction.
- Feedback appends evidence and advances only the event cursor; it never rewrites terminal state.
- Approval is accepted only when a persisted pending action ID and immutable digest match. Because G01 creates no actions, the truthful default is conflict, not fabricated success.
- `/v1/tools` and `/v1/skills` truthfully return empty arrays until their later Gates establish capability.

## SSE state and failure semantics

The connection follows `OPEN → REPLAY → LIVE → CLOSED`. Projection sequences are tenant/Incident scoped and strictly increasing. `Last-Event-ID` replays every retained event with a greater sequence. A future or malformed cursor is rejected; an expired cursor receives a typed `control.retention_gap` event and closes. A saturated per-client buffer receives `control.slow_consumer` with its recoverable cursor and closes without blocking the publisher. Heartbeats do not advance the cursor, and a connection cannot outlive its token expiration.

Retention is bounded by seven days or 100,000 projected events per Incident, whichever is reached first. Domain events remain governed by their separate audit retention policy.
