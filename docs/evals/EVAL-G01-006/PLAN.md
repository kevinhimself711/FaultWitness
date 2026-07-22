# EVAL-G01-006 Plan — Authenticated Control API and Recoverable SSE

## Purpose

Prove that all frozen public paths derive identity from OIDC, enforce tenant/role/version/idempotency semantics, and provide a durable SSE feed that recovers precisely under reconnect, retention, and backpressure.

## Candidate protocol

1. Provision two synthetic tenants and four roles in the candidate Keycloak realm.
2. Execute OpenAPI positive/negative conformance for all eight paths with real state and Outbox services.
3. Inject forged, expired, wrong-audience, wrong-issuer, and identity-bearing body/header requests before any write.
4. Publish 10,000 mixed Incident Events, reconnect 100 times at deterministic cursors, and compare projection sequence/content.
5. Exercise expired/future/invalid cursors, heartbeat, buffer saturation, token expiry, and Keycloak outage.

## Blocking checks

- Tenant/user/roles can arise only from validated JWT claims and cannot be overridden.
- Create returns idempotent original responses; conflicting digests and stale state versions fail with typed errors.
- Approval succeeds only for a real pending proposal with a matching digest; empty Tool/Skill capability remains truthful.
- Feed sequence is durable and strictly increasing; retention gap emits a typed terminal control event.
- Slow consumers close without blocking publisher and resume from the last delivered ID.

## Pass criteria

- Eight of eight paths conform; invalid identity, body/header injection, and cross-tenant success: 0.
- Unauthorized state mutation and false approval/capability success: 0.
- 10,000-event loss, duplicate projection, or order mismatch: 0.
- All 100 reconnects recover exactly; retention/backpressure cases are typed and recoverable.

## Evidence contract

Only synthetic tenant pseudonyms, typed outcomes, counts, timings, digests, and candidate SHA enter public evidence. JWTs, realm admin credentials, raw user identifiers, private reasoning, and server addresses never do.
