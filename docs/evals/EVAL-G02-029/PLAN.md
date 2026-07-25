# EVAL-G02-029 Plan — Candidate-Bound Trace Service Deployment Corrective

## Purpose

Verify only the changed G02 lab-to-trace-service binding seam. Reuse the existing protocol and
observability tests, then execute the existing trace-service deploy, inspect, and sanitized smoke
commands once on the exact corrective candidate.

## Frozen checks

- Local tests prove the lab handler establishes and verifies the exact trace candidate before its
  SUT result can pass, and rejects a stale deployment summary.
- The real seam deploys the existing service, proves `1/1` Ready with `ClusterIP` and the exact
  candidate binding, then completes the existing sanitized smoke with zero pending delivery. The
  rollout wait has no preset wall-clock kill.
- The public artifact contains only candidate/environment binding, sanitized readiness/outcome,
  and artifact digests; no credential, response body, private trace, secret, or PII is retained.
- Gate L2, six-stage/access/canary matrices, destructive scenarios, Bailian, model calls, tokens,
  and cost remain zero; `open_evidence: []` is required.

No preset orchestration timeout and no validation N, threshold, permission, oracle, quality,
performance, model route, token/cost ceiling, or failure-semantic change is permitted.
