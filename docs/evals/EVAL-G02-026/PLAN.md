# EVAL-G02-026 Plan — Post-LangSmith Unified Candidate Gate Attempt

## Purpose

在 post-C-G02-002 不可变候选上执行新候选所需的四个 fail-fast preflight、lab binding、
受影响的 access phase 和全部 downstream phases。EVAL-G02-024 的失败和 57 个 passing
cell 永久保留，不复制为新候选 trial。

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

所有冻结 N、阈值、权限、模型 route、token、费用上限和失败语义不变。时间估算只用于
观测与预算，不是 kill timeout。A-G02-002 只编排冻结 runner，不新增实现或测试框架。
