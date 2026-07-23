# EVAL-G02-005 Plan — Unified Candidate Orchestration

## Purpose

Evaluate one frozen G02 candidate using only runners, fixtures, interfaces, and adjudication
semantics completed by I-0016 through I-0019. This Eval establishes readiness but does not close
G02.

## Phase order and budget

1. `preflight-manifests` — 2m.
2. `preflight-candidate-binding` — 3m.
3. `preflight-static-inheritance` — 8m.
4. `preflight-upstream-g01` — 2m.
5. `lab-deploy-and-bind` — 12m.
6. `isolation-access-matrix` — 10m.
7. `trace-six-stage-matrix` — 8m.
8. `all-surface-canary` — 10m.
9. `scenario-matrix` — 40m, destructive and once per exact cache key.
10. `baseline-deterministic` — 2m.
11. `baseline-live` — 45m with 192 atomic trials.
12. `baseline-aggregate` — 3m.
13. `candidate-reconciliation` — 5m.
14. `close-readiness` — 3m.

Total: 2h33.

## Pass criteria

- Every validation in `docs/gates/G02/VALIDATIONS.yaml` passes under its assigned layer.
- No pending, `infra_failed`, blocked, open evidence, fallback, unauthorized access, canary hit, or
  duplicate destructive execution remains.
- Three G01 supplemental artifacts are labeled in the future G02 Gate Report.
- No runner, fixture, test framework, threshold, workflow, or product behavior is added in I-0020.
