# EVAL-G02-044 Plan — Deterministic-Workload Unified Candidate Gate Attempt

## Purpose

Execute the frozen fourteen-phase G02 Gate Eval on candidate
`bd374683de25b824af8669a993c8c7b771c6001e` after C-G02-011 proved deterministic payment workload
and left a clean, restored, 24/24 Ready candidate-bound lab.

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

The first four deterministic checks execute before remote work. `lab-deploy-and-bind` consumes the
EVAL-G02-043 exact-candidate deployment artifact with `execution_count: 0`; rerunning the deployer
would delete the unchanged namespace and add no information. Because that deployment created a new
namespace epoch, the 60/6/22 matrices and all 32 scenarios execute fresh before baseline phases.

No phase changes N, thresholds, permissions, model route, token/cost ceilings, health windows, or
failure meaning. Live trials persist atomically; only classified transport/infrastructure failures
resume their affected unit.
