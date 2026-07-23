# EVAL-G01-006 Report

## Result

Result: **PASS** on final candidate `4c843553bad7a13023259d474e8fea1b8c174d40`.

Candidate `5a1b607ff34e47b1f40d7dcb7e4042d0a384621d` implements the eight frozen FastAPI paths, fail-closed RS256 OIDC tenant derivation, PostgreSQL Incident/idempotency/event projection, and recoverable SSE controls. The candidate-bound private Control API and Keycloak realm were deployed with two synthetic tenants, four roles, and eight users. Live smoke passed authenticated create/read/SSE and rejected cross-tenant access, role injection, and false approval. Focused deployment tests passed (`6 passed`); the repository fast suite previously passed with 159 tests before this final identity reconciliation.

This checkpoint is not a complete EVAL-G01-006 pass. The full eight-path conformance and negative identity matrix, 10,000-event projection, 100 reconnects, retention-gap matrix, sustained slow-consumer/backpressure run, and correlated LangSmith evidence remain open and blocking for Gate closure.

## Required evidence

- Full candidate SHA and eight-path OpenAPI conformance.
- Identity/tenant/role/idempotency/version negative matrix.
- Ten-thousand-event projection and 100-reconnect replay results, including retention and backpressure.

## Open evidence at implementation checkpoint

- Full eight-path OpenAPI and identity/tenant/role/idempotency/version matrix.
- 10,000-event ordering/projection and 100-reconnect recovery matrix.
- Retention-gap, slow-consumer, and backpressure outcomes under sustained load.
- Correlated sanitized LangSmith evidence for executed API and SSE paths.

## I-0015 replay checkpoint

The candidate audit now passes a deterministic 10,000-event ordering and
100-reconnect exact-cursor matrix plus retention-gap and bounded slow-consumer
tests. The real OIDC private smoke remains passing for create/read/SSE and
cross-tenant, identity-injection, role, and false-approval denial. Sustained live
backpressure and correlated final-candidate Trace evidence remain open.

The live private API matrix on candidate
`2d05b23ab01a1eb87317b9050475ec9ece309803` used the production PostgreSQL
store for 10,000 events and 100 SSE reconnects with exact ordering, no loss,
duplicate, or out-of-order event, correct retention-gap behavior, bounded
slow-consumer closure, and zero rows after cleanup. Candidate `c297dc6527b11c3272cee6378a270cb24f5a13af`
also passed the expanded live API path and denial matrix. Candidate `5638eb9`
then passed the cold-JWKS Keycloak outage matrix: a pre-issued token was denied
with HTTP 401 after Keycloak was stopped and the Control API cache was cleared,
before any state mutation; both services recovered Ready and the temporary token
Secret was removed. Final same-SHA replay and correlated Trace evidence remain.
