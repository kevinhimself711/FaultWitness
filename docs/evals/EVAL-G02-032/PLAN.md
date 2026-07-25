# EVAL-G02-032 Plan — Post-Payment-Observer Unified Candidate Gate Attempt

## Purpose

Execute the unchanged fourteen-phase G02 Gate Eval on the immutable post-C-G02-005 candidate. All
prior failed Eval assets remain immutable and are not rebound or counted as new-candidate evidence.

## Frozen phase order

1. `preflight-manifests`
2. `preflight-candidate-binding`
3. `preflight-static-inheritance`
4. `preflight-upstream-g01`
5. `lab-deploy-and-bind`
6. `isolation-access-matrix`
7. `trace-six-stage-matrix`
8. `all-surface-canary`
9. `scenario-matrix`
10. `baseline-deterministic`
11. `baseline-live`
12. `baseline-aggregate`
13. `candidate-reconciliation`
14. `close-readiness`

All frozen N, thresholds, permissions, model route, token/cost ceilings, destructive-once rule, and
failure semantics remain unchanged. Estimates are observability only and never kill execution.
