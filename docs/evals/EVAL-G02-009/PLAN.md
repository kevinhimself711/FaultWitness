# EVAL-G02-009 Plan — Candidate-Bound L2 Collector Corrective

## Purpose

以本地、确定性方式证明 I-0024 补齐了三个 L2 runner 的完整执行路径。本 Eval 不连接
private server、MinIO、PostgreSQL、Redis、LangSmith 或模型服务，也不执行任何 Gate phase。

## Deterministic cases

1. Provisioning plan 绑定 candidate/environment，覆盖四个 principal、五个 prefix、所需
   namespace 与 credential reference，且资产中不含 Secret 值。
2. Access collector 使用 fake live executor 产生并验证精确 60 cells，错误 allow 与缺失
   principal fixture 均 fail closed。
3. Trace collector 产生同一 trace ID 的六个冻结 stage，missing-stage fixture fail closed。
4. Canary collector 枚举 22 个冻结 surface，零 hit 控制通过，leaked-artifact fixture 阻断。
5. 三个 Gate handler 直接调用 runner、逐项原子落盘并绑定 phase cache；缺失/漂移的
   candidate、environment、artifact reference 或 collector capability 不可由操作员裁定通过。

Fake collector 的 60/6/22 枚举只证明 runner contract，不是 Gate L2 样本。验证项的
Iteration N 仍严格为 V-G02-009 的四个 identity policy、V-G02-010 的零次 live stage、
V-G02-011 的四个 writer path；artifact 必须明确记录 Gate L2 execution count 为零。

## Pass criteria

- 五个确定性 case 全部通过；V-G02-009 与 V-G02-011 的 Iteration N 仍分别为 4 和 4。
- `g02.access_matrix`、`g02.stage_matrix`、`g02.canary_matrix` 均有具名 runner、负例 fixture、
  phase interface 和目标 Gate artifact 路径。
- Gate L2 cells、destructive scenarios、external calls 与 model calls 均为零。
- `verify-fast`、`eval-changed` 通过，`open_evidence: []`。
