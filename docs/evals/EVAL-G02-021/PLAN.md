# EVAL-G02-021 Plan — Exact GetObject Probe Corrective

## Purpose

在 I-0036 的实现候选上执行三个封闭、确定性的 object-probe case：允许读取使用直接
`GetObject` 且不需要 `ListBucket`；拒绝读取保持 fail closed；write probe 不变。

## Boundaries

- V-G02-009 Iteration N 仍为 4；本 Eval 的三个 case 是 runner 语义分支，不是 Gate matrix N。
- Gate L2 cell、remote deployment、trace、canary、destructive scenario、external service 与
  model call 均为 0。
- 不修改 isolation policy、validation N、threshold、Ground Truth、locked test 或费用上限。
