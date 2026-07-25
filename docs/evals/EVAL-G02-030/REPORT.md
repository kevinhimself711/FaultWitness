# EVAL-G02-030 Report

Result: `fail`.

Candidate `723c056defa11355b3c3ad48648c5d9deb4961b8` passed all four fail-fast
preflights, the real candidate-bound lab deployment, all 60 live access cells, all six trace-stage
cells, and all 22 canary surfaces. Each recorded phase executed exactly once. The access evidence
includes the complete Ground Truth and locked-test deny matrix; the trace and all-surface G01
carry-in supplements passed on the same candidate.

## Blocking result

The destructive `scenario-matrix` executed once. `SEED-G02-0001` (`kafkaQueueProblems`) completed
the frozen `HEALTHY -> FAULT_ACTIVE -> HEALTHY` sequence. `SEED-G02-0002`
(`paymentUnreachable`) then failed because the fault oracle did not reach `FAULT_ACTIVE`. Injection
readback succeeded, and no exact-restoration or recovery failure replaced the primary result. The
remaining 30 scenarios did not run and the phase was not retried on this candidate.

The live observer currently queries Jaeger with `service=payment` for `paymentUnreachable`, while
the unreachable condition can place the connection failure on the checkout caller without a
payment callee span. This is the bounded working hypothesis, not a retroactive pass or a claimed
root cause: the terminal trial persisted the typed reason but not its final raw observer sample.

## Adjudication

This is a deterministic `metric_fail`, not a classified transport failure. A-G02-004 is terminal
with complete negative evidence and `open_evidence: []`. C-G02-005 must first prove or falsify the
single caller/callee observation hypothesis through a named read-only real seam, then make only the
minimum attributable change. A later A-G02-005 uses a new candidate; no terminal work item or
destructive phase is reopened.

No deterministic baseline, live baseline, Bailian trial, model call, token, or model cost phase
ran. No validation N, quality/performance threshold, permission, Ground Truth, locked-test rule,
model route, token/cost ceiling, oracle, destructive-once rule, or failure semantic changed.
