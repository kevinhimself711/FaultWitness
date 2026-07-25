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

## Closure-freeze execution boundary

ADR-0013's 2026-07-25 correction applies. EVAL-G02-030 remains immutable and is not rebound as a
passing attempt. Its individually passing, semantically unaffected phase evidence is referenced
without execution:

- `preflight-manifests` and `preflight-upstream-g01`: their manifest inputs did not change;
- `isolation-access-matrix`: collector, fixture, permissions, namespaces, runtime/configuration,
  environment, and all 60 matrix cells did not change;
- `trace-six-stage-matrix`: collector, fixture, stage definitions, trace route, runtime/configuration,
  environment, and all six stages did not change; and
- `all-surface-canary`: collector, fixture, canary values, 22 surfaces, runtime/configuration,
  environment, and egress/persistence routes did not change.

Each inherited phase records EVAL-G02-030 as its source, retains the original artifact digest,
producing revision, timestamps, execution count and private journal URI, and has new-candidate
`execution_count: 0`. No old artifact or trial is copied, relabelled, or executed.

The current candidate executes only `preflight-candidate-binding`,
`preflight-static-inheritance`, `lab-deploy-and-bind` (candidate/runtime binding only), the failed
`scenario-matrix`, and its downstream baseline, reconciliation, and close-readiness phases. The
payment-unreachable corrective changed only the scenario observer in `g02_lab.py` and its runbook;
it did not change the inherited phases' semantic subjects. If static impact proof contradicts any
statement above, the affected phase is not inherited and the attempt stops for attribution.
