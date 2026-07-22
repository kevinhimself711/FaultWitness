# EVAL-G01-005 Plan — Durable State, Checkpoint and Transactional Events

## Purpose

Prove on real PostgreSQL and Redis that state, idempotency, Outbox, Inbox, checkpoint, fencing, and at-least-once delivery converge without partial commit or duplicate effect under crash and replay.

## Candidate protocol

1. Apply migrations to a clean database and verify role/schema ownership and migration head.
2. Run all 82 transition paths through real owner transactions and compare state/Event outputs to EVAL-G01-004.
3. Inject failures before/after state write, Outbox write, commit, XADD, Inbox commit, XACK, checkpoint, and lease expiry.
4. Run 10,000 duplicate deliveries and at least 100 deterministic crash schedules with stable seeds.
5. Drain and reconcile Outbox, consumer pending entries, Inbox, DLQ, and trace-buffer placeholders before reporting.

## Blocking checks

- State, idempotent response, and Outbox are atomic within an owner transaction.
- XADD-before-mark and commit-before-XACK duplicates are absorbed by Inbox without duplicate state mutation.
- Stale/expired fencing tokens cannot write checkpoint, complete task, or dispatch work.
- Encrypted serializer rejects pickle/unknown formats; checkpoint and graph Outbox commit together.
- Poison/incompatible messages enter auditable DLQ and never mutate business state.

## Pass criteria

- Partial commit, duplicate state mutation, stale-fence acceptance, and committed checkpoint loss: 0.
- All 82 transitions conform on PostgreSQL.
- All 10,000 duplicate deliveries and 100 crash schedules converge to the expected state.
- Candidate ends with migration drift, unexplained DLQ, stale lease, and backlog threshold violation: 0.

## Evidence contract

Public artifacts contain synthetic IDs, aggregate counts, seeds, failure-point outcomes, digests, and candidate SHA. Database URLs, tenant secrets, payload canaries, and raw rows remain private.
