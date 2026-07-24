# EVAL-G02-012 Plan — Third Replacement Unified Candidate Orchestration

## Purpose

在一个 post-I-0026 不可变候选上执行十四个冻结 Gate phases。EVAL-G02-005、008、010
保持永久失败历史；本 Eval 不继承其 blocked phase，也不改写任何旧 artifact。

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

Gate Eval 正常预计 **2h33**，不是 kill timeout。V-G02-003 仍为精确 N=13：九个 G01
manifest 加 EVAL-G02-001 至 EVAL-G02-004。失败与纠错 Evals 不增加冻结 N。

## Pass criteria

- `docs/gates/G02/VALIDATIONS.yaml` 中每项验证按冻结层级和 N 通过。
- 无 pending、`infra_failed`、blocked、waiver、open evidence、fallback、unauthorized access、
  canary hit 或 duplicate destructive execution。
- I-0027 不新增产品行为、runner、fixture、framework、threshold、workflow 或 sample。
- 所有旧 terminal Iteration 与失败 Eval 资产保持不变。
