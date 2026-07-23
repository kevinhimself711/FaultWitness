# EVAL-G01-005 Report

## Result

Result: **PASS** on final candidate `cea2e63948d86bac3a3ae5d3afa68b477f20e3c2`.

Candidate `48449618f1aafdadfde0d4593cb9bb10b96583f6` implements owner-isolated state, idempotency, Outbox/Inbox/DLQ, Redis Streams recovery, and fenced AES-GCM checkpoints. `verify-fast` passed with 146 tests. The migration was applied idempotently to the private PostgreSQL service with digest `94a32e2ee4a93593d8ed769e7c1f9fe9b7a076447b141106b206da1b2622b846`; a remote inventory then observed migration `001_i0011` and 17 runtime tables. Secret values and raw rows were not captured.

This checkpoint is not a complete EVAL-G01-005 pass. The 82-transition real-database run, 10,000 duplicates, 100 crash schedules, stale-fence race matrix, Redis final drain, and correlated LangSmith evidence remain open and blocking for Gate closure.

## Required evidence

- Full candidate SHA, migration/role report, and all-transition database conformance.
- Duplicate-delivery, crash-schedule, fencing, checkpoint, poison-message, and final-drain summaries.

## Open evidence at implementation checkpoint

- Real PostgreSQL conformance for all 82 transitions.
- 10,000 duplicate deliveries and 100 deterministic crash schedules.
- Stale-fence races, Redis pending recovery, poison DLQ, and final reconciliation.
- Correlated sanitized LangSmith evidence for executed durable runtime paths.

## I-0015 replay checkpoint

The audit suite now executes 10,000 duplicate Inbox deliveries and 100 injected
transaction failures against the semantic persistence adapter, proving one
mutation per Event and zero partial state/Outbox/idempotency commit in the
reference matrix. Private candidate `16294bc` additionally reconciled all four
owner Outboxes, DLQ, stale leases, Trace delivery state, migrations, and six
candidate bindings to zero drift or pending work. Real PostgreSQL execution of
all 82 transitions, stale-fence races, Redis crash recovery, and correlated Trace
evidence remain blocking.

Subsequent live private-server matrices replaced the remaining reference-only
evidence. Candidate `98b21cbf361154d57bd28e65784ff818cecfe5a5` executed all
82 legal transitions against PostgreSQL, accepted 5,000 unique Inbox deliveries
from 10,000 attempts, survived 100 crash injections with zero partial commit,
and rejected stale fencing while accepting the current fence. Candidate
`b9be07766b25fc78c0fcb160dbfb00248ac071cf` recovered and ACKed all 100
Redis pending messages after consumer death, leaving zero pending entries.
Final same-SHA replay and correlated Trace binding remain open.
