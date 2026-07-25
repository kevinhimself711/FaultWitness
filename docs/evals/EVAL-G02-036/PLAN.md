# EVAL-G02-036 Plan — Email-Memory Unified Candidate Gate Attempt

## Purpose

Execute the unchanged fourteen-phase G02 Gate Eval on candidate
`0ef51cdb5987aa8b1c5cf17e712fe513f1d33b74`. Prior terminal Eval assets remain immutable.

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

The manifest/G01 debt and 60/6/22 matrices retain their named passing source records with original
timestamps, artifact digests, producing revisions, and current-attempt `execution_count: 0`.
Scenario seeds 1–7 retain complete passing source trial payloads and digests; execution starts at
seed 8 and continues through seed 32. Candidate binding, static proof, candidate lab dependency,
affected scenarios, and all downstream phases execute for this candidate.

No inheritance changes N, thresholds, permissions, model route, token/cost ceilings, health
windows, destructive-once semantics, or failure meaning. Live trials persist atomically and only
classified transport/infrastructure failures are resumable.
