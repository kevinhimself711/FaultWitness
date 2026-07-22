# EVAL-G01-006 Report

## Result

Result: implementation checkpoint passed; complete Eval pending.

Candidate `5a1b607ff34e47b1f40d7dcb7e4042d0a384621d` implements the eight frozen FastAPI paths, fail-closed RS256 OIDC tenant derivation, PostgreSQL Incident/idempotency/event projection, and recoverable SSE controls. The candidate-bound private Control API and Keycloak realm were deployed with two synthetic tenants, four roles, and eight users. Live smoke passed authenticated create/read/SSE and rejected cross-tenant access, role injection, and false approval. Focused deployment tests passed (`6 passed`); the repository fast suite previously passed with 159 tests before this final identity reconciliation.

This checkpoint is not a complete EVAL-G01-006 pass. The full eight-path conformance and negative identity matrix, 10,000-event projection, 100 reconnects, retention-gap matrix, sustained slow-consumer/backpressure run, and correlated LangSmith evidence remain open and blocking for Gate closure.

## Required evidence

- Full candidate SHA and eight-path OpenAPI conformance.
- Identity/tenant/role/idempotency/version negative matrix.
- Ten-thousand-event projection and 100-reconnect replay results, including retention and backpressure.

## Open evidence

- Full eight-path OpenAPI and identity/tenant/role/idempotency/version matrix.
- 10,000-event ordering/projection and 100-reconnect recovery matrix.
- Retention-gap, slow-consumer, and backpressure outcomes under sustained load.
- Correlated sanitized LangSmith evidence for executed API and SSE paths.
