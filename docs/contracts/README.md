# FaultWitness Contract Baseline

## Authority order

1. `state-machines/*.yaml` is the single source of truth for state transitions.
2. `COMMAND_EVENT_CATALOG.yaml` defines ownership, idempotency, concurrency checks, and typed errors for every referenced Command/Event.
3. `TYPE_CATALOG.yaml` freezes owner, store, version, fields, source, sensitivity, and invariants for the 21 core types.
4. `openapi.yaml` and `asyncapi.yaml` freeze external REST/SSE and internal Command/Event designs.
5. `FAILURE_SEMANTICS.yaml` fixes error codes and dependency/action failure behavior.
6. `WALKTHROUGH_BINDINGS.yaml` binds every frozen architecture walkthrough to concrete transitions, Commands, failures, and REST operations.
7. `STATE_MACHINE_DIAGRAMS.md` is deterministically rendered from the YAML and byte-checked; it is not independently editable.

These are design contracts, not generated server/client code and not proof that the product is running.

## Mutation contract

- A component may mutate only the state it owns in `ARCHITECTURE.yaml`.
- Every state transition declares Actor, Guard, structured Preconditions, Command, Event, automatic/manual behavior, and failure semantics.
- Every state-changing Command is idempotent and checks `state_version`, fencing token, or action digest plus version.
- State and outbox commit in one owner transaction; event delivery is at least once and consumers deduplicate `event_id`.
- Terminal states have no outgoing transition. Feedback, audit, and reconciliation evidence append separately.

## Identity and tenancy

`tenant_id`, `user_id`, and `roles` originate only in validated OIDC claims. Public request schemas intentionally omit these fields. Internal envelopes propagate authenticated tenant context but do not let message payloads replace it. Every receiving owner revalidates tenant and scope.

## REST and SSE

The REST baseline contains exactly eight paths. Create, approval, cancel, and feedback require `Idempotency-Key`; approval, cancel, and feedback carry `expected_state_version`. Conflict uses HTTP 409, quota/backpressure 429, dependency failure 503, and every error uses `code`, `message`, `retryable`, `correlation_id`, and `details`.

Incident events use SSE with monotonic event IDs and `Last-Event-ID`. A retention gap is a typed visible event, never a silently fabricated resume.

## Command and Event delivery

Commands express intent to the state owner and are not authorization by themselves. Events describe committed owner facts. The receiving owner checks current policy, tenant, version, digest, idempotency, and fencing as applicable. Publisher retry and consumer deduplication provide at-least-once reliability without a false exactly-once claim.

## Safety paths

- R2 can dispatch only after tenant, digest, resource version, expiry, policy, and single-use grant checks.
- Agent Graph can emit an ActionProposal but cannot execute it.
- Action Executor is the sole privileged writer and requires verified postconditions for `COMMITTED`.
- `UNCERTAIN` has no automatic transition; only read-only reconciliation or manual handling is allowed.
- Runtime success requires the current fencing token, matching attempt, committed checkpoint, and state version.
- Ground Truth, locked answers, secrets, and private chain-of-thought are absent from request and core type contracts.

## Verification

`uv run python -m faultwitness_dev validate` validates Schema syntax, cross-references, reachability, terminal convergence, safety paths, diagrams, external/internal interface envelopes, fixed failure semantics, and core type boundaries. EVAL-G00-005 adds frozen negative mutations for each high-risk invariant.
