# EVAL-G02-042 Plan — Clean-Lab Unified Candidate Gate Attempt

## Purpose

Execute the frozen fourteen-phase G02 Gate Eval on candidate
`9f51ddaf8c6d2168ef6676ccb8e8b133599cd2a9` after clean `fw-sut` recreation. Prior terminal Eval
assets remain immutable.

## Exact phase order

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

Only manifest debt and immutable G01 debt retain source records with original timestamps, artifact
digests, producing revisions, and current-attempt `execution_count: 0`. Candidate binding and static
proof execute before all remote work. Namespace recreation invalidates prior remote-state evidence,
so 60/6/22 and all 32 scenarios execute on this candidate before baseline phases.

No phase changes N, thresholds, permissions, model route, token/cost ceilings, health windows, or
failure meaning. Live trials persist atomically; only classified transport/infrastructure failures
resume their affected unit.
