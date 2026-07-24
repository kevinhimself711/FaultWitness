# EVAL-G02-008 Plan — Replacement Unified Candidate Orchestration

## Purpose

Evaluate one post-I-0022 G02 candidate with the same fourteen frozen Gate phases. This replaces the
terminal failed EVAL-G02-005 attempt without modifying or deleting it.

## Phase order

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

The Gate Eval estimate remains **2h33** and is never a kill timeout. V-G02-003 remains exactly 13
manifests: nine G01 plus EVAL-G02-001 through EVAL-G02-004. EVAL-G02-005, EVAL-G02-006, and
EVAL-G02-007 are separately referenced forward-history evidence and do not increase the frozen N.

## Pass criteria

- Every validation in `docs/gates/G02/VALIDATIONS.yaml` passes at its unchanged layer and N.
- No pending, `infra_failed`, blocked, waiver, open evidence, fallback, unauthorized access,
  canary hit, or duplicate destructive execution remains.
- EVAL-G02-005 remains immutable and I-0020 remains terminal `failed`.
- I-0023 adds no product behavior, runner, fixture, framework, threshold, workflow, or sample.
