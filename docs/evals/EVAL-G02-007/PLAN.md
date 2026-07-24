# EVAL-G02-007 Plan — Live Isolation Reachability Corrective

## Purpose

Prove the I-0022 correction locally and deterministically. This Eval does not run any G02 Gate
phase, access cell, destructive scenario, external service, or model call.

## Deterministic cases

1. The baseline principal has exact egress to Prometheus, Loki, and Tempo in
   `fw-observability` on the frozen read-only ports.
2. The matching `fw-observability` ingress selects only `fw-baseline` plus the
   `baseline-agent` pod label.
3. Public HTTPS egress needed for LangSmith excludes private, loopback, link-local, metadata, and
   cluster address ranges; a broad private-network fixture fails closed.
4. Scenario-controller, sealed-evaluator, and ordinary-developer negative paths retain their frozen
   denies.
5. Gate orchestration resolves the active Iteration record's `eval_id`; terminal I-0020 cannot
   select or overwrite EVAL-G02-005, planned I-0023 resolves EVAL-G02-008, and `eval-changed`
   attributes an active-to-failed transition to the terminal Iteration rather than G01 closure.

## Pass criteria

- All five cases pass with one named negative fixture for each changed policy/selection branch.
- `verify-fast` and `eval-changed` pass.
- Validation N, Ground Truth, locked tests, quality/performance thresholds, health-oracle windows,
  model route, retry budget, tokens, cost, and Gate failure semantics are byte-for-byte unchanged.
- `open_evidence: []`.
