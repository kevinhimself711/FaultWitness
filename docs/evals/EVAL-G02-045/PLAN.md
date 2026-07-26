# EVAL-G02-045 Plan — Replay-Stable Trace Envelope Corrective

## Purpose

Prove exact replayability of one candidate/environment-bound trace envelope without executing a Gate
matrix.

## Scope

1. Run the existing G02 collector tests, including byte-equivalent envelope replay. The immutable
   commit timestamp must be normalized to UTC and accepted by the strict `TraceEnvelope` contract
   before remote execution.
2. Deploy the committed corrective trace-service candidate and provision its existing probe binding.
3. Invoke the same existing candidate-bound trace operation twice.
4. Verify both invocations return the same six trace IDs/stages and the second produces no payload
   conflict; preserve sanitized trace-service readiness and duplicate evidence.
5. Confirm access, canary, scenarios, baselines, Gate L2 orchestration, and model calls remain zero.

No stage count, observability target, N, permission, quality/performance threshold, model route,
token, or cost setting changes.
