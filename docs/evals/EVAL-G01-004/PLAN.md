# EVAL-G01-004 Plan — Executable Contracts and Transition Kernel

## Purpose

Prove that executable Pydantic and transition contracts are a deterministic, strict, backward-compatible compilation of the frozen G00 authority rather than a second hand-maintained model.

## Candidate protocol

1. Generate package resources twice from a clean checkout and compare bytes and recorded source digests.
2. Enumerate every core/support type, state, transition, Command, Event, Error, actor, guard, and precondition.
3. Execute all legal transitions and mutation-generated illegal cases for owner, actor, guard, version, idempotency, terminal state, and schema version.
4. Compare OpenAPI/AsyncAPI and public examples against 1.0.0 for breaking changes; record intended additive 1.1.0 support contracts.
5. Verify startup rejection for unknown or missing registry bindings.

## Blocking checks

- Exact counts and identifiers for 21 core types, 52 states, 82 transitions, 34 Commands, 43 Events, and 10 Errors.
- `extra="forbid"`, UTC time, typed IDs, canonical digest, TenantContext provenance, and terminal immutability.
- Separate write ownership for Incident, Runtime Task, Agent Graph, and ActionTransaction.
- No executable YAML expression or dynamic guard evaluation.
- Byte-stable generation and non-edited generated outputs.

## Pass criteria

- Frozen contract drift, illegal-transition acceptance, missing registry rejection, and public breaking change: 0.
- Every legal transition emits the specified typed state/Event result.
- Same idempotency key with a different canonical digest is rejected.
- Generation is byte-identical across Windows and Ubuntu.

## Evidence contract

Artifacts include normalized conformance/mutation summaries, source/output digests, compatibility report, and candidate SHA. This deterministic Eval produces no live model trace, while LangSmith remains mandatory for later G01 runtime Evals.
