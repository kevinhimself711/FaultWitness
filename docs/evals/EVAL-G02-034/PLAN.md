# EVAL-G02-034 Plan — Prior-Recovery Unified Candidate Gate Attempt

## Purpose

Execute the unchanged fourteen-phase G02 Gate Eval on candidate
`7fdb34999bef3413ccf16774440135730b23b5e4`. Prior terminal Eval assets remain immutable.

## Phase order and execution boundary

The exact frozen phase IDs and order are:

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

The manifest/G01 debt and 60/6/22 matrices are inherited from their named passing source records
with original timestamps, artifact digests, producing revisions, and new-attempt
`execution_count: 0`. Scenario seeds 1–3 are inherited from EVAL-G02-032 with their complete trial
payloads and source digests. The scenario runner starts execution at seed 4 and continues through
seed 32. Candidate binding, static proof, the candidate lab dependency, scenario seeds 4–32, and
all downstream phases execute for this candidate.

No inherited evidence changes N, thresholds, permissions, model route, token/cost ceilings,
health windows, destructive-once semantics, or failure meaning. Every live trial persists
atomically; only a classified transport/infrastructure failure is resumable.
