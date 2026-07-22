# EVAL-G01-005 Report

## Result

Result: implementation checkpoint passed; complete Eval pending.

Candidate `48449618f1aafdadfde0d4593cb9bb10b96583f6` implements owner-isolated state, idempotency, Outbox/Inbox/DLQ, Redis Streams recovery, and fenced AES-GCM checkpoints. `verify-fast` passed with 146 tests. The migration was applied idempotently to the private PostgreSQL service with digest `94a32e2ee4a93593d8ed769e7c1f9fe9b7a076447b141106b206da1b2622b846`; a remote inventory then observed migration `001_i0011` and 17 runtime tables. Secret values and raw rows were not captured.

This checkpoint is not a complete EVAL-G01-005 pass. The 82-transition real-database run, 10,000 duplicates, 100 crash schedules, stale-fence race matrix, Redis final drain, and correlated LangSmith evidence remain open and blocking for Gate closure.

## Required evidence

- Full candidate SHA, migration/role report, and all-transition database conformance.
- Duplicate-delivery, crash-schedule, fencing, checkpoint, poison-message, and final-drain summaries.

## Open evidence

- Real PostgreSQL conformance for all 82 transitions.
- 10,000 duplicate deliveries and 100 deterministic crash schedules.
- Stale-fence races, Redis pending recovery, poison DLQ, and final reconciliation.
- Correlated sanitized LangSmith evidence for executed durable runtime paths.
