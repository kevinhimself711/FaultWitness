# EVAL-G02-024 Plan — Unified Candidate Gate Attempt

## Purpose

在一个 post-C-G02-001 不可变候选上执行十四个冻结 Gate phases。所有旧失败 Eval 保持
永久历史；本 attempt 不继承失败结果，也不改写旧 artifact。

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

Gate Eval 正常预计 **2h33**，不是 kill timeout。所有冻结 N、阈值、权限、模型 route、token
与费用上限不变。

## Pass criteria

- `docs/gates/G02/VALIDATIONS.yaml` 中每项验证按冻结层级和 N 通过。
- 无 pending、`infra_failed`、blocked、waiver、open evidence、fallback、unauthorized access、
  canary hit 或 duplicate destructive execution。
- A-G02-001 不新增产品行为、runner、fixture、framework、threshold、workflow 或 sample。
- 失败诊断只能调用冻结的只读 runner/command template；不得现场造工具，失败 artifact 必须
  记录 diagnostic invocation 与 command-construction error 数量。
