# EVAL-G02-023 Plan — Exact GetObject Probe Corrective

## Purpose

复用现有测试框架证明三个变化分支：allowed read 使用精确 GetObject；denied read 使用同一
操作并保持 fail closed；write probe 不变。另记录一次真实 `mc` seam proof，确认读取操作
不需要 `ListBucket`。复用入口是 `tests/g02/test_g02_gate_collectors.py`；真实操作由
`docs/runbooks/G02_ISOLATION.md#exact-getobject-seam-proof` 固定，结果写入
`docs/evals/EVAL-G02-023/artifacts/real-seam-proof.json`。

## Cost and execution boundary

- Corrective case count 是三个变化分支，不是 Gate N。
- Gate L2 cell、完整 60-cell matrix、deployment、trace、canary、destructive、external
  service 与 model call 均为 0。
- 不新增专用 evaluator 函数或测试框架；证据只汇总既有 pytest 与定向 real-seam 结果。
- 工程、targeted verification、Gate attempt execution 与 governance sync 分别核算。
